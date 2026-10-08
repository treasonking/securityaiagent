from __future__ import annotations

from pathlib import Path

from worker.registry import load_target_registry


def test_registry_origin_fields_are_self_consistent():
    path = Path(__file__).resolve().parents[1] / "config" / "targets.json"
    registry = load_target_registry(path)
    assert registry["lab-web"].base_url == "http://10.78.0.30:8080"
