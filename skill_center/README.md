# BioFlow Skill 中心 · 管理与算法工作台 v1.2

在原 M0～M3 独立管理版上增量增加算法和绘图工作台。2026-10-14 导入的 63 个已发布技能与 11 个只读原版保留；2026-10-27 增加 6 个含示例和脚本的本地绘图模板 Skill、已有 10 个算法的目录界面，以及 PCA、K-means、随机森林三条真实运行流程。原算法实现、旧 Skill 模块、总前端和其他三个板块保持原样。

新增入口：`/algorithms` 算法库、`/plots` 绘图示例与模板、`/runs` 运行记录。支持数据预览、参数配置、结果表与 PNG/SVG/PDF、独立重绘、参数版本和源码包增量导入验证。详见 [本次增量范围与操作](docs/WORKBENCH_20261027.md)。

服务器项目目录：`/home/xh/BioFLow/skill_center`。本地源码副本：`D:\workspace\xh\skill_center`。

## 已实现

- 管理员登录及退出；所有内容与管理 API 均需要会话。
- Skill 库业务板块分组（可多选归属）、搜索、类别/来源/状态/收藏筛选、最近打开排序、分页、卡片/列表视图及空状态。
- 五种新建模板；完整 MD/ZIP 上传；公开 GitHub 仓库、tree、blob/SKILL.md 导入。
- 固定 GitHub 提交后扫描与预览；多入口选择、共享资源确认、格式诊断、取消、失败重试及重复提交处理。
- 导入原版只读；副本保留父技能、父版本和全部资源；本地内容可编辑。
- 文件树、Markdown 预览、原文、代码高亮、资源上传、新增/删除文本文件。
- 基础信息表单保留其他 YAML 字段；标准名改变时调整对应目录。
- 保存草稿、版本冲突检测、格式校验、不可变发布、文件差异及旧版恢复。
- 展示名称/简介、分类、标签、启用状态、执行类型、收藏、归档与取消归档。
- 复制正文、使用提示、上游安装命令和完整 ZIP 导出；下载清单记录入口、版本、来源、文件哈希。
- 来源查看、固定提交链接、最新来源链接、手动检查更新、比较差异及明确导入新版本。
- SQLite WAL、版本快照原子落盘、数据库迁移、重启中断识别、孤立快照登记、启动/停止和一致性备份恢复。

正文与资源由完整技能包保存，格式依据 [Agent Skills specification](https://agentskills.io/specification)。外部安装命令采用官方 [skills CLI](https://github.com/vercel-labs/skills) 已核实的 `add`、`--skill` 和 `--agent codex` 参数。

## 使用入口

服务器只监听 `127.0.0.1:18120`。在自己的电脑运行：

```sh
ssh -N -L 18120:127.0.0.1:18120 xh@219.224.3.96
```

保持 SSH 窗口运行，然后访问 `http://127.0.0.1:18120/skills`。如果本机端口占用，可改为 `-L 18130:127.0.0.1:18120`，浏览器访问 18130。

登录使用独立管理员账号。初始化凭据在服务器 `storage/initial-access.txt`（权限 0600），本次交付也保存了工作区外层的登录信息文件。该文件、数据库、凭据和任务材料均不提交到源码库；SSH 密码未写入项目。

## 构建、测试与运维

```sh
cd /home/xh/BioFLow/skill_center
bash deploy/build.sh
.venv/bin/python deploy/manage.py start
.venv/bin/python deploy/manage.py status
.venv/bin/python deploy/manage.py stop
```

依赖隔离在本项目 `.venv` 和 `frontend/node_modules`。前端使用 `package-lock.json`；后端完整锁定见 `requirements.lock`。重新部署使用 `pip install -r requirements.lock` 和 `npm ci`；`requirements.txt` 保留直接依赖声明。修改依赖后才用 `SC_UPDATE_LOCK=1 bash deploy/build.sh` 更新前端锁文件。

详见 [本次分类与来源核验](docs/IMPORT_REPORT_20261014.md)、[部署与备份](docs/DEPLOYMENT.md)、[内容 API 与后续模型接入](docs/CONTENT_API.md)、[首轮验收记录](docs/ACCEPTANCE.md)。自动化测试使用 `python -m pytest`；配置仅收集本项目 `tests`，导入包不参与测试收集。

## 本轮的边界

服务器模型调用、通用 Skill 自动执行、SSE 及跨模块令牌仍未实现。新增算法与固定绘图模板由独立科学进程运行，设有任务并发及资源时限；这不等于通用 Skill 执行环境或操作系统安全沙箱。当前内容 API 仍可读取明确版本的完整正文和资源。第三方 Skill 的执行类型只是管理员声明，环境就绪状态继续保持“未验证”。

复制与 ZIP 下载用于分享完整内容，当前没有公开分享链接或开放匿名访问。外部安装命令只面向明确的 GitHub 上游来源，标明安装上游最新分支；本地原创/副本及需确认共享资源的技能使用 ZIP 和手动安装说明。

参考资源检测依据相对链接和常见资源路径，动态脚本依赖需人工确认。超大、非 UTF-8 或不支持的文件保留原始字节，提供下载。带 YAML 别名或不合规元数据的原包保留为阅读快照，格式错误阻止发布；修复时创建副本。保存草稿为显式操作，离开有修改的页面会提示。

默认限额：上传/下载压缩体积 50 MB、解压总量 200 MB、5000 文件、8 层路径；均可通过 `SC_MAX_*` 环境变量调整。正文预览 2 MB。外部 Markdown 图片不自动加载，危险 HTML 不执行。
