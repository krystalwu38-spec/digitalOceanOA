import sqlite3
import time

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def build_client(tmp_path, monkeypatch, *, min_ttl_seconds: int = 30):
    storage_dir = tmp_path / "private"
    db_path = tmp_path / "metadata.db"

    monkeypatch.setenv("SFS_APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("SFS_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("SFS_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("SFS_MAX_UPLOAD_SIZE_BYTES", "1000000")
    monkeypatch.setenv("SFS_MIN_TTL_SECONDS", str(min_ttl_seconds))
    monkeypatch.setenv("SFS_MAX_TTL_SECONDS", "3600")
    get_settings.cache_clear()

    app = create_app()
    return TestClient(app), db_path


def test_upload_and_list_files(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        upload = client.post(
            "/v1/files/upload",
            data={"user_id": "u-1"},
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        assert upload.status_code == 201
        payload = upload.json()
        assert payload["owner_id"] == "u-1"
        assert payload["filename"] == "hello.txt"
        assert payload["size"] == 11

        listing = client.get("/v1/users/u-1/files")
        assert listing.status_code == 200
        files = listing.json()["files"]
        assert len(files) == 1
        assert files[0]["file_id"] == payload["file_id"]


def test_signed_url_download_and_expiry(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch, min_ttl_seconds=1)
    with client:
        upload = client.post(
            "/v1/files/upload",
            data={"user_id": "u-2"},
            files={"file": ("note.txt", b"private data", "text/plain")},
        )
        file_id = upload.json()["file_id"]

        sign = client.post(
            f"/v1/files/{file_id}/sign",
            json={"owner_id": "u-2", "ttl_seconds": 2},
        )
        assert sign.status_code == 200
        signed_url = sign.json()["signed_url"]

        download = client.get(signed_url)
        assert download.status_code == 200
        assert download.content == b"private data"

        time.sleep(3)
        expired = client.get(signed_url)
        assert expired.status_code == 410
        assert expired.json()["error"]["message"] == "link expired"


def test_sign_records_audit_event(tmp_path, monkeypatch):
    client, db_path = build_client(tmp_path, monkeypatch)
    with client:
        upload = client.post(
            "/v1/files/upload",
            data={"user_id": "u-3"},
            files={"file": ("audit.txt", b"audit", "text/plain")},
        )
        file_id = upload.json()["file_id"]

        sign = client.post(
            f"/v1/files/{file_id}/sign",
            json={"owner_id": "u-3", "ttl_seconds": 600},
        )
        assert sign.status_code == 200

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM link_audit WHERE file_id = ?", (file_id,)).fetchone()[0]
    conn.close()
    assert count == 1


def test_sign_rejects_ttl_below_minimum(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        upload = client.post(
            "/v1/files/upload",
            data={"user_id": "u-ttl"},
            files={"file": ("note.txt", b"data", "text/plain")},
        )
        file_id = upload.json()["file_id"]

        sign = client.post(
            f"/v1/files/{file_id}/sign",
            json={"owner_id": "u-ttl", "ttl_seconds": 29},
        )
        assert sign.status_code == 400
        assert sign.json()["error"]["code"] == "bad_request"


def test_sign_rejects_ttl_above_maximum(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        upload = client.post(
            "/v1/files/upload",
            data={"user_id": "u-ttl-max"},
            files={"file": ("note.txt", b"data", "text/plain")},
        )
        file_id = upload.json()["file_id"]

        sign = client.post(
            f"/v1/files/{file_id}/sign",
            json={"owner_id": "u-ttl-max", "ttl_seconds": 3601},
        )
        assert sign.status_code == 400
        assert sign.json()["error"]["code"] == "bad_request"


def test_download_invalid_signature_returns_forbidden_without_leaking_existence(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        now = int(time.time())
        bad = client.get(
            "/v1/files/download",
            params={
                "file_id": "non-existent-file",
                "owner_id": "u-any",
                "exp": now + 120,
                "sig": "invalid",
            },
        )
        assert bad.status_code == 403
        body = bad.json()
        assert body["error"]["code"] == "forbidden"
        assert body["error"]["message"] == "invalid signature"


def test_upload_rejects_payload_too_large(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        huge = client.post(
            "/v1/files/upload",
            data={"user_id": "u-big"},
            files={"file": ("huge.bin", b"a" * (1_000_001), "application/octet-stream")},
        )
        assert huge.status_code == 413
        assert huge.json()["error"]["code"] == "payload_too_large"


def test_missing_required_parameter_returns_bad_request(tmp_path, monkeypatch):
    client, _ = build_client(tmp_path, monkeypatch)
    with client:
        missing = client.post(
            "/v1/files/upload",
            files={"file": ("hello.txt", b"hello", "text/plain")},
        )
        assert missing.status_code == 400
        body = missing.json()
        assert body["error"]["code"] == "bad_request"
        assert "missing parameters" in body["error"]["message"]
