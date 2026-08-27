from __future__ import annotations
import fcntl,hashlib,json,os
from pathlib import Path
from e4a_trial_registry import E4AError,canonical
ZERO='0'*64
def write_json(path,value):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); data=json.dumps(value,sort_keys=True,indent=2).encode()+b'\n'; fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
 with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
 d=os.open(path.parent,os.O_RDONLY); os.fsync(d); os.close(d)
class Journal:
 def __init__(self,p): self.path=Path(p); self.path.mkdir(parents=True,exist_ok=True); self.lock=self.path/'.append.lock'
 def read(self):
  out=[]; prev=ZERO
  for n,p in enumerate(sorted(self.path.glob('*-attempt.json')),1):
   if p.name!=f'{n:06d}-attempt.json': raise E4AError('journal gap')
   r=json.loads(p.read_text()); b=dict(r); got=b.pop('record_hash',None); want=hashlib.sha256(canonical(b)).hexdigest()
   if r.get('sequence')!=n or r.get('previous_record_hash')!=prev or got!=want: raise E4AError('journal chain mismatch')
   out.append(r); prev=got
  return out
 def append(self,payload):
  with self.lock.open('a+b') as l:
   fcntl.flock(l.fileno(),fcntl.LOCK_EX); rs=self.read(); n=len(rs)+1; r={'sequence':n,'previous_record_hash':rs[-1]['record_hash'] if rs else ZERO,**payload}; r['record_hash']=hashlib.sha256(canonical(r)).hexdigest(); write_json(self.path/f'{n:06d}-attempt.json',r); return r

