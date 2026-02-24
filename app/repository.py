import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FileRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    storage_path TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS link_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    generated_at TEXT NOT NULL
                );
                """
            )

    def create_file(
        self,
        *,
        file_id: str,
        owner_id: str,
        filename: str,
        storage_path: str,
        size: int,
    ) -> dict:
        uploaded_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files(file_id, owner_id, filename, storage_path, size, uploaded_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (file_id, owner_id, filename, storage_path, size, uploaded_at),
            )
            row = conn.execute(
                "SELECT file_id, owner_id, filename, size, uploaded_at FROM files WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        return dict(row)

    def get_file(self, file_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
        return dict(row) if row else None

    def list_files_for_owner(self, owner_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT file_id, owner_id, filename, size, uploaded_at
                FROM files
                WHERE owner_id = ?
                ORDER BY uploaded_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_link_generation(self, *, file_id: str, owner_id: str, ttl_seconds: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO link_audit(file_id, owner_id, ttl_seconds, generated_at)
                VALUES(?, ?, ?, ?)
                """,
                (file_id, owner_id, ttl_seconds, utc_now_iso()),
            )
