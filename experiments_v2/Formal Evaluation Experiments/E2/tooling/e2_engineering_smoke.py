#!/usr/bin/env python3
"""Run one non-registered real frozen E2 wrapper/resolver smoke."""
from __future__ import annotations
from copy import deepcopy
import argparse,json
from pathlib import Path
from e2_common import POLICY_PATH,ensure_runtime_import_paths,canonical_sha256,write_json_exclusive
ensure_runtime_import_paths()
from e2_commitment_wrapper import build_commitment_pair
from location_allocate.lfs_types import StateSnapshot,UAVState
from location_allocate.late_resolution import resolve_execution_task
from location_allocate.policy_adapter import load_runtime_policy

FIXTURE="ENG-E2-OFFLINE-WRAPPER-v1"
def snapshot(epoch,shift=0.0):
 return StateSnapshot(epoch=epoch,states={i:UAVState(position=(-6.0+3.0*i+shift,20.0,3.0),receive_timestamp=epoch,velocity=(0.0,0.0,0.0),source_timestamp=epoch,timestamp_source='source_time') for i in (1,2,3,4)},warnings=())
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists(): raise SystemExit('output exists')
 a.output.mkdir(parents=True)
 candidate={'task_id':9901,'U':[1,2,3,4],'F':{'type':'Line'},'c':{'mode':'relative','reference':'current_swarm_centroid','offset':[2.5,-1.0,0.5],'frame':'world'},'r':{'mode':'qualitative','value':'spacious'},'T':{'mode':'auto'},'m':'smooth','s':1.25,'q':{'mode':'direct'}}
 before=deepcopy(candidate); policy=load_runtime_policy(POLICY_PATH)[1]
 pair=build_commitment_pair(candidate,snapshot(900.0),policy)
 early=resolve_execution_task(deepcopy(pair.early_candidate),snapshot(902.0,0.25),policy)
 late=resolve_execution_task(deepcopy(pair.late_candidate),snapshot(902.0,0.25),policy)
 evidence={'manifest_type':'E2_live_engineering_smoke_v1','fixture_id':FIXTURE,
  'fixture_registered_formal_trial':False,'dataset_class':'engineering_validation',
  'accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','scientific_interpretation':None,
  'candidate_not_mutated':candidate==before,'wrapper_real_backend':True,
  'resolver_real_backend':True,'early_trace_hash':canonical_sha256(early.trace),
  'late_trace_hash':canonical_sha256(late.trace),'commitment_fields':['c','r','T'],
  'invariant_fields_equal':all(pair.early_candidate[k]==pair.late_candidate[k] for k in ('task_id','U','F','m','s','q'))}
 evidence['status']='PASS' if all(evidence[k] for k in ('candidate_not_mutated','wrapper_real_backend','resolver_real_backend','invariant_fields_equal')) else 'FAIL'
 write_json_exclusive(a.output/'smoke_manifest.json',evidence); print(json.dumps(evidence,sort_keys=True)); return evidence['status']!='PASS'
if __name__=='__main__': raise SystemExit(main())
