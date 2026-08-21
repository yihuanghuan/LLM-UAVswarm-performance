# Paper-final experiment governance

This document governs the new paper-final calibration and formal-evaluation
workflow. It does not replace or modify `experiments/docs/requirements.md`,
which remains authoritative only for legacy experiments and the retained
`exp/*` branches.

## Immutable algorithm baseline

- Algorithm tag: `paper-algorithm-freeze-v1`
- Commit: `56e8d2c8e59fc3513769e21910b7a20b2b43088d`
- Policy present at the freeze: `paper-current-v7`
- Hash manifest: `experiments/calibration/algorithm_freeze_manifest.json`

The tag is immutable. It must never be recreated, moved, force-pushed, or
deleted. Existing `exp/*` branches and `gazebo-experiment-v1` are historical
evidence and must remain intact.

The frozen boundary includes Candidate LFS/schema semantics, validation and
resolution, geometry, the lexicographic allocator objective, Minimum-Jerk
mathematics, Execution Profile and Safety Compiler structure, LADRC
mathematics, IAPF equations/gates/hysteresis/escape logic, the PX4
acceleration-level interface, and the one-time mapping of `s` to allocator
`d_plan` and IAPF enter/exit/repulsion scale. Calibration may change only
ledgered numerical values owned by the active C0 experiment.

Before accepting a parameter-freeze commit, recompute every SHA-256 in the
algorithm manifest against the freeze tag and audit any changed core file. A
core-file change is not a calibration result; it invalidates the algorithm
freeze and requires an explicitly versioned new baseline.

Run the automated gates from the repository root before a C0 trial and before
accepting its parameter-freeze commit:

```bash
python3 experiments/calibration/scripts/check_algorithm_freeze.py
python3 experiments/calibration/scripts/check_parameter_ownership.py \
  --calibration C0-A
```

Replace `C0-A` with the active owner. The ownership checker defaults to the
local `paper/calibration` ref; CI or a review branch may pass an explicit
`--baseline-ref origin/paper/calibration`. Parameter policy/config files are
checked key by key and are deliberately not treated as wholly immutable
algorithm files.

## The one calibration mainline

`paper/calibration` is the only cumulative parameter-freeze branch. Use this
order:

```text
paper-algorithm-freeze-v1
└── paper/calibration
    ├── cal/C0-A-ladrc-motion-limits
    ├── cal/C0-B-state-freshness
    ├── cal/C0-C-geometry-scale
    ├── cal/C0-G-allocator-numerical
    ├── cal/C0-D-safety
    ├── cal/C0-E-iapf
    └── cal/C0-F-motion-style
```

For each C0:

1. Create `cal/C0-X-*` from the latest `paper/calibration`.
2. Freeze its `CALIBRATION_PROTOCOL.md` before examining sweep results.
3. Keep runners, debug hooks, bags, raw data, metrics and figures on the
   temporary C0 branch or in external artifact storage.
4. Retain every trial, including failures and timeouts.
5. Apply to `paper/calibration` only the selected parameter values, ledger
   status, provenance, result manifest and a concise result record.
6. Create and push a new immutable checkpoint tag such as
   `paper-cal-C0A-v1`; do not move a checkpoint tag.
7. Create the next C0 branch from the updated `paper/calibration`, never from a
   preceding temporary C0 branch.

Do not merge calibration-only launch wrappers, rosbag data, sweep code,
plotting, debug instrumentation or generated results into
`paper/calibration`. A parameter owned by a completed C0 is read-only to every
later C0.

## Parameter ownership and freeze gate

The authoritative ownership inventory is
`docs/paper_parameter_freeze_ledger.md`. Every `PROVISIONAL` row must have
exactly one owner among C0-A through C0-G. A C0 branch may write only its owned
rows. `ARCHITECTURE_FROZEN` rows are never calibration variables.

Each parameter-freeze commit must record the selected value, protocol and
result paths, calibration scenario IDs, seeds, raw-data URI/hash, analysis
script commit, environment versions and the new policy/config hash. A
development value is not `FROZEN` merely because it is currently runnable.

## Calibration and formal-data isolation

The directory-level rules are documented under
`experiments_v2/Calibration Experiments/README.md` and
`experiments_v2/Formal Evaluation Experiments/README.md`.

- Calibration scenarios and seeds may select parameters.
- Formal scenarios and seeds must remain sealed and may not select parameters.
- If any formal scenario or seed influences a parameter choice, permanently
  reclassify it into the calibration set and replace it in the formal registry
  before any formal run is accepted.
- Calibration raw data and formal-evaluation data must never be pooled,
  aggregated or reported as one statistical sample.
- Historical `exp/*` results are legacy/pilot evidence. They do not
  automatically enter either new dataset and cannot confer paper-final status
  on a development value.

Every artifact manifest must declare `dataset_class` as exactly
`calibration`, `formal_evaluation`, or `legacy_pilot`, plus scenario registry
version, scenario ID, seed, Git commit and policy hash. Cross-class output
directories are prohibited.

## Paper-final and formal branches

After all C0 rows are frozen, audit the cumulative diff against
`paper-algorithm-freeze-v1`. It may contain frozen numerical parameters,
provenance and non-semantic documentation only. Then create a new immutable
paper-final tag (planned configuration ID `paper-final-sim-v1`).

Every formal experiment branch must start independently from that exact tag:

```text
paper-final-sim-v1
├── paper-exp/<experiment-a>
├── paper-exp/<experiment-b>
└── paper-exp/<experiment-c>
```

Formal branches may add observation, recording, plotting, scenario runners,
and already-defined baseline/ablation switches. They may not change a Full
Method parameter, parser/prompt/schema, resolver, geometry, allocator
objective, safety mapping, trajectory/controller/IAPF mathematics, or PX4
control interface. Any post-freeze semantic or parameter change marks affected
formal results `INVALIDATED_BY_POST_FREEZE_CHANGE` and requires a new
calibration/final version.
