#!/usr/bin/env python3
"""Frozen numerical and provenance primitives for formal-analysis-v1."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


SEMANTICS_VERSION = "formal-analysis-semantics-v1"
ANALYSIS_VERSION = "formal-analysis-v1"
MAX_GAP_S = 0.20
DUPLICATE_ATOL = 1.0e-12


class AnalysisError(RuntimeError):
    """Base fail-closed analysis error."""


class EvidenceError(AnalysisError):
    """Required evidence is absent, inconsistent, or incomplete."""


class ProvenanceError(AnalysisError):
    """An authoritative identity or dataset label did not match."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_inventory(root: Path) -> dict[str, str]:
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def inventory_sha256(root: Path) -> str:
    return canonical_sha256(file_inventory(root))


def json_load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read required JSON {path}: {exc}") from exc


def as_float_array(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise EvidenceError("signal contains non-finite numeric values")
    return array


@dataclass(frozen=True)
class Series:
    t: np.ndarray
    value: np.ndarray
    dropped_duplicate_count: int = 0

    def diagnostics(self, start: float | None = None, end: float | None = None) -> dict[str, Any]:
        gaps = np.diff(self.t)
        output: dict[str, Any] = {
            "first_timestamp": float(self.t[0]) if self.t.size else None,
            "last_timestamp": float(self.t[-1]) if self.t.size else None,
            "sample_count": int(self.t.size),
            "maximum_sample_gap_s": float(np.max(gaps)) if gaps.size else None,
            "dropped_duplicate_sample_count": self.dropped_duplicate_count,
        }
        if start is not None and end is not None:
            output.update({
                "expected_start": float(start),
                "expected_end": float(end),
                "expected_duration_s": float(end - start),
            })
        return output


def normalize_series(times: Sequence[float], values: Sequence[Any], *, atol: float = DUPLICATE_ATOL) -> Series:
    if len(times) != len(values) or not times:
        raise EvidenceError("time/value series is empty or length-mismatched")
    ordered = sorted(zip((float(t) for t in times), values), key=lambda item: item[0])
    out_t: list[float] = []
    out_v: list[np.ndarray] = []
    dropped = 0
    for timestamp, value in ordered:
        if not math.isfinite(timestamp):
            raise EvidenceError("non-finite timestamp")
        array = as_float_array(value)
        if out_t and timestamp == out_t[-1]:
            if out_v[-1].shape != array.shape or not np.allclose(out_v[-1], array, rtol=0.0, atol=atol):
                raise EvidenceError(f"materially conflicting values at duplicate timestamp {timestamp}")
            dropped += 1
            continue
        out_t.append(timestamp)
        out_v.append(array)
    return Series(np.asarray(out_t, dtype=np.float64), np.stack(out_v), dropped)


def _value_at(series: Series, timestamp: float, *, max_gap_s: float) -> tuple[np.ndarray, bool]:
    idx = int(np.searchsorted(series.t, timestamp, side="left"))
    if idx < series.t.size and series.t[idx] == timestamp:
        return series.value[idx].copy(), False
    if idx == 0 or idx == series.t.size:
        raise EvidenceError(f"boundary {timestamp} is outside raw support")
    left_t, right_t = series.t[idx - 1], series.t[idx]
    if right_t - left_t > max_gap_s:
        raise EvidenceError(f"boundary {timestamp} is bracketed by gap {right_t-left_t:.9f}s > {max_gap_s}s")
    alpha = (timestamp - left_t) / (right_t - left_t)
    return series.value[idx - 1] + alpha * (series.value[idx] - series.value[idx - 1]), True


def clip_series(series: Series, start: float, end: float, *, max_gap_s: float = MAX_GAP_S) -> tuple[Series, dict[str, Any]]:
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        raise EvidenceError("invalid scored interval")
    start_v, start_interp = _value_at(series, start, max_gap_s=max_gap_s)
    end_v, end_interp = _value_at(series, end, max_gap_s=max_gap_s)
    mask = (series.t > start) & (series.t < end)
    times = np.concatenate(([start], series.t[mask], [end]))
    values = np.concatenate((start_v[None, ...], series.value[mask], end_v[None, ...]), axis=0)
    gaps = np.diff(times)
    maximum_gap = float(np.max(gaps)) if gaps.size else 0.0
    if maximum_gap > max_gap_s:
        raise EvidenceError(f"required interval has maximum gap {maximum_gap:.9f}s > {max_gap_s}s")
    clipped = Series(times, values, series.dropped_duplicate_count)
    diagnostics = clipped.diagnostics(start, end)
    diagnostics.update({
        "start_interpolated": start_interp,
        "end_interpolated": end_interp,
        "coverage_fraction": 1.0,
        "completeness_status": "COMPLETE",
        "maximum_allowed_gap_s": max_gap_s,
    })
    return clipped, diagnostics


def interpolate_series(series: Series, grid: np.ndarray, *, max_gap_s: float = MAX_GAP_S) -> np.ndarray:
    rows = [_value_at(series, float(t), max_gap_s=max_gap_s)[0] for t in grid]
    return np.stack(rows)


def synchronized_grid(series_by_id: Mapping[int, Series], start: float, end: float,
                      *, max_gap_s: float = MAX_GAP_S) -> tuple[np.ndarray, dict[int, np.ndarray], dict[str, Any]]:
    clipped: dict[int, Series] = {}
    coverage: dict[str, Any] = {}
    for uav_id, series in sorted(series_by_id.items()):
        clipped[uav_id], coverage[str(uav_id)] = clip_series(series, start, end, max_gap_s=max_gap_s)
    grid = np.unique(np.concatenate([item.t for item in clipped.values()]))
    values = {uav_id: interpolate_series(series, grid, max_gap_s=max_gap_s)
              for uav_id, series in clipped.items()}
    return grid, values, coverage


def vector_norm(values: np.ndarray) -> np.ndarray:
    array = as_float_array(values)
    if array.ndim == 1:
        return np.abs(array)
    return np.linalg.norm(array, axis=1)


def trapezoidal_integral(times: Sequence[float], values: Sequence[float]) -> float:
    t = as_float_array(times)
    v = as_float_array(values)
    if t.ndim != 1 or v.ndim != 1 or t.size != v.size or t.size < 2 or np.any(np.diff(t) <= 0):
        raise EvidenceError("trapezoidal integration requires aligned strictly increasing samples")
    return float(np.trapz(v, t))


def time_weighted_rms(times: Sequence[float], magnitude: Sequence[float]) -> float:
    t = as_float_array(times)
    m = as_float_array(magnitude)
    duration = float(t[-1] - t[0])
    if duration <= 0:
        raise EvidenceError("RMS interval has non-positive duration")
    return math.sqrt(max(0.0, trapezoidal_integral(t, np.square(m)) / duration))


def threshold_intervals(times: Sequence[float], values: Sequence[float], threshold: float) -> list[tuple[float, float]]:
    """Maximal intervals where the linearly interpolated scalar is strictly below threshold."""
    t = as_float_array(times)
    v = as_float_array(values)
    if t.ndim != 1 or v.ndim != 1 or t.size != v.size or t.size < 2 or np.any(np.diff(t) <= 0):
        raise EvidenceError("threshold segmentation requires aligned increasing samples")
    intervals: list[tuple[float, float]] = []
    open_start: float | None = float(t[0]) if v[0] < threshold else None
    for k in range(t.size - 1):
        ta, tb = float(t[k]), float(t[k + 1])
        va, vb = float(v[k]), float(v[k + 1])
        inside_a, inside_b = va < threshold, vb < threshold
        if inside_a == inside_b:
            continue
        if vb == va:
            crossing = ta
        else:
            crossing = ta + (threshold - va) * (tb - ta) / (vb - va)
        crossing = min(tb, max(ta, crossing))
        if not inside_a and inside_b:
            open_start = crossing
        elif inside_a and not inside_b:
            if open_start is None:
                open_start = ta
            intervals.append((open_start, crossing))
            open_start = None
    if v[-1] < threshold:
        if open_start is None:
            open_start = float(t[-1])
        intervals.append((open_start, float(t[-1])))
    return [(a, b) for a, b in intervals if b > a]


def union_duration(intervals: Iterable[tuple[float, float]]) -> float:
    ordered = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not ordered:
        return 0.0
    total = 0.0
    left, right = ordered[0]
    for a, b in ordered[1:]:
        if a <= right:
            right = max(right, b)
        else:
            total += right - left
            left, right = a, b
    return total + right - left


def below_threshold_metrics(times: Sequence[float], distance_by_pair: Mapping[str, Sequence[float]],
                            threshold: float) -> dict[str, Any]:
    all_intervals: list[tuple[float, float]] = []
    pair_diagnostics: dict[str, Any] = {}
    count = 0
    exposure = 0.0
    for pair, distances in sorted(distance_by_pair.items()):
        values = as_float_array(distances)
        intervals = threshold_intervals(times, values, threshold)
        durations = [b - a for a, b in intervals]
        count += len(intervals)
        exposure += sum(durations)
        all_intervals.extend(intervals)
        pair_diagnostics[pair] = {
            "event_count": len(intervals),
            "exposure_duration_s": float(sum(durations)),
            "events": [{"start": a, "end": b, "duration_s": b - a} for a, b in intervals],
            "minimum_distance_m": float(np.min(values)),
        }
    return {
        "hard_risk_event_count": count,
        "hard_risk_exposure_duration": float(exposure),
        "hard_risk_exposure_unit": "pair-seconds",
        "any_pair_hard_risk_duration": union_duration(all_intervals),
        "pair_diagnostics": pair_diagnostics,
    }


def zero_order_hold_duration(times: Sequence[float], active: Sequence[bool], start: float, end: float,
                             *, max_gap_s: float = MAX_GAP_S) -> tuple[float, dict[str, Any]]:
    if len(times) != len(active) or not times:
        raise EvidenceError("empty discrete state signal")
    ordered = sorted((float(t), bool(v)) for t, v in zip(times, active))
    dedup: list[tuple[float, bool]] = []
    dropped = 0
    for item in ordered:
        if dedup and item[0] == dedup[-1][0]:
            if item[1] != dedup[-1][1]:
                raise EvidenceError(f"conflicting Boolean state at duplicate timestamp {item[0]}")
            dropped += 1
        else:
            dedup.append(item)
    raw_t = np.asarray([x[0] for x in dedup])
    if raw_t[0] > start or raw_t[-1] < end:
        raise EvidenceError("discrete state does not cover required interval")
    index = int(np.searchsorted(raw_t, start, side="right") - 1)
    if start - raw_t[index] > max_gap_s:
        raise EvidenceError("discrete state at interval start is stale")
    points = [(start, dedup[index][1])]
    points.extend((t, value) for t, value in dedup[index + 1:] if start < t < end)
    points.append((end, points[-1][1]))
    gaps = np.diff([x[0] for x in points])
    if gaps.size and float(np.max(gaps)) > max_gap_s:
        raise EvidenceError("discrete state interval contains an excessive gap")
    duration = sum((points[k + 1][0] - points[k][0]) for k in range(len(points) - 1) if points[k][1])
    return float(duration), {
        "first_timestamp": float(raw_t[0]), "last_timestamp": float(raw_t[-1]),
        "sample_count": len(dedup), "dropped_duplicate_sample_count": dropped,
        "maximum_sample_gap_s": float(np.max(gaps)) if gaps.size else None,
        "expected_start": start, "expected_end": end, "coverage_fraction": 1.0,
        "completeness_status": "COMPLETE", "state_interpolation": "zero_order_hold",
    }


def first_rising_crossing(times: Sequence[float], values: Sequence[float], threshold: float,
                          *, not_before: float | None = None) -> float | None:
    t = as_float_array(times); v = as_float_array(values)
    if not_before is not None:
        if not_before < t[0] or not_before > t[-1]:
            return None
        start_index = int(np.searchsorted(t, not_before, side="right"))
        initial = float(np.interp(not_before, t, v))
        t = np.concatenate(([not_before], t[start_index:]))
        v = np.concatenate(([initial], v[start_index:]))
    if v[0] >= threshold:
        return float(t[0])
    for k in range(1, t.size):
        if v[k] >= threshold and v[k - 1] < threshold:
            if v[k] == v[k - 1]:
                return float(t[k])
            return float(t[k - 1] + (threshold - v[k - 1]) * (t[k] - t[k - 1]) / (v[k] - v[k - 1]))
    return None


def acceleration_rise_time(times: Sequence[float], magnitudes: Sequence[float]) -> dict[str, Any]:
    t = as_float_array(times); u = as_float_array(magnitudes)
    peak = float(np.max(u))
    if peak <= 0.0:
        return {"valid": False, "value_s": None, "reason": "nonpositive_global_peak", "peak": peak}
    t10 = first_rising_crossing(t, u, 0.1 * peak)
    t90 = first_rising_crossing(t, u, 0.9 * peak, not_before=t10) if t10 is not None else None
    if t10 is None or t90 is None or t90 < t10:
        return {"valid": False, "value_s": None, "reason": "no_valid_90_percent_crossing", "peak": peak,
                "t10": t10, "t90": t90}
    return {"valid": True, "value_s": float(t90 - t10), "reason": None,
            "peak": peak, "t10": t10, "t90": t90}


def pooled_equal_uav_rms(values: Sequence[float]) -> float:
    array = as_float_array(values)
    if array.size == 0:
        raise EvidenceError("cannot aggregate empty UAV metric")
    return math.sqrt(float(np.mean(np.square(array))))


def metric_na(reason: str, **diagnostics: Any) -> dict[str, Any]:
    return {"valid": False, "value": None, "reason": reason, **diagnostics}


def metric_value(value: Any, **diagnostics: Any) -> dict[str, Any]:
    return {"valid": True, "value": value, "reason": None, **diagnostics}


def complete_interval_metric(value: float, required_start: float, required_end: float,
                             observed_start: float | None, observed_end: float | None,
                             *, partial_value: float | None = None,
                             partial_reason: str = "incomplete required evidence interval") -> dict[str, Any]:
    expected = required_end - required_start
    complete = (observed_start is not None and observed_end is not None
                and observed_start <= required_start and observed_end >= required_end)
    if complete:
        return metric_value(value, required_start=required_start, required_end=required_end,
                            coverage_fraction=1.0)
    covered = 0.0 if observed_start is None or observed_end is None else max(
        0.0, min(required_end, observed_end) - max(required_start, observed_start))
    return metric_na(partial_reason, partial_observed_value=partial_value,
                     partial_coverage_s=covered, partial_expected_s=expected,
                     partial_coverage_fraction=covered / expected if expected > 0 else 0.0,
                     partial_reason=partial_reason)
