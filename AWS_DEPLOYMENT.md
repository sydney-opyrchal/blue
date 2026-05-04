# AWS Deployment Topology (Target)

This document maps the v.1 stack to its intended production AWS deployment. It is design-only: v.1 ships to Fly.io (see `fly.*.toml` and the deployment runbook). The AWS topology is the architecture this design will move to once the v.1.5 roadmap closes (see `KNOWN_ISSUES.md`).

The local stack is intentionally portable. Each local component has a direct AWS analogue, and the application code does not embed any Fly-specific or AWS-specific assumptions. Migration is a configuration change, not a rewrite.

---

## Service mapping

| Local component | AWS production target | Why |
| --- | --- | --- |
| Mosquitto broker | **AWS IoT Core** (MQTT broker) | Managed MQTT with mTLS device auth, fleet provisioning, message routing rules, and ITAR-eligible regions. Mosquitto is the right local-dev story; IoT Core is the right operational story. |
| Edge gateway (specified, not yet built) | **AWS IoT Greengrass** at the cell or bay level | Greengrass provides the store-and-forward, local Lambda execution, and component lifecycle management ADR-005 describes. One Greengrass core per bay; devices publish to it locally; it forwards to IoT Core. |
| FastAPI ingest service | **ECS Fargate** behind an Application Load Balancer | Fargate keeps the deployable artifact a container (matching local), removes node management, and ALB terminates TLS and upgrades to WebSocket cleanly. |
| TimescaleDB | **Amazon RDS for PostgreSQL** with the Timescale extension, OR **Amazon Timestream** | RDS+Timescale keeps the SQL surface and the existing schema. Timestream is more cost-efficient at scale but requires a query-language change (Timestream uses a SQL dialect with restrictions). v.1.5 chooses based on retention and query-pattern measurements. |
| React SPA | **CloudFront** with **S3** origin | Static assets cached at edge; ALB only serves API and WebSocket traffic. |
| WebSocket fan-out | Terminated at the **ALB**, served by Fargate tasks | ALB supports long-lived WebSocket connections; sticky sessions ensure each client stays on one task across reconnects. At higher concurrency, **API Gateway WebSocket APIs** with a Fargate or Lambda backend become the cleaner option. |
| MQTT topic routing | **IoT Core Rules Engine** | Routes telemetry to the ingest service, archive (S3 via Kinesis Firehose), and any other consumers. Replaces the single-subscriber model with a fan-out the ingest service no longer has to own. |
| Long-term archive | **Kinesis Data Firehose → S3 (Parquet)** | Raw telemetry archive for replay, model training, and audit. Outside the 7-day TimescaleDB retention. |

---

## Networking

Single VPC, two private subnets per Availability Zone (one for application tier, one for data tier), two public subnets for the ALB. NAT gateways for outbound from the application subnets.

Security group posture:

- ALB security group: ingress 443 from 0.0.0.0/0; egress to the application security group on the FastAPI port.
- Application security group: ingress only from the ALB security group; egress to the data security group (5432) and to IoT Core (443).
- Data security group: ingress only from the application security group on 5432; no public ingress.
- IoT Core: device authentication via X.509 certificates, with policies scoped per device.

ITAR / EAR considerations: deploy in **us-east-1** or **us-gov-west-1** depending on the data classification. AWS GovCloud is the right answer if any telemetry crosses the line into export-controlled technical data (for an actual rocket-engine factory, it almost certainly does).

---

## Secrets and configuration

No secrets in environment variables or in the repo. Migration:

- Database password: **AWS Secrets Manager**, rotated automatically on a schedule. Fargate task definition references the secret ARN; the application reads from the injected environment variable at boot.
- IoT Core device certificates: stored in Secrets Manager or Parameter Store, distributed via Greengrass core deployments.
- Application configuration (MQTT host, DB host, log level): **Systems Manager Parameter Store** with hierarchical paths (`/forge/prod/api/mqtt-host`, etc.). Read at boot via the AWS SDK.

---

## Observability

Three pillars in the production deployment:

- **Logs**: structured JSON to stdout in every service; collected by the Fargate log driver and shipped to **CloudWatch Logs**, with log groups per service. Retention 30 days; archive to S3 for longer.
- **Metrics**: **CloudWatch Metrics** for infrastructure (Fargate CPU, ALB request count, RDS connections); custom metrics emitted by the ingest service for telemetry rate, alarm rate, anomaly detector hit rate. Dashboards organized by FR / NFR.
- **Traces**: **AWS X-Ray** instrumentation on the ingest service for request flow visibility, especially the MQTT-callback-to-asyncpg-write hop. Useful for diagnosing tail-latency issues.

Alerting tied to SLOs: CloudWatch Alarms on the metrics that map to NFRs (sustained throughput, p99 ingest latency, DB connection pool saturation, MQTT disconnect duration). Each alarm routes to PagerDuty via SNS.

The `/health` endpoint feeds the ALB healthcheck; the structured dependency status visible in v.1's `/health` response is exactly the shape ALB needs.

---

## CI / CD

GitHub Actions on `push` to `main`:

1. Run the test suite (must stay green; the v.1 coverage gate is in `pytest.ini`).
2. Build the multi-stage Docker image (frontend → backend bundle).
3. Push to **Amazon ECR** with the commit SHA as the tag.
4. Update the Fargate task definition's image reference and trigger a service deployment.
5. ECS performs a rolling deployment with healthcheck-gated cutover; failed tasks roll back automatically.
6. Post-deploy: run the acceptance script (`scripts/acceptance_test.sh`, queued for v.1.5) against the staging environment before promoting to production.

The simulator does not deploy to production. In a real factory, OPC UA → MQTT bridges run on the Greengrass cores; the simulator is a development-only artifact.

---

## What this document deliberately does not cover

These are real production concerns deferred to follow-on documents:

- Disaster recovery: backup strategy, RPO/RTO targets, multi-region failover.
- Capacity planning: scaling thresholds, reserved-capacity vs on-demand mix, cost projections.
- Security threat model: STRIDE-format analysis with mitigations per asset.
- Data lifecycle and PII posture: what's collected, retained, deleted, and who can access each.
- AS9100 / CMMC documentation: control mappings, audit evidence collection, change-management policy.

Each of these is named in `SPEC.md` §16 as a v.1.5+ deliverable. They are missing from this document on purpose — getting them right requires real production data and stakeholder input that v.1 does not have.

---

## Migration path from v.1 to AWS

This is the sequence v.1.5 would follow, in dependency order:

1. **Stand up the AWS networking foundation** (VPC, subnets, security groups, IAM roles). One-time setup.
2. **Migrate the database first**: provision RDS+Timescale, run the v.1.5 schema migration, point a staging deployment at it. Confirm read/write parity with the local TimescaleDB.
3. **Migrate the broker**: stand up IoT Core, define topic policies, generate a small batch of device certificates, run the simulator against IoT Core in staging.
4. **Migrate the ingest service**: build the ECS task definition, deploy to staging, point at the IoT Core broker and the RDS instance. Run the acceptance script end to end.
5. **Migrate the frontend**: build the SPA, push to S3, configure CloudFront. Update the ingest service CORS to allow the CloudFront origin.
6. **Cut DNS over from `forge-apis.fly.dev` to the new ALB**. Keep Fly running in parallel for a defined period as fallback; tear it down once production is stable.

Greengrass and the dedicated edge gateway (ADR-005) come in as a separate phase after the ingest service is live on AWS, since the gateway represents new functionality rather than a migration.
