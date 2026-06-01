# Partner Customer Import API

Backend service for importing partner customer CSV exports and managing customer records.

## Live Deployment

The service is deployed on Railway and publicly accessible:

| | |
|---|---|
| **Base URL** | `https://zenafide-customer-import-api-production.up.railway.app` |
| **API Docs** | `https://zenafide-customer-import-api-production.up.railway.app/docs` |
| **Health** | `https://zenafide-customer-import-api-production.up.railway.app/health` |
| **Metrics** | `https://zenafide-customer-import-api-production.up.railway.app/metrics` |

Demo credentials:

```text
admin@example.com / admin123
operator@example.com / operator123
```

## Run With Docker

Start Docker Desktop first, then run:

```bash
docker compose up --build
```

For local development with hot-reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The API will be available at:

```text
http://localhost:8000
```

Interactive API docs:

```text
http://localhost:8000/docs
```

Health check:

```bash
curl http://localhost:8000/health
```

Metrics:

```bash
curl http://localhost:8000/metrics
```

## Authentication

The local setup seeds two demo users:

```text
admin@example.com / admin123
operator@example.com / operator123
```

Create an access token:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin123"
```

Copy the returned `access_token`, then use it for protected endpoints:

```bash
export TOKEN="<access-token>"
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Both roles can view and edit customers and run imports. Only admins can delete customers.

## Run Tests

Locally (after `pip install -r requirements.txt`):

```bash
pytest
```

Inside Docker:

```bash
docker compose exec api pytest tests/ -q
```

## Database Migrations

Docker Compose applies migrations automatically before starting the API.

To apply migrations manually:

```bash
alembic upgrade head
```

To view the current revision:

```bash
alembic current
```

If you created a local development database before Alembic was added, remove the disposable `app.db` file before running the first migration. For an old disposable Docker volume, run `docker compose down --volumes` once before restarting.

## Logging And Monitoring

The API writes structured JSON logs to stdout for:

- completed HTTP requests with request IDs, status codes, and durations
- started and completed CSV imports
- invalid CSV rows with import IDs and error codes

Every HTTP response includes an `X-Request-ID` header. You can supply your own `X-Request-ID` header to correlate a request with its logs.

When running with Docker Compose, JSON logs are also written to:

```text
/var/log/zenafide/app.log
```

The `logs_data` Docker volume keeps this file across `docker compose down` and subsequent restarts.

The public monitoring endpoints are:

```text
GET /health
GET /metrics
```

`/health` verifies database connectivity. `/metrics` returns request counters stored in PostgreSQL and import counters derived from persisted import jobs. Metrics therefore survive API restarts and `docker compose down`.

Docker Compose persists PostgreSQL data in `postgres_data`, logs in `logs_data`,
uploaded CSV files in `uploads_data`, and Redis queues in `redis_data`. Running
`docker compose down --volumes` intentionally deletes these volumes.

## Customer API

Create a customer:

```bash
curl -X POST http://localhost:8000/customers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "partner_id": "p1",
    "partner_customer_id": "C1001",
    "email": "ada@example.com",
    "name": "Ada Lovelace",
    "status": "active",
    "tier": "ent",
    "tags": "vip",
    "note": "created manually"
  }'
```

List customers:

```bash
curl "http://localhost:8000/customers?page=1&page_size=50&status=active" \
  -H "Authorization: Bearer $TOKEN"
```

Update a customer:

```bash
curl -X PATCH http://localhost:8000/customers/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tier": "pro", "internal_note": "manual correction"}'
```

Delete a customer:

```bash
curl -X DELETE http://localhost:8000/customers/1 \
  -H "Authorization: Bearer $TOKEN"
```

## Customer CSV Import

Upload a partner customer CSV:

```bash
curl -X POST http://localhost:8000/imports/customers \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@customers.csv"
```

Example response:

```json
{
  "id": 1,
  "filename": "customers.csv",
  "status": "pending",
  "total_rows": 0,
  "successful_rows": 0,
  "failed_rows": 0,
  "created_at": "2026-05-31T03:46:57",
  "completed_at": null,
  "errors_url": "/imports/1/errors"
}
```

The upload endpoint returns `202 Accepted`. Poll the import summary endpoint until
the status changes from `pending`, `processing`, or `retrying` to `completed`,
`partial_success`, or `failed`.

Fetch an import summary:

```bash
curl http://localhost:8000/imports/1 \
  -H "Authorization: Bearer $TOKEN"
```

Fetch row-level import errors:

```bash
curl http://localhost:8000/imports/1/errors \
  -H "Authorization: Bearer $TOKEN"
```

Import rules:

- The API stores the CSV in durable upload storage and queues a Celery task.
- Celery retries unexpected worker failures up to three times with backoff.
- Each worker attempt processes rows sequentially so row-level validation stays deterministic.
- Invalid rows are saved to `import_errors`; the rest of the file continues.
- Customers are matched by `partner_id + partner_customer_id` when `cid` exists.
- If `cid` is missing, customers are matched by `partner_id + email`.
- Newer `upd` values update existing customers.
- Older or same `upd` values are treated as successfully processed but do not overwrite customer data.
- Blank `tier` defaults to `std`.
- Manual `internal_note` values are preserved during imports.

## Services

The Docker Compose setup starts:

- `api`: FastAPI app + Celery worker running together via supervisord on port `8000`
- `redis`: persistent Celery broker and result backend
- `db`: PostgreSQL running on port `5432`

The API reads its database connection from:

```text
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/zenafide
```

Copy `.env.example` to `.env` and replace `JWT_SECRET_KEY` with a random secret
before deploying:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Deploy To Railway

Create a Railway project from this GitHub repository and add PostgreSQL and Redis services.

The API and Celery worker run together in a single container via supervisord, so no separate worker service is needed. Migrations run automatically on startup via `start.sh`.

Set these variables on the API service:

```text
DATABASE_URL=<PostgreSQL DATABASE_URL from Railway Connect tab>
CELERY_BROKER_URL=<Redis URL from Railway Connect tab>
CELERY_RESULT_BACKEND=<same Redis URL>
JWT_SECRET_KEY=<random secret — generate with the command above>
SEED_DEMO_USERS=true
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<your password>
OPERATOR_EMAIL=operator@example.com
OPERATOR_PASSWORD=<your password>
STORAGE_BACKEND=local
```

Railway supplies `PORT` automatically.

After deployment, verify:

```text
GET /health
GET /metrics
GET /docs
```

> **Note:** `STORAGE_BACKEND=local` works for single-container deployments. To scale
> to multiple replicas in future, switch to `STORAGE_BACKEND=s3` and add the
> corresponding `S3_BUCKET`, `S3_REGION`, `AWS_ACCESS_KEY_ID`, and
> `AWS_SECRET_ACCESS_KEY` variables.

## Assumptions

The following assumptions were made during design and implementation.
They are documented here so reviewers and future contributors can challenge or extend them.

### CSV Format

- **Header row is always the first line.** Files without a header are rejected outright (`missing_header` error).
- **Exactly 10 columns are expected** (`p, row, cid, email, name, status, tier, upd, tags, note`). This count is used to detect and recover visually wrapped rows — if a physical line has fewer than 10 comma-separated values, the next physical line is stitched on to it with a space until 10 columns are reached. A row that cannot be recovered this way is recorded as `invalid_column_count` and skipped.
- **Column names may vary between partner exports.** Headers are normalised to lowercase and stripped of whitespace before field lookup, so minor capitalisation differences are tolerated.
- **Files are UTF-8 encoded** (BOM variant `utf-8-sig` is also accepted). Files in other encodings are rejected with an `invalid_encoding` error.
- **The `upd` field uses `YYYYMMDD` format.** Any other format is rejected as `invalid_date`.
- **Blank `tier` defaults to `std`.** An absent or empty tier is treated as standard tier. Any other unrecognised tier value is a validation error.
- **`tags` and `note` are free-text strings** — no validation beyond presence. They are stored as plain text and are nullable.
- **The `row` column is a partner-assigned sequence number** used only for human traceability; it is not stored or validated beyond being part of the column count.
- **File size is capped at 100 MB.** Files larger than this are rejected at upload time with a `413` response.

### Customer Identity and Deduplication

- **A customer is uniquely identified within a partner by `partner_id + partner_customer_id` when `cid` is present**, or by `partner_id + email` when `cid` is absent. Two rows in the same file with the same identity are treated as duplicates.
- **Partner namespaces are completely isolated.** `p1/C1001` and `p2/C1001` are different customers even if they share the same email address.
- **The `upd` date is the source of truth for staleness.** A newer `upd` value overwrites all customer fields except `internal_note`. An equal or older `upd` is silently skipped (counted as successful, no data change).
- **`internal_note` is never overwritten by an import.** It is reserved for manually entered notes from operators and is preserved across all import runs.
- **Email addresses are normalised** (lowercased and validated via `email-validator`) before storage and comparison. Deliverability is not checked — only format validity.

### Import Lifecycle

- **Imports are processed asynchronously.** The upload endpoint returns `202 Accepted` immediately. Clients must poll `GET /imports/{id}` until the status is `completed`, `partial_success`, or `failed`.
- **A bad row never aborts the rest of the file.** Each row is validated and processed independently. Failures are recorded in `import_errors` and the import continues.
- **Worker failures are retried up to 3 times with exponential backoff.** On each retry attempt all row counters and errors for that import job are reset so results are always consistent with the final attempt. If all retries are exhausted the job is marked `failed` with error code `worker_failed`.
- **Uploaded files are stored durably** (local volume or S3) before the Celery task is queued. If the worker cannot read the file it records `stored_file_unavailable` and fails the job rather than silently losing rows.
- **Row processing within a single worker attempt is sequential**, not parallel. This keeps row-level error reporting deterministic and avoids write conflicts on the same customer record within one import.

### Authentication and Authorisation

- **Two roles exist: `admin` and `operator`.** Both can create, view, and edit customers and trigger imports. Only `admin` can delete customers.
- **Authentication uses short-lived JWT bearer tokens** (default 30-minute expiry). There is no refresh token mechanism — clients must re-authenticate after expiry.
- **Passwords are hashed with Argon2** via `pwdlib`. Plain-text passwords are never stored or logged.
- **Demo users (`admin@example.com`, `operator@example.com`) are seeded only when `SEED_DEMO_USERS=true`.** This is off by default in production. Demo credentials are only appropriate for local development.

### Monitoring and Metrics

- **Request metrics are persisted in PostgreSQL**, not in memory. This means metrics survive API restarts and `docker compose down`. The trade-off is a small extra write per request.
- **The `/metrics` endpoint is public** (no authentication required) to allow infrastructure health checks without managing tokens. It exposes only aggregate counts — no customer data.
- **Import metrics are derived from persisted import jobs**, not a separate counter table. `by_status` and row counts are always consistent with the actual job records.

### Infrastructure

- **The API and Celery worker run in the same container** via supervisord. This keeps upload storage simple (local filesystem, no S3 needed) and is suitable for single-instance deployments. To scale horizontally in future, switch to `STORAGE_BACKEND=s3` and run the worker as a separate service.
- **Redis is used as both the Celery broker and result backend.** Persistence is enabled (`appendonly yes`) so queued tasks survive Redis restarts.
- **Database migrations are applied automatically** (`alembic upgrade head`) on API startup. This is safe for development and small deployments; larger production setups may prefer to run migrations as a separate step before deploying.
