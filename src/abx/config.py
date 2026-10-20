"""Settings for every abx command.

Everything is overridable from the environment with an ``ABX_`` prefix
(``ABX_CATALOG=dev_sandbox``), or from a local ``.env`` that is never committed.
The Asset Bundle passes the same values as job parameters, so a workspace run and
a laptop run resolve identical names.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from abx.seed import RequestShape


class Settings(BaseSettings):
    """Names of every Unity Catalog and MLflow object the project touches."""

    model_config = SettingsConfigDict(env_prefix="ABX_", env_file=".env", extra="ignore")

    catalog: str = "main"
    schema_name: str = Field(default="ab_demo", alias="ABX_SCHEMA")
    volume: str = "ka_data"

    ka_display_name: str = "halcyon-handbook-ka"
    ka_description: str = "Answers questions about the Halcyon Freight employee handbook."
    ka_instructions: str = (
        "You answer questions strictly from the Halcyon Freight handbook documents. "
        "Cite the document you used. If the handbook does not cover the question, say so "
        "plainly and do not guess."
    )

    eval_dataset: str = "handbook_eval"
    experiment_path: str = "/Shared/abx/handbook-ka"

    # Optional. The deployed endpoint name is read back from the assistant after
    # creation; set this only to evaluate an endpoint the project did not create.
    endpoint_name: str | None = None
    # Payload shape of the endpoint: Knowledge Assistants take a Responses-style
    # `input` list. Confirm with Playground → Get code; see docs/runbook.md.
    request_shape: RequestShape = "responses"

    # Needed by `abx cost`; system tables are queried through a SQL warehouse.
    sql_warehouse_id: str | None = None
    cost_window_days: int = 7

    # Deploy polling
    deploy_timeout_s: int = 1800
    deploy_poll_s: int = 20

    @property
    def schema_fqn(self) -> str:
        """``catalog.schema``."""
        return f"{self.catalog}.{self.schema_name}"

    @property
    def volume_path(self) -> str:
        """Root of the UC volume as a ``/Volumes`` path."""
        return f"/Volumes/{self.catalog}/{self.schema_name}/{self.volume}"

    @property
    def knowledge_path(self) -> str:
        """Folder the Knowledge Assistant ingests."""
        return f"{self.volume_path}/knowledge"

    @property
    def reports_path(self) -> str:
        """Folder the eval and cost jobs write their markdown report to."""
        return f"{self.volume_path}/reports"

    @property
    def eval_dataset_fqn(self) -> str:
        """Three-part name of the MLflow evaluation dataset in Unity Catalog."""
        return f"{self.schema_fqn}.{self.eval_dataset}"
