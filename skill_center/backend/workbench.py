"""Additive algorithm/plot workbench. Existing Skill records are left unchanged."""
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import zipfile

from fastapi import APIRouter,File,UploadFile,Form
from fastapi.responses import FileResponse,Response
from starlette.concurrency import run_in_threadpool

from . import db,packages
from .workbench_catalog import PARAMETERS,RECIPES,recipe

router=APIRouter(prefix='/api/v1/workbench')
PROJECT=Path(__file__).resolve().parents[1]
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=2,thread_name_prefix='bioflow-analysis')
PROCESSES={}
PROCESS_LOCK=threading.Lock()
SLUG=re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
TASKS={'classification','clustering','feature_selection'}


def area():
    root=db.ROOT/'workbench';root.mkdir(exist_ok=True);return root


def runtime():
    return os.getenv('SC_ML_PYTHON',str(PROJECT/'.ml-venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')))


def worker_env(folder):
    env={k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL'}}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(folder/'matplotlib'),HOME=str(folder),PYTHONUNBUFFERED='1')
    return env


def invoke(request,folder,timeout=180):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    request={**request,'output_dir':str(folder/'output')}
    request_path=folder/'request-internal.json';request_path.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
    with (folder/'worker.log').open('wb') as log:
        process=subprocess.Popen([runtime(),str(PROJECT/'backend/workbench_worker.py'),str(request_path)],cwd=folder,env=worker_env(folder),stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        key=request.get('run_id')
        if key:
            with PROCESS_LOCK:PROCESSES[key]=process
            current=db.get('runs',key)
            if current and current['status'] in {'cancelled','interrupted'}:process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill();process.wait();raise packages.Fault('RUN_TIMEOUT','任务超过运行时限，已停止。',408)
        finally:
            if key:
                with PROCESS_LOCK:PROCESSES.pop(key,None)
    if process.returncode:
        error=folder/'output/error.json'
        message=json.loads(error.read_text(encoding='utf-8'))['message'] if error.exists() else '运行失败，请查看任务日志。'
        raise packages.Fault('EXECUTION_FAILED',message,422)
    return json.loads((folder/'output/result.json').read_text(encoding='utf-8'))


def require(table,key):
    item=db.get(table,key)
    if not item:raise packages.Fault('NOT_FOUND','记录不存在。',404)
    return item


def available_algorithm(key):
    entry=require('algorithms',key)
    if entry.get('archived_at'):raise packages.Fault('ALGORITHM_ARCHIVED','该算法已移至回收站，请先恢复。',409)
    return entry


def text(value,label,limit=500,required=False):
    if not isinstance(value,str) or len(value)>limit or required and not value.strip():raise packages.Fault('INVALID_REQUEST',f'{label}不能为空或超出长度限制。')
    return value.strip()


def validate_schema(schema):
    if not isinstance(schema,dict) or len(schema)>25:raise packages.Fault('INVALID_PARAMETERS','参数定义需要是最多 25 项的对象。')
    for name,spec in schema.items():
        if not re.fullmatch('[a-z][a-z0-9_]{0,39}',name) or not isinstance(spec,dict) or spec.get('type') not in {'integer','number','string','boolean'}:raise packages.Fault('INVALID_PARAMETERS','参数名或类型不合法。')
        if spec.get('type') in {'integer','number'}:
            if not all(isinstance(spec.get(k), (int,float)) and not isinstance(spec.get(k),bool) for k in ['min','max']) or spec['min']>spec['max']:raise packages.Fault('INVALID_PARAMETERS','数值参数需要有效上下限。')
        if 'enum' in spec and (not isinstance(spec['enum'],list) or not 1<=len(spec['enum'])<=30):raise packages.Fault('INVALID_PARAMETERS','枚举定义不合法。')
        if 'enum' in spec and (spec['type']!='string' or not all(isinstance(x,str) and len(x)<=200 for x in spec['enum'])):raise packages.Fault('INVALID_PARAMETERS','首版枚举参数仅支持字符串选项。')
    return schema


def parameters(schema,values):
    if not isinstance(values,dict) or set(values)-set(schema):raise packages.Fault('INVALID_PARAMETERS','包含未声明的算法参数。')
    result={}
    for name,spec in schema.items():
        value=values.get(name,spec.get('default'));kind=spec['type']
        valid=(kind=='integer' and isinstance(value,int) and not isinstance(value,bool)) or (kind=='number' and isinstance(value,(int,float)) and not isinstance(value,bool)) or (kind=='string' and isinstance(value,str) and len(value)<=200) or (kind=='boolean' and isinstance(value,bool))
        if not valid or kind in {'integer','number'} and not spec['min']<=value<=spec['max'] or 'enum' in spec and value not in spec['enum']:raise packages.Fault('INVALID_PARAMETERS','参数 '+name+' 的类型或范围不合法。')
        result[name]=value
    return result


def version_view(version):
    return {k:v for k,v in version.items() if k not in {'source_root','plugin_root','example_path'}}


def entry_view(entry):
    versions=sorted([v for v in db.all_rows('algorithm_versions') if v['algorithm_id']==entry['id']],key=lambda v:v['number'],reverse=True)
    active=db.get('algorithm_versions',entry.get('active_version_id',''))
    return {**entry,'active_version':version_view(active) if active else None,'versions':[version_view(v) for v in versions]}


def revision(entry,payload=None):
    key=(payload or {}).get('version_id') or entry.get('active_version_id')
    value=require('algorithm_versions',key or '')
    if value['algorithm_id']!=entry['id']:raise packages.Fault('INVALID_REQUEST','版本不属于该算法。')
    return value


def create_version(entry,base,defaults,note):
    values=parameters(base['parameters'],defaults)
    number=max([v['number'] for v in db.all_rows('algorithm_versions') if v['algorithm_id']==entry['id']]+[0])+1
    version={**base,'id':db.uid(),'algorithm_id':entry['id'],'number':number,'defaults':values,'change_note':text(note,'版本说明',500),'created_at':db.now(),'validation_status':'pending','validation_run_id':None,'published_at':None}
    db.put('algorithm_versions',version)
    return version


def job_path(job):
    return area()/'runs'/job['id']


def run_view(job):
    result={**job}
    log=job_path(job)/'worker.log'
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-16000));value=stream.read().decode('utf-8','replace')
        result['log']=value.replace(str(db.ROOT),'<storage>').replace(str(PROJECT),'<project>')
    return result


def execute_job(run_id,request):
    job=require('runs',run_id)
    if job['status']!='queued':return
    job.update(status='running',started_at=db.now());db.put('runs',job)
    try:
        result=invoke({**request,'run_id':run_id},job_path(job))
        job=require('runs',run_id)
        if job['status']!='running':return
        output=job_path(job)/'output'
        provenance={**job['request'],'run_id':job['id'],'dataset_sha256':job.get('dataset_sha256'),'canonical_dataset_sha256':job.get('canonical_dataset_sha256'),'environment':result.get('environment'),'algorithm_version_id':job.get('algorithm_version_id'),'source_hash':job.get('source_hash'),'library_source_hash':job.get('library_source_hash'),'created_at':job['created_at']}
        (output/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
        manifest=[]
        for file in sorted(output.iterdir()):
            if not file.is_file() or file.is_symlink() or file.suffix not in {'.json','.csv','.png','.svg','.pdf'}:continue
            if file.stat().st_size>100*1024**2:raise ValueError('单个结果文件超过 100 MB。')
            manifest.append({'name':file.name,'size':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        job.update(status='succeeded',result=result,files=manifest,completed_at=db.now());db.put('runs',job)
        if job.get('validation'):
            version=require('algorithm_versions',job['algorithm_version_id']);version.update(validation_status='passed',validation_run_id=job['id']);db.put('algorithm_versions',version)
    except Exception as exc:
        job=require('runs',run_id)
        if job['status']!='running':return
        job.update(status='failed',error=exc.message if isinstance(exc,packages.Fault) else str(exc),completed_at=db.now());db.put('runs',job)
        if job.get('validation'):
            version=require('algorithm_versions',job['algorithm_version_id']);version.update(validation_status='failed',validation_run_id=job['id']);db.put('algorithm_versions',version)


def submit(request,public,**extra):
    if sum(r['status'] in {'queued','running'} for r in db.all_rows('runs'))>=12:raise packages.Fault('QUEUE_FULL','等待或运行的任务较多，请稍后再试。',429)
    job={'id':db.uid(),'kind':request['kind'],'status':'queued','created_at':db.now(),'request':public,'files':[],**extra}
    db.put('runs',job);job_path(job).mkdir(parents=True,exist_ok=True)
    POOL.submit(execute_job,job['id'],request)
    return job


def dataset_path(dataset):
    return area()/'datasets'/dataset['id']/'output/data.csv'


def example_request(version):
    root=area()/'examples'
    return {'kind':'algorithm','engine':version['engine'],'source_root':version['source_root'],'plugin_root':version.get('plugin_root'),'entrypoint':version.get('entrypoint'),'name':version['name'],'expected_spec_version':version['upstream_version'],'task':version['task'],'params':version['defaults'],'dataset_path':str(root/'matrix.csv'),'selection':{'sample_column':'sample_id','target_column':'group' if version['task']=='classification' else '', 'group_column':'group' if version['task']!='classification' else '', 'features':['feature_1','feature_2','feature_3','feature_4']},'scale':False}


def recover():
    for run in db.all_rows('runs'):
        if run['status'] in {'queued','running'}:
            run.update(status='interrupted',error='服务重启，任务已中断；请重新提交。',completed_at=db.now());db.put('runs',run)
    for version in db.all_rows('algorithm_versions'):
        if version['validation_status']=='running':
            version['validation_status']='pending';db.put('algorithm_versions',version)


def shutdown():
    recover()
    with PROCESS_LOCK:
        for process in list(PROCESSES.values()):
            if process.poll() is None:process.terminate()


@router.get('/algorithms')
def algorithms(archived:bool=False):
    return {'items':[entry_view(e) for e in sorted(db.all_rows('algorithms'),key=lambda e:e['name']) if bool(e.get('archived_at'))==archived]}


@router.get('/algorithms/{key}')
def algorithm(key):return entry_view(require('algorithms',key))


@router.patch('/algorithms/{key}')
def edit_algorithm(key,payload:dict):
    with db.transaction():
        entry=available_algorithm(key)
        if payload.get('updated_at') and payload['updated_at']!=entry['updated_at']:raise packages.Fault('REVISION_CONFLICT','算法展示信息已更新，请刷新后再保存。',409)
        for name,limit in [('display_name',120),('description',1200),('category',80)]:
            if name in payload:entry[name]=text(payload[name],name,limit,required=True)
        if 'enabled' in payload:
            if not isinstance(payload['enabled'],bool):raise packages.Fault('INVALID_REQUEST','启用状态必须为布尔值。')
            if payload['enabled'] and not entry.get('active_version_id'):raise packages.Fault('NOT_PUBLISHED','请先验证并发布一个版本。')
            entry['enabled']=payload['enabled']
        entry['updated_at']=db.now();db.put('algorithms',entry)
    return entry_view(entry)


@router.post('/algorithms/{key}/archive')
def archive_algorithm(key,payload:dict):
    archived=payload.get('archived',True)
    if not isinstance(archived,bool):raise packages.Fault('INVALID_REQUEST','删除状态必须为布尔值。')
    with db.transaction():
        entry=require('algorithms',key)
        if payload.get('updated_at') and payload['updated_at']!=entry['updated_at']:raise packages.Fault('REVISION_CONFLICT','算法信息已变化，请刷新后重试。',409)
        if bool(entry.get('archived_at'))!=archived:
            if archived:
                entry.update(archived_at=db.now(),enabled_before_archive=entry['enabled'],enabled=False)
            else:
                entry.update(archived_at=None,enabled=bool(entry.pop('enabled_before_archive',False) and entry.get('active_version_id')))
            entry['updated_at']=db.now();db.put('algorithms',entry)
    return entry_view(entry)


@router.post('/algorithms',status_code=201)
def add_algorithm(payload:dict):
    name=text(payload.get('name'),'标准名称',64,True)
    if not SLUG.fullmatch(name) or any(e['name']==name for e in db.all_rows('algorithms')):raise packages.Fault('INVALID_REQUEST','标准名称须为未使用的小写字母、数字和连字符。')
    base_entry=available_algorithm(payload.get('base_algorithm_id',''));base=revision(base_entry)
    entry={'id':db.uid(),'name':name,'display_name':text(payload.get('display_name'),'展示名称',120,True),'description':text(payload.get('description') or base_entry['description'],'用途说明',1200,True),'category':base_entry['category'],'origin':'configuration','base_algorithm_id':base_entry['id'],'enabled':False,'active_version_id':None,'created_at':db.now(),'updated_at':db.now()}
    with db.transaction():
        db.put('algorithms',entry);version=create_version(entry,base,payload.get('defaults',base['defaults']),'从已有算法建立参数配置')
    return {**entry_view(entry),'new_version':version_view(version)}


@router.post('/algorithms/{key}/versions',status_code=201)
def new_version(key,payload:dict):
    with db.transaction():
        entry=available_algorithm(key);base=revision(entry,{'version_id':payload.get('base_version_id') or entry.get('active_version_id')})
        value=create_version(entry,base,payload.get('defaults',base['defaults']),payload.get('change_note','参数更新'))
    return version_view(value)


@router.post('/algorithms/{key}/versions/{version_id}/validate',status_code=202)
def validate_version(key,version_id):
    entry=available_algorithm(key);version=revision(entry,{'version_id':version_id})
    if version['validation_status']=='catalog_only':raise packages.Fault('NOT_SUPPORTED','该算法首版只提供目录，尚未接入运行适配。')
    request=example_request(version)
    job=submit(request,{'kind':'validation','algorithm_id':key,'algorithm_name':entry['display_name'],'params':version['defaults'],'dataset':'内置合成示例'},algorithm_id=key,algorithm_version_id=version_id,source_hash=version['source_hash'],validation=True)
    version.update(validation_status='running',validation_run_id=job['id']);db.put('algorithm_versions',version)
    return job


@router.post('/algorithms/{key}/versions/{version_id}/publish')
def publish_version(key,version_id,payload:dict):
    with db.transaction():
        entry=available_algorithm(key);version=revision(entry,{'version_id':version_id})
        if version['validation_status']!='passed':raise packages.Fault('NOT_VALIDATED','版本需先通过示例运行验证。')
        if 'expected_active_version_id' in payload and payload['expected_active_version_id']!=entry.get('active_version_id'):raise packages.Fault('REVISION_CONFLICT','当前发布版本已变化，请刷新后重试。',409)
        if not version.get('published_at'):version['published_at']=db.now();db.put('algorithm_versions',version)
        entry.update(active_version_id=version_id,enabled=True,updated_at=db.now());db.put('algorithms',entry)
    return entry_view(entry)


@router.post('/algorithm-packages',status_code=201)
async def import_algorithm(file:UploadFile=File(...),algorithm_id:str=Form('')):
    data=await file.read(8*1024**2+1)
    if len(data)>8*1024**2 or not (file.filename or '').lower().endswith('.zip'):raise packages.Fault('INVALID_PACKAGE','请选择不超过 8 MB 的算法 ZIP 包。')
    digest=hashlib.sha256(data).hexdigest();root=area()/'plugins'/digest
    if not root.exists():
        root.mkdir(parents=True);packages.extract_zip(data,root)
    if len(packages.files(root))>100:raise packages.Fault('INVALID_PACKAGE','算法包最多包含 100 个文件。')
    try:manifest=json.loads((root/'algorithm.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):raise packages.Fault('INVALID_PACKAGE','算法包根目录需要 algorithm.json。')
    name=text(manifest.get('name'),'标准名称',64,True)
    entrypoint=manifest.get('entrypoint','')
    if not re.fullmatch(r'[a-z0-9]+(?:[-_][a-z0-9]+)*',name) or not re.fullmatch(r'algorithm\.py:[A-Za-z][A-Za-z0-9_]{0,79}',entrypoint) or not (root/'algorithm.py').is_file():raise packages.Fault('INVALID_PACKAGE','入口必须为 algorithm.py:类名，且提供对应源码。')
    task=manifest.get('task')
    if task not in TASKS:raise packages.Fault('INVALID_PACKAGE','不支持的算法任务。')
    schema=validate_schema(manifest.get('parameters',{}));defaults=parameters(schema,{})
    base=next((v for v in db.all_rows('algorithm_versions') if v.get('source_root')),None)
    if not base:raise packages.Fault('SETUP_REQUIRED','请先初始化内置算法环境。')
    with db.transaction():
        if algorithm_id:
            entry=available_algorithm(algorithm_id)
            if entry['name']!=name:raise packages.Fault('INVALID_PACKAGE','新版本清单名称必须与当前算法一致。')
        else:
            if any(e['name']==name for e in db.all_rows('algorithms')):raise packages.Fault('DUPLICATE_ALGORITHM','同名算法已存在，请从详情导入新版本。',409)
            entry={'id':db.uid(),'name':name,'display_name':text(manifest.get('display_name',name),'展示名称',120,True),'description':text(manifest.get('description'),'用途说明',1200,True),'category':{'classification':'分类','clustering':'聚类','feature_selection':'特征选择'}[task],'origin':'package','enabled':False,'active_version_id':None,'created_at':db.now(),'updated_at':db.now()};db.put('algorithms',entry)
        version=create_version(entry,{'engine':'plugin','name':name,'task':task,'parameters':schema,'source_root':base['source_root'],'library_source_hash':base.get('library_source_hash',base['source_hash']),'plugin_root':str(root),'entrypoint':entrypoint,'source_hash':digest,'upstream_version':text(manifest.get('version','0.1.0'),'版本号',80)},defaults,'导入算法源码包；尚未执行')
    return {**entry_view(entry),'new_version':version_view(version)}


@router.post('/datasets',status_code=201)
async def upload_dataset(file:UploadFile=File(...)):
    filename=Path(file.filename or 'data.csv').name
    if Path(filename).suffix.lower() not in {'.csv','.tsv','.txt','.xlsx'}:raise packages.Fault('INVALID_DATASET','支持 CSV、TSV、制表符 TXT 和 XLSX。')
    data=await file.read(10*1024**2+1)
    if not data or len(data)>10*1024**2:raise packages.Fault('INVALID_DATASET','数据文件不能为空且最多为 10 MB。')
    key=db.uid();folder=area()/'datasets'/key;folder.mkdir(parents=True);raw=folder/('upload'+Path(filename).suffix.lower());raw.write_bytes(data)
    try:description=await run_in_threadpool(invoke,{'kind':'inspect','dataset_path':str(raw)},folder,timeout=45)
    except Exception:
        shutil.rmtree(folder);raise
    dataset={'id':key,'filename':filename,'sha256':hashlib.sha256(data).hexdigest(),'canonical_sha256':hashlib.sha256((folder/'output/data.csv').read_bytes()).hexdigest(),'created_at':db.now(),**description}
    db.put('datasets',dataset);return dataset


@router.get('/datasets/{key}')
def dataset(key):return require('datasets',key)


@router.get('/examples/{name}')
def example(name):
    if name not in {'matrix','abundance','importance','workflow','algorithm-package'}:raise packages.Fault('NOT_FOUND','示例不存在。',404)
    suffix='.zip' if name=='algorithm-package' else '.csv';path=area()/'examples'/(name+suffix)
    if not path.exists():raise packages.Fault('SETUP_REQUIRED','示例尚未初始化。',503)
    return FileResponse(path,filename='bioflow-example-'+name+suffix)


@router.get('/plots')
def plots():
    result=[]
    for r in RECIPES:
        s=next((s for s in db.all_rows('skills') if s['skill_name']=='bioflow-plot-'+r['id']),None)
        result.append({**r,'skill_id':s['id'] if s else None,'skill_revision_id':s.get('published_revision_id') if s else None})
    return {'items':result}


@router.get('/plots/{key}/preview')
def plot_preview(key):
    if not recipe(key):raise packages.Fault('NOT_FOUND','绘图模板不存在。',404)
    path=area()/'examples'/key/'figure.png'
    if not path.exists():raise packages.Fault('SETUP_REQUIRED','示例尚未初始化。',503)
    return FileResponse(path,media_type='image/png')


@router.post('/runs',status_code=202)
def create_run(payload:dict):
    dataset=require('datasets',payload.get('dataset_id',''));kind=payload.get('kind','algorithm')
    public={'kind':kind,'dataset_id':dataset['id'],'dataset_name':dataset['filename'],'selection':payload.get('selection',{}),'params':payload.get('params',{}),'scale':bool(payload.get('scale',False)),'plot_options':payload.get('plot_options',{})}
    if not isinstance(public['selection'],dict) or not isinstance(public['plot_options'],dict):raise packages.Fault('INVALID_REQUEST','列选择或绘图设置需要是对象。')
    request={'kind':kind,'dataset_path':str(dataset_path(dataset)),'plot_options':public['plot_options']}
    extra={'dataset_id':dataset['id'],'dataset_sha256':dataset['sha256'],'canonical_dataset_sha256':dataset['canonical_sha256']}
    if kind=='algorithm':
        entry=available_algorithm(payload.get('algorithm_id',''));version=revision(entry,payload)
        if not entry['enabled'] or version['validation_status']!='passed' or not version.get('published_at'):raise packages.Fault('ALGORITHM_DISABLED','请选择已验证、已发布且启用的算法版本。')
        values=parameters(version['parameters'],payload.get('params',version['defaults']));public.update(algorithm_id=entry['id'],algorithm_name=entry['display_name'],params=values)
        request.update(engine=version['engine'],source_root=version['source_root'],plugin_root=version.get('plugin_root'),entrypoint=version.get('entrypoint'),name=version['name'],expected_spec_version=version['upstream_version'],task=version['task'],params=values,selection=public['selection'],scale=public['scale'])
        extra.update(algorithm_id=entry['id'],algorithm_version_id=version['id'],source_hash=version['source_hash'],library_source_hash=version.get('library_source_hash',version['source_hash']))
    elif kind=='plot':
        if not recipe(payload.get('template_id')):raise packages.Fault('INVALID_REQUEST','请选择有效绘图模板。')
        request.update(template_id=payload['template_id'],mapping=public['selection']);public['template_id']=payload['template_id']
    else:raise packages.Fault('INVALID_REQUEST','不支持的任务类型。')
    return submit(request,public,**extra)


@router.get('/runs')
def runs():return {'items':sorted(db.all_rows('runs'),key=lambda r:r['created_at'],reverse=True)[:100]}


@router.get('/runs/{key}')
def run(key):return run_view(require('runs',key))


@router.post('/runs/{key}/cancel')
def cancel(key):
    job=require('runs',key)
    if job['status'] in {'queued','running'}:
        job.update(status='cancelled',completed_at=db.now());db.put('runs',job)
        with PROCESS_LOCK:
            process=PROCESSES.get(key)
            if process:process.terminate()
    return job


@router.post('/runs/{key}/replot',status_code=202)
def replot(key,payload:dict):
    parent=require('runs',key)
    if parent['status']!='succeeded':raise packages.Fault('RUN_NOT_READY','请等待算法运行成功后再重绘。')
    template=payload.get('template_id');source=parent.get('result',{}).get('plot_sources',{}).get(template)
    if not source:raise packages.Fault('INVALID_REQUEST','该结果不提供所选绘图模板需要的数据。')
    request={'kind':'plot','dataset_path':str(job_path(parent)/'output'/source['file']),'template_id':template,'mapping':source['mapping'],'plot_options':payload.get('plot_options',{})}
    public={'kind':'plot','template_id':template,'parent_run_id':key,'mapping':source['mapping'],'plot_options':request['plot_options'],'dataset_name':'已有算法结果'}
    return submit(request,public,parent_run_id=key,algorithm_version_id=parent.get('algorithm_version_id'),dataset_sha256=parent.get('dataset_sha256'),canonical_dataset_sha256=parent.get('canonical_dataset_sha256'),source_hash=parent.get('source_hash'),library_source_hash=parent.get('library_source_hash'))


@router.get('/runs/{key}/files/{name}')
def run_file(key,name,download:bool=True):
    job=require('runs',key)
    if job['status']!='succeeded' or name not in {f['name'] for f in job['files']}:raise packages.Fault('NOT_FOUND','结果文件不存在。',404)
    path=packages.safe(job_path(job)/'output',name)
    if path.is_symlink():raise packages.Fault('INVALID_PATH','结果路径不合法。')
    if name.endswith('.png') and not download:return FileResponse(path,media_type='image/png')
    if name.endswith('.csv') and not download:
        # Bounded preview; no scientific dependencies in the API process.
        import csv
        with path.open(encoding='utf-8',newline='') as stream:
            reader=csv.DictReader(stream);columns=reader.fieldnames or [];rows=[]
            for i,row in enumerate(reader):
                if i>=20:break
                rows.append(row)
        return {'columns':columns[:30],'rows':[{k:v for k,v in r.items() if k in columns[:30]} for r in rows]}
    return FileResponse(path,filename=name)


@router.get('/runs/{key}/export')
def export_run(key):
    job=require('runs',key)
    if job['status']!='succeeded':raise packages.Fault('RUN_NOT_READY','任务尚未完成。')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for f in job['files']:
            path=packages.safe(job_path(job)/'output',f['name']);archive.write(path,f['name'])
    return Response(buffer.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="bioflow-run-{key}.zip"'})
