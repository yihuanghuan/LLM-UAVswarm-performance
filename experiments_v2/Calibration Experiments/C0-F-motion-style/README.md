# C0-F — Motion style

Owner scope: auto-duration style factors, non-normal style gains and declared
profile application smoothing. `task_adaptation=identity`, `task_gain=1.0`,
normal identity gain and all earlier C0 values are read-only.

The calibration harness is in `motion_style_calibration_pipeline/`. It runs the
fixed 12-condition screen, one alpha=1 style-switch smoke, and—only after a
candidate lock—the fixed 24-condition confirmation plus the locked smoke.
Raw bags are append-only local evidence under the freeze directory and are not
tracked; the content-addressed CSV/YAML summaries and audit are tracked.

The four scenes translate an already-spaced rigid formation. This exercises the
production Candidate allocator and `ladrc_acceleration` chain without making
C0-F a safety/IAPF stress experiment.
