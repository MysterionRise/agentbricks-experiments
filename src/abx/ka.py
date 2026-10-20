"""Idempotent deployment of the Knowledge Assistant through the Databricks SDK.

Running ``deploy`` twice yields one assistant with one files source, not two.
The assistant is found by display name, so the name is the identity.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from databricks.sdk.service.knowledgeassistants import (
    FilesSpec,
    KnowledgeAssistant,
    KnowledgeAssistantState,
    KnowledgeSource,
)

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


def deploy(w: WorkspaceClient, settings: Settings) -> KnowledgeAssistant:
    """Create or reuse the assistant, attach the corpus, sync, and wait for ACTIVE."""
    assistant = ensure_assistant(w, settings)
    if assistant.name is None:
        msg = "assistant has no resource name"
        raise DeployError(msg)
    ensure_files_source(w, assistant.name, settings)
    w.knowledge_assistants.sync_knowledge_sources(assistant.name)
    return wait_until_active(
        w, assistant.name, timeout_s=settings.deploy_timeout_s, poll_s=settings.deploy_poll_s
    )


def resolve_endpoint_name(w: WorkspaceClient, settings: Settings) -> str:
    """The serving endpoint to evaluate: an override, else the deployed assistant's."""
    if settings.endpoint_name:
        return settings.endpoint_name
    assistant = find_assistant(w, settings.ka_display_name)
    if assistant is None or not assistant.endpoint_name:
        msg = f"no endpoint for assistant {settings.ka_display_name!r}; run `abx deploy` first"
        raise DeployError(msg)
    return assistant.endpoint_name
