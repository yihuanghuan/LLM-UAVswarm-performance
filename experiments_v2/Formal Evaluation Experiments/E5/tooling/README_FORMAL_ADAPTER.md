# E5 formal exact-trial adapter

`e5_formal_adapter.py` accepts exactly one globally supplied registered E5 trial. It never selects campaign order, replaces a seed, retries a retained attempt, or writes a suite journal. Formal execution is present only behind the external launch authorization gate.

The formal backend cold-starts the pinned eight-UAV PX4/Gazebo/controller deployment and sends the sealed command bytes through the frozen Candidate parser and `PaperMissionRuntime`. Candidate ground truth is never a runtime input. Raw LLM, validation, resolution, assignment, execution-command, controller, safety, and vehicle traces are retained, with the sealed latency components kept separate.

`e5_engineering_smoke.py` uses a single non-registered natural-language fixture. Its output is engineering validation only (`accepted_formal_result=false`) and is not interpreted scientifically.
