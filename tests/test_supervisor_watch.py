from __future__ import annotations

import json
import subprocess

import pytest

from aao import supervisor_service
from aao.notifier import FileSink, consume


class Client:
    def __init__(self, events, rules):
        self.events = events
        self.rules = rules
        self.calls = []

    def installation_token(self, owner, repo):
        assert (owner, repo) == ("acme", "widget")
        return "test-token"

    def request(self, method, path):
        self.calls.append(path)
        if path.endswith("/events?per_page=100"):
            return self.events
        if path.endswith("/rules/branches/main"):
            if isinstance(self.rules, Exception):
                raise self.rules
            return self.rules
        raise AssertionError(path)


def _events(actor="alessbarb", ref="refs/heads/main", push_id=7):
    return [{"type": "PushEvent", "actor": {"login": actor}, "payload": {
        "before": "a" * 40, "head": "b" * 40, "push_id": push_id, "ref": ref, "repository_id": 42,
    }}]


def _rules(audit_integration=5448107, omit_update=False):
    rules = [{"type": rule, "ruleset_source_type": "Repository", "ruleset_source": "acme/widget",
              "ruleset_id": 1, "parameters": {}}
             for rule in ("pull_request", "non_fast_forward", "deletion")]
    if not omit_update:
        rules.append({"type": "update", "ruleset_source_type": "Repository", "ruleset_source": "acme/widget",
                      "ruleset_id": 1, "parameters": {}})
    rules.append({"type": "required_status_checks", "ruleset_source_type": "Repository",
                  "ruleset_source": "acme/widget", "ruleset_id": 1, "parameters": {
                      "required_status_checks": [{"context": "aao-audit", "integration_id": audit_integration},
                                                   {"context": "test"}]}})
    return rules


@pytest.fixture
def setup(tmp_path):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True)
    config = {"repository": "acme/widget", "state_path": str(tmp_path / "supervisor-state.json"),
              "private_key": str(private), "key_id": "supervisor", "validity_seconds": 300,
              "integrator_login": "aao-integrator[bot]"}
    events = tmp_path / "events"
    return config, public, events, tmp_path


def _watch(config, events_dir, events, rules):
    return supervisor_service.watch(config, Client(events, rules), events_dir=events_dir)


def _read_events(path):
    return [json.loads(item.read_text()) for item in sorted(path.glob("*.json"))]


def _consume_each(events, public, tmp_path):
    sink = FileSink(tmp_path / "notifications.jsonl")
    state = tmp_path / "notifier-state.json"
    for event in events:
        assert consume(event, {"supervisor": str(public)}, state,
                       event["detected_at"] if "detected_at" in event else event["expires_at"], sink) == event["sequence"]


def test_watch_detects_non_integrator_main_push_once_and_ignores_other_pushes(setup):
    config, public, directory, tmp_path = setup
    assert _watch(config, directory, _events(), _rules())["governance_violations"] == 1
    assert _watch(config, directory, _events(), _rules())["events"] == 0
    assert _watch(config, directory, _events(actor="aao-integrator[bot]", push_id=8), _rules())["events"] == 0
    assert _watch(config, directory, _events(ref="refs/heads/feature", push_id=9), _rules())["events"] == 0
    recorded = _read_events(directory)
    assert [event["type"] for event in recorded] == ["governance-violation"]
    assert recorded[0]["actor"] == "alessbarb" and recorded[0]["push_id"] == 7
    _consume_each(recorded, public, tmp_path)


def test_watch_drift_dedupes_and_emits_restore(setup):
    config, public, directory, tmp_path = setup
    rules_off = _rules(omit_update=True)
    assert _watch(config, directory, [], rules_off)["ruleset_drift"] == 1
    assert _watch(config, directory, [], rules_off)["events"] == 0
    assert _watch(config, directory, [], _rules())["ruleset_restored"] == 1
    recorded = _read_events(directory)
    assert [event["type"] for event in recorded] == ["ruleset-drift", "ruleset-restored"]
    assert "update" in recorded[0]["missing"]
    _consume_each(recorded, public, tmp_path)


def test_watch_detects_audit_check_publisher_change(setup):
    config, _public, directory, _ = setup
    result = _watch(config, directory, [], _rules(audit_integration=123))
    assert result["ruleset_drift"] == 1
    assert "required_status_checks:aao-audit:integration_id" in _read_events(directory)[0]["missing"]


def test_watch_api_failure_writes_nothing(setup):
    config, _public, directory, _ = setup
    with pytest.raises(RuntimeError):
        _watch(config, directory, _events(), RuntimeError("API unavailable"))
    assert not directory.exists()
    assert not (directory.parent / "watch-state.json").exists()
