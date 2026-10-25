"""Minimal type-specific contract requirements for registered capabilities."""
import re

REQUIRED_CONTRACT_FIELDS = {
    "cli_script": {"purpose", "entrypoint", "inputs", "outputs", "platform"},
    "library": {"purpose", "import_name", "inputs", "outputs", "platform"},
    "application_service": {"purpose", "endpoint", "authentication", "inputs", "outputs"},
    "agent": {"purpose", "compatible_roles", "inputs", "outputs", "authority_boundary"},
    "agent_skill": {
        "purpose", "compatible_roles", "inputs", "outputs", "usage_limits",
    },
    "knowledge_procedure": {"purpose", "procedure", "inputs", "outputs", "applicability"},
    "workflow": {"purpose", "trigger", "steps", "inputs", "outputs"},
}


def missing_contract_fields(capability_type: str, contract: dict) -> set[str]:
    """Return absent/empty fields from a type's contract; does not assess truth."""
    required = REQUIRED_CONTRACT_FIELDS.get(capability_type)
    if required is None:
        return {"<known capability type>"}
    return {field for field in required if not contract.get(field)}


AGENT_BACKENDS = {"fixture", "codex"}
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def model_profile_errors(contract: dict) -> list[str]:
    """Shape errors of an optional ``model_profile``: which backend, provider and model an agent capability runs.

    The model is data in the catalog, never a name the code branches on; registering it activates nothing."""
    if "model_profile" not in contract:
        return []
    profile = contract["model_profile"]
    if not isinstance(profile, dict):
        return ["model_profile must be an object"]
    errors = []
    if profile.get("backend") not in AGENT_BACKENDS:
        errors.append("model_profile.backend must be one of " + ", ".join(sorted(AGENT_BACKENDS)))
    if not isinstance(profile.get("provider"), str) or not _PROFILE_NAME.fullmatch(profile["provider"]):
        errors.append("model_profile.provider is required")
    model = profile.get("model")
    if model is not None and (not isinstance(model, str) or not _PROFILE_NAME.fullmatch(model)):
        errors.append("model_profile.model must be a model id or null")
    quality = profile.get("quality", {})
    if not isinstance(quality, dict) or not all(
            isinstance(k, str) and type(v) is int and 0 <= v <= 5 for k, v in quality.items()):
        errors.append("model_profile.quality must map seats to 0-5")
    cost = profile.get("cost_per_attempt_usd", 0)
    if type(cost) not in (int, float) or not 0 <= cost <= 1000:
        errors.append("model_profile.cost_per_attempt_usd must be a number between 0 and 1000")
    seats = profile.get("seats", [])
    if not isinstance(seats, list) or not all(isinstance(s, str) and _PROFILE_NAME.fullmatch(s) for s in seats):
        errors.append("model_profile.seats must be a list of names")
    return errors
