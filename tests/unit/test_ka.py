from unittest.mock import MagicMock

import pytest
from databricks.sdk.errors import OperationFailed
from databricks.sdk.service.files import DirectoryEntry
from databricks.sdk.service.knowledgeassistants import (
    FilesSpec,
    KnowledgeAssistant,
    KnowledgeAssistantState,
    KnowledgeSource,
    KnowledgeSourceState,
)
from databricks.sdk.service.serving import (
    EndpointState,
    EndpointStateReady,
    ServingEndpointDetailed,
)
from google.protobuf.timestamp_pb2 import Timestamp

from abx.config import Settings
from abx.ka import (
    DeployError,
    deploy,
    ensure_assistant,
    ensure_files_source,
    newest_file_ms,
    resolve_endpoint_name,
    sync_instructions,
    wait_for_endpoint,
    wait_until_active,
    wait_until_indexed,
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


SOURCE = f"{NAME}/knowledge-sources/1"


def _source(
    state=KnowledgeSourceState.UPDATED,
    cutoff_ms=None,
    path="/Volumes/main/ab_demo/ka_data/knowledge",
):
    cutoff = None
    if cutoff_ms is not None:
        cutoff = Timestamp()
        cutoff.FromMilliseconds(cutoff_ms)
    return KnowledgeSource(
        display_name="handbook",
        description="d",
        source_type="files",
        files=FilesSpec(path=path),
        name=SOURCE,
        state=state,
        knowledge_cutoff_time=cutoff,
    )


def _endpoint(ready=EndpointStateReady.READY):
    return ServingEndpointDetailed(name="ka-abc", state=EndpointState(ready=ready))


def _matching(settings: Settings, **overrides):
    fields = {
        "display_name": settings.ka_display_name,
        "description": settings.ka_description,
        "instructions": settings.ka_instructions,
        "name": NAME,
        "state": KnowledgeAssistantState.ACTIVE,
        "endpoint_name": "ka-abc",
    }
    fields.update(overrides)
    return KnowledgeAssistant(**fields)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 1)


def test_deploy_waits_for_fresh_index_and_ready_endpoint(settings: Settings):
    settings = settings.model_copy(update={"deploy_poll_s": 0})
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [_matching(settings)]
    w.knowledge_assistants.list_knowledge_sources.return_value = [
        _source(path=settings.knowledge_path)
    ]
    w.knowledge_assistants.get_knowledge_assistant.return_value = _matching(settings)
    w.files.list_directory_contents.return_value = [
        DirectoryEntry(path="a.md", last_modified=1_000, is_directory=False),
        DirectoryEntry(path="sub", last_modified=9_999, is_directory=True),
    ]
    # First poll: UPDATED but the cutoff predates the newest file (left over
    # from the previous sync). Second poll: indexed.
    w.knowledge_assistants.get_knowledge_source.side_effect = [
        _source(cutoff_ms=500),
        _source(cutoff_ms=2_000),
    ]
    w.serving_endpoints.wait_get_serving_endpoint_not_updating.return_value = _endpoint()

    got = deploy(w, settings)

    assert got.endpoint_name == "ka-abc"
    w.knowledge_assistants.sync_knowledge_sources.assert_called_once_with(NAME)
    w.knowledge_assistants.update_knowledge_assistant.assert_not_called()
    w.knowledge_assistants.create_knowledge_source.assert_not_called()
    assert w.knowledge_assistants.get_knowledge_source.call_count == 2
    w.serving_endpoints.wait_get_serving_endpoint_not_updating.assert_called_once()


def test_deploy_without_endpoint_raises(settings: Settings):
    settings = settings.model_copy(update={"deploy_poll_s": 0})
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [_matching(settings)]
    w.knowledge_assistants.list_knowledge_sources.return_value = [
        _source(path=settings.knowledge_path)
    ]
    w.knowledge_assistants.get_knowledge_assistant.return_value = _matching(
        settings, endpoint_name=None
    )
    w.files.list_directory_contents.return_value = []
    w.knowledge_assistants.get_knowledge_source.return_value = _source()
    with pytest.raises(DeployError, match="no serving endpoint"):
        deploy(w, settings)


def test_sync_instructions_updates_only_on_drift(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.get_knowledge_assistant.return_value = _matching(settings)
    sync_instructions(w, NAME, settings)
    w.knowledge_assistants.update_knowledge_assistant.assert_not_called()

    w.knowledge_assistants.get_knowledge_assistant.return_value = _matching(
        settings, instructions="old"
    )
    sync_instructions(w, NAME, settings)
    name, body, mask = w.knowledge_assistants.update_knowledge_assistant.call_args.args
    assert name == NAME
    assert body.instructions == settings.ka_instructions
    assert mask.ToJsonString() == "instructions,description"


def test_newest_file_ms_ignores_directories():
    w = MagicMock()
    w.files.list_directory_contents.return_value = [
        DirectoryEntry(path="a", last_modified=5, is_directory=False),
        DirectoryEntry(path="b", last_modified=7, is_directory=False),
        DirectoryEntry(path="d", last_modified=99, is_directory=True),
    ]
    assert newest_file_ms(w, "/x") == 7
    w.files.list_directory_contents.return_value = []
    assert newest_file_ms(w, "/x") is None


def test_failed_update_raises_naming_the_source(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_sources.return_value = [_source()]
    w.knowledge_assistants.get_knowledge_source.return_value = _source(
        KnowledgeSourceState.FAILED_UPDATE
    )
    with pytest.raises(DeployError, match=r"knowledge-sources/1 failed to update"):
        wait_until_indexed(w, NAME, 1_000, settings, sleep=lambda _: None)


def test_stale_cutoff_times_out(settings: Settings):
    settings = settings.model_copy(update={"deploy_timeout_s": 3, "deploy_poll_s": 1})
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_sources.return_value = [_source()]
    w.knowledge_assistants.get_knowledge_source.return_value = _source(cutoff_ms=10)
    clock = FakeClock()
    with pytest.raises(DeployError, match="not indexed after 3s"):
        wait_until_indexed(w, NAME, 1_000, settings, sleep=clock.sleep, clock=clock)


def test_freshness_check_can_be_disabled(settings: Settings):
    settings = settings.model_copy(update={"deploy_require_fresh_index": False})
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_sources.return_value = [_source()]
    w.knowledge_assistants.get_knowledge_source.return_value = _source(cutoff_ms=None)
    wait_until_indexed(w, NAME, 1_000, settings, sleep=lambda _: None)


def test_assistant_without_sources_raises(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_sources.return_value = []
    with pytest.raises(DeployError, match="no knowledge sources"):
        wait_until_indexed(w, NAME, None, settings, sleep=lambda _: None)


def test_endpoint_not_ready_raises():
    w = MagicMock()
    w.serving_endpoints.wait_get_serving_endpoint_not_updating.return_value = _endpoint(
        EndpointStateReady.NOT_READY
    )
    with pytest.raises(DeployError, match="not READY"):
        wait_for_endpoint(w, "ka-abc", 60)


@pytest.mark.parametrize("error", [OperationFailed("UPDATE_FAILED"), TimeoutError("slow")])
def test_endpoint_wait_errors_become_deploy_errors(error):
    w = MagicMock()
    w.serving_endpoints.wait_get_serving_endpoint_not_updating.side_effect = error
    with pytest.raises(DeployError, match="did not finish updating"):
        wait_for_endpoint(w, "ka-abc", 60)
    timeout = w.serving_endpoints.wait_get_serving_endpoint_not_updating.call_args.kwargs["timeout"]
    assert timeout.total_seconds() == 60


def test_resolve_endpoint_name(settings: Settings):
    w = MagicMock()
    w.knowledge_assistants.list_knowledge_assistants.return_value = [_assistant()]
    assert resolve_endpoint_name(w, settings) == "ka-abc"
    assert resolve_endpoint_name(w, settings.model_copy(update={"endpoint_name": "mine"})) == "mine"
    w.knowledge_assistants.list_knowledge_assistants.return_value = []
    with pytest.raises(DeployError, match="abx deploy"):
        resolve_endpoint_name(w, settings)
