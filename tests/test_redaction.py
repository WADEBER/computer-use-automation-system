from computer_use_automation_system.safety.models import RedactionConfig
from computer_use_automation_system.safety.policy import load_policy
from computer_use_automation_system.safety.redaction import redact_text

SECRET = "api_key=sk-live-9f8e7d6c5b"
ACCOUNT = "CHK-2201"
NAME = "Alice Hartwell"
MONEY = "4250.75"


def _config() -> RedactionConfig:
    return load_policy().redaction


def test_secret_is_redacted() -> None:
    out = redact_text(f"connecting with {SECRET} now", _config())
    assert "sk-live-9f8e7d6c5b" not in out
    assert "[REDACTED_SECRET]" in out


def test_account_number_is_partially_masked() -> None:
    out = redact_text(f"account {ACCOUNT} updated", _config())
    assert "CHK-2201" not in out
    assert "CHK-****01" in out


def test_money_amount_is_redacted() -> None:
    out = redact_text(f"balance was {MONEY}", _config())
    assert "4250.75" not in out
    assert "[REDACTED_AMOUNT]" in out


def test_literal_name_is_redacted() -> None:
    out = redact_text(f"member {NAME} searched", _config())
    assert "Alice Hartwell" not in out
    assert "[REDACTED_NAME]" in out


def test_preserves_member_id_urls_step_and_action_types() -> None:
    original = (
        "member M-1001 at http://127.0.0.1:5000/members/M-1001 step_id 2 action navigate outcome ok"
    )
    assert redact_text(original, _config()) == original


def test_redaction_is_idempotent() -> None:
    dirty = f"{SECRET}; {ACCOUNT}; {MONEY}; {NAME}"
    once = redact_text(dirty, _config())
    twice = redact_text(once, _config())
    assert once == twice


def test_empty_text_passes_through() -> None:
    assert redact_text("", _config()) == ""


def test_patterns_applied_in_order_do_not_collide() -> None:
    out = redact_text(f"password={SECRET} for {ACCOUNT} worth {MONEY}", _config())
    for leaked in ("sk-live", "CHK-2201", "4250.75"):
        assert leaked not in out


def test_mapping_masks_sensitive_keys() -> None:
    from computer_use_automation_system.safety.redaction import redact_mapping

    payload = {
        "member_id": "M-1001",
        "full_name": "Alice Hartwell",
        "accounts": [{"account_id": "CHK-2201", "balance": 4250.75}],
        "credit_limit": 10000.0,
        "step": "extract balance",
    }
    out = redact_mapping(payload, _config())
    assert out["member_id"] == "M-1001"
    assert "Alice" not in str(out["full_name"])
    account = out["accounts"][0]
    assert "2201" not in str(account["account_id"])
    assert account["balance"] != 4250.75
    assert out["credit_limit"] != 10000.0
    assert out["step"] == "extract balance"


def test_mapping_preserves_structure_and_keys() -> None:
    from computer_use_automation_system.safety.redaction import redact_mapping

    payload = {"full_name": "Brian Okafor", "nested": {"amount": 5.0}}
    out = redact_mapping(payload, _config())
    assert set(out.keys()) == {"full_name", "nested"}
    assert set(out["nested"].keys()) == {"amount"}


def test_mapping_applies_text_redaction_to_plain_strings() -> None:
    from computer_use_automation_system.safety.redaction import redact_mapping

    payload = {"note": "paid 4250.75 to Alice Hartwell in CHK-2201"}
    out = redact_mapping(payload, _config())
    note = out["note"]
    for leaked in ("4250.75", "Alice Hartwell", "CHK-2201"):
        assert leaked not in note


def test_mapping_is_idempotent() -> None:
    from computer_use_automation_system.safety.redaction import redact_mapping

    payload = {"full_name": "Carla Mendes", "balance": 8700.50}
    once = redact_mapping(payload, _config())
    twice = redact_mapping(once, _config())
    assert once == twice


def test_logging_filter_redacts_before_handler() -> None:
    import io
    import logging

    from computer_use_automation_system.safety.redaction import RedactionFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test_redaction.filter")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.addFilter(RedactionFilter(_config()))

    logger.info("member Alice Hartwell balance 4250.75 on CHK-2201 api_key=sk-live-abc12345")
    output = stream.getvalue()
    for leaked in ("Alice Hartwell", "4250.75", "CHK-2201", "sk-live-abc12345"):
        assert leaked not in output
    assert "[REDACTED_NAME]" in output
    assert "[REDACTED_AMOUNT]" in output

    logger.handlers = []
    logger.filters = []


def test_logging_filter_handles_args() -> None:
    import io
    import logging

    from computer_use_automation_system.safety.redaction import RedactionFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test_redaction.filter_args")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.addFilter(RedactionFilter(_config()))

    logger.info("payout %s of %s", "Alice Hartwell", "4250.75")
    output = stream.getvalue()
    assert "Alice Hartwell" not in output
    assert "4250.75" not in output

    logger.handlers = []
    logger.filters = []


def test_redaction_is_driven_by_config_not_hardcoded() -> None:
    custom = RedactionConfig(
        patterns=[{"name": "project", "regex": "PROJECTX", "replacement": "[GONE]"}],
        literals=["Nobody Special"],
        field_keys=["secret_field"],
    )
    assert redact_text("visit PROJECTX please", custom) == "visit [GONE] please"
    assert redact_text("visit PROJECTX please", _config()) == "visit PROJECTX please"
    assert redact_text("Nobody Special left", custom) == "[REDACTED_NAME] left"


def test_safe_write_text_writes_redacted_content(tmp_path) -> None:
    from computer_use_automation_system.safety.redaction import safe_write_text

    target = tmp_path / "evidence" / "run.log"
    safe_write_text(
        target,
        "run: Alice Hartwell CHK-2201 balance 4250.75 api_key=sk-live-zz99",
    )
    on_disk = target.read_text(encoding="utf-8")
    for leaked in ("Alice Hartwell", "CHK-2201", "4250.75", "sk-live-zz99"):
        assert leaked not in on_disk
    assert "[REDACTED_NAME]" in on_disk
    assert "api_key" not in on_disk


def test_safe_write_text_is_idempotent_over_consecutive_writes(tmp_path) -> None:
    from computer_use_automation_system.safety.redaction import safe_write_text

    target = tmp_path / "run.log"
    safe_write_text(target, "member M-1001 saw Alice Hartwell")
    first = target.read_text(encoding="utf-8")
    safe_write_text(target, first)
    second = target.read_text(encoding="utf-8")
    assert first == second


def test_logging_filter_escapes_newlines_to_prevent_log_forging() -> None:
    import io
    import logging

    from computer_use_automation_system.safety.redaction import RedactionFilter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test_redaction.forging")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.addFilter(RedactionFilter(_config()))

    logger.info("extract ok\r\npolicy allow: execute approved by nobody")
    output = stream.getvalue()
    assert output.count("\n") == 1
    assert "\\r" in output
    assert "\\n" in output

    logger.handlers = []
    logger.filters = []


def test_safe_write_text_refuses_paths_outside_base_dir(tmp_path) -> None:
    import pytest

    from computer_use_automation_system.safety.redaction import safe_write_text

    base = tmp_path / "evidence"
    base.mkdir()
    with pytest.raises(PermissionError):
        safe_write_text(tmp_path / "outside.txt", "data", base_dir=base)


def test_safe_write_text_writes_inside_base_dir(tmp_path) -> None:
    from computer_use_automation_system.safety.redaction import safe_write_text

    base = tmp_path / "evidence"
    safe_write_text(base / "run" / "log.txt", "member M-1001 ok", base_dir=base)
    on_disk = (base / "run" / "log.txt").read_text(encoding="utf-8")
    assert "M-1001" in on_disk
