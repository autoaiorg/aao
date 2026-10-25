from aao.planner import Admission, decide_admission

BASE = {
    "project_active": True,
    "mandate_confirmed": True,
    "authorized": True,
    "dependencies_satisfied": True,
    "capacity_available": True,
    "within_budget": True,
    "residual_risk": "low",
    "emergency_stop": False,
}


def test_admission_permits_only_fully_authorized_work():
    assert decide_admission(**BASE).status == Admission.READY
    for field, value, expected in [
        ("emergency_stop", True, Admission.DENY),
        ("mandate_confirmed", False, Admission.DENY),
        ("authorized", False, Admission.DENY),
        ("project_active", False, Admission.DEFER),
        ("dependencies_satisfied", False, Admission.DEFER),
        ("capacity_available", False, Admission.DEFER),
        ("within_budget", False, Admission.DEFER),
        ("residual_risk", "high", Admission.DEFER),
        ("residual_risk", "unknown", Admission.DENY),
    ]:
        assert decide_admission(**{**BASE, field: value}).status == expected


def test_residual_risk_boundaries():
    assert decide_admission(**{**BASE, "residual_risk": "moderate"}).status == Admission.READY
    assert decide_admission(**{**BASE, "residual_risk": "critical"}).status == Admission.DEFER


def test_emergency_stop_takes_precedence_over_other_failed_conditions():
    result = decide_admission(
        project_active=False,
        mandate_confirmed=False,
        authorized=False,
        dependencies_satisfied=False,
        capacity_available=False,
        within_budget=False,
        residual_risk="unknown",
        emergency_stop=True,
    )

    assert result.status == Admission.DENY
    assert result.reason == "Emergency stop active"
