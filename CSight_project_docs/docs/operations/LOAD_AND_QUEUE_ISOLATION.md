# Load and queue-isolation qualification

## 1. Scope

This qualification measures two independent product claims without creating a Case, Decision,
Report, or external business action:

1. twenty independent HTTP clients repeatedly read the current demo operator Case and Review APIs;
2. an isolated RabbitMQ/Celery stack runs two 120-second synthetic model jobs in the model lane while
   twenty short decision probes measure enqueue-to-start delay in a separate decision lane.

It is evidence for read capacity and broker/worker routing isolation. It is not OIDC session
qualification, a real model-provider benchmark, a 20-workflow terminal test, or mutation latency
evidence.

## 2. Run

Keep the current local demo healthy, then run:

```bash
make qualify-load-isolation
```

The read phase uses 20 independently authenticated clients, 10 requests per endpoint per client,
and three repetitions. It performs 600 requests to `/api/v1/operator/cases` and 600 to
`/api/v1/operator/reviews`. Both endpoints must have zero contract/error failures and the worst run
p95 must be at most 500 ms.

The queue phase uses a digest-pinned RabbitMQ on an internal-only network with no host ports. The
model worker has concurrency 1 and the decision worker concurrency 2. Two fixed synthetic tasks are
published to the model queue; after exactly one begins its 120-second sleep, twenty decision tasks
are published. All twenty must start and complete exactly once with queue-wait p95 at most 2,000 ms
while no model task completes. The qualifier then removes the in-flight synthetic tasks together
with all isolated containers, queues, networks, and volumes.

## 3. Evidence and safety boundary

The aggregate report is stored at
`local-data/load-isolation-qualification/latest/qualification-report.json`. The raw queue event file
contains only fixed event names, integer indexes, and timing values. Neither artifact contains
tokens, tenant/Case/user IDs, customer text, or object keys.

The 2026-08-30 local result was:

- Case-list worst p95: 396.274 ms;
- Review-list worst p95: 460.999 ms;
- decision queue-wait p95: 574.339 ms, max 574.404 ms;
- read errors, lost/duplicate decision tasks, DB mutations, and business side effects: zero.

The result remains bounded by `current-demo-read-only-legacy-auth-not-pilot-oidc` and
`isolated-synthetic-rabbitmq-celery-routing-only`. Do not set the 20-session/20-workflow release gate
from this report. A strict RLS/OIDC pilot profile, non-model mutation p95, 20 complete workflows,
queue drain, terminal/duplicate/stall checks, and actual 4090 model load remain `NOT_RUN`.
