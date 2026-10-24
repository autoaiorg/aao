from __future__ import annotations

import copy
import json

import pytest

from aao import protected_routes, r1_pipeline


@pytest.fixture
def normative():
    return protected_routes.load_document()

def _copy(routes):
    routes = dict(routes)
    return {"protected_routes": routes, "protected_routes_sha256": protected_routes.routes_digest(routes)}

@pytest.mark.nt("NT-01-1")
def test_added_route_divergence_rejects(normative):
    base = _copy(protected_routes.route_map(normative))
    registry = copy.deepcopy(base)
    registry["protected_routes"]["new-policy-file"] = "R3"
    registry["protected_routes_sha256"] = protected_routes.routes_digest(registry["protected_routes"])
    with pytest.raises(ValueError, match="protected routes digest mismatch: registry"):
        protected_routes.compare_copies(normative, registry, base)

@pytest.mark.nt("NT-01-2")
def test_removed_route_divergence_rejects(normative):
    base = _copy(protected_routes.route_map(normative))
    operational = copy.deepcopy(base)
    operational["protected_routes"].pop(next(iter(operational["protected_routes"])))
    operational["protected_routes_sha256"] = protected_routes.routes_digest(operational["protected_routes"])
    with pytest.raises(ValueError, match="protected routes digest mismatch: operational"):
        protected_routes.compare_copies(normative, base, operational)

@pytest.mark.nt("NT-01-3")
def test_changed_class_divergence_rejects(normative):
    base = _copy(protected_routes.route_map(normative))
    changed = copy.deepcopy(base)
    path = next(iter(changed["protected_routes"]))
    changed["protected_routes"][path] = "R1"
    changed["protected_routes_sha256"] = protected_routes.routes_digest(changed["protected_routes"])
    with pytest.raises(ValueError, match="protected routes digest mismatch: registry"):
        protected_routes.compare_copies(normative, changed, base)

@pytest.mark.nt("NT-01-4")
def test_overlapping_higher_pattern_controls_classification():
    assert protected_routes.classify(["docs/GOV-REV-002x"], {
        "docs/GOV-REV-002*": "R3", "*": "R2",
    }) == "R3"
    assert protected_routes.classify(["docs/GOV-REV-002x"], {"*": "R2"}) == "R2"

@pytest.mark.nt("NT-01-4")
def test_overlapping_route_added_to_only_one_copy_fails_closed(normative):
    registry = _copy(protected_routes.route_map(normative))
    operational = _copy(protected_routes.route_map(normative))
    changed = copy.deepcopy(normative)
    changed["routes"].append({"path": "docs/GOV-REV-*", "minimum_risk_class": "R3"})
    with pytest.raises(ValueError, match="protected routes digest mismatch: registry"):
        protected_routes.compare_copies(changed, registry, operational)

@pytest.mark.nt("NT-01-5")
@pytest.mark.parametrize("divergent_copy,reason", [
    ("registry", "registry"), ("operational", "operational"), ("normative", "registry"),
])
def test_every_pairwise_copy_divergence_rejects(normative, divergent_copy, reason):
    routes = protected_routes.route_map(normative)
    registry, operational = _copy(routes), _copy(routes)
    candidate_normative = copy.deepcopy(normative)
    if divergent_copy == "registry":
        registry["protected_routes_sha256"] = "0" * 64
    elif divergent_copy == "operational":
        operational["protected_routes"]["extra"] = "R3"
    else:
        candidate_normative["routes"].append({"path": "extra-route", "minimum_risk_class": "R3"})
    with pytest.raises(ValueError, match=f"protected routes digest mismatch: {reason}"):
        protected_routes.compare_copies(candidate_normative, registry, operational)

class _CheckClient:
    def __init__(self, app_id):
        self.app_id = app_id

    def request(self, method, path, body=None):
        return {"check_runs": [{"id": 1, "name": "test", "status": "completed", "conclusion": "success",
                                "app": {"id": self.app_id}}]}

@pytest.mark.nt("NT-02-5")
def test_production_required_check_requires_authorized_publisher():
    allowed = {"test": [15368]}
    assert r1_pipeline._check_passed(_CheckClient(999), "org/repo", "a" * 40, "test", allowed) == (
        False, "required check publisher is unauthorized: test")
    assert r1_pipeline._check_passed(_CheckClient(15368), "org/repo", "a" * 40, "test", allowed) == (True, "passed")

class _AttributionClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def installation_token(self, *_args):
        return "opaque-test-token"

    def request(self, method, path):
        self.calls.append(path)
        value = self.responses.get(path, [])
        if isinstance(value, Exception):
            raise value
        return value

def _push(actor, head, before, ref="refs/heads/feature"):
    return {"type": "PushEvent", "actor": {"login": actor}, "payload":
            {"head": head, "before": before, "ref": ref}}

@pytest.mark.nt("NT-02-3")
def test_supervisor_attributes_fork_prs_through_push_chain_and_commit_history(tmp_path, monkeypatch):
    from aao import manifest_audit
    from aao.manifest_audit import attributed_implementers, attributed_principals
    from aao.supervisor_service import attribution

    candidate, parent, commit = "a" * 40, "b" * 40, "c" * 40
    registry = "/repos/org/repo/pulls?state=open&per_page=100"
    fork_events = "/repos/forker/repo/events?per_page=100"
    responses = {registry: [{"number": 7, "head": {"sha": candidate, "ref": "feature",
                       "repo": {"full_name": "forker/repo"}}}],
        fork_events: [_push("unregistered[bot]", candidate, parent),
                      _push("from-other-branch[bot]", commit, "d" * 40, "refs/heads/source"),
                      _push("creator[bot]", parent, "0" * 40)],
        "/repos/org/repo/pulls/7/commits?per_page=100": [{"sha": candidate}, {"sha": commit}]}
    client = _AttributionClient(responses)
    path = tmp_path / "attribution.json"
    result = attribution({"repository": "org/repo", "attribution_path": str(path)}, client)
    assert result == {"candidates": 1, "skipped_prs": []}
    data = json.loads(path.read_text())
    assert data["candidates"][candidate] == ["creator[bot]", "from-other-branch[bot]", "unregistered[bot]"]
    assert fork_events in client.calls
    monkeypatch.setattr(manifest_audit, "read_protected", lambda file_path, owners: file_path.read_bytes())
    anchor = {"attribution_path": path, "anchor_owner_uids": (path.stat().st_uid,),
              "attribution_writer_uid": path.stat().st_uid,
              "policy": {"push_principals": {"creator[bot]": "codex"}}}
    assert attributed_principals(anchor, candidate) == data["candidates"][candidate]
    assert attributed_implementers(anchor, candidate) == []

def test_supervisor_incomplete_chain_and_malformed_fork_events_skip_prs(tmp_path):
    from aao.supervisor_service import attribution
    pulls = "/repos/org/repo/pulls?state=open&per_page=100"
    client = _AttributionClient({pulls: [
        {"number": 8, "head": {"sha": "a" * 40, "ref": "f", "repo": {"full_name": "fork/repo"}}}],
        "/repos/fork/repo/events?per_page=100": [_push("x", "a" * 40, "b" * 40, "refs/heads/f")]})
    path = tmp_path / "attribution.json"
    assert attribution({"repository": "org/repo", "attribution_path": str(path)}, client) == {
        "candidates": 0, "skipped_prs": [8]}
    assert not path.exists()

def test_supervisor_malformed_fork_skips_repo_and_pull_failure_writes_nothing(tmp_path):
    from aao.supervisor_service import attribution
    pulls = "/repos/org/repo/pulls?state=open&per_page=100"
    pr = {"number": 9, "head": {"sha": "a" * 40, "ref": "f", "repo": {"full_name": "fork/repo"}}}
    path = tmp_path / "attribution.json"
    client = _AttributionClient({pulls: [pr], "/repos/fork/repo/events?per_page=100": [
        {"type": "PushEvent", "actor": {"login": "x"}, "payload": {"head": "bad", "before": "0" * 40, "ref": "refs/heads/f"}}]})
    assert attribution({"repository": "org/repo", "attribution_path": str(path)}, client)["skipped_prs"] == [9]
    assert not path.exists()
    failed = _AttributionClient({pulls: RuntimeError("API failure")})
    with pytest.raises(RuntimeError):
        attribution({"repository": "org/repo", "attribution_path": str(path)}, failed)
    assert not path.exists()

@pytest.mark.nt("NT-02-10")
def test_push_principal_maps_must_be_injective(tmp_path):
    import json

    from aao import integration_authorization
    from aao.manifest_audit import attributed_implementers
    from aao.supervisor_service import load_config
    registry = tmp_path / "registry.json"
    config_path = tmp_path / "config.json"
    registry.write_text(json.dumps({"ledger_keys": {"k": "key"}, "integrator_key_id": "k",
        "push_principals": {"one": "same", "two": "same"}}))
    config_path.write_text(json.dumps({"schema": "aao.supervisor-config.v1", "auditor_uid": 1,
        "ledger_path": "l", "state_path": "s", "heartbeat_path": "h", "intake_socket": "i",
        "private_key": "p", "key_id": "k", "trust_registry": str(registry), "validity_seconds": 1,
        "repository": "org/repo", "attribution_path": "a"}))
    registry.chmod(0o600)
    config_path.chmod(0o600)
    with pytest.raises(ValueError, match="ambiguous"):
        load_config(config_path, (0, config_path.stat().st_uid), (registry.stat().st_uid,))
    attrib_path = tmp_path / "attrib.json"
    attrib_path.write_text(json.dumps({"candidates": {"a" * 40: ["one"]}}))
    monkeypatch = pytest.MonkeyPatch()
    from aao import manifest_audit
    monkeypatch.setattr(manifest_audit, "read_protected", lambda file_path, owners: file_path.read_bytes())
    anchor = {"attribution_path": attrib_path, "anchor_owner_uids": (attrib_path.stat().st_uid,),
              "attribution_writer_uid": attrib_path.stat().st_uid,
              "policy": {"push_principals": {"one": "same", "two": "same"}}}
    assert attributed_implementers(anchor, "a" * 40) == []
    reasons = integration_authorization.validate({"attribution": [{"principal": "same"}]}, "", {
        "push_principals": {"one": "same", "two": "same"}})
    monkeypatch.undo()
    assert "actor attribution inconclusive" in reasons
