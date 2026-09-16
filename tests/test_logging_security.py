import logging

from app import main as main_module


def test_production_exception_logging_omits_exception_details_and_stacktrace(caplog, monkeypatch):
    monkeypatch.setattr(main_module, "is_development", False)
    secret = "password=super-secret-token"
    error = RuntimeError(secret)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        main_module._log_exception("operation_failed request_id=%s", error, "trace-123")

    message = caplog.records[-1].getMessage()
    assert "operation_failed request_id=%s" in message
    assert "trace-123" in message
    assert "RuntimeError" in message
    assert secret not in message
    assert "Traceback" not in message


def test_production_exception_logging_sanitizes_context(caplog, monkeypatch):
    monkeypatch.setattr(main_module, "is_development", False)
    error = RuntimeError("sensitive detail")

    with caplog.at_level(logging.ERROR, logger="app.main"):
        main_module._log_exception(
            "operation_failed request_id=%s",
            error,
            "trace-123\nforged-entry",
        )

    message = caplog.records[-1].getMessage()
    assert "trace-123 forged-entry" in message
    assert "\n" not in message
    assert "sensitive detail" not in message
