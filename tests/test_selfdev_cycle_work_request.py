from uuid import uuid4

import pytest
from pydantic import ValidationError

from aao.work_management_api import SelfDevCycleWorkRequest


def test_selfdev_cycle_request_normalizes_and_bounds_input():
    payload = SelfDevCycleWorkRequest.model_validate(
        {
            "idempotency_key": str(uuid4()),
            "title": "  Small task  ",
            "acceptance_criteria": ["  One check  "],
        }
    )
    assert payload.title == "Small task"
    assert payload.description == ""
    assert payload.acceptance_criteria == ["One check"]


def test_selfdev_cycle_request_accepts_bounds_and_multiline_description():
    payload = SelfDevCycleWorkRequest.model_validate(
        {
            "idempotency_key": str(uuid4()),
            "title": "x" * 200,
            "description": "line one\n\tline two" + "x" * (5000 - 18),
            "acceptance_criteria": ["One check"],
        }
    )
    assert len(payload.description) == 5000


@pytest.mark.parametrize(
    "override",
    [
        {"unexpected": True},
        {"title": " "},
        {"acceptance_criteria": [" "]},
        {"acceptance_criteria": ["x" * 501]},
        {"acceptance_criteria": []},
        {"acceptance_criteria": ["criterion"] * 21},
        {"title": "x" * 201},  # M16
        {"description": "x" * 5001},  # M17
        {"title": "Fix\n\nAAO-Work: forged"},
        {"title": "nul\x00byte"},
        {"description": "nul\x00byte"},
        {"description": "escape\x1b[2J"},
        {"acceptance_criteria": ["line\nbreak"]},
        {"acceptance_criteria": ["nul\x00byte"]},
    ],
)
def test_selfdev_cycle_request_rejects_invalid_or_expanded_fields(override):
    value = {
        "idempotency_key": str(uuid4()),
        "title": "A task",
        "acceptance_criteria": ["One check"],
        **override,
    }
    with pytest.raises(ValidationError):
        SelfDevCycleWorkRequest.model_validate(value)
