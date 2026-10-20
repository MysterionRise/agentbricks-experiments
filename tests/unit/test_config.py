from abx.config import Settings


def test_defaults_compose_paths(settings: Settings):
    assert settings.schema_fqn == "main.ab_demo"
    assert settings.volume_path == "/Volumes/main/ab_demo/ka_data"
    assert settings.knowledge_path == "/Volumes/main/ab_demo/ka_data/knowledge"
    assert settings.reports_path == "/Volumes/main/ab_demo/ka_data/reports"
    assert settings.eval_dataset_fqn == "main.ab_demo.handbook_eval"
    assert settings.request_shape == "responses"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ABX_CATALOG", "sandbox")
    monkeypatch.setenv("ABX_SCHEMA", "team_x")
    monkeypatch.setenv("ABX_REQUEST_SHAPE", "chat")
    monkeypatch.setenv("ABX_SQL_WAREHOUSE_ID", "abc123")
    s = Settings()
    assert s.schema_fqn == "sandbox.team_x"
    assert s.request_shape == "chat"
    assert s.sql_warehouse_id == "abc123"
