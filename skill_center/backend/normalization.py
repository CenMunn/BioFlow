"""Minimal, explicit metadata normalization for a fork. Never edits upstream originals."""
import json
import re
from pathlib import PurePosixPath

import yaml

from . import main,packages


def normalize_copy(client,sid,rid,modules,category,summary=None):
    original=client.get('/api/v1/skills/'+sid).json()
    rev=client.get(f'/api/v1/skills/{sid}/revisions/{rid}').json()
    raw=packages.safe(main.db.revision_root(rev),rev['entry_path']).read_bytes()
    fields,body,text=packages.metadata(raw)
    fields=dict(fields);changes=[]
    name=fields.get('name')
    if not isinstance(name,str) or len(name)>64 or not packages.NAME.fullmatch(name):
        candidate=PurePosixPath(rev['entry_path']).parent.name
        candidate=re.sub('[^a-z0-9]+','-',candidate.lower()).strip('-')[:64].rstrip('-')
        if not candidate: candidate='normalized-skill-'+sid[:8]
        fields['name']=candidate;changes.append('name 改为与技能目录相符的标准标识')
    if PurePosixPath(rev['entry_path']).parent.name!=fields['name']:
        changes.append('技能目录调整为标准名称')
    meta=fields.get('metadata',{})
    if not isinstance(meta,dict): meta={'upstream_metadata':json.dumps(meta,ensure_ascii=False,default=str)}
    normalized_meta={str(k):v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,default=str) for k,v in meta.items()}
    if meta!=normalized_meta:
        changes.append('metadata 非字符串值保留为 JSON 字符串')
    if normalized_meta: fields['metadata']=normalized_meta
    for key in ('allowed-tools','license'):
        if key in fields and not isinstance(fields[key],str):
            value=fields[key]
            fields[key]=' '.join(value) if key=='allowed-tools' and isinstance(value,list) and all(isinstance(x,str) for x in value) else json.dumps(value,ensure_ascii=False,default=str)
            changes.append(key+' 规范为字符串')
    # Preserve uncommon long source metadata, rather than silently discarding it.
    if 'compatibility' in fields and (not isinstance(fields['compatibility'],str) or not 1<=len(fields['compatibility'])<=500):
        fields.setdefault('metadata',{})['upstream_compatibility']=json.dumps(fields['compatibility'],ensure_ascii=False,default=str)
        fields['compatibility']='完整上游环境要求见 metadata.upstream_compatibility。'
        changes.append('完整兼容要求保留在扩展元数据中')
    description=fields.get('description')
    if not isinstance(description,str) or not 1<=len(description)<=1024:
        fields.setdefault('metadata',{})['upstream_description']=json.dumps(description,ensure_ascii=False,default=str)
        fields['description']=(summary or original.get('description') or '按正文说明处理用户任务，实际执行需配置匹配环境。')[:1024]
        changes.append('用途描述规范为字符串，原值保留')
    rewritten='---\n'+yaml.safe_dump(fields,allow_unicode=True,sort_keys=False)+'---\n'+body
    existing=next((s for s in main.db.all_rows('skills') if s.get('parent_skill_id')==sid and s.get('parent_revision_id')==rid and '规范副本' in s.get('tags',[]) and s.get('published_revision_id') and not s.get('archived_at')),None)
    if existing:
        child=existing['id'];published=main.db.get('revisions',existing['published_revision_id'])
        if packages.safe(main.db.revision_root(published),published['entry_path']).read_bytes()!=rewritten.encode('utf-8'):
            raise ValueError('Existing normalized copy has changed; explicit review required')
    else:
        display=original['display_name'].removesuffix('（原版·格式待修复）')+'（规范副本）'
        fork=client.post(f'/api/v1/skills/{sid}/fork',json={'revision_id':rid,'display_name':display})
        if fork.status_code!=201: raise ValueError(fork.text)
        fork=fork.json();draft=fork['draft'];child=fork['skill']['id']
        update=client.patch(f'/api/v1/drafts/{draft["id"]}/files',json={'draft_counter':draft['draft_counter'],'changes':[{'path':draft['entry_path'],'content':rewritten}]})
        if update.status_code!=200: raise ValueError(update.text)
        updated=update.json()
        if updated['diagnostics']['errors']: raise ValueError(json.dumps(updated['diagnostics'],ensure_ascii=False))
        pub=client.post(f'/api/v1/drafts/{draft["id"]}/publish',json={'draft_counter':updated['draft_counter'],'change_note':'规范副本：'+ '；'.join(changes)+'。正文与资源未改写，原版和父版本保留。'})
        if pub.status_code!=201: raise ValueError(pub.text)
        published=pub.json()
    # Assert the body is unchanged and every non-entry file is preserved byte-for-byte,
    # allowing only the declared directory rename.
    normalized_root=main.db.revision_root(published)
    _,new_body,_=packages.metadata(packages.safe(normalized_root,published['entry_path']).read_bytes())
    if new_body!=body: raise ValueError('Normalization changed the skill body')
    old_parent=str(PurePosixPath(rev['entry_path']).parent)
    new_parent=str(PurePosixPath(published['entry_path']).parent)
    for f in rev['files']:
        if f['path']==rev['entry_path']:continue
        dest=new_parent+f['path'][len(old_parent):] if f['path'].startswith(old_parent+'/') else f['path']
        if packages.safe(main.db.revision_root(rev),f['path']).read_bytes()!=packages.safe(normalized_root,dest).read_bytes():raise ValueError('Resource bytes changed: '+f['path'])
    patch=client.patch('/api/v1/skills/'+child,json={'applicable_modules':modules,'category':category,'tags':['用户选定来源','规范副本'],'display_summary':summary or original.get('display_summary','')})
    if patch.status_code!=200: raise ValueError(patch.text)
    client.patch('/api/v1/skills/'+sid,json={'enabled':False,'applicable_modules':[],'display_name':original['display_name'].removesuffix('（原版·格式待修复）')+'（原版·格式待修复）'})
    return {'skill_id':child,'revision_id':published['id'],'original_skill_id':sid,'original_revision_id':rid,'normalization_changes':changes,'body_unchanged':True,'resources_unchanged':True}
