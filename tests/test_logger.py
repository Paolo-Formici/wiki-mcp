import json
import logging
from wiki_mcp.logger import StreamJsonFormatter, get_logger, log_event


def test_logger_json_output(capsys):
    logger = get_logger("test_json")
    log_event(logger, logging.INFO, "test_event", "Test message", key="val")

    captured = capsys.readouterr()
    assert captured.out
    data = json.loads(captured.out.strip())
    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["event"] == "test_event"
    assert data["details"]["key"] == "val"
