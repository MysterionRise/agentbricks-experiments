# ADR 0003: Cost is a reported number; governance is Unity Catalog

Status: accepted. Date: 2026-10-20.

## Context

A managed agent bills per request through serverless and model-serving SKUs.
Nobody will approve a rollout without a cost per thousand questions, and nobody
will keep it running if that number is a surprise later.

## Decision

### Cost

- `abx cost` reads two system tables through a SQL warehouse:
  `system.serving.endpoint_usage` (requests, tokens, status codes, joined to
  `served_entities` by endpoint name) and `system.billing.usage` joined to
  `system.billing.list_prices` (DBU and list-price USD attributed to the endpoint).
- The number that goes in the report is **USD per 1,000 requests at list price**
  over a 7-day window. Discounts are a Finance conversation; list price is the
  comparable figure.
- When the warehouse is not configured or a query fails, the report says
  "unavailable" with the reason. It never prints zeros that look like data.
- Column names follow the system-table reference; the first real run validates
  them. Until then the cost section is marked unavailable.

### Governance

- The assistant, the volume, the eval dataset and the experiment are Unity
  Catalog objects under one schema. Access is `CAN_QUERY` for the pilot group
  and `CAN_MANAGE` for the service principal that runs the bundle.
- **AI Gateway** on the endpoint: rate limit per user, payload logging to an
  inference table (which also gives the per-request latency the system tables
  lack), and usage tracking on. Configured in the UI for phase 1; a Terraform
  or bundle resource is a phase 2 item once the gateway settings for Agent
  Bricks endpoints are stable in the SDK.
- A **serverless budget policy** is attached to the assistant so its spend is
  tagged and capped separately from notebooks.
- The schema has one named owner. The runbook lists who that is per
  environment.

## Consequences

- The README can show a cost line that a Finance partner can reconcile to the
  bill.
- A spike in `failed_requests` or tokens per request shows up in the weekly
  report before it shows up on the invoice.

## Not decided here

Chargeback across teams, reserved capacity, and whether to pin the model
version behind the assistant. Revisit when the pilot has a month of data.
