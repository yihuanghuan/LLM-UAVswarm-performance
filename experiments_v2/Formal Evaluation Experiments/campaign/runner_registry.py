"""Pinned formal adapter registry and fail-closed launch gate."""
from __future__ import annotations
import hashlib,json,subprocess
from typing import Any,Dict,List,Tuple
from campaign_common import CampaignError,FAMILIES,REPO_ROOT,RUNNER_REGISTRY_PATH,canonical_sha256,load_json
REQUIRED_STATUS={'contract_validation_status':'READY','spec_validation_status':'PASS','live_smoke_status':'PASS','formal_adapter_status':'READY'}
def _git(*args,binary=False):return subprocess.run(['git',*args],cwd=REPO_ROOT,check=True,capture_output=True,text=not binary).stdout
def _blob(commit,path):return _git('show',f'{commit}:{path}',binary=True)
def load_runner_registry()->Dict[str,Any]:
 r=load_json(RUNNER_REGISTRY_PATH)
 if tuple(r.get('required_families',()))!=FAMILIES:raise CampaignError('runner registry required_families mismatch')
 if r.get('formal_campaign_status')!='READY_FOR_LAUNCH_GATE':raise CampaignError('registry is not READY_FOR_LAUNCH_GATE')
 runners=r.get('runners')
 if not isinstance(runners,dict) or set(runners)!=set(FAMILIES):raise CampaignError('registry must contain exactly five families')
 fields=('contract_branch','contract_commit','adapter_branch','adapter_commit','adapter_implementation_commit','adapter_entrypoint','adapter_source_sha256','adapter_manifest_path','adapter_manifest_sha256','protocol_path','protocol_sha256','registry_path','registry_sha256')
 for family,e in runners.items():
  if e.get('experiment')!=family or not all(e.get(x) for x in fields):raise CampaignError(f'incomplete pin for {family}')
  for key,value in REQUIRED_STATUS.items():
   if e.get(key)!=value:raise CampaignError(f'{family} {key} != {value}')
 return r
def validate_registry_pins(registry=None)->Dict[str,Any]:
 r=registry or load_runner_registry();checks=[]
 for family,e in r['runners'].items():
  try:
   branch_head=str(_git('rev-parse',e['adapter_branch'])).strip();contract_head=str(_git('rev-parse',e['contract_branch'])).strip();source=_blob(e['adapter_commit'],e['adapter_entrypoint']);manifest_bytes=_blob(e['adapter_commit'],e['adapter_manifest_path']);protocol=_blob(e['adapter_commit'],e['protocol_path']);registry_blob=_blob(e['adapter_commit'],e['registry_path']);manifest=json.loads(manifest_bytes)
   values={'adapter_branch_head':branch_head==e['adapter_commit'],'contract_branch_head':contract_head==e['contract_commit'],'adapter_source':hashlib.sha256(source).hexdigest()==e['adapter_source_sha256'],'adapter_manifest':hashlib.sha256(manifest_bytes).hexdigest()==e['adapter_manifest_sha256'],'protocol':hashlib.sha256(protocol).hexdigest()==e['protocol_sha256'],'registry':hashlib.sha256(registry_blob).hexdigest()==e['registry_sha256'],'manifest_status':manifest.get('validation_status')=='READY_FOR_GLOBAL_PIN','manifest_implementation_commit':manifest.get('adapter_commit')==e['adapter_implementation_commit'],'manifest_source':manifest.get('adapter_source_sha256')==e['adapter_source_sha256'],'manifest_smoke':manifest.get('live_engineering_smoke_status')=='PASS'}
  except Exception as x:values={'internal_error':False,'error':f'{type(x).__name__}: {x}'}
  checks.append({'family':family,'status':'PASS' if all(v is True for k,v in values.items() if k!='error') else 'FAIL','checks':values})
 return {'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','families':checks}
def formal_launch_gate(registry=None)->Tuple[bool,List[str]]:
 try:r=registry or load_runner_registry()
 except Exception as x:return False,[str(x)]
 pins=validate_registry_pins(r);blockers=[]
 if pins['status']!='PASS':blockers += [f"{x['family']} pin validation failed" for x in pins['families'] if x['status']!='PASS']
 if r.get('formal_campaign_status')!='READY_FOR_LAUNCH_GATE':blockers.append('registry status is not READY_FOR_LAUNCH_GATE')
 return not blockers,blockers
def registry_sha256(registry=None)->str:return canonical_sha256(registry or load_runner_registry())
