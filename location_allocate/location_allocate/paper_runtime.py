"""Production Paper Candidate mission runtime, isolated from legacy code."""

import math
import time

import rclpy

from .candidate_mission_runtime import execute_candidate_payload
from .execution_command_builder import (
    build_parallel_command_batch,
    build_task_command_batch,
)
from .late_resolution import resolve_execution_parallel, resolve_execution_task
from .mission_executor import MissionRuntimeCallbacks
from .paper_lfs_validator import early_validate_candidate_mission
from .state_snapshot import SnapshotError
from .trace_logger import append_resolution_trace


class PaperMissionRuntime:
    """Own Paper late resolution, publication, completion, and failure trace."""

    def __init__(self, node, policy_config, candidate_policy, snapshot_manager,
                 publishers, completion_tracker, available_uav_ids):
        self.node = node
        self.policy_config = policy_config
        self.candidate_policy = candidate_policy
        self.snapshot_manager = snapshot_manager
        self.publishers = publishers
        self.completion_tracker = completion_tracker
        self.available_uav_ids = tuple(available_uav_ids)
        self._mission_counter = 0

    def _fresh_snapshot(self, uav_ids):
        deadline = (
            time.monotonic()
            + self.policy_config.state.fresh_state_wait_timeout
        )
        last_error = None
        now = self.node.get_clock().now().nanoseconds / 1e9
        try:
            return self.snapshot_manager.snapshot(uav_ids, now)
        except SnapshotError as exc:
            last_error = exc
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            rclpy.spin_once(self.node, timeout_sec=min(0.05, remaining))
            now = self.node.get_clock().now().nanoseconds / 1e9
            try:
                return self.snapshot_manager.snapshot(uav_ids, now)
            except SnapshotError as exc:
                last_error = exc
        raise RuntimeError(
            f"fresh state wait timed out: {last_error or 'no state'}"
        )

    def _publish_commands(self, commands):
        self.completion_tracker.arm(command.uav_id for command in commands)
        for command in commands:
            if int(command.uav_id) not in self.publishers:
                raise RuntimeError(
                    f"missing execution publisher for UAV{command.uav_id}"
                )
        for command in commands:
            self.publishers[int(command.uav_id)].publish(command)

    def _resolve_task(self, task, mission_id, group_id=0):
        snapshot = self._fresh_snapshot(task["U"])
        resolved = resolve_execution_task(
            task, snapshot, self.candidate_policy
        )
        commands = build_task_command_batch(
            resolved, mission_id, int(task["task_id"]), group_id,
            self.node.get_clock().now().to_msg(),
        )
        append_resolution_trace(resolved.trace)
        self._publish_commands(commands)
        return resolved

    def _resolve_parallel(self, tasks, mission_id, group_id, completion_mode):
        participant_ids = [uid for task in tasks for uid in task["U"]]
        snapshot = self._fresh_snapshot(participant_ids)
        group_d_plan = max(
            self.candidate_policy.resolve_safety(float(task["s"])).d_plan
            for task in tasks
        )
        resolved_group = resolve_execution_parallel(
            tasks, snapshot, self.candidate_policy, completion_mode,
            group_d_plan,
        )
        commands = build_parallel_command_batch(
            resolved_group, mission_id, group_id,
            self.node.get_clock().now().to_msg(),
        )
        for resolved in resolved_group.tasks:
            append_resolution_trace(resolved.trace)
        self._publish_commands(commands)
        return resolved_group

    def _failure(self, task, stage, error, mission_id, group_id=0):
        try:
            record = {
                "mission_id": mission_id,
                "group_id": group_id,
                "task_id": int(task.get("task_id", 0)),
                "candidate_lfs": task,
                "configuration_id": self.policy_config.configuration_id,
                "rejection_stage": stage,
                "rejection_reason": str(error),
            }
            error_code = getattr(error, "code", None)
            diagnostics = getattr(error, "diagnostics", None)
            if error_code is not None:
                record["error_code"] = error_code
            if diagnostics:
                record["diagnostics"] = diagnostics
            append_resolution_trace(record)
        except Exception as trace_error:
            self.node.get_logger().error(
                f"failed to write Candidate rejection trace: {trace_error}"
            )

    def _wait_elapsed(self, duration):
        if not math.isfinite(duration) or duration < 0.0:
            raise ValueError("elapsed wait duration must be finite and non-negative")
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            rclpy.spin_once(
                self.node,
                timeout_sec=min(0.1, max(0.0, deadline - time.monotonic())),
            )

    def _wait_stable(self, uav_ids):
        timeout = float(
            self.node.get_parameter("candidate_completion_timeout").value
        )
        deadline = time.monotonic() + timeout
        ids = tuple(int(uid) for uid in uav_ids)
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.1)
            if self.completion_tracker.all_stable(ids):
                return
        pending = [
            uid for uid in ids if not self.completion_tracker.is_stable(uid)
        ]
        raise TimeoutError(f"Candidate hover completion timed out: {pending}")

    def _wait_machine(self, machine, resolved):
        if machine.completion_event == "stable":
            self._wait_stable(resolved.executable_lfs.uav_ids)
        elif machine.completion_event == "trajectory_complete":
            self._wait_elapsed(resolved.executable_lfs.duration)
        else:
            raise ValueError(
                f"unsupported completion event: {machine.completion_event}"
            )

    def _wait_parallel(self, machines, resolved_group):
        started = time.monotonic()
        configured_timeout = float(
            self.node.get_parameter("candidate_completion_timeout").value
        )
        records = []
        for machine, resolved in zip(machines, resolved_group.tasks):
            records.append({
                "machine": machine,
                "resolved": resolved,
                "completion_deadline": (
                    started + resolved.executable_lfs.duration
                    if machine.completion_event == "trajectory_complete"
                    else None
                ),
                "completed": False,
                "wait_deadline": None,
                "done": False,
            })
        longest = max(
            record["resolved"].executable_lfs.duration
            + (
                record["machine"].post_completion_wait.duration
                if record["machine"].post_completion_wait is not None
                and record["machine"].post_completion_wait.duration is not None
                else 0.0
            )
            for record in records
        )
        timeout = max(configured_timeout, longest)
        while time.monotonic() - started < timeout:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            now = time.monotonic()
            for record in records:
                if not record["completed"]:
                    machine = record["machine"]
                    resolved = record["resolved"]
                    if machine.completion_event == "stable":
                        completed = self.completion_tracker.all_stable(
                            resolved.executable_lfs.uav_ids
                        )
                    elif machine.completion_event == "trajectory_complete":
                        completed = now >= record["completion_deadline"]
                    else:
                        raise ValueError(
                            f"unsupported completion event: "
                            f"{machine.completion_event}"
                        )
                    if completed:
                        record["completed"] = True
                        wait = machine.post_completion_wait
                        if wait is None:
                            record["done"] = True
                        elif wait.condition == "elapsed" and wait.duration is not None:
                            record["wait_deadline"] = now + wait.duration
                        else:
                            raise ValueError(
                                "unsupported parallel post-completion wait"
                            )
                elif not record["done"] and now >= record["wait_deadline"]:
                    record["done"] = True
            if all(record["done"] for record in records):
                return
        raise TimeoutError("Candidate parallel completion timed out")

    def run(self, candidate_mission):
        validated = early_validate_candidate_mission(
            candidate_mission, available_uav_ids=self.available_uav_ids
        )
        for node in validated["mission"]["nodes"]:
            tasks = [node["task"]] if node["type"] == "task" else node["tasks"]
            for task in tasks:
                self.candidate_policy.resolve_safety(float(task["s"]))
        self._mission_counter += 1
        mission_id = self._mission_counter
        group_counter = {"value": 0}

        def execute_task(machine):
            try:
                resolved = self._resolve_task(machine.task, mission_id)
                self._wait_machine(machine, resolved)
            except Exception as exc:
                self._failure(machine.task, "task_runtime", exc, mission_id)
                raise

        def execute_parallel(machines, completion_mode):
            group_counter["value"] += 1
            group_id = group_counter["value"]
            tasks = [machine.task for machine in machines]
            try:
                resolved = self._resolve_parallel(
                    tasks, mission_id, group_id, completion_mode
                )
                self._wait_parallel(machines, resolved)
            except Exception as exc:
                for task in tasks:
                    self._failure(
                        task, "parallel_runtime", exc, mission_id, group_id
                    )
                raise

        def execute_wait(wait_spec):
            if wait_spec.condition != "elapsed" or wait_spec.duration is None:
                raise ValueError("unsupported internal WaitSpec")
            self._wait_elapsed(wait_spec.duration)

        compiled = execute_candidate_payload(
            validated,
            MissionRuntimeCallbacks(
                execute_task=execute_task,
                execute_parallel=execute_parallel,
                execute_wait=execute_wait,
            ),
            available_uav_ids=self.available_uav_ids,
        )
        self.node.get_logger().info(f"Candidate mission {mission_id} completed")
        return compiled
