"""Load the five real pinned adapter entrypoints from their exact worktrees."""
from __future__ import annotations
import importlib.util,os,subprocess,sys
from pathlib import Path
from campaign_common import CampaignError,REPO_ROOT,sha256_file
from runner_registry import load_runner_registry,validate_registry_pins
DEFAULT_CHECKOUTS={'E2':'e2_adapter_worktree','E3':'e3_adapter_worktree','E4A':'e4a_adapter_worktree','E4B':'e4b_adapter_worktree','E5':'e5_adapter_worktree'}
class PinnedAdapterLoader:
 def __init__(self,registry=None,checkout_roots=None):
  self.registry=registry or load_runner_registry();self.checkout_roots=checkout_roots or {};self.modules={}
  pins=validate_registry_pins(self.registry)
  if pins['status']!='PASS':raise CampaignError('runner registry pin verification failed')
 def checkout(self,family):return Path(self.checkout_roots.get(family,os.environ.get(f'FORMAL_{family}_ADAPTER_CHECKOUT',REPO_ROOT.parent/DEFAULT_CHECKOUTS[family]))).resolve()
 def _load(self,family):
  if family in self.modules:return self.modules[family]
  e=self.registry['runners'][family];root=self.checkout(family)
  if not root.is_dir():raise CampaignError(f'{family} adapter checkout missing: {root}')
  head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();branch=subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()
  if head!=e['adapter_commit'] or branch!=e['adapter_branch']:raise CampaignError(f'{family} checkout branch/commit mismatch')
  source=root/e['adapter_entrypoint']
  if not source.is_file() or sha256_file(source)!=e['adapter_source_sha256']:raise CampaignError(f'{family} checkout source hash mismatch')
  tooling=source.parent.as_posix()
  if tooling not in sys.path:sys.path.insert(0,tooling)
  name=f'pinned_formal_adapter_{family.lower()}';spec=importlib.util.spec_from_file_location(name,source)
  if spec is None or spec.loader is None:raise CampaignError(f'cannot load {family} adapter')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  if not callable(getattr(module,'run_exact_trial',None)):raise CampaignError(f'{family} adapter contract missing')
  self.modules[family]=module;return module
 def verify_all_checkouts(self):
  details={}
  for family in self.registry['required_families']:
   module=self._load(family);identity=(getattr(module,'identity',None) or getattr(module,'adapter_identity'))();pin=self.registry['runners'][family];ok=identity['commit']==pin['adapter_commit'] and identity['branch']==pin['adapter_branch'] and identity['source_sha256']==pin['adapter_source_sha256'];details[family]={'status':'PASS' if ok else 'FAIL','identity':identity,'checkout':str(self.checkout(family))}
  return {'status':'PASS' if all(x['status']=='PASS' for x in details.values()) else 'FAIL','families':details}
 def run_exact_trial(self,family,trial_id,context):return self._load(family).run_exact_trial(trial_id,context)
