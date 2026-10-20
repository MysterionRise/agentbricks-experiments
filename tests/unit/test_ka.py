from unittest.mock import MagicMock

import pytest
from databricks.sdk.service.knowledgeassistants import (
    FilesSpec,
    KnowledgeAssistant,
    KnowledgeAssistantState,
    KnowledgeSource,
)

from abx.config import Settings
from abx.ka import (
    DeployError,
    deploy,
    ensure_assistant,
    ensure_files_source,
    resolve_endpoint_name,
    wait_until_active,
)

NAME = "knowledge-assistants/abc"


def _assistant(
    state=KnowledgeAssistantState.ACTIVE, endpoint="ka-abc", display="halcyon-handbook-ka"
):
    return KnowledgeAssistant(
        display_name=display, description="d", name=NAME, state=state, endpoint_name=endpoint
    )


def test_ensure_assistant_reuses_existing(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [
        _assistant(display="other"),
        _assistant(),
    ]
    got = ensure_assistant(w, settings)
    assert got.name == NAME
    w.knowledge_assistants.create_knowledge_assistant.assert_not_called()


def test_ensure_assistant_creates_when_absent(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = []
    w.knowledge_assistants.create_knowledge_assistant.return_value = _assistant()
    ensure_assistant(w, settings)
    created = w.knowledge_assistants.create_knowledge_assistant.call_args.args[0]
    assert created.display_name == settings.ka_display_name
    assert created.instructions == settings.ka_instructions


def test_ensure_files_source_idempotent(settings: Settings):
    w = MagicMock()
    existing = KnowledgeSource(
        display_name="handbook",
        description="d",
        source_type="files",
        files=FilesSpec(path=settings.knowledge_path),
        name=f"{NAME}/knowledge-sources/1",
    )
    w.knowledge_assistants.list_knowledge_sources.return_value = [existing]
    assert ensure_files_source(w, NAME, settings) is existing
    w.knowledge_assistants.create_knowledge_source.assert_not_called()

    w.knowledge_assistants.list_knowledge_sources.return_value = []
    ensure_files_source(w, NAME, settings)
    parent, source = w.knowledge_assistants.create_knowledge_source.call_args.args
    assert parent == NAME
    assert source.source_type == "files"
    assert source.files.path == settings.knowledge_path


def test_wait_until_active_polls_then_returns():
    w = MagicMock()
    w.knowledge_assistants.get_knowledge_assistant.side_effect = [
        _assistant(KnowledgeAssistantState.CREATING),
        _assistant(KnowledgeAssistantState.CREATING),
        _assistant(KnowledgeAssistantState.ACTIVE),
    ]
    sleeps: list[float] = []
    got = wait_until_active(
        w, NAME, timeout_s=100, poll_s=5, sleep=sleeps.append, clock=lambda: 0.0
    )
    assert got.state == KnowledgeAssistantState.ACTIVE
    assert sleeps == [5, 5]


def test_wait_until_active_failed_state():
    w = MagicMock()
    failed = _assistant(KnowledgeAssistantState.FAILED)
    failed.error_info = "quota"
    w.knowledge_assistants.get_knowledge_assistant.return_value = failed
    with pytest.raises(DeployError, match="quota"):
        wait_until_active(w, NAME, timeout_s=10, poll_s=1, sleep=lambda _: None)


def test_wait_until_active_timeout():
    w = MagicMock()
    w.knowledge_assistants.get_knowledge_assistant.return_value = _assistant(
        KnowledgeAssistantState.CREATING
    )
    ticks = iter([0.0, 5.0, 11.0])
    with pytest.raises(DeployError, match="not ACTIVE after 10s"):
        wait_until_active(
            w, NAME, timeout_s=10, poll_s=1, sleep=lambda _: None, clock=lambda: next(ticks)
        )


def test_deploy_orchestrates(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [
        _assistant(KnowledgeAssistantState.CREATING)
    ]
    w.knowledge_assistants.list_knowledge_sources.return_value = []
    w.knowledge_assistants.get_knowledge_assistant.return_value = _assistant()
    settings = settings.model_copy(update={"deploy_poll_s": 0})
    got = deploy(w, settings)
    assert got.endpoint_name == "ka-abc"
    w.knowledge_assistants.sync_knowledge_sources.assert_called_once_with(NAME)


def test_resolve_endpoint_name(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [_assistant()]
    assert resolve_endpoint_name(w, settings) == "ka-abc"
    assert resolve_endpoint_name(w, settings.model_copy(update={"endpoint_name": "mine"})) == "mine"
    w.knowledge_assistants.list_knowledge_assistants.return_value = []
    with pytest.raises(DeployError, match="abx deploy"):
        resolve_endpoint_name(w, settings)
