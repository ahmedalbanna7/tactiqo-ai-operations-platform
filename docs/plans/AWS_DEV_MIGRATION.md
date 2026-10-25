# AWS DEV Migration Plan

Status: NexaOps POC approved for implementation, targeting $20/month; deployment blocked by missing core artifacts package. No AWS resources have been changed.
Date: 2026-10-25

## Scope and assumptions

- Target account: AWS account `345259854056`, region `us-east-1`, authenticated
  through the local `default` AWS CLI profile.
- Create a dedicated, tagged NexaOps stack. Do not modify or reuse resources
  owned by other applications, including the active `merasad-dev-app` ECS
  cluster, the Registfy sizing cluster, existing S3 buckets, or unrelated
  Lambda functions and roles.
- Preserve the modular-monolith application boundaries and PostgreSQL as the
  canonical data store. Run the current Next.js web process, FastAPI API,
  asynchronous parser worker, PostgreSQL/pgvector, Redis, and RabbitMQ as
  containers on one small EC2 host for this low-traffic demonstration.
- Use the AWS DEV account only after a reviewed Terraform plan and an explicit final
  deployment confirmation. A deploy creates billable, persistent resources.
- Do not move local `.env` values or test data into AWS. No data migration or
  tenant/user provisioning is included in the initial infrastructure change.

## Repository assessment

The repository is a private full-stack platform, not a static frontend. It
contains a Next.js 16 frontend, a FastAPI 0.138 API, a Python 3.12 worker and MCP
demo, 25 Alembic migration files, and a PostgreSQL/pgvector data layer. The
current local Compose services are PostgreSQL, Redis, RabbitMQ, MinIO, API,
worker, MCP demo, web, and optional Prometheus/Grafana.

The DEV account inventory was read-only. It has no bucket, RDS instance,
ElastiCache cluster, Amazon MQ broker, or CloudFormation stack named Tactiqo.
Existing ECS clusters, S3 buckets, queues, and functions belong to other
projects and are excluded. Bedrock foundation-model IDs are available in
`us-east-1`, but model invocation entitlement, quota, and cost have not been
validated.

Two source defects currently block a full deployment:

1. `backend/src/tactiqo/artifacts/` is absent from the checked-out `main` commit,
   although the API composition, migrations, tests, and plans import it. This
   causes test collection and Alembic migration startup to fail.
2. `apps/web/Dockerfile` copies `apps/web/public`, but that directory is absent,
   so the web image build fails.

The second issue has been repaired by adding the required empty public directory.
The first module is also absent from all checked out Git history and the GitHub
repository. Python import confirms `ModuleNotFoundError`. It cannot be safely
regenerated from migrations or assumed interfaces. AWS resources must not be
created until the module is restored and migrations and the API image build
successfully.

## Proposed AWS POC architecture

```text
Developer browser -- SSM port-forward --> one EC2 host (Docker Compose)
                                         |-- web + API + worker
                                         |-- PostgreSQL/pgvector
                                         |-- Redis + RabbitMQ
                                         |-- private S3 bucket
                                         `-- Amazon Bedrock Runtime
```

Use Terraform for a dedicated, single-AZ VPC, public subnet and internet gateway,
one x86 `t3a.medium` EC2 instance (2 vCPU, 4 GiB), a 30 GiB gp3 EBS data volume,
one private versioned S3 bucket, ECR image repositories, weekday EventBridge
Scheduler start/stop rules in `Africa/Cairo`, and a least-privilege EC2 instance
role. Do not create an ALB, NAT gateway, CloudFront distribution,
RDS, ElastiCache, or Amazon MQ. PostgreSQL/pgvector, Redis, and RabbitMQ remain
Compose services on the EC2 host. Disable Prometheus, Grafana, and the optional
MCP demo in this POC. Bound container memory and CPU, add Docker log rotation,
and make the local Postgres volume durable on EBS. Back up small PostgreSQL
`pg_dump` files to the private S3 bucket with a short lifecycle retention.

The instance starts at 09:00 and stops at 17:00 Monday-Friday Cairo time; this
models about 176 hours/month on average and at most 184 hours in a 23-weekday
month. Manual starts outside that window consume
the remaining monthly margin and should be limited to planned demonstrations.
The EC2 instance has no inbound security-group rules and uses Systems Manager
Session Manager for administration and browser port forwarding. An automatically
assigned public IPv4 is used only for outbound access to ECR, S3, SSM, and
Bedrock; it is released when the instance stops. Use the instance role, not AWS
access keys. Configure Bedrock to use Nova Lite and Titan v2 only, and keep AI
invocation disabled until the account's model access is confirmed. No public
website, custom domain, or HTTPS endpoint is included in this POC; a user opens
the demo through a local SSM tunnel.

### Monthly cost target

Target instance uptime is at most 184 hours/month (weekdays, 09:00-17:00 Cairo).
Assume on-demand `t3a.medium` at $0.0376/hour, one public IPv4 at $0.005/hour
while running, and 30 GiB gp3 at $0.08/GiB-month. The EC2 runtime is configured
for Standard CPU credit mode so it cannot accumulate unlimited-mode surplus CPU
charges. These inputs yield an estimated EC2/IP/EBS baseline of $10.24/month
in a 23-weekday month.
Reserve up to $4 for Bedrock inference and $2 for S3, ECR, logs, scheduler, and
data transfer, for an estimated total of $16.24/month and $3.76 of headroom to
the $20 target.
This is incremental NexaOps spend; unrelated account charges and taxes are
excluded. Exceptional egress or larger-than-budgeted model use can raise it.
Leaving the instance running continuously would break the target. AWS Budgets
alerts can lag usage and are not a guaranteed hard bill ceiling. Keep Bedrock
calls disabled or limited in application configuration until a durable usage
quota is in place.

## Contracts and data impact

- HTTP and SSE contracts remain FastAPI routes and Next.js browser calls. The
  user reaches the Arabic RTL web app and API through local SSM port forwards.
- Replace the MinIO adapter behind `ObjectStorage` with an AWS SDK adapter using
  the instance role, bucket name, and existing organization-scoped object keys.
  No database schema change is needed for the storage API.
- Retain RabbitMQ ingestion publication/consumption through the local POC
  container, including the existing retry and DLQ semantics. Its existing job
  processor contracts remain unchanged and no unimplemented job consumer will
  be claimed. Messages continue to carry only IDs, signed execution context,
  and object references.
- Keep the current SQLAlchemy/Alembic database schema. Use the Compose Postgres
  container on EBS for this disposable, single-host POC, and execute migrations
  only after all imported model modules are present.
- Add a Bedrock Converse/InvokeModel adapter behind the existing `LLMAdapter` and
  `EmbeddingAdapter` ports. Use Converse/tool configuration for model planning
  and answers; use InvokeModel for Titan text embeddings. Keep tenant profiles,
  capability routing, and encryption of third-party provider credentials in
  PostgreSQL. AWS model invocation credentials come from the task role.
- API responses, job payloads, audits, and telemetry must not expose AWS
  credentials, signed URLs beyond their intended short-lived operation, or raw
  source-document content.

## Security, approval, and failure handling

- Dedicated AWS resource names and tags: `application=nexaops`,
  `environment=dev`, `managed-by=terraform`.
- Block public S3 access, enable encryption and versioning, and preserve objects
  on stack deletion. Encrypt EBS at rest. Data on the single EC2 host is
  development-grade and has no managed-database SLA; use the S3 backup lifecycle
  and document recovery steps. Stateful data is retained on stack removal; data
  deletion needs a separate, explicit plan.
- Use the EC2 instance role rather than static AWS keys. Keep external provider
  credentials write-only in the existing encrypted tenant store. Never copy the
  local development signing key into AWS; generate and store an independent
  secret.
- Keep local development identity disabled in the deployed environment. Use a
  Cognito User Pool as the configured OIDC identity provider. Provision an
  invite-only Cognito account for the supplied initial Owner email, then run a
  one-time, audited tenant bootstrap that maps the Cognito issuer/subject to the
  Owner membership before enabling login. Do not enable unauthenticated access.
- Human-approval gates for external mutations and tenant authorization remain
  application responsibilities and must not be relaxed for the migration.
- Keep API and worker concurrency bounded, and retries visible through RabbitMQ
  DLQs. Docker logs must be sanitized and size-rotated. Session Manager access is
  restricted to the operator role; there are no inbound SSH or web ports.

## Verification and documentation

Before deployment, restore the missing artifacts source, repair the frontend
Docker build, then run frozen dependency installation, Ruff, mypy, full pytest,
Alembic `heads`, frontend lint/typecheck/build, Docker Compose validation, and
`terraform fmt`, `validate`, and `plan`. After an approved deployment, verify
the SSM tunnel, API health/readiness, database migrations, S3 private access,
Bedrock model/embedding probes, RabbitMQ retry/DLQ handling, and scheduled stop.
Document `DEPLOY.md`, environment variables, access provisioning, the 184-hour
runtime cap, backup/restore, rollback, and teardown retention. Cloud deployment
and cost-bearing resources remain unperformed until the missing source blocker
is resolved. The user has authorized implementation, a separate GitHub PR, and
deployment of the POC under the $20/month target.

## Open decisions

1. Restore `tactiqo.artifacts` from the intended repository source/commit. This
   is the current deployment blocker.
2. The initial Owner email is `ahmed.albanna@registfy.com`; build and review the
   one-time Cognito-to-tenant bootstrap flow before inviting the account.
3. Confirm model ID and approved Bedrock inference profile after access/quota
   checks; no model invocation is included in the read-only inventory.
4. The $20 target assumes the instance runs no more than 184 scheduled
   hours/month. Keep that limit operationally visible; the estimate is not a
   guaranteed AWS bill cap. Bedrock remains disabled until an app-level durable
   usage limit exists.
