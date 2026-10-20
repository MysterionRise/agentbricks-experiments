# On-call rotation

Owner: Engineering. Applies to engineers in the Platform, Routing and Customer Portal
teams. The Data team is not on call.

## Rotation

Each team runs a weekly rotation with one **primary** and one **secondary** engineer.
The week starts on Monday at 09:00 Central European Time. Rotations are published in
the on-call tool at least **4 weeks** ahead. Engineers join the rotation after
**3 months** on the team and after shadowing two shifts.

## Paging

The primary is paged for any alert of priority P1 or P2. If the primary does not
acknowledge within **10 minutes**, the secondary is paged. If neither acknowledges within
**20 minutes**, the team lead is paged.

| Priority | Meaning | Acknowledge within | Example |
|---|---|---|---|
| P1 | Compass or Beacon down or unusable for customers | 10 minutes | Dispatch screens blank at a hub |
| P2 | Degraded service, a hub affected, workaround exists | 10 minutes | Tracking updates delayed by more than 30 minutes |
| P3 | Minor fault, no customer impact | Next business day | A nightly report failed |

P3 alerts do not page; they create a ticket.

## Expectations while on call

The primary must be able to start working on an incident within **15 minutes** of
acknowledging a page, with a laptop and a reliable connection. On-call engineers do not
travel abroad during their shift unless the team lead agrees and connectivity is
confirmed. Alcohol is to be avoided during the shift.

## Compensation

On-call pays a flat allowance of **EUR 250 per week** for the primary and **EUR 100 per
week** for the secondary, whether or not pages happen. Time worked on an incident
outside working hours is compensated with time off in lieu at **1.5 times** the hours
worked, to be taken within 2 months.

## Swaps

Engineers may swap shifts between themselves and record the swap in the on-call tool.
A swap less than **48 hours** before the shift starts also needs the team lead's
agreement.

## Handover

Each Monday at 09:30 the outgoing and incoming primaries hold a 15-minute handover
covering open incidents, noisy alerts, and any planned deployments in the coming week.
