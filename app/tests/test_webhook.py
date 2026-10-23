import json

from webhook import SECRET_HEADER, health_payload, is_configured, process_webhook

SECRET = "s3cr3t-largo"


def run(headers, body, expected=SECRET, handler=None):
    seen = []
    status, text = process_webhook(
        headers=headers,
        body=body,
        expected_secret=expected,
        handle=handler or seen.append,
    )
    return status, text, seen


def test_valid_request_calls_the_handler():
    update = {"update_id": 1}
    status, _, seen = run({SECRET_HEADER: SECRET}, json.dumps(update))
    assert status == 200 and seen == [update]


def test_wrong_secret_is_rejected_without_calling_the_handler():
    status, _, seen = run({SECRET_HEADER: "otro"}, "{}")
    assert status == 401 and seen == []


def test_missing_header_is_rejected():
    status, _, seen = run({}, "{}")
    assert status == 401 and seen == []


def test_unresolved_key_vault_reference_gives_503():
    status, _, seen = run(
        {SECRET_HEADER: "@Microsoft.KeyVault(VaultName=x;SecretName=y)"},
        "{}",
        expected="@Microsoft.KeyVault(VaultName=x;SecretName=y)",
    )
    assert status == 503 and seen == []


def test_missing_expected_secret_gives_503():
    assert run({SECRET_HEADER: ""}, "{}", expected=None)[0] == 503
    assert run({SECRET_HEADER: ""}, "{}", expected="")[0] == 503


def test_invalid_json_gives_400():
    assert run({SECRET_HEADER: SECRET}, b"no es json")[0] == 400


def test_handler_error_still_returns_200_to_avoid_retry_loops():
    def boom(update):
        raise RuntimeError("fallo interno")

    status, _, _ = run({SECRET_HEADER: SECRET}, "{}", handler=boom)
    assert status == 200


def test_is_configured():
    assert is_configured("valor")
    assert not is_configured("")
    assert not is_configured(None)
    assert not is_configured("@Microsoft.KeyVault(SecretUri=https://x)")


def test_health_reports_presence_but_never_values():
    env = {
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "TELEGRAM_WEBHOOK_SECRET": "@Microsoft.KeyVault(VaultName=v;SecretName=s)",
        "OWNER_TELEGRAM_ID": "5",
    }
    payload = health_payload(env)
    assert payload == {
        "status": "ok",
        "token_configured": True,
        "webhook_secret_configured": False,
        "owner_configured": True,
    }
    assert "123:ABC" not in json.dumps(payload)
