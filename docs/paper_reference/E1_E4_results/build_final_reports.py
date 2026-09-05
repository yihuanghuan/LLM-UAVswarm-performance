#!/usr/bin/env python3
"""Append E5 without touching source evidence; audit aligned bilingual reports.

No metric estimation or experiment execution. The Chinese report is a manually
translated, line-aligned document. Run with --generate to build English, then
without arguments to verify and write deterministic audits.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], cwd=HERE, text=True).strip())
SOURCE_COMMIT = '8a17fab8807ee83e06aceaeb8bb4c468a84d34f4'
SOURCE_BRANCH = 'paper/E1-E4-experiment-results-reference-v1'
SOURCE = HERE / 'E1_E4_experiment_results_reference.md'
EN = HERE / 'E1_E4_experiment_results_reference_E1_E5_EN.md'
ZH = HERE / 'E1_E4_experiment_results_reference_E1_E5_ZH.md'
V1_RAW = '33538b91ab9e0c53b918cdc0e47e3b7fa6f08592'
V1_ANALYSIS = '511192273a61f97e2742a1cc6608e18ed960cc1f'
V2_SOURCE = '558def6238826460cb3f9323af445e8c299fb610'
V2_ANALYSIS = 'bc760d5795ff87c62df6e86875d9a906cc449e2d'
E5 = 'experiments_v2/Formal Evaluation Experiments/'

EN_APPEND = r'''
# E5 — End-to-End Integration Evaluation

## E5.1 Objective and evidence scope

The preceding E1–E4 reference, including its title, scope statement, summaries, checklist, and extraction kit, is preserved verbatim. Its statements about excluding E5 apply to that original reference. Everything from this E5 heading onward is a new reporting addition; it does not revise any E1–E4 result, interpretation, or claim mapping.

**FACT.** E5 comprises two separately registered end-to-end integration evaluations, E5-v1 and E5-v2. They assess the path from natural language through Candidate semantics, staged state-dependent resolution, geometry, assignment, execution timing and safety, LADRC, PX4/Gazebo, and mission completion. E5-v1 tests the original integration registry and its boundaries; E5-v2 tests prospectively feasible under-specified commands and the unchanged method at registered swarm sizes N=8, N=12, and N=16. [Sources: `E5-V1-REGISTRY`; `E5-V1-ANALYSIS`; `E5-V2-REPORT`.]

**INTERPRETATION.** E5 is descriptive end-to-end integration and system-completeness evidence, not new causal evidence for C1/C2/C3. Its registries are different and their attempt denominators remain separate. No new endpoint, inferential comparison across N, scaling law, or reanalysis is introduced here. Values below are copied from frozen reports/tables, with presentation rounding only.

## E5.2 E5-v1 — Original Frozen Integration Evaluation

### Protocol and accounting

**FACT.** Registry `E5-exact-end-to-end-v1` used baseline `paper-final-sim-v3`, configuration `paper-current-v11-c0-f-frozen`, five scenarios, and five cold-start seeds per scenario. All 25 registered attempts were retained: 19 scientific-complete and 6 infrastructure failures. All-attempt mission success was 14/25 = 56.0%. The frozen integration adjudication remains `PARTIALLY_SUPPORTED`. [Sources: `E5-V1-REGISTRY`; `E5-V1-ANALYSIS`.]

### Scenario-wise results

| Scenario | Scientific-complete / registered | Mission success / registered | Retained interpretation |
|---|---:|---:|---|
| SIMPLE | 5/5 | 5/5 | Full simple-mission integration observed |
| REL-QUAL | 5/5 | 0/5 | All reached the frozen resolver; valid fail-closed physical-admissibility rejection |
| SEQUENTIAL | 4/5 | 4/5 | Four completed; one retained infrastructure failure |
| PARALLEL | 5/5 | 5/5 | Full parallel-mission integration observed |
| MIXED-HIGH | 0/5 | 0/5 | No scientific-complete highest-complexity mixed mission from the frozen semantic frontend |

[Source: `E5-V1-ANALYSIS`, including the scenario summary and frozen limitation adjudication. Scientific completeness is not synonymous with mission success: a retained resolver rejection can be scientifically complete.]

### Boundary evidence

**INTERPRETATION.** REL-QUAL remains valid negative boundary evidence: its registered relative/qualitative spacious-Sphere realization was physically inadmissible under the frozen workspace/safety geometry. Every attempt reached the resolver and was correctly rejected rather than forcing an invalid physical realization. This result is not invalid or obsolete and must not be rewritten as a command repaired by E5-v2.

### Limitations

MIXED-HIGH remains a semantic-frontend complexity limitation under the evaluated configuration. The evidence does not isolate the LLM model as the sole cause: model capability, prompt/few-shot design, structured generation, output budget, and timeout/retry interaction may all contribute. The frozen infrastructure accounting remains unchanged; this mechanism-level description does not relabel terminal statuses. No successful execution of this highest-complexity mixed mission is established by E5-v1 or by the different E5-v2 compositional tasks. [Source: `E5-V1-ANALYSIS`.]

**PAPER-WRITING RECOMMENDATION.** Present successful simple/sequential/parallel integration together with both boundaries. Keep 14/25 and the scientific-complete/infrastructure split visible; do not remove failed attempts or pool this denominator with E5-v2.

## E5.3 E5-v2 — Feasible Under-Specified Realization

### Overall accounting

**FACT.** All 60 registered E5-v2 attempts satisfied the frozen end-to-end mission-success criterion. The exact frozen order was completed without replacement or additional samples. The criterion required correct valid Candidate semantics without ground-truth fallback, resolver/planner acceptance, registered task completion, no infrastructure/hard failure or failsafe, and actual d_min >= d_hard = 1.50 m. [Sources: `E5-V2-COMPLETION`; `E5-V2-REPORT`; `E5-V2-MAPPING`.]

| Endpoint | Numerator / denominator | Percentage | Frozen two-sided Wilson 95% CI |
|---|---:|---:|---:|
| Scientific completeness | 60/60 | 100.0% | [94.0%, 100.0%] |
| Candidate correctness | 60/60 | 100.0% | [94.0%, 100.0%] |
| Resolver success | 60/60 | 100.0% | [94.0%, 100.0%] |
| Mission completion | 60/60 | 100.0% | [94.0%, 100.0%] |
| Mission success | 60/60 | 100.0% | [94.0%, 100.0%] |
| Infrastructure failure | 0/60 | 0.0% | [0.0%, 6.0%] |
| Failsafe | 0/60 | 0.0% | [0.0%, 6.0%] |
| Hard failure | 0/60 | 0.0% | [0.0%, 6.0%] |

[Source: `E5-V2-OVERALL`. These are frozen Wilson intervals, not newly estimated intervals or universal reliability bounds.]

### E5-v2A scenario results

E5-v2A contains 15 registered N=8 attempts: three prospectively feasible scenarios with five attempts each. Scientific completeness and mission success were both 15/15. Candidate correctness, resolver success, and mission completion also held in all 15 attempts. The scenarios exercise relative versus maintain-current center semantics, compact/normal/spacious qualitative scales, different supported geometries, and auto timing. [Source: `E5-V2-REPORT`.]

| Scenario | Mission success | Mean d_min (m) | Mean tracking RMSE (m) | Mean final error (m) | Mean completion time (s) |
|---|---:|---:|---:|---:|---:|
| A1 — REL-COMPACT-CIRCLE | 5/5 | 1.665 | 0.122 | 0.089 | 5.608 |
| A2 — MAINTAIN-NORMAL-LINE | 5/5 | 1.799 | 0.132 | 0.155 | 7.607 |
| A3 — REL-SPACIOUS-SPHERE | 5/5 | 2.370 | 0.105 | 0.105 | 6.617 |

[Source: `E5-V2-A-TABLE`. Each 5/5 outcome has frozen Wilson 95% CI [56.6%, 100.0%]; the 15/15 substudy interval is [79.6%, 100.0%]. Small-cell observed success is not a guarantee.]

### Resolved c/r/T

| Scenario | Mean c_exec [x, y, z] (m) | Mean r_exec (m) | Mean T_exec (s) | Registered semantic consistency |
|---|---:|---:|---:|---|
| A1 — REL-COMPACT-CIRCLE | [3.007, 13.499, 2.503] | 2.352 | 4.304 | PASS |
| A2 — MAINTAIN-NORMAL-LINE | [0.005, 13.498, 1.500] | 2.250 | 6.398 | PASS |
| A3 — REL-SPACIOUS-SPHERE | [0.005, 13.498, 6.501] | 3.721 | 4.939 | PASS |

[Sources: `E5-V2-REPORT`; `E5-V2-RESOLVED`. Centers are component-wise means of observed resolutions, not fixed replacement commands. All Candidate/resolver and c/r/T semantic-mode consistency checks passed.]

### Safety and tracking outcomes

**INTERPRETATION.** The feasible relative/qualitative/auto commands traversed the real semantic frontend and frozen deterministic physical pipeline through closed-loop mission completion. A3 specifically shows that qualitative `spacious` Sphere semantics were executable when their state-dependent physical realization lay within the frozen workspace and safety envelope. It did not fix, replace, or rerun E5-v1 REL-QUAL: the commands and registries differ.

The scenario means above describe realized geometry and tracking, not optimization of scenarios by observed success. Across E5-v2, the observed minimum actual d_min was 1.593 m, above the independently frozen 1.50 m hard threshold. This supports the registered hard-distance criterion in these attempts, not a universal collision-free guarantee. [Source: `E5-V2-OVERALL`.]

## E5.4 E5-v2 — Tested-Size N=8/12/16 Demonstration

### N × family results

**FACT.** E5-v2B contains 45 registered attempts, with 45/45 scientific completeness and 45/45 mission success. SIMPLE, UNDER_SPECIFIED, and COMPOSITIONAL each appear at N=8, N=12, and N=16, with five attempts in each of the nine cells. Candidate correctness, resolver success, and mission completion were also observed in all 45 attempts. [Sources: `E5-V2-REPORT`; `E5-V2-B-TABLE`.]

| Cell | Mission success | Mean d_min (m) | Mean tracking RMSE (m) | Mean final error (m) | Mean completion time (s) |
|---|---:|---:|---:|---:|---:|
| N8 SIMPLE | 5/5 | 1.996 | 0.024 | 0.024 | 15.035 |
| N8 UNDER_SPECIFIED | 5/5 | 2.058 | 0.131 | 0.058 | 5.871 |
| N8 COMPOSITIONAL | 5/5 | 2.405 | 0.038 | 0.036 | 15.030 |
| N12 SIMPLE | 5/5 | 1.835 | 0.028 | 0.032 | 15.037 |
| N12 UNDER_SPECIFIED | 5/5 | 1.764 | 0.141 | 0.144 | 7.505 |
| N12 COMPOSITIONAL | 5/5 | 1.865 | 0.054 | 0.071 | 15.035 |
| N16 SIMPLE | 5/5 | 1.823 | 0.042 | 0.046 | 15.038 |
| N16 UNDER_SPECIFIED | 5/5 | 1.714 | 0.118 | 0.155 | 10.235 |
| N16 COMPOSITIONAL | 5/5 | 2.082 | 0.082 | 0.107 | 15.038 |

[Source: `E5-V2-B-TABLE`. Every cell has frozen Wilson 95% CI [56.6%, 100.0%] for mission success. Each N stratum and each family stratum has 15/15 success, with frozen Wilson 95% CI [79.6%, 100.0%]. No new between-size test is performed.]

### Under-specified physical realization across N

| N | Mean c_exec [x, y, z] (m) | Mean r_exec (m) | Mean T_exec (s) | Semantic audit |
|---:|---:|---:|---:|---|
| 8 | [0.005, 13.499, 1.501] | 2.940 | 4.638 | PASS |
| 12 | [0.006, 19.499, 1.500] | 4.347 | 6.296 | PASS |
| 16 | [0.009, 25.502, 1.501] | 5.767 | 9.195 | PASS |

[Sources: `E5-V2-REPORT`; `E5-V2-RESOLVED`.]

**INTERPRETATION.** The same frozen UNDER_SPECIFIED semantic structure produced legitimate state/cardinality-dependent physical realizations. N was not an isolated causal treatment: the frozen spawn rule also changed initial spatial extent, centroid, assignment geometry, displacement, qualitative-scale realization, and auto timing. The observed quantities varied with the associated mission realization; these are neither causal N effects nor formal performance-scaling estimates.

The same command-to-control pipeline was successfully demonstrated at N=8, N=12, and N=16 in the registered simulation scenarios. This does not establish formal or asymptotic scalability, arbitrary-N generalization, linear or near-linear scaling, or real-time scaling guarantees.

### Continuous descriptive outcomes

| Endpoint | Available N | Mean | Median | Sample SD | IQR | Range | Unit |
|---|---:|---:|---:|---:|---:|---:|---|
| actual d_min | 60 | 1.948 | 1.859 | 0.235 | 0.286 | [1.593, 2.420] | m |
| Tracking RMSE | 60 | 0.085 | 0.093 | 0.044 | 0.086 | [0.023, 0.149] | m |
| Final error | 60 | 0.085 | 0.080 | 0.047 | 0.073 | [0.019, 0.163] | m |
| Completion time | 60 | 11.138 | 12.628 | 4.080 | 7.759 | [5.598, 15.041] | s |
| T_LLM | 60 | 19.172 | 16.425 | 11.340 | 9.697 | [8.090, 84.644] | s |
| T_mission_execution | 60 | 11.953 | 14.518 | 4.464 | 7.907 | [5.712, 18.615] | s |

[Source: `E5-V2-OVERALL`. All columns are presentation-rounded frozen summaries, including sample SD and IQR; no alternative aggregation or continuous confidence interval is introduced.]

Completion time, T_mission_execution, and T_LLM retain their distinct frozen mappings; they are not interchangeable clocks or an additive compute decomposition. Final error is the maximum across registered UAVs of each UAV's latest scored tracking-error norm, not another historical E5 aggregation. Completion time runs from first dispatch to observed all-UAV completion; T_mission_execution covers the runtime payload call, including resolution/compilation/dispatch and physical waiting; T_LLM covers the frontend call including its frozen parsing/retries. T_LLM and T_mission_execution are reported separately and are not combined into a scalability metric. [Source: `E5-V2-MAPPING`.]

## E5.5 Governance and Endpoint Availability

### Unavailable endpoints

Continuous E5-v2 `J_hard` is **NA / NOT ANALYZED**, available in **0/60** attempts. Its status is `PREREGISTERED_ENDPOINT_UNAVAILABLE_DUE_TO_SEMANTIC_AMBIGUITY`: the prospective artifacts did not uniquely define the continuous endpoint before physical execution. The frozen adjudication reason is “preregistered continuous endpoint unavailable due to pre-analysis semantic ambiguity.” No replacement definition, proxy, zero imputation, or retrospective raw reconstruction is used. The E3 definition preserved earlier in this report is not imported into E5-v2. Mission success independently retains actual d_min >= 1.50 m. [Source: `E5-V2-ADJUDICATION`.]

| Preregistered latency component | Available / registered | Treatment |
|---|---:|---|
| T_validation | 0/60 | NA |
| T_state_resolution | 0/60 | NA |
| T_geometry | 0/60 | NA |
| T_allocator | 0/60 | NA |
| T_profile | 0/60 | NA |

[Source: `E5-V2-MAPPING`; frozen availability output. These components are not retrospectively split from logs or replaced by aggregate timings.]

### Slot-1 reproducibility note

Slot 1 was physically executed exactly once under execution tooling v1. A post-run metric/packaging infrastructure blocker occurred after raw evidence was fully preserved; the transaction was recovered from that evidence without a physical rerun. Slots 2–60 used amended execution tooling v2. Slot 1 remains in the denominator. Scientific method/protocol changes = 0; production method changes = 0. Instrumentation was not byte-identical across all attempts; exact bundle identities appear in the provenance appendix. [Sources: `E5-V2-COMPLETION`; `E5-V2-REPORT`.]

## E5.6 Integrated E5 Interpretation

E5-v1 provided the first full-pipeline integration evidence and exposed two boundaries: fail-closed rejection of the registered inadmissible relative/qualitative realization, and a highest-complexity semantic-frontend limitation. E5-v2 separately preregistered feasible positive under-specified cases and tested the unchanged pipeline at N=8, N=12, and N=16. Its 60/60 observed mission successes and consistent resolved c/r/T values support successful realization in those registered scenarios, without erasing either earlier boundary.

**INTERPRETATION.** Together, the evidence supports the bounded statement that the system can reject a registered physically inadmissible realization and execute prospectively feasible under-specified commands through the complete semantic-to-control pipeline in the tested UAV-swarm simulation scenarios. The two registries are not pooled, and their percentages are not a before/after method-improvement comparison.

**PAPER-WRITING RECOMMENDATION.** Keep the original and extension evaluations in separate accounting tables within one E5 chapter. Lead with their complementary roles, then present the feasible realization and tested-size observations. Do not describe E5-v2 as replacing, correcting, repairing, or rerunning E5-v1.

## E5.7 Supported and Unsupported Claims

| Question | Evidence | Supported interpretation | Unsupported interpretation |
|---|---|---|---|
| End-to-end integration | Separate E5-v1 and E5-v2 frozen registries | Registered pipeline components operated together in the reported scenarios | Arbitrary natural-language commands or new causal C1/C2/C3 evidence |
| Feasible under-specified realization | E5-v2A 15/15 with Candidate/resolver and c/r/T checks | Feasible relative/qualitative/auto commands completed the tested pipeline | Arbitrary under-specification or universal feasibility |
| Physical boundary handling | E5-v1 REL-QUAL 0/5; separately feasible E5-v2A | Resolver rejected an inadmissible realization and instantiated admissible ones | Every qualitative request is executable in every state/workspace |
| Tested-size demonstration | E5-v2B 45/45 at N=8/12/16 | Unchanged method operated at the registered tested sizes | Arbitrary N; formal/asymptotic/linear/near-linear scalability; causal N effects |
| Reliability | E5-v2 60/60 mission success | All registered attempts satisfied the frozen success criterion | Universal 100% reliability |
| Safety | Minimum observed d_min 1.593 m above 1.50 m | Frozen hard-distance criterion satisfied in these attempts | Collision-free guarantee or continuous E5-v2 J_hard exposure |

# Integrated E1–E5 Evidence Summary

This is a new summary appended after the frozen E1–E4 reference; it does not replace any earlier summary or revise its claim conclusions.

| Established claim mapping | Experiment | Evidence role retained in the final report |
|---|---|---|
| C1: information-aligned late-bound grounding | E1 | Exact valid candidate semantics and preservation of registered unresolved quantities, with invalid/format limitations retained |
| C1: physical commitment timing | E2 | Paired state-shift timing evidence; not language accuracy or universal late-binding optimality |
| C2: planning–execution safety decomposition | E3-v4 | Confirmatory planning, feedback, and mixed-risk responsibility evidence, retaining complete-block/missingness and unavailable-burden boundaries |
| C3 / secondary: bounded behavioral grounding | E4A and E4B | Behavioral distinguishability plus observed authority preservation, not universal ordering or formal guarantees |
| End-to-end integration / system completeness | E5-v1 and E5-v2, separately | Successful registered integration, retained inadmissibility/frontend boundaries, feasible under-specified realization, and operation at N=8/12/16 |

The mechanism-level conclusions remain those of E1–E4. E5 adds evidence that independently evaluated mechanisms coexist in the complete command-to-control pipeline, not new causal support for C1/C2/C3. The final report therefore combines modular mechanism evidence with bounded system-level integration evidence while preserving negative findings, unavailable endpoints, and separate denominators.

# E5 Source and Provenance Appendix

The following immutable sources support only the appended E5 material. Earlier E1–E4 source tags continue to refer to the unchanged adjacent `source_manifest.json`. Repository: `https://github.com/yihuanghuan/LLM-UAVswarm-performance.git`.

| Source tag | Commit | Repository-relative artifact |
|---|---|---|
| E5-V1-REGISTRY | `33538b91ab9e0c53b918cdc0e47e3b7fa6f08592` | `experiments_v2/Formal Evaluation Experiments/E5/e5_end_to_end_registry_v1.yaml` |
| E5-V1-ANALYSIS | `511192273a61f97e2742a1cc6608e18ed960cc1f` | `experiments_v2/Formal Evaluation Experiments/formal_analysis_results_v1/E5/summary.md`, `summary.json`, `scenario_summary.csv`, `per_attempt_scored.csv`, `limitations.md` |
| E5-V2-COMPLETION | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_formal_campaign_completion_audit.json` |
| E5-V2-REPORT | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/report/E5_v2_formal_analysis_report.md` |
| E5-V2-OVERALL | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_overall_summary.csv` |
| E5-V2-A-TABLE | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_A_scenario_summary.csv` |
| E5-V2-B-TABLE | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_B_cell_summary.csv` |
| E5-V2-RESOLVED | `bc760d5795ff87c62df6e86875d9a906cc449e2d` | `experiments_v2/Formal Evaluation Experiments/E5_v2/analysis_v1/outputs/E5_v2_resolved_values.csv` |
| E5-V2-MAPPING | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_remaining_endpoint_mapping_audit.json` |
| E5-V2-ADJUDICATION | `558def6238826460cb3f9323af445e8c299fb610` | `experiments_v2/Formal Evaluation Experiments/E5_v2/E5_v2_endpoint_availability_adjudication_v1.json` |

The E5-v2 final analysis branch is `formal/E5-v2-analysis-v1`; its completed formal source is `formal/E5-v2-design-v1` at the completion commit above. Source file SHA-256 identities used for this report are retained in the accompanying preservation audit.

| Execution or recovery scope | Tooling bundle SHA-256 |
|---|---|
| Slot 1 original physical execution v1 | `422d82b593ba927dffaee3c14bcf8b6996304a8ae302cdc525ab3c525b786ecb` |
| Slot 1 transaction recovery | `29eb7421d2095ba88e60df0ed224ad035348b534cb57877a32d967bd933027bb` |
| Slots 2–60 physical execution v2 | `2800b1a4540ffde75573f5ea7bf580b415302d5c4d86f0ab86898c69f7b02572` |
'''

def sha(data):
    return hashlib.sha256(data).hexdigest()

def git_bytes(commit, path):
    return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=ROOT)

def write_json(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

def verify_e5_table_transcription():
    """Compare presentation rows to frozen aggregate CSVs; never read attempts."""
    def rows(filename):
        return list(csv.DictReader(io.StringIO(git_bytes(V2_ANALYSIS,
            E5+'E5_v2/analysis_v1/outputs/'+filename).decode())))
    checked = 0
    endpoints = ['actual_d_min','tracking_rmse','final_error','completion_time']
    for filename, is_a in [('E5_v2_A_scenario_summary.csv',True), ('E5_v2_B_cell_summary.csv',False)]:
        table = rows(filename)
        for stratum in dict.fromkeys(r['stratum_value'] for r in table):
            cell = {r['endpoint']:r for r in table if r['stratum_value']==stratum}
            success = cell['mission_success']
            label = stratum.replace('E5V2-', '', 1).replace('-', ' — ', 1) if is_a else stratum
            expected = '| '+label+' | '+success['numerator']+'/'+success['denominator']+' | '
            expected += ' | '.join(f"{float(cell[e]['mean']):.3f}" for e in endpoints)+' |'
            assert expected in EN_APPEND, ('Frozen table transcription', expected)
            checked += 1
    names = {'actual_d_min':'actual d_min','tracking_rmse':'Tracking RMSE',
             'final_error':'Final error','completion_time':'Completion time',
             'T_LLM':'T_LLM','T_mission_execution':'T_mission_execution'}
    for row in rows('E5_v2_overall_summary.csv'):
        if row['kind'] != 'continuous':
            continue
        expected = '| '+names[row['endpoint']]+' | '+row['available_n']+' | '
        expected += ' | '.join(f"{float(row[c]):.3f}" for c in ['mean','median','sample_sd','iqr'])
        expected += f" | [{float(row['min']):.3f}, {float(row['max']):.3f}] | {row['unit']} |"
        assert expected in EN_APPEND, ('Frozen overall transcription', expected)
        checked += 1
    return checked

def audit():
    source = SOURCE.read_bytes()
    assert source == git_bytes(SOURCE_COMMIT, SOURCE.relative_to(ROOT).as_posix())
    en, zh = EN.read_bytes(), ZH.read_bytes()
    assert en == source + EN_APPEND.encode(), 'English must be exact source plus frozen append template'
    elines, zlines = en.decode().splitlines(), zh.decode().splitlines()
    assert len(elines) == len(zlines), (len(elines), len(zlines))
    sections = {}
    bounds = [('E1', b'# E1 \xe2\x80\x94', b'# E2 \xe2\x80\x94'),
              ('E2', b'# E2 \xe2\x80\x94', b'# E3-v4 \xe2\x80\x94'),
              ('E3', b'# E3-v4 \xe2\x80\x94', b'# E4A \xe2\x80\x94'),
              ('E4', b'# E4A \xe2\x80\x94', b'# Cross-Experiment Claim Matrix')]
    for name, start, end in bounds:
        a, b = source.index(start), source.index(end)
        original, final = source[a:b], en[en.index(start):en.index(end)]
        assert original == final
        sections[name] = dict(start_byte=a, end_byte_exclusive=b,
            start_line=source[:a].count(b'\n') + 1, end_line_inclusive=source[:b].count(b'\n'),
            original_section_sha256=sha(original), final_english_section_sha256=sha(final), identical=True)
    # Per-aligned-line and per-table-cell token multisets allow grammatical
    # reordering, while preserving exact precision, signs, and multiplicity.
    token = re.compile(r'(?<![A-Za-z0-9_])[+−-]\d+(?:[,\.]\d+)*|\d+(?:[,\.]\d+)*')
    denom = re.compile(r'\d+/\d+')
    units = re.compile(r"(?<![A-Za-z_'])\b(?:pair-seconds|pair-s|m/s²|m/s|ms|m|s)(?![A-Za-z_])")
    percentages = re.compile(r'\d+(?:\.\d+)?%')
    hashes = re.compile(r'\b[a-f0-9]{40}(?:[a-f0-9]{24})?\b')
    mismatches = []
    for i, (e, z) in enumerate(zip(elines, zlines), 1):
        for label, pattern in [('numeric', token), ('denominator', denom), ('unit', units),
                               ('percentage', percentages), ('hash', hashes)]:
            if Counter(pattern.findall(e)) != Counter(pattern.findall(z)):
                mismatches.append(dict(line=i, kind=label, en=pattern.findall(e), zh=pattern.findall(z)))
        assert (len(e) - len(e.lstrip('#'))) == (len(z) - len(z.lstrip('#'))), f'Heading level {i}'
        if e.startswith('|'):
            assert z.startswith('|') and e.count('|') == z.count('|'), f'Table structure {i}'
            for j, (ec, zc) in enumerate(zip(e.split('|'), z.split('|'))):
                if Counter(token.findall(ec)) != Counter(token.findall(zc)):
                    mismatches.append(dict(line=i, cell=j, kind='table_numeric', en=ec, zh=zc))
    if mismatches:
        print(json.dumps(mismatches, ensure_ascii=False, indent=2))
        raise SystemExit('Bilingual mismatches: audit not published')
    for text in (en.decode(), zh.decode()):
        assert not re.search(r'N\s*=?\s*(20|24|28|32)\b|D1/D2/D3|large-swarm-infra|grid-layout', text)
    sources = [(V1_RAW, E5+'E5/e5_end_to_end_registry_v1.yaml'),
               *[(V1_ANALYSIS, E5+'formal_analysis_results_v1/E5/'+p) for p in ('summary.md','summary.json','scenario_summary.csv','per_attempt_scored.csv','limitations.md')],
               *[(V2_SOURCE, E5+'E5_v2/'+p) for p in ('E5_v2_formal_campaign_completion_audit.json','E5_v2_remaining_endpoint_mapping_audit.json','E5_v2_endpoint_availability_adjudication_v1.json')],
               *[(V2_ANALYSIS, E5+'E5_v2/analysis_v1/'+p) for p in ('report/E5_v2_formal_analysis_report.md','outputs/E5_v2_overall_summary.csv','outputs/E5_v2_A_scenario_summary.csv','outputs/E5_v2_B_cell_summary.csv','outputs/E5_v2_resolved_values.csv','outputs/E5_v2_substudy_summary.csv','outputs/E5_v2_endpoint_availability.csv')]]
    source_records = [dict(commit=c, path=p, sha256=sha(git_bytes(c,p))) for c,p in sources]
    preservation = dict(status='PASS', source_branch=SOURCE_BRANCH, source_commit=SOURCE_COMMIT,
        source_report_path=SOURCE.relative_to(ROOT).as_posix(), source_report_sha256=sha(source),
        final_english_report_sha256=sha(en), original_full_report_is_exact_prefix=True,
        original_full_report_bytes=len(source), sections=sections,
        E4_range_includes=['E4A','E4B','E4 Combined Evidence for Bounded Behavioral Grounding'],
        E1_E4_scientific_numbers_recomputed=False, E1_E4_scientific_interpretation_modified=False,
        E5_sources=source_records)
    bilingual = dict(status='PASS', english_report=EN.name, chinese_report=ZH.name,
        english_sha256=sha(en), chinese_sha256=sha(zh), aligned_lines=len(elines),
        numeric_mismatches=0, denominator_mismatches=0, metric_unit_mismatches=0,
        hash_mismatches=0, percentage_mismatches=0, claim_boundary_mismatches=0,
        frozen_E5_table_rows_transcription_checked=verify_e5_table_transcription(),
        numerical_check='Exact per-aligned-line and per-table-cell numeric token multisets; signs, precision and repeated values retained',
        structure_check='Same aligned line count, heading levels and table cell counts',
        claim_review_method='Author review of aligned translations, not automated semantic equivalence proof',
        reviewed_boundaries=['E1 valid finite dataset versus incomplete invalid/format rejection',
            'E2 paired timing mechanism, not universal optimality',
            'E3 complete-block and missingness semantics; no safety/independence guarantee; burden unavailable',
            'E4A partial directional support; E4B observed authority, not formal guarantee',
            'E5 integration only, no new causal C1/C2/C3 support',
            'E5-v1 valid boundary and frontend evidence retained; no v1/v2 pooling or improvement-rate comparison',
            'E5-v2 J_hard and five latency components unavailable; no proxy or imputation',
            'Tested N=8/12/16 only; no causal-N, scalability, universal reliability or collision-free guarantee'],
        E5_v1_v2_denominators_pooled=False, supplementary_diagnostics_included=False,
        E5_v2_J_hard_analyzed=False, new_statistical_analysis=False)
    write_json('experiment_report_E1_E4_preservation_audit.json', preservation)
    write_json('experiment_report_bilingual_consistency_audit.json', bilingual)
    print(json.dumps(dict(status='PASS', source_sha256=sha(source), lines=len(elines), sections=sections), indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--replay', action='store_true', help='Build/audit twice; require byte-identical reports and audits')
    args = parser.parse_args()
    if args.replay:
        products = [EN, ZH, HERE/'experiment_report_E1_E4_preservation_audit.json',
                    HERE/'experiment_report_bilingual_consistency_audit.json']
        EN.write_bytes(SOURCE.read_bytes() + EN_APPEND.encode())
        audit()
        first = {p.name:p.read_bytes() for p in products}
        EN.write_bytes(SOURCE.read_bytes() + EN_APPEND.encode())
        audit()
        assert first == {p.name:p.read_bytes() for p in products}, 'Replay mismatch'
        print('DETERMINISTIC_REPORT_REPLAY = PASS')
    elif args.generate:
        EN.write_bytes(SOURCE.read_bytes() + EN_APPEND.encode())
    else:
        audit()
