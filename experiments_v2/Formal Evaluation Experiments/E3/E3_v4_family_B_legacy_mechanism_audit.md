# E3-v4 Family-B legacy mechanism audit

Status: `FROZEN_BEFORE_NEW_FAMILY_B_IMPLEMENTATION`

This audit was performed after the approved wrench-assay transition and before
any new Family-B physical attempt.  It examines mechanism compatibility only;
it does not import legacy numerical settings or legacy outcome definitions.

## Sources inspected

- Exp08 branch `exp/08-iapf` at
  `bed7c764daaf8d9825c34032767b711986cab078`:
  - `scripts/run_experiment.py`, SHA-256
    `8bdf54e31c2b4ff3c8b97667c0dbf7af681116686286b5a0f383510fa8de4617`;
  - `staggered_crossing_delay.yaml`, SHA-256
    `19d3d687050313e593aacd351e86f930be624dbabf1d2acd7b05abc8707ef54b`;
  - `dense_local_bias.yaml`, SHA-256
    `ab981fccc4f6faeabeb866503e6c342d0a8abf02f891898e66713750129c10e6`;
  - its README and batch runner.
- Exp09 branch `exp/09-safety-ablation` at
  `5996da84d21ab04b9684b2e7a585be79698672b4`:
  - `scripts/run_experiment.py`, SHA-256
    `9e431b3b46d06b075d04a8caf5ec895aa31e330ad8bcfdc584265802f0aa0dc2`;
  - `s2_dense_local_bias.yaml`, SHA-256
    `07fdf8bf46aabe7fcb653e6cc2cbc47b6a3d3cebf0d59180b4aafdcd173294be`;
  - `s3_staggered_dynamic_crossing.yaml`, SHA-256
    `0e02fc4a3fc3c56364058012a7819cbce702d8bd85c290f17c6deaf633c360b9`;
  - its README and protocol-freeze material.

## Command-delay mechanism

The legacy runner completed target allocation before ROS execution.  For a
delay scene it split the already allocated groups into immediate and delayed
UAVs, published the immediate commands, waited for `delay_sec`, then published
the delayed commands.  It did not rerun allocation or change target ownership.
Exp09 generalized this from one UAV to a fixed subgroup.

The scientific mechanism is reusable, but the legacy delivery implementation
is not sufficient for E3-v4.  Its wait was governed by `time.monotonic()`, its
event records did not independently verify every command publication, and it
did not fail closed on the achieved ROS/simulation-time delay.  E3-v4 will use
the existing frozen `UAVExecutionCommand` interface, but will schedule and
verify both command generations from ROS time.  The bagged command header and
bag timestamp, followed by the controller's bagged `StartupEvent` acceptance,
will be authoritative.  Allocation and compiled profiles remain committed
before the first interaction command.

The legacy numerical scenes are not current Family-B candidates.  In
particular, current-policy offline evaluation of Exp09 `s3` gives one P0
predicted hard violation (`d_min = 0.734709 m`) while P1 changes assignment and
gives `d_min = 2.898310 m`; that is a planning manipulation, not a planning-safe
Family-B assay.  Current-policy evaluation of Exp08's two-UAV delay geometry is
planning-safe, but both allocators swap the legacy target order and predict
`d_min = 4.215317 m`, so the old geometry does not preserve its intended
crossing mechanism.

## Reference-deviation mechanism

The legacy Exp08/09 runner called each controller's parameter service after
execution began and set `experiment_reference_bias_{x,y,z}`.  It later reset
those values to zero.  The legacy controller source declared those parameters
and added the bias inside its control reference calculation.

That hook is **not present** in the frozen current controller source
(`minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`,
SHA-256
`cc7a3b1c36126555749504d03b504c1c6c01e210ffb829b473d8980a87973dfa`),
and the installed frozen binary contains no corresponding parameter symbols.
Reintroducing it would modify production controller semantics and is forbidden.
The legacy parameter-hook implementation therefore will not be copied.

The current frozen controller does, however, already support accepting a new
validated `UAVExecutionCommand` during an active mission.  Acceptance calls the
existing command-initialization path and generates a new minimum-jerk reference
from the current realized state to the newly commanded target.  The current
interface SHA-256 is
`10d329b9d8bc859a453ad62cb21a4eae11b1c57b85758d9a4cee1716e07a0058`.

E3-v4 will therefore implement B-02 as an **external execution-reference
command deviation**, not as the removed legacy controller-parameter bias:

1. publish and obtain acceptance of the nominal committed command;
2. at a registered ROS time, publish one validated command for the affected UAV
   whose endpoint is the counterfactual nominal reference at the registered
   reset time plus the registered offset;
3. after the registered interval, publish one validated reset command to the
   original committed target.

This uses only an existing production input interface.  It changes no planner,
allocator, controller, IAPF, threshold, profile compiler, or safety semantics.
The bias and reset commands receive distinct mission IDs.  Their exact payloads
and header stamps, controller `command_accepted` acknowledgments, and
`ControlTrackingDebug` mission/reference samples will independently prove that
the requested reference deviation became effective and was reset.  A request
without all three evidence classes is an infrastructure failure.

Current-policy evaluation of the legacy six-UAV dense geometry gives the same
identity assignment for P0 and P1, zero predicted hard violations, and
`d_min = 2.400000 m`.  Thus its planning-side idea is compatible, but its old
1.5 m parameter-hook bias, timing, and geometry are only priors; none are
adopted without a new finite preregistration.

## Reuse decision

- Reuse: post-allocation command staggering, current validated execution
  command interface, controller acceptance events, and current debug evidence.
- Reimplement experiment-only: ROS-time scheduling, event ledger, exact
  delivery verification, and temporary reference command/reset orchestration.
- Do not reuse: wall-clock scientific timing, request-only evidence, removed
  production parameter hooks, legacy thresholds, old metric definitions, or
  unvalidated legacy numerical settings.
- Production source modification authorized or required: **none**.
- F1 attempts inspected or executed for selection: **zero**.
- Formal E3-v4 attempts executed: **zero**.
