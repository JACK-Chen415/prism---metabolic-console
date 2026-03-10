"""
短信验证码服务（开发版）

当前实现为内存存储，适合本地开发和单实例部署。
"""

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from secrets import randbelow
from typing import Dict, Optional


@dataclass
class VerificationRecord:
    code: str
    purpose: str
    expires_at: datetime
    attempts: int = 0


class VerificationService:
    def __init__(self, expire_minutes: int = 5, max_attempts: int = 5):
        self.expire_minutes = expire_minutes
        self.max_attempts = max_attempts
        self._records: Dict[str, VerificationRecord] = {}

    def _key(self, phone: str, purpose: str) -> str:
        return f"{phone}:{purpose}"

    def issue_code(self, phone: str, purpose: str) -> str:
        code = f"{randbelow(1000000):06d}"
        self._records[self._key(phone, purpose)] = VerificationRecord(
            code=code,
            purpose=purpose,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes),
        )
        return code

    def verify(self, phone: str, purpose: str, code: str) -> bool:
        key = self._key(phone, purpose)
        record = self._records.get(key)
        if not record:
            return False

        now = datetime.now(timezone.utc)
        if record.expires_at < now:
            self._records.pop(key, None)
            return False

        if record.attempts >= self.max_attempts:
            self._records.pop(key, None)
            return False

        if record.code != code:
            record.attempts += 1
            self._records[key] = record
            return False

        self._records.pop(key, None)
        return True


verification_service = VerificationService()
