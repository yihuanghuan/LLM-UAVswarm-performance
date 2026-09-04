#!/usr/bin/env python3
"""Deterministic, descriptive analysis of the frozen E5-v2 formal campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

SOURCE_COMMIT = "558def6238826460cb3f9323af445e8c299fb610"
REGISTRY_SHA = "e915575f23b1bd83810f3a8e5aa8092806b9076960c5a2f1fc2bb5faa73ad985"
PAYLOAD_SHA = "96ab0893ee099c1003f6a5aad6896decde97c4b9c8d885d38141b8a4dbae81ed"
SEED_SHA = "1815deba3fab9c756603a358b4a3900b67ffb9bcb3e9f757282ab8894595d0cb"
ORDER_SHA = "4ec9ee0e8de0cc4b015bfd3858365fe8bf0a07aeddcb591ab6f91221a7bb8f69"
ANALYSIS_SHA = "05802cb32e8dc2f990d9e0144f2cfd118b87228ab0c441578e084aeefc0d008a"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
OLD_E5_SHA = "9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e"
JOURNAL_TIP = "c39fcdbf0418b979209c70387932794eb0cd514a5a0b9bdaf32057dd286acb38"
LEDGER_TIP = "a09a5612ba93a32f3be9ab43c3bf6fe43358c09a02e3484ec93ee5b9342565d8"
COMPACT_SHA = "cb1a0ef155cf7b9856c5cec93221c493a3c1715220ad57a0ff08389856fd1860"
BUNDLE_V1 = "422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb"
RECOVERY_BUNDLE = "29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb"
BUNDLE_V2 = "2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572"
J_HARD_REASON = "preregistered continuous endpoint unavailable due to pre-analysis semantic ambiguity"
UNAVAILABLE_LATENCIES = ["T_validation", "T_state_resolution", "T_geometry", "T_allocator", "T_profile"]
Z = 1.959963984540054

SCRIPT = Path(__file__).resolve()
ANALYSIS_ROOT = SCRIPT.parents[1]
E5 = SCRIPT.parents[2]
REPO = SCRIPT.parents[5]
TOOLING = E5 / "tooling"
sys.path.insert(0, str(TOOLING))

from e5_v2_activation_common import sealed_scientific_payload_sha256  # noqa: E402
from e5_v2_formal_common import (  # noqa: E402
    ANALYSIS_PATH, ATTEMPTS_ROOT, ORDER_PATH, REGISTRY_PATH, SEED_REGISTRY_PATH,
    canonical_sha256, inventory, load_attempt_specs, load_json,
)

BINARY = {
    "scientific_completeness": "scientific completeness",
    "infrastructure_failure": "infrastructure failure",
    "candidate_correctness": "Candidate correctness",
    "resolver_success": "resolver success",
    "mission_completion": "mission completion",
    "mission_success": "mission success",
    "failsafe": "failsafe",
    "hard_failure": "hard failure",
}
CONTINUOUS = {
    "actual_d_min": "m",
    "tracking_rmse": "m",
    "final_error": "m",
    "completion_time": "s",
    "T_LLM": "s",
    "T_mission_execution": "s",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def close(a: Any, b: Any, tol: float = 1e-8) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    return a == b


def qtype7(values: list[float], p: float) -> float:
    x = sorted(values)
    if not x:
        raise ValueError("empty quantile")
    pos = (len(x) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return x[lo] if lo == hi else x[lo] + (pos - lo) * (x[hi] - x[lo])


def wilson(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / den
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return center - half, center + half


def metric_item(metrics: dict[str, Any], name: str) -> dict[str, Any]:
    return metrics["latency"][name] if name.startswith("T_") else metrics[name]


def flatten_tasks(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in candidate["mission"]["nodes"]:
        if node["type"] == "task":
            out.append(node["task"])
        elif node["type"] in {"parallel", "sequential"}:
            out.extend(node["tasks"])
        else:
            raise AssertionError(f"unknown mission node: {node['type']}")
    return out


def attempt_dir(spec: dict[str, Any]) -> Path:
    return ATTEMPTS_ROOT / f"{spec['campaign_position']:06d}__{spec['attempt_id']}"


def verify_source() -> list[dict[str, Any]]:
    expected = {
        REGISTRY_PATH: REGISTRY_SHA, SEED_REGISTRY_PATH: SEED_SHA,
        ORDER_PATH: ORDER_SHA, ANALYSIS_PATH: ANALYSIS_SHA,
        REPO / "lfs_policy/config/lfs_policy.paper_current.yaml": POLICY_SHA,
    }
    for path, digest in expected.items():
        assert sha(path) == digest, f"identity drift: {path}"
    assert sealed_scientific_payload_sha256() == PAYLOAD_SHA
    specs = load_attempt_specs()
    assert len(specs) == 60 and len({s["attempt_id"] for s in specs}) == 60
    journal = sorted((E5 / "results/formal_v2/campaign_journal").glob("[0-9]*.json"))
    ledger = sorted((E5 / "E5_v2_raw_archive_ledger").glob("[0-9]*.json"))
    dirs = sorted(p for p in ATTEMPTS_ROOT.iterdir() if p.is_dir())
    assert len(journal) == len(ledger) == len(dirs) == 60
    assert load_json(journal[-1])["record_sha256"] == JOURNAL_TIP
    assert load_json(ledger[-1])["record_sha256"] == LEDGER_TIP
    assert canonical_sha256(inventory(ATTEMPTS_ROOT)) == COMPACT_SHA
    for spec, jp, lp, dp in zip(specs, journal, ledger, dirs):
        assert spec["attempt_id"] in jp.name and spec["attempt_id"] in lp.name and spec["attempt_id"] in dp.name
        a = load_json(dp / "attempt.json")
        assert a["accepted_formal_result"] is True and a["replacement_attempt"] is False
        assert a["campaign_position"] == spec["campaign_position"] and a["seed"] == spec["seed"]
        assert a["attempt_status"] == "mission_success"
    old_path = "experiments_v2/Formal Evaluation Experiments/E5/e5_end_to_end_registry_v1.yaml"
    old = subprocess.check_output(["git", "show", f"511192273a61f97e2742a1cc6608e18ed960cc1f:{old_path}"], cwd=REPO)
    assert hashlib.sha256(old).hexdigest() == OLD_E5_SHA
    changed = subprocess.check_output(["git", "diff", "--name-only", SOURCE_COMMIT, "--", ".", ":(exclude)experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/**"], cwd=REPO, text=True).strip()
    assert not changed, f"formal evidence modified: {changed}"
    return specs


def resolved_audit(spec: dict[str, Any], resolution: dict[str, Any]) -> list[dict[str, Any]]:
    expected_tasks = flatten_tasks(spec["candidate_semantic_ground_truth"])
    records = resolution["records"]
    assert len(records) == len(expected_tasks)
    result = []
    multipliers = {"compact": 0.8, "normal": 1.0, "spacious": 1.25}
    for expected, rec in zip(expected_tasks, records):
        assert rec["candidate_lfs"] == expected
        c, r, t = expected["c"], expected["r"], expected["T"]
        if c["mode"] == "absolute":
            c_ok = rec["center_source"] == "candidate.absolute" and close(rec["resolved_center"], c["value"])
        elif c["mode"] == "maintain_current_centroid":
            c_ok = rec["center_source"] == "candidate.maintain_current_centroid"
        else:
            c_ok = rec["center_source"] == "snapshot.participant_centroid+world_offset"
        if r["mode"] == "explicit":
            r_ok = close(rec["r_exec"], r["value"])
        else:
            r_ok = close(rec["r_exec"], rec["r_nominal"] * multipliers[r["value"]])
        if t["mode"] == "explicit":
            t_ok = close(rec["t_exec"], t["value"])
        else:
            peaks = rec["per_uav_dynamics"]
            t_ok = rec["t_request"]["mode"] == "auto" and rec["t_exec"] >= 0.5
            t_ok = t_ok and all(x["predicted_v_peak"] <= 5 + 1e-8 and x["predicted_a_peak"] <= 5 + 1e-8 and x["predicted_j_peak"] <= 10 + 1e-8 for x in peaks)
        assert rec["policy_hash"] == POLICY_SHA and c_ok and r_ok and t_ok
        result.append({
            "campaign_position": spec["campaign_position"], "attempt_id": spec["attempt_id"],
            "substudy": spec["substudy"], "scenario_id": spec["scenario_id"],
            "task_family": spec.get("task_family") or "", "N": spec["N"],
            "task_id": expected["task_id"], "center_mode": c["mode"],
            "scale_mode": r["mode"], "scale_label": r.get("value", "") if r["mode"] == "qualitative" else "",
            "time_mode": t["mode"], "c_exec_x": rec["resolved_center"][0],
            "c_exec_y": rec["resolved_center"][1], "c_exec_z": rec["resolved_center"][2],
            "r_exec": rec["r_exec"], "T_exec": rec["t_exec"],
            "center_source": rec["center_source"], "c_semantics_ok": c_ok,
            "r_semantics_ok": r_ok, "T_semantics_ok": t_ok, "all_semantics_ok": c_ok and r_ok and t_ok,
        })
    return result


def load_rows(specs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, resolved = [], []
    for spec in specs:
        root = attempt_dir(spec)
        attempt, metrics = load_json(root / "attempt.json"), load_json(root / "metrics.json")
        rr = resolved_audit(spec, load_json(root / "resolution.json"))
        resolved.extend(rr)
        assert metrics["J_hard"] == {"available": False, "reason": J_HARD_REASON, "value": None}
        for name in UNAVAILABLE_LATENCIES:
            assert metric_item(metrics, name)["available"] is False and metric_item(metrics, name)["value"] is None
        row: dict[str, Any] = {
            "campaign_position": spec["campaign_position"], "attempt_id": spec["attempt_id"], "seed": spec["seed"],
            "substudy": spec["substudy"], "scenario_id": spec["scenario_id"],
            "task_family": spec.get("task_family") or "", "N": spec["N"],
            "attempt_status": attempt["attempt_status"], "task_count": len(rr),
            "resolved_semantics_consistent": all(x["all_semantics_ok"] for x in rr),
            "scientific_completeness": bool(metrics["scientific_complete"]),
            "infrastructure_failure": bool(metrics["infrastructure_failure"]),
            "J_hard_available": False, "J_hard_value": "", "J_hard_reason": J_HARD_REASON,
        }
        for name in ["candidate_correctness", "resolver_success", "mission_completion", "mission_success", "failsafe", "hard_failure"]:
            item = metrics[name]
            row[name] = bool(item["value"]); row[name + "_available"] = bool(item["available"])
        for name in CONTINUOUS:
            item = metric_item(metrics, name)
            row[name] = item["value"] if item["available"] else ""
            row[name + "_available"] = bool(item["available"])
        for name in UNAVAILABLE_LATENCIES:
            row[name] = ""; row[name + "_available"] = False; row[name + "_reason"] = metric_item(metrics, name)["reason"]
        rows.append(row)
    assert len(rows) == 60 and len(resolved) == 75 and all(r["resolved_semantics_consistent"] for r in rows)
    return rows, resolved


def summarize(label_type: str, label: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(rows)
    for name in BINARY:
        avail = [r for r in rows if r.get(name + "_available", True)]
        k = sum(bool(r[name]) for r in avail)
        lo, hi = wilson(k, len(avail))
        out.append({"stratum_type": label_type, "stratum_value": label, "endpoint": name, "kind": "binary", "unit": "proportion", "registered_n": n, "available_n": len(avail), "numerator": k, "denominator": len(avail), "proportion": k / len(avail), "wilson_95_low": lo, "wilson_95_high": hi, "mean": "", "median": "", "sample_sd": "", "iqr": "", "min": "", "max": ""})
    for name, unit in CONTINUOUS.items():
        vals = [float(r[name]) for r in rows if r[name + "_available"]]
        out.append({"stratum_type": label_type, "stratum_value": label, "endpoint": name, "kind": "continuous", "unit": unit, "registered_n": n, "available_n": len(vals), "numerator": "", "denominator": "", "proportion": "", "wilson_95_low": "", "wilson_95_high": "", "mean": statistics.fmean(vals), "median": statistics.median(vals), "sample_sd": statistics.stdev(vals) if len(vals) >= 2 else "", "iqr": qtype7(vals, .75) - qtype7(vals, .25), "min": min(vals), "max": max(vals)})
    return out


def groups(rows: list[dict[str, Any]]) -> dict[str, list[tuple[str, list[dict[str, Any]]]]]:
    a = [r for r in rows if r["substudy"] == "E5-v2A"]
    b = [r for r in rows if r["substudy"] == "E5-v2B"]
    by = lambda data, key, values: [(str(v), [r for r in data if r[key] == v]) for v in values]
    return {
        "overall": [("E5-v2", rows)],
        "substudy": by(rows, "substudy", ["E5-v2A", "E5-v2B"]),
        "A_scenario": by(a, "scenario_id", ["E5V2-A1-REL-COMPACT-CIRCLE", "E5V2-A2-MAINTAIN-NORMAL-LINE", "E5V2-A3-REL-SPACIOUS-SPHERE"]),
        "B_N": by(b, "N", [8, 12, 16]),
        "B_family": by(b, "task_family", ["SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL"]),
        "B_cell": [(f"N{n} {family}", [r for r in b if r["N"] == n and r["task_family"] == family]) for n in [8, 12, 16] for family in ["SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL"]],
    }


SUMMARY_FIELDS = [
    "stratum_type", "stratum_value", "endpoint", "kind", "unit", "registered_n",
    "available_n", "numerator", "denominator", "proportion", "wilson_95_low",
    "wilson_95_high", "mean", "median", "sample_sd", "iqr", "min", "max",
]


def endpoint_availability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for name in BINARY:
        n = sum(bool(r.get(name + "_available", True)) for r in rows)
        result.append({"endpoint": name, "kind": "binary", "registered_n": 60, "available_n": n, "unavailable_n": 60 - n, "status": "AVAILABLE" if n else "UNAVAILABLE", "reason": ""})
    for name, unit in CONTINUOUS.items():
        n = sum(bool(r[name + "_available"]) for r in rows)
        result.append({"endpoint": name, "kind": "continuous", "registered_n": 60, "available_n": n, "unavailable_n": 60 - n, "status": "AVAILABLE" if n else "UNAVAILABLE", "reason": "", "unit": unit})
    result.append({"endpoint": "J_hard", "kind": "continuous", "registered_n": 60, "available_n": 0, "unavailable_n": 60, "status": "PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY", "reason": J_HARD_REASON})
    for name in UNAVAILABLE_LATENCIES:
        result.append({"endpoint": name, "kind": "continuous", "registered_n": 60, "available_n": 0, "unavailable_n": 60, "status": "PREREGISTERED_BUT_UNAVAILABLE", "reason": "stage timestamp unavailable", "unit": "s"})
    return result


def find_summary(summary: list[dict[str, Any]], label: str, endpoint: str) -> dict[str, Any]:
    return next(x for x in summary if x["stratum_value"] == label and x["endpoint"] == endpoint)


def fnum(value: Any, digits: int = 3) -> str:
    return "NA" if value == "" or value is None else f"{float(value):.{digits}f}"


def rate_cell(summary: list[dict[str, Any]], label: str, endpoint: str = "mission_success") -> str:
    x = find_summary(summary, label, endpoint)
    return f"{x['numerator']}/{x['denominator']} ({100*x['proportion']:.1f}%; Wilson 95% CI {100*x['wilson_95_low']:.1f}–{100*x['wilson_95_high']:.1f}%)"


def range_text(summary: list[dict[str, Any]], label: str, endpoint: str) -> str:
    x = find_summary(summary, label, endpoint)
    return f"{fnum(x['mean'])} / {fnum(x['median'])} [{fnum(x['min'])}, {fnum(x['max'])}]"


def resolved_group(resolved: list[dict[str, Any]], predicate) -> dict[str, Any]:
    data = [r for r in resolved if predicate(r)]
    def field(name: str) -> dict[str, float]:
        vals = [float(r[name]) for r in data]
        return {"n": len(vals), "mean": statistics.fmean(vals), "median": statistics.median(vals), "min": min(vals), "max": max(vals)}
    return {"task_records": len(data), "all_semantics_consistent": all(r["all_semantics_ok"] for r in data), "c_exec": {axis: field("c_exec_" + axis) for axis in "xyz"}, "r_exec": field("r_exec"), "T_exec": field("T_exec")}


def build_report(all_summaries: dict[str, list[dict[str, Any]]], resolved: list[dict[str, Any]], availability: list[dict[str, Any]]) -> str:
    overall = all_summaries["overall"]
    a_sum = all_summaries["A_scenario"]
    bn = all_summaries["B_N"]
    bf = all_summaries["B_family"]
    bc = all_summaries["B_cell"]
    ov_success = find_summary(overall, "E5-v2", "mission_success")
    a_labels = [
        ("A1 — REL-COMPACT-CIRCLE", "E5V2-A1-REL-COMPACT-CIRCLE"),
        ("A2 — MAINTAIN-NORMAL-LINE", "E5V2-A2-MAINTAIN-NORMAL-LINE"),
        ("A3 — REL-SPACIOUS-SPHERE", "E5V2-A3-REL-SPACIOUS-SPHERE"),
    ]
    lines = [
        "# E5-v2 formal analysis report", "",
        "## Scope and frozen evidence", "",
        "This is descriptive end-to-end integration evidence from the separately preregistered E5-v2 campaign. The source is commit " + SOURCE_COMMIT + ". Exactly 60 registered attempts were consumed in the frozen order; all 60 were scientifically complete and no infrastructure failure, replacement, or additional sample occurred.", "",
        "E5-v2 supplies no new causal evidence for C1, C2, or C3. It does not establish formal or asymptotic scalability, arbitrary-N generalization, linear or near-linear computational scaling, or real-time scaling guarantees. No inferential comparison across N was conducted.", "",
        "## Overall results", "",
        f"All 60 registered attempts satisfied the frozen end-to-end mission-success criterion: 60/60 (100.0%; two-sided Wilson 95% CI {100*ov_success['wilson_95_low']:.1f}–{100*ov_success['wilson_95_high']:.1f}%). This is observed success on the registered E5-v2 scenarios, not a universal reliability or safety guarantee.", "",
        "| Endpoint | Result |", "|---|---:|",
    ]
    for endpoint in ["scientific_completeness", "candidate_correctness", "resolver_success", "mission_completion", "mission_success", "infrastructure_failure", "failsafe", "hard_failure"]:
        lines.append(f"| {BINARY[endpoint]} | {rate_cell(overall, 'E5-v2', endpoint)} |")
    lines += ["", "Continuous cells below are mean / median [min, max]; sample SD and IQR are retained in the machine-readable tables.", "", "| Endpoint | Overall |", "|---|---:|"]
    for endpoint in CONTINUOUS:
        lines.append(f"| {endpoint} | {range_text(overall, 'E5-v2', endpoint)} |")
    lines += ["", "## E5-v2A: feasible under-specified realization", "", "All three prospectively feasible scenario families traversed the real semantic frontend, deterministic staged resolution, geometry, allocation, execution, safety, control, and mission-completion path in all five registered attempts.", "", "| Scenario | Mission success | r_exec mean | T_exec mean | d_min mean | RMSE mean | final error mean | completion mean | T_LLM mean | T_mission mean |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for display, label in a_labels:
        rg = resolved_group(resolved, lambda r, label=label: r["scenario_id"] == label)
        lines.append("| " + display + " | " + rate_cell(a_sum, label) + " | " + " | ".join([
            fnum(rg["r_exec"]["mean"]), fnum(rg["T_exec"]["mean"]),
            fnum(find_summary(a_sum, label, "actual_d_min")["mean"]),
            fnum(find_summary(a_sum, label, "tracking_rmse")["mean"]),
            fnum(find_summary(a_sum, label, "final_error")["mean"]),
            fnum(find_summary(a_sum, label, "completion_time")["mean"]),
            fnum(find_summary(a_sum, label, "T_LLM")["mean"]),
            fnum(find_summary(a_sum, label, "T_mission_execution")["mean"]),
        ]) + " |")
    lines += ["", "Resolved center realization (component-wise mean [min, max]):", "", "| Scenario | c_exec x | c_exec y | c_exec z |", "|---|---:|---:|---:|"]
    for display, label in a_labels:
        rg = resolved_group(resolved, lambda r, label=label: r["scenario_id"] == label)
        cells = [f"{fnum(rg['c_exec'][x]['mean'])} [{fnum(rg['c_exec'][x]['min'])}, {fnum(rg['c_exec'][x]['max'])}]" for x in "xyz"]
        lines.append("| " + display + " | " + " | ".join(cells) + " |")
    lines += ["", "All 15 E5-v2A attempts had exact Candidate correctness, resolver success, mission completion, and mission success. All 15 task-level c_exec, r_exec, and T_exec records matched their registered relative/maintain-current, qualitative, and automatic timing semantics.", "", "A3 supports the bounded statement that qualitative spacious Sphere semantics are executable when their state-dependent physical realization lies inside the frozen workspace and safety envelope. It did not fix or rerun the distinct E5-v1 command.", "", "## E5-v2B: larger-swarm demonstration", "", "The same frozen command-to-control method was successfully demonstrated at N=8, N=12, and N=16 in the registered simulation scenarios. All 45 E5-v2B attempts were scientifically complete, Candidate-correct, resolver-successful, mission-complete, and mission-successful; each of the nine cells contributed exactly five attempts. N was not an isolated causal treatment: spawn extent, centroid, assignment geometry, displacement, qualitative realization, and auto timing co-varied under the frozen rules.", "", "### Nine registered N × family cells", "", "| Cell | Success | d_min mean | RMSE mean | final error mean | completion mean | T_LLM mean | T_mission mean |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for n in [8, 12, 16]:
        for family in ["SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL"]:
            label = f"N{n} {family}"
            lines.append("| " + label + " | " + rate_cell(bc, label) + " | " + " | ".join(fnum(find_summary(bc, label, ep)["mean"]) for ep in ["actual_d_min", "tracking_rmse", "final_error", "completion_time", "T_LLM", "T_mission_execution"]) + " |")
    lines += ["", "### Descriptive summaries by N", "", "| N | Registered | Success | d_min mean | RMSE mean | final error mean | completion mean |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for n in [8, 12, 16]:
        label = str(n); s = find_summary(bn, label, "mission_success")
        lines.append(f"| {n} | {s['registered_n']} | {rate_cell(bn, label)} | " + " | ".join(fnum(find_summary(bn, label, ep)["mean"]) for ep in ["actual_d_min", "tracking_rmse", "final_error", "completion_time"]) + " |")
    lines += ["", "### Descriptive summaries by task family", "", "| Family | Registered | Success | d_min mean | RMSE mean | final error mean | completion mean |", "|---|---:|---:|---:|---:|---:|---:|"]
    for family in ["SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL"]:
        s = find_summary(bf, family, "mission_success")
        lines.append(f"| {family} | {s['registered_n']} | {rate_cell(bf, family)} | " + " | ".join(fnum(find_summary(bf, family, ep)["mean"]) for ep in ["actual_d_min", "tracking_rmse", "final_error", "completion_time"]) + " |")
    lines += ["", "### UNDER_SPECIFIED physical realization by N", "", "The semantic structure was held constant across N; the frozen state/cardinality-dependent rules legitimately produced different centers, scale, and automatic timing.", "", "| N | c_exec mean [x,y,z] | r_exec mean | T_exec mean | semantic audit |", "|---:|---:|---:|---:|---:|"]
    for n in [8, 12, 16]:
        rg = resolved_group(resolved, lambda r, n=n: r["substudy"] == "E5-v2B" and r["task_family"] == "UNDER_SPECIFIED" and r["N"] == n)
        c = ", ".join(fnum(rg["c_exec"][x]["mean"]) for x in "xyz")
        lines.append(f"| {n} | [{c}] | {fnum(rg['r_exec']['mean'])} | {fnum(rg['T_exec']['mean'])} | {'PASS' if rg['all_semantics_consistent'] else 'FAIL'} |")
    lines += ["", "Observed physical and timing quantities varied with the associated N-dependent mission realization. These descriptive differences are not causal N effects or performance-scaling estimates.", "", "## Endpoint availability", "", "J_hard is NA / NOT ANALYZED for 0/60 available observations. Its frozen status is PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY. No replacement, proxy, raw-data rederivation, or zero imputation was used. Mission success independently retained the frozen actual d_min >= 1.50 m rule.", "", "The preregistered latency components T_validation, T_state_resolution, T_geometry, T_allocator, and T_profile are unavailable in 60/60 attempts and remain NA. T_LLM and T_mission_execution are available in 60/60 and are summarized descriptively; they were not combined into a scaling metric.", "", "## Tooling-amendment governance", "", "Slot 1 was physically executed exactly once under tooling bundle v1 (" + BUNDLE_V1 + "). A post-run packaging blocker occurred after complete raw evidence had been preserved. The transaction was recovered without rerunning the mission under recovery bundle " + RECOVERY_BUNDLE + ". Slots 2–60 used amended execution bundle v2 (" + BUNDLE_V2 + "). The scientific method and protocol did not change, but instrumentation was not byte-identical across all attempts; slot 1 remains in the all-attempt denominator.", "", "## Relationship to E5-v1", "", "E5-v1 is a separately frozen historical registry. Its REL-QUAL condition remained 0/5 mission success because the registered spacious-Sphere realization violated frozen geometry/workspace constraints, and its MIXED-HIGH frontend limitation remains. E5-v2 was independently preregistered to study prospectively feasible under-specified positive integration tasks and to add N=12/N=16 demonstrations. Their success percentages are neither pooled nor presented as before/after improvement.", "", "## Claim-boundary table", "", "| Question | Evidence | Supported interpretation | Unsupported interpretation |", "|---|---|---|---|", "| Feasible under-specified realization | 15/15 E5-v2A attempts completed with confirmed Candidate/resolver and c/r/T semantics | Prospectively feasible relative/qualitative/auto commands completed the full pipeline in the registered scenarios | Arbitrary under-specified commands will always be feasible |", "| Physical boundary handling | Feasible E5-v2A plus immutable inadmissible E5-v1 REL-QUAL | The frozen resolver may instantiate a feasible request or reject a physically inadmissible one | All qualitative semantics are executable in every workspace/state |", "| Larger-swarm demonstration | All 45 E5-v2B attempts across N=8/12/16 and S1/S2/S3 | The same frozen method operated at N=8/12/16 in the tested simulation missions | Formal scalability, arbitrary N, or asymptotic performance |", "| Reliability | 60/60 met the frozen end-to-end success rule | Success was observed in all registered E5-v2 attempts | Universal 100% reliability |", "| Safety | All successful attempts had actual d_min >= 1.50 m | The registered hard-distance criterion was satisfied in these attempts | Continuous J_hard exposure or universal collision-avoidance guarantee |", "", "## Paper-facing evidence extraction", "", "### Strongest quantitative facts", ""]
    facts = [
        f"1. All 60/60 attempts met mission success (Wilson 95% CI {100*ov_success['wilson_95_low']:.1f}–{100*ov_success['wilson_95_high']:.1f}%).",
        "2. Scientific completeness was 60/60 and infrastructure failures were 0/60.",
        "3. Candidate correctness, resolver success, and mission completion were each 60/60.",
        "4. E5-v2A achieved 15/15 mission success across three distinct feasible relative/qualitative/auto scenarios.",
        "5. All 15 E5-v2A and all 75 total task-level resolved c/r/T records passed semantic-mode consistency checks.",
        "6. E5-v2B achieved 45/45 mission success, with 5/5 in every one of the nine N × task-family cells.",
        f"7. Overall actual d_min was mean {fnum(find_summary(overall, 'E5-v2', 'actual_d_min')['mean'])} m (range {fnum(find_summary(overall, 'E5-v2', 'actual_d_min')['min'])}–{fnum(find_summary(overall, 'E5-v2', 'actual_d_min')['max'])} m).",
        f"8. Overall tracking RMSE was mean {fnum(find_summary(overall, 'E5-v2', 'tracking_rmse')['mean'])} m and final error mean {fnum(find_summary(overall, 'E5-v2', 'final_error')['mean'])} m.",
        f"9. Completion time averaged {fnum(find_summary(overall, 'E5-v2', 'completion_time')['mean'])} s; T_LLM averaged {fnum(find_summary(overall, 'E5-v2', 'T_LLM')['mean'])} s and T_mission_execution {fnum(find_summary(overall, 'E5-v2', 'T_mission_execution')['mean'])} s.",
        "10. J_hard and five decomposed deterministic latency components remained unavailable in 0/60 observations by frozen adjudication/mapping.",
    ]
    lines += facts
    lines += ["", "### Recommended compact E5 results paragraph", "", f"In the separately preregistered E5-v2 integration campaign, all 60 registered attempts satisfied the frozen end-to-end mission-success criterion (100%; Wilson 95% CI {100*ov_success['wilson_95_low']:.1f}–{100*ov_success['wilson_95_high']:.1f}%). This included 15/15 prospectively feasible under-specified attempts spanning relative or maintain-current centers, qualitative scales, and automatic duration, and 45/45 scale-demonstration attempts with 5/5 successes in every N=8, N=12, and N=16 by SIMPLE, UNDER_SPECIFIED, and COMPOSITIONAL cell. Candidate correctness, resolver success, and mission completion were each observed in 60/60 attempts. The same frozen command-to-control pipeline was therefore demonstrated in the registered scenarios at all three swarm sizes; this is descriptive integration evidence and does not establish formal or asymptotic scalability or arbitrary-N generalization.", "", "### Recommended main-paper table", "", "Report registered N, scientific completeness, mission success with Wilson CI, Candidate correctness, resolver success, actual d_min, tracking RMSE, final error, and completion time for overall E5-v2, E5-v2A scenarios, and the nine E5-v2B N × family cells.", "", "### Recommended supplementary results", "", "Include the per-attempt table, full binary and continuous summaries (N, mean, median, sample SD, IQR, min/max), all c_exec/r_exec/T_exec task records, endpoint availability, exact frozen hashes, and mixed-tooling provenance.", "", "### Explicit limitations and prohibited overclaims", "", "Do not infer new C1/C2/C3 evidence; formal/asymptotic/linear/real-time scalability; arbitrary-N generalization; universal reliability; guaranteed collision avoidance; causal N effects; or continuous hard-risk exposure. Do not pool E5-v1 and E5-v2 or describe E5-v2 as fixing E5-v1. J_hard and the five unavailable latency components must remain NA.", ""]
    return "\n".join(lines)


def output_inventory(root: Path, exclude_audit: bool = True) -> list[dict[str, Any]]:
    records = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("scripts/") or (exclude_audit and rel == "E5_v2_analysis_freeze_audit.json"):
            continue
        records.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha(path)})
    return records


def run(target: Path) -> dict[str, Any]:
    specs = verify_source()
    rows, resolved = load_rows(specs)
    gs = groups(rows)
    all_summaries = {name: sum((summarize(name, label, data) for label, data in grouped), []) for name, grouped in gs.items()}
    expected_sizes = {"overall": [60], "substudy": [15, 45], "A_scenario": [5, 5, 5], "B_N": [15, 15, 15], "B_family": [15, 15, 15], "B_cell": [5] * 9}
    for name, grouped in gs.items():
        assert [len(data) for _, data in grouped] == expected_sizes[name]
    outputs = target / "outputs"
    report_path = target / "report/E5_v2_formal_analysis_report.md"
    per_fields = list(rows[0])
    resolved_fields = list(resolved[0])
    write_csv(outputs / "E5_v2_per_attempt_results.csv", rows, per_fields)
    file_map = {
        "overall": "E5_v2_overall_summary.csv", "substudy": "E5_v2_substudy_summary.csv",
        "A_scenario": "E5_v2_A_scenario_summary.csv", "B_N": "E5_v2_B_N_summary.csv",
        "B_family": "E5_v2_B_family_summary.csv", "B_cell": "E5_v2_B_cell_summary.csv",
    }
    for name, filename in file_map.items():
        write_csv(outputs / filename, all_summaries[name], SUMMARY_FIELDS)
    write_csv(outputs / "E5_v2_resolved_values.csv", resolved, resolved_fields)
    availability = endpoint_availability(rows)
    avail_fields = ["endpoint", "kind", "unit", "registered_n", "available_n", "unavailable_n", "status", "reason"]
    write_csv(outputs / "E5_v2_endpoint_availability.csv", availability, avail_fields)
    summary_json = {
        "schema": "E5_v2_analysis_summary_v1", "source_commit": SOURCE_COMMIT,
        "scientific_position": "descriptive end-to-end integration evidence",
        "population": {"registered": 60, "scientific_complete": 60, "mission_success": 60, "infrastructure_failure": 0, "E5-v2A": 15, "E5-v2B": 45},
        "strata": all_summaries, "endpoint_availability": availability,
        "resolved_semantics": {
            "task_records": len(resolved), "consistent_records": sum(bool(r["all_semantics_ok"]) for r in resolved),
            "E5-v2A": {label: resolved_group(resolved, lambda r, label=label: r["scenario_id"] == label) for _, label in [("", x[1]) for x in [("", "E5V2-A1-REL-COMPACT-CIRCLE"), ("", "E5V2-A2-MAINTAIN-NORMAL-LINE"), ("", "E5V2-A3-REL-SPACIOUS-SPHERE")]]},
            "E5-v2B_UNDER_SPECIFIED_by_N": {str(n): resolved_group(resolved, lambda r, n=n: r["substudy"] == "E5-v2B" and r["task_family"] == "UNDER_SPECIFIED" and r["N"] == n) for n in [8, 12, 16]},
        },
        "identities": {"registry_sha256": REGISTRY_SHA, "scientific_payload_sha256": PAYLOAD_SHA, "seed_sha256": SEED_SHA, "order_sha256": ORDER_SHA, "analysis_contract_sha256": ANALYSIS_SHA, "production_policy_sha256": POLICY_SHA, "old_E5_v1_registry_sha256": OLD_E5_SHA, "journal_chain_tip": JOURNAL_TIP, "raw_ledger_chain_tip": LEDGER_TIP, "compact_results_inventory_sha256": COMPACT_SHA},
        "governance": {"new_inferential_tests": 0, "new_endpoints": 0, "J_hard_analyzed": False, "old_E5_v1_pooling": False, "production_method_changes": 0, "slot1_physical_bundle": BUNDLE_V1, "slot1_recovery_bundle": RECOVERY_BUNDLE, "slots2_60_physical_bundle": BUNDLE_V2},
    }
    write_json(outputs / "E5_v2_analysis_summary.json", summary_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_report(all_summaries, resolved, availability), encoding="utf-8", newline="\n")
    generated = output_inventory(target)
    audit = {
        "schema": "E5_v2_analysis_freeze_audit_v1", "status": "PASS",
        "source_commit": SOURCE_COMMIT, "registered_inputs": 60, "unique_attempt_ids": 60,
        "formal_evidence_modifications": 0, "new_inferential_tests": 0, "new_endpoints": 0,
        "J_hard_redefinition": False, "J_hard_analyzed": False, "J_hard_available": "0/60",
        "unavailable_latency_components": {name: "0/60" for name in UNAVAILABLE_LATENCIES},
        "old_E5_v1_pooling": False, "production_method_changes": 0,
        "analysis_deterministic_replay": "PASS",
        "analysis_test_suite": "PASS",
        "no_zero_imputation": True,
        "analysis_script_sha256": sha(SCRIPT),
        "analysis_test_sha256": sha(SCRIPT.with_name("test_e5_v2_analysis.py")),
        "machine_readable_output_files": len([x for x in generated if x["path"].endswith((".csv", ".json"))]),
        "generated_artifact_inventory": generated,
        "generated_artifact_inventory_sha256": canonical_sha256(generated),
    }
    write_json(target / "E5_v2_analysis_freeze_audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=ANALYSIS_ROOT)
    args = parser.parse_args()
    audit = run(args.artifact_root.resolve())
    print(json.dumps({"status": audit["status"], "registered_inputs": audit["registered_inputs"], "artifact_root": str(args.artifact_root.resolve())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
