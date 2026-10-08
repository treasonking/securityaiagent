from __future__ import annotations

import json
import sqlite3

from common.schemas import RunStatus
from controller.repository import Repository


def test_sqlite_wal_history_redaction_and_restart_interrupt(tmp_path):
    path = tmp_path / "controller.sqlite3"
    repo = Repository(path)
    conversation = repo.create_conversation("local-user")
    repo.add_message(
        conversation["conversation_id"],
        "user",
        "Authorization: Bearer secret-token and api_key=sk-1234567890abcdef",
    )
    run_id = repo.create_run(
        conversation_id=conversation["conversation_id"],
        owner_id="local-user",
        scenario_id="access-control",
        target_id="lab-web",
        provider_mode="mock",
        tool_transport="function",
    )
    repo.update_run_status(run_id, RunStatus.RUNNING)
    assert repo.journal_mode() == "wal"
    assert "secret-token" not in repo.list_messages(conversation["conversation_id"])[0]["content"]
    assert "sk-1234567890abcdef" not in path.read_bytes().decode("utf-8", errors="ignore")
    assert repo.interrupt_unfinished_runs() == 1
    assert repo.get_run(run_id, "local-user")["status"] == RunStatus.INTERRUPTED


def test_event_ids_are_monotonic_and_unique(tmp_path):
    repo = Repository(tmp_path / "controller.sqlite3")
    conversation = repo.create_conversation("local-user")
    run_id = repo.create_run(
        conversation_id=conversation["conversation_id"],
        owner_id="local-user",
        scenario_id="access-control",
        target_id="lab-web",
        provider_mode="mock",
        tool_transport="function",
    )
    ids = [repo.append_event(run_id, "running", {"index": index})["event_id"] for index in range(4)]
    assert ids == [1, 2, 3, 4]
    assert [item["event_id"] for item in repo.list_events(run_id)] == ids
