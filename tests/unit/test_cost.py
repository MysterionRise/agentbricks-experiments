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
from abx.cost import CostSummary, fetch_cost


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
        _ok(["4.5", "3.6"]),
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


def test_fetch_cost_empty_result(settings: Settings):
    settings = settings.model_copy(update={"sql_warehouse_id": "wh"})
    w = MagicMock()
    w.statement_execution.execute_statement.return_value = StatementResponse(
        statement_id="s",
        status=StatementStatus(state=StatementState.SUCCEEDED),
        result=ResultData(),
    )
    c = fetch_cost(w, settings, "ep")
    assert c.available and c.requests == 0 and c.usd_per_1k_requests is None


def test_as_dict_has_derived_metric():
    c = CostSummary("ep", 7, True, requests=10, usd_list=1.0)
    assert c.as_dict()["usd_per_1k_requests"] == 100.0
