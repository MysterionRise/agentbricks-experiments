# Security incident response

Owner: Security. Applies to everyone. When in doubt, report.

## How to report

Report any suspected security incident to the Security team through the **#sec-incident**
channel or, outside office hours, by paging the security on-call through the on-call
tool. Do not investigate on your own and do not try to fix the problem before reporting.

## Severity levels

| Level | Definition | First response target | Examples |
|---|---|---|---|
| **Severity 1** | Confirmed breach of Restricted data, or an outage of Compass or Beacon caused by an attack | 15 minutes, any hour | Ransomware on a hub, leaked payroll file |
| **Severity 2** | Likely exposure of Confidential data, or a compromised employee account | 1 hour, any hour | Phished credentials used to log in, customer contract sent to the wrong recipient |
| **Severity 3** | Lost or stolen device, policy violation with no evidence of data exposure, malware blocked by endpoint protection | 1 business day | Laptop left on a train, unapproved software installed |
| **Severity 4** | Suspicious activity needing review, phishing email reported before being opened | 3 business days | Phishing report, unusual login alert |

The Security on-call assigns the initial severity. The incident commander can change it
as facts emerge.

## Roles

- **Incident commander**: the Security on-call engineer, or a person they delegate to.
  Runs the response and is the single source of truth.
- **Communications lead**: from the People team for internal matters, from the Chief
  Operating Officer's office for customer-facing matters.
- **Scribe**: keeps a timestamped log in the incident channel.

## Timelines

- A Severity 1 or 2 incident is reported to the Chief Technology Officer within
  **1 hour** of being confirmed.
- Customers affected by a confirmed breach of their data are informed within
  **72 hours**. Legal drafts the notice.
- Every Severity 1 and 2 incident gets a written post-incident review within
  **10 working days**. Reviews are blameless and are stored in Atlas as Confidential.

## Containment powers

The incident commander can disable any account, block any network, or take any system
offline, including Compass and Beacon, without further approval. They inform the Chief
Technology Officer and the Chief Operating Officer as soon as practical.

## Phishing

Report phishing with the **Report** button in the mail client. Do not forward phishing
emails to colleagues. If you clicked a link or entered a password, report it at
Severity 2 immediately; you will not be penalised for reporting.
