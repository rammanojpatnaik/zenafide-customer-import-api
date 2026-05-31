# Partner Customer Import API

Backend service for importing partner customer CSV exports and managing customer records.

## Run With Docker

Start Docker Desktop first, then run:

```bash
docker compose up --build
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

```bash
pytest
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

The Celery worker writes its logs to `/var/log/zenafide/worker.log`. The `logs_data`
Docker volume keeps both files across `docker compose down` and subsequent restarts.

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

- `api`: FastAPI app running on port `8000`
- `worker`: Celery worker processing queued CSV imports
- `redis`: persistent Celery broker and result backend
- `db`: PostgreSQL running on port `5432`

The API reads its database connection from:

```text
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/zenafide
```

Copy `.env.example` to `.env` and replace `JWT_SECRET_KEY` before deploying the service.

## Deploy To Railway

The Docker Compose setup uses a shared upload volume between the API and worker.
For a multi-service cloud deployment, replace that shared volume with object
storage such as S3 before deploying.

Create a Railway project from this GitHub repository and add PostgreSQL and Redis
services. Set these variables on the API and worker services:

```text
DATABASE_URL=<PostgreSQL DATABASE_URL>
JWT_SECRET_KEY=<random secret>
SEED_DEMO_USERS=true
CELERY_BROKER_URL=<Redis URL>
CELERY_RESULT_BACKEND=<Redis URL>
```

Railway supplies `PORT` automatically. The Docker image applies `alembic upgrade head` before starting the API.

After deployment, verify:

```text
GET /health
GET /metrics
GET /docs
```
