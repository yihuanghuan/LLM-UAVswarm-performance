from e5_trial_registry import E5Error
PRIMARY={'all_attempt_mission_success','tracking_RMSE','final_error','actual_d_min','iapf_burden','latency_decomposition'}; LAT={'LLM_inference','parse_validation','snapshot_wait','resolution','allocation','dispatch','physical_execution'}
def validate_artifact(a):
 if a.get('dataset_class')!='synthetic_validation' or a.get('accepted_formal_result') is not False or a.get('result_notice')!='NOT_FORMAL_RESULT': raise E5Error('bad labels')
 if a['mock_execution'].get('scientific_outcomes') is not None or a['mock_execution'].get('llm_called'): raise E5Error('LLM/scientific execution forbidden')
 s=a['execution_spec']; schema=s['metric_log_schema']
 if set(schema['primary_metrics'])!=PRIMARY or set(schema['latency_components'])!=LAT: raise E5Error('metric/latency schema mismatch')
 if s['candidate_semantic_ground_truth']['usage']!='audit_and_scoring_only_not_runtime_input' or s['frozen_language_runtime']['candidate_gt_used_as_input']: raise E5Error('Candidate GT input substitution forbidden')
 return {'validation_status':'SPEC_VALIDATED','scientific_interpretation':None}

