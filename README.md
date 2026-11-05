# BioFlow｜科研分析工作台

BioFlow 将文献检索、数据与样本管理、生信分析、科研绘图和论文写作组织到同一个项目工作区。数据分析以 **Nextflow** 为执行层，提供可视化 Workflow 设计、逐节点参数配置、运行监控、受限 AI 辅助诊断和结果溯源。

> 本仓库是最新部署版本的**公开源码快照**，不是服务器数据备份或开箱即用的完整运行镜像。包含统一工作台、分析、写作、文献及独立 Skill/算法服务的源码；不包含医院数据、用户上传文件、任务数据库、日志、分析结果、参考数据库、模型权重、账号密码或 API Key。

## 1. 主要功能

### 项目与资料

- 登录后按项目管理文献、测序数据、任务及写作资源。
- 支持上传、样本配对、输入登记和已有兼容结果复用。
- 资源访问通过账户、项目归属和服务端校验约束。

### 数据分析

- 标准宏基因组流程：输入校验、FastQC、fastp、去宿主、物种注释、功能注释与报告。
- 保留 Kraken2/Bracken、HUMAnN 和既有 MAG 工具链；可用性取决于工具、数据库和资源预检。
- Workflow 设计器支持添加/移动节点、连接与删除连线、参数配置、草稿保存、检查和版本发布。
- 每个节点实例独立保存参数；任务冻结流程、参数和输入快照，后续模板修改不会改写历史任务。
- 展示运行状态、当前节点、进度、耗时、失败原因和日志。估算进度不代表工具内部的精确完成比例。
- 通过 Nextflow 缓存复用已完成节点，从失败的计算节点恢复；不保证恢复到工具内部中断的具体百分比。
- 共享并发队列、线程上限及资源提示；并发与磁盘估算不是绝对的资源配额保证。

### 有类型的输入

| 输入 | 典型用途与约束 |
| --- | --- |
| 原始 paired-end FASTQ | 从质控开始；校验内容、R1/R2 配对与完整性 |
| 已质控 reads | 接入兼容的去宿主及后续阶段 |
| 已去宿主 reads | 接入兼容的物种/功能注释 |
| Contigs FASTA | 接入已有组装结果；分箱等操作仍需匹配的伴随 reads |
| MAG FASTA 集合 | 按 MAG ID 和 cohort ID 登记，接入支持的注释 |
| 丰度矩阵 | 物种、基因家族、KO、EC、通路丰度/覆盖度的描述性汇总 |
| 已有任务产物 | 复用已登记、成功、归属当前用户且兼容的产物 |

外部质控/去宿主 reads 必须填写处理说明并二次确认，标记为 **“用户声明、未经平台验证”**。文件名、来源任务和校验和均不能证明生物学处理有效。

矩阵需明确特征类型、单位及标准化说明。支持 canonical 长表及精确识别的 BioFlow 标准富表，不根据数值大小猜测是否乘以 100，也不新增隐式标准化。覆盖度与丰度不同，不能直接加和解释。未知宽表或原始工具表需先明确转换契约。

导入任务有持久化历史。刷新后可继续查看排队、校验、失败或完成的记录；网络结果不确定时先核对已受理任务。解除待确认标记需显式确认重复风险，不会自动提交、取消或删除服务器任务。

### AI、图表与写作

- 受限 AI 自动修复是每个任务的可选项，默认关闭；无法处理时暂停并提示人工介入。
- 当前本地模型配置沿用 `qwen3:14b`/Ollama，但模型权重和运行服务不在仓库中。
- 图表使用实际数值结果及渲染代码；绘图工作台支持可用图型、参数、版本和来源记录。
- 初步解读需结合可追溯数据，不能把宏基因组功能潜力解释为表达、代谢活性、疾病因果或临床诊断。
- 写作模块复用选定任务的分析证据；文献模块提供文献管理和 RAG 相关服务。
- Skill 中心支持能力来源、版本与运行记录管理；网页模型/Skill 配置不意味着每个设计中的节点都已接入执行。

## 2. 源码结构

```text
BioFlow/
├── ai4s-interface.html              # 统一工作台页面
├── frontend/                       # 页面、流程设计器、运行面板与数据导入
├── backend/bioflow_platform/        # FastAPI 网关、账户/项目及模块对接
├── BioLLM_RawDataAnalysis/
│   ├── backend/                    # 分析 API、输入契约、编译器、任务与产物
│   ├── workflow/                   # Nextflow 流程、模块、脚本与 schema
│   └── scripts/                    # 分析服务运维入口
├── article_writing/                # 写作业务、分析证据适配与导出
├── Article_repository/
│   ├── article_repository/         # 文献采集、检索及 RAG 适配
│   └── ai-localbase/               # 文献服务 Go 后端、前端和 Docker 配置
├── skill_center/                   # 独立 Skill 中心 API 与 React/Vite 前端
├── bioflow_skills/                 # 注册能力与执行适配
├── bioflow_ml/                     # 算法与机器学习相关源码
├── bioflow/                        # 原有分析/模型/RAG 编排源码
├── deploy/                         # 既有服务器部署工具（使用前核对环境）
├── scripts/                        # 辅助脚本；部分为历史迁移工具
└── tests/                          # 网关、输入、流程和界面测试
```

`bioflow/` 保留原有编排与 mock 能力，**不是本次新数据分析执行层的替代实现**。科研分析任务继续由 `BioLLM_RawDataAnalysis/` 和 Nextflow 执行。当前未用 LangGraph 重写生信流程。

## 3. 环境与部署

### 安全复现入口（Linux 优先）

请从全新克隆开始，按 [复现说明](docs/REPRODUCIBILITY.md) 准备隔离环境，
再运行 `python repro/quickstart.py check`、`init`、`fixtures` 与
`start --isolated-development`。默认仅启动回环地址的网关/分析 API；AI 自动修复、
自动任务执行关闭，不准备 MAG、模型或参考数据库，也不迁移旧账号。
合成样例只验证软件，不具生物学意义。完整公开 WGS 样本 SRR9224248 约 1.09 GB，
通过 `python repro/public_data.py plan` 查看离线计划；下载须显式 `--allow-network`，
完成后单独 `verify`。工具/数据库的来源与版本缺口见 `repro/resources.json`。
这些检查不代表全生信流程或论文数值结果已复现；缺失资源不得视为通过。

### 基础环境

- 正式生信计算建议使用 Linux；Python 使用与各模块依赖兼容的版本，原服务器分析验证环境为 Python 3.10。
- Java、Nextflow、各生信工具及参考数据库需要独立配置，不能只安装 Python 包。
- 前端源码构建需要适配相应 `package.json` 的 Node.js/npm；Go 文献服务还需要 Go 或 Docker。
- Ollama、模型、Qdrant 与文献/Skill 服务分别管理；不要把这些服务默认公开到公网。

在仓库根目录准备 Python 环境：

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r BioLLM_RawDataAnalysis/backend/requirements.txt
python -m pip install -r article_writing/requirements.txt
```

其他模块依赖分别位于 `skill_center/requirements.txt`、`bioflow_ml/requirements.txt`、`bioflow_skills/requirements.txt` 和各前端目录。它们不承诺可以不经核对全部安装在同一个环境中。

### 分别启动服务

终端 A：

```bash
cd BioLLM_RawDataAnalysis
python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8803
```

终端 B，在仓库根目录：

```bash
export BIOFLOW_ANALYSIS_ROOT="$PWD/BioLLM_RawDataAnalysis"
export BIOFLOW_ANALYSIS_URL=http://127.0.0.1:8803
export BIOFLOW_WRITING_URL=http://127.0.0.1:8765
export BIOFLOW_LITERATURE_URL=http://127.0.0.1:8080
python -m uvicorn backend.bioflow_platform.app:app --host 127.0.0.1 --port 8800
```

终端 C，在仓库根目录启动写作 API：

```bash
export BIOFLOW_ANALYSIS_ROOT="$PWD/BioLLM_RawDataAnalysis"
python -m uvicorn backend.bioflow_platform.writing_api:app --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8800/`。未启动的文献、模型或 Skill 服务会显示不可用，不应将其误认为已就绪。文献服务参照 `Article_repository/ai-localbase/README.md`；Skill 中心参照 `skill_center/README.md`，并配置统一入口的相关环境变量。

Linux 正式执行默认要求可用的用户级 systemd 隔离环境。`process_group` 模式仅适合明确了解其限制的隔离开发测试；不要把它当成与 systemd 同等的进程回收保证。

### 账户与数据初始化

仓库**没有可登录的预置账号或密码**。可通过注册创建普通账户；管理员应在自己控制的部署中初始化。以下操作仅用于全新环境，不会重置已有账号：

```bash
export BIOFLOW_DEVELOPER_USERNAME='your_admin_name'
read -s -p 'New administrator password: ' BIOFLOW_DEVELOPER_PASSWORD
export BIOFLOW_DEVELOPER_PASSWORD
python -c "import os; from pathlib import Path; from backend.bioflow_platform.store import Store; from backend.bioflow_platform.auth import create_user; create_user(Store(Path('runtime/bioflow.sqlite3')),os.environ['BIOFLOW_DEVELOPER_USERNAME'],os.environ['BIOFLOW_DEVELOPER_PASSWORD'],'developer')"
unset BIOFLOW_DEVELOPER_PASSWORD
```

不要用 `scripts/bootstrap_developer.py` 初始化新环境：它是包含账号和历史记录迁移行为的旧运维脚本。`Start-BioFlow.sh`、`deploy/server96.py` 也保留原服务器运维假设，**不是新机器上免配置的一键安装器**；使用前需核对 Python、数据库、目录和服务配置。

### 数据库配置

- schema：`BioLLM_RawDataAnalysis/workflow/assets/database-registry.schema.json`
- 示例：`BioLLM_RawDataAnalysis/workflow/assets/database-registry.example.json`
- 配置环境变量：`BIOLLM_DATABASE_REGISTRY`、`BIOLLM_DATABASE_PROFILE`、`BIOLLM_DATABASE_MANIFEST`。

真实 registry 应在仓库外维护，填写实际 release、工具兼容版本及文件校验信息。数据库缺失、关键文件不全或版本不匹配时应预检失败；模型、参考序列与数据库请按各自许可证另行获取。

## 4. 使用顺序

1. 登录并选择/创建研究项目。
2. 上传文件，或从当前用户拥有的兼容产物中选择来源。
3. 在“分析 → 导入分析数据”登记类型、处理状态、单位和必要说明，等待校验完成。
4. 选择已发布流程，为每个输入节点绑定兼容数据，点击节点调整参数。
5. 核对资源与数据库；按需开启受限 AI 修复，再确认提交真实计算任务。
6. 查看节点状态和日志；失败后仅在满足恢复条件时续跑。
7. 查看实际节点输出、允许下载的文件、图表版本及相应数据依据。
8. 设计自己的流程时先保存草稿、检查，再发布固定版本；发布不会自动运行任务。

## 5. 当前边界

- 外部 MAG 定量尚不支持，不能用虚构 reads/assembly 绕过输入契约。
- typed 输入流程不能直接接旧的 CSV REPORT；使用原生节点输出、矩阵汇总和受保护的完整归档。
- 16S 及部分模型/图表/解读节点仍有设计或接线边界，不能把画布上的存在当作完整可执行能力。
- MAG 是 cohort/联合组装实体，不应唯一归属于某个样本；检出/丰度必须有独立的样本映射证据。
- 完整归档可能含原始数据，因此沿用敏感归档下载保护；应通过授权渠道获取，不应直接公开。
- 公开源码没有用户项目、任务结果、向量库、论文全文库、已安装 Skill bundle 或模型。导入与注册记录需在部署环境重新建立。
- 本仓库不宣称经过生产安全认证、临床验证或新机器上的全流程复现验证。

## 6. 验证与开发

服务器部署基线来自分析 main `0103c1eaa1706606953a3dfda143869d86ce56f3`，同时包含正式网站当时的模块对接和前端更新。公开快照不携带原仓库 Git 历史，以避免历史配置或数据泄露；GitHub 提交 SHA 与该服务器 SHA 不同。

发布前原服务器的验证记录：完整兼容性回归 828 passed / 26 skipped；7 项实际 Nextflow 接线/缓存测试通过；前端启用对应浏览器夹具后 49 passed / 17 gated skipped。**这些是服务器版本的软件验证，不等于公开副本在任意机器上可直接跑通生物学分析**，也不证明所用数据库与算法对任意数据都有效。

```bash
python -m pytest tests -q
cd BioLLM_RawDataAnalysis
python -m pytest backend/tests -q
# 仅在 Nextflow 与对应测试条件可用时启用：
BIOFLOW_TEST_NEXTFLOW=1 python -m pytest backend/tests/test_typed_nextflow.py -q
```

浏览器测试需要自行准备 Playwright 和相应浏览器，部分夹具使用 Edge；不具备认证、Linux、systemd 或工具条件的测试会跳过，跳过不能作为通过证据。开发数据、环境、缓存和测试输出不得提交。

## 7. 安全与第三方代码

- 勿提交 `.env`、API Key、SSH 密钥、用户数据库、原始 reads、中间文件、结果归档或医院数据。
- 服务默认先绑定回环地址；公网部署需另行配置 HTTPS、身份认证、访问限制、配额、备份与日志策略。
- 原服务器的现存账号、密码、密钥及数据不会因为上传源码而自动迁移或更改；维护者应独立管理并轮换凭据。
- 沿用目标仓库初始化提交的 [MIT 许可证](LICENSE)。保留第三方子项目的许可证与署名，例如 `Article_repository/ai-localbase/LICENSE`。其他依赖、工具、数据库与模型遵循各自条款；仓库许可证不替代第三方授权。

公开副本仅删除部署私有清单/运行数据，并移除了旧启动提示中写死的登录密码；没有更改服务器上的运行代码、配置或数据。不要把公开仓库当作现有服务器的完整备份。
