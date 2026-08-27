"""Schema-only E3 synthetic validator; no scientific endpoints are computed."""
from e3_trial_registry import E3Error

REQUIRED_METRICS={"actual_d_min","predicted_d_min","hard_risk_events","hard_risk_exposure_duration","mission_success","iapf_activation_time","integral_delta_p","integral_delta_a","trajectory_deviation"}

def validate_artifact(artifact):
    if artifact.get("dataset_class")!="synthetic_validation" or artifact.get("accepted_formal_result") is not False or artifact.get("result_notice")!="NOT_FORMAL_RESULT": raise E3Error("invalid synthetic labels")
    if artifact.get("mock_execution",{}).get("scientific_outcomes") is not None: raise E3Error("synthetic E3 artifact contains scientific outcomes")
    if set(artifact["execution_spec"]["metric_log_schema"]["primary_metrics"])!=REQUIRED_METRICS: raise E3Error("sealed metric schema mismatch")
    return {"validation_status":"SPEC_VALIDATED","scientific_interpretation":None}

