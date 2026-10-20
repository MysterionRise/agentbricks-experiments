"""Cost and usage of the serving endpoint from Databricks system tables.

Two queries through a SQL warehouse:

* ``system.serving.endpoint_usage`` joined to ``system.serving.served_entities``
  for request and token counts;
* ``system.billing.usage`` joined to ``system.billing.list_prices`` for DBU and
  list-price USD attributed to the endpoint.

Column names follow the system table reference. The first real run validates
them; until then ``CostSummary.available`` is False and the report says so
rather than printing zeros.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from databricks.sdk.service.sql import (
    StatementParameterListItem,
    StatementState,
)

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

    from abx.config import Settings

log = logging.getLogger(__name__)

USAGE_SQL = """
SELECT
  COUNT(*)                                          AS requests,
  COALESCE(SUM(u.input_token_count), 0)             AS input_tokens,
  COALESCE(SUM(u.output_token_count), 0)            AS output_tokens,
  SUM(CASE WHEN u.status_code <> 200 THEN 1 ELSE 0 END) AS failed_requests
FROM system.serving.endpoint_usage u
JOIN system.serving.served_entities e
  ON u.served_entity_id = e.served_entity_id
WHERE e.endpoint_name = :endpoint_name
  AND u.request_time >= CURRENT_TIMESTAMP() - INTERVAL :window_days DAYS
"""

BILLING_SQL = """
SELECT
  COALESCE(SUM(b.usage_quantity), 0)                       AS dbu,
  COALESCE(SUM(b.usage_quantity * p.pricing.default), 0)   AS usd_list
FROM system.billing.usage b
LEFT JOIN system.billing.list_prices p
  ON b.sku_name = p.sku_name
 AND b.cloud = p.cloud
 AND b.usage_start_time >= p.price_start_time
 AND (p.price_end_time IS NULL OR b.usage_start_time < p.price_end_time)
WHERE b.usage_metadata.endpoint_name = :endpoint_name
  AND b.usage_start_time >= CURRENT_TIMESTAMP() - INTERVAL :window_days DAYS
"""


@dataclass(frozen=True)
class CostSummary:
    """Usage and cost over the window. ``available`` is False when queries failed."""

    endpoint_name: str
    window_days: int
    available: bool
    note: str = ""
    requests: int = 0
    failed_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    dbu: float = 0.0
    usd_list: float = 0.0

    @property
    def usd_per_1k_requests(self) -> float | None:
        """List-price cost per thousand requests, or None without traffic."""
        if not self.available or self.requests == 0:
            return None
        return self.usd_list / self.requests * 1000

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly form."""
        return {
            "endpoint_name": self.endpoint_name,
            "window_days": self.window_days,
            "available": self.available,
            "note": self.note,
            "requests": self.requests,
            "failed_requests": self.failed_requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "dbu": self.dbu,
            "usd_list": self.usd_list,
            "usd_per_1k_requests": self.usd_per_1k_requests,
        }


class CostQueryError(RuntimeError):
    """A system-table query did not succeed."""


def _run_query(
    w: WorkspaceClient, warehouse_id: str, sql: str, endpoint_name: str, window_days: int
) -> list[Any]:
    """Execute one statement synchronously and return the first row's values."""
    response = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        parameters=[
            StatementParameterListItem(name="endpoint_name", value=endpoint_name),
            StatementParameterListItem(name="window_days", value=str(window_days), type="INT"),
        ],
        wait_timeout="50s",
    )
    status = response.status
    if status is None or status.state != StatementState.SUCCEEDED:
        detail = status.error.message if status and status.error else "unknown"
        msg = f"statement {response.statement_id} state={getattr(status, 'state', None)}: {detail}"
        raise CostQueryError(msg)
    data = response.result.data_array if response.result else None
    if not data:
        return []
    return list(data[0])


def _int(value: object) -> int:
    return int(str(value)) if value is not None else 0


def _float(value: object) -> float:
    return float(str(value)) if value is not None else 0.0


def fetch_cost(w: WorkspaceClient, settings: Settings, endpoint_name: str) -> CostSummary:
    """Query both tables. Any failure yields an unavailable summary with the reason."""
    if not settings.sql_warehouse_id:
        return CostSummary(
            endpoint_name,
            settings.cost_window_days,
            available=False,
            note="ABX_SQL_WAREHOUSE_ID not set; system tables need a SQL warehouse",
        )
    try:
        usage = _run_query(
            w, settings.sql_warehouse_id, USAGE_SQL, endpoint_name, settings.cost_window_days
        )
        billing = _run_query(
            w, settings.sql_warehouse_id, BILLING_SQL, endpoint_name, settings.cost_window_days
        )
    except Exception as exc:
        log.warning("cost query failed: %s", exc)
        return CostSummary(endpoint_name, settings.cost_window_days, available=False, note=str(exc))

    requests, input_tokens, output_tokens, failed = [*usage, 0, 0, 0, 0][:4]
    dbu, usd_list = [*billing, 0.0, 0.0][:2]
    return CostSummary(
        endpoint_name=endpoint_name,
        window_days=settings.cost_window_days,
        available=True,
        requests=_int(requests),
        failed_requests=_int(failed),
        input_tokens=_int(input_tokens),
        output_tokens=_int(output_tokens),
        dbu=_float(dbu),
        usd_list=_float(usd_list),
    )
