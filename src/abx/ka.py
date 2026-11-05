"""Idempotent deployment of the Knowledge Assistant through the Databricks SDK.

Running ``deploy`` twice yields one assistant with one files source, not two.
The assistant is found by display name, so the name is the identity.

``deploy`` returns only when the assistant can be evaluated honestly: it is
ACTIVE, every knowledge source has indexed the current files, and its serving
endpoint is READY. An ACTIVE assistant alone is not enough: a sync does not move
the assistant out of ACTIVE, so an evaluation could otherwise hit a stale index.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from databricks.sdk.common.types.fieldmask import FieldMask
from databricks.sdk.errors import OperationFailed
from databricks.sdk.service.knowledgeassistants import (
    FilesSpec,
    KnowledgeAssistant,
    KnowledgeAssistantState,
    KnowledgeSource,
    KnowledgeSourceState,
)
from databricks.sdk.service.serving import EndpointStateReady

if TYPE_CHECKING:
    from collections.abc import Callable

    from databricks.sdk import WorkspaceClient

    from abx.config import Settings

log = logging.getLogger(__name__)

FILES_SOURCE_TYPE = "files"


class DeployError(RuntimeError):
    """The assistant did not reach ACTIVE, or has no endpoint."""


def find_assistant(w: WorkspaceClient, display_name: str) -> KnowledgeAssistant | None:
    """Return the assistant with this display name, or None."""
    for assistant in w.knowledge_assistants.list_knowledge_assistants():
        if assistant.display_name == display_name:
            return assistant
    return None


def ensure_assistant(w: WorkspaceClient, settings: Settings) -> KnowledgeAssistant:
    """Create the assistant if missing; return the existing one otherwise."""
    existing = find_assistant(w, settings.ka_display_name)
    if existing is not None:
        log.info("assistant exists: %s (%s)", existing.display_name, existing.name)
        return existing
    log.info("creating assistant %s", settings.ka_display_name)
    return w.knowledge_assistants.create_knowledge_assistant(
        KnowledgeAssistant(
            display_name=settings.ka_display_name,
            description=settings.ka_description,
            instructions=settings.ka_instructions,
        )
    )


def ensure_files_source(
    w: WorkspaceClient, assistant_name: str, settings: Settings
) -> KnowledgeSource:
    """Attach the knowledge folder as a files source once."""
    for source in w.knowledge_assistants.list_knowledge_sources(assistant_name):
        if source.files is not None and source.files.path == settings.knowledge_path:
            log.info("files source exists: %s", source.name)
            return source
    log.info("adding files source %s", settings.knowledge_path)
    return w.knowledge_assistants.create_knowledge_source(
        assistant_name,
        KnowledgeSource(
            display_name="handbook",
            description="Halcyon Freight handbook markdown files",
            source_type=FILES_SOURCE_TYPE,
            files=FilesSpec(path=settings.knowledge_path),
        ),
    )


def wait_until_active(
    w: WorkspaceClient,
    assistant_name: str,
    timeout_s: int,
    poll_s: int,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> KnowledgeAssistant:
    """Poll until the assistant is ACTIVE. FAILED or timeout raises DeployError."""
    deadline = clock() + timeout_s
    while True:
        assistant = w.knowledge_assistants.get_knowledge_assistant(assistant_name)
        state = assistant.state
        log.info("assistant %s state=%s", assistant_name, state)
        if state == KnowledgeAssistantState.ACTIVE:
            return assistant
        if state == KnowledgeAssistantState.FAILED:
            detail = assistant.error_info or "no error_info returned"
            msg = f"assistant {assistant_name} failed: {detail}"
            raise DeployError(msg)
        if clock() >= deadline:
            msg = f"assistant {assistant_name} not ACTIVE after {timeout_s}s (state={state})"
            raise DeployError(msg)
        sleep(poll_s)


def sync_instructions(
    w: WorkspaceClient, assistant_name: str, settings: Settings
) -> KnowledgeAssistant:
    """Bring instructions and description in line with settings; return the assistant.

    Reads the assistant with ``get`` (list results may omit fields) and updates
    only when something differs, so an unchanged deploy writes nothing.
    """
    current = w.knowledge_assistants.get_knowledge_assistant(assistant_name)
    if (
        current.instructions == settings.ka_instructions
        and current.description == settings.ka_description
    ):
        return current
    log.info("updating instructions and description of %s", assistant_name)
    return w.knowledge_assistants.update_knowledge_assistant(
        assistant_name,
        KnowledgeAssistant(
            display_name=settings.ka_display_name,
            description=settings.ka_description,
            instructions=settings.ka_instructions,
        ),
        # A list, not a string: FieldMask joins its paths with commas.
        FieldMask(field_mask=["instructions", "description"]),  # type: ignore[no-untyped-call]
    )


def newest_file_ms(w: WorkspaceClient, path: str) -> int | None:
    """Last-modified time, in epoch milliseconds, of the newest file under ``path``."""
    times = [
        entry.last_modified
        for entry in w.files.list_directory_contents(path)
        if not entry.is_directory and entry.last_modified is not None
    ]
    return max(times) if times else None


def _source_ready(source: KnowledgeSource, newest_ms: int | None, require_fresh: bool) -> bool:
    if source.state != KnowledgeSourceState.UPDATED:
        return False
    if not require_fresh or newest_ms is None:
        return True
    cutoff = source.knowledge_cutoff_time
    return cutoff is not None and cutoff.ToMilliseconds() >= newest_ms


def wait_until_indexed(
    w: WorkspaceClient,
    assistant_name: str,
    newest_ms: int | None,
    settings: Settings,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Wait until every knowledge source has ingested the current files.

    A source is ready when it is UPDATED and its knowledge cutoff is no older than
    the newest file in the volume; the cutoff check guards against reading an
    UPDATED state left over from the previous sync. ``FAILED_UPDATE`` raises.
    """
    deadline = clock() + settings.deploy_timeout_s
    while True:
        names = [s.name for s in w.knowledge_assistants.list_knowledge_sources(assistant_name)]
        if not names:
            msg = f"assistant {assistant_name} has no knowledge sources"
            raise DeployError(msg)
        pending: list[str] = []
        for name in names:
            if name is None:
                continue
            source = w.knowledge_assistants.get_knowledge_source(name)
            if source.state == KnowledgeSourceState.FAILED_UPDATE:
                msg = f"knowledge source {name} failed to update (FAILED_UPDATE)"
                raise DeployError(msg)
            if not _source_ready(source, newest_ms, settings.deploy_require_fresh_index):
                pending.append(f"{name}={source.state}")
        if not pending:
            return
        log.info("waiting for indexing: %s", ", ".join(pending))
        if clock() >= deadline:
            msg = (
                f"knowledge sources not indexed after {settings.deploy_timeout_s}s: "
                f"{', '.join(pending)}"
            )
            raise DeployError(msg)
        sleep(settings.deploy_poll_s)


def wait_for_endpoint(w: WorkspaceClient, endpoint_name: str, timeout_s: int) -> None:
    """Wait until the serving endpoint has no update in progress and is READY."""
    try:
        endpoint = w.serving_endpoints.wait_get_serving_endpoint_not_updating(
            endpoint_name, timeout=timedelta(seconds=timeout_s)
        )
    except (OperationFailed, TimeoutError) as exc:
        msg = f"endpoint {endpoint_name} did not finish updating: {exc}"
        raise DeployError(msg) from exc
    ready = endpoint.state.ready if endpoint.state is not None else None
    if ready != EndpointStateReady.READY:
        msg = f"endpoint {endpoint_name} is not READY (ready={ready})"
        raise DeployError(msg)


def deploy(w: WorkspaceClient, settings: Settings) -> KnowledgeAssistant:
    """Create or reuse the assistant and return once it can be evaluated."""
    assistant = ensure_assistant(w, settings)
    if assistant.name is None:
        msg = "assistant has no resource name"
        raise DeployError(msg)
    name = assistant.name
    ensure_files_source(w, name, settings)
    sync_instructions(w, name, settings)
    newest_ms = newest_file_ms(w, settings.knowledge_path)
    w.knowledge_assistants.sync_knowledge_sources(name)
    assistant = wait_until_active(
        w, name, timeout_s=settings.deploy_timeout_s, poll_s=settings.deploy_poll_s
    )
    wait_until_indexed(w, name, newest_ms, settings)
    if not assistant.endpoint_name:
        msg = f"assistant {name} is ACTIVE but has no serving endpoint"
        raise DeployError(msg)
    wait_for_endpoint(w, assistant.endpoint_name, settings.deploy_timeout_s)
    return assistant


def resolve_endpoint_name(w: WorkspaceClient, settings: Settings) -> str:
    """The serving endpoint to evaluate: an override, else the deployed assistant's."""
    if settings.endpoint_name:
        return settings.endpoint_name
    assistant = find_assistant(w, settings.ka_display_name)
    if assistant is None or not assistant.endpoint_name:
        msg = f"no endpoint for assistant {settings.ka_display_name!r}; run `abx deploy` first"
        raise DeployError(msg)
    return assistant.endpoint_name
