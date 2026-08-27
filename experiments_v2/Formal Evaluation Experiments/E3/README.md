# E3 exact-trial planning × feedback safety runner

Synthetic/contract validation only. Every artifact is `synthetic_validation`,
`accepted_formal_result: false`, and `NOT_FORMAL_RESULT`. The runner accepts one
exact sealed E3 ID, reconstructs its registered execution spec, durably retains
the mock artifact, and only then appends its local hash-chained journal. It has
no “next” selector and never reads or mutates the global campaign journal.

The four mappings are exact: P1=`safety_aware`, P0=`distance_hungarian` without
fixed target ownership, F1=`iapf_dual`, and F0=`off`. Staging requires 2.0
continuous stable seconds and is unscored; scoring ends at duration+2 seconds
and timeout is duration+6 seconds after interaction t0. Every condition loads
the sealed GazeboRosForce/e3_wrench_driver path, including Family A zero force.

The validation backend never launches ROS/Gazebo/PX4 and never creates metric
endpoint values. LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL DATA-COLLECTION
ORDER.

Run from repository root with the tooling directory on `PYTHONPATH`:

```bash
pytest -q "experiments_v2/Formal Evaluation Experiments/E3/tooling/test_e3_runner.py"
python3 "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runner.py" --synthetic-validation --run-id RUN_ID
python3 "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_audit.py" RUN_DIR
```
