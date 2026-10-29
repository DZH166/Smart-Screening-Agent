# 丝带设计前端

从原丝带设计助手的 React/TypeScript 工作台整合，原工程仍保留。
此目录只构建 HSD 同页面工作区，不提供另一套登录或独立网站。

- `pnpm install --frozen-lockfile`，然后 `pnpm build`。
- 产物为 `hsd_tool/static/ribbon/ribbon.js`，由 `ribbon-loader.js` 在首次进入 `#ribbon` 时加载。
- ShadowRoot 隔离工作台与已有页面样式；切换功能保留表单，切出停止轮询，重新进入校验当前会话。
- API 统一使用 `/api/ribbon`，身份取 `/auth/me`；写入携带 HSD 当前页面令牌。用户归属和管理员维护权限以服务端为准。
- 管理入口 `#ribbon-admin`；模型配置在原管理员 Key 账本。
- 草稿选择及未决提交键使用服务端用户 ID 分区。成功精修次数、父版本回退、幂等和下载版本均由服务端决定。
- 未配置正式输出规格时必须保留“演示输出”提示；真实 AI 失败保留错误，不生成演示成功结果。
- 个人作品、版本与私有素材保留50小时；页脚读取接口的 `retention_hours` 并提醒及时下载。共享库和输出配置独立保留。

`node --test tests/api.test.mjs` 验证接口前缀、写令牌和错误处理。
`node tests/browser-smoke.mjs` 用明确的合成接口检查构建产物、同页切换与权限展示；需本机可用的 Playwright（通过 `HSD_PLAYWRIGHT_MODULE` 指定模块绝对路径）。不调用真实模型，不证明图像业务效果。

发布时需同时包含源码和构建产物；不得提交 node_modules、测试截图或运行数据。
