from scripts import ai_release_smoke as smoke


class FakeReadyClient:
    def __init__(self, response):
        self.response = response

    def get(self, _url):
        return self.response


class FakeReadyResponse:
    status_code = 503
    content = b"{}"
    headers = {"x-request-id": "req-ready"}
    is_success = False

    def json(self):
        return {
            "status": "degraded",
            "checks": {
                "database": "ok",
                "config": "degraded",
            },
        }


class FakeImageClient:
    def __init__(self, response):
        self.response = response

    def post(self, *_args, **_kwargs):
        return self.response


class FakeFailedImageResponse:
    status_code = 200
    content = b"{}"
    headers = {"x-request-id": "req-image"}
    is_success = True

    def json(self):
        return {
            "success": False,
            "foods": [],
        }


def test_normalize_api_url_adds_api_prefix_once():
    assert smoke.normalize_api_url("https://api.example.com") == "https://api.example.com/api"
    assert smoke.normalize_api_url("https://api.example.com/api") == "https://api.example.com/api"
    assert smoke.normalize_api_url("https://api.example.com/api/") == "https://api.example.com/api"


def test_smoke_check_public_dict_redacts_sensitive_metadata():
    check = smoke.SmokeCheck(
        name="chat.message.create",
        status="pass",
        duration_ms=12.5,
        status_code=200,
        request_id="req-1",
        metadata={
            "phone": "13900000000",
            "password": "secret",
            "access_token": "token",
            "prompt": "raw user prompt",
            "image_path": "/tmp/private.jpg",
            "message_id": 123,
            "nested": {
                "refresh_token": "refresh",
                "cost_status": "unconfigured",
            },
        },
    )

    public = check.to_public_dict()
    serialized = str(public)

    assert public["metadata"]["message_id"] == 123
    assert public["metadata"]["nested"] == {"cost_status": "unconfigured"}
    assert "13900000000" not in serialized
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "raw user prompt" not in serialized
    assert "/tmp/private.jpg" not in serialized


def test_hash_identifier_is_stable_and_short_without_raw_value():
    raw = "13900000000"

    hashed = smoke.hash_identifier(raw)

    assert hashed == smoke.hash_identifier(raw)
    assert hashed is not None and len(hashed) == 16
    assert raw not in hashed


def test_allow_degraded_ready_accepts_degraded_503():
    runner = smoke.SmokeRunner(api_url="https://api.example.com", timeout_seconds=1, fail_on_degraded_ready=False)
    runner.client = FakeReadyClient(FakeReadyResponse())

    runner.check_ready()

    assert runner.checks[0].status == "pass"
    assert runner.checks[0].status_code == 503


def test_image_smoke_fails_when_backend_returns_no_foods(tmp_path):
    image_path = tmp_path / "food.jpg"
    image_path.write_bytes(b"fake image bytes")
    runner = smoke.SmokeRunner(api_url="https://api.example.com", timeout_seconds=1)
    runner.session_id = 123
    runner.client = FakeImageClient(FakeFailedImageResponse())

    runner.recognize_image(image_path=image_path, prompt="smoke")

    assert runner.checks[0].status == "fail"
    assert runner.checks[0].status_code == 200
    assert runner.checks[0].metadata["food_count"] == 0
