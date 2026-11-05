"""Import user-selected public snapshots. Reads files only; executes no repository code.

Input: a reviewed plan containing immutable commit IDs and Git tree manifests.
Only --commit saves verified candidates as skills; source preview jobs remain traceable.
"""
import argparse
import concurrent.futures
import hashlib
import json
import posixpath
import re
import shutil
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from backend import db,main,packages,sources
from fastapi.testclient import TestClient


def digest_git(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def download_file(client,repo,commit,node,root):
    p=packages.safe(root,node['path'])
    if p.is_file() and digest_git(p.read_bytes())==node['sha']: return node['path']
    if node.get('mode') not in {'100644','100755'}: raise ValueError('Unsupported link or special file: '+node['path'])
    if node.get('size',0)>packages.MAX_UPLOAD: raise ValueError('File exceeds limit: '+node['path'])
    url=f"https://raw.githubusercontent.com/{repo}/{commit}/{quote(node['path'],safe='/')}"
    content=[];total=0
    for attempt in range(3):
        try:
            with client.stream('GET',url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    total+=len(chunk)
                    if total>packages.MAX_UPLOAD: raise ValueError('Download size exceeded')
                    content.append(chunk)
            break
        except httpx.HTTPError:
            content=[];total=0
            if attempt==2: raise
            time.sleep(1+attempt)
    data=b''.join(content)
    if digest_git(data)!=node['sha']: raise ValueError('Git blob hash mismatch: '+node['path'])
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(data)
    return node['path']


def prepare_repo(inventory,items,cache):
    repo=inventory['repository'];commit=inventory['commit_sha']
    if not re.fullmatch('[0-9a-f]{40}',commit) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo): raise ValueError('Invalid pinned source')
    all_nodes={n['path']:n for n in inventory['tree'] if n['type']=='blob'}
    root=cache/repo.replace('/','__')/commit/'bundle';root.mkdir(parents=True,exist_ok=True)
    prefixes={str(PurePosixPath(x['entry_path']).parent) for x in items}
    supports={p for x in items for p in x.get('shared_paths',[])}
    licenses=set(inventory.get('license_files',[]))
    def wanted(path): return path in licenses or any(p=='.' or path==p or path.startswith(p+'/') for p in prefixes|supports)
    nodes=[n for path,n in all_nodes.items() if wanted(path)]
    print('PREPARING',repo,len(nodes),'files',flush=True)
    if len(nodes)>packages.MAX_FILES or sum(n.get('size',0) for n in nodes)>packages.MAX_EXTRACT: raise ValueError('Selected bundle exceeds configured limits')
    archive_file=root.parent/'repository.zip'
    cache_complete=all(packages.safe(root,n['path']).is_file() and digest_git(packages.safe(root,n['path']).read_bytes())==n['sha'] for n in nodes)
    if not cache_complete and not archive_file.exists():
        owner,name=repo.split('/')
        archive_file.write_bytes(sources.download({'owner':owner,'repo':name,'commit_sha':commit}))
    # Extract exactly the selected complete directories and licenses, without unrelated
    # application files. Every saved byte is checked against the fixed Git tree.
    archive=archive_file.read_bytes() if archive_file.exists() else None
    if not cache_complete: packages.extract_zip(archive,root,True,{n['path'] for n in nodes})
    for node in nodes:
        file=packages.safe(root,node['path'])
        if not file.is_file() or digest_git(file.read_bytes())!=node['sha']: raise ValueError('Snapshot file hash mismatch: '+node['path'])
    with httpx.Client(timeout=httpx.Timeout(20,read=30),follow_redirects=False,headers={'User-Agent':'BioFlow-verified-skill-import'}) as client:
        # Resolve explicit relative cross-directory references against the fixed tree.
        # Existing chosen skill folders are complete; sibling support is recorded separately.
        for _ in range(3):
            missing=set()
            for item in items:
                d=packages.diagnose(root,item['entry_path'])
                missing.update(p for p in d['missing_paths'] if p in all_nodes and not packages.safe(root,p).exists())
                text=packages.safe(root,item['entry_path']).read_bytes().decode('utf-8-sig','replace')
                for ref in re.findall(r'(?:\.\./)+[^\s`<>\[\]()"\']+',text):
                    path=posixpath.normpath(posixpath.join(str(PurePosixPath(item['entry_path']).parent),ref.rstrip('.,:;')))
                    if path in all_nodes and not path.startswith('../') and not packages.safe(root,path).exists(): missing.add(path)
            if not missing: break
            if archive is not None: packages.extract_zip(archive,root,True,missing)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                    list(pool.map(lambda p:download_file(client,repo,commit,all_nodes[p],root),missing))
            for p in missing:
                if digest_git(packages.safe(root,p).read_bytes())!=all_nodes[p]['sha']: raise ValueError('Support file hash mismatch: '+p)
            supports.update(missing)
    # Bundle cache is exclusively for this reviewed repository snapshot.
    packages.files(root)
    for f in packages.files(root):
        if f['path'] not in all_nodes or digest_git(packages.safe(root,f['path']).read_bytes())!=all_nodes[f['path']]['sha']: raise ValueError('Cached support file hash mismatch: '+f['path'])
        if not wanted(f['path']): supports.add(f['path'])
    return root,sorted(supports)


def execute(plan_path,commit,normalize=False):
    plan=json.loads(Path(plan_path).read_text(encoding='utf-8'))
    inventories={r['repository']:r for r in plan['inventories']}
    groups={}
    for item in plan['skills']: groups.setdefault(item['repository'],[]).append(item)
    work=db.ROOT/'source-verification-20261014';work.mkdir(exist_ok=True)
    report_path=work/'import-report.json'
    report={'date':'2026-10-14','requested_entries':len(plan['skills']),'committed':commit,'repositories':[],'external_tools':plan.get('external_tools',[])}
    credentials=(db.ROOT/'initial-access.txt').read_text(encoding='utf-8')
    username=re.search(r'用户名：([^\r\n]+)',credentials)[1]
    password=re.search(r'密码：([^\r\n]+)',credentials)[1]
    with TestClient(main.app) as client:
        assert client.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==200
        for repo,items in groups.items():
            record={'repository':repo,'entries':[]}
            try:
                inventory=inventories[repo]
                root,supports=prepare_repo(inventory,items,work/'packages')
                support_declarations={p for item in items for p in item.get('shared_paths',[])}|{p for p in supports if PurePosixPath(p).name=='SKILL.md'}
                job=main.new_job('github',{'url':'https://github.com/'+repo,'ref':inventory['ref'],'support_only_paths':sorted(support_declarations)})
                target=main.job_root(job['id']);target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(root,target)
                owner,name=repo.split('/')
                source={'repository_url':'https://github.com/'+repo,'owner':owner,'repo':name,'ref':inventory['ref'],'commit_sha':inventory['commit_sha'],'requested_path':'','license':inventory.get('license'),'snapshot_method':'Git tree and raw files at fixed commit, verified against Git blob SHA-1'}
                main.candidates_finish(job,source)
                ready=client.get('/api/v1/imports/'+job['id']).json()
                record.update(import_job_id=job['id'],commit_sha=inventory['commit_sha'],support_paths=supports)
                prefix=(ready.get('source') or {}).get('package_prefix')
                chosen=[];mapping={}
                for item in items:
                    entry=(prefix+'/' if prefix else '')+item['entry_path']
                    c=next((c for c in ready['candidates'] if c['entry_path']==entry),None)
                    if c is None: raise ValueError('Selected candidate missing: '+entry)
                    diagnosis=c['diagnostics']
                    result={'entry_path':entry,'upstream_entry_path':item['entry_path'],'skill_name':c['skill_name'],'diagnostics':diagnosis,'applicable_modules':item['applicable_modules'],'category':item['category']}
                    if diagnosis['errors']:
                        result['status']='format_needs_repair'
                    else:
                        result['status']='verified'
                    if not diagnosis['errors'] or normalize:
                        chosen.append(entry);mapping[entry]=(item,result)
                    record['entries'].append(result)
                if commit and chosen:
                    selected_supports=[(prefix+'/' if prefix else '')+p for p in supports]
                    response=client.post('/api/v1/imports/'+job['id']+'/commit',json={'entries':chosen,'support_paths':selected_supports,'applicable_modules':[]})
                    if response.status_code!=200: raise ValueError(response.text)
                    for entry,value in zip(chosen,response.json()['items']):
                        item,result=mapping[entry]
                        sid=value['skill_id']
                        current=client.get('/api/v1/skills/'+sid).json()
                        payload={'applicable_modules':list(dict.fromkeys(current.get('applicable_modules',[])+item['applicable_modules'])),'category':item['category'],'tags':list(dict.fromkeys(current.get('tags',[])+['用户选定来源']))}
                        if item.get('display_name'): payload['display_name']=item['display_name']
                        if item.get('display_summary'): payload['display_summary']=item['display_summary']
                        response=client.patch('/api/v1/skills/'+sid,json=payload)
                        if response.status_code!=200: raise ValueError(response.text)
                        result.update(status='already_imported' if value.get('skipped') else 'imported',skill_id=sid,revision_id=value['revision_id'])
                        if normalize and result['diagnostics']['errors']:
                            from backend.normalization import normalize_copy
                            result.update(normalize_copy(client,sid,value['revision_id'],item['applicable_modules'],item['category'],item.get('display_summary')))
                            result['status']='normalized_copy'
                print(json.dumps({'repository':repo,'verified':len(chosen),'deferred':len(items)-len(chosen),'files':len(ready['files'])},ensure_ascii=False),flush=True)
            except Exception as e:
                record['error']=str(e)[:1500]
                print(json.dumps({'repository':repo,'error':record['error']},ensure_ascii=False),flush=True)
            report['repositories'].append(record)
            report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        client.post('/api/v1/auth/logout',json={})
    report['catalog']=main.modules_catalog()
    report['completed_at']=db.now()
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('IMPORT_REVIEW_COMPLETE',json.dumps(report['catalog'],ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('plan');p.add_argument('--commit',action='store_true');p.add_argument('--normalize-copies',action='store_true');args=p.parse_args()
    execute(args.plan,args.commit,args.normalize_copies)
