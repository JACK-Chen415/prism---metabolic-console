"""OTP verification service with provider abstraction and abuse controls."""

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from secrets import randbelow
from typing import Dict, Optional, Protocol

from app.core.config import settings


@dataclass
class VerificationRecord:
    code: str
    purpose: str
    expires_at: datetime
    attempts: int = 0
    locked_until: Optional[datetime] = None


@dataclass
class OTPDeliveryReceipt:
    provider_name: str
    delivered: bool
    debug_code: Optional[str] = None
    message: str = "验证码已发送"


@dataclass
class OTPDispatchResult:
    success: bool
    expires_in: int
    provider_name: str
    message: str
    debug_code: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    locked_until: Optional[datetime] = None


class OTPProvider(Protocol):
    name: str

    def send(self, *, phone: str, purpose: str, code: str) -> OTPDeliveryReceipt:
        ...


class DevOTPProvider:
    """Development-only provider that surfaces the code for local testing."""

    name = "dev"

    def send(self, *, phone: str, purpose: str, code: str) -> OTPDeliveryReceipt:
        return OTPDeliveryReceipt(
            provider_name=self.name,
            delivered=True,
            debug_code=code,
            message="验证码已发送",
        )


class AuditOnlyOTPProvider:
    """Mock external provider placeholder: never returns the OTP to callers."""

    name = "audit_only"

    def send(self, *, phone: str, purpose: str, code: str) -> OTPDeliveryReceipt:
        return OTPDeliveryReceipt(
            provider_name=self.name,
            delivered=True,
            debug_code=None,
            message="验证码已发送",
        )


class VerificationService:
    def __init__(
        self,
        expire_minutes: int = 5,
        max_attempts: int = 5,
        send_limit: int = 5,
        send_window_seconds: int = 600,
        lockout_minutes: int = 15,
        provider: Optional[OTPProvider] = None,
    ):
        self.expire_minutes = expire_minutes
        self.max_attempts = max_attempts
        self.send_limit = send_limit
        self.send_window_seconds = send_window_seconds
        self.lockout_minutes = lockout_minutes
        self.provider = provider or self._build_provider()
        self._records: Dict[str, VerificationRecord] = {}
        self._send_history: Dict[str, list[datetime]] = {}

    def _key(self, phone: str, purpose: str) -> str:
        return f"{phone}:{purpose}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _build_provider() -> OTPProvider:
        provider_name = settings.otp_provider.strip().lower().replace("-", "_")
        if provider_name in {"dev", "development", "console"}:
            return DevOTPProvider()
        if provider_name == "audit_only":
            return AuditOnlyOTPProvider()
        raise RuntimeError("Unsupported OTP_PROVIDER; configure an implemented provider")

    def _rate_limit_retry_after(self, key: str, now: datetime) -> Optional[int]:
        window_start = now - timedelta(seconds=self.send_window_seconds)
        attempts = [item for item in self._send_history.get(key, []) if item >= window_start]
        self._send_history[key] = attempts
        if len(attempts) < self.send_limit:
            return None
        oldest = min(attempts)
        return max(1, int((oldest + timedelta(seconds=self.send_window_seconds) - now).total_seconds()))

    def _record_send(self, key: str, now: datetime) -> None:
        attempts = self._send_history.setdefault(key, [])
        attempts.append(now)

    def send_code(self, phone: str, purpose: str) -> OTPDispatchResult:
        key = self._key(phone, purpose)
        now = self._now()
        record = self._records.get(key)
        if record and record.locked_until and record.locked_until > now:
            retry_after = int((record.locked_until - now).total_seconds())
            return OTPDispatchResult(
                success=False,
                expires_in=self.expire_minutes * 60,
                provider_name=self.provider.name,
                message="验证码请求过于频繁，请稍后再试",
                retry_after_seconds=retry_after,
                locked_until=record.locked_until,
            )

        retry_after = self._rate_limit_retry_after(key, now)
        if retry_after is not None:
            return OTPDispatchResult(
                success=False,
                expires_in=self.expire_minutes * 60,
                provider_name=self.provider.name,
                message="验证码请求过于频繁，请稍后再试",
                retry_after_seconds=retry_after,
            )

        code = f"{randbelow(1000000):06d}"
        self._records[key] = VerificationRecord(
            code=code,
            purpose=purpose,
            expires_at=now + timedelta(minutes=self.expire_minutes),
        )
        self._record_send(key, now)

        receipt = self.provider.send(phone=phone, purpose=purpose, code=code)
        return OTPDispatchResult(
            success=receipt.delivered,
            expires_in=self.expire_minutes * 60,
            provider_name=receipt.provider_name,
            message=receipt.message,
            debug_code=receipt.debug_code,
        )

    def issue_code(self, phone: str, purpose: str) -> str:
        """Backward-compatible helper for local tests."""
        result = self.send_code(phone, purpose)
        return result.debug_code or ""

    def verify(self, phone: str, purpose: str, code: str) -> bool:
        key = self._key(phone, purpose)
        record = self._records.get(key)
        if not record:
            return False

        now = self._now()
        if record.expires_at < now:
            self._records.pop(key, None)
            return False

        if record.locked_until and record.locked_until > now:
            return False

        if record.attempts >= self.max_attempts:
            record.locked_until = now + timedelta(minutes=self.lockout_minutes)
            self._records[key] = record
            return False

        if record.code != code:
            record.attempts += 1
            if record.attempts >= self.max_attempts:
                record.locked_until = now + timedelta(minutes=self.lockout_minutes)
            self._records[key] = record
            return False

        self._records.pop(key, None)
        return True

    def is_locked(self, phone: str, purpose: str) -> bool:
        record = self._records.get(self._key(phone, purpose))
        return bool(record and record.locked_until and record.locked_until > self._now())


verification_service = VerificationService()
