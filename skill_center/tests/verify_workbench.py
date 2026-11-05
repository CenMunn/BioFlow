"""Opt-in real-worker integration acceptance against an isolated initialized storage."""
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend import main,db,workbench

CHECKS=[]


def check(name):CHECKS.append(name);print('PASS',name,flush=True)


def wait(client,job):
    for _ in range(250):
        value=client.get('/api/v1/workbench/runs/'+job['id']).json()
        if value['status'] not in {'queued','running'}:return value
        time.sleep(.3)
    raise AssertionError('Task timeout: '+job['id'])


def main_check():
    prefix='/api/v1/workbench';root=workbench.area()
    credentials=(db.ROOT/'initial-access.txt').read_text(encoding='utf-8')
    username=re.search('用户名：([^\r\n]+)',credentials)[1];password=re.search('密码：([^\r\n]+)',credentials)[1]
    with TestClient(main.app) as client:
        assert client.get(prefix+'/algorithms').status_code==401
        assert client.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==200
        entries=client.get(prefix+'/algorithms').json()['items'];builtins=[e for e in entries if e['origin']=='builtin']
        assert len(builtins)==10 and sum(bool(e['active_version']) for e in builtins)==3
        check('10 existing algorithms listed; exactly three builtin implementations enabled')
        response=client.post(prefix+'/datasets',files={'file':('matrix.csv',(root/'examples/matrix.csv').read_bytes())})
        assert response.status_code==201,response.text
        dataset=response.json();assert dataset['rows']==24
        check('Dataset preview exposes row/column types and source hash')
        sample={'sample_column':'sample_id','group_column':'group','features':['feature_1','feature_2','feature_3','feature_4']}
        jobs={}
        for name in ['pca','kmeans','random_forest']:
            entry=next(e for e in builtins if e['name']==name);selection=sample.copy()
            if name=='random_forest':selection['group_column']='';selection['target_column']='group'
            r=client.post(prefix+'/runs',json={'kind':'algorithm','algorithm_id':entry['id'],'dataset_id':dataset['id'],'selection':selection,'params':entry['active_version']['defaults']})
            assert r.status_code==202,r.text
            run=wait(client,r.json());assert run['status']=='succeeded',run
            assert run['algorithm_version_id']==entry['active_version_id']
            assert {'figure.png','figure.svg','figure.pdf','provenance.json'}<={f['name'] for f in run['files']}
            artifact=client.get(prefix+'/runs/'+run['id']+'/files/figure.png?download=false');assert artifact.content.startswith(b'\x89PNG')
            archive=client.get(prefix+'/runs/'+run['id']+'/export');z=zipfile.ZipFile(io.BytesIO(archive.content))
            provenance=json.loads(z.read('provenance.json'));assert provenance['dataset_sha256']==dataset['sha256'] and provenance['source_hash']
            assert 'source_root' not in provenance
            jobs[name]=run;check(name+' complete run, figure, tables and provenance ZIP')
        pca=jobs['pca'];original_hashes={f['name']:f['sha256'] for f in pca['files']}
        r=client.post(prefix+'/runs/'+pca['id']+'/replot',json={'template_id':'scatter','plot_options':{'palette':'blue','title':'Replot without recomputing'}})
        redraw=wait(client,r.json());assert redraw['status']=='succeeded' and redraw['parent_run_id']==pca['id']
        assert {f['name']:f['sha256'] for f in client.get(prefix+'/runs/'+pca['id']).json()['files']}==original_hashes
        check('Independent replot reuses original results and leaves original artifacts unchanged')
        for item in client.get(prefix+'/plots').json()['items']:
            data=client.post(prefix+'/datasets',files={'file':(item['example']+'.csv',(root/'examples'/(item['example']+'.csv')).read_bytes())}).json()
            response=client.post(prefix+'/runs',json={'kind':'plot','dataset_id':data['id'],'template_id':item['id'],'selection':item['mapping']})
            assert response.status_code==202,response.text
            run=wait(client,response.json());assert run['status']=='succeeded',run
            check('Portable plot template: '+item['id'])
        entry=next(e for e in builtins if e['name']=='pca');old=entry['active_version_id']
        v=client.post(prefix+'/algorithms/'+entry['id']+'/versions',json={'defaults':{'n_components':3,'random_state':42},'change_note':'Acceptance version test'}).json()
        assert client.post(prefix+f'/algorithms/{entry["id"]}/versions/{v["id"]}/publish',json={}).status_code==400
        job=client.post(prefix+f'/algorithms/{entry["id"]}/versions/{v["id"]}/validate',json={}).json();assert wait(client,job)['status']=='succeeded'
        assert client.post(prefix+f'/algorithms/{entry["id"]}/versions/{v["id"]}/publish',json={'expected_active_version_id':old}).status_code==200
        assert client.post(prefix+f'/algorithms/{entry["id"]}/versions/{old}/publish',json={'expected_active_version_id':old}).status_code==409
        assert client.post(prefix+f'/algorithms/{entry["id"]}/versions/{old}/publish',json={'expected_active_version_id':v['id']}).status_code==200
        assert client.get(prefix+'/runs/'+pca['id']).json()['algorithm_version_id']==old
        check('Pending version cannot publish; validation, release, conflict check and rollback preserve historical runs')
        before=client.get(prefix+'/algorithms/'+entry['id']).json()
        r=client.patch(prefix+'/algorithms/'+entry['id'],json={'display_name':'PCA 主成分分析','updated_at':before['updated_at']});assert r.status_code==200
        assert client.patch(prefix+'/algorithms/'+entry['id'],json={'display_name':'Stale','updated_at':before['updated_at']}).status_code==409
        check('Metadata edit uses optimistic concurrency')
        package=(root/'examples/algorithm-package.zip').read_bytes()
        existing=next((e for e in entries if e['name']=='variance-ranking'),None)
        data={'algorithm_id':existing['id']} if existing else {}
        r=client.post(prefix+'/algorithm-packages',data=data,files={'file':('algorithm.zip',package)})
        assert r.status_code==201,r.text
        plugin=r.json();v=plugin['new_version'];assert v['validation_status']=='pending'
        assert plugin['enabled']==(existing['enabled'] if existing else False)
        assert plugin['active_version_id']==(existing['active_version_id'] if existing else None)
        job=client.post(prefix+f'/algorithms/{plugin["id"]}/versions/{v["id"]}/validate',json={}).json();assert wait(client,job)['status']=='succeeded'
        assert client.post(prefix+f'/algorithms/{plugin["id"]}/versions/{v["id"]}/publish',json={}).status_code==200
        r=client.post(prefix+'/runs',json={'kind':'algorithm','algorithm_id':plugin['id'],'dataset_id':dataset['id'],'selection':sample,'params':{'top_k':2}})
        assert r.status_code==202,r.text
        assert wait(client,r.json())['status']=='succeeded'
        check('New source package imports without execution, validates, publishes and runs through the same interface')
        assert client.post(prefix+'/datasets',files={'file':('bad.csv',b'sample_id,a,a\nS1,1,2\n')}).status_code==422
        dataset_zero=client.post(prefix+'/datasets',files={'file':('zeros.csv',b'sample_id,A,B\nS1,0,0\nS2,1,2\n')}).json()
        r=client.post(prefix+'/runs',json={'kind':'plot','dataset_id':dataset_zero['id'],'template_id':'stacked','selection':{'sample_column':'sample_id','features':['A','B']}})
        assert wait(client,r.json())['status']=='failed'
        r=client.post(prefix+'/runs',json={'kind':'algorithm','algorithm_id':entry['id'],'dataset_id':dataset['id'],'selection':sample,'params':{'n_components':99,'random_state':42}})
        assert r.status_code==400
        catalog_only=next(e for e in builtins if e['name']=='umap')
        assert client.post(prefix+f'/algorithms/{catalog_only["id"]}/versions/{catalog_only["versions"][0]["id"]}/validate',json={}).status_code==400
        check('Duplicate columns, invalid parameters, zero-total abundance and unsupported algorithm execution fail explicitly')
        assert client.get(prefix+'/runs/'+pca['id']+'/files/not-in-manifest.csv').status_code==404
        assert client.get(prefix+'/runs/'+pca['id']+'/files/input_values.csv?download=false').json()['rows']
        check('Only manifested result files are downloadable; bounded table preview works')
        client.post('/api/v1/auth/logout',json={})
    output={'passed':True,'checks':CHECKS,'algorithms':len(db.all_rows('algorithms')),'run_count':len(db.all_rows('runs'))}
    (PROJECT/'test-results/workbench-20261027/api-acceptance.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    print(json.dumps(output,ensure_ascii=False),flush=True)


PROJECT=Path(__file__).resolve().parents[1]
if __name__=='__main__':main_check()
