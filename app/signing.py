import hashlib
import hmac


class URLSigner:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode("utf-8")

    def _message(self, *, file_id: str, owner_id: str, expires_at: int) -> bytes:
        return f"{file_id}:{owner_id}:{expires_at}".encode("utf-8")

    def sign(self, *, file_id: str, owner_id: str, expires_at: int) -> str:
        msg = self._message(file_id=file_id, owner_id=owner_id, expires_at=expires_at)
        return hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()

    def verify(self, *, file_id: str, owner_id: str, expires_at: int, signature: str) -> bool:
        expected = self.sign(file_id=file_id, owner_id=owner_id, expires_at=expires_at)
        return hmac.compare_digest(expected, signature)
