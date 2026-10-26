import threading

import pytest

from scripts import run_project_coordinator as coordinator


def test_one_pass_assigns_only_confirmed_groups_with_unassigned_children(monkeypatch):
    calls = []
    groups = [
        {"id": "g-ready", "parent_status": "INBOX", "children": [
            {"assigned_principal_id": None, "status": "INBOX"},
        ]},
        {"id": "g-assigned", "parent_status": "INBOX", "children": [
            {"assigned_principal_id": "agent-a", "status": "INBOX"},
        ]},
        {"id": "g-done", "parent_status": "DONE", "children": [
            {"assigned_principal_id": None, "status": "INBOX"},
        ]},
        {"id": "g-empty", "parent_status": "INBOX", "children": []},
    ]

    monkeypatch.setattr(coordinator, "api_call", lambda path, **kwargs: (
        {"principal_id": "pm-1"} if path == "/v1/principals/me"
        else groups if path.endswith("/work-groups")
        else calls.append((path, kwargs)) or {"assigned": [{"work_id": "w-1"}]}
    ))

    assert coordinator.coordinate_once("project-1", "pm-1").assigned == 1
    assert len(calls) == 1
    assert calls[0][0] == (
        "/v1/agent/projects/project-1/work-groups/g-ready/assign-unassigned"
    )
    assert calls[0][1]["method"] == "POST"


def test_one_pass_only_consolidates_ready_groups_when_explicitly_enabled(monkeypatch):
    calls = []
    groups = [
        {
            "id": "g-ready", "title": "Ready", "parent_status": "INBOX",
            "source_sha256": "a" * 64, "consolidation_ready": True,
            "consolidation": None,
            "children": [{
                "work_id": "w-done", "status": "DONE", "assigned_principal_id": "agent-1",
                "executions": [{"id": "exec-1", "status": "DONE", "result_sha256": "b" * 64}],
                "reviews": [{
                    "id": "review-1", "decision": "APPROVE", "candidate_sha": "c" * 40,
                    "evidence": "private auditor notes must not be copied into the summary",
                }],
                "evidence": "private work evidence must not be copied into the summary",
            }],
        },
        {
            "id": "g-not-ready", "parent_status": "INBOX", "source_sha256": "d" * 64,
            "consolidation_ready": False, "consolidation": None,
            "children": [{"work_id": "w-running", "status": "IN_PROGRESS"}],
        },
        {
            "id": "g-already", "parent_status": "INBOX", "source_sha256": "e" * 64,
            "consolidation_ready": True, "consolidation": {"id": "c-existing"},
            "children": [{"work_id": "w-done-2", "status": "DONE"}],
        },
    ]

    def fake_api(path, *, method="GET", body=None):
        if path == "/v1/principals/me":
            return {"principal_id": "pm-1"}
        if path.endswith("/work-groups"):
            return groups
        calls.append((path, method, body))
        return {"id": "consolidation-1", "created": True}

    monkeypatch.setattr(coordinator, "api_call", fake_api)

    default_result = coordinator.coordinate_once("project-1", "pm-1")
    assert default_result.assigned == 0
    assert default_result.consolidated == 0
    assert calls == []

    result = coordinator.coordinate_once(
        "project-1", "pm-1", auto_consolidate=True,
    )
    assert result.assigned == 0
    assert result.consolidated == 1
    assert len(calls) == 1
    path, method, body = calls[0]
    assert path == "/v1/agent/projects/project-1/work-groups/g-ready/consolidation"
    assert method == "POST"
    assert body["expected_source_sha256"] == "a" * 64
    assert body["summary"].startswith("Consolidación descriptiva automática")
    assert "w-done" in body["summary"]
    assert "c" * 40 in body["summary"]
    assert "evidence" not in body["summary"].lower()
    assert "private auditor notes" not in body["summary"]
    assert "private work evidence" not in body["summary"]

    coordinator.coordinate_once("project-1", "pm-1", auto_consolidate=True)
    assert calls[1][2] == body


def test_auto_consolidation_fails_closed_without_a_valid_source_digest(monkeypatch):
    monkeypatch.setattr(coordinator, "api_call", lambda path, **kwargs: (
        {"principal_id": "pm-1"} if path == "/v1/principals/me"
        else [{"id": "g-ready", "parent_status": "INBOX", "source_sha256": "bad",
               "consolidation_ready": True, "consolidation": None,
               "children": [{"work_id": "w-1", "status": "DONE"}]}]
    ))
    with pytest.raises(coordinator.CoordinatorError, match="source digest"):
        coordinator.coordinate_once("project-1", "pm-1", auto_consolidate=True)


def test_auto_consolidation_reports_only_newly_created_records(monkeypatch):
    group = {
        "id": "g-ready", "parent_status": "INBOX", "source_sha256": "a" * 64,
        "consolidation_ready": True, "consolidation": None,
        "children": [{"work_id": "w-done", "status": "DONE"}],
    }
    monkeypatch.setattr(coordinator, "api_call", lambda path, **kwargs: (
        {"principal_id": "pm-1"} if path == "/v1/principals/me"
        else [group] if path.endswith("/work-groups")
        else {"id": "consolidation-1", "created": False}
    ))

    result = coordinator.coordinate_once("project-1", "pm-1", auto_consolidate=True)

    assert result.consolidated == 0


def test_one_pass_fails_closed_if_token_identity_does_not_match_config(monkeypatch):
    monkeypatch.setattr(coordinator, "api_call", lambda *_args, **_kwargs: {"principal_id": "other-pm"})
    with pytest.raises(coordinator.CoordinatorError, match="does not match"):
        coordinator.coordinate_once("project-1", "pm-1")


def test_watch_runs_again_until_stopped(monkeypatch):
    stop = threading.Event()
    calls = []
    waits = []

    def one_pass(project_id, principal_id, *, auto_consolidate=False, materialize_routines=False):
        calls.append((project_id, principal_id))
        if len(calls) == 2:
            stop.set()
        return coordinator.CoordinatorPassResult(assigned=len(calls))

    monkeypatch.setattr(coordinator, "coordinate_once", one_pass)
    assert coordinator.run_watch(
        "project-1", "pm-1", poll_interval_seconds=2,
        stop_event=stop, wait=waits.append,
    ) == 0
    assert calls == [("project-1", "pm-1"), ("project-1", "pm-1")]
    assert waits == [2]


@pytest.mark.parametrize("interval", [0, 301])
def test_watch_rejects_unbounded_poll_interval(interval):
    with pytest.raises(coordinator.CoordinatorError, match="poll interval"):
        coordinator.run_watch(
            "p", "pm", poll_interval_seconds=interval,
            stop_event=threading.Event(),
        )


def test_routines_materialize_only_when_explicitly_enabled(monkeypatch):
    calls = []

    def api(path, **kwargs):
        calls.append((path, kwargs))
        if path == "/v1/principals/me":
            return {"principal_id": "pm-1"}
        if path.endswith("/routines/materialize"):
            return {"materialized": [{"work_id": "real-work"}]}
        return []

    monkeypatch.setattr(coordinator, "api_call", api)
    assert coordinator.coordinate_once("p", "pm-1").materialized == 0
    assert not any("routines" in path for path, _ in calls)
    assert coordinator.coordinate_once("p", "pm-1", materialize_routines=True).materialized == 1
    assert ("/v1/agent/projects/p/routines/materialize", {"method": "POST"}) in calls


def test_watch_keeps_backend_routine_ticks_without_a_browser(monkeypatch):
    stop = threading.Event()
    calls = []

    def one_pass(project_id, principal_id, *, auto_consolidate=False, materialize_routines=False):
        calls.append(materialize_routines)
        if len(calls) == 2:
            stop.set()
        return coordinator.CoordinatorPassResult(materialized=1)

    monkeypatch.setattr(coordinator, "coordinate_once", one_pass)
    assert coordinator.run_watch("p", "pm", poll_interval_seconds=1, stop_event=stop,
                                 materialize_routines=True, wait=lambda _: None) == 0
    assert calls == [True, True]


def test_cli_parses_routine_opt_in(monkeypatch):
    calls = []
    monkeypatch.setattr("sys.argv", ["coordinator", "--project-id", "p", "--principal-id", "pm",
                                    "--materialize-routines"])

    def one_pass(project, principal, **kwargs):
        calls.append((project, principal, kwargs))
        return coordinator.CoordinatorPassResult(materialized=1)

    monkeypatch.setattr(coordinator, "coordinate_once", one_pass)
    assert coordinator.main() == 0
    assert calls == [("p", "pm", {"auto_consolidate": False, "materialize_routines": True})]
