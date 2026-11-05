import concurrent.futures
import json
import re
import subprocess
from pathlib import Path
import httpx

ROOT=Path('/home/xh/BioFLow/skill_center/storage/source-verification-20261014')
ROOT.mkdir(parents=True,exist_ok=True)
rows=json.loads((ROOT/'requested-rows.json').read_text())
extra=['https://github.com/Yuan1z0825/nature-skills','https://github.com/GPTomics/bioSkills','https://github.com/jihe520/sci-box','https://github.com/LigphiDonk/academic-figure-generator']
repos=sorted({ '/'.join(x['url'].split('/')[3:5]) for x in rows } | { '/'.join(u.split('/')[3:5]) for u in extra })

def check(repo):
    out={'repository':repo}
    dest=ROOT/(repo.replace('/','__')+'.json')
    if dest.exists():
        cached=json.loads(dest.read_text())
        if not cached.get('error'): return cached
    try:
        with httpx.Client(timeout=45,follow_redirects=False,headers={'User-Agent':'BioFlow-source-verification'}) as c:
            metadata=c.get('https://api.github.com/repos/'+repo);metadata.raise_for_status();info=metadata.json()
            branch=info['default_branch']
            response=c.get('https://api.github.com/repos/'+repo+'/commits/'+branch);response.raise_for_status();commit=response.json()['sha']
            out.update(commit_sha=commit,ref=branch,license=(info.get('license') or {}).get('spdx_id'))
            response=c.get(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1');response.raise_for_status();tree=response.json()
        if tree.get('truncated'): raise ValueError('GitHub tree truncated; not a complete inventory')
        out['tree']=tree.get('tree',[])
        out['entries']=[n['path'] for n in out['tree'] if n['type']=='blob' and n['path'].endswith('/SKILL.md') or (n['type']=='blob' and n['path']=='SKILL.md')]
        out['license_files']=[n['path'] for n in out['tree'] if '/' not in n['path'] and n['path'].lower().startswith(('license','copying','notice'))]
    except Exception as e: out['error']=str(e)
    dest.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({k:out[k] for k in ('repository','commit_sha','ref','entries','error') if k in out},ensure_ascii=False),flush=True)
    return out

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    values=list(pool.map(check,repos))
(ROOT/'inventory.json').write_text(json.dumps(values,ensure_ascii=False,indent=2))
print('INVENTORY_DONE',len(values),flush=True)
