from scripts import ai_release_smoke as smoke


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
