from aao.model_router import Requirements, route


def _cap(cid, backend, provider, quality, seats=("patch.tests",), roles=("implementer",)):
    return {"capability_id": cid, "version": "1", "compatible_roles": list(roles),
            "model_profile": {"backend": backend, "provider": provider, "model": None, "seats": list(seats),
                              "quality": {s: quality for s in seats}}}


def test_never_recommends_a_backend_that_is_not_activated_even_if_best():
    catalog = [_cap("codex", "codex", "openai", 5), _cap("fixture", "fixture", "fixture", 1)]
    decision = route(Requirements(seat="patch.tests"), catalog, activated=frozenset())
    assert decision.capability_id == "fixture"
    assert ("codex@1", "backend codex not activated") in decision.rejected
    assert route(Requirements(seat="patch.tests"), catalog, activated=frozenset({"codex"})).capability_id == "codex"


def test_a_tie_yields_no_recommendation():
    catalog = [_cap("a", "codex", "openai", 3), _cap("b", "claude", "anthropic", 3)]
    decision = route(Requirements(seat="patch.tests"), catalog, activated=frozenset({"codex", "claude"}))
    assert decision.capability_id is None and "PM decides" in decision.reasons[0]


def test_filters_record_why_each_candidate_was_rejected():
    catalog = [_cap("other-seat", "codex", "openai", 5, seats=("patch.docs",)),
               _cap("other-role", "codex", "openai", 5, roles=("auditor",)),
               _cap("excluded", "codex", "openai", 5),
               _cap("down", "claude", "anthropic", 5),
               {"capability_id": "legacy", "version": "1", "compatible_roles": ["implementer"], "model_profile": None}]
    decision = route(Requirements(seat="patch.tests", exclude_providers=frozenset({"openai"})), catalog,
                     activated=frozenset({"codex", "claude"}), unavailable=frozenset({"claude"}))
    assert decision.capability_id is None and decision.reasons == ("no eligible candidate",)
    assert dict(decision.rejected) == {
        "other-seat@1": "seat patch.tests not offered", "other-role@1": "role implementer not compatible",
        "excluded@1": "provider openai excluded", "down@1": "backend claude unavailable",
        "legacy@1": "no model_profile"}


def test_budget_filters_candidates_whose_estimate_does_not_fit():
    cheap, dear = _cap("cheap", "fixture", "fixture", 1), _cap("dear", "codex", "openai", 5)
    cheap["model_profile"]["cost_per_attempt_usd"] = 0.1
    dear["model_profile"]["cost_per_attempt_usd"] = 2
    decision = route(Requirements(seat="patch.tests"), [cheap, dear], activated=frozenset({"codex"}), budget_left=1)
    assert decision.capability_id == "cheap"
    assert ("dear@1", "estimated cost 2 over budget left 1") in decision.rejected
    assert route(Requirements(seat="patch.tests"), [cheap, dear], activated=frozenset({"codex"})).capability_id == "dear"
