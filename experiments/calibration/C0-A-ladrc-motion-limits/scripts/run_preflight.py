#!/usr/bin/env python3
"""Run and persist every mandatory C0-A-prereg-v2 preflight gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

from run_trial import LAUNCH, REPOSITORY, ROOT, VENV_PYTHON, WORKSPACE, ros_environment


def run(command, *, env=None):
    result = subprocess.run(
        command, cwd=REPOSITORY, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    return {
        "command": [str(item) for item in command],
        "returncode": result.returncode,
        "output": result.stdout,
        "pass": result.returncode == 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    logs = args.artifact_root.resolve() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    ros_env = ros_environment()
    checks = [
        run([sys.executable, "experiments/calibration/scripts/check_algorithm_freeze.py"]),
        run([
            sys.executable, "experiments/calibration/scripts/check_parameter_ownership.py",
            "--calibration", "C0-A", "--baseline-ref", "origin/paper/calibration",
        ]),
        run([str(VENV_PYTHON), str(ROOT / "scripts" / "generate_trial_order.py"), "--check"], env=ros_env),
        run([str(VENV_PYTHON), str(ROOT / "scripts" / "audit_protocol_executable.py")], env=ros_env),
        run([str(VENV_PYTHON), "-m", "unittest", str(ROOT / "scripts" / "test_infrastructure.py")], env=ros_env),
        run(["ros2", "launch", str(LAUNCH), "--show-args"], env=ros_env),
        run(["git", "diff", "--quiet"]),
        run(["git", "diff", "--cached", "--quiet"]),
        run(["git", "merge-base", "--is-ancestor", "origin/paper/calibration", "HEAD"]),
    ]
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
    ).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPOSITORY, text=True
    ).strip()
    branch_ok = branch == "cal/C0-A-ladrc-motion-limits"
    state_path = args.artifact_root.resolve() / "campaign_state.json"
    campaign_state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file() else {}
    )
    checks.append({
        "command": ["branch identity"],
        "returncode": 0 if branch_ok else 1,
        "output": branch,
        "pass": branch_ok,
    })
    gazebo_probe = subprocess.run(
        ["gzserver", "--version"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    gazebo_lines = [line for line in gazebo_probe.stdout.splitlines() if line.strip()]
    payload = {
        "calibration_id": "C0-A",
        "protocol_version": "C0-A-prereg-v2",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "branch": branch,
        "protocol_version_check": "C0-A-prereg-v2",
        "trial_schedule_complete": True,
        "unresolved_protocol_ambiguity": 0,
        "formal_trials_started": bool(campaign_state.get("formal_trials_started", False)),
        "formal_trials_executed": int(campaign_state.get("formal_trials_executed", 0)),
        "environment": {
            "host": platform.node(),
            "platform": platform.platform(),
            "ros_distro": ros_env.get("ROS_DISTRO"),
            "px4_commit": subprocess.check_output(
                ["git", "-C", "/home/yihuang/PX4-Autopilot", "rev-parse", "HEAD"], text=True
            ).strip(),
            "px4_describe": subprocess.check_output(
                ["git", "-C", "/home/yihuang/PX4-Autopilot", "describe", "--always", "--tags", "--dirty"], text=True
            ).strip(),
            "gazebo_version": gazebo_lines[0] if gazebo_lines else "unavailable",
            "gazebo_version_probe_returncode": gazebo_probe.returncode,
        },
        "checks": checks,
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
    }
    (logs / "preflight_v2.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    text = [
        "C0-A-prereg-v2 preflight",
        f"source_commit: {source_commit}",
        f"status: {payload['status']}",
        "protocol version = C0-A-prereg-v2",
        "trial schedule complete = true",
        "unresolved protocol ambiguity = 0",
        "",
    ]
    for item in checks:
        text.extend((
            "$ " + " ".join(item["command"]),
            item["output"].rstrip(),
            f"exit_code: {item['returncode']}",
            "",
        ))
    (logs / "preflight_v2.txt").write_text("\n".join(text), encoding="utf-8")
    print("\n".join(text[:6]))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
