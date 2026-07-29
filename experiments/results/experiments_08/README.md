# Experiment 08 results

Results are separated by protocol version:

- `v1_original/formal/exp08-formal-20260728`: original M0–M5 formal batch;
- `v1_original/smoke_runs`: original development/smoke runs, not formal data;
- `v2_patch/pilot`: 27-arm patch-protocol qualification batches;
- `v2_patch/formal`: 230-trial patch-protocol formal batches.

Each execution creates a new `<batch_id>` directory. Raw per-trial artifacts,
rosbags, and videos are tracked with Git LFS; summaries, statistics, figures,
metadata, reports, and SHA-256 manifests remain normal Git objects.

Existing batch directories must never be reused or overwritten.
