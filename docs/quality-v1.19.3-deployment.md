# v1.19.3 部署与线上复核回执

- 时间：2026-10-28 15:01 +0800（Asia/Shanghai）
- 版本：`v1.19.3`，提交 `63ad8ce68d5c37b8bc5c9846b66f1438164a9b70`
- 目标：`https://39.106.45.116:8443`（Nginx TLS → 127.0.0.1:8830 单 Gunicorn worker）
- 前置：部署前 `busy jobs: 0`，没有打断员工任务

## 1. 部署与代码核对

```
releasing 63ad8ce6… -> /opt/hsd-agent/releases/63ad8ce6…
service: active
current: /opt/hsd-agent/releases/63ad8ce68d5c37b8bc5c9846b66f1438164a9b70
```

`/opt/hsd-agent/current` 指向新版本；`NRestarts=0`，近 15 分钟无 ERROR 日志。

## 2. 接口复核（只读）

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| `GET /healthz`（带正式 Host） | `ok` | 新增的未登录存活探针 |
| `GET /` | `200` | 员工入口正常 |
| `GET /api/health`（未登录） | `401` | 详细状态仍要求登录，未因探针放宽 |
| `GET /` 直连 8830（无代理头） | `403` | 代理边界按设计拒绝非 Nginx 来源 |
| 访问日志 | 有 `GET / … 403 74 "-" "curl/7.81.0"` 行 | Gunicorn access log 已写入 journald |
| `busy jobs` | `0` | 部署后无残留运行中任务 |

## 3. 运维项执行结果

- **systemd 加固**：已写入 `CapabilityBoundingSet=`、`AmbientCapabilities=`、
  `SystemCallArchitectures=native`、`RestrictNamespaces=yes`、`RestrictSUIDSGID=yes`、
  `LockPersonality=yes`、`ProtectClock=yes`、`ProtectKernelLogs=yes`、`ProtectHostname=yes`；
  原单元备份在 `/root/hsd-agent.service.bak.<时间戳>`。服务重启后仍 active。
- **健康探针**：`hsd-healthcheck.timer` 已 `enabled` + `active`，每 5 分钟执行一次。
  首次运行输出 `ok host=39.106.45.116:8443 free_mb=2351`，`systemctl --failed` 中没有本项目单元。
- **备份**：`/var/backups/hsd-agent/hsd-agent-20261028T070125Z.tar.gz`（权限 600），
  sha256 `ac7e74df4fec8ebdb61467cfc1f806bdb8660f052511b980445e72bd9fb7f988`，
  `gzip -t` 通过，内容 13 项：`etc/hsd-agent/{service.env,private/{admin.json,employee.code,credential.key}}`
  与 `settings/{ai_settings.json,ai_usage.json,material_volcengine_settings.json,employee_access/access_codes.json}`。

## 4. 部署中实际发现并修掉的问题

第一次部署后健康探针启动失败：`/usr/bin/env: 'bash\r': No such file or directory`，
`backup.sh` 报 `set: pipefail: invalid option name`。原因是本机 `core.autocrlf=true`，
`git archive` 把 `deploy/*.sh` 打成了 CRLF，安装到服务器后 shebang 与 `set -o pipefail` 全部失效。

修复：新增 `.gitattributes`（`*.sh`/`*.service`/`*.timer` 强制 `eol=lf`），重新打包并部署
（提交 `63ad8ce`），随后探针一次通过。该问题只在 Linux 部署侧暴露，本地测试与 Python
代码不受影响；教训是「部署脚本本身也要在目标系统上跑一次」已写进本轮审核报告。

## 5. 未做 / 遗留

- 未调用付费模型，未对真实图片做画质验收。
- 未删除任何员工上传、结果或人工验收目录；数据卷剩余 2 351 MB（81% 已用）。
- 服务器上另一个项目 `hsdribbon-backup.service`（CRM PostgreSQL 备份）自 02:15 起为 failed，
  **不是本项目单元**，未做改动，建议另行处理。
