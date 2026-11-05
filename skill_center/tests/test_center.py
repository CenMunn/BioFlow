import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import db, main, packages, sources


def skill_md(name='test-skill', extra=''):
    return f'---\nname: {name}\ndescription: A reproducible test skill.\nmetadata:\n  custom: preserved\n{extra}---\n\n# Method\nRead [notes](references/notes.md).\n'.encode()


def zipped(content):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        for path,body in content.items(): archive.writestr(path,body)
    return stream.getvalue()


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'ROOT',tmp_path/'storage'); db.ROOT.mkdir()
    monkeypatch.setattr(db,'DB',db.ROOT/'center.sqlite'); db.migrate()
    monkeypatch.setattr(main,'AUTH_FILE',db.ROOT/'admin.json')
    salt='00'*16
    main.AUTH_FILE.write_text(json.dumps({'username':'tester','salt':salt,'password_hash':main.password_hash('test-password',salt)}))
    main.ATTEMPTS.clear()
    with TestClient(main.app) as c:
        assert c.post('/api/v1/auth/login',json={'username':'tester','password':'test-password'}).status_code==200
        yield c


def import_zip(client, content, entries=None, support=None):
    response=client.post('/api/v1/imports/upload/preview',files={'file':('bundle.zip',zipped(content),'application/zip')})
    assert response.status_code==201,response.text
    job=response.json()
    selected=entries or [job['candidates'][0]['entry_path']]
    committed=client.post('/api/v1/imports/'+job['id']+'/commit',json={'entries':selected,'support_paths':support or []})
    assert committed.status_code==200,committed.text
    return job,committed.json()['items'][0]


def create(client):
    response=client.post('/api/v1/skills',json={'skill_name':'new-skill','display_name':'科研技能','description':'用于测试方法。'})
    assert response.status_code==201,response.text
    return response.json()


def test_empty_auth_and_csrf(client):
    assert client.get('/api/v1/skills').json()['total']==0
    assert client.post('/api/v1/skills',json={},headers={'Origin':'https://evil.example'}).status_code==403
    client.post('/api/v1/auth/logout',json={})
    assert client.get('/api/v1/skills').status_code==401
    assert client.get('/api/v1/health').json()['scope']=='M0-M3'


def test_full_bundle_roundtrip_bytes_and_hash(client):
    original={'test-skill/SKILL.md':skill_md(),'test-skill/references/notes.md':'保留原文\r\n'.encode(),'test-skill/assets/binary.dat':b'\x00\xff\x04','LICENSE':b'MIT\n'}
    job,item=import_zip(client,original)
    rev=client.get(f"/api/v1/skills/{item['skill_id']}/revisions/{item['revision_id']}").json()
    out=client.get(f"/api/v1/skills/{item['skill_id']}/export").content
    with zipfile.ZipFile(io.BytesIO(out)) as archive:
        for p,b in original.items(): assert archive.read(p)==b
        assert packages.EXPORT_MANIFEST in archive.namelist()
    again=client.post('/api/v1/imports/upload/preview',files={'file':('export.zip',out)})
    assert again.status_code==201
    root=main.job_root(again.json()['id'])
    assert packages.content_hash(packages.files(root))==rev['content_hash']
    repeated=client.post('/api/v1/imports/'+job['id']+'/commit',json={'entries':['test-skill/SKILL.md'],'support_paths':[]})
    assert repeated.json()['items'][0]['revision_id']==item['revision_id']


def test_duplicates_and_same_name_do_not_overwrite(client):
    bundle={'test-skill/SKILL.md':skill_md(),'test-skill/references/notes.md':b'A'}
    _,first=import_zip(client,bundle)
    _,second=import_zip(client,bundle)
    assert second['skipped'] and second['skill_id']==first['skill_id']
    bundle['test-skill/references/notes.md']=b'B'
    _,third=import_zip(client,bundle)
    assert not third['skipped'] and third['skill_id']!=first['skill_id']
    assert client.get('/api/v1/skills').json()['total']==2


def test_fork_readonly_conflict_publish_restore(client):
    _,parent=import_zip(client,{'test-skill/SKILL.md':skill_md(),'test-skill/references/notes.md':b'A'})
    sid=parent['skill_id']; rid=parent['revision_id']
    assert client.post(f'/api/v1/skills/{sid}/drafts',json={}).status_code==409
    fork=client.post(f'/api/v1/skills/{sid}/fork',json={}).json(); d=fork['draft']; child=fork['skill']['id']
    p=d['entry_path']; original=client.get(f'/api/v1/drafts/{d["id"]}/files',params={'path':p}).json()['content']
    changed=original.replace('test-skill','renamed-skill')+'\nA changed method.\n'
    update=client.patch(f'/api/v1/drafts/{d["id"]}/files',json={'draft_counter':1,'changes':[{'path':p,'content':changed}]})
    assert update.status_code==200,update.text
    next=update.json(); assert next['entry_path']=='renamed-skill/SKILL.md'
    assert any(f['path']=='renamed-skill/references/notes.md' for f in next['files'])
    assert client.patch(f'/api/v1/drafts/{d["id"]}/files',json={'draft_counter':1,'changes':[]}).status_code==409
    v1=client.post(f'/api/v1/drafts/{d["id"]}/publish',json={'draft_counter':2}).json()
    assert v1['status']=='published'
    assert client.get(f'/api/v1/skills/{sid}/revisions/{rid}/files',params={'path':p}).json()['content']==original
    d2=client.post(f'/api/v1/skills/{child}/drafts',json={}).json()
    client.patch(f'/api/v1/drafts/{d2["id"]}/files',json={'draft_counter':1,'changes':[{'path':d2['entry_path'],'content':changed+'\nVersion 2.\n'}]})
    v2=client.post(f'/api/v1/drafts/{d2["id"]}/publish',json={'draft_counter':2}).json()
    delta=client.get(f'/api/v1/skills/{child}/diff',params={'from_revision_id':v1['id'],'to_revision_id':v2['id']}).json()
    assert delta['changes'][0]['change']=='modified'
    v3=client.post(f'/api/v1/skills/{child}/restore',json={'revision_id':v1['id']}).json()
    assert v3['content_hash']==v1['content_hash'] and v3['id']!=v1['id'] and v3['platform_version']==3


def test_metadata_form_preserves_extensions(client):
    item=create(client); d=item['draft']; did=d['id']
    text=client.get(f'/api/v1/drafts/{did}/files',params={'path':d['entry_path']}).json()['content']
    text=text.replace('---\n\n','metadata:\n  custom: preserved\nallowed-tools: Read\n---\n\n',1)
    assert client.patch(f'/api/v1/drafts/{did}/files',json={'draft_counter':1,'changes':[{'path':d['entry_path'],'content':text}]}).status_code==200
    response=client.patch(f'/api/v1/drafts/{did}/files',json={'draft_counter':2,'metadata':{'description':'Changed description.'}})
    assert response.status_code==200
    parsed=response.json()['diagnostics']['metadata']
    assert parsed['metadata']['custom']=='preserved' and parsed['allowed-tools']=='Read'


def test_missing_reference_and_invalid_import_saved_for_reading(client):
    _,item=import_zip(client,{'test-skill/SKILL.md':b'# no YAML\nscripts/missing.py\n'})
    s=client.get('/api/v1/skills/'+item['skill_id']).json()
    assert s['content_status']=='draft' and not s['published_revision_id']
    assert s['diagnostics']['errors']
    _,valid=import_zip(client,{'test-skill/SKILL.md':skill_md()})
    rev=client.get(f'/api/v1/skills/{valid["skill_id"]}/revisions/{valid["revision_id"]}').json()
    assert rev['diagnostics']['resource_status']=='incomplete'
    assert not client.get(f'/api/v1/skills/{valid["skill_id"]}/usage-options').json()['server_trial']['available']


def test_multiskill_shared_selection(client):
    data={'a-skill/SKILL.md':skill_md('a-skill').replace(b'references/notes.md',b'../shared/notes.md'),'b-skill/SKILL.md':skill_md('b-skill'),'shared/notes.md':b'COMMON','LICENSE':b'MIT'}
    j,item=import_zip(client,data,['a-skill/SKILL.md'],['shared/notes.md'])
    assert len(j['candidates'])==2
    r=client.get(f'/api/v1/skills/{item["skill_id"]}/revisions/{item["revision_id"]}').json()
    assert r['diagnostics']['resource_status']=='complete'
    assert {f['path'] for f in r['files']}=={'a-skill/SKILL.md','shared/notes.md','LICENSE'}


def test_single_md_normalized(client):
    response=client.post('/api/v1/imports/upload/preview',files={'file':('SKILL.md',skill_md())})
    assert response.status_code==201
    assert response.json()['candidates'][0]['entry_path']=='test-skill/SKILL.md'


@pytest.mark.parametrize('path',['../outside','/etc/passwd','a/../../x','C:/windows','a\\b','a/../b'])
def test_unsafe_paths(path,tmp_path):
    with pytest.raises(packages.Fault): packages.safe(tmp_path,path)


def test_symlink_and_zip_bomb(client,tmp_path,monkeypatch):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        info=zipfile.ZipInfo('test-skill/escape'); info.create_system=3; info.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(info,'/etc/passwd')
    assert client.post('/api/v1/imports/upload/preview',files={'file':('bad.zip',stream.getvalue())}).status_code==400
    assert client.post('/api/v1/imports/upload/preview',files={'file':('bad.zip',zipped({'../escape':b'bad'}))}).status_code==400
    monkeypatch.setattr(packages,'MAX_EXTRACT',10)
    assert client.post('/api/v1/imports/upload/preview',files={'file':('huge.zip',zipped({'a.txt':b'X'*1000}))}).status_code==413


def test_filter_favorite_archive_usage(client):
    item=create(client); sid=item['skill']['id']; d=item['draft']
    r=client.post(f'/api/v1/drafts/{d["id"]}/publish',json={'draft_counter':1}).json()
    assert client.get(f'/api/v1/skills/{sid}/usage-options').json()['install_command'] is None
    client.put(f'/api/v1/skills/{sid}/favorite',json={'favorite':True})
    assert client.get('/api/v1/skills',params={'favorite':True,'q':'科研'}).json()['total']==1
    assert client.get('/api/v1/skills',params={'q':'unrelated'}).json()['total']==0
    client.post(f'/api/v1/skills/{sid}/archive',json={})
    assert client.get('/api/v1/skills').json()['total']==0
    assert client.get('/api/v1/skills',params={'content_status':'archived'}).json()['total']==1
    assert client.get(f'/api/v1/skills/{sid}/revisions/{r["id"]}').status_code==200
    snapshot=db.get('revisions',r['id'])
    client.post(f'/api/v1/skills/{sid}/archive',json={'archived':False})
    assert client.get('/api/v1/skills',params={'q':'科研'}).json()['total']==1
    assert client.get('/api/v1/skills',params={'content_status':'archived'}).json()['total']==0
    assert db.get('revisions',r['id'])==snapshot


def test_restart_persistence_and_interruption(client):
    item=create(client)
    j=main.new_job('github',{'url':'https://github.com/example/example'})
    j['status']='running'; db.put('imports',j)
    main.recover()
    assert db.get('imports',j['id'])['status']=='interrupted'
    assert client.get('/api/v1/skills/'+item['skill']['id']).status_code==200


def test_github_branch_with_slash_and_ssrf_rejection(monkeypatch):
    with pytest.raises(packages.Fault): sources.resolve('http://127.0.0.1/private')
    with pytest.raises(packages.Fault): sources.resolve('https://github.com.evil.example/a/b')
    def fake(url,*args,**kwargs):
        if url.endswith('/repos/owner/repo'): return {'default_branch':'main','private':False}
        if '/commits/feature%2Fbranch' in url and not url.endswith('SKILL.md'): return {'sha':'a'*40} if url.endswith('/feature%2Fbranch') else (_ for _ in ()).throw(packages.Fault('SOURCE_NOT_FOUND','missing',404))
        raise packages.Fault('SOURCE_NOT_FOUND','missing',404)
    monkeypatch.setattr(sources,'fetch',fake)
    result=sources.resolve('https://github.com/owner/repo/tree/feature/branch/my-skill')
    assert result['ref']=='feature/branch' and result['requested_path']=='my-skill'


def test_import_cancel_and_commit_conflict(client):
    j=main.new_job('github',{'url':'https://github.com/example/example'})
    assert client.post('/api/v1/imports/'+j['id']+'/cancel',json={}).json()['status']=='cancelled'
    assert not main.job_update(j['id'],status='ready')
    assert client.post('/api/v1/imports/'+j['id']+'/commit',json={'entries':['x/SKILL.md']}).status_code==409


def test_atomic_multiselect_rollback(client,monkeypatch):
    response=client.post('/api/v1/imports/upload/preview',files={'file':('two.zip',zipped({'a-skill/SKILL.md':skill_md('a-skill'),'b-skill/SKILL.md':skill_md('b-skill')}))})
    job=response.json(); original=main.snapshot
    def failing(*args,**kwargs):
        if args[2].startswith('b-skill'): raise packages.Fault('TEST_FAILURE','Artificial I/O failure.')
        return original(*args,**kwargs)
    monkeypatch.setattr(main,'snapshot',failing)
    result=client.post('/api/v1/imports/'+job['id']+'/commit',json={'entries':['a-skill/SKILL.md','b-skill/SKILL.md']})
    assert result.status_code==400
    assert client.get('/api/v1/skills').json()['total']==0
    assert client.get('/api/v1/imports/'+job['id']).json()['status']=='ready'


def test_root_source_links_point_to_actual_upstream():
    source={'repository_url':'https://github.com/owner/repo','ref':'main','commit_sha':'a'*40,'package_prefix':'root-skill'}
    links=sources.links(source,'root-skill/SKILL.md')
    assert links['imported']=='https://github.com/owner/repo/tree/'+'a'*40


def test_nonstring_yaml_and_aliases_saved_without_execution(client):
    raw=b'---\nname: [bad]\ndescription: {bad: value}\nother: 2020-01-01\n---\nBody\n'
    _,item=import_zip(client,{'invalid-skill/SKILL.md':raw})
    assert not item['published']
    assert client.get('/api/v1/skills/'+item['skill_id']).status_code==200
    aliases=b'---\nname: &a test-skill\ndescription: *a\n---\nBody'
    _,item=import_zip(client,{'test-skill/SKILL.md':aliases})
    assert not item['published']


def test_foreign_revision_and_download_paths_rejected(client):
    a=create(client); b=create(client)
    r=client.post(f'/api/v1/drafts/{a["draft"]["id"]}/publish',json={'draft_counter':1}).json()
    assert client.get(f'/api/v1/skills/{b["skill"]["id"]}/revisions/{r["id"]}').status_code==404
    assert client.get(f'/api/v1/skills/{a["skill"]["id"]}/revisions/{r["id"]}/files',params={'path':'../../admin.json'}).status_code==400


def test_multiple_business_modules_filter_and_counts(client):
    a=create(client); sid=a['skill']['id']
    assert client.patch('/api/v1/skills/'+sid,json={'applicable_modules':['writing','analysis','writing']}).status_code==200
    assert client.get('/api/v1/skills',params={'module':'writing'}).json()['total']==1
    assert client.get('/api/v1/skills',params={'module':'analysis','q':'科研'}).json()['total']==1
    assert client.get('/api/v1/modules').json()['total']==1
    assert [m['count'] for m in client.get('/api/v1/modules').json()['items']]==[1,1]
    client.post('/api/v1/skills/'+sid+'/archive',json={})
    assert [m['count'] for m in client.get('/api/v1/modules').json()['items']]==[0,0]
    assert client.get('/api/v1/skills',params={'module':'unknown'}).status_code==400
    assert client.patch('/api/v1/skills/'+sid,json={'applicable_modules':'writing'}).status_code==400


def test_fork_and_duplicate_import_preserve_module_assignment(client):
    j,item=import_zip(client,{'test-skill/SKILL.md':skill_md()})
    sid=item['skill_id']
    client.patch('/api/v1/skills/'+sid,json={'applicable_modules':['writing']})
    copy=client.post('/api/v1/skills/'+sid+'/fork',json={}).json()
    assert copy['skill']['applicable_modules']==['writing']
    new=client.post('/api/v1/imports/upload/preview',files={'file':('same.zip',zipped({'test-skill/SKILL.md':skill_md()}))}).json()
    result=client.post('/api/v1/imports/'+new['id']+'/commit',json={'entries':['test-skill/SKILL.md'],'applicable_modules':['analysis']})
    assert result.json()['items'][0]['skipped']
    assert client.get('/api/v1/skills/'+sid).json()['applicable_modules']==['writing','analysis']


def test_shared_support_entry_is_not_registered_as_a_skill(client):
    j=main.new_job('github',{'url':'https://github.com/example/repo','support_only_paths':['skills/shared']})
    root=main.job_root(j['id']); root.mkdir(parents=True)
    for p,text in {'skills/main-skill/SKILL.md':skill_md('main-skill').replace(b'references/notes.md',b'../shared/notes.md'),'skills/shared/SKILL.md':skill_md('shared'),'skills/shared/notes.md':b'SUPPORT'}.items():
        file=root/p;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(text)
    main.candidates_finish(j)
    ready=client.get('/api/v1/imports/'+j['id']).json()
    assert [c['entry_path'] for c in ready['candidates']]==['skills/main-skill/SKILL.md']
    result=client.post('/api/v1/imports/'+j['id']+'/commit',json={'entries':['skills/main-skill/SKILL.md'],'support_paths':['skills/shared'],'applicable_modules':['writing']})
    assert result.status_code==200,result.text
    assert client.get('/api/v1/skills').json()['total']==1
    r=client.get('/api/v1/skills/'+result.json()['items'][0]['skill_id']).json()
    assert r['diagnostics']['resource_status']=='complete'


def test_root_support_entry_does_not_rename_nested_candidate(client):
    j=main.new_job('github',{'url':'https://github.com/example/repo','support_only_paths':['SKILL.md']})
    root=main.job_root(j['id']);root.mkdir(parents=True)
    (root/'SKILL.md').write_text('---\nname: root-helper\ndescription: Shared helper.\n---\n',encoding='utf-8')
    (root/'skills'/'reviewer').mkdir(parents=True)
    (root/'skills'/'reviewer'/'SKILL.md').write_text('---\nname: reviewer\ndescription: Review papers.\n---\n[helper](../../SKILL.md)',encoding='utf-8')
    main.candidates_finish(j,{'repository_url':'https://github.com/example/repo','commit_sha':'a'*40})
    ready=client.get('/api/v1/imports/'+j['id']).json()
    assert [c['entry_path'] for c in ready['candidates']]==['skills/reviewer/SKILL.md']
    result=client.post('/api/v1/imports/'+j['id']+'/commit',json={'entries':['skills/reviewer/SKILL.md'],'support_paths':['SKILL.md'],'applicable_modules':['writing']})
    assert result.status_code==200,result.text


def test_scoped_repository_extraction_preserves_complete_selected_paths(tmp_path):
    data=zipped({'repo-commit/skill/SKILL.md':skill_md('skill'),'repo-commit/skill/references/notes.md':b'A','repo-commit/unrelated/a/b/c/d/e/f/g/h/deep.txt':b'IGNORE'})
    paths={'skill/SKILL.md','skill/references/notes.md'}
    packages.extract_zip(data,tmp_path,True,paths)
    assert {f['path'] for f in packages.files(tmp_path)}==paths
    assert (tmp_path/'skill/SKILL.md').read_bytes()==skill_md('skill')


def test_normalized_fork_preserves_original_body_and_resource_bytes(client):
    from backend.normalization import normalize_copy
    raw=b'---\nname: bio-test-skill\ndescription: Test original.\nmetadata:\n  priority: 3\nallowed-tools: [Read, Write]\n---\n\n# Body\nRead [notes](references/notes.md).\n'
    _,item=import_zip(client,{'test-skill/SKILL.md':raw,'test-skill/references/notes.md':b'ORIGINAL\r\n','LICENSE':b'License data'})
    result=normalize_copy(client,item['skill_id'],item['revision_id'],['analysis'],'生信分析')
    assert result['body_unchanged'] and result['resources_unchanged']
    parent=client.get('/api/v1/skills/'+item['skill_id']).json()
    child=client.get('/api/v1/skills/'+result['skill_id']).json()
    assert not parent['enabled'] and not parent['published_revision_id'] and parent['applicable_modules']==[]
    assert child['published_revision_id']==result['revision_id'] and child['applicable_modules']==['analysis']
    revision=client.get(f'/api/v1/skills/{result["skill_id"]}/revisions/{result["revision_id"]}').json()
    assert revision['entry_path']=='bio-test-skill/SKILL.md' and not revision['diagnostics']['errors']
    assert revision['diagnostics']['metadata']['metadata']['priority']=='3'
    assert revision['diagnostics']['metadata']['allowed-tools']=='Read Write'
    assert client.get(f'/api/v1/skills/{item["skill_id"]}/revisions/{item["revision_id"]}/files',params={'path':'test-skill/SKILL.md'}).json()['content'].encode()==raw
    again=normalize_copy(client,item['skill_id'],item['revision_id'],['analysis'],'生信分析')
    assert (again['skill_id'],again['revision_id'])==(result['skill_id'],result['revision_id'])
    assert client.get('/api/v1/skills').json()['total']==2
