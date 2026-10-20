# ADR 0001: Use Agent Bricks Knowledge Assistant for document Q&A

Status: accepted. Date: 2026-10-20.

## Context

We need an assistant that answers employee questions from a set of policy
documents, with citations, that can be rebuilt from code and shown to be good
before anyone depends on it. Three ways to get there on Databricks:

1. **Agent Bricks Knowledge Assistant.** Managed retrieval, generation, and
   serving. Configuration is a volume path, instructions, and optional examples.
2. **Mosaic AI Agent Framework.** We write the agent (retriever, prompt, tool
   loop) in Python, log it with MLflow, and deploy it to Model Serving.
3. **Own stack** (LangGraph or similar) on Model Serving or Databricks Apps,
   with Vector Search for retrieval.

## Decision

Option 1 for this use case. The agent is a commodity here; the work that
matters is around it (data, evaluation, cost, governance), and option 1 lets us
spend our effort there.

## Reasons

- **Time to a measurable baseline.** A deployed endpoint in under an hour means
  the eval harness, not the agent, is the first thing built. That ordering keeps
  the team honest.
- **Quality floor.** Databricks reports a retrieval approach tuned for this
  shape of problem. We do not have to believe that; the gate measures it.
- **Operations.** Scaling, model upgrades, and the chat protocol are not ours.
- **Governance comes free.** The assistant is a Unity Catalog object with
  permissions, and the endpoint sits behind AI Gateway.

## Costs of this decision

- **Opacity.** We cannot see or change the prompt, the chunking, or the
  reranker. When quality is off, our levers are the corpus, the instructions,
  and examples. That is a real constraint; ADR 0002 makes it tolerable by
  measuring the outcome, not the mechanism.
- **Lock-in.** Covered in ADR 0004. The eval dataset, the corpus and the gate
  survive a move; the assistant does not.
- **Beta exposure.** Knowledge Assistant is GA; other Agent Bricks types are
  not. `docs/status.md` tracks this.

## When we would choose otherwise

- The agent needs tools beyond retrieval (write actions, multi-step plans).
  Phase 2 adds a Supervisor Agent for exactly that; if that proves too
  constrained, Agent Framework is next.
- We need a specific embedding or chunking strategy for a strange corpus
  (tables, code, scanned forms). Then Vector Search plus Agent Framework.
- Unit cost at scale beats build cost. Revisit when `reports/latest.md`
  shows a cost per thousand requests that a self-built stack would clearly
  undercut, including the engineers who would run it.
