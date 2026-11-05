"""Read-only verification of the reviewed import, original snapshots and forks."""
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db,main,packages

work=db.ROOT/'source-verification-20261014'
report=json.loads((work/'import-report.json').read_text())
plan=json.loads((work/'import-plan.json').read_text())
trees={r['repository']:{n['path']:n['sha'] for n in r['tree'] if n['type']=='blob'} for r in plan['inventories']}
original_files=0;normalized=0;expected=set()
for repo in report['repositories']:
    assert not repo.get('error'),repo
    job=db.get('imports',repo['import_job_id'])
    prefix=job.get('source',{}).get('package_prefix','')
    for item in repo['entries']:
        sid=item.get('original_skill_id',item['skill_id'])
        rid=item.get('original_revision_id',item['revision_id'])
        original=db.get('revisions',rid);root=db.revision_root(original)
        expected.add(sid);expected.add(item['skill_id'])
        for f in original['files']:
            data=packages.safe(root,f['path']).read_bytes()
            path=f['path'][len(prefix)+1:] if prefix else f['path']
            digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            assert digest==trees[repo['repository']][path],(repo['repository'],path)
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            original_files+=1
        skill=db.get('skills',item['skill_id']);rev=db.get('revisions',item['revision_id'])
        assert skill['published_revision_id']==rev['id'] and skill['enabled']
        assert skill['applicable_modules']==item['applicable_modules']
        assert not rev['diagnostics']['errors'],item
        if item['status']=='normalized_copy':
            normalized+=1;parent=db.get('skills',sid)
            assert not parent['enabled'] and parent['applicable_modules']==[] and not parent['published_revision_id']
            assert skill['parent_skill_id']==sid and skill['parent_revision_id']==rid
            child_root=db.revision_root(rev)
            raw_body=packages.metadata(packages.safe(root,original['entry_path']).read_bytes())[1]
            assert packages.metadata(packages.safe(child_root,rev['entry_path']).read_bytes())[1]==raw_body
            old=str(PurePosixPath(original['entry_path']).parent);new=str(PurePosixPath(rev['entry_path']).parent)
            for f in original['files']:
                if f['path']==original['entry_path']:continue
                dest=new+f['path'][len(old):] if f['path'].startswith(old+'/') else f['path']
                assert packages.safe(root,f['path']).read_bytes()==packages.safe(child_root,dest).read_bytes()
skills=db.all_rows('skills')
assert {s['id'] for s in skills}==expected
assert len(skills)==74 and sum(bool(s['published_revision_id']) for s in skills)==63
assert all(s['execution_state']=='unverified' for s in skills)
result={'passed':True,'skills':len(skills),'published':63,'normalized_copies':normalized,'original_files_verified':original_files,'catalog':main.modules_catalog(),'execution_state':'unverified'}
(Path(__file__).resolve().parents[1]/'test-results'/'import-snapshot-20261014.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
