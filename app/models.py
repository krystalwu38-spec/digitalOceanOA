from datetime import datetime

from pydantic import BaseModel, Field


class FileRecord(BaseModel):
    file_id: str
    owner_id: str
    filename: str
    size: int
    uploaded_at: datetime


class UploadResponse(BaseModel):
    file_id: str
    owner_id: str
    filename: str
    size: int
    uploaded_at: datetime


class SignLinkRequest(BaseModel):
    owner_id: str = Field(min_length=1, max_length=128)
    ttl_seconds: int = Field(gt=0)


class SignLinkResponse(BaseModel):
    file_id: str
    expires_at: int
    signed_url: str


class FileListResponse(BaseModel):
    files: list[FileRecord]
