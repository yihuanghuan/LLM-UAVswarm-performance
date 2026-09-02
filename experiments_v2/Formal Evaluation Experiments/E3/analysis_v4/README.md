# E3-v4 confirmatory analysis bundle

This directory contains the deterministic analysis of the completed standalone E3-v4 confirmatory campaign. Its immutable campaign source is commit `f61c8c174eb4ca836a54af999189550a2bf46f34`; analysis lives only on `formal/E3-v4-analysis-v1`.

Run from the repository root:

```bash
python3 "experiments_v2/Formal Evaluation Experiments/E3/analysis_v4/scripts/test_e3_v4_analysis.py"
python3 "experiments_v2/Formal Evaluation Experiments/E3/analysis_v4/scripts/run_e3_v4_analysis.py" --clean
```

The script verifies all frozen identities and campaign invariants before producing output. It consumes only the frozen `metrics` payloads in formal attempt evidence. It does not read qualification or E3-v3 outcomes, recompute scientific metrics from raw data, or mutate campaign evidence.

Primary inference uses exactly 74 complete scenario-by-seed four-cell blocks. Available-cell and all-attempt results are clearly separated sensitivities. The preregistered feedback-intervention-burden endpoint remains explicitly unavailable (`N=0/343`) under the branch-local pre-effect-estimation human adjudication, with no proxy or imputation.

Generated products are in `outputs/`, `report/`, and the two analysis freeze-audit files at this directory root. The output manifest intentionally excludes its own hash to avoid recursive self-reference; its SHA-256 is reported at handoff.
