"""Sanitized gray-release smoke checks for a deployed Prism API.

This script is intentionally conservative: it never prints passwords, tokens,
OTP codes, raw chat text, food names, image bytes, image paths, or raw response
bodies. Output is a small JSON report with status codes, request IDs, timings,
and aggregate counts so operators can prove the deployed API is alive before a
controlled internal test or gray release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000/api"
CONSENT_VERSION = "2026-05-30"
SENSITIVE_METADATA_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "new_password",
    "old_password",
    "phone",
    "code",
    "otp",
    "prompt",
    "content",
    "raw_response",
    "image",
    "image_path",
    "file_path",
}


@dataclass
class SmokeCheck:
    name: str
    status: str
    duration_ms: float
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_type: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.request_id:
            payload["request_id"] = self.request_id
        safe_metadata = sanitize_metadata(self.metadata)
        if safe_metadata:
            payload["metadata"] = safe_metadata
        if self.error_type:
            payload["error_type"] = self.error_type
        return payload


def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = key.strip().lower()
        if normalized_key in SENSITIVE_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = [item for item in value if isinstance(item, (str, int, float, bool)) or item is None]
        elif isinstance(value, dict):
            nested = sanitize_metadata(value)
            if nested:
                safe[key] = nested
    return safe


def normalize_api_url(value: str | None) -> str:
    raw = (value or DEFAULT_API_URL).strip().rstrip("/")
    if not raw:
        raw = DEFAULT_API_URL.rstrip("/")
    return raw if raw.endswith("/api") else f"{raw}/api"


def hash_identifier(value: str | None) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def generated_phone() -> str:
    # 139 + 8 digits keeps the value inside the backend's China mobile regex.
    return "139" + f"{secrets.randbelow(100_000_000):08d}"


def generated_password() -> str:
    return "Smoke-" + secrets.token_urlsafe(12)


class SmokeRunner:
    def __init__(self, *, api_url: str, timeout_seconds: float, fail_on_degraded_ready: bool = True):
        self.api_url = normalize_api_url(api_url)
        self.fail_on_degraded_ready = fail_on_degraded_ready
        self.client = httpx.Client(timeout=httpx.Timeout(timeout_seconds))
        self.access_token: Optional[str] = None
        self.session_id: Optional[int] = None
        self.checks: list[SmokeCheck] = []

    def close(self) -> None:
        self.client.close()

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def _record_response(
        self,
        *,
        name: str,
        response: httpx.Response,
        start: float,
        ok: bool,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.checks.append(
            SmokeCheck(
                name=name,
                status="pass" if ok else "fail",
                status_code=response.status_code,
                request_id=response.headers.get("x-request-id"),
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                metadata=metadata or {},
            )
        )

    def _record_exception(self, *, name: str, start: float, exc: Exception) -> None:
        self.checks.append(
            SmokeCheck(
                name=name,
                status="fail",
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
                error_type=exc.__class__.__name__,
            )
        )

    def check_ready(self) -> None:
        name = "ready"
        start = time.perf_counter()
        try:
            response = self.client.get(self._url("/ready"))
            payload = response.json() if response.content else {}
            checks = payload.get("checks") if isinstance(payload, dict) else {}
            config = checks.get("config") if isinstance(checks, dict) else None
            database = checks.get("database") if isinstance(checks, dict) else None
            ready_status = payload.get("status") if isinstance(payload, dict) else None
            ok = response.is_success and (ready_status == "ready" or not self.fail_on_degraded_ready)
            self._record_response(
                name=name,
                response=response,
                start=start,
                ok=ok,
                metadata={
                    "ready_status": ready_status,
                    "database": database,
                    "config": config,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            self._record_exception(name=name, start=start, exc=exc)

    def register_or_login(self, *, phone: str, password: str, nickname: str) -> None:
        name = "auth.register_or_login"
        start = time.perf_counter()
        register_payload = {
            "phone": phone,
            "password": password,
            "nickname": nickname,
            "terms_accepted": True,
            "privacy_accepted": True,
            "ai_use_accepted": True,
            "health_disclaimer_accepted": True,
            "consent_version": CONSENT_VERSION,
        }
        try:
            response = self.client.post(self._url("/auth/register"), json=register_payload)
            flow = "register"
            if response.status_code == 400:
                flow = "login_existing"
                response = self.client.post(
                    self._url("/auth/login"),
                    json={"phone": phone, "password": password},
                )
            payload = response.json() if response.content else {}
            tokens = payload.get("tokens") if isinstance(payload, dict) else None
            if isinstance(tokens, dict):
                self.access_token = str(tokens.get("access_token") or "") or None
            ok = response.is_success and bool(self.access_token)
            self._record_response(
                name=name,
                response=response,
                start=start,
                ok=ok,
                metadata={
                    "flow": flow,
                    "actor_hash": hash_identifier(phone),
                    "has_access_token": bool(self.access_token),
                },
            )
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            self._record_exception(name=name, start=start, exc=exc)

    def create_chat_session(self) -> None:
        name = "chat.session.create"
        start = time.perf_counter()
        try:
            response = self.client.post(
                self._url("/chat/sessions"),
                headers=self._headers(),
                json={"title": "Gray release smoke"},
            )
            payload = response.json() if response.content else {}
            session_id = payload.get("id") if isinstance(payload, dict) else None
            self.session_id = int(session_id) if isinstance(session_id, int) else None
            self._record_response(
                name=name,
                response=response,
                start=start,
                ok=response.is_success and self.session_id is not None,
                metadata={"session_created": self.session_id is not None},
            )
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            self._record_exception(name=name, start=start, exc=exc)

    def send_chat_message(self, *, prompt: str) -> None:
        name = "chat.message.create"
        start = time.perf_counter()
        if not self.session_id:
            self.checks.append(
                SmokeCheck(name=name, status="skip", duration_ms=0, metadata={"reason": "missing_session"})
            )
            return
        try:
            response = self.client.post(
                self._url(f"/chat/sessions/{self.session_id}/messages"),
                headers=self._headers(),
                json={
                    "content": prompt,
                    "ai_mode": "STRICT",
                    "intervention_intensity": "STANDARD",
                },
            )
            payload = response.json() if response.content else {}
            attachments = payload.get("attachments") if isinstance(payload, dict) else {}
            telemetry = attachments.get("telemetry") if isinstance(attachments, dict) else {}
            knowledge = attachments.get("knowledge") if isinstance(attachments, dict) else {}
            self._record_response(
                name=name,
                response=response,
                start=start,
                ok=response.is_success and bool(payload.get("id") if isinstance(payload, dict) else None),
                metadata={
                    "message_id": payload.get("id") if isinstance(payload, dict) else None,
                    "cloud_called": telemetry.get("cloud_called") if isinstance(telemetry, dict) else None,
                    "cost_status": telemetry.get("cost_status") if isinstance(telemetry, dict) else None,
                    "origin": knowledge.get("origin") if isinstance(knowledge, dict) else None,
                    "fallback_status": knowledge.get("fallback_status") if isinstance(knowledge, dict) else None,
                    "response_chars": telemetry.get("response_chars") if isinstance(telemetry, dict) else None,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            self._record_exception(name=name, start=start, exc=exc)

    def recognize_image(self, *, image_path: Path, prompt: str) -> None:
        name = "chat.recognize_food.upload"
        start = time.perf_counter()
        if not self.session_id:
            self.checks.append(
                SmokeCheck(name=name, status="skip", duration_ms=0, metadata={"reason": "missing_session"})
            )
            return
        if not image_path.exists() or not image_path.is_file():
            self.checks.append(
                SmokeCheck(name=name, status="fail", duration_ms=0, metadata={"reason": "image_not_found"})
            )
            return
        content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
        try:
            with image_path.open("rb") as handle:
                files = {"file": ("smoke-image", handle, content_type)}
                data = {"prompt": prompt, "session_id": str(self.session_id)}
                response = self.client.post(
                    self._url("/chat/recognize-food/upload"),
                    headers=self._headers(),
                    files=files,
                    data=data,
                )
            payload = response.json() if response.content else {}
            foods = payload.get("foods") if isinstance(payload, dict) else []
            self._record_response(
                name=name,
                response=response,
                start=start,
                ok=response.is_success and "success" in payload,
                metadata={
                    "message_id": payload.get("message_id") if isinstance(payload, dict) else None,
                    "food_count": len(foods) if isinstance(foods, list) else 0,
                    "image_size_bytes": image_path.stat().st_size,
                    "content_type": content_type,
                },
            )
        except Exception as exc:  # pragma: no cover - exercised by live failures.
            self._record_exception(name=name, start=start, exc=exc)

    def report(self) -> dict[str, Any]:
        checks = [check.to_public_dict() for check in self.checks]
        failed = [check for check in self.checks if check.status == "fail"]
        return {
            "status": "fail" if failed else "pass",
            "api_url_hash": hash_identifier(self.api_url),
            "check_count": len(checks),
            "failed_count": len(failed),
            "checks": checks,
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run sanitized Prism gray-release smoke checks.")
    parser.add_argument("--api-url", default=os.getenv("PRISM_API_URL", DEFAULT_API_URL))
    parser.add_argument("--phone", default=os.getenv("PRISM_SMOKE_PHONE") or generated_phone())
    parser.add_argument("--password", default=os.getenv("PRISM_SMOKE_PASSWORD") or generated_password())
    parser.add_argument("--nickname", default=os.getenv("PRISM_SMOKE_NICKNAME", "PrismSmoke"))
    parser.add_argument(
        "--chat-prompt",
        default=os.getenv(
            "PRISM_SMOKE_CHAT_PROMPT",
            "请用不超过80字说明饭后散步对一般代谢健康的帮助，并提醒不能替代医生建议。",
        ),
    )
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--image-path", default=os.getenv("PRISM_SMOKE_IMAGE_PATH"))
    parser.add_argument(
        "--image-prompt",
        default=os.getenv("PRISM_SMOKE_IMAGE_PROMPT", "灰度冒烟：请识别图片中的食物并给出保守提示。"),
    )
    parser.add_argument("--allow-degraded-ready", action="store_true")
    parser.add_argument("--timeout", type=float, default=float(os.getenv("PRISM_SMOKE_TIMEOUT", "45")))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    runner = SmokeRunner(
        api_url=args.api_url,
        timeout_seconds=args.timeout,
        fail_on_degraded_ready=not args.allow_degraded_ready,
    )
    try:
        runner.check_ready()
        runner.register_or_login(phone=args.phone, password=args.password, nickname=args.nickname)
        if not args.skip_chat:
            runner.create_chat_session()
            runner.send_chat_message(prompt=args.chat_prompt)
            if args.image_path:
                runner.recognize_image(image_path=Path(args.image_path), prompt=args.image_prompt)
        report = runner.report()
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["status"] == "pass" else 1
    finally:
        runner.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
