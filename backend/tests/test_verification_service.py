from app.services.verification_service import AuditOnlyOTPProvider, DevOTPProvider, VerificationService


def test_issue_and_verify_code_success():
    service = VerificationService(expire_minutes=5, max_attempts=3, provider=DevOTPProvider())
    code = service.issue_code("13800138000", "login")
    assert len(code) == 6
    assert service.verify("13800138000", "login", code) is True


def test_verify_code_fail_after_wrong_attempts():
    service = VerificationService(expire_minutes=5, max_attempts=2, provider=DevOTPProvider())
    code = service.issue_code("13800138000", "login")
    assert service.verify("13800138000", "login", "000000") is False
    assert service.verify("13800138000", "login", "111111") is False
    assert service.verify("13800138000", "login", code) is False


def test_send_code_returns_debug_code_and_rate_limits():
    service = VerificationService(
        expire_minutes=5,
        send_limit=1,
        send_window_seconds=600,
        provider=DevOTPProvider(),
    )
    first = service.send_code("13800138000", "login")
    second = service.send_code("13800138000", "login")

    assert first.success is True
    assert first.debug_code is not None and len(first.debug_code) == 6
    assert second.success is False
    assert second.retry_after_seconds is not None


def test_verify_code_locks_after_max_attempts():
    service = VerificationService(
        expire_minutes=5,
        max_attempts=2,
        lockout_minutes=15,
        provider=DevOTPProvider(),
    )
    code = service.issue_code("13800138000", "login")

    assert service.verify("13800138000", "login", "000000") is False
    assert service.verify("13800138000", "login", "111111") is False
    assert service.is_locked("13800138000", "login") is True
    assert service.verify("13800138000", "login", code) is False


def test_audit_only_provider_never_returns_debug_code():
    service = VerificationService(expire_minutes=5, provider=AuditOnlyOTPProvider())

    result = service.send_code("13800138000", "login")

    assert result.success is True
    assert result.debug_code is None
