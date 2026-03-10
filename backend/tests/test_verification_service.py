from app.services.verification_service import VerificationService


def test_issue_and_verify_code_success():
    service = VerificationService(expire_minutes=5, max_attempts=3)
    code = service.issue_code("13800138000", "login")
    assert len(code) == 6
    assert service.verify("13800138000", "login", code) is True


def test_verify_code_fail_after_wrong_attempts():
    service = VerificationService(expire_minutes=5, max_attempts=2)
    code = service.issue_code("13800138000", "login")
    assert service.verify("13800138000", "login", "000000") is False
    assert service.verify("13800138000", "login", "111111") is False
    assert service.verify("13800138000", "login", code) is False
