"""Defensive extractors for SimplyPrint's loosely-typed job payloads.

The live ``job`` object inside ``printers/Get`` is rendered by the panel and a
few of its keys vary by host/firmware. These helpers try the documented key
first and fall back to known aliases so sensors degrade gracefully instead of
breaking when a field is named differently or missing.
"""

from __future__ import annotations

from typing import Any


def _first(data: dict[str, Any] | None, *keys: str) -> Any:
    """Return the first present, non-None value among ``keys``."""
    if not data:
        return None
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def job_progress(job: dict[str, Any] | None) -> float | None:
    """Return print progress as a 0-100 percentage."""
    value = _first(
        job,
        "currentPercentage",
        "percentage",
        "progress",
        "completion",
        "percent",
    )
    if value is None:
        return None
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return None
    # Some hosts report 0-1 completion fractions.
    if 0 < pct <= 1:
        pct *= 100
    return round(max(0.0, min(100.0, pct)), 1)


def job_filename(job: dict[str, Any] | None) -> str | None:
    """Return the printing filename."""
    return _first(job, "filename", "name", "file")


def job_time_left(job: dict[str, Any] | None) -> int | None:
    """Return seconds remaining, if reported."""
    value = _first(
        job,
        "timeLeft",
        "time_left",
        "estimatedTime",
        "remaining",
        "secondsLeft",
    )
    return _as_int_seconds(value)


def job_time_elapsed(job: dict[str, Any] | None) -> int | None:
    """Return seconds elapsed, if reported."""
    value = _first(
        job,
        "printTime",
        "timePrinting",
        "elapsed",
        "time",
        "printedTime",
    )
    return _as_int_seconds(value)


def job_started(job: dict[str, Any] | None) -> Any:
    """Return the raw job start value (ISO string or unix seconds)."""
    return _first(job, "startDate", "started", "start_date", "start")


def job_layer(job: dict[str, Any] | None) -> int | None:
    """Return the current layer number, if reported."""
    value = _first(job, "layer", "currentLayer", "current_layer")
    return _as_int(value)


def job_total_layers(job: dict[str, Any] | None) -> int | None:
    """Return the total layer count, if reported."""
    value = _first(job, "totalLayers", "layers", "layer_count", "maxLayer")
    return _as_int(value)


def job_filament_grams(job: dict[str, Any] | None) -> float | None:
    """Return filament used for the current job in grams, if reported."""
    value = _first(job, "filUsageGram", "filamentUsageGram", "filament_grams")
    try:
        return round(float(value), 2) if value is not None else None
    except (TypeError, ValueError):
        return None


def primary_filament(filament: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the first assigned filament spool (lowest extruder index)."""
    if not isinstance(filament, dict) or not filament:
        return None
    # Keys are extruder indices as strings ("0", "1", ...).
    try:
        ordered = sorted(filament.items(), key=lambda kv: int(kv[0]))
    except (TypeError, ValueError):
        ordered = list(filament.items())
    for _, spool in ordered:
        if isinstance(spool, dict):
            return spool
    return None


def filament_remaining_percent(spool: dict[str, Any] | None) -> float | None:
    """Return remaining filament as a percentage of the spool total."""
    if not spool:
        return None
    total = spool.get("total")
    left = spool.get("left")
    try:
        if total and left is not None and float(total) > 0:
            return round(float(left) / float(total) * 100, 1)
    except (TypeError, ValueError):
        return None
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int_seconds(value: Any) -> int | None:
    try:
        return int(round(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None
