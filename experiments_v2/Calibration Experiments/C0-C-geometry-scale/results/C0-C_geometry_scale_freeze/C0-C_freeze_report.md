# C0-C geometry / qualitative-scale freeze report

## Governance preflight

- Base branch/head: `cal/C0-B-state-freshness` at `0aab111a14cd59145309b8282ca5c1376e4a5b8f`.
- Algorithm-freeze audit: **PASS**; the manifest SHA-256 is `e8ff8a27e65e1e62b031e50c6c4283b6f1b265a7051ad723c6a2ca3c032e102e`.
- C0-A frozen execution-policy SHA-256: `1ac009c4da6636fe4a3fcd8492fe9957e22bba94412e005a3555dd5985a5d325`.
- C0-B frozen state-freshness-policy SHA-256: `fdc7b3fd038ae623699eaefd131028d53a259c22507b320c2775369c23594884`.
- Ownership audit: **PASS**; this campaign only selects `geometry.workspace_bounds`, `geometry.nominal_spacing`, and `geometry.qualitative_multipliers`.

## Stage A result

The bounded fixed-multiplier grid selected **2.25 m**.  All legal Line, Triangle, Circle, Polygon (every legal side/count pairing), and Sphere cases through eight UAVs resolved through `build_unit_geometry()`, `resolve_scale()`, and `build_final_geometry()` without failure.  The requested nearest-neighbor invariant held in every row before safety correction.

The winner is the smallest grid point with valid geometry and strictly distinct executed compact/normal/spacious spacings at `s=1`; it therefore wins the preregistered minimum-deviation tie-break.  No fallback multiplier grid was used.

The workspace is retained unchanged: lower `[-15.0, -10.0, 0.5]`, upper `[15.0, 35.0, 15.0]`.  This is a conservative simulation experiment envelope, retained from the current Gazebo/PX4 calibration lanes (which use ENU coordinates inside it); face checks exercise rejection and the canonical inset has a finite positive limiter.  It is not represented as a motion-capture-room measurement.

## Safety-floor compatibility

At the current runnable `d_plan(s=1)=2.0 m`, `35` of `105` selected-case qualitative requests are safety-raised (the compact request is clipped).  The levels still execute at distinct spacings.  For compact to remain unclipped at baseline safety preference, future C0-D `d_plan_base` must not exceed **1.8 m**.  This is a downstream compatibility ceiling, not a C0-D freeze.

## Stage B

All nine predeclared cold-start trials passed: Triangle (3 UAV), Line (8 UAV), and Sphere (8 UAV), each at compact, normal, and spacious.  The runtime table records Candidate completion, geometry validity, workspace result, frozen-freshness outcome, resolved scale, and final target coordinates.  The temporary Candidate-owned readiness harness is startup infrastructure only; it leaves the frozen post-submission freshness predicates unchanged.

This commit records Stage A/B evidence only.  It does not integrate or freeze the canonical Paper policy.
