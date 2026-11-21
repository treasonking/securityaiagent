import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import service_config as config


def values_for(service):
    values = config.read_config(service, config.ROOT / f".env.{service}.example")
    for key in config.SECRETS & values.keys():
        if key != "OPENAI_API_KEY":
            values[key] = "fake-test-secret-for-" + key
    return values


@pytest.mark.parametrize("service", sorted(config.KEYS))
def test_service_examples_are_separate_and_checks_never_launch(service, monkeypatch):
    values = values_for(service)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("offline validation launched a process"))
    result = config.validate_config(service, values)
    assert result["network_requests"] == 0
    serialized = json.dumps(result)
    assert not any(values[key] in serialized for key in config.SECRETS & values.keys() if values[key])
    if service == "worker":
        http = result["scope_policies"][1]
        assert http["effective_limits"]["max_requests"] == 9
        assert http["effective_limits"]["max_tool_calls"] == 10
        assert http["snapshot_sha256"] == "d8136fafff1bda07b32b13feab426c76ccf570e40ac52c9b8e494f48ef2a9d1a"


@pytest.mark.parametrize("service,foreign", [("controller", "LAB_USER_A_PASSWORD"), ("worker", "OPENAI_API_KEY"),
                                            ("target", "WORKER_TOKEN"), ("worker", "APP_SESSION_SECRET")])
def test_foreign_secrets_rejected_without_echo(tmp_path, service, foreign):
    path = tmp_path / "settings.env"
    path.write_text(f"{foreign}=DO-NOT-ECHO\n")
    with pytest.raises(config.ServiceConfigError) as exc:
        config.read_config(service, path)
    assert "DO-NOT-ECHO" not in str(exc.value)


@pytest.mark.parametrize("body", ['WORKER_TOKEN=one\nWORKER_TOKEN=two', 'WORKER_TOKEN',
                                  'WORKER_TOKEN="unfinished', 'WORKER_TOKEN=${AMBIENT_SECRET}',
                                  'WORKER_TOKEN="first\nsecond"', 'UNREVIEWED_KEY=secret'])
def test_malformed_duplicate_and_interpolated_files_rejected(tmp_path, body):
    path = tmp_path / "settings.env"
    path.write_text(body)
    with pytest.raises(config.ServiceConfigError):
        config.read_config("worker", path)


@pytest.mark.parametrize("key,value", [("WORKER_TOKEN", ""), ("APP_ACCESS_TOKEN", "short"),
    ("APP_SECURE_COOKIE", "yes"), ("CONTROLLER_RUN_TIMEOUT_SECONDS", "nan"),
    ("MODEL_MAX_CALLS", "0"), ("MODEL_PROVIDER", "other"), ("TOOL_TRANSPORT", "other"),
    ("WORKER_URL", "http://evil.example:9000"), ("MCP_WORKER_URL", "http://10.77.0.21:9000/mcp"),
    ("MCP_WORKER_URL", "http://10.77.0.20:9000/mcp?key=secret"), ("UI_ALLOWED_HOSTS", "*")])
def test_invalid_controller_settings_fail_before_launch(key, value):
    values = values_for("controller")
    values[key] = value
    with pytest.raises(config.ServiceConfigError):
        config.validate_config("controller", values)


def test_distinct_auth_domains_and_explicit_live_configuration():
    values = values_for("controller")
    values["APP_ACCESS_TOKEN"] = values["WORKER_TOKEN"]
    with pytest.raises(config.ServiceConfigError):
        config.validate_config("controller", values)
    values = values_for("controller")
    values["MODEL_PROVIDER"] = "openai"
    with pytest.raises(config.ServiceConfigError):
        config.validate_config("controller", values)
    values.update(OPENAI_API_KEY="fake-not-a-live-key", OPENAI_MODEL="test-model")
    assert config.validate_config("controller", values)["ok"]


def test_worker_uses_scope_checker_and_does_not_accept_origin_override():
    values = values_for("worker")
    values["TARGET_BASE_URL"] = "http://10.78.0.31:8080"
    with pytest.raises(config.ServiceConfigError, match="SCOPE_ORIGIN_MISMATCH"):
        config.validate_config("worker", values)
    values = values_for("worker")
    values["HTTP_MAX_REQUESTS"] = "2"
    assert config.validate_config("worker", values)["scope_policies"][1]["effective_limits"]["max_requests"] == 2
    values["HTTP_REQUESTS_PER_SECOND"] = "0"
    assert config.validate_config("worker", values)["scope_policies"][1]["effective_limits"]["requests_per_second"] == 2


@pytest.mark.parametrize("service", sorted(config.KEYS))
def test_launcher_filters_inherited_application_settings(service, monkeypatch, tmp_path):
    values = values_for(service)
    path = tmp_path / "service.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()))
    monkeypatch.setenv("OPENAI_API_KEY", "inherited-secret-never-pass")
    monkeypatch.setenv("LAB_USER_A_PASSWORD", "inherited-password-never-pass")
    monkeypatch.setenv("TARGET_REGISTRY_PATH", "inherited-invalid-file")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "inherited-access-never-pass")
    captured = {}
    def launch(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, "run", launch)
    monkeypatch.setattr(sys, "argv", ["service_config", "serve", service, "--env-file", str(path)])
    with pytest.raises(SystemExit) as exc:
        config.main()
    assert exc.value.code == 0
    assert captured["command"] == [sys.executable, *config.COMMANDS[service]]
    assert captured["cwd"] == config.ROOT
    assert not set(captured["env"]) & (config.ALL_KEYS - config.KEYS[service])
    assert "inherited-secret-never-pass" not in captured["env"].values()
    assert "inherited-password-never-pass" not in captured["env"].values()
    assert os.environ["OPENAI_API_KEY"] == "inherited-secret-never-pass"


def test_invalid_file_cannot_start_process(tmp_path, monkeypatch, capsys):
    path = tmp_path / "bad.env"
    path.write_text("UNKNOWN_SECRET=never-echo-value\n")
    monkeypatch.setattr(sys, "argv", ["service_config", "serve", "worker", "--env-file", str(path)])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("invalid config launched a service"))
    with pytest.raises(SystemExit) as exc:
        config.main()
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "never-echo-value" not in output.out + output.err
    assert json.loads(output.out)["reason_code"] == "SERVICE_CONFIG_INVALID"


def test_offline_target_check_has_no_target_database_side_effect(tmp_path):
    values = values_for("target")
    database = tmp_path / "must-not-create.sqlite3"
    values["TARGET_DATABASE_PATH"] = str(database)
    path = tmp_path / "target.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()))
    result = subprocess.run([sys.executable, "-m", "common.service_config", "check", "target", "--env-file", str(path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0 and json.loads(result.stdout)["network_requests"] == 0
    assert not database.exists()
