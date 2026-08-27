from e4a_trial_registry import E4AError
PRIMARY={'settling_time','control_effort','acceleration_response','tracking_RMSE'}
def validate_artifact(a):
 if a.get('dataset_class')!='synthetic_validation' or a.get('accepted_formal_result') is not False or a.get('result_notice')!='NOT_FORMAL_RESULT': raise E4AError('bad synthetic labels')
 if a['mock_execution'].get('scientific_outcomes') is not None: raise E4AError('scientific endpoints forbidden')
 if set(a['execution_spec']['metric_log_schema']['primary_metrics'])!=PRIMARY: raise E4AError('metric schema mismatch')
 return {'validation_status':'SPEC_VALIDATED','scientific_interpretation':None}

