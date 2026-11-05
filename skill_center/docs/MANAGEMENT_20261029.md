# Skill 与算法管理补充（2026-10-29）

本次仅更新独立 `/home/xh/BioFLow/skill_center`。沿用已有界面和接口，不更改原算法库、总前端或其他业务部分。

## 页面操作

| 操作 | Skill 中心 | 算法库 |
| --- | --- | --- |
| 新增 | 新建 Skill；导入 GitHub 或 ZIP | 新增算法配置；导入包含 algorithm.json 和 algorithm.py 的 ZIP |
| 修改 | 展示设置；编辑草稿及资源，检查后发布；上游原版先创建规范副本 | 展示设置；保存参数新版本；导入源码新版本，验证后发布 |
| 删除 | 详情 → 删除技能 | 详情 → 删除算法 |
| 恢复 | 状态 → 回收站（已删除）→ 详情 → 恢复技能 | 列表范围 → 回收站 → 查看与恢复 → 恢复算法 |
| 搜索 | 名称、用途、标签；可叠加业务板块、类别等筛选 | 名称、用途、类别；可叠加类别及回收站筛选 |

删除采用可恢复方式：正常列表隐藏，保存历史版本、资源和运行结果。算法删除后禁止提交新运行、修改、验证和发布，已提交任务继续执行；恢复时恢复删除前的启用状态。回收站中的名称仍被保留，同名算法应恢复后更新版本。

算法源码通过新版本 ZIP 更新，页面没有 Python 源码在线编辑器。新版本验证通过后方可发布。新增记录不等于自动具备执行能力；通用 Skill 的模型调用仍待接入。

## 接口

- `GET /api/v1/workbench/algorithms`：正常算法列表。
- `GET /api/v1/workbench/algorithms?archived=true`：回收站列表。
- `POST /api/v1/workbench/algorithms/{id}/archive`：请求体 `{"archived": true, "updated_at": "当前记录时间"}` 删除，`archived: false` 恢复。时间过期返回 409；重复操作不覆盖原状态。
- Skill 继续使用既有 `POST /api/v1/skills/{id}/archive` 和 `content_status=archived` 查询。

无数据库结构迁移，既有记录的缺省 archived_at 视为未删除。没有清空回收站或物理擦除接口。
