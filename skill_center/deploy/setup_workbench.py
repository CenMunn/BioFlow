"""Initialize only the additive workbench; never write to the source algorithm library."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import sys
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from backend import db,main,workbench
from backend.workbench_catalog import NAMES,PARAMETERS,RECIPES


def examples(root):
    root.mkdir(parents=True,exist_ok=True)
    rng=random.Random(42)
    with (root/'matrix.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['sample_id','group','feature_1','feature_2','feature_3','feature_4'])
        for i in range(24):
            shift=0 if i<12 else 2
            writer.writerow([f'S{i+1:02d}','Control' if i<12 else 'Case',*[round(rng.gauss(shift if j<2 else 0,1),5) for j in range(4)]])
    with (root/'abundance.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['sample_id','Taxon_A','Taxon_B','Taxon_C','Taxon_D'])
        for i in range(8):writer.writerow([f'S{i+1}',*[rng.randint(10,100) for _ in range(4)]])
    (root/'importance.csv').write_text('feature,importance\nFeature_A,0.38\nFeature_B,0.27\nFeature_C,0.18\nFeature_D,0.11\nFeature_E,0.06\n',encoding='utf-8')
    (root/'workflow.csv').write_text('step\nResearch question\nSample collection\nData processing\nStatistical analysis\nFigure review\n',encoding='utf-8')
    manifest={'name':'variance-ranking','display_name':'方差排序（新增算法示例）','version':'0.1.0','description':'对已选择的数值特征按样本方差排序，输出分数与选中特征。用于演示增量算法接入，不代表生物学显著性。','task':'feature_selection','entrypoint':'algorithm.py:VarianceRanking','parameters':{'top_k':{'label':'保留特征数','type':'integer','default':3,'min':1,'max':100}}}
    code='''from bioflow_ml.core import BaseAlgorithm, AlgorithmSpec, AlgorithmResult
class VarianceRanking(BaseAlgorithm):
    spec=AlgorithmSpec(name="variance-ranking",version="0.1.0",tasks=("feature_selection",),description="Rank selected features by sample variance")
    def run(self,data):
        top_k=int(self.merged_params(data).get("top_k",3))
        scores=data.X.var(axis=0).sort_values(ascending=False).to_frame("score")
        return AlgorithmResult(algorithm=self.spec.name,feature_scores=scores,transformed_data=data.X[scores.index[:top_k]],metadata={"top_k":top_k},warnings=["Variance ranking is not a significance test."])
'''
    with zipfile.ZipFile(root/'algorithm-package.zip','w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('algorithm.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        archive.writestr('algorithm.py',code)
        archive.writestr('README.md','# Incremental algorithm example\nUses the existing MLInput / AlgorithmResult contract.\nImport, validate on the synthetic example, then publish before use.\n')


def source_snapshot(root):
    entries=[]
    for p in sorted(root.rglob('*.py')):
        rel=p.relative_to(root)
        if any(x in {'tests','__pycache__','.venv','venv'} for x in rel.parts):continue
        entries.append((rel,p.read_bytes()))
    if not any(str(p)=='core.py' for p,_ in entries):raise ValueError('Expected the existing bioflow_ml source folder')
    digest=hashlib.sha256(b''.join(str(p).encode()+b'\0'+hashlib.sha256(data).digest() for p,data in entries)).hexdigest()
    target=workbench.area()/'sources'/digest/'bioflow_ml'
    for rel,data in entries:
        dest=target/rel
        if dest.exists() and dest.read_bytes()!=data:raise ValueError('Source snapshot mismatch')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    return digest,target


def initialize(source):
    example_root=workbench.area()/'examples';examples(example_root)
    digest,snapshot=source_snapshot(source)
    catalog=workbench.invoke({'kind':'catalog','source_root':str(snapshot)},workbench.area()/'setup/catalog',timeout=45)
    for item in catalog['items']:
        name=item['name'];schema=PARAMETERS.get(name,{})
        entry=next((e for e in db.all_rows('algorithms') if e['origin']=='builtin' and e['name']==name),None)
        if entry is None:
            task=item['tasks'][0]
            category='降维' if name in {'pca','tsne','umap'} else {'classification':'分类','clustering':'聚类','feature_selection':'特征选择'}.get(task,task)
            entry={'id':db.uid(),'name':name,'display_name':NAMES.get(name,name),'description':item['description'],'category':category,'origin':'builtin','enabled':False,'active_version_id':None,'created_at':db.now(),'updated_at':db.now(),'input_requirements':item.get('input_requirements',[]),'output_description':item.get('output_description',''),'notes':item.get('notes','')}
            db.put('algorithms',entry)
        version=next((v for v in db.all_rows('algorithm_versions') if v['algorithm_id']==entry['id'] and v['source_hash']==digest),None)
        if version is None:
            base={'engine':name,'name':name,'task':item['tasks'][0],'parameters':schema,'source_root':str(snapshot),'source_hash':digest,'upstream_version':item['version']}
            version=workbench.create_version(entry,base,{k:v['default'] for k,v in schema.items()},'读取现有算法源码快照，原实现未修改')
            if name not in PARAMETERS:
                version['validation_status']='catalog_only';db.put('algorithm_versions',version)
        if name in PARAMETERS and version['validation_status']!='passed':
            request=workbench.example_request(version)
            job=workbench.submit(request,{'kind':'validation','algorithm_id':entry['id'],'algorithm_name':entry['display_name'],'params':version['defaults'],'dataset':'内置合成示例'},algorithm_id=entry['id'],algorithm_version_id=version['id'],source_hash=digest,validation=True)
            import time
            for _ in range(200):
                state=db.get('runs',job['id'])
                if state['status'] not in {'queued','running'}:break
                time.sleep(.5)
            if state['status']!='succeeded':raise RuntimeError(json.dumps(state,ensure_ascii=False))
            version=db.get('algorithm_versions',version['id'])
        if name in PARAMETERS and not entry.get('active_version_id'):
            version['published_at']=db.now();db.put('algorithm_versions',version)
            entry.update(active_version_id=version['id'],enabled=True,updated_at=db.now());db.put('algorithms',entry)
        print('CATALOG',name,version['validation_status'],flush=True)
    for item in RECIPES:
        folder=example_root/item['id']
        if not (folder/'figure.png').exists():
            workbench.invoke({'kind':'plot','dataset_path':str(example_root/(item['example']+'.csv')),'template_id':item['id'],'mapping':item['mapping'],'plot_options':{'title':'Synthetic example - '+item['id']}},folder)
            for p in (folder/'output').iterdir():
                if p.is_file():shutil.copy2(p,folder/p.name)
        standard='bioflow-plot-'+item['id']
        if any(s['skill_name']==standard for s in db.all_rows('skills')):continue
        stage=workbench.area()/'setup'/standard;skill_root=stage/standard
        for sub in ['scripts','templates','examples','assets']:(skill_root/sub).mkdir(parents=True,exist_ok=True)
        content=f'''---
name: {standard}
description: {item['summary']} 输入要求：{item['input']}。用于真实数据绘图或已有结果重绘。
metadata:
  template-id: {item['id']}
  author: BioFlow
  example-data: synthetic
---

# {item['name']}

{item['summary']}

## 输入与输出

{item['input']}。样本标识和分组应先核对；输入文件可参照 [合成示例](examples/data.csv)。
输出 PNG、SVG、PDF、作图数据 CSV 和设置 JSON。示例图仅展示格式，不代表真实研究结论。

![合成示例图](assets/example.png)

## 运行

安装 requirements.txt 中的绘图依赖后，运行：

```bash
python scripts/render.py --input examples/data.csv --output figure-output
```

列名、配色、标题和尺寸在 [默认模板](templates/default.json) 中设置，也可通过 --config 指定另一份 JSON 配置。
不自动删除异常值、不隐式补缺失值、不自动添加显著性星号。相对丰度图会明确记录行归一化；其他模板不改变数据含义。

## 模板与版本

页面绘图入口使用同一份绘图实现。技能正文、脚本、模板和示例完整保存；算法计算与绘图任务分别记录版本、参数和输入哈希。
'''
        (skill_root/'SKILL.md').write_text(content,encoding='utf-8')
        shutil.copy2(PROJECT/'backend/workbench_plotting.py',skill_root/'scripts/plotting.py')
        (skill_root/'scripts/render.py').write_text('''import argparse,json
from pathlib import Path
import pandas as pd
from plotting import render_table
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);parser.add_argument('--config',default=str(root/'templates/default.json'));args=parser.parse_args()
config=json.loads(Path(args.config).read_text(encoding='utf-8'))
render_table(pd.read_csv(args.input),config['template'],config['mapping'],config.get('options',{}),args.output)
''',encoding='utf-8')
        (skill_root/'templates/default.json').write_text(json.dumps({'template':item['id'],'mapping':item['mapping'],'options':{'palette':'forest','width':8,'height':5,'font_size':10,'title':'Synthetic example - '+item['id']}},ensure_ascii=False,indent=2),encoding='utf-8')
        shutil.copy2(example_root/(item['example']+'.csv'),skill_root/'examples/data.csv')
        shutil.copy2(folder/'figure.png',skill_root/'assets/example.png')
        (skill_root/'requirements.txt').write_text('numpy>=1.26,<3\npandas>=2.2,<3\nmatplotlib>=3.9,<3.11\n',encoding='utf-8')
        skill=main.new_skill(standard,item['name']+' · 模板 Skill',item['summary'],category='科研绘图模板',tags=['绘图模板','含合成示例','BioFlow'],applicable_modules=['analysis'])
        db.put('skills',skill)
        revision=main.snapshot(skill,stage,standard+'/SKILL.md','首版绘图模板与合成数据示例；未调用模型')
        if revision['diagnostics']['errors']:raise ValueError(revision['diagnostics'])
        print('PLOT_SKILL',standard,flush=True)
    print('SETUP_COMPLETE',json.dumps({'algorithms':len(db.all_rows('algorithms')),'templates':len(RECIPES),'catalog':main.modules_catalog()},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,default=PROJECT.parent/'bioflow_ml');args=parser.parse_args()
    initialize(args.source_root.resolve())
