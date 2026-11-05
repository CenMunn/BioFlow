"""Scientific work runs in a separate, time-limited process, never in the API."""
import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

import numpy as np
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from backend.workbench_plotting import numeric,render_table


def jsonable(value):
    if isinstance(value,dict):return {str(k):jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [jsonable(v) for v in value]
    if isinstance(value,np.generic):return jsonable(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    if isinstance(value,pd.Series):return value.to_dict()
    return str(value)


def write_json(path,value):
    Path(path).write_text(json.dumps(jsonable(value),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def read_table(path):
    path=Path(path)
    if path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        workbook=load_workbook(path,read_only=True,data_only=True)
        sheet=workbook.worksheets[0]
        if sheet.max_row>20001 or sheet.max_column>501:raise ValueError('表格最多 20000 行、500 列。')
        rows=list(sheet.iter_rows(values_only=True));workbook.close()
        if len(rows)<2:raise ValueError('表格需要表头和数据行。')
        headers=[str(x).strip() if x is not None else '' for x in rows[0]]
        frame=pd.DataFrame(rows[1:],columns=headers)
    else:
        delimiter='\t' if path.suffix.lower() in {'.tsv','.txt'} else ','
        with path.open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.reader(stream,delimiter=delimiter))
        if not rows or len(rows)<2:raise ValueError('文件需要表头和数据行；TXT 使用制表符分隔。')
        headers=[x.strip() for x in rows[0]]
        if len(rows)>20001 or len(headers)>500:raise ValueError('表格最多 20000 行、500 列。')
        if any(len(r)!=len(headers) for r in rows[1:]):raise ValueError('每行列数必须与表头一致。')
        frame=pd.read_csv(path,sep=delimiter,encoding='utf-8-sig',dtype=str,keep_default_na=False)
        frame.columns=headers
        frame=frame.replace('',np.nan)
        for column in frame.columns:
            if str(column).lower() in {'sample_id','sample','id','subject_id','样本编号','样本id','group','label','class','分组'}:continue
            try:frame[column]=pd.to_numeric(frame[column],errors='raise')
            except (TypeError,ValueError):pass
    if not headers or any(not h or len(h)>120 for h in headers) or len(set(headers))!=len(headers):raise ValueError('列名不能为空或重复，长度最多 120 字符。')
    if frame.empty or frame.size>2000000:raise ValueError('表格为空或超过 200 万单元格。')
    if len(frame)>20000 or len(headers)>500:raise ValueError('表格最多 20000 行、500 列。')
    return frame


def describe(frame):
    return {'rows':len(frame),'columns':[{'name':str(c),'numeric':pd.api.types.is_numeric_dtype(frame[c]),'missing':int(frame[c].isna().sum()),'unique':int(frame[c].nunique())} for c in frame.columns], 'preview':jsonable(frame.head(8).replace({np.nan:None}).to_dict(orient='records'))}


def import_library(root):
    root=Path(root)
    if not (root/'core.py').is_file():raise ValueError('算法库目录缺少 core.py。')
    sys.path.insert(0,str(root.parent))
    import bioflow_ml
    if Path(bioflow_ml.__file__).resolve()!=root.resolve()/'__init__.py':raise ValueError('算法库来源路径不匹配。')
    return bioflow_ml


def run_algorithm(request,out):
    library=import_library(request['source_root'])
    frame=read_table(request['dataset_path'])
    selection=request['selection'];features=selection.get('features',[])
    sample=selection.get('sample_column');target=selection.get('target_column');group=selection.get('group_column')
    if len(features)<2 or len(set(features))!=len(features):raise ValueError('请选择至少两个不同的数值特征。')
    if set(features)&{sample,target,group}:raise ValueError('样本标识、分组和标签列不能作为特征。')
    X=numeric(frame,features)
    if sample:
        if sample not in frame or frame[sample].isna().any() or frame[sample].astype(str).duplicated().any():raise ValueError('样本标识必须存在、完整且唯一。')
        X.index=pd.Index(frame[sample].astype(str),name='sample_id')
    else:X.index=pd.Index([f'S{i+1}' for i in range(len(frame))],name='sample_id')
    if len(X)<4:raise ValueError('至少需要 4 个样本。')
    y=None
    if target:
        if target not in frame or frame[target].isna().any():raise ValueError('分类标签列不存在或有缺失。')
        y=pd.Series(frame[target].to_numpy(),index=X.index,name=target)
    engine=request['engine'];params=request['params'].copy()
    if engine=='random_forest':params['n_jobs']=1
    if request.get('plugin_root'):
        entry=request['entrypoint'];module_file,class_name=entry.split(':')
        plugin=Path(request['plugin_root'])/module_file
        spec=importlib.util.spec_from_file_location('bioflow_custom_algorithm',plugin)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cls=getattr(module,class_name)
        if not isinstance(cls,type) or not issubclass(cls,library.BaseAlgorithm):raise ValueError('算法入口必须继承 BaseAlgorithm。')
        algorithm=cls(**params)
        if algorithm.spec.name!=request['name']:raise ValueError('AlgorithmSpec.name 与清单名称不符。')
    else:algorithm=library.registry.create(engine,**params)
    if request.get('scale'):
        from sklearn.preprocessing import StandardScaler
        X=pd.DataFrame(StandardScaler().fit_transform(X),index=X.index,columns=X.columns)
    task='classification' if engine=='random_forest' else request.get('task','clustering')
    if task=='classification':
        if y is None:raise ValueError('分类算法需要选择标签列。')
        if y.nunique()<2 or y.nunique()>20 or y.value_counts().min()<2:raise ValueError('分类需要 2～20 个类别，且每类至少两个样本。')
        if request.get('scale'):raise ValueError('本版分类流程不提供全量预标准化，以避免交叉验证数据泄漏。')
    if not isinstance(algorithm.spec,library.AlgorithmSpec):raise ValueError('算法需要声明 AlgorithmSpec。')
    if request.get('expected_spec_version') and algorithm.spec.version!=request['expected_spec_version']:raise ValueError('AlgorithmSpec.version 与算法清单版本不符。')
    result=algorithm.run(library.MLInput(X=X,y=y,task=task,params=params))
    if not isinstance(result,library.AlgorithmResult):raise ValueError('算法必须返回 AlgorithmResult。')
    result_metrics=jsonable(result.metrics)
    warnings=list(result.warnings)
    frames={};sources={}
    input_table=X.reset_index()
    if group and group in frame:input_table['group']=frame[group].fillna('(missing)').astype(str).to_numpy()
    input_table.to_csv(out/'input_values.csv',index=False)
    sources['heatmap']={'file':'input_values.csv','mapping':{'sample_column':'sample_id','features':features[:40]}}
    if result.transformed_data is not None:
        transformed=result.transformed_data.copy();transformed.index=X.index
        frames['transformed.csv']=transformed.reset_index()
        if transformed.shape[1]>=2:
            projection=transformed.iloc[:,:2].copy()
            if group and group in frame:projection['group']=frame[group].fillna('(missing)').astype(str).to_numpy()
            frames['projection.csv']=projection.reset_index()
            sources['scatter']={'file':'projection.csv','mapping':{'sample_column':'sample_id','x_column':str(transformed.columns[0]),'y_column':str(transformed.columns[1]),'group_column':'group' if group else ''}}
    if result.labels is not None:
        labels=pd.Series(result.labels.to_numpy(),index=X.index,name='cluster')
        frames['labels.csv']=labels.reset_index()
        from sklearn.decomposition import PCA
        projection=pd.DataFrame(PCA(n_components=2,svd_solver='full').fit_transform(X),index=X.index,columns=['PC1','PC2'])
        projection['cluster']=labels.astype(str)
        frames['projection.csv']=projection.reset_index()
        sources['scatter']={'file':'projection.csv','mapping':{'sample_column':'sample_id','x_column':'PC1','y_column':'PC2','group_column':'cluster'}}
        warnings.append('聚类在选定特征空间计算；散点图为额外 PCA 二维投影，仅用于展示。')
    if result.predictions is not None:
        predictions=pd.DataFrame({'sample_id':X.index,'observed':y.to_numpy() if y is not None else '', 'prediction':result.predictions.to_numpy()})
        frames['predictions.csv']=predictions
        if engine=='random_forest':warnings.append('分类指标和预测采用原算法交叉验证；特征重要性来自全量数据拟合，不能当作外部验证或因果证据。')
    if result.feature_scores is not None:
        scores=result.feature_scores.copy();scores.index.name='feature'
        frames['feature_scores.csv']=scores.reset_index()
        column='importance' if 'importance' in scores else 'score' if 'score' in scores else str(scores.columns[0])
        sources['importance']={'file':'feature_scores.csv','mapping':{'x_column':'feature','y_column':column}}
    for name,data in frames.items():data.to_csv(out/name,index=False)
    pd.DataFrame([{'metric':k,'value':v} for k,v in result_metrics.items()]).to_csv(out/'metrics.csv',index=False)
    default='scatter' if 'scatter' in sources else 'importance' if 'importance' in sources else 'heatmap'
    plot_source=sources[default]
    try:
        warnings+=render_table(pd.read_csv(out/plot_source['file']),default,plot_source['mapping'],request.get('plot_options',{}),out)
    except ValueError as e:
        warnings.append('结果已保存；默认绘图未生成：'+str(e))
    return {'metrics':result_metrics,'warnings':warnings,'plot_sources':sources,'default_template':default,'rows':len(X),'features':features,'algorithm_spec':{'name':algorithm.spec.name,'version':algorithm.spec.version}}


def execute(path):
    request=json.loads(Path(path).read_text(encoding='utf-8'));out=Path(request['output_dir']);out.mkdir(parents=True,exist_ok=True)
    kind=request['kind']
    if kind=='inspect':
        frame=read_table(request['dataset_path']);frame.to_csv(out/'data.csv',index=False);result=describe(frame)
    elif kind=='algorithm':result=run_algorithm(request,out)
    elif kind=='plot':
        frame=read_table(request['dataset_path'])
        notes=render_table(frame,request['template_id'],request['mapping'],request.get('plot_options',{}),out)
        result={'warnings':notes,'template_id':request['template_id'],'rows':len(frame)}
    elif kind=='catalog':
        library=import_library(request['source_root']);result={'items':library.get_algorithm_catalog()}
    else:raise ValueError('未知任务类型。')
    result['environment']={name:importlib.metadata.version(name) for name in ['numpy','pandas','scikit-learn','matplotlib','openpyxl']}
    write_json(out/'result.json',result)
    print('Completed:',kind,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('request');args=parser.parse_args()
    try:
        if os.name!='nt':
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(120,120))
            resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
            resource.setrlimit(resource.RLIMIT_FSIZE,(100*1024**2,100*1024**2))
        execute(args.request)
    except Exception as exc:
        traceback.print_exc()
        try:
            req=json.loads(Path(args.request).read_text());write_json(Path(req['output_dir'])/'error.json',{'message':str(exc)[:2000]})
        except Exception:pass
        sys.exit(1)
