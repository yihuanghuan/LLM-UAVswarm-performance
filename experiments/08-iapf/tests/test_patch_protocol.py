from run_batch import protocol_arms, protocol_trials


def test_patch_protocol_has_27_pilot_and_230_formal_trials():
    assert len(protocol_arms()) == 27
    trials = protocol_trials()
    assert sum(trial.phase == "pilot" for trial in trials) == 27
    assert sum(trial.phase != "pilot" for trial in trials) == 230


def test_formal_pairs_reuse_identical_seeds():
    trials = [trial for trial in protocol_trials() if trial.phase != "pilot"]
    by_arm = {}
    for trial in trials:
        by_arm.setdefault((trial.family, trial.scenario), {}).setdefault(
            trial.method, set()).add(trial.seed)
    for family, scenarios in (
        ("nonintrusive", ["safe_wide_line_to_circle", "safe_parallel_groups"]),
        ("fallback", [
            "staggered_crossing_delay", "group_crossing_hold",
            "dense_local_bias"]),
        ("stress", [
            "head_on", "vertical", "grouped_reconfiguration",
            "dense_infeasible"]),
    ):
        for scenario in scenarios:
            seeds = list(by_arm[(family, scenario)].values())
            assert len(seeds) == 2
            assert seeds[0] == seeds[1]
