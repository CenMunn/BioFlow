"""Portable deterministic figure templates; also shipped inside the six Skills."""
import json
import hashlib
from pathlib import Path
import textwrap

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.patches import FancyBboxPatch

PALETTES={'forest':['#527d60','#c6904b','#648ba5','#ac6e7b','#8c86ab','#a6a968'], 'blue':['#3478a0','#e49d48','#60a491','#ab739b','#7b8291','#c3b35e'], 'colorblind':['#0072B2','#E69F00','#009E73','#CC79A7','#D55E00','#56B4E9']}


def numeric(frame,columns):
    if not columns or any(c not in frame.columns for c in columns):raise ValueError('请选择存在的数值列。')
    data=frame[columns].apply(pd.to_numeric,errors='raise')
    if not np.isfinite(data.to_numpy(dtype=float)).all():raise ValueError('数值列不能包含缺失值或无穷值。')
    return data


def render_table(frame,template,mapping,options,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    colors=PALETTES.get(options.get('palette','forest'),PALETTES['forest'])
    width=float(options.get('width',8));height=float(options.get('height',5));font=int(options.get('font_size',10))
    if not (4<=width<=14 and 3<=height<=12 and 8<=font<=20):raise ValueError('图形尺寸或字体大小超出范围。')
    plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Noto Sans CJK SC','WenQuanYi Micro Hei','DejaVu Sans'],'font.size':font,'svg.fonttype':'none','pdf.fonttype':42,'axes.unicode_minus':False})
    fig,ax=plt.subplots(figsize=(width,height),layout='constrained')
    x=mapping.get('x_column');y=mapping.get('y_column');group=mapping.get('group_column');sample=mapping.get('sample_column')
    plotted=frame.copy();notes=[]
    if template=='scatter':
        frame=frame.copy();frame[[x,y]]=numeric(frame,[x,y])
        plotted=frame[list(dict.fromkeys(c for c in [sample,group,x,y] if c and c in frame))].copy()
        groups=frame[group].fillna('(missing)').astype(str) if group and group in frame else pd.Series(['All']*len(frame),index=frame.index)
        if groups.nunique()>20:raise ValueError('分组数最多为 20。')
        for i,label in enumerate(groups.unique()):
            mask=groups==label;ax.scatter(frame.loc[mask,x],frame.loc[mask,y],label=label,color=colors[i%len(colors)],s=36,alpha=.85,edgecolors='white',linewidths=.4)
        ax.set(xlabel=x,ylabel=y);ax.legend(title=group or 'Group',frameon=False)
    elif template=='heatmap':
        features=mapping.get('features',[])
        data=numeric(frame,features)
        plotted=data.copy()
        if sample and sample in frame:plotted.insert(0,sample,frame[sample].to_numpy())
        if len(data)>100 or len(features)>60:raise ValueError('热图预览最多 100 个样本、60 个特征，请先选择数据子集。')
        im=ax.imshow(data.to_numpy(),aspect='auto',interpolation='nearest',cmap='viridis')
        ax.set_xticks(range(len(features)),features,rotation=55,ha='right')
        labels=frame[sample].astype(str).tolist() if sample and sample in frame else [str(i+1) for i in range(len(frame))]
        ax.set_yticks(range(len(labels)),labels);fig.colorbar(im,ax=ax,label='Value');notes.append('原始数值，无自动标准化或聚类。')
    elif template=='box':
        frame=frame.copy();frame[[y]]=numeric(frame,[y])
        if not group or group not in frame:raise ValueError('箱线图需要分组列。')
        if frame[group].isna().any():raise ValueError('分组列不能缺失。')
        groups=frame[group].astype(str);labels=list(groups.unique())
        plotted=frame[list(dict.fromkeys(c for c in [sample,group,y] if c and c in frame))].copy()
        if len(labels)>20:raise ValueError('分组数最多为 20。')
        arrays=[frame.loc[groups==g,y].to_numpy(dtype=float) for g in labels]
        boxes=ax.boxplot(arrays,positions=range(len(labels)),patch_artist=True,showfliers=False)
        for i,(patch,values) in enumerate(zip(boxes['boxes'],arrays)):
            patch.set_facecolor(colors[i%len(colors)]);patch.set_alpha(.3)
            jitter=np.random.default_rng(42+i).uniform(-.13,.13,len(values));ax.scatter(i+jitter,values,s=20,color=colors[i%len(colors)],alpha=.75)
        ax.set_xticks(range(len(labels)),[f'{g}\n(n={len(v)})' for g,v in zip(labels,arrays)]);ax.set(xlabel=group,ylabel=y);notes.append('显示所有观测点；未进行显著性检验。')
    elif template=='stacked':
        features=mapping.get('features',[]);data=numeric(frame,features)
        if len(data)>100 or len(features)>30:raise ValueError('堆叠图最多 100 个样本、30 个特征。')
        if (data<0).any().any() or (data.sum(axis=1)<=0).any():raise ValueError('相对丰度图要求非负数值，且每行总和大于零。')
        plotted=data.div(data.sum(axis=1),axis=0)*100;bottom=np.zeros(len(data));positions=np.arange(len(data))
        for i,col in enumerate(features):
            ax.bar(positions,plotted[col],bottom=bottom,label=col,color=colors[i%len(colors)],width=.8);bottom+=plotted[col].to_numpy()
        labels=frame[sample].astype(str).tolist() if sample and sample in frame else [str(i+1) for i in range(len(frame))]
        ax.set_xticks(positions,labels,rotation=70,ha='right');ax.set(ylabel='Relative abundance (%)',ylim=(0,100));ax.legend(bbox_to_anchor=(1.02,1),loc='upper left',frameon=False)
        if sample and sample in frame:plotted.insert(0,sample,frame[sample].to_numpy())
        notes.append('各样本选定特征的总和归一为 100%；未选特征不计入分母。')
    elif template=='importance':
        frame=frame.copy();frame[[y]]=numeric(frame,[y])
        if not x or x not in frame:raise ValueError('请选择特征名称列。')
        top=int(options.get('top_n',20))
        if not 1<=top<=50:raise ValueError('显示特征数须在 1～50 之间。')
        plotted=frame.sort_values(y,ascending=False).head(top).iloc[::-1][[x,y]]
        ax.barh(plotted[x].astype(str),plotted[y],color=colors[0]);ax.set(xlabel=y,ylabel=x);notes.append('按已有重要性分数排序，不表示因果关系。')
    elif template=='workflow':
        if not x or x not in frame or not 1<=len(frame)<=8:raise ValueError('流程图需要 1～8 行有效步骤。')
        labels=frame[x].astype(str)
        plotted=frame[[x]].copy()
        if labels.str.len().max()>100:raise ValueError('每步说明最多 100 个字符。')
        ax.set(xlim=(0,1),ylim=(0,len(labels)));ax.axis('off')
        for i,label in enumerate(labels):
            yy=len(labels)-i-.75
            ax.add_patch(FancyBboxPatch((.18,yy),.64,.48,boxstyle='round,pad=0.025',facecolor='#edf3e9',edgecolor=colors[0]))
            ax.text(.5,yy+.24,textwrap.fill(label,45),ha='center',va='center')
            if i<len(labels)-1:ax.annotate('',xy=(.5,yy-.45),xytext=(.5,yy-.03),arrowprops={'arrowstyle':'->','color':colors[0]})
        notes.append('根据已提供步骤排版的示意图，不是数据分析结果。')
    else:raise ValueError('不支持的绘图模板。')
    title=str(options.get('title','')).strip()
    if len(title)>160:raise ValueError('标题最多 160 字符。')
    if title:ax.set_title(title)
    if template not in {'heatmap','workflow'}:
        ax.spines[['top','right']].set_visible(False)
    for extension in ['png','svg','pdf']:fig.savefig(output/('figure.'+extension),dpi=300)
    plt.close(fig)
    plotted.to_csv(output/'plot_data.csv',index=False)
    (output/'plot_settings.json').write_text(json.dumps({'template':template,'mapping':mapping,'options':options,'notes':notes,'renderer_version':'1.2.0','renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
    return notes
