# Deployment runbook

Owner: Engineering. Applies to Compass, Beacon and all internal services. Ledger is
owned by Finance and is out of scope.

## Release windows

Production deployments happen **Monday to Thursday between 10:00 and 16:00 Central
European Time**. There are no routine deployments on Fridays, on weekends, or during the
**peak freeze**, which runs from **15 November to 5 January** each year.

Emergency fixes may be deployed outside these windows with approval from the on-call
primary and the team lead. The fix must be announced in the **#deploys** channel before
and after.

## Approvals

Every change reaches production through a pull request that has:

1. At least **one approving review** from another engineer on the owning team.
2. Green continuous integration, including the service's contract tests.
3. For Compass and Beacon, a successful run in the **staging** environment for at
   least **30 minutes** with no new alerts.

Changes to the database schema also need a review from the Data team.

## Rollout

Compass and Beacon use a **canary** rollout: the new version first serves **5 percent**
of traffic for 15 minutes, then 50 percent for 15 minutes, then 100 percent. The
on-call primary watches the dashboards during the rollout.

Internal services deploy in one step.

## Rollback

Rolling back is the default response to a deployment that triggers a P1 or P2 alert.
Roll back first; investigate afterwards. A rollback does not need a pull request; the
on-call primary triggers it from the deployment tool. The team lead is told within
**30 minutes**.

Schema migrations must be backward compatible for at least one release so that a
rollback never needs a data migration.

## Feature flags

New customer-facing behaviour in Beacon ships behind a feature flag and is enabled for
internal users first, then for a pilot group of customers, then for everyone. Flags are
removed within **2 months** of full rollout.

## Records

The deployment tool keeps the record of who deployed what and when. Deployments are
Internal data; the deployment log for Beacon is retained for **13 months** alongside
security logs.
