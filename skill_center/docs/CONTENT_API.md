# 内容 API 与后续模型接入

本轮只实现 Skill 管理与内容 API，不提交模型任务。未来模型模块可以使用下面的身份和快照关系，避免重新迁移内容。

2026-10-27 增量：`/api/v1/workbench` 提供独立算法和绘图工作台，仍不提交模型任务。它不改变下述 Skill 内容 API。算法目录用 `/algorithms`，版本验证、发布与回退按各算法版本接口完成；数据上传用 `/datasets`，运行与绘图用 `/runs`，模板用 `/plots`。任务记录固定 `algorithm_version_id`、源码哈希和输入哈希，结果通过任务文件接口及完整 ZIP 导出。具体限制见 WORKBENCH_20261027.md。

## 身份与版本

- `skill_id`：稳定平台 ID，同名技能可并存。
- `revision_id`：不可变包版本；模型实际使用时必须固定具体 ID。
- `platform_version`：平台发布序号，不代表上游版本。
- `content_hash`：排序后的相对路径和文件 SHA-256 组成的包哈希。
- `published_revision_id`：技能的当前发布指针；更新/恢复不会改变已存在的快照。
- `entry_path`：包内 SKILL.md 路径；资源和共享目录保留相对布局。

## 读取顺序

业务板块存于 `applicable_modules` 数组，允许 `writing`（文献撰写）和 `analysis`（数据分析与生图），可同时选择。`GET /api/v1/modules` 返回板块和数量；`GET /api/v1/skills?module=writing` 或 `module=analysis` 按板块筛选。新建、展示设置、导入确认接受该字段，副本继承原归属。此字段是平台元数据，修改归属不会改写正文或已发布快照。

1. `GET /api/v1/skills?content_status=published` 获取目录，检查 `enabled` 与 `archived_at`。
2. `GET /api/v1/skills/{skill_id}` 确认用户实际选择的技能。
3. 固定 `published_revision_id`，读取 `GET /api/v1/skills/{skill_id}/revisions/{revision_id}`。
4. 根据返回的 `entry_path` 读取 `GET .../files?path=<相对路径>`，获取 SKILL.md 原文。
5. 按明确需要和文件清单读取支持的文本资源；二进制通过 `download=true` 授权下载。
6. 模型侧保存使用版本、资源清单与包哈希，并自行实现上下文预算、工具权限、运行结果和真实能力验证。

文件接口不接收主机绝对路径。`files` 返回相对路径、大小、SHA-256、MIME 和预览能力，不泄露服务器目录或密钥。

## 会话示例

以下为占位值，没有实际密码或令牌：

```sh
curl -c session.cookies -H 'Content-Type: application/json' \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}' \
  http://127.0.0.1:18120/api/v1/auth/login

curl -b session.cookies \
  'http://127.0.0.1:18120/api/v1/skills?content_status=published'

curl -b session.cookies \
  'http://127.0.0.1:18120/api/v1/skills/SKILL_ID/revisions/REVISION_ID/files?path=skill-name/SKILL.md'
```

首轮只有管理员会话。跨模块专用令牌、`integration/catalog`、`integration/resolve` 和托管运行 API 属于 M6，尚未实现；不要把网页登录 Cookie 用作长期模块凭据。

## 状态与权限

内容状态 `draft/published/archived` 与运行状态独立。`execution_type` 支持 `text/tool/manual/unclassified`，并不证明环境可运行；`execution_state` 目前为 `unverified`。

格式无效的导入原包有可阅读快照，但没有有效发布指针。资源缺失/未确认依赖单独记录。外部 Skill 正文是内容，平台和用户授权决定模型的数据范围和工具权限。

原版只读。调用方要编辑时先创建副本。草稿修改必须携带 `draft_counter`，不匹配返回 409 `REVISION_CONFLICT`；发布不会自动执行脚本。

## 错误格式

```json
{"error":{"code":"INVALID_PATH","message":"文件路径不能越过技能包边界。","details":{},"request_id":"REQUEST_ID"}}
```

接口功能列表与输入示例可查看后端路由及 tests。当前没有匿名 API、任意 URL 模型代理或任意 shell 执行入口。
