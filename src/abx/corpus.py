"""Load the handbook corpus from the repo and place it in a Unity Catalog volume."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from databricks.sdk.errors import NotFound
from databricks.sdk.service.catalog import VolumeType

if TYPE_CHECKING:
    from pathlib import Path

    from databricks.sdk import WorkspaceClient

    from abx.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorpusDoc:
    """One markdown document destined for the knowledge folder."""

    name: str
    text: str


def load_corpus(path: Path) -> list[CorpusDoc]:
    """Read every ``*.md`` under ``path`` in name order."""
    docs = [
        CorpusDoc(name=p.name, text=p.read_text(encoding="utf-8"))
        for p in sorted(path.glob("*.md"))
    ]
    if not docs:
        msg = f"no markdown documents under {path}"
        raise FileNotFoundError(msg)
    return docs


def ensure_schema_and_volume(w: WorkspaceClient, settings: Settings) -> None:
    """Create the schema and the managed volume if they do not exist."""
    try:
        w.schemas.get(settings.schema_fqn)
        log.info("schema exists: %s", settings.schema_fqn)
    except NotFound:
        log.info("creating schema %s", settings.schema_fqn)
        w.schemas.create(name=settings.schema_name, catalog_name=settings.catalog)

    volume_fqn = f"{settings.schema_fqn}.{settings.volume}"
    try:
        w.volumes.read(volume_fqn)
        log.info("volume exists: %s", volume_fqn)
    except NotFound:
        log.info("creating volume %s", volume_fqn)
        w.volumes.create(
            catalog_name=settings.catalog,
            schema_name=settings.schema_name,
            name=settings.volume,
            volume_type=VolumeType.MANAGED,
            comment="Knowledge Assistant corpus and reports (abx)",
        )


def upload_corpus(w: WorkspaceClient, settings: Settings, docs: list[CorpusDoc]) -> list[str]:
    """Upload every document into the knowledge folder, overwriting. Returns volume paths."""
    w.files.create_directory(settings.knowledge_path)
    w.files.create_directory(settings.reports_path)
    uploaded: list[str] = []
    for doc in docs:
        target = f"{settings.knowledge_path}/{doc.name}"
        w.files.upload(target, io.BytesIO(doc.text.encode("utf-8")), overwrite=True)
        uploaded.append(target)
    log.info("uploaded %d documents to %s", len(uploaded), settings.knowledge_path)
    return uploaded
