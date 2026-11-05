# 部署与备份

## 当前实例

- 独立目录：`/home/xh/BioFLow/skill_center`。
- 生产监听：`127.0.0.1:18120`；不开放新公网管理端口。
- 单管理员会话，HttpOnly、SameSite=Strict cookie，12 小时有效。
- 元数据和快照：`storage/`；实际凭据：`storage/admin.json`。
- 服务日志：`storage/server.log`；进程号：`storage/server.pid`。
- 没有修改总前端入口、旧库、其他板块、共享 Python 环境或既有服务。

启动方式：

```sh
cd /home/xh/BioFLow/skill_center
.venv/bin/python deploy/manage.py start
```

停止命令只在进程工作目录与 `uvicorn backend.main:app` 相符时发送 SIGTERM，不按端口杀其他服务。`start` 遇到被占用端口会退出，不替换既有监听。

本实例使用独立后台进程，不自动注册系统服务。服务器重启后手动执行启动命令；后续有明确运维要求再注册 user systemd 服务。

## 一致性备份

备份期间停掉本应用，其他服务保持运行：

```sh
cd /home/xh/BioFLow/skill_center
.venv/bin/python deploy/manage.py stop
.venv/bin/python deploy/manage.py backup backups/skill-center.tar.gz
.venv/bin/python deploy/manage.py start
```

备份同时包含数据库、WAL 文件、技能快照、草稿、来源记录、配置和必要凭据。备份权限为 0600，按私人配置保管，不放在公开下载目录。日志与 PID 不包含在备份中。

## 独立恢复检查

恢复拒绝非空目标，避免覆盖当前库：

```sh
SC_STORAGE=/home/xh/BioFLow/skill_center/test-results/restored-storage \
  .venv/bin/python deploy/manage.py restore backups/skill-center.tar.gz
```

用同一份代码与不同 `SC_STORAGE` 检查数据库记录和文件哈希。需要启动恢复实例时使用空闲本机端口，禁止覆盖正式实例。

## 升级和回退

1. 备份当前源码及 `storage`。
2. 在独立测试库构建并执行单元/API/浏览器测试。
3. 停止本应用，更新源码与锁定依赖，再启动并检查 `/api/v1/health`。
4. 失败时回退源码；若升级涉及数据库迁移，在空目录恢复匹配的备份，再切换 `SC_STORAGE`。

数据库当前 `PRAGMA user_version=3`。版本 3 只增加算法、算法版本、数据集和运行表；旧记录的 `applicable_modules` 自动补为 `[]`。应用启动会将未完成扫描和工作台任务标为 interrupted，缺失版本快照的技能停用，将无索引快照登记到 `orphaned-snapshots.json`，不把孤立文件当作有效技能。科学运行环境及首版操作见 WORKBENCH_20261027.md。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| SC_STORAGE | 项目下 storage | 数据和配置根目录 |
| SC_AUTH_FILE | storage/admin.json | 管理员哈希配置 |
| SC_PORT | 18120 | manage.py 启动端口 |
| SC_ADMIN_USERNAME | xh | 首次初始化用户名 |
| SC_MAX_UPLOAD | 52428800 | 上传和 GitHub 下载压缩体积 |
| SC_MAX_EXTRACT | 209715200 | 解压总体积 |
| SC_MAX_FILES | 5000 | 包文件/压缩条目限额 |
| SC_MAX_DEPTH | 8 | 文件路径层数 |

实际账号只在服务器配置与交付登录文件中，浏览器和源码没有模型密钥或 SSH 密码。
