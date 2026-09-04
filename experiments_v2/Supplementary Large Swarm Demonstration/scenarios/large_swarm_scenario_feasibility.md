# Large-swarm deterministic scenario feasibility

This is pre-mission, read-only design analysis using the frozen validator, geometry, allocator, timing, and policy. It made no LLM call and executed no Gazebo mission.

| Candidate | N | selected | feasible | r_exec | T_exec | target d_min | predicted path d_min | hard conflicts | disposition |
|---|---:|---|---|---|---|---:|---:|---:|---|
| D1 | 24 | true | true | 10.000 | 16.000 | 2.610523844401028 | 1.8373227364618427 | 0 | accepted by every deterministic gate |
| D1 | 28 | true | true | 10.000 | 16.000 | 2.2392895220661475 | 1.8873909657849957 | 0 | accepted by every deterministic gate |
| D1 | 32 | true | true | 10.000 | 16.000 | 1.9603428065912047 | 1.711782556044825 | 0 | accepted by every deterministic gate |
| D2 | 24 | true | true | 8.619 | 9.455 | 2.2499999999999987 | 1.5960351211141646 | 0 | accepted by every deterministic gate |
| D2 | 28 | true | true | 10.048 | 5.988 | 2.2499999999999996 | 1.8933268226246938 | 0 | accepted by every deterministic gate |
| D2 | 32 | true | true | 11.478 | 9.153 | 2.249999999999999 | 1.8709029995886992 | 0 | accepted by every deterministic gate |
| D3 | 24 | true | true | 5.000,5.000 | 16.000,16.000 | 2.5881904510252043 | 2.1945692419225247 | 0 | accepted by every deterministic gate |
| D3 | 28 | true | true | 5.000,5.000 | 16.000,16.000 | 2.22520933956314 | 1.7872314414388424 | 0 | accepted by every deterministic gate |
| D3 | 32 | true | true | 5.000,5.000 | 16.000,16.000 | 1.9509032201612795 | 1.7234563520802577 | 0 | accepted by every deterministic gate |
| R-D1-R8 | 24 | false | true | 8.000 | 16.000 | 2.0884190755208225 | 1.813985250472748 | 0 | accepted by every deterministic gate |
| R-D1-R8 | 28 | false | false | 8.038 | 16.000 | 1.7999999999999998 | 1.6156645736505193 | 0 | resolved output violates workspace, hard-safety, dynamics, or exact explicit-value gate |
| R-D1-R8 | 32 | false | false | 9.182 | 16.000 | 1.7999999999999996 | 1.6071228684721055 | 0 | resolved output violates workspace, hard-safety, dynamics, or exact explicit-value gate |
| R-D1-T8 | 24 | false | true | 10.000 | 8.000 | 2.610523844401028 | 1.8373227364618427 | 0 | accepted by every deterministic gate |
| R-D1-T8 | 28 | false | true | 10.000 | 8.000 | 2.2392895220661475 | 1.8873909657849957 | 0 | accepted by every deterministic gate |
| R-D1-T8 | 32 | false | true | 10.000 | 8.000 | 1.9603428065912047 | 1.711782556044825 | 0 | accepted by every deterministic gate |
| R-D2-SPHERE | 24 | false | false | NA | NA | NA | NA | 0 | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-D2-SPHERE | 28 | false | false | NA | NA | NA | NA | 0 | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-D2-SPHERE | 32 | false | false | NA | NA | NA | NA | 0 | workspace scale limit conflicts with d_plan(s) or requested scale |
| R-D3-CONTIGUOUS-HALVES | 24 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |
| R-D3-CONTIGUOUS-HALVES | 28 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |
| R-D3-CONTIGUOUS-HALVES | 32 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |
| R-D3-CLOSE | 24 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |
| R-D3-CLOSE | 28 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |
| R-D3-CLOSE | 32 | false | false | NA | NA | NA | NA | 0 | parallel nominal trajectory violates d_hard |

D1, D2, and the spatially partitioned D3 are feasible for N=24, 28, and 32. D3's initially examined contiguous-ID partition is retained as rejected because it creates nominal cross-group hard conflicts; the selected left/right parking partition is the first feasible D3 candidate and keeps equal subgroup sizes.

Rejected/non-selected candidates are not ranked by predicted mission success: radius 8 requires frozen safety enlargement at N=28/32; the shorter D1 duration is feasible but follows the already selected first representative D1 candidate; maintain-current Sphere conflicts with the lower workspace boundary; close or contiguous parallel groups fail the nominal hard gate.

Despite scenario feasibility, no primary showcase N is selected because none of N=24, 28, or 32 passed the infrastructure sweep. No showcase mission may start under this candidate protocol.
