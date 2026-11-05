"""Deterministic, presentation-only motion for the virtual office.

Routes are supplied by the versioned visual floor plan. This module never
creates organization records, assignments, messages, tasks, or evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from math import atan2, hypot, isfinite


@dataclass(frozen=True)
class Point:
    x: float
    z: float


@dataclass(frozen=True)
class WorldPosition:
    x: float
    z: float
    facing: float
    segment: int
    distance_along_route: float


def validate_route(points: Sequence[Point]) -> tuple[Point, ...]:
    """Validate a repeatable walk circuit; endpoints are connected implicitly."""
    if not 2 <= len(points) <= 128:
        raise ValueError("A world route needs between 2 and 128 waypoints")
    result = tuple(points)
    if any(not isfinite(p.x) or not isfinite(p.z) or abs(p.x) > 500 or abs(p.z) > 500 for p in result):
        raise ValueError("World route coordinates must be finite and inside the map bounds")
    if any(hypot(a.x - b.x, a.z - b.z) < 0.05 for a, b in pairwise(result)):
        raise ValueError("Adjacent route waypoints must be distinct")
    if hypot(result[0].x - result[-1].x, result[0].z - result[-1].z) < 0.05:
        raise ValueError("Route must not repeat its first waypoint as the last")
    return result


def position_on_route(
    points: Sequence[Point], *, started_at: datetime, now: datetime, speed: float,
) -> WorldPosition:
    """Resolve the server-time position on a closed route, stable across reloads."""
    route = validate_route(points)
    if not isfinite(speed) or not 0.05 <= speed <= 2.0:
        raise ValueError("World route speed must be between 0.05 and 2.0 map units/second")
    lengths = [hypot(b.x - a.x, b.z - a.z) for a, b in zip(route, (*route[1:], route[0]))]
    perimeter = sum(lengths)
    elapsed = max(0.0, (now - started_at).total_seconds())
    distance = (elapsed * speed) % perimeter
    remaining = distance
    for index, (start, end, length) in enumerate(zip(route, (*route[1:], route[0]), lengths)):
        if remaining <= length:
            ratio = remaining / length
            return WorldPosition(
                x=start.x + (end.x - start.x) * ratio,
                z=start.z + (end.z - start.z) * ratio,
                facing=atan2(end.x - start.x, end.z - start.z),
                segment=index,
                distance_along_route=distance,
            )
        remaining -= length
    raise AssertionError("Validated route must contain a positive perimeter")
