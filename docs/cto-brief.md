# Brief: an internal Q&A assistant on Databricks, run like a product

One page for a non-engineer. Written 2026-10-20.

## The problem

People spend time hunting through policies and asking colleagues questions the
handbook already answers. An assistant that answers from the handbook with a
citation saves that time. The risk is an assistant that answers confidently and
wrongly, which costs more trust than it saves time.

## What we built in phase 1

- A Knowledge Assistant on Databricks Agent Bricks, deployed from code so it can
  be rebuilt in any workspace in minutes.
- A test set of 39 questions, including 8 the handbook cannot answer, run through
  five independent automated judges after every change. If the score drops below
  thresholds we agreed on in writing, the deployment is blocked.
- A cost line, in dollars per thousand questions at list price, from Databricks'
  own billing tables, refreshed weekly.
- Four short decision records explaining why this approach, what the gate
  measures, how cost and access are controlled, and what we would lose if we
  moved off Databricks.

## What it is not yet

- Not connected to the real handbook. The corpus is a fictional company so the
  test is honest; swapping in real documents is a data task, not an engineering
  one.
- Not collecting human feedback. That is phase 3.
- No real run numbers yet: the report page says "not yet run" until the first
  evaluation on the target workspace completes. It will never show invented
  figures.

## The three numbers to watch

| Number | Where | Why it matters |
|---|---|---|
| Correctness (target ≥ 80%) | `reports/latest.md` | Share of answers that contain the facts the handbook states. |
| Refusal on unanswerable questions (target ≥ 90%) | same | Share of times it says "the handbook does not cover this" instead of guessing. |
| Cost per 1,000 questions | same | What a month of usage will cost before anyone commits to it. |

## Risks and how they are handled

- **The vendor changes the model under us.** The weekly evaluation catches it;
  the gate blocks a redeploy until it is fixed or thresholds are consciously
  re-agreed.
- **Someone pastes sensitive data into it.** Access is controlled in Unity
  Catalog; requests are logged; the handbook's own data-classification rules
  apply to the assistant.
- **It is more expensive than expected.** The cost page is the first thing
  reviewed each week, with a budget policy on the endpoint as a hard stop.
- **We are locked in.** The questions, expected answers, and thresholds are plain
  files in our repository; rebuilding the agent elsewhere is about a week of work.

## Next 90 days

1. Run the gate on the real workspace; publish the first real report.
2. Replace the fictional handbook with one real policy area and re-baseline.
3. Add a Supervisor Agent that can also answer from a shipments table, with
   routing correctness added to the gate.
4. Decide on a pilot group and a feedback loop.

## Ask

Approve a 90-day pilot with one policy area and a named owner for the content.
No new headcount; one engineer at roughly one day a week.
