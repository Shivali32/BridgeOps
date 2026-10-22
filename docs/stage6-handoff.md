# Historical Stage 6 planning notes

Kafka dispatch is now implemented on `work/bridgops-kafka`. See [kafka.md](kafka.md)
for current behavior and setup, and [progress.md](progress.md) for verification.
The text below records the original Stage 5 handoff.

## Original plan

Stages 1 to 5 deliver a synchronous local integration product. Kafka is not installed
or implemented. First review the final engineering report and keep the verified
order/approval/recovery semantics as regression requirements.

The workflow runner is a service boundary callable outside HTTP. A future stage can
add a transactional outbox when order processing is requested, publish durable events,
and let a worker claim executions. Preserve tenant ownership, immutable snapshots,
provider idempotency keys, step history, approval states and ownership fencing.

Do not merely call Kafka after committing an order and assume publication cannot be
lost. Define outbox claim/publication/acknowledgment behavior and test worker crashes,
redelivery, ordering, lease renewal and duplicate messages. Approval decisions should
resume through durable work requests while keeping their existing idempotent transitions.

Use Compose profiles so ordinary local development does not require the broker.
Measure a concrete asynchronous behavior improvement before adding more infrastructure.
Authentication and tenant authorization remain prerequisites for any public deployment.
