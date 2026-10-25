"""Recommend an agent capability for a task from the catalog. Pure: no I/O, and it authorizes nothing.

Choosing a model is separate from being allowed to run it: staging re-checks provider activation on its own,
so a recommendation for a non-activated provider can never execute.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Requirements:
    seat: str                                   # what the task needs, e.g. "patch.tests"
    role: str = "implementer"                   # AAO role the model will fill
    exclude_providers: frozenset[str] = field(default_factory=frozenset)  # e.g. the implementer's, for an auditor


@dataclass(frozen=True)
class RouteDecision:
    capability_id: str | None                   # None: no candidate, or a tie the PM must break
    version: str | None
    reasons: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]       # ("capability@version", why)


def route(req: Requirements, candidates: list[dict], *, activated: frozenset[str],
          unavailable: frozenset[str] = frozenset()) -> RouteDecision:
    """``candidates``: {"capability_id", "version", "compatible_roles", "model_profile"} rows of the catalog.

    Filters, each with a recorded reason: role, seat, backend activated, provider not excluded, backend
    available. The highest ``quality[seat]`` wins; a tie yields no recommendation (same rule as
    ``capability_evaluation.recommend``)."""
    rejected: list[tuple[str, str]] = []
    eligible: list[tuple[int, dict]] = []
    for c in candidates:
        name = f"{c['capability_id']}@{c['version']}"
        profile = c.get("model_profile") or {}
        backend, provider = profile.get("backend"), profile.get("provider")
        if not profile:
            why = "no model_profile"
        elif req.role not in (c.get("compatible_roles") or []):
            why = f"role {req.role} not compatible"
        elif req.seat not in (profile.get("seats") or []):
            why = f"seat {req.seat} not offered"
        elif backend != "fixture" and backend not in activated:
            why = f"backend {backend} not activated"
        elif provider in req.exclude_providers:
            why = f"provider {provider} excluded"
        elif backend in unavailable:
            why = f"backend {backend} unavailable"
        else:
            eligible.append((int((profile.get("quality") or {}).get(req.seat, 0)), c))
            continue
        rejected.append((name, why))
    if not eligible:
        return RouteDecision(None, None, ("no eligible candidate",), tuple(rejected))
    best = max(q for q, _ in eligible)
    winners = [c for q, c in eligible if q == best]
    if len(winners) > 1:
        names = ", ".join(f"{c['capability_id']}@{c['version']}" for c in winners)
        return RouteDecision(None, None, (f"tie at quality {best} between {names}; PM decides",), tuple(rejected))
    w = winners[0]
    return RouteDecision(w["capability_id"], w["version"], (f"highest quality {best} for seat {req.seat}",),
                         tuple(rejected))
