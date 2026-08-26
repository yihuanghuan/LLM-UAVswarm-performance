# E1 formal tooling

This directory contains experiment-only tooling for the sealed E1 protocol.
It imports the frozen production Candidate parser and does not implement a
replacement parser or fallback path.

No command invokes the real provider unless `e1_runner.py` is given the
explicit `--execute-real-provider` flag. Fixture runs are labeled
`synthetic_validation` and are not accepted formal results.

Before a future formal run, use the locked client environment:

```bash
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python e1_provenance.py
```

The real runner performs the same fail-closed validation again before its
first request. Results default to `E1/results/formal/<run-id>` and use an
append-only hash-chained event journal. The scorer and auditor are offline:

```bash
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python e1_scorer.py RUN_DIR
/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python e1_audit.py RUN_DIR
```
