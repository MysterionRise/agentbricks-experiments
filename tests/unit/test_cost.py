from unittest.mock import MagicMock

import pytest
from databricks.sdk.service.sql import (
    ResultData,
    ServiceError,
    StatementResponse,
    StatementState,
    StatementStatus,
)

from abx.config import Settings
from abx.cost import BILLING_SQL, USAGE_SQL, CostSummary, fetch_cost


def _ok(row):
    return StatementResponse(
        statement_id="s",
        status=StatementStatus(state=StatementState.SUCCEEDED),
        result=ResultData(data_array=[row]),
    )


def test_no_warehouse_is_unavailable(settings: Settings):
    c = fetch_cost(MagicMock(), settings, "ep")
    assert not c.available
    assert "ABX_SQL_WAREHOUSE_ID" in c.note
    assert c.usd_per_1k_requests is None


def test_fetch_cost_parses_rows(settings: Settings):
    settings = settings.model_copy(update={"sql_warehouse_id": "wh"})
    w = MagicMock()
    w.statement_execution.execute_statement.side_effect = [
        _ok(["120", "5000", "9000", "3"]),
        _ok(["4.5", "3.6", "14"]),
    ]
    c = fetch_cost(w, settings, "ep")
    assert c.available
    assert (c.requests, c.failed_requests, c.input_tokens, c.output_tokens) == (120, 3, 5000, 9000)
    assert c.dbu == 4.5 and c.usd_list == 3.6
    assert c.usd_per_1k_requests == pytest.approx(30.0)
    params = w.statement_execution.execute_statement.call_args.kwargs["parameters"]
    assert {p.name: p.value for p in params} == {"endpoint_name": "ep", "window_days": "7"}


def test_fetch_cost_failed_statement(settings: Settings):
    settings = settings.model_copy(update={"sql_warehouse_id": "wh"})
    w = MagicMock()
    w.statement_execution.execute_statement.return_value = StatementResponse(
        statement_id="s",
        status=StatementStatus(state=StatementState.FAILED, error=ServiceError(message="no table")),
    )
    c = fetch_cost(w, settings, "ep")
    assert not c.available
    assert "no table" in c.note


def test_fetch_cost_empty_result_is_unavailable_not_zero(settings: Settings):
    settings = settings.model_copy(update={"sql_warehouse_id": "wh"})
    w = MagicMock()
    w.statement_execution.execute_statement.return_value = StatementResponse(
        statement_id="s",
        status=StatementStatus(state=StatementState.SUCCEEDED),
        result=ResultData(),
    )
    c = fetch_cost(w, settings, "ep")
    assert not c.available
    assert "no rows in system.serving.endpoint_usage" in c.note
    assert "no billing rows" in c.note


def test_zero_usage_with_billing_is_unavailable(settings: Settings):
    """Agent endpoints may record billing but no usage rows: no per-request figure."""
    settings = settings.model_copy(update={"sql_warehouse_id": "wh"})
    w = MagicMock()
    w.statement_execution.execute_statement.side_effect = [
        _ok(["0", "0", "0", "0"]),
        _ok(["2.0", "1.5", "3"]),
    ]
    c = fetch_cost(w, settings, "ep")
    assert not c.available
    assert "endpoint_usage" in c.note and "ADR 0003" in c.note
    assert "no billing rows" not in c.note


def test_sql_is_valid_spark_and_does_not_multiply_rows():
    for sql in (USAGE_SQL, BILLING_SQL):
        assert "INTERVAL :" not in sql
        assert "make_dt_interval(:window_days)" in sql
    assert "JOIN system.serving.served_entities" not in USAGE_SQL
    assert "served_entity_id IN (" in USAGE_SQL
    assert "billing_rows" in BILLING_SQL


def test_as_dict_has_derived_metric():
    c = CostSummary("ep", 7, True, requests=10, usd_list=1.0)
    assert c.as_dict()["usd_per_1k_requests"] == 100.0
