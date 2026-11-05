"""Small, explicit UI contracts for the first three supported algorithms."""
PARAMETERS = {
    'pca': {
        'n_components': {'label':'主成分数','type':'integer','default':2,'min':2,'max':20},
        'random_state': {'label':'随机种子','type':'integer','default':42,'min':0,'max':2147483647},
    },
    'kmeans': {
        'n_clusters': {'label':'聚类数','type':'integer','default':3,'min':2,'max':20},
        'n_init': {'label':'初始化次数','type':'integer','default':10,'min':1,'max':50},
        'max_iter': {'label':'最大迭代数','type':'integer','default':300,'min':10,'max':1000},
        'random_state': {'label':'随机种子','type':'integer','default':42,'min':0,'max':2147483647},
    },
    'random_forest': {
        'n_estimators': {'label':'树的数量','type':'integer','default':100,'min':10,'max':500},
        'max_depth': {'label':'最大树深','type':'integer','default':10,'min':1,'max':50},
        'cv': {'label':'交叉验证折数','type':'integer','default':5,'min':2,'max':10},
        'random_state': {'label':'随机种子','type':'integer','default':42,'min':0,'max':2147483647},
    },
}
NAMES={'pca':'PCA 主成分分析','kmeans':'K-means 聚类','random_forest':'随机森林分类','hierarchical':'层次聚类','tsne':'t-SNE','umap':'UMAP','lasso':'LASSO 特征选择','rfe':'RFE 特征选择','svm':'支持向量机分类','logistic_regression':'逻辑回归分类'}
RECIPES = [
    {'id':'scatter','name':'分组散点图','summary':'展示 PCA 坐标或两列数值，按分组着色。','input':'两列数值、可选分组列','example':'matrix','mapping':{'sample_column':'sample_id','x_column':'feature_1','y_column':'feature_2','group_column':'group'},'algorithms':['pca','kmeans']},
    {'id':'heatmap','name':'数值矩阵热图','summary':'展示样本与特征的数值矩阵；配色变化不修改原始数值。','input':'样本 × 数值特征矩阵','example':'matrix','mapping':{'sample_column':'sample_id','features':['feature_1','feature_2','feature_3','feature_4']},'algorithms':['pca','kmeans','random_forest']},
    {'id':'box','name':'分组箱线与散点图','summary':'保留每个观测点，显示组内分布；不自动添加显著性结论。','input':'一列数值和一列分组','example':'matrix','mapping':{'sample_column':'sample_id','y_column':'feature_1','group_column':'group'},'algorithms':[]},
    {'id':'stacked','name':'相对丰度堆叠图','summary':'非负数值按样本换算为百分比，保留转换后的作图数据。','input':'非负丰度矩阵，每行至少有一个正值','example':'abundance','mapping':{'sample_column':'sample_id','features':['Taxon_A','Taxon_B','Taxon_C','Taxon_D']},'algorithms':[]},
    {'id':'importance','name':'特征重要性条形图','summary':'按已有分数排序显示特征，不将预测贡献解释为因果机制。','input':'特征名称和重要性数值两列','example':'importance','mapping':{'x_column':'feature','y_column':'importance'},'algorithms':['random_forest']},
    {'id':'workflow','name':'科研流程示意图','summary':'根据已确认的步骤生成可编辑矢量示意图，不生成分析结果。','input':'step 列，每行一个流程步骤，最多 8 步','example':'workflow','mapping':{'x_column':'step'},'algorithms':[]},
]


def recipe(key):
    return next((r for r in RECIPES if r['id']==key),None)
