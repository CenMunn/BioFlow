import difflib
import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import threading
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

import yaml
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import db, sources, workbench
from .packages import (Fault, MAX_UPLOAD, MAX_PREVIEW, EXPORT_MANIFEST, content_hash, copy_selection,
                       diagnose, export_zip, extract_zip, files, initial, metadata, relative, safe, scan)

PREFIX = '/api/v1'
AUTH_FILE = Path(os.getenv('SC_AUTH_FILE', db.ROOT / 'admin.json'))
ATTEMPTS = {}
MODULES = [
    {'id':'writing','name':'文献撰写','description':'检索与综述、论文写作、引用核验、审稿及方法描述'},
    {'id':'analysis','name':'数据分析与生图','description':'生信分析、数据图表、科研示意图及配图提示词'},
]


def selected_modules(values):
    if not isinstance(values,list) or any(not isinstance(v,str) or v not in {m['id'] for m in MODULES} for v in values):
        raise Fault('INVALID_MODULE','请选择有效业务板块。')
    return list(dict.fromkeys(values))


def modules_catalog():
    with db.transaction() as conn:
        counts={m['id']:conn.execute("SELECT count(*) FROM skills s WHERE json_extract(s.body,'$.archived_at') IS NULL AND EXISTS(SELECT 1 FROM json_each(s.body,'$.applicable_modules') a WHERE a.value=?)",(m['id'],)).fetchone()[0] for m in MODULES}
        total=conn.execute("SELECT count(*) FROM skills WHERE json_extract(body,'$.archived_at') IS NULL").fetchone()[0]
    return {'items':[{**m,'count':counts[m['id']]} for m in MODULES],'total':total}


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()


def require(table, key):
    value = db.get(table,key)
    if not value:
        raise Fault('NOT_FOUND','请求的记录不存在。',404)
    return value


def skill(key):
    return require('skills',key)


def revision(sid, rid=None):
    s = skill(sid)
    rid = rid or s.get('published_revision_id') or s.get('latest_revision_id')
    if not rid:
        raise Fault('NEEDS_PUBLISH','该技能尚无发布或导入快照，请打开草稿。',409)
    r = require('revisions',rid)
    if r['skill_id']!=sid:
        raise Fault('NOT_FOUND','版本不属于该技能。',404)
    if not db.revision_root(r).exists():
        raise Fault('SNAPSHOT_MISSING','版本文件缺失，请从备份恢复。',409)
    return r


def new_skill(name, display, description, origin='local', **extra):
    return {'id':db.uid(),'skill_name':name,'display_name':display or name,'description':description,
            'display_summary':'','category':'通用','tags':[],'applicable_modules':[],'origin_type':origin,'source_id':None,
            'parent_skill_id':None,'parent_revision_id':None,'enabled':True,'archived_at':None,
            'published_revision_id':None,'latest_revision_id':None,'favorite':False,'last_viewed_at':None,
            'execution_type':'unclassified','execution_state':'unverified','created_at':db.now(),
            'updated_at':db.now(),**extra}


def make_draft(s, source_root=None, entry=None, base=None, note=None):
    draft = {'id':db.uid(),'skill_id':s['id'],'entry_path':entry or s['skill_name']+'/SKILL.md',
             'base_revision_id':base,'draft_counter':1,'updated_at':db.now(),'change_note':note or ''}
    root = db.draft_root(draft)
    root.mkdir(parents=True)
    if source_root:
        shutil.copytree(source_root,root,dirs_exist_ok=True)
    db.put('drafts',draft)
    return draft


def snapshot(s, root, entry, note='', source_snapshot=None, support_paths=None, restoring=None):
    diagnosis = diagnose(root,entry)
    manifest = files(root)
    prior = [r for r in db.all_rows('revisions') if r['skill_id']==s['id']]
    valid = not diagnosis['errors']
    version = max([r['platform_version'] for r in prior]+[0])+1
    r = {'id':db.uid(),'skill_id':s['id'],'platform_version':version,'entry_path':entry,
         'content_hash':content_hash(manifest),'files':manifest,'diagnostics':diagnosis,
         'status':'published' if valid else 'imported-invalid','created_at':db.now(),'change_note':note,
         'source_snapshot':source_snapshot,'support_paths':support_paths or [],'restored_from':restoring}
    stage = db.ROOT/'staging'/r['id']
    stage.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root,stage)
    target = db.revision_root(r)
    target.parent.mkdir(parents=True,exist_ok=True)
    stage.replace(target)
    try:
        with db.transaction() as conn:
            db.put('revisions',r,conn)
            s['latest_revision_id']=r['id']
            if valid:
                s['published_revision_id']=r['id']
                s['skill_name']=diagnosis['metadata']['name']
                s['description']=diagnosis['metadata']['description']
            s['updated_at']=db.now()
            db.put('skills',s,conn)
    except BaseException:
        shutil.rmtree(target)
        raise
    return r


def decorated(s):
    result=dict(s)
    rid=s.get('published_revision_id') or s.get('latest_revision_id')
    rev=db.get('revisions',rid) if rid else None
    result['content_status']='archived' if s['archived_at'] else ('published' if s['published_revision_id'] else 'draft')
    result['diagnostics']=rev['diagnostics'] if rev else None
    result['version']=rev['platform_version'] if rev else None
    result['drafts']=[d for d in db.all_rows('drafts') if d['skill_id']==s['id']]
    result['source']=db.get('sources',s['source_id']) if s.get('source_id') else None
    if rev and rev.get('source_snapshot'):
        result['source_links']=sources.links(rev['source_snapshot'],rev['entry_path'])
    else:
        result['source_links']=None
    return result


def recover():
    for job in db.all_rows('imports'):
        if job['status'] in {'queued','running'}:
            job.update(status='interrupted',error='服务重启，扫描任务已中断，请重试。')
            db.put('imports',job)
    for r in db.all_rows('revisions'):
        if not db.revision_root(r).is_dir():
            s=skill(r['skill_id'])
            s['enabled']=False
            s['snapshot_error']='快照文件缺失，已停用。'
            db.put('skills',s)
    known={db.revision_root(r).resolve() for r in db.all_rows('revisions')}
    orphaned=[str(p.relative_to(db.ROOT)) for p in (db.ROOT/'skills').glob('*/revisions/*/bundle') if p.resolve() not in known]
    if orphaned:
        (db.ROOT/'orphaned-snapshots.json').write_text(json.dumps({'detected_at':db.now(),'paths':orphaned}),encoding='utf-8')
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE json_extract(body,'$.expires_at') < ?",(time.time(),))
    staging=db.ROOT/'staging'
    if staging.exists():
        # Only abandoned staging data created by this application is disposable.
        shutil.rmtree(staging)


@asynccontextmanager
async def lifespan(app):
    recover()
    workbench.recover()
    yield
    workbench.shutdown()


app=FastAPI(title='BioFlow Skill 中心',version='1.2.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.include_router(workbench.router)


@app.exception_handler(Fault)
async def fault_handler(request, exc):
    return JSONResponse({'error':{'code':exc.code,'message':exc.message,'details':exc.details,'request_id':db.uid()}},status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    return JSONResponse({'error':{'code':'INVALID_REQUEST','message':'请求参数格式不正确。','details':{},'request_id':db.uid()}},status_code=422)


@app.middleware('http')
async def auth(request:Request, call_next):
    path=request.url.path
    if path.startswith(PREFIX) and path not in {PREFIX+'/health',PREFIX+'/auth/login'}:
        raw=request.cookies.get('sc_session','')
        session=db.get('sessions',hashlib.sha256(raw.encode()).hexdigest()) if raw else None
        if not session or session['expires_at']<time.time():
            return JSONResponse({'error':{'code':'UNAUTHORIZED','message':'请先登录。','details':{},'request_id':db.uid()}},status_code=401)
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'error':{'code':'INVALID_ORIGIN','message':'拒绝跨站写入请求。','details':{},'request_id':db.uid()}},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    if path.startswith(PREFIX):
        response.headers['Cache-Control']='no-store'
    return response


@app.get(PREFIX+'/health')
def health():
    return {'status':'ok','version':'1.2.0','scope':'M0-M3','model_execution':'not_implemented','algorithm_execution':'local-worker'}


@app.post(PREFIX+'/auth/login')
def login(payload:dict,request:Request):
    peer=request.client.host if request.client else 'unknown'
    attempts=[x for x in ATTEMPTS.get(peer,[]) if x>time.time()-60]
    ATTEMPTS[peer]=attempts
    if len(attempts)>=10:
        raise Fault('RATE_LIMITED','登录尝试过多，请一分钟后重试。',429)
    if not AUTH_FILE.exists():
        raise Fault('SETUP_REQUIRED','管理员尚未配置，请运行部署初始化命令。',503)
    config=json.loads(AUTH_FILE.read_text())
    password=payload.get('password','')
    if not isinstance(password,str) or len(password)>512:
        raise Fault('UNAUTHORIZED','用户名或密码错误。',401)
    ok=hmac.compare_digest(password_hash(password,config['salt']),config['password_hash'])
    if payload.get('username')!=config['username'] or not ok:
        attempts.append(time.time())
        raise Fault('UNAUTHORIZED','用户名或密码错误。',401)
    ATTEMPTS.pop(peer,None)
    token=secrets.token_urlsafe(32)
    db.put('sessions',{'id':hashlib.sha256(token.encode()).hexdigest(),'expires_at':time.time()+43200,'username':config['username']})
    response=JSONResponse({'username':config['username']})
    response.set_cookie('sc_session',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200)
    return response


@app.get(PREFIX+'/auth/me')
def me():
    return {'role':'administrator','scope':'M0-M3'}


@app.post(PREFIX+'/auth/logout')
def logout(request:Request):
    key=hashlib.sha256(request.cookies.get('sc_session','').encode()).hexdigest()
    with db.transaction() as conn:
        conn.execute('DELETE FROM sessions WHERE id=?',(key,))
    response=JSONResponse({'ok':True})
    response.delete_cookie('sc_session')
    return response


@app.get(PREFIX+'/templates')
def templates():
    return {'items':[{'id':key,'name':name} for key,name in [('blank','空白技能'),('writing','科研写作'),('literature','文献阅读'),('tool','工具执行'),('visualization','可视化')]]}


@app.get(PREFIX+'/skills')
def catalog(q='', category='', origin_type='', content_status='', execution_state='', module='', favorite=False, sort='updated',page:int=1,page_size:int=12):
    page=max(page,1); page_size=min(max(page_size,1),100)
    where, params=[],[]
    if module:
        selected_modules([module])
        where.append("EXISTS(SELECT 1 FROM json_each(skills.body,'$.applicable_modules') m WHERE m.value=?)")
        params.append(module)
    if q:
        where.append("(json_extract(body,'$.skill_name') LIKE ? OR json_extract(body,'$.display_name') LIKE ? OR json_extract(body,'$.description') LIKE ? OR json_extract(body,'$.tags') LIKE ?)")
        params.extend(['%'+q+'%']*4)
    for key,value in [('category',category),('origin_type',origin_type),('execution_state',execution_state)]:
        if value:
            where.append(f"json_extract(body,'$.{key}')=?"); params.append(value)
    if favorite:
        where.append("json_extract(body,'$.favorite')=1")
    if content_status=='archived':
        where.append("json_extract(body,'$.archived_at') IS NOT NULL")
    else:
        where.append("json_extract(body,'$.archived_at') IS NULL")
        if content_status=='published':
            where.append("json_extract(body,'$.published_revision_id') IS NOT NULL")
        elif content_status=='draft':
            where.append("json_extract(body,'$.published_revision_id') IS NULL")
    order={'name':"json_extract(body,'$.display_name') ASC",'recent':"json_extract(body,'$.last_viewed_at') DESC"}.get(sort,"json_extract(body,'$.updated_at') DESC")
    clause=' WHERE '+' AND '.join(where) if where else ''
    with db.transaction() as conn:
        total=conn.execute('SELECT count(*) FROM skills'+clause,params).fetchone()[0]
        rows=conn.execute('SELECT body FROM skills'+clause+' ORDER BY '+order+' LIMIT ? OFFSET ?',params+[page_size,(page-1)*page_size]).fetchall()
        categories=[r[0] for r in conn.execute("SELECT DISTINCT json_extract(body,'$.category') FROM skills") if r[0]]
    return {'items':[decorated(json.loads(r[0])) for r in rows],'total':total,'page':page,'page_size':page_size,'categories':sorted(set(categories+['文献','写作','分析','可视化','通用'])),'modules':modules_catalog()}


@app.get(PREFIX+'/modules')
def module_list():
    return modules_catalog()


@app.post(PREFIX+'/skills',status_code=201)
def create(payload:dict):
    name=payload.get('skill_name','')
    text=initial(name,payload.get('description',''),payload.get('template','blank'))
    s=new_skill(name,payload.get('display_name'),payload['description'],category=payload.get('category') or '通用',applicable_modules=selected_modules(payload.get('applicable_modules',[])))
    with db.LOCK:
        db.put('skills',s)
        draft=make_draft(s)
        p=safe(db.draft_root(draft),draft['entry_path']); p.parent.mkdir(parents=True)
        p.write_text(text,encoding='utf-8')
    return {'skill':decorated(s),'draft':draft}


@app.get(PREFIX+'/skills/{sid}')
def detail(sid):
    s=skill(sid); s['last_viewed_at']=db.now(); db.put('skills',s)
    return decorated(s)


@app.patch(PREFIX+'/skills/{sid}')
def patch_skill(sid,payload:dict):
    with db.LOCK:
        s=skill(sid)
        for key in ('display_name','display_summary','category','tags','enabled','execution_type','applicable_modules'):
            if key not in payload: continue
            value=payload[key]
            if key=='applicable_modules': value=selected_modules(value)
            if key=='enabled' and not isinstance(value,bool): raise Fault('INVALID_REQUEST','enabled 须为布尔值。')
            if key=='tags' and (not isinstance(value,list) or len(value)>30 or any(not isinstance(x,str) or len(x)>80 for x in value)): raise Fault('INVALID_REQUEST','标签格式无效。')
            if key=='execution_type' and value not in {'text','tool','manual','unclassified'}: raise Fault('INVALID_REQUEST','执行类型无效。')
            if key not in {'enabled','tags','execution_type','applicable_modules'} and (not isinstance(value,str) or len(value)>2048): raise Fault('INVALID_REQUEST','展示信息无效。')
            s[key]=value
        s['updated_at']=db.now(); db.put('skills',s)
    return decorated(s)


@app.put(PREFIX+'/skills/{sid}/favorite')
def favorite(sid,payload:dict):
    with db.LOCK:
        s=skill(sid); s['favorite']=bool(payload.get('favorite')); db.put('skills',s)
    return {'favorite':s['favorite']}


@app.post(PREFIX+'/skills/{sid}/archive')
def archive(sid,payload:dict):
    with db.LOCK:
        s=skill(sid); s['archived_at']=db.now() if payload.get('archived',True) else None; db.put('skills',s)
    return decorated(s)


@app.post(PREFIX+'/skills/{sid}/fork',status_code=201)
def fork(sid,payload:dict):
    with db.LOCK:
        parent=skill(sid); rev=revision(sid,payload.get('revision_id'))
        s=new_skill(parent['skill_name'],payload.get('display_name') or parent['display_name']+'（副本）',parent['description'],'fork',parent_skill_id=sid,parent_revision_id=rev['id'],category=parent['category'],tags=parent['tags'],applicable_modules=parent.get('applicable_modules',[]))
        db.put('skills',s)
        d=make_draft(s,db.revision_root(rev),rev['entry_path'],rev['id'])
    return {'skill':decorated(s),'draft':d}


@app.get(PREFIX+'/skills/{sid}/revisions')
def revisions(sid):
    skill(sid)
    return {'items':sorted([r for r in db.all_rows('revisions') if r['skill_id']==sid],key=lambda x:x['platform_version'],reverse=True)}


@app.get(PREFIX+'/skills/{sid}/revisions/{rid}')
def get_revision(sid,rid):
    r=revision(sid,rid)
    return {**r,'source_links':sources.links(r['source_snapshot'],r['entry_path']) if r.get('source_snapshot') else None}


@app.get(PREFIX+'/skills/{sid}/revisions/{rid}/files')
def get_file(sid,rid,path:str,download:bool=False):
    r=revision(sid,rid); root=db.revision_root(r)
    p=safe(root,path)
    if not p.is_file(): raise Fault('NOT_FOUND','文件不存在。',404)
    if download: return FileResponse(p,filename=p.name,media_type='application/octet-stream')
    if p.stat().st_size>MAX_PREVIEW: raise Fault('PREVIEW_LIMIT','文件太大，请下载后查看。',413)
    try: text=p.read_bytes().decode('utf-8-sig')
    except UnicodeDecodeError: raise Fault('UNSUPPORTED_PREVIEW','该文件不能作为 UTF-8 文本预览，请下载。')
    return {'path':path,'content':text,'encoding':'utf-8','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


@app.post(PREFIX+'/skills/{sid}/drafts',status_code=201)
def edit_draft(sid,payload:dict):
    with db.LOCK:
        s=skill(sid)
        if s['origin_type'] in {'github','upload'}: raise Fault('READ_ONLY_ORIGINAL','导入原版只读，请创建副本后编辑。',409)
        r=revision(sid,payload.get('revision_id'))
        d=make_draft(s,db.revision_root(r),r['entry_path'],r['id'])
    return draft_detail(d['id'])


@app.get(PREFIX+'/drafts/{did}')
def draft_detail(did):
    with db.LOCK:
        d=require('drafts',did)
        return {**d,'files':files(db.draft_root(d)),'diagnostics':diagnose(db.draft_root(d),d['entry_path'])}


@app.get(PREFIX+'/drafts/{did}/files')
def draft_file(did,path:str):
    with db.LOCK:
        d=require('drafts',did); p=safe(db.draft_root(d),path)
        if not p.is_file(): raise Fault('NOT_FOUND','文件不存在。',404)
        if p.stat().st_size>MAX_PREVIEW: raise Fault('PREVIEW_LIMIT','文件太大，不能直接编辑。',413)
        try: return {'path':path,'content':p.read_bytes().decode('utf-8-sig')}
        except UnicodeDecodeError: raise Fault('UNSUPPORTED_PREVIEW','二进制文件请保留或替换，不能直接文本编辑。')


def mutate_draft(did,payload,blob=None):
    with db.LOCK:
        d=require('drafts',did); s=skill(d['skill_id'])
        if s['origin_type'] in {'github','upload'}: raise Fault('READ_ONLY_ORIGINAL','导入原版不可编辑。',409)
        if payload.get('draft_counter')!=d['draft_counter']: raise Fault('REVISION_CONFLICT','草稿已有更新，请重新加载并比较内容。',409,{'current_counter':d['draft_counter']})
        root=db.draft_root(d); stage=root.parent/('edit-'+db.uid()); old=root.parent/('old-'+db.uid())
        shutil.copytree(root,stage)
        previous=dict(d)
        try:
            for item in payload.get('changes',[]):
                p=safe(stage,item.get('path',''))
                if item.get('delete'):
                    if item['path']==d['entry_path']: raise Fault('INVALID_REQUEST','不能删除技能入口。')
                    if p.is_file(): p.unlink()
                else:
                    text=item.get('content')
                    if not isinstance(text,str) or len(text.encode())>MAX_PREVIEW: raise Fault('PREVIEW_LIMIT','文本内容过大或无效。',413)
                    p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(text.encode('utf-8'))
            if blob:
                p=safe(stage,blob[0]); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(blob[1])
            if payload.get('metadata'):
                p=safe(stage,d['entry_path']); fields,body,_=metadata(p.read_bytes())
                fields.update({k:v for k,v in payload['metadata'].items() if k in {'name','description'}})
                p.write_text('---\n'+yaml.safe_dump(fields,allow_unicode=True,sort_keys=False)+'---\n'+body,encoding='utf-8')
            # A standard-name change also renames the export entry directory.
            try:
                fields,_,_=metadata(safe(stage,d['entry_path']).read_bytes()); new_name=fields.get('name')
                from .packages import NAME
                parent=PurePosixPath(d['entry_path']).parent
                if isinstance(new_name,str) and len(new_name)<=64 and NAME.fullmatch(new_name) and parent.name!=new_name:
                    new_parent=parent.parent/new_name
                    source=safe(stage,str(parent)); destination=safe(stage,str(new_parent))
                    if destination.exists(): raise Fault('NAME_CONFLICT','新标准名称的目录已经存在。',409)
                    source.rename(destination); d['entry_path']=str(new_parent/'SKILL.md')
            except Fault as exc:
                if exc.code not in {'INVALID_SKILL_FORMAT'}: raise
            files(stage)
            root.rename(old); stage.rename(root)
            try:
                d['draft_counter']+=1; d['updated_at']=db.now(); db.put('drafts',d)
            except BaseException:
                shutil.rmtree(root); old.rename(root); raise
            shutil.rmtree(old)
        except BaseException:
            if stage.exists(): shutil.rmtree(stage)
            raise
        return draft_detail(did)


@app.patch(PREFIX+'/drafts/{did}/files')
def draft_update(did,payload:dict):
    return mutate_draft(did,payload)


@app.post(PREFIX+'/drafts/{did}/upload')
async def draft_upload(did,path:str,draft_counter:int,file:UploadFile=File(...)):
    content=await file.read(MAX_UPLOAD+1)
    if len(content)>MAX_UPLOAD: raise Fault('IMPORT_LIMIT_EXCEEDED','附件超过大小限额。',413)
    return mutate_draft(did,{'draft_counter':draft_counter},(path,content))


@app.post(PREFIX+'/drafts/{did}/validate')
def validate(did):
    d=require('drafts',did)
    return diagnose(db.draft_root(d),d['entry_path'])


@app.post(PREFIX+'/drafts/{did}/publish',status_code=201)
def publish(did,payload:dict):
    with db.LOCK:
        d=require('drafts',did); s=skill(d['skill_id'])
        if s['origin_type'] in {'github','upload'}: raise Fault('READ_ONLY_ORIGINAL','导入原版只读。',409)
        if payload.get('draft_counter')!=d['draft_counter']: raise Fault('REVISION_CONFLICT','草稿版本冲突，请重新加载。',409)
        if d.get('base_revision_id') and s.get('published_revision_id') and d['base_revision_id']!=s['published_revision_id']: raise Fault('REVISION_CONFLICT','发布版本已变化，请基于最新版本编辑。',409)
        diagnosis=diagnose(db.draft_root(d),d['entry_path'])
        if diagnosis['errors']: raise Fault('INVALID_SKILL_FORMAT','修复格式错误后才能发布。',409,diagnosis)
        r=snapshot(s,db.draft_root(d),d['entry_path'],payload.get('change_note',''))
        with db.transaction() as conn: conn.execute('DELETE FROM drafts WHERE id=?',(did,))
        shutil.rmtree(db.draft_root(d))
        return r


@app.post(PREFIX+'/skills/{sid}/restore',status_code=201)
def restore(sid,payload:dict):
    with db.LOCK:
        s=skill(sid); r=revision(sid,payload.get('revision_id'))
        if r['diagnostics']['errors']: raise Fault('INVALID_SKILL_FORMAT','无效快照不能恢复为发布版本。',409)
        return snapshot(s,db.revision_root(r),r['entry_path'],'恢复平台版本 '+str(r['platform_version']),r.get('source_snapshot'),r.get('support_paths'),r['id'])


def compare(root_a,root_b):
    a={f['path']:f for f in files(root_a)}; b={f['path']:f for f in files(root_b)}
    changes=[]
    for p in sorted(a.keys()|b.keys()):
        if p not in a: kind='added'
        elif p not in b: kind='deleted'
        elif a[p]['sha256']==b[p]['sha256']: continue
        else: kind='modified'
        diff=None
        try:
            left=safe(root_a,p).read_text(encoding='utf-8-sig') if p in a and a[p]['size']<=MAX_PREVIEW else ''
            right=safe(root_b,p).read_text(encoding='utf-8-sig') if p in b and b[p]['size']<=MAX_PREVIEW else ''
            diff=''.join(difflib.unified_diff(left.splitlines(True),right.splitlines(True),fromfile='old/'+p,tofile='new/'+p))[:200000]
        except UnicodeDecodeError: pass
        changes.append({'path':p,'change':kind,'diff':diff,'before_hash':a.get(p,{}).get('sha256'),'after_hash':b.get(p,{}).get('sha256')})
    return changes


@app.get(PREFIX+'/skills/{sid}/diff')
def diff_versions(sid,from_revision_id:str,to_revision_id:str):
    return {'changes':compare(db.revision_root(revision(sid,from_revision_id)),db.revision_root(revision(sid,to_revision_id)))}


@app.get(PREFIX+'/skills/{sid}/export')
def export(sid,revision_id:str=None):
    r=revision(sid,revision_id); s=skill(sid)
    manifest={'skill_id':sid,'revision_id':r['id'],'platform_version':r['platform_version'],'entry_path':r['entry_path'],'content_hash':r['content_hash'],'source':r.get('source_snapshot'),'support_paths':r.get('support_paths',[]),'files':r['files']}
    return Response(export_zip(db.revision_root(r),manifest),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{s["skill_name"]}-v{r["platform_version"]}.zip"'})


@app.get(PREFIX+'/skills/{sid}/usage-options')
def usage(sid,revision_id:str=None):
    s=skill(sid); r=revision(sid,revision_id)
    p=safe(db.revision_root(r),r['entry_path'])
    try: text=p.read_bytes().decode('utf-8-sig')
    except UnicodeDecodeError: text=None
    source=r.get('source_snapshot'); command=None
    if source and s['origin_type']=='github' and r['diagnostics']['resource_status']=='complete' and not r.get('support_paths'):
        import shlex
        link=sources.links(source,r['entry_path'])['latest']
        command='npx skills add '+shlex.quote(link)+' --skill '+shlex.quote(s['skill_name'])+' --agent codex'
    return {'content':text,'prompt':f"使用技能 {s['skill_name']}（平台版本 {r['platform_version']}）。用途：{s['description']}\n请按完整技能包说明处理以下任务：\n[在此填写任务和材料]",
            'copy_note':'复制正文不能替代完整技能包及附属资源。','install_command':command,
            'install_note':'安装对象：上游最新分支；目标：当前项目 Codex。与本平台导入快照不同。' if command else '请下载完整包并放入客户端技能目录。没有可验证的远程安装对象，或共享资源需手动放置。',
            'server_trial':{'available':False,'reason':'本轮为 M0～M3 管理版；后续连接服务器模型。'},
            'content_api':f'{PREFIX}/skills/{sid}/revisions/{r["id"]}','files_api':f'{PREFIX}/skills/{sid}/revisions/{r["id"]}/files?path='+r['entry_path']}


def job_root(jid):
    return db.ROOT/'imports'/jid/'bundle'


def job_update(jid,**updates):
    with db.LOCK:
        j=require('imports',jid)
        if j['status']=='cancelled': return False
        j.update(updates,updated_at=db.now()); db.put('imports',j)
        return True


def candidates_finish(job,source=None):
    candidates,manifest=scan(job_root(job['id']), (source or {}).get('requested_path',''))
    support_only_paths=[relative(p).rstrip('/') for p in job.get('input',{}).get('support_only_paths',[])]
    # Normalize an entry at bundle root into the skill's named directory.
    if any(c['entry_path']=='SKILL.md' for c in candidates) and 'SKILL.md' not in support_only_paths:
        try: name=metadata((job_root(job['id'])/'SKILL.md').read_bytes())[0].get('name')
        except Fault: name=None
        from .packages import NAME
        name=name if isinstance(name,str) and len(name)<=64 and NAME.fullmatch(name) else 'imported-skill'
        root=job_root(job['id']); moved=root.parent/('normalize-'+db.uid())
        root.rename(moved); root.mkdir(); shutil.move(str(moved),str(root/name))
        if source: source['package_prefix']=name
        candidates,manifest=scan(root)
        support_only_paths=[name+'/'+p for p in support_only_paths]
    support_entries=[f['path'] for f in manifest if PurePosixPath(f['path']).name=='SKILL.md' and any(f['path']==p or f['path'].startswith(p+'/') for p in support_only_paths)]
    candidates=[c for c in candidates if c['entry_path'] not in support_entries]
    if not candidates: raise Fault('NO_SKILLS','未发现可选择的 SKILL.md，请检查路径或压缩包。')
    known=db.all_rows('skills')
    for c in candidates:
        c['same_name_skills']=[{'id':s['id'],'display_name':s['display_name'],'origin_type':s['origin_type']} for s in known if s['skill_name']==c['skill_name']]
    all_candidates,_=scan(job_root(job['id']))
    skill_dirs=[str(PurePosixPath(c['entry_path']).parent) for c in all_candidates if c['entry_path'] not in support_entries]
    support=[f for f in manifest if not any(p=='.' or f['path'].startswith(p+'/') for p in skill_dirs)]
    job_update(job['id'],status='ready',progress='请选择技能与共享资源后确认保存。',candidates=candidates,files=manifest,support_files=support,source=source,support_only_entries=support_entries)
    if job.get('source_id') and source:
        record=require('sources',job['source_id'])
        record.update(latest_observed_commit_sha=source['commit_sha'],last_checked_at=db.now(),last_error=None)
        db.put('sources',record)


def github_worker(jid):
    try:
        j=require('imports',jid)
        if not job_update(jid,status='running',progress='解析 GitHub 仓库与版本…'): return
        source=sources.resolve(j['input']['url'],j['input'].get('ref'),j['input'].get('path'))
        if not job_update(jid,source=source,progress='已固定提交，下载完整快照…'): return
        data=sources.download(source,lambda:require('imports',jid)['status']=='cancelled')
        if not job_update(jid,progress='检查压缩包与扫描技能…'): return
        root=job_root(jid); root.mkdir(parents=True,exist_ok=True)
        extract_zip(data,root,True)
        candidates_finish(j,source)
    except Fault as exc:
        job_update(jid,status='failed',error=exc.message,error_code=exc.code,error_details=exc.details)
        j=require('imports',jid)
        if j.get('source_id'):
            record=require('sources',j['source_id']);record['last_error']=exc.message;db.put('sources',record)
    except Exception:
        job_update(jid,status='failed',error='扫描失败，请重试或使用上传方式。',error_code='IMPORT_FAILED')


def new_job(kind,input_data,source_id=None,update_skill_id=None):
    j={'id':db.uid(),'input_type':kind,'input':input_data,'status':'queued','progress':'等待扫描','candidates':[],'files':[],'support_files':[],'source':None,'source_id':source_id,'update_skill_id':update_skill_id,'created_at':db.now(),'updated_at':db.now(),'error':None}
    db.put('imports',j); return j


@app.post(PREFIX+'/imports/github/preview',status_code=202)
def github_preview(payload:dict):
    url=payload.get('url')
    if not isinstance(url,str) or len(url)>2048: raise Fault('INVALID_SOURCE','请输入 GitHub 链接。')
    shared=payload.get('support_only_paths',[])
    if not isinstance(shared,list) or len(shared)>30: raise Fault('INVALID_SELECTION','共享支持目录格式无效。')
    shared=[relative(p) for p in shared]
    j=new_job('github',{'url':url,'ref':payload.get('ref') or None,'path':payload.get('path') or None,'support_only_paths':shared})
    threading.Thread(target=github_worker,args=(j['id'],),daemon=True).start()
    return j


@app.post(PREFIX+'/imports/upload/preview',status_code=201)
async def upload_preview(file:UploadFile=File(...)):
    data=await file.read(MAX_UPLOAD+1)
    if len(data)>MAX_UPLOAD: raise Fault('IMPORT_LIMIT_EXCEEDED','文件超过上传限额。',413)
    filename=file.filename or ''
    if not filename.lower().endswith(('.md','.zip')): raise Fault('UNSUPPORTED_INPUT_TYPE','请上传 SKILL.md 或 ZIP。')
    j=new_job('upload',{'filename':filename})
    root=job_root(j['id']); root.mkdir(parents=True)
    try:
        if filename.lower().endswith('.zip'): extract_zip(data,root)
        else: (root/'SKILL.md').write_bytes(data)
        if (root/EXPORT_MANIFEST).exists(): (root/EXPORT_MANIFEST).unlink()
        candidates_finish(j)
    except Fault as exc:
        job_update(j['id'],status='failed',error=exc.message,error_code=exc.code)
        raise
    return require('imports',j['id'])


@app.get(PREFIX+'/imports')
def import_jobs():
    return {'items':sorted(db.all_rows('imports'),key=lambda j:j['created_at'],reverse=True)[:100]}


@app.get(PREFIX+'/imports/{jid}')
def get_import(jid):
    return require('imports',jid)


@app.get(PREFIX+'/imports/{jid}/files')
def import_file(jid,path:str):
    j=require('imports',jid)
    if j['status'] not in {'ready','committed'}: raise Fault('IMPORT_NOT_READY','扫描尚未完成。',409)
    p=safe(job_root(jid),path)
    if not p.is_file(): raise Fault('NOT_FOUND','文件不存在。',404)
    if p.stat().st_size>MAX_PREVIEW: raise Fault('PREVIEW_LIMIT','文件太大，预览不可用。',413)
    try: text=p.read_bytes().decode('utf-8-sig')
    except UnicodeDecodeError: raise Fault('UNSUPPORTED_PREVIEW','二进制文件仅显示大小和哈希。')
    return {'path':path,'content':text}


@app.post(PREFIX+'/imports/{jid}/cancel')
def cancel_import(jid):
    with db.LOCK:
        j=require('imports',jid)
        if j['status'] in {'queued','running','ready'}:
            j.update(status='cancelled',progress='已取消'); db.put('imports',j)
    return j


@app.post(PREFIX+'/imports/{jid}/retry',status_code=202)
def retry_import(jid):
    j=require('imports',jid)
    if j['input_type']!='github': raise Fault('REUPLOAD_REQUIRED','上传失败后请重新选择文件上传。')
    result=new_job('github',j['input'],j.get('source_id'),j.get('update_skill_id'))
    threading.Thread(target=github_worker,args=(result['id'],),daemon=True).start()
    return result


@app.post(PREFIX+'/imports/{jid}/commit')
def commit_import(jid,payload:dict):
    selection=payload.get('entries',[]); supports=payload.get('support_paths',[])
    assignment=selected_modules(payload.get('applicable_modules',[]))
    if not isinstance(selection,list) or not selection or any(not isinstance(x,str) for x in selection) or not isinstance(supports,list) or any(not isinstance(x,str) for x in supports): raise Fault('INVALID_SELECTION','请选择技能和资源。')
    signature=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    with db.LOCK, db.transaction():
        j=require('imports',jid)
        if j['status']=='committed':
            if j['commit_signature']!=signature: raise Fault('REVISION_CONFLICT','该预览已经使用其他选择提交。',409)
            return j['result']
        if j['status']!='ready': raise Fault('IMPORT_NOT_READY','扫描尚未完成或已取消。',409)
        allowed={c['entry_path'] for c in j['candidates']}
        if not set(selection)<=allowed: raise Fault('INVALID_SELECTION','选择了预览中不存在的技能。')
        if j.get('update_skill_id') and len(selection)!=1: raise Fault('INVALID_SELECTION','来源更新只能选择一个对应入口。')
        for p in supports:
            relative(p)
            if not safe(job_root(jid),p).exists(): raise Fault('INVALID_SELECTION','共享资源不存在。')
            all_entries={f['path'] for f in j['files'] if PurePosixPath(f['path']).name=='SKILL.md'}
            if any(e==p or e.startswith(p.rstrip('/')+'/') for e in all_entries if e not in selection and e not in j.get('support_only_entries',[])): raise Fault('INVALID_SELECTION','不能通过共享资源隐式导入未选择的技能。')
        results=[]
        for entry in dict.fromkeys(selection):
            stage=db.ROOT/'staging'/db.uid(); stage.mkdir(parents=True)
            try:
                manifest=copy_selection(job_root(jid),stage,entry,supports); digest=content_hash(manifest)
                source=j.get('source')
                duplicates=[]
                for r in db.all_rows('revisions'):
                    rs=r.get('source_snapshot') or {}
                    if r['entry_path']==entry and r['content_hash']==digest and ((source and rs.get('repository_url')==source['repository_url']) or (not source and skill(r['skill_id'])['origin_type']=='upload')): duplicates.append(r)
                if duplicates and not payload.get('new_copy'):
                    if assignment:
                        existing=skill(duplicates[0]['skill_id'])
                        existing['applicable_modules']=selected_modules(existing.get('applicable_modules',[])+assignment)
                        db.put('skills',existing)
                    results.append({'skill_id':duplicates[0]['skill_id'],'revision_id':duplicates[0]['id'],'skipped':True}); continue
                diagnosis=diagnose(stage,entry); name=diagnosis['metadata'].get('name')
                name=name if isinstance(name,str) else PurePosixPath(entry).parent.name
                description=diagnosis['metadata'].get('description')
                description=description if isinstance(description,str) else ''
                if j.get('update_skill_id'):
                    s=skill(j['update_skill_id'])
                    if entry!=(require('sources',s['source_id'])['skill_path']): raise Fault('INVALID_SELECTION','更新必须对应原技能入口。')
                else:
                    s=new_skill(name,name,description,j['input_type'],applicable_modules=assignment)
                source_id=s.get('source_id')
                if source:
                    upstream_entry=entry[len(source['package_prefix'])+1:] if source.get('package_prefix') and entry.startswith(source['package_prefix']+'/') else entry
                    record={**source,'id':source_id or db.uid(),'skill_path':entry,'upstream_skill_path':upstream_entry,'support_paths':supports,'support_only_paths':j.get('input',{}).get('support_only_paths',[]),'last_checked_at':db.now(),'last_commit_sha':source['commit_sha'],'last_error':None,'skill_id':s['id']}
                    db.put('sources',record); s['source_id']=record['id']
                db.put('skills',s)
                r=snapshot(s,stage,entry,'来源更新' if j.get('update_skill_id') else '完整包导入',source,supports)
                results.append({'skill_id':s['id'],'revision_id':r['id'],'skipped':False,'published':r['status']=='published'})
            finally:
                if stage.exists(): shutil.rmtree(stage)
        j.update(status='committed',commit_signature=signature,result={'items':results},selection_manifest={'entries':selection,'support_paths':supports},progress='保存完成')
        db.put('imports',j)
        return j['result']


@app.get(PREFIX+'/sources')
def source_list():
    return {'items':sorted(db.all_rows('sources'),key=lambda s:s.get('last_checked_at',''),reverse=True)}


@app.post(PREFIX+'/sources/{source_id}/check-update',status_code=202)
def check_update(source_id):
    record=require('sources',source_id)
    j=new_job('github',{'url':record['repository_url'],'ref':record['ref'],'path':record.get('upstream_skill_path',record['skill_path']),'support_only_paths':record.get('support_only_paths',[])},source_id,record['skill_id'])
    record['last_checked_at']=db.now(); record['update_job_id']=j['id']; db.put('sources',record)
    threading.Thread(target=github_worker,args=(j['id'],),daemon=True).start()
    return j


@app.get(PREFIX+'/sources/{source_id}/diff')
def source_diff(source_id,import_job_id:str,revision_id:str=None):
    record=require('sources',source_id); j=require('imports',import_job_id)
    if j.get('source_id')!=source_id: raise Fault('INVALID_SELECTION','扫描任务不属于该来源。')
    if j['status'] not in {'ready','committed'}: raise Fault('IMPORT_NOT_READY','更新扫描尚未完成。',409)
    r=revision(record['skill_id'],revision_id)
    stage=db.ROOT/'staging'/db.uid(); stage.mkdir(parents=True)
    try:
        copy_selection(job_root(j['id']),stage,record['skill_path'],record.get('support_paths',[]))
        changes=compare(db.revision_root(r),stage)
    finally: shutil.rmtree(stage)
    return {'changes':changes,'old_commit_sha':(r.get('source_snapshot') or {}).get('commit_sha'),'new_commit_sha':(j.get('source') or {}).get('commit_sha')}


FRONTEND=Path(os.getenv('SC_FRONTEND_DIR',Path(__file__).resolve().parents[1]/'frontend'/'dist'))
if FRONTEND.is_dir():
    app.mount('/assets',StaticFiles(directory=FRONTEND/'assets'),name='assets')

    @app.get('/{path:path}')
    def spa(path):
        if path.startswith('api/'): raise Fault('NOT_FOUND','接口不存在。',404)
        return FileResponse(FRONTEND/'index.html',headers={'Cache-Control':'no-cache'})
