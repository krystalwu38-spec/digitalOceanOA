from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


class LocalPrivateStorage:
    def __init__(self, root_dir: str):
        self.root = Path(root_dir)

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _owner_dir(self, owner_id: str) -> Path:
        owner_path = self.root / owner_id
        owner_path.mkdir(parents=True, exist_ok=True)
        return owner_path

    def save_file(self, *, owner_id: str, source: UploadFile, max_size_bytes: int) -> tuple[str, Path, int]:
        file_id = str(uuid4())
        suffix = Path(source.filename or "").suffix
        target = self._owner_dir(owner_id) / f"{file_id}{suffix}"

        total = 0
        with target.open("wb") as f:
            while True:
                chunk = source.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size_bytes:
                    f.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("File exceeds max upload size")
                f.write(chunk)
        return file_id, target, total
