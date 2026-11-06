# 丝带设计质量分支（feat/ribbon-design-quality）

- 基线：`v1.26.2` / `cd198d4`（main）
- 本分支只做“表达 → 构图 → 观感”里可独立合并的一层：**设计风格预设 + 底纹处理档位 + 重复节奏指标**；
  不改动 `seamless-unit-v2` 的几何算法，不改旧作品快照，也没有调用付费模型。
- 与 main 上的另一条排版优化并行，合并时预计只有 `App.tsx`、`styles.css`、`service.py`、`loop_pipeline_v2.py` 少量冲突。

## 1. 解决的问题

现场样本（`Downloads/背景` ×4、`Downloads/素材` ×27，本分支笔记只引用不提交）暴露三个问题：

1. 背景纹理比主图更抢眼，重复后像墙纸；
2. 所有图案同一基准尺寸，没有主次，画面“平”；
3. 只能凭“密度三档 + 文字精修”表达，用户说不清“差在哪”。

## 2. 本分支实现的改动

### 2.1 设计风格预设（`ribbon_backend/design_style.py`）

`GET /api/ribbon/design-styles` 返回 5 个预设；生成请求在 `selection.design_style` 里带上 id：

| id | 名称 | 落到的字段 |
| --- | --- | --- |
| `classic` | 经典等距 | 不改任何值（老作品、老客户端默认） |
| `airy` | 留白高级 | `density=airy`、`spacing=1.3`、`scale=0.92`、底纹更淡 |
| `hierarchy` | 主辅层级 | 第一个图案 1.24×，其余 0.78×；`spacing=1.08`、底纹更淡 |
| `rhythm` | 大小节奏 | 图案按 1.0/0.8 交替；底纹更淡 |
| `festive` | 热闹饱满 | `density=rich`、`spacing=0.82`、`scale=1.06` |

规则：客户端总是会发完整 `params`，所以“没选”用引擎默认值表示；预设只填这些默认值，
**员工真正改过的值不会被覆盖**。`design_style` 会写入快照，重放/审计可复现。

### 2.2 底纹处理增加 `quiet`

原来只有 `original` / `soft`（55% 白纱）。新增 `quiet`（80% 白纱），并让 `airy/hierarchy/rhythm`
默认使用它；界面上的勾选框改为三档下拉（保持原色 / 柔和 / 更淡）。
样本实测：同一张心形底纹，`quiet` 后主图明显成为视觉主体。

### 2.3 重复节奏指标（`loop.rhythm`）

新作品在循环报告里附带：

```
unit_width       单元宽度 px
repeats_to_length 按 100cm 成品需要的重复次数
groups           本单元的分组数
spacing_cv       组间间距变异系数
size_variety     最大/最小图案尺寸比
coverage         图案覆盖率
```

作品页「输出详情」多一行“100cm 约 N 个单元 · 尺寸差 X×”。指标只描述构图，不参与
`checked/needs_review` 判定（那仍只由像素接缝决定）。

## 3. 样本实测（本地渲染，无模型调用）

用 4 张真实素材 + 1 张真实背景，在 520px 高、300 DPI 下渲染 5 个预设：

| 模式/预设 | 单元宽 | 覆盖率 | 尺寸差 |
| --- | --- | --- | --- |
| grid/classic | 867px | 0.428 | 1.36× |
| grid/airy | 952px | 0.192 | 1.36× |
| grid/hierarchy | 826px | 0.381 | **1.98×** |
| grid/rhythm | 776px | 0.350 | 1.56× |
| grid/festive | 604px | 0.654 | 1.37× |

结论（主观判断，样本有限，不代表所有素材）：

- `hierarchy` 的主图一眼可见，画面有重心；
- `airy` 呼吸感明显，但需要主图支撑，否则显空；
- `quiet` 对“花纹吵闹”的背景改善最大；
- `festive` 在已有复杂背景时容易糊成一片，适合纯色底。

对比图：`docs/preview/ribbon-design-quality-grid.png`、`...-panels.png`。

## 4. 尚未做（留给后续或合并讨论）

1. **三选一候选对比**（同一次输入渲染 3 个风格缩略图再选）——仍需新增“试排”接口，收益最大；
2. 规划器接收本地计算的图案主色/边缘密度描述；
3. 底纹按图案主色自动着色；
4. 真实付费模型的小样本复核（本轮为 0 次调用）。

## 5. 验证

- `tests/ribbon/test_design_styles.py`（预设展开、默认值覆盖规则、未知 id 回退）
- `tests/ribbon/test_loop_workflow.py`（快照落地: spacing/scale/quiet tone）
- `tests/ribbon/test_loop_v2_geometry.py`（rhythm 指标）
- 丝带其余测试 109 项、宿主 98 项、质量门禁通过；前端已重建 `hsd_tool/static/ribbon/ribbon.js`。
