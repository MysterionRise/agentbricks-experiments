from pathlib import Path
from unittest.mock import MagicMock

import pytest
from databricks.sdk.errors import NotFound

from abx.config import Settings
from abx.corpus import ensure_schema_and_volume, load_corpus, upload_corpus


def test_repo_corpus_loads(repo_root: Path):
    docs = load_corpus(repo_root / "data" / "corpus")
    assert len(docs) >= 10
    assert docs[0].name.startswith("00-")
    assert all(d.text.startswith("# ") for d in docs)


def test_empty_corpus_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_corpus(tmp_path)


def test_ensure_creates_missing_objects(settings: Settings):
    w = MagicMock()
    w.schemas.get.side_effect = NotFound("no schema")
    w.volumes.read.side_effect = NotFound("no volume")
    ensure_schema_and_volume(w, settings)
    w.schemas.create.assert_called_once_with(name="ab_demo", catalog_name="main")
    kwargs = w.volumes.create.call_args.kwargs
    assert (kwargs["catalog_name"], kwargs["schema_name"], kwargs["name"]) == (
        "main",
        "ab_demo",
        "ka_data",
    )


def test_ensure_is_noop_when_present(settings: Settings):
    w = MagicMock()
    ensure_schema_and_volume(w, settings)
    w.schemas.create.assert_not_called()
    w.volumes.create.assert_not_called()


def test_upload_writes_every_doc(settings: Settings, tmp_path: Path):
    (tmp_path / "a.md").write_text("# A")
    (tmp_path / "b.md").write_text("# B")
    w = MagicMock()
    paths = upload_corpus(w, settings, load_corpus(tmp_path))
    assert paths == [f"{settings.knowledge_path}/a.md", f"{settings.knowledge_path}/b.md"]
    assert w.files.upload.call_count == 2
    first_call = w.files.upload.call_args_list[0]
    assert first_call.args[0].endswith("/a.md")
    assert first_call.args[1].read() == b"# A"
    assert first_call.kwargs == {"overwrite": True}
