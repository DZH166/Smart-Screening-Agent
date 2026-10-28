# 全项目质量审核报告（2026-10-28）

范围：`v1.19.2` 线上代码（`eb7030e`）到本轮修改。目标是「完整运行 + 质量安全」，
不是新增业务功能。所有结论都来自本机代码阅读、可复跑的测试，以及对生产服务器的
**只读**检查；没有调用付费模型，没有改动员工数据。

结论：发现 6 处真实缺陷（全部已修复并补测试），5 项运维缺口（已补齐），
若干 P2 建议（列在第 5 节，未改并说明理由）。审核后完整测试套件通过，
线上部署并逐项复核。

## 1. 检查范围与方法

1. **代码通读**：`hsd_tool/` 全部模块（服务入口、鉴权、素材流水线、归档、清理、
   设置与凭据、静态页面脚本），重点看「异常路径」而不是正常路径。
2. **三个方向的独立审计子代理**：素材流水线与并发、鉴权与密钥、部署与运维。
   子代理结论只作线索，本报告每一条都回到代码或服务器现场复核后才写入。
3. **生产只读检查**：服务状态、发布目录、磁盘/内存、数据卷各目录占用、保留期是否
   真的生效、近三天日志、`busy jobs`。未读员工图片内容，未打印任何密钥。
4. **可复跑验证**：`python -m pytest`（全量）、`node tests/*.js`（8 个浏览器脚本
   合成套件）、新增 `tools/quality_gate.py`、以及部署后的线上复核（第 6 节）。

## 2. 已修复的缺陷

### 2.1 首次保存失败会让任务永久卡在「处理中」（P1）

`material_service._run` 在第一次把任务写成 `processing` 时若磁盘满/权限异常，
异常被外层吞掉，任务停在 `processing`：页面一直转圈，保留期清理也不会处理它
（清理跳过运行中任务），只能等重启。

修复：首存失败即把任务和源图置为 `error`、写可见原因、尽力再保存一次后结束；
兜底 `except Exception` 现在会把所有排队/处理中的源图收敛成 `error`（计费未知的
标记 `submission_unknown`），不再留下「假运行中」的批次。
测试：`tests/test_material_resilience.py::test_a_failed_first_save_ends_the_batch_instead_of_leaving_it_processing`。

### 2.2 精修期间整批都不能下载（P1）

`snapshot` 里 `row["downloadable"]` 额外要求「任务不忙」，于是精修开始后，同一批里
**其它已完成**的素材下载按钮全部变灰，与 v1.19.1「精修只锁该卡片」的承诺矛盾。

修复：可下载性只由服务端状态集合决定（`_DOWNLOADABLE`），与「是否正在跑」解耦；
`asset()` 与打包下载同样只校验状态，不再因忙碌拒绝。
测试：`test_refining_one_design_keeps_the_other_results_downloadable`（`tests/test_material_refine.py`）。

### 2.3 失败批次的源图停在 `queued`，页面看不到原因也无法一键重试（P1）

任务级异常只把任务置为 `error`，源图仍是 `queued`：卡片没有「自动重试」（该按钮只在
源图 `error` 时出现），用户只能框选补提。

修复：任务失败时把每个源图收敛到终态并带上原因；`redo()` 允许对 `error` 源图不带框
一键重跑。
测试：`test_material_resilience.py` 三个用例 + `tests/test_material_ui.js` 的重试用例。

### 2.4 ZIP 中央目录可被用来撑爆内存（P1）

`uploads._validate_archives` 与 `matching._collect` 先用 `zipfile.ZipFile` 解析整包，
再检查条目数。构造一个中央目录很大、实际内容很小的 ZIP（或伪造条目数）即可在
解析阶段吃掉大量内存，而服务是 2 GiB 上限的单进程。

修复：新增 `archive_io.check_directory_size()`，直接读 EOCD/Zip64 EOCD 得到条目数与
声明大小，`os.stat` 之前就拒绝超限包（5000 条 / 20 MB 目录区）；结构损坏转成现有的
友好 ZIP 提示；分卷压缩包明确拒绝。
测试：`tests/test_archive_directory_guard.py`（8 项，含伪造条目数、Zip64、多磁盘）。

### 2.5 内网网关可被 DNS rebinding 读出令牌（P1，仅内网网关模式）

`gateway.is_host()` 只判断 `remote_addr`，`_same_origin()` 又拿请求自己的 `Host` 反推
期望来源。攻击者把域名重绑定到网关监听的内网地址后，浏览器发出的请求来源地址正是
`bind`，同源检查也「自证」，于是能读到状态页里内嵌的网关令牌（可无限制使用共享
DeepSeek Key）并 `POST /configure` 改写共享 Key。

修复：新增 `before_request` 固定主机名白名单（`bind`、`127.0.0.1`、`localhost`、`[::1]`、
本机主机名），不匹配直接 403；同源比较改为与这份固定名单比对，不再信任请求头。
测试：`tests/test_gateway.py` 三个新用例（重绑定读页、伪造 Origin 改写、正常本机访问）。

### 2.6 登录限流表可被未认证流量撑大（P2）

`admin_auth.LoginLimiter` 与 `lan.LanAccess` 用 `defaultdict(deque)` 按来源地址计数，
键只增不减：每次 `blocked()` 探测（登录接口每请求都调）都会新建一个键，
登录成功只 `clear()` 不删键。

修复：读路径不再创建键；空集合立即删除；超过 1024 条时清理过期项并做硬上限（按最后
时间淘汰最旧地址，被淘汰地址重新获得完整配额）。
测试：`tests/test_login_limiter_memory.py`（4 项，含 2000 个来源地址后仍有界）。

## 3. 补齐的运维能力

| 能力 | 文件 | 说明 |
| --- | --- | --- |
| 存活探针 | `hsd_tool/server.py` → `GET /healthz` | 未登录只回 `ok`；`/api/health` 仍需登录，不泄露部署细节 |
| 访问日志 | `hsd_tool/cloud_gunicorn.py` | `accesslog="-"` 写 journald：方法、路径、状态、大小、耗时；不含 Cookie/请求体/密钥 |
| systemd 加固 | `deploy/hsd-agent.service.example` | 清空 Capability、禁新 namespace/SUID/改时钟改主机名，`SystemCallArchitectures=native` |
| 健康检查 | `deploy/hsd-healthcheck.{sh,service,timer}` | 每 5 分钟只读检查 active/`/healthz`/挂载/剩余空间/单实例；失败写 ALERT 到 journal，不重启 |
| 备份与恢复 | `deploy/backup.sh` + [运维与备份](运维与备份.md) | 只备份 `/etc/hsd-agent` 与 `settings`（密钥、访问码哈希、用量），`gzip -t` 校验 + sha256，权限 600 |
| 质量门禁 | `tools/quality_gate.py` | 1 分钟内：编译、导入、JS 语法、8 个合成 UI 套件、密钥扫描、部署文件引用检查 |

## 4. 顺带修掉的工程隐患

- `pytest.ini` 的 `addopts = --basetemp=.pytest_tmp` 会让**两个并发 pytest 进程互相删除**
  临时目录（本轮实际踩到过）。已移除，改用 pytest 自带的唯一临时根。
- `requirements.txt` 里 Pillow 是唯一未锁定的依赖（`>=12.0,<13`），已按本机与服务器
  实测版本锁为 `Pillow==12.3.0`。
- `tools/prepare_release.py` 用 `shutil.copytree(ROOT/"tests")` 打包，会把 git-ignored 的
  `tests/.admin-password` 之类本地凭据一起塞进交付包；且交付说明里写死了历史批次的
  「69 项通过 / 44 自动 16 人工」。已改为只复制 `test_*` 源码、拒绝任何含 password 或点
  开头的文件，版本号从源码读取，并删掉写死的历史数字。
- 素材上传成功后若紧接着的进度查询失败，旧代码先清空上传 id，导致「重新查询」失效、
  只能刷新页面。现在先记住批次 id，查询失败给明确提示，且「重新查询」可继续恢复。
  测试：`tests/test_material_ui.js` 新增用例。

## 5. 已确认但本轮不改（附理由）

1. **`TimeoutStopSec=infinity` + `SendSIGKILL=no`**：停止服务可能长时间等待。这是为了
   让已接受的付费调用收敛并完整记账；改成 90 秒会在部署/重启时丢掉「计费未知」的
   记录。已在运维文档写明卡死时的 `systemctl kill -s SIGKILL` 处置方式。
2. **数据卷 81%（剩 2.3 GiB）**：保留期清理本身工作正常（7 个素材任务目录，0 个超期）。
   占用来自 `jobs` 4.9G 与 `uploads` 2.2G 的历史批次；另有人工验收目录 `acceptance` 836M
   与 `tmp` 54M 不参与自动清理。**删除属于数据操作，未获授权不动**；探针会在剩余
   < 1 GiB 时告警。
3. **`MemoryHigh=1500M` 已触发**（实测常驻约 1.54 GB）：`MemoryHigh` 只做回收压力，
   不是泄漏证据；单 worker + 8 路图像的峰值是设计使然。若要降内存需改图像并发上限，
   属于产品取舍，不在一轮审核里暗改。
4. **无 CI**：仓库没有 `.github/`，本轮先提供可本地/手动运行的 `tools/quality_gate.py`；
   是否接 GitHub Actions 由你决定（私有仓库 Actions 消耗额度）。
5. **`material-settings.js` 的 fetch 没有超时**：只在管理员设置页，最坏是页面一直转圈，
   刷新即可；改动会影响现有保存交互，留待下一轮体验优化一起做。
6. **员工上传图片本身没有单文件上限**：这是已确认的产品决定（大图必须能传），
   像素/结构/磁盘检查仍在；不加字节上限。
7. **同 IP 不同端口不隔离 Cookie**：端口方案固有边界，已在文档声明；换独立域名才能解决。

## 6. 验证回执

- 全量 Python：`python -m pytest` → **2108 passed, 76 skipped**（25 分 17 秒，2026-10-28 14:53 +0800）。
  其后新增的 1 项云模式探针用例单独运行通过；生产代码在两次运行之间未变。
- 浏览器合成套件：8 个 `tests/test_*.js` 全部通过（素材员工页 74 项，含本轮新增的
  “上传后查询失败仍可恢复”用例）。
- 质量门禁：`python tools/quality_gate.py` → `{"ok": true}`，覆盖编译/导入/JS/密钥/部署文件。
- 生产复核（部署 v1.19.3 后）：`/healthz` 200、`/` 200、`/api/health` 未登录 401、
  服务 active 且 `NRestarts` 计数、`busy jobs: 0`、健康定时器首次运行通过、备份脚本产出可校验归档。
- 未做：真实付费模型的图像效果验收；任何员工数据的删除或改写。

## 7. 怎么复跑

```powershell
# 1 分钟门禁（提交前必跑）
.venv\Scripts\python.exe tools\quality_gate.py

# 全量测试（约 26 分钟，不要并发跑两个）
.venv\Scripts\python.exe -m pytest

# 只跑素材相关
.venv\Scripts\python.exe -m pytest tests/test_material_*.py
node tests\test_material_ui.js
```
