# Secure File Service

REST API for private file uploads with temporary cryptographically signed download links.

## Features

- Private file ingestion into a non-public local directory
- Per-file owner association (`user_id`)
- Signed URL generation with TTL
- Public download endpoint that validates signature and expiry
- File metadata listing per owner
- Audit recording for every link generation
- Automated tests and GitHub Actions CI pipeline

## Stack

- Python 3.10+
- FastAPI
- SQLite (metadata + audit log)
- Pytest

## Quickstart

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements-dev.txt
```

3. Configure environment:

```bash
cp .env.example .env
```

4. Run the API:

```bash
uvicorn app.main:app --reload
```

5. Run tests:

```bash
pytest -q
```

## API Contract

### Error responses

All non-2xx responses follow a consistent shape:

```json
{
	"error": {
		"code": "bad_request",
		"message": "human-readable reason"
	}
}
```

Status mapping:
- `400`: invalid TTL, missing/invalid parameters
- `401` / `403`: auth missing/invalid (if used) or invalid signature
- `404`: file not found
- `410`: expired signed link
- `413`: file too large

### 1) Upload file

`POST /v1/files/upload`

Form data:
- `user_id` (string)
- `file` (binary)

Response `201`:

```json
{
	"file_id": "uuid",
	"owner_id": "u-123",
	"filename": "report.pdf",
	"size": 48222,
	"uploaded_at": "2026-02-24T18:48:09.849921+00:00"
}
```

### 2) Generate signed URL

`POST /v1/files/{file_id}/sign`

Body:

```json
{
	"owner_id": "u-123",
	"ttl_seconds": 600
}
```

Response `200`:

```json
{
	"file_id": "uuid",
	"expires_at": 1770000000,
	"signed_url": "http://localhost:8000/v1/files/download?file_id=...&owner_id=...&exp=...&sig=..."
}
```

### 3) Download using signed URL

`GET /v1/files/download?file_id=...&owner_id=...&exp=...&sig=...`

- Validates expiry timestamp
- Validates HMAC-SHA256 signature
- Serves file bytes only when valid

### 4) Query owner file metadata

`GET /v1/users/{user_id}/files`

Returns filename, size, upload time, and file id for the owner.

## Security notes

- Signature uses HMAC-SHA256 over: `file_id:owner_id:expires_at`
- Signature key comes from `SFS_APP_SECRET_KEY`
- Default upload limit is `50MB` (`SFS_MAX_UPLOAD_SIZE_BYTES`)
- Default signed-link TTL range is `30s` to `24h` (`SFS_MIN_TTL_SECONDS`, `SFS_MAX_TTL_SECONDS`)
- Signed URLs remain valid across service restarts as long as:
	- the same secret key is used
	- metadata DB and stored files persist
- File content is stored in an application-managed private folder and never directly exposed as static public assets

## Audit logging

Every successful signer request stores an audit row in `link_audit` with:

- `file_id`
- `owner_id`
- `ttl_seconds`
- `generated_at`

## CI

GitHub Actions workflow at `.github/workflows/ci.yml`:

- installs dependencies
- runs test suite on pushes and pull requests

## Suggested production hardening

- Set a strong random `SFS_APP_SECRET_KEY`
- Put API behind TLS and an auth layer
- Add rate limiting and per-user quotas
- Store files on durable volume/object store for horizontal scaling
