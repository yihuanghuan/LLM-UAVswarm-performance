from e4b_trial_registry import *
def validate_authority(spec):
 vals=deterministic_policy_values(); sid=spec['scenario_id']; checks=[]
 def add(pid,status,evidence): checks.append({'predicate_id':pid,'status':status,'evidence':evidence})
 add('feasible_explicit_T_style_override','PASS' if sid!='E4B-FEASIBLE-EXPLICIT-T' or abs(spec['expected_T_exec_s']-4.0)<=TOLERANCE else 'FAIL',{'expected_T_exec_s':spec['expected_T_exec_s']})
 add('infeasible_T_or_vaj_bypass','PASS' if sid!='E4B-INFEASIBLE-EXPLICIT-T' or (spec['expected_T_exec_s']+TOLERANCE>=spec['T_min_s'] and abs(vals['T_min_s']-spec['T_min_s'])<=TOLERANCE) else 'FAIL',{'production_policy_T_min_s':vals['T_min_s']})
 expected=vals['auto_T_exec_s'].get(spec['style']); add('auto_T_below_T_min','PASS' if sid!='E4B-AUTO-T' or (spec['expected_T_exec_s']+TOLERANCE>=spec['T_min_s'] and abs(expected-spec['expected_T_exec_s'])<=TOLERANCE) else 'FAIL',{'production_policy_expected_T_exec_s':expected})
 add('style_safety_override','SCHEMA_VALIDATED',spec['safety_contract'])
 limits=spec['frozen_motion_limits']; clamps=spec['controller_hard_clamps']; ok=(limits=={'velocity_mps':5.0,'acceleration_mps2':5.0,'jerk_mps3':10.0} and clamps['velocity_max']==5.0 and clamps['acceleration_max']==5.0 and clamps['jerk_max']==10.0); add('profile_or_clamp_exceeded','PASS' if ok else 'FAIL',{'limits':limits,'clamps':clamps})
 add('priority_above_style_changed','SCHEMA_VALIDATED',{'hierarchy':spec['authority_hierarchy']})
 if {x['predicate_id'] for x in checks}!={p['id'] for p in PREDICATES}: raise E4BError('predicate coverage mismatch')
 return checks
def validate_artifact(a):
 if a.get('dataset_class')!='synthetic_validation' or a.get('accepted_formal_result') is not False or a.get('result_notice')!='NOT_FORMAL_RESULT': raise E4BError('bad labels')
 if a['mock_execution'].get('scientific_outcomes') is not None: raise E4BError('physical/scientific outcomes forbidden')
 checks=validate_authority(a['execution_spec'])
 if any(x['status']=='FAIL' for x in checks): raise E4BError('deterministic authority check failed')
 return checks

