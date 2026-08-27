#!/usr/bin/env python3
"""Fail-closed E5 formal-capable exact-trial adapter."""
from __future__ import annotations
import json,os,subprocess
from pathlib import Path
from e5_trial_registry import *
BRANCH='formal/E5-formal-adapter-v1';CONTRACT_BRANCH='formal/E5-end-to-end-v1';CONTRACT_COMMIT='016e5ee573a52a704f6a890e1177b4bab9d489cb';PREFLIGHT='36dba68c6b16681ec98500b49c5a83095de4b634';BASELINE_TAG='paper-final-sim-v3';BASELINE='6cf402debf23851b1eff3edc6f3ab49eae7127c4';ENTRYPOINT='experiments_v2/Formal Evaluation Experiments/E5/tooling/e5_formal_adapter.py'
class FormalAdapterError(E5Error):pass
def identity():return {'branch':subprocess.check_output(['git','branch','--show-current'],cwd=REPO_ROOT,text=True).strip(),'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO_ROOT,text=True).strip(),'entrypoint':ENTRYPOINT,'source_sha256':sha256_file(__file__)}
def _validate(t,c):
 s=build_exact_spec(t);order=ORDER_PATH.read_text().splitlines();pos=order.index(t)+1;i=identity();checks={'trial':c.get('trial_id')==t,'position':c.get('global_trial_position')==pos,'commit':c.get('runner_commit')==i['commit'],'source':c.get('runner_source_sha256')==i['source_sha256'],'policy':c.get('policy_sha256')==POLICY_SHA256,'protocol':c.get('protocol_sha256')==PROTOCOL_SHA256,'registry':c.get('registry_sha256')==REGISTRY_SHA256,'order':c.get('global_trial_order_sha256')==ORDER_SHA256}
 if not all(checks.values()):raise FormalAdapterError(f'context mismatch: {checks}')
 mode=c.get('execution_mode')
 if mode=='formal':
  if not(c.get('dataset_class')=='formal_evaluation' and c.get('formal_launch_authorized') is True and c.get('launch_gate_status')=='READY_FOR_FORMAL_LAUNCH'):raise FormalAdapterError('formal gate/authorization required')
 elif mode=='spec_rehearsal':
  if c.get('dataset_class') not in {'synthetic_validation','engineering_validation'} or c.get('formal_launch_authorized') is not False:raise FormalAdapterError('nonformal rehearsal context required')
 else:raise FormalAdapterError('unsupported mode')
 return s,pos,i,mode
def _write(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():raise FormalAdapterError('duplicate retained attempt')
 data=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode();tmp=path.with_name(path.name+f'.tmp-{os.getpid()}');fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path);d=os.open(path.parent,os.O_DIRECTORY);os.fsync(d);os.close(d)
def run_exact_trial(t,c):
 s,pos,i,mode=_validate(t,c);root=Path(c['attempt_output_dir']).resolve()
 if root.exists():raise FormalAdapterError('duplicate retained attempt directory')
 root.mkdir(parents=True);(root/'raw').mkdir();accepted=mode=='formal';status='success';backend={'backend':'E5_pinned_adapter_spec_rehearsal_v1','physical_execution_performed':False,'llm_called':False,'scientific_outcomes':None,'exact_command_utf8_sha256':s['exact_command_utf8_sha256'],'mission_graph':s['mission_graph']}
 if mode=='formal':
  try:
   from e5_formal_backend import execute_registered_trial
   backend=execute_registered_trial(s,root/'raw');status=backend.get('attempt_status','success')
  except Exception as e:status='infrastructure_failure';backend={'error':f'{type(e).__name__}: {e}'}
 if c.get('failure_injection') and not accepted:status=str(c['failure_injection'])
 a={'record_type':'E5_formal_capable_attempt_v1','dataset_class':'formal_evaluation' if accepted else c['dataset_class'],'accepted_formal_result':accepted,'result_notice':None if accepted else 'NOT_FORMAL_RESULT','trial_id':t,'experiment':'E5','global_trial_position':pos,'attempt_status':status,'replacement_attempt':False,'execution_mode':mode,'execution_spec':s,'backend_result':backend,'adapter':i,'provenance':{'preflight_commit':PREFLIGHT,'baseline_tag':BASELINE_TAG,'baseline_commit':BASELINE,'policy_sha256':POLICY_SHA256,'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'global_trial_order_sha256':ORDER_SHA256,'llm_runtime_manifest_sha256':LLM_MANIFEST_SHA256}}
 p=root/'attempt.json';_write(p,a);return {'trial_id':t,'experiment':'E5','attempt_status':status,'artifact_path':str(p),'artifact_sha256':sha256_file(p),'dataset_class':a['dataset_class'],'accepted_formal_result':accepted,'runner_commit':i['commit'],'runner_source_sha256':i['source_sha256'],'suite_journal_mutated':False}
