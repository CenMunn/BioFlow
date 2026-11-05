"""Fast boundary tests; scientific acceptance is opt-in verify_workbench.py."""
import hashlib
import io
import json
import zipfile

from fastapi.testclient import TestClient
import pytest

from backend import db,main,workbench


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'ROOT',tmp_path/'storage');db.ROOT.mkdir()
    monkeypatch.setattr(db,'DB',db.ROOT/'center.sqlite');db.migrate()
    monkeypatch.setattr(main,'AUTH_FILE',db.ROOT/'admin.json')
    salt='00'*16
    main.AUTH_FILE.write_text(json.dumps({'username':'test','salt':salt,'password_hash':main.password_hash('test-password',salt)}))
    main.ATTEMPTS.clear()
    with TestClient(main.app) as client:
        assert client.post('/api/v1/auth/login',json={'username':'test','password':'test-password'}).status_code==200
        yield client


def seed():
    entry={'id':db.uid(),'name':'pca','display_name':'PCA','description':'Test description','category':'降维','origin':'builtin','enabled':True,'active_version_id':None,'updated_at':db.now(),'created_at':db.now()}
    schema={'n_components':{'type':'integer','default':2,'min':2,'max':20}}
    version=workbench.create_version(entry,{'name':'pca','engine':'pca','parameters':schema,'source_root':'/source/snapshot/bioflow_ml','source_hash':'a'*64,'task':'clustering','upstream_version':'0.1.0'},{},'initial')
    version.update(validation_status='passed',published_at=db.now());db.put('algorithm_versions',version)
    entry['active_version_id']=version['id'];db.put('algorithms',entry)
    return entry,version


def test_parameter_values_are_bounded_and_boolean_is_not_integer():
    schema={'n':{'type':'integer','default':2,'min':2,'max':10}}
    for value in [True,1,11,2.5,'2']:
        with pytest.raises(workbench.packages.Fault):workbench.parameters(schema,{'n':value})
    with pytest.raises(workbench.packages.Fault):workbench.parameters(schema,{'hidden':1})
    assert workbench.parameters(schema,{})=={'n':2}


def test_version_publish_requires_successful_validation_and_does_not_mutate_old_defaults(client):
    entry,old=seed();path='/api/v1/workbench/algorithms/'+entry['id']
    v=client.post(path+'/versions',json={'defaults':{'n_components':3},'change_note':'new'}).json()
    assert client.post(path+'/versions/'+v['id']+'/publish',json={}).status_code==400
    assert db.get('algorithm_versions',old['id'])['defaults']=={'n_components':2}
    assert db.get('algorithms',entry['id'])['active_version_id']==old['id']


def test_source_import_never_executes_uploaded_python(client,tmp_path):
    seed();marker=tmp_path/'should-not-exist'
    manifest={'name':'new-method','task':'feature_selection','description':'New method','entrypoint':'algorithm.py:NewMethod','parameters':{}}
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('algorithm.json',json.dumps(manifest))
        z.writestr('algorithm.py',f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n')
    response=client.post('/api/v1/workbench/algorithm-packages',files={'file':('new.zip',stream.getvalue())})
    assert response.status_code==201,response.text
    assert response.json()['new_version']['validation_status']=='pending'
    assert not response.json()['enabled'] and not marker.exists()


def test_source_zip_traversal_rejected_without_database_registration(client,tmp_path):
    seed();before=len(db.all_rows('algorithms'));stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('../outside.py','bad')
    r=client.post('/api/v1/workbench/algorithm-packages',files={'file':('bad.zip',stream.getvalue())})
    assert r.status_code==400 and len(db.all_rows('algorithms'))==before


def test_cancel_and_restart_recovery_keep_terminal_runs_intact(client):
    entry,v=seed();pending={'id':db.uid(),'status':'queued','algorithm_version_id':v['id'],'validation':True};complete={'id':db.uid(),'status':'succeeded'}
    db.put('runs',pending);db.put('runs',complete)
    assert client.post('/api/v1/workbench/runs/'+pending['id']+'/cancel',json={}).json()['status']=='cancelled'
    pending.update(status='running');db.put('runs',pending);v['validation_status']='running';db.put('algorithm_versions',v)
    workbench.recover()
    assert db.get('runs',pending['id'])['status']=='interrupted'
    assert db.get('algorithm_versions',v['id'])['validation_status']=='pending'
    assert db.get('runs',complete['id'])['status']=='succeeded'


def test_result_download_requires_manifest_membership(client):
    key=db.uid();folder=workbench.area()/'runs'/key/'output';folder.mkdir(parents=True)
    (folder/'private.json').write_text('secret')
    db.put('runs',{'id':key,'status':'succeeded','files':[]})
    assert client.get('/api/v1/workbench/runs/'+key+'/files/private.json').status_code==404


def test_metadata_conflict_and_dataset_file_type_fail_without_worker(client):
    entry,v=seed();path='/api/v1/workbench/algorithms/'+entry['id']
    first=client.patch(path,json={'display_name':'PCA new','updated_at':entry['updated_at']})
    assert first.status_code==200
    assert client.patch(path,json={'display_name':'stale','updated_at':entry['updated_at']}).status_code==409
    assert client.post('/api/v1/workbench/datasets',files={'file':('model.pkl',b'not-data')}).status_code==400


def test_archive_hides_algorithm_blocks_new_work_and_preserves_history(client):
    entry,v=seed();path='/api/v1/workbench/algorithms/'+entry['id']
    job={'id':db.uid(),'status':'succeeded','algorithm_id':entry['id'],'algorithm_version_id':v['id'],'files':[{'name':'result.csv'}]}
    db.put('runs',job);folder=workbench.job_path(job)/'output';folder.mkdir(parents=True);(folder/'result.csv').write_text('value\n1\n')
    dataset={'id':db.uid(),'filename':'test.csv','sha256':'b'*64,'canonical_sha256':'c'*64};db.put('datasets',dataset)
    archived=client.post(path+'/archive',json={'updated_at':entry['updated_at']}).json()
    assert archived['archived_at'] and not archived['enabled']
    assert client.get('/api/v1/workbench/algorithms').json()['items']==[]
    assert client.get('/api/v1/workbench/algorithms?archived=true').json()['items'][0]['id']==entry['id']
    assert client.get(path).status_code==200
    for suffix,payload in [('/versions',{}),('/versions/'+v['id']+'/validate',{}),('/versions/'+v['id']+'/publish',{})]:
        assert client.post(path+suffix,json=payload).status_code==409
    assert client.patch(path,json={'enabled':True}).status_code==409
    assert client.post('/api/v1/workbench/algorithms',json={'name':'derived','display_name':'derived','base_algorithm_id':entry['id']}).status_code==409
    assert client.post('/api/v1/workbench/runs',json={'algorithm_id':entry['id'],'dataset_id':dataset['id']}).status_code==409
    assert db.get('algorithm_versions',v['id'])==v and db.get('runs',job['id'])==job
    assert client.get('/api/v1/workbench/runs/'+job['id']+'/files/result.csv').text=='value\n1\n'
    restored=client.post(path+'/archive',json={'archived':False,'updated_at':archived['updated_at']}).json()
    assert not restored['archived_at'] and restored['enabled'] and restored['active_version_id']==v['id']
    assert len(client.get('/api/v1/workbench/algorithms').json()['items'])==1


def test_archive_checks_conflicts_and_restores_previous_disabled_state(client):
    entry,v=seed();entry['enabled']=False;db.put('algorithms',entry);path='/api/v1/workbench/algorithms/'+entry['id']
    assert client.post(path+'/archive',json={'archived':'false'}).status_code==400
    assert client.post(path+'/archive',json={'updated_at':'stale'}).status_code==409
    archived=client.post(path+'/archive',json={}).json()
    repeated=client.post(path+'/archive',json={}).json()
    assert archived==repeated
    assert client.post(path+'/archive',json={'archived':False,'updated_at':entry['updated_at']}).status_code==409
    restored=client.post(path+'/archive',json={'archived':False}).json()
    assert not restored['enabled'] and not restored['archived_at']
