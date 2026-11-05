"""Explicit, isolated live-network acceptance; never imports into production."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
os.environ['SC_STORAGE']=str(PROJECT/'test-results'/'github-storage')
sys.path.insert(0,str(PROJECT))
from backend import main,db
from fastapi.testclient import TestClient

salt='00'*16
main.AUTH_FILE.write_text(json.dumps({'username':'verify','salt':salt,'password_hash':main.password_hash('verification-only',salt)}))
report={}
with TestClient(main.app) as client:
    assert client.post('/api/v1/auth/login',json={'username':'verify','password':'verification-only'}).status_code==200
    response=client.post('/api/v1/imports/github/preview',json={'url':'https://github.com/vercel-labs/skills/tree/main/skills/find-skills'})
    assert response.status_code==202,response.text
    jid=response.json()['id']
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        job=client.get('/api/v1/imports/'+jid).json()
        if job['status'] in {'ready','failed','cancelled'}: break
        time.sleep(1)
    report['preview']={k:job.get(k) for k in ['id','status','source','error','error_code']}
    assert job['status']=='ready',job
    entry=job['candidates'][0]['entry_path']
    response=client.post('/api/v1/imports/'+jid+'/commit',json={'entries':[entry],'support_paths':[]})
    assert response.status_code==200,response.text
    result=response.json()['items'][0]; report['commit']=result
    sid,rid=result['skill_id'],result['revision_id']
    rev=client.get(f'/api/v1/skills/{sid}/revisions/{rid}').json()
    report['revision']={k:rev[k] for k in ['id','entry_path','content_hash','diagnostics','files']}
    report['usage']=client.get(f'/api/v1/skills/{sid}/usage-options').json()
    report['source_links']=client.get(f'/api/v1/skills/{sid}').json()['source_links']
    original=main.safe(db.revision_root(rev),entry).read_bytes()
    assert original==main.safe(main.job_root(jid),entry).read_bytes()
    source_id=client.get('/api/v1/skills/'+sid).json()['source_id']
    update=client.post(f'/api/v1/sources/{source_id}/check-update',json={}).json()
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        update=client.get('/api/v1/imports/'+update['id']).json()
        if update['status'] in {'ready','failed'}: break
        time.sleep(1)
    assert update['status']=='ready',update
    diff=client.get(f'/api/v1/sources/{source_id}/diff',params={'import_job_id':update['id']})
    assert diff.status_code==200,diff.text
    report['update_diff']=diff.json()
    duplicate=client.post('/api/v1/imports/'+update['id']+'/commit',json={'entries':[entry],'support_paths':[]})
    assert duplicate.status_code==200 and duplicate.json()['items'][0]['skipped']
    report['duplicate_update']=duplicate.json()
    report['passed']=True
path=PROJECT/'test-results'/'live-github.json';path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('LIVE_GITHUB_OK',rev['content_hash'],len(rev['files']))
