#!/usr/bin/env python3
import hashlib,json,subprocess
from e5_trial_registry import *
SOURCE='36dba68c6b16681ec98500b49c5a83095de4b634'; BASELINE_TAG='paper-final-sim-v3'; BASELINE='6cf402debf23851b1eff3edc6f3ab49eae7127c4'; BRANCHES={'formal/E5-end-to-end-v1','formal/E5-formal-adapter-v1'}
PRODUCTION=['location_allocate/location_allocate/paper_candidate_parser.py','location_allocate/location_allocate/prompt_loader.py','location_allocate/location_allocate/paper_runtime.py','location_allocate/location_allocate/late_resolution.py','location_allocate/location_allocate/safety_aware_allocator.py','location_allocate/location_allocate/candidate_dispatch.py','location_allocate/prompts/paper_candidate_en_v2_system.txt','location_allocate/prompts/paper_candidate_en_v2_fewshot.json','schemas/paper_candidate_schema_v2.json','lfs_policy/config/lfs_policy.paper_current.yaml']
def git(*a,binary=False): return subprocess.run(['git',*a],cwd=REPO_ROOT,check=True,capture_output=True,text=not binary).stdout
def validate():
 cs=[]
 def ck(n,o,d): cs.append({'check':n,'status':'PASS' if o else 'FAIL','details':d})
 try:
  head=git('rev-parse','HEAD').strip(); branch=git('branch','--show-current').strip(); ck('ancestry',subprocess.run(['git','merge-base','--is-ancestor',SOURCE,'HEAD'],cwd=REPO_ROOT).returncode==0,head); ck('branch',branch in BRANCHES,branch); ck('baseline',git('rev-parse',f'{BASELINE_TAG}^{{}}').strip()==BASELINE,BASELINE); load_registry(); registered_trial_ids(); ck('sealed_hashes',True,{'protocol':PROTOCOL_SHA256,'registry':REGISTRY_SHA256,'global':GLOBAL_REGISTRY_SHA256,'order':ORDER_SHA256,'policy':POLICY_SHA256,'llm_manifest':LLM_MANIFEST_SHA256}); ds={}; ok=True
  for rel in PRODUCTION:
   b=(REPO_ROOT/rel).read_bytes(); same=b==git('show',f'{SOURCE}:{rel}',binary=True); ok&=same; ds[rel]={'sha256':hashlib.sha256(b).hexdigest(),'byte_identical':same}
  ck('production_prompt_schema_byte_identical',ok,ds); changed=git('diff','--name-only',SOURCE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines(); bad=[p for p in changed if not p.startswith('experiments_v2/Formal Evaluation Experiments/E5/')]; ck('experiment_only_changes',not bad,bad)
 except Exception as e: ck('internal_error',False,str(e)); head='UNKNOWN'
 return {'manifest_type':'E5_provenance_v1','status':'PASS' if all(c['status']=='PASS' for c in cs) else 'FAIL','runner_branch':branch if 'branch' in locals() else 'UNKNOWN','runner_commit':head,'checks':cs}
if __name__=='__main__': r=validate(); print(json.dumps(r,indent=2)); raise SystemExit(r['status']!='PASS')
