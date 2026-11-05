# Skill 业务板块与来源核验 · 2026-10-14

本轮按用户授权增加“文献撰写 / 数据分析与生图”板块，导入指定来源，并为格式不合规的原包创建规范副本。只写入独立项目 `/home/xh/BioFLow/skill_center`。文献分类表与上游 SKILL.md 作为待核验内容读取，不作为代理授权或执行指令。

## 交付结果

- 已发布技能 63 个；文献撰写 54 个、数据分析与生图 11 个。`nature-figure` 和 `statistical-analysis` 同时归属两个板块。
- 11 个不合规原版保留为只读、停用的阅读快照，分别有规范副本及父技能/父版本关系。全部技能共 74 条记录。
- 按固定提交核验 23 个导入仓库。原版快照共 2052 个文件（共享资源在多个技能包中分别保存），逐个通过 Git blob 哈希校验；规范副本正文与非入口资源保持一致。
- 表格中的 6 个来源在已核验提交没有独立 SKILL.md，记录为外部工具候选。未安装这些 MCP 或应用。
- 已发布表示内容格式通过检查。所有技能运行能力为未验证；未接入模型，未安装上游运行依赖。

入口：[文献撰写](http://127.0.0.1:18120/skills?module=writing) · [数据分析与生图](http://127.0.0.1:18120/skills?module=analysis)。需要本机 SSH 端口转发与独立管理员登录。

## 分类表 33 项对应结果

表格用途说明用于分类，不代表功能已实际执行。集合类来源按所需独立入口拆分；相同名称的不同上游技能可同时存在。

| 表格项目 | 类别 | 处理结果 |
|---|---|---|
| [K-Dense paper-lookup](https://github.com/K-Dense-AI/scientific-agent-skills) | 文献检索与综述 | `skills/paper-lookup/SKILL.md` |
| [BERIL literature-review](https://github.com/kbaseincubator/BERIL-research-observatory/pull/134) | 文献检索与综述 | `.claude/skills/literature-review/SKILL.md` |
| [claude-code-templates literature-review](https://github.com/davila7/claude-code-templates) | 文献检索与综述 | `cli-tool/components/skills/scientific/literature-review/SKILL.md`（规范副本） |
| [paperscraper](https://github.com/jannisborn/paperscraper) | 文献检索与综述 | 外部工具候选：固定提交无独立 SKILL.md |
| [PaperSkills](https://github.com/andchamorro/PaperSkills) | 文献检索与综述 | `skills/lit-search/SKILL.md`（规范副本）；`skills/literature-review/SKILL.md`；`skills/connected-citations/SKILL.md`；`skills/paper-tracker/SKILL.md`；`skills/research-gap/SKILL.md` |
| [lab-codex-skills](https://github.com/JasperPWang/lab-codex-skills) | 文献检索与综述 | `paper-deep-dive/SKILL.md`；`paper-rag/SKILL.md`；`paper-spine-research/SKILL.md`；`paper-card-delivery/SKILL.md` |
| [OpenPapers MCP](https://github.com/kaago/openpapers-mcp) | 文献检索与综述 | 外部工具候选：固定提交无独立 SKILL.md |
| [academic-research-mcp](https://github.com/alisoroushmd/academic-research-mcp) | 文献检索与综述 | 外部工具候选：固定提交无独立 SKILL.md |
| [skill-research-papers](https://github.com/marciob/skill-research-papers) | 文献检索与综述 | `research-papers/SKILL.md` |
| [research-writing-skill](https://github.com/zLanqing/codex-claude-academic-skills) | 论文结构规划与学术写作 | `research-writing-skill/SKILL.md` |
| [qinyan-nature-writing](https://github.com/LeonChaoX/qinyan-academic-skills) | 论文结构规划与学术写作 | `skills/沁言学术skills/qinyan-nature-writing/SKILL.md` |
| [citation-verify](https://github.com/InfinityScopebio/citation-verify) | 引用管理与核验 | `SKILL.md` |
| [CiteCheck](https://github.com/color4-alt/CiteCheck) | 引用管理与核验 | `skills/citecheck/SKILL.md` |
| [skillz citation-verifier](https://github.com/jkitchin/skillz/tree/main/skills/citation-verifier) | 引用管理与核验 | `skills/citation-verifier/SKILL.md`（规范副本） |
| [Nature-Paper-Skills citation-verifier](https://github.com/Boom5426/Nature-Paper-Skills/tree/main/skills/core/citation-verifier) | 引用管理与核验 | `skills/core/citation-verifier/SKILL.md` |
| [deltasci](https://github.com/boheling/deltasci) | 引用管理与核验 | `skill/SKILL.md`（规范副本） |
| [paper-verify](https://github.com/nolainjin/paper-verify) | 引用管理与核验 | `integrations/skills/paper-verify/SKILL.md` |
| [FixBib](https://github.com/xmoezzz/fixbib) | 引用管理与核验 | 外部工具候选：固定提交无独立 SKILL.md |
| [cite-verify](https://github.com/jonckr/cite-verify) | 引用管理与核验 | `SKILL.md` |
| [citation-audit](https://github.com/BryanTegomoh/citation-audit) | 引用管理与核验 | 外部工具候选：固定提交无独立 SKILL.md |
| [statistical-analysis](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/statistical-analysis) | 结果解读与统计验证；Methods与生信分析流程 | `skills/statistical-analysis/SKILL.md` |
| [scikit-learn](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scikit-learn) | 结果解读与统计验证 | `skills/scikit-learn/SKILL.md` |
| [scientific-writing](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scientific-writing) | 结果解读与统计验证；Methods与生信分析流程 | `skills/scientific-writing/SKILL.md` |
| [MAC-n-CHEESE](https://github.com/leejaywon/MAC-n-CHEESE) | 论文审稿与科学批判 | 外部工具候选：固定提交无独立 SKILL.md |
| [paper-review.skill](https://github.com/jam-cc/paper-review.skill) | 论文审稿与科学批判 | `SKILL.md` |
| [research-paper-review](https://github.com/chunhualiao/paper-review-skill) | 论文审稿与科学批判 | `skills/research-paper-review/SKILL.md` |
| [peer-review](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/peer-review) | 论文审稿与科学批判 | `skills/peer-review/SKILL.md` |
| [scientific-critical-thinking](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scientific-critical-thinking) | 论文审稿与科学批判 | `skills/scientific-critical-thinking/SKILL.md` |
| [scholar-evaluation](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scholar-evaluation) | 论文审稿与科学批判 | `skills/scholar-evaluation/SKILL.md` |
| [experimental-design](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/experimental-design) | Methods与生信分析流程 | `skills/experimental-design/SKILL.md` |
| [ngs-amplicon-microbiome](https://github.com/openai/plugins/tree/main/plugins/ngs-analysis/skills/ngs-amplicon-microbiome) | Methods与生信分析流程 | `plugins/ngs-analysis/skills/ngs-amplicon-microbiome/SKILL.md` |
| [ngs-shotgun-metagenomics](https://github.com/openai/plugins/tree/main/plugins/ngs-analysis/skills/ngs-shotgun-metagenomics) | Methods与生信分析流程 | `plugins/ngs-analysis/skills/ngs-shotgun-metagenomics/SKILL.md` |
| [tooluniverse-multi-omics-integration](https://github.com/mims-harvard/ToolUniverse/tree/main/skills/tooluniverse-multi-omics-integration) | Methods与生信分析流程 | `skills/tooluniverse-multi-omics-integration/SKILL.md` |

## Nature 与数据分析来源

[Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) 导入 22 个业务技能。`nature-shared` 作为共享支持资源随相关技能包保存，不单列业务技能。[Nature-Paper-Skills](https://github.com/Boom5426/Nature-Paper-Skills) 则导入分类表明确指定的 citation-verifier。

| 来源 | 已导入入口 | 固定提交 |
|---|---|---|
| [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) | `skills/nature-academic-search/SKILL.md`、`skills/nature-citation/SKILL.md`、`skills/nature-data/SKILL.md`、`skills/nature-downloader/SKILL.md`、`skills/nature-experiment-log/SKILL.md`、`skills/nature-figure/SKILL.md`、`skills/nature-image2ppt/SKILL.md`、`skills/nature-literature-pipeline/SKILL.md`、`skills/nature-paper-card/SKILL.md`、`skills/nature-paper-to-patent/SKILL.md`、`skills/nature-paper-trans/SKILL.md`、`skills/nature-paper-xray/SKILL.md`、`skills/nature-paper2ppt/SKILL.md`、`skills/nature-polishing/SKILL.md`、`skills/nature-proposal-writer/SKILL.md`、`skills/nature-reader/SKILL.md`、`skills/nature-ref-verifier/SKILL.md`、`skills/nature-response/SKILL.md`、`skills/nature-reviewer/SKILL.md`、`skills/nature-social-science/SKILL.md`、`skills/nature-statistics/SKILL.md`、`skills/nature-writing/SKILL.md` | [19be8d45e0d5](https://github.com/Yuan1z0825/nature-skills/commit/19be8d45e0d5233aa44be6d4572e655b9914ff54) |
| [GPTomics/bioSkills](https://github.com/GPTomics/bioSkills) | `metagenomics/metagenome-visualization/SKILL.md` | [d91ed3d56301](https://github.com/GPTomics/bioSkills/commit/d91ed3d563019e649dc854c56ccd62551359488a) |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | `skills/statistical-analysis/SKILL.md`、`skills/scikit-bio/SKILL.md`、`skills/scientific-visualization/SKILL.md` | [a1043ef544e3](https://github.com/K-Dense-AI/scientific-agent-skills/commit/a1043ef544e3a100c28e70a736b6cf32554d0677) |
| [jihe520/sci-box](https://github.com/jihe520/sci-box) | `skills/scibox-diagram/SKILL.md`、`skills/scibox-figure/SKILL.md` | [9687d2a52037](https://github.com/jihe520/sci-box/commit/9687d2a52037e92bf68a781b9b1e061ca03c8125) |
| [LigphiDonk/academic-figure-generator](https://github.com/LigphiDonk/academic-figure-generator) | `academic-figure-prompt-pastel/SKILL.md`、`academic-figure-prompt/SKILL.md` | [0a2bec6bb56d](https://github.com/LigphiDonk/academic-figure-generator/commit/0a2bec6bb56d6b47143a81909f8d818716bdcbab) |

Academic Figure Generator 当前标准入口包括普通配图提示词和 pastel 柔和配色提示词。Sci-box 包括数据绘图模板与 draw.io 示意图两个技能。

## 规范副本改动

规范化仅涉及入口 YAML 和对应目录名。原 YAML 值转为 JSON 字符串时保留原值；正文、脚本、模板及其他附件不改写。原版快照仍记录来源提交。

| 上游入口 | 规范化内容 |
|---|---|
| [Yuan1z0825/nature-skills / skills/nature-experiment-log/SKILL.md](https://github.com/Yuan1z0825/nature-skills/blob/19be8d45e0d5233aa44be6d4572e655b9914ff54/skills/nature-experiment-log/SKILL.md) | metadata 非字符串值保留为 JSON 字符串 |
| [Yuan1z0825/nature-skills / skills/nature-literature-pipeline/SKILL.md](https://github.com/Yuan1z0825/nature-skills/blob/19be8d45e0d5233aa44be6d4572e655b9914ff54/skills/nature-literature-pipeline/SKILL.md) | metadata 非字符串值保留为 JSON 字符串 |
| [Yuan1z0825/nature-skills / skills/nature-proposal-writer/SKILL.md](https://github.com/Yuan1z0825/nature-skills/blob/19be8d45e0d5233aa44be6d4572e655b9914ff54/skills/nature-proposal-writer/SKILL.md) | 技能目录调整为标准名称；metadata 非字符串值保留为 JSON 字符串 |
| [andchamorro/PaperSkills / skills/lit-search/SKILL.md](https://github.com/andchamorro/PaperSkills/blob/b34fe22569ac538d2273ee6db20f2f74c7e5481b/skills/lit-search/SKILL.md) | name 改为与技能目录相符的标准标识 |
| [davila7/claude-code-templates / cli-tool/components/skills/scientific/literature-review/SKILL.md](https://github.com/davila7/claude-code-templates/blob/f497abcc0f2d9a6f15549598323fd1322cc8feda/cli-tool/components/skills/scientific/literature-review/SKILL.md) | allowed-tools 规范为字符串 |
| [jkitchin/skillz / skills/citation-verifier/SKILL.md](https://github.com/jkitchin/skillz/blob/b28fcf4c9f882cd890a3b59a160a2ff1b7d3e3de/skills/citation-verifier/SKILL.md) | allowed-tools 规范为字符串 |
| [boheling/deltasci / skill/SKILL.md](https://github.com/boheling/deltasci/blob/5b36015ead6934a67622b1777f11ce59dfe36a68/skill/SKILL.md) | 技能目录调整为标准名称 |
| [GPTomics/bioSkills / metagenomics/metagenome-visualization/SKILL.md](https://github.com/GPTomics/bioSkills/blob/d91ed3d563019e649dc854c56ccd62551359488a/metagenomics/metagenome-visualization/SKILL.md) | 技能目录调整为标准名称 |
| [jihe520/sci-box / skills/scibox-figure/SKILL.md](https://github.com/jihe520/sci-box/blob/9687d2a52037e92bf68a781b9b1e061ca03c8125/skills/scibox-figure/SKILL.md) | 技能目录调整为标准名称 |
| [LigphiDonk/academic-figure-generator / academic-figure-prompt-pastel/SKILL.md](https://github.com/LigphiDonk/academic-figure-generator/blob/0a2bec6bb56d6b47143a81909f8d818716bdcbab/academic-figure-prompt-pastel/SKILL.md) | name 改为与技能目录相符的标准标识 |
| [LigphiDonk/academic-figure-generator / academic-figure-prompt/SKILL.md](https://github.com/LigphiDonk/academic-figure-generator/blob/0a2bec6bb56d6b47143a81909f8d818716bdcbab/academic-figure-prompt/SKILL.md) | name 改为与技能目录相符的标准标识 |

## 资源诊断的限制

相对引用检测会识别正文示例的 URL、占位符和预期生成的输出路径，因此“缺失”不一定是运行依赖缺失。下列 8 个入口保留原始告警；真实可用性仍需后续按环境验证。对已核验树中存在的明确支持资源已补齐，上游没有的文件未编造。

| 上游入口 | 检测到的路径 |
|---|---|
| Yuan1z0825/nature-skills / skills/nature-reviewer/SKILL.md | `skills/nature-reviewer/<references/editorial` |
| andchamorro/PaperSkills / skills/literature-review/SKILL.md | `skills/literature-review/references/anti-leakage-prompt.md` |
| JasperPWang/lab-codex-skills / paper-deep-dive/SKILL.md | `paper-deep-dive/pdf-url`；`paper-deep-dive/url` |
| JasperPWang/lab-codex-skills / paper-card-delivery/SKILL.md | `paper-card-delivery/...`；`paper-card-delivery/relative-image-path`；`paper-card-delivery/relative-or-native-image` |
| davila7/claude-code-templates / cli-tool/components/skills/scientific/literature-review/SKILL.md | `cli-tool/components/skills/scientific/literature-review/scripts/generate_schematic.py` |
| marciob/skill-research-papers / research-papers/SKILL.md | `research-papers/path` |
| jkitchin/skillz / skills/citation-verifier/SKILL.md | `skills/citation-verifier/url` |
| jihe520/sci-box / skills/scibox-figure/SKILL.md | `skills/scibox-figure/templates/scripts/render_template.py` |

## 验收与运维

29 项项目测试、TypeScript 检查与 Vite 生产构建通过。浏览器检查覆盖板块归属继承、多板块筛选、URL 刷新、展示设置、导入归属以及 1440/768/375 像素布局。正式库检查覆盖两个板块计数、指定生图来源、只读原版与规范副本关系。

测试收集限定为本项目 `tests`，避免 pytest 默认扫描导入包中的上游测试模块。测试日志存在一项上游 Starlette/httpx 弃用提示，不影响通过结果。

一致性备份：服务器 `backups/skill-center-v1.1-20261014.tar.gz`（私有，含数据库及管理员配置，不进入源码发布包）。正式服务只监听 `127.0.0.1:18120`。

范围核查：基线 2861 个文件中，总前端、ML、旧 Skill 库、文献库及原始数据分析目录一致。文献撰写目录期间出现 4 个源文件变化和 21 个输出文件新增，单独记录在 scope-audit.json；本轮未写入或回滚它们。

完整机器可读核验、父版本和来源提交见同目录 SOURCE_MANIFEST_20261014.json；工作区验收目录为 `D:/workspace/xh/deliverables/skill_center_20261014_checks`。
