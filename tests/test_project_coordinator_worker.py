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

    assert coordinator.coordinate_once("project-1", "pm-1") == 1
    assert len(calls) == 1
    assert calls[0][0] == (
        "/v1/agent/projects/project-1/work-groups/g-ready/assign-unassigned"
    )
    assert calls[0][1]["method"] == "POST"


def test_one_pass_fails_closed_if_token_identity_does_not_match_config(monkeypatch):
    monkeypatch.setattr(coordinator, "api_call", lambda *_args, **_kwargs: {"principal_id": "other-pm"})
    with pytest.raises(coordinator.CoordinatorError, match="does not match"):
        coordinator.coordinate_once("project-1", "pm-1")


def test_watch_runs_again_until_stopped(monkeypatch):
    stop = threading.Event()
    calls = []
    waits = []

    def one_pass(project_id, principal_id):
        calls.append((project_id, principal_id))
        if len(calls) == 2:
            stop.set()
        return len(calls)

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
