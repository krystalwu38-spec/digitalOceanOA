from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.config import Settings, get_settings
from app.models import FileListResponse, FileRecord, SignLinkRequest, SignLinkResponse, UploadResponse
from app.repository import FileRepository
from app.signing import URLSigner
from app.storage import LocalPrivateStorage

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    repository = FileRepository(settings.database_path)
    storage = LocalPrivateStorage(settings.storage_dir)
    signer = URLSigner(settings.app_secret_key)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
        repository.init()
        storage.init()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/")
    def root() -> dict:
        return {"status": "ok", "service": "secure-file-service"}

    def error_response(status_code: int, message: str, code: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": message}},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(_: Request, exc: RequestValidationError):
        missing_fields = [
            ".".join(str(item) for item in error["loc"] if item != "body")
            for error in exc.errors()
            if error.get("type") == "missing"
        ]
        if missing_fields:
            message = f"missing parameters: {', '.join(missing_fields)}"
        else:
            message = "invalid request parameters"
        return error_response(400, message, "bad_request")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        message = str(exc.detail) if exc.detail else "request failed"
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            410: "expired",
            413: "payload_too_large",
        }
        return error_response(exc.status_code, message, code_map.get(exc.status_code, "error"))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "environment": settings.app_env}

    @app.post("/v1/files/upload", response_model=UploadResponse, status_code=201)
    def upload_file(user_id: str = Form(...), file: UploadFile = File(...)):
        if not user_id.strip():
            raise HTTPException(status_code=400, detail="user_id is required")
        if not file.filename:
            raise HTTPException(status_code=400, detail="filename is required")

        try:
            file_id, saved_path, size = storage.save_file(
                owner_id=user_id,
                source=file,
                max_size_bytes=settings.max_upload_size_bytes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc

        record = repository.create_file(
            file_id=file_id,
            owner_id=user_id,
            filename=file.filename,
            storage_path=str(saved_path),
            size=size,
        )
        return UploadResponse(**record)

    @app.get("/v1/users/{user_id}/files", response_model=FileListResponse)
    def list_owner_files(user_id: str):
        rows = repository.list_files_for_owner(user_id)
        files = [FileRecord(**row) for row in rows]
        return FileListResponse(files=files)

    @app.post("/v1/files/{file_id}/sign", response_model=SignLinkResponse)
    def create_signed_link(file_id: str, payload: SignLinkRequest, request: Request):
        if payload.ttl_seconds < settings.min_ttl_seconds:
            raise HTTPException(
                status_code=400,
                detail=f"ttl_seconds must be >= {settings.min_ttl_seconds}",
            )
        if payload.ttl_seconds > settings.max_ttl_seconds:
            raise HTTPException(
                status_code=400,
                detail=f"ttl_seconds must be <= {settings.max_ttl_seconds}",
            )

        file_row = repository.get_file(file_id)
        if not file_row:
            raise HTTPException(status_code=404, detail="file not found")
        if file_row["owner_id"] != payload.owner_id:
            raise HTTPException(status_code=403, detail="forbidden")

        expires_at = int(datetime.now(timezone.utc).timestamp()) + payload.ttl_seconds
        signature = signer.sign(file_id=file_id, owner_id=payload.owner_id, expires_at=expires_at)

        repository.record_link_generation(
            file_id=file_id,
            owner_id=payload.owner_id,
            ttl_seconds=payload.ttl_seconds,
        )

        params = urlencode(
            {
                "file_id": file_id,
                "owner_id": payload.owner_id,
                "exp": expires_at,
                "sig": signature,
            }
        )
        signed_url = str(request.base_url)[:-1] + f"/v1/files/download?{params}"

        return SignLinkResponse(file_id=file_id, expires_at=expires_at, signed_url=signed_url)

    @app.get("/v1/files/download")
    def download_file(
        file_id: str = Query(...),
        owner_id: str = Query(...),
        exp: int = Query(...),
        sig: str = Query(...),
    ):
        now = int(datetime.now(timezone.utc).timestamp())
        if exp < now:
            raise HTTPException(status_code=410, detail="link expired")
        if not signer.verify(file_id=file_id, owner_id=owner_id, expires_at=exp, signature=sig):
            raise HTTPException(status_code=403, detail="invalid signature")

        file_row = repository.get_file(file_id)
        if not file_row:
            raise HTTPException(status_code=404, detail="file not found")
        if file_row["owner_id"] != owner_id:
            raise HTTPException(status_code=403, detail="forbidden")

        file_path = Path(file_row["storage_path"])
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="file content missing")

        return FileResponse(path=file_path, filename=file_row["filename"], media_type="application/octet-stream")

    return app


app = create_app()
