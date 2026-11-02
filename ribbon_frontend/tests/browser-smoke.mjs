// Render the built integration against synthetic HTTP only. No model calls.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.HSD_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const output = path.join(root, "ribbon_frontend/test-results");
await mkdir(output, { recursive: true });
let user = { id: "synthetic-a", username: "测试员工", role: "employee" };
let authorized = true, design = null, job = null, owner = "", jobReads = 0;
const writes = [], errors = [];
let exampleCatalogReads = 0, failExampleCatalog = 0, exampleVariant = "normal", exampleImageRevision = 0;
let holdNextCatalog = false, releaseCatalog = null;
let modelProvider = "test", modelReady = true, modelEditing, modelAuthMode = "demo";
let backgroundFixture = null, rejectBackground = false;
let assetReads = 0, uploadAttempts = 0, uploadFailureAt = 0, uploadHoldAt = 0, releaseUpload = null;
const exampleImageReads = [], badExampleImages = new Set();
const profile = { id: "synthetic-profile", version: 1, name: "合成测试规格", is_demo: true, width: 2400, height: 600, dpi: 150 };
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="150"><rect width="600" height="150" fill="#e7eee2"/><circle cx="120" cy="75" r="40" fill="#a4b989"/><text x="210" y="82" font-size="28">SYNTHETIC TEST</text></svg>';
const imageUrl = "/api/ribbon/synthetic.svg";
const assets = ["flower", "star", "ring"].map(name => ({ id: `demo-${name}`, name: `测试图案 ${name}`, kind: "pattern", source: "synthetic", is_demo: true, shared: true, url: imageUrl }));
assets.push({ id: "demo-bg-sage", name: "测试底图", kind: "background", source: "synthetic", is_demo: true, shared: true, url: imageUrl });
const modes = ["grid", "stagger", "scatter", "single", "ends", "panels", "bordered", "scene", "fullwidth", "alternating", "ends_open", "split", "stacked", "opposed"];
const templates = modes.map((mode, i) => ({ id: `t${i}`, name: ["整齐平铺", "错位平铺", "随机散点", "单排重复", "两端主图", "分区拼接", "上下边饰", "组合循环", "整幅定位", "大小交替", "两端留白", "左右分区", "上下分区", "正倒交替"][i], version: 1, mode, thumbnail_url: imageUrl, enabled: true, rules: {} }));
const exampleCode = mode => `SYNTHETIC-${mode.toUpperCase()}`;
const modeNotes = {
  grid: "合成案例说明排列思路，行数和间距以当前模板为准。",
  stagger: "合成案例用于对照相邻行的错位。",
  scatter: "合成案例的小配饰需要自行选择素材。",
  single: "一个图案重复，多个图案依次排列。",
  ends: "案例中间留白；当前模板中间仍有小图。",
  panels: "案例为两段；当前模板按左中右三段生成。",
  bordered: "第一个图案放中间，其余图案作为上下边饰。",
  scene: "完整组合沿长度重复，不保证无缝拼接。",
  fullwidth: "完整图案保持比例，仅放置一次。",
  alternating: "一大一小交替。",
  ends_open: "两端放图，中间留白。",
  split: "前半组在左，后半组在右。",
  stacked: "前半组在上，后半组在下。",
  opposed: "正向与旋转180度的图案交替，不做镜像。",
};
function exampleCatalog() {
  const examples = templates.map(template => {
    const code = exampleCode(template.mode), missing = exampleVariant === "missing" && template.mode === "grid";
    return { id: code, code, title: `合成${template.name}案例`, description: `明确标记的合成图片，仅测试 ${template.mode} 案例展示。`, look_for: `合成 ${template.mode} 排列`, mode_tags: [template.mode], reference_only: false, width: 1200, height: 150, available: !missing,
      image_url: missing ? null : exampleVariant === "unsafe" && template.mode === "grid" ? "https://example.invalid/unsafe-preview.svg" : `/api/ribbon/layout-examples/${code}/image?v=synthetic-${exampleImageRevision}` };
  });
  for (const [id, title] of [["SCENE", "场景参考"], ["BORDER", "边饰参考"], ["SHAPE", "整幅造型参考"]]) {
    const code = `SYNTHETIC-REFERENCE_${id}`;
    examples.push({ id: code, code, title, description: "明确的合成延展参考，不是新增生成模式。", look_for: "只作排版参考", mode_tags: [], reference_only: true, width: 1200, height: 150, available: true, image_url: `/api/ribbon/layout-examples/${code}/image` });
  }
  return { modes: templates.map(template => ({ mode: template.mode, name: template.name, summary: `合成 ${template.mode} 模式说明`, note: modeNotes[template.mode], example_ids: [exampleCode(template.mode)] })), examples, source_name: `合成案例图库：${user.id}`, note: "仅合成接口，不包含真实图库或模型调用。" };
}
function version(sequence, parent) {
  const id = `v${sequence}`;
  return { id, design_id: design.id, parent_version_id: parent, sequence, prompt: sequence ? "图案缩小" : "", render_kind: "parameters", snapshot: { asset_refs: assets.slice(0, 3).map(a => a.id), background_ref: "demo-bg-sage", template_id: "t1", template_mode: "stagger", template_version: 1, output_profile: profile, params: {} }, preview_url: imageUrl, download_url: `/api/ribbon/versions/${id}/download`, created_at: "2026-01-01T00:00:00Z", provider: "test" };
}
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost"), pathname = url.pathname;
    const json = (value, status = 200) => { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }); res.end(JSON.stringify(value)); };
    if (pathname === "/") {
      let html = await readFile(path.join(root, "hsd_tool/static/index.html"), "utf8");
      html = html.replace("__HSD_TOKEN__", JSON.stringify("synthetic-token")).replace("__HSD_ACCESS__", "{}").replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g, "");
      res.writeHead(200, { "Content-Type": "text/html" }); res.end(html); return;
    }
    if (pathname.startsWith("/static/")) {
      const resolved = path.resolve(root, "hsd_tool", `.${pathname}`);
      if (!resolved.startsWith(path.join(root, "hsd_tool/static") + path.sep)) return json({ error: "not found" }, 404);
      res.writeHead(200, { "Content-Type": pathname.endsWith(".css") ? "text/css" : "text/javascript" }); res.end(await readFile(resolved)); return;
    }
    if (pathname === imageUrl || pathname === "/api/ribbon/synthetic-thumbnail.svg") { res.writeHead(200, { "Content-Type": "image/svg+xml" }); res.end(svg); return; }
    if (pathname === "/api/material/config") return json({ available: false, reason: "合成验收不调用素材模型" });
    if (!pathname.startsWith("/api/ribbon/")) return json({}, 404);
    if (!authorized) return json({ error: "登录已失效" }, 401);
    if (!["GET", "HEAD"].includes(req.method)) {
      assert.equal(req.headers["x-hsd-token"], "synthetic-token");
      let body = ""; for await (const chunk of req) body += chunk;
      if (pathname === "/api/ribbon/assets" && req.headers["content-type"]?.startsWith("multipart/form-data;")) {
        const attempt = ++uploadAttempts;
        writes.push({ path: pathname, body: { multipart: true, attempt } });
        if (attempt === uploadHoldAt) {
          await new Promise(resolve => { releaseUpload = resolve; });
          releaseUpload = null;
          if (res.destroyed) return;
        }
        if (attempt === uploadFailureAt) return json({ detail: "合成：本张上传失败，原文件未保存" }, 422);
        const asset = { id: `synthetic-upload-${attempt}`, name: `上传图案${attempt}`, kind: "pattern", source: "upload", shared: false, is_demo: false,
          url: imageUrl, thumbnail_url: "/api/ribbon/synthetic-thumbnail.svg" };
        assets.push(asset);
        return json(asset);
      }
      writes.push({ path: pathname, body: JSON.parse(body || "{}") });
    }
    if (pathname.endsWith("/auth/me")) return json(user);
    if (pathname.endsWith("/config")) return json({ provider: modelProvider, ai_ready: modelReady, auth_mode: modelAuthMode, output_profile: profile, max_refinements: 2, editing: modelEditing });
    if (pathname.endsWith("/assets")) { assetReads++; return json(assets); }
    if (pathname.endsWith("/templates")) return json(templates);
    if (pathname === "/api/ribbon/layout-examples") {
      exampleCatalogReads++;
      if (holdNextCatalog) {
        holdNextCatalog = false;
        await new Promise(resolve => { releaseCatalog = resolve; });
        releaseCatalog = null;
        if (res.destroyed) return;
      }
      if (failExampleCatalog > 0) { failExampleCatalog--; return json({ error: "合成目录暂时不可用" }, 503); }
      return json(exampleCatalog());
    }
    const exampleImage = /^\/api\/ribbon\/layout-examples\/(SYNTHETIC-[A-Z_]+)\/image$/.exec(pathname);
    if (exampleImage) {
      exampleImageReads.push(exampleImage[1]);
      res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "no-store" });
      res.end(badExampleImages.has(exampleImage[1]) ? "not an image: deliberate synthetic failure" : svg);
      return;
    }
    if (pathname.endsWith("/admin/overview")) return user.role === "admin" ? json({ jobs: [], templates, output_profiles: [profile], users: [user] }) : json({ detail: "仅管理员可维护" }, 403);
    if (pathname.endsWith("/background-jobs")) {
      if (rejectBackground) return json({ detail: "合成底图请求失败，请重试。" }, 400);
      backgroundFixture = { id: "synthetic-background-job", design_id: null, kind: "background", status: "RUNNING", phase: "正在生成底图", provider: modelProvider, attempt: 1, error: null, result_asset_id: null };
      return json(backgroundFixture);
    }
    if (pathname.endsWith("/designs")) {
      if (req.method === "POST") {
        owner = user.id;
        design = { id: "synthetic-design", name: "合成验收作品", current_version_id: null, successful_refinement_count: 0, active_job_id: null, revision: 0, versions: [], active_job: null };
        return json(design);
      }
      return json(design && owner === user.id ? [design] : []);
    }
    if (pathname.includes("/versions/")) { res.writeHead(200, { "Content-Type": "image/svg+xml", "Content-Disposition": 'attachment; filename="synthetic.svg"' }); res.end(svg); return; }
    if (pathname.includes("/jobs/")) { jobReads++; return json(pathname.endsWith("/synthetic-background-job") ? backgroundFixture : job); }
    if (!design || owner !== user.id) return json({ detail: "作品不存在" }, 404);
    if (pathname.endsWith("/generate") || pathname.endsWith("/refinements")) {
      const sequence = design.versions.length, v = version(sequence, design.current_version_id);
      const requested = writes.at(-1).body, selection = pathname.endsWith("/generate") ? requested : requested.selection;
      if (selection) v.snapshot = { ...v.snapshot, asset_refs: selection.asset_ids, background_ref: selection.background_id,
        template_id: selection.template_id, template_mode: templates.find(t => t.id === selection.template_id)?.mode };
      v.editing = modelEditing;
      design.versions.push(v); design.current_version_id = v.id; design.revision++;
      if (sequence) design.successful_refinement_count++;
      job = { id: `job-${sequence}`, design_id: design.id, kind: sequence ? "refinement" : "generate", status: "SUCCEEDED", phase: "completed", attempt: 1, provider: "test", error: null, result_version_id: v.id, result_asset_id: null, created_at: "2026-01-01", updated_at: "2026-01-01", needs_clarification: false };
      return json(job);
    }
    if (pathname.endsWith("/rollback")) {
      design.current_version_id = design.versions.find(v => v.id === design.current_version_id).parent_version_id;
      design.revision++; return json(design);
    }
    return json(design);
  } catch (error) { errors.push(String(error)); res.writeHead(500); res.end("synthetic fixture error"); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
if (process.argv.includes("--serve")) {
  if (process.argv.includes("--admin")) user = { id: "synthetic-admin", username: "合成测试管理员", role: "admin" };
  console.log(`SYNTHETIC UI ONLY: ${base}/#ribbon`);
  await new Promise(() => {});
}
const browser = await chromium.launch({ channel: process.env.HSD_BROWSER_CHANNEL || "chrome", headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  const unsafeRequests = [];
  await context.route("https://example.invalid/**", route => route.abort());
  page.on("request", request => { if (request.url().startsWith("https://example.invalid/")) unsafeRequests.push(request.url()); });
  page.on("pageerror", error => errors.push(String(error)));
  await page.goto(base);
  assert.equal(await page.locator("#ribbon-mount").evaluate(el => !!el.shadowRoot), false, "bundle remains lazy");
  await page.locator('[data-workspace="ribbon"]').click();
  await page.getByRole("button", { name: "生成首稿", exact: true }).waitFor();
  assert.equal(await page.locator(".template-card").count(), 6);
  const moreLayouts = page.getByRole("button", { name: "更多排法（8）", exact: true });
  assert.equal(await moreLayouts.getAttribute("aria-expanded"), "false", "extra modes stay collapsed initially");
  assert.equal(await page.getByRole("button", { name: "排版与规格", exact: true }).count(), 0);
  assert.equal(await page.locator("#ribbon-mount iframe").count(), 0);
  assert.match(await page.locator(".environment-strip").innerText(), /演示输出/);
  assert.match(await page.locator(".page-footer").innerText(), /保留 50 小时/);
  assert.equal(exampleCatalogReads, 0, "case catalog remains lazy before viewing");
  assert.equal(exampleImageReads.length, 0, "case images remain lazy before viewing");
  async function selectLayout(mode) {
    if (modes.indexOf(mode) >= 6 && await moreLayouts.getAttribute("aria-expanded") !== "true") await moreLayouts.click();
    const template = templates.find(item => item.mode === mode);
    const button = page.locator(".template-card").filter({ hasText: template.name });
    await button.click();
    assert.equal(await button.getAttribute("aria-pressed"), "true");
  }
  async function setPatterns(ids) {
    await page.getByRole("button", { name: "素材库", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "图案素材库", exact: true });
    await dialog.waitFor();
    for (const asset of assets.filter(item => item.kind === "pattern")) {
      const button = dialog.locator(".library-card").filter({ has: page.getByRole("img", { name: asset.name, exact: true }) });
      const wanted = ids.includes(asset.id);
      if ((await button.getAttribute("aria-pressed") === "true") !== wanted) await button.click();
      assert.equal(await button.getAttribute("aria-pressed"), String(wanted));
    }
    await dialog.getByRole("button", { name: "关闭弹窗", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
  }
  await moreLayouts.click();
  assert.equal(await page.locator(".template-card").count(), 14, "all eight new algorithms can be selected");
  const generateButton = page.getByRole("button", { name: "生成首稿", exact: true });
  await selectLayout("fullwidth");
  assert.match(await page.locator(".layout-selection-issue").innerText(), /只使用 1 个/);
  assert.equal(await generateButton.isEnabled(), false, "multiple patterns cannot be submitted as a whole fixed design");
  await setPatterns(["demo-flower"]);
  assert.equal(await generateButton.isEnabled(), true);
  assert.match(await page.locator(".layout-selection-help").innerText(), /重复间距不适用/);
  for (const mode of ["bordered", "split", "stacked"]) {
    await selectLayout(mode);
    assert.match(await page.locator(".layout-selection-issue").innerText(), /至少需要 2 个/);
    assert.equal(await generateButton.isEnabled(), false, `${mode} requires two patterns`);
  }
  await setPatterns(["demo-flower", "demo-star"]);
  for (const mode of ["bordered", "split", "stacked", "ends_open"]) {
    await selectLayout(mode);
    assert.equal(await page.locator(".layout-selection-issue").count(), 0);
    assert.equal(await generateButton.isEnabled(), true, `valid ${mode} selection is usable`);
  }
  await setPatterns(["demo-flower", "demo-star", "demo-ring"]);
  assert.equal(await generateButton.isEnabled(), false, "two open ends reject three patterns");
  assert.match(await page.locator(".layout-selection-issue").innerText(), /最多使用 2 个/);
  for (const mode of ["scene", "alternating", "opposed"]) {
    await selectLayout(mode);
    assert.equal(await generateButton.isEnabled(), true, `${mode} accepts the selected three patterns`);
  }
  await selectLayout("stagger");
  await moreLayouts.click();
  assert.equal(await page.locator(".template-card").count(), 6);
  assert.equal(writes.length, 0, "choosing layouts and correcting selection only edits the local draft");
  await page.getByRole("button", { name: "生成首稿", exact: true }).click();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  const text = page.locator(".refinement-body textarea");
  await text.fill("图案缩小一些");
  await moreLayouts.click();

  // The custom template IDs intentionally differ from their modes: employee
  // case viewing must use mode, remain read-only, and preserve the workspace.
  async function workspaceState() {
    return page.locator("#ribbon-mount").evaluate(host => {
      const scope = host.shadowRoot;
      return {
        template: scope.querySelector('.template-card[aria-pressed="true"]')?.textContent?.trim(),
        patterns: [...scope.querySelectorAll(".pattern-tile > span")].map(item => item.textContent),
        background: scope.querySelector(".background-selected strong")?.textContent,
        prompt: scope.querySelector(".refinement-body textarea")?.value,
        download: scope.querySelector("a[download]")?.getAttribute("href"),
        quota: scope.querySelector(".quota-card")?.textContent,
        moreLayoutsOpen: scope.querySelector(".more-layouts-toggle")?.getAttribute("aria-expanded"),
      };
    });
  }
  async function waitCaseImage(code) {
    await page.waitForFunction(expected => {
      const scope = document.querySelector("#ribbon-mount")?.shadowRoot;
      const image = [...(scope?.querySelectorAll(".layout-example img") || [])].find(item => item.alt.includes(expected));
      return !!image?.complete && image.naturalWidth > 0;
    }, code);
  }
  async function openCase(mode) {
    const template = templates.find(item => item.mode === mode);
    await page.getByRole("button", { name: `查看${template.name}案例`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: `${template.name} · 案例`, exact: true });
    await dialog.waitFor();
    return dialog;
  }
  async function closeCase(mode, escape = false) {
    const template = templates.find(item => item.mode === mode);
    if (escape) await page.keyboard.press("Escape");
    else await page.getByRole("dialog").getByRole("button", { name: "关闭弹窗", exact: true }).click();
    await page.locator(".layout-examples-modal").waitFor({ state: "hidden" });
    await page.waitForFunction(label => document.querySelector("#ribbon-mount")?.shadowRoot?.activeElement?.getAttribute("aria-label") === label, `查看${template.name}案例`);
  }
  async function refreshWorkspace() {
    await page.locator('[data-workspace="numbering"]').click();
    await page.locator('[data-workspace="ribbon"]').click();
    await page.getByRole("button", { name: "开始精修", exact: true }).waitFor();
  }
  const unchangedWorkspace = await workspaceState(), writesBeforeCases = writes.length;
  const quotaBeforeCases = design.successful_refinement_count;
  for (const [index, template] of templates.entries()) {
    const dialog = await openCase(template.mode), code = exampleCode(template.mode);
    await dialog.getByText(code, { exact: true }).waitFor();
    assert.equal(await dialog.locator(".layout-example").count(), 1, `only ${template.mode} case is shown`);
    assert.equal(await dialog.locator(".layout-mode-note").innerText(), modeNotes[template.mode]);
    await waitCaseImage(code);
    if (template.mode === "stagger") {
      await dialog.getByRole("button", { name: `放大查看 ${code}`, exact: true }).click();
      assert.equal(await dialog.locator(".layout-example-viewport.is-zoomed").getAttribute("tabindex"), "0");
      assert.equal(await dialog.locator(".layout-example-viewport").evaluate(el => el.scrollWidth > el.clientWidth), true, "wide case can be scrolled at original preview size");
      await dialog.getByRole("button", { name: "关闭弹窗", exact: true }).focus();
      await page.keyboard.press("Shift+Tab");
      assert.equal(await page.locator("#ribbon-mount").evaluate(el => el.shadowRoot.activeElement?.classList.contains("layout-example-viewport")), true, "backward focus reaches the keyboard-scrollable image");
      await page.keyboard.press("Tab");
      assert.equal(await page.locator("#ribbon-mount").evaluate(el => el.shadowRoot.activeElement?.getAttribute("aria-label")), "关闭弹窗", "focus is trapped inside the case dialog");
    }
    await closeCase(template.mode, index % 2 === 0);
    assert.deepEqual(await workspaceState(), unchangedWorkspace, "viewing and closing never edits selection or refinement text");
  }
  assert.equal(exampleCatalogReads, 1, "same workspace reuses the loaded catalog");
  assert.equal(exampleImageReads.length, 14, "only the fourteen requested case images loaded");
  await page.getByRole("button", { name: "查看全部案例", exact: true }).click();
  let caseDialog = page.getByRole("dialog", { name: "全部排版案例", exact: true });
  await caseDialog.locator(".layout-example").last().waitFor();
  assert.equal(await caseDialog.locator(".layout-reference-tag").count(), 3, "extensions remain reference-only");
  assert.equal(await caseDialog.locator(".layout-example-reference").count(), 3);
  for (const mode of ["ends", "panels"]) {
    const article = caseDialog.locator(".layout-example").filter({ has: page.getByText(exampleCode(mode), { exact: true }) });
    assert.match(await article.locator(".layout-mode-note").innerText(), new RegExp(modeNotes[mode]));
  }
  await caseDialog.getByRole("button", { name: "关闭弹窗", exact: true }).click();
  await caseDialog.waitFor({ state: "hidden" });
  const cachedReads = exampleCatalogReads;
  await openCase("grid");
  await page.getByRole("dialog").getByText(exampleCode("grid"), { exact: true }).waitFor();
  assert.equal(exampleCatalogReads, cachedReads, "reopening does not request the catalog again");
  await closeCase("grid");
  await refreshWorkspace();
  await openCase("grid");
  await page.getByRole("dialog").getByText(exampleCode("grid"), { exact: true }).waitFor();
  assert.equal(exampleCatalogReads, cachedReads + 1, "leaving the feature clears its private case cache");
  await closeCase("grid");

  // A request that finishes after a closed dialog must not reopen it or seed
  // a catalog cache for a later view.
  await refreshWorkspace();
  holdNextCatalog = true;
  await openCase("grid");
  await page.getByText("正在加载排版案例…", { exact: true }).waitFor();
  await closeCase("grid", true);
  assert.equal(typeof releaseCatalog, "function");
  releaseCatalog();
  const closedReads = exampleCatalogReads;
  await openCase("grid");
  await page.getByRole("dialog").getByText(exampleCode("grid"), { exact: true }).waitFor();
  assert.equal(exampleCatalogReads, closedReads + 1, "cancelled lookup did not fill the next cache");
  await closeCase("grid");

  await refreshWorkspace();
  failExampleCatalog = 1;
  await openCase("grid");
  await page.getByRole("button", { name: "重新加载案例", exact: true }).waitFor();
  const failedReads = exampleCatalogReads;
  await page.getByRole("button", { name: "重新加载案例", exact: true }).click();
  await page.getByRole("dialog").getByText(exampleCode("grid"), { exact: true }).waitFor();
  assert.equal(exampleCatalogReads, failedReads + 1, "catalog failure is recoverable without reloading the workspace");
  await waitCaseImage(exampleCode("grid"));
  await closeCase("grid");

  await refreshWorkspace();
  exampleVariant = "missing";
  const imagesBeforeMissing = exampleImageReads.length;
  caseDialog = await openCase("grid");
  await caseDialog.getByText("这张案例图暂未加载，排版说明仍可查看。", { exact: true }).waitFor();
  assert.equal(await caseDialog.locator(".layout-example img").count(), 0, "missing image does not show a broken picture");
  assert.equal(exampleImageReads.length, imagesBeforeMissing, "missing image is not requested");
  exampleVariant = "normal";
  await caseDialog.getByRole("button", { name: "重新加载", exact: true }).click();
  await waitCaseImage(exampleCode("grid"));
  await closeCase("grid");

  await refreshWorkspace();
  badExampleImages.add(exampleCode("grid"));
  // Give this deliberately broken fixture new content identity so the browser
  // cannot satisfy it from a previously decoded successful image.
  exampleImageRevision++;
  const badReads = exampleImageReads.filter(code => code === exampleCode("grid")).length;
  caseDialog = await openCase("grid");
  await caseDialog.getByRole("button", { name: "重试图片", exact: true }).waitFor();
  assert.equal(await caseDialog.locator(".layout-example img").count(), 0, "failed picture is removed while its explanation remains");
  badExampleImages.delete(exampleCode("grid"));
  await caseDialog.getByRole("button", { name: "重试图片", exact: true }).click();
  await waitCaseImage(exampleCode("grid"));
  assert.equal(exampleImageReads.filter(code => code === exampleCode("grid")).length, badReads + 2, "image retry requested and decoded a recovered image");
  await closeCase("grid");

  await refreshWorkspace();
  exampleVariant = "unsafe";
  caseDialog = await openCase("grid");
  await caseDialog.getByText("这张案例图暂未加载，排版说明仍可查看。", { exact: true }).waitFor();
  assert.equal(await caseDialog.locator(".layout-example img").count(), 0, "unsafe external image URL is refused");
  assert.deepEqual(unsafeRequests, [], "no external gallery or model image request is emitted");
  await closeCase("grid");
  exampleVariant = "normal";

  // Reproduce a busy accepted task without creating another task or model call.
  // Viewing help must stay enabled while the actual selection controls lock.
  const settledJob = job;
  job = { ...settledJob, status: "RUNNING", phase: "rendering" };
  design.active_job_id = job.id;
  design.active_job = job;
  await refreshWorkspace();
  await page.waitForFunction(() => [...document.querySelector("#ribbon-mount").shadowRoot.querySelectorAll(".template-card")].every(button => button.disabled));
  assert.equal(await page.getByRole("button", { name: "查看两端主图案例", exact: true }).isEnabled(), true);
  await openCase("ends");
  await page.getByRole("dialog").getByText(exampleCode("ends"), { exact: true }).waitFor();
  await closeCase("ends");
  design.active_job_id = null;
  design.active_job = null;
  job = settledJob;
  await refreshWorkspace();
  await page.waitForFunction(() => [...document.querySelector("#ribbon-mount").shadowRoot.querySelectorAll(".template-card")].every(button => !button.disabled));
  assert.deepEqual(await workspaceState(), unchangedWorkspace, "all case loading and failure paths preserve the workspace");
  assert.equal(writes.length, writesBeforeCases, "case views and retries never create a mutation request");
  assert.equal(design.successful_refinement_count, quotaBeforeCases, "case views never debit refinements");

  await page.locator('[data-workspace="numbering"]').click();
  await page.locator('[data-workspace="ribbon"]').click();
  await page.getByRole("button", { name: "开始精修", exact: true }).waitFor();
  assert.equal(await text.inputValue(), "图案缩小一些", "same-user switch retains draft text");
  await page.getByRole("button", { name: "开始精修", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/v1/download");
  await page.getByRole("button", { name: "回退上一版", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/v0/download");
  assert.equal(design.successful_refinement_count, 1, "rollback does not refund quota");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载当前图", exact: true }).click();
  assert.equal((await downloadPromise).suggestedFilename(), "synthetic.svg");
  for (const size of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }, { width: 1100, height: 768 }]) {
    await page.setViewportSize(size);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
    assert.equal(overflow, false, `no horizontal overflow at ${size.width}`);
    await page.screenshot({ path: path.join(output, `ribbon-${size.width}.png`), fullPage: true });
  }
  const reads = jobReads;
  await page.waitForTimeout(1500);
  assert.equal(jobReads, reads, "terminal task stops polling");
  // An already saved extended layout must reveal its selected option when the
  // employee returns, rather than resetting to a basic layout or hiding it.
  const currentVersion = design.versions.find(v => v.id === design.current_version_id);
  currentVersion.snapshot = { ...currentVersion.snapshot, asset_refs: ["demo-flower"], template_id: templates.find(t => t.mode === "fullwidth").id, template_mode: "fullwidth" };
  await page.evaluate(() => localStorage.removeItem("ribbon:synthetic-a:selection"));
  await page.reload();
  await page.locator('.template-card[aria-pressed="true"]').filter({ hasText: "整幅定位" }).waitFor();
  assert.equal(await moreLayouts.getAttribute("aria-expanded"), "true", "restoring a new mode automatically expands its section");
  assert.equal(await page.locator(".pattern-tile").count(), 1);
  assert.equal(await page.locator(".layout-selection-issue").count(), 0, "valid restored whole design is not incorrectly blocked");
  await openCase("fullwidth");
  await page.getByRole("dialog").getByText(exampleCode("fullwidth"), { exact: true }).waitFor();
  await closeCase("fullwidth", true);
  assert.equal(await moreLayouts.getAttribute("aria-expanded"), "true", "case viewing preserves the expanded new mode section");
  user = { id: "synthetic-b", username: "另一测试员工", role: "employee" };
  await page.locator('[data-workspace="numbering"]').click();
  await page.locator('[data-workspace="ribbon"]').click();
  await page.getByRole("button", { name: "生成首稿", exact: true }).waitFor();
  assert.equal(await page.getByRole("link", { name: "下载当前图", exact: true }).count(), 0, "different user cannot see old version UI");
  const readsBeforeIdentity = exampleCatalogReads;
  await openCase("grid");
  await page.getByRole("dialog").getByText(exampleCode("grid"), { exact: true }).waitFor();
  assert.equal(exampleCatalogReads, readsBeforeIdentity + 1, "new identity does not reuse the prior employee catalog");
  assert.match(await page.locator(".layout-examples-source").innerText(), /synthetic-b/, "catalog is fetched under the current identity");
  await closeCase("grid");

  // A configured provider label is synthetic here: no external model request
  // is ever made. Exercise the employee handoff using the real built UI.
  modelProvider = "deepseek_seedream";
  modelAuthMode = "hsd";
  modelReady = false;
  modelEditing = { allowed_operations: ["parameters", "edit_asset", "edit_background"],
    allowed_parameters: ["scale", "spacing", "rotation", "offset_x", "offset_y", "background_color"],
    composite_edit: false, composite_edit_reason: "合成长条不支持直接整幅修改，请修改图案或底图后重新排版。", planner_sees_images: false };
  await page.reload();
  await generateButton.waitFor();
  assert.equal(await generateButton.isEnabled(), true, "an unconfigured AI does not block deterministic first drafts");
  let backgroundButton = page.getByRole("button", { name: "AI 生成底图", exact: true });
  assert.equal(await backgroundButton.isEnabled(), false);
  assert.equal(await page.getByLabel("底图要求（可不填）", { exact: true }).isEnabled(), false);
  assert.match(await page.locator("#background-ai-unavailable").innerText(), /仍可/);
  await generateButton.click();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  await text.fill("图案缩小一些");
  assert.equal(await page.getByRole("button", { name: "开始精修", exact: true }).isEnabled(), false, "unconfigured AI cannot accept a text model request");
  await selectLayout("single");
  await text.fill("");
  assert.equal(await page.getByRole("button", { name: "开始精修", exact: true }).isEnabled(), true, "applying a new selection remains available without AI");
  await page.getByRole("button", { name: "开始精修", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/v1/download");
  assert.equal(writes.at(-1).body.prompt, "应用所选配置");
  assert.equal(writes.at(-1).body.selection.template_id, templates.find(t => t.mode === "single").id);
  modelReady = true;
  await page.reload();
  await text.waitFor();
  await page.locator(".model-edit-boundary").waitFor();
  assert.match(await page.locator(".model-edit-boundary").innerText(), /修改图案或底图/);
  assert.equal(await page.getByRole("button", { name: "给画面添加星光", exact: true }).count(), 0, "unsupported whole-strip edits are not encouraged");
  assert.match(await page.locator(".pattern-tile > span").first().innerText(), /^1\. /, "selected pattern order is visible");
  await page.locator(".model-workflow-help summary").click();
  assert.match(await page.locator(".model-workflow-help").innerText(), /不把图片发给它审图/);
  await page.locator(".model-workflow-help summary").click();
  const backgroundText = page.getByLabel("底图要求（可不填）", { exact: true });
  await backgroundText.fill(" 浅蓝色细条纹，不要文字 ");
  rejectBackground = true;
  const requestsBeforeFailure = writes.length;
  await backgroundButton.click();
  await page.getByRole("alert").getByText("合成底图请求失败，请重试。", { exact: true }).waitFor();
  assert.equal(writes.length, requestsBeforeFailure + 1);
  assert.equal(writes.at(-1).body.prompt, "浅蓝色细条纹，不要文字", "employee background instructions reach the existing API");
  assert.equal(await backgroundText.inputValue(), " 浅蓝色细条纹，不要文字 ", "failure keeps the input draft");
  assert.equal(await backgroundButton.isEnabled(), true, "definite failure permits a clear retry");
  rejectBackground = false;
  await backgroundButton.click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector("#background-prompt")?.disabled);
  assert.equal(await backgroundButton.isEnabled(), false, "an accepted background request cannot be submitted twice");
  const acceptedBackgroundWrites = writes.filter(w => w.path.endsWith("/background-jobs")).length;
  assets.push({ id: "synthetic-ai-background", name: "合成AI底图", kind: "background", source: "synthetic", is_demo: true, shared: false, url: imageUrl });
  backgroundFixture = { ...backgroundFixture, status: "SUCCEEDED", phase: "已保存", result_asset_id: "synthetic-ai-background" };
  await page.locator(".background-selected strong").filter({ hasText: "合成AI底图" }).waitFor();
  assert.equal(writes.filter(w => w.path.endsWith("/background-jobs")).length, acceptedBackgroundWrites);
  assert.equal(await backgroundText.inputValue(), " 浅蓝色细条纹，不要文字 ");
  await backgroundText.focus();
  await page.locator('[data-workspace="numbering"]').click();
  await page.locator('[data-workspace="ribbon"]').click();
  assert.equal(await backgroundText.inputValue(), " 浅蓝色细条纹，不要文字 ", "same-user feature switching preserves the draft");

  // Existing works retain their own output geometry when inputs are changed;
  // global profile changes must neither remove nor invent edit capabilities.
  const savedProfile = { ...profile };
  const baseVersion = design.versions.find(v => v.id === design.current_version_id);
  baseVersion.snapshot = { ...baseVersion.snapshot, composite_ref: "synthetic-composite",
    output_profile: { ...profile, width: 1024, height: 1024 } };
  baseVersion.editing = { ...modelEditing, allowed_operations: ["edit_composite"], allowed_parameters: [],
    composite_edit: true, composite_edit_reason: "" };
  Object.assign(profile, { width: 11811, height: 520 });
  await page.evaluate(() => localStorage.removeItem("ribbon:synthetic-b:selection"));
  await page.reload();
  await page.getByRole("button", { name: "给画面添加星光", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "图案缩小一些，间距拉开一点", exact: true }).count(), 0, "a composite has no independent parameter suggestions before reselecting");
  await setPatterns(["demo-flower"]);
  await selectLayout("fullwidth");
  assert.equal(await page.getByRole("button", { name: "给画面添加星光", exact: true }).count(), 1, "old square work keeps its supported geometry despite a new global long strip");
  assert.equal(await page.getByRole("button", { name: "图案缩小一些", exact: true }).count(), 1, "reselection restores independent layer editing");
  assert.equal(await page.getByRole("button", { name: "图案缩小一些，间距拉开一点", exact: true }).count(), 0, "the selected non-repeating mode does not offer spacing");
  await selectLayout("stagger");
  assert.equal(await page.getByRole("button", { name: "图案缩小一些，间距拉开一点", exact: true }).count(), 1, "the newly selected repeating mode restores spacing");

  baseVersion.snapshot = { ...baseVersion.snapshot, output_profile: { ...profile, width: 11811, height: 520 } };
  baseVersion.editing = { ...modelEditing, allowed_operations: [], allowed_parameters: [],
    composite_edit: false, composite_edit_reason: "原长条不可直接整幅编辑，请重新选图后修改独立图案或底图。" };
  Object.assign(profile, { width: 1024, height: 1024 });
  modelEditing = { ...modelEditing, allowed_operations: ["parameters", "edit_asset", "edit_background", "edit_composite"],
    composite_edit: true, composite_edit_reason: "" };
  await page.evaluate(() => localStorage.removeItem("ribbon:synthetic-b:selection"));
  await page.reload();
  await page.locator(".model-edit-boundary").waitFor();
  await selectLayout("grid");
  assert.equal(await page.getByRole("button", { name: "给画面添加星光", exact: true }).count(), 0, "old long-strip work does not gain whole-image editing from the new global square profile");
  assert.equal(await page.getByRole("button", { name: "给第一个图案添加星光", exact: true }).count(), 1, "reselection restores asset editing without inventing unsupported whole-image editing");
  assert.match(await page.locator(".model-edit-boundary").innerText(), /原长条/);
  await page.getByRole("button", { name: "新建作品", exact: true }).click();
  await generateButton.waitFor();
  assert.equal(await page.getByRole("button", { name: "给画面添加星光", exact: true }).count(), 1, "a genuinely new work uses the current global profile capabilities");
  Object.assign(profile, savedProfile);
  modelProvider = "test"; modelReady = false; modelEditing = undefined;
  modelAuthMode = "local";
  await page.reload();
  await generateButton.waitFor();
  const localBackground = page.getByRole("button", { name: "生成测试底图", exact: true });
  assert.equal(await localBackground.isEnabled(), true, "local fixtures remain usable without real AI credentials");
  assert.match(await page.locator(".environment-strip").innerText(), /测试模型 · 演示模式/);
  assert.match(await page.locator(".test-limit").innerText(), /测试替身/);
  await generateButton.click();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  await text.fill("图案缩小一些");
  assert.equal(await page.getByRole("button", { name: "开始精修", exact: true }).isEnabled(), true);
  await page.getByRole("button", { name: "开始精修", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/v1/download");
  await page.getByLabel("底图要求（可不填）", { exact: true }).fill("本地测试蓝色底图");
  await localBackground.click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector("#background-prompt")?.disabled);
  assert.equal(writes.at(-1).body.prompt, "本地测试蓝色底图");
  backgroundFixture = { ...backgroundFixture, status: "SUCCEEDED", phase: "已保存", result_asset_id: "synthetic-ai-background" };
  await page.locator(".background-selected strong").filter({ hasText: "合成AI底图" }).waitFor();
  modelAuthMode = "demo";

  modelAuthMode = "hsd";
  await page.reload();
  await localBackground.waitFor();
  assert.equal(await localBackground.isEnabled(), false, "employee HSD mode never permits the test provider");
  await text.fill("图案缩小一些");
  assert.equal(await page.getByRole("button", { name: "开始精修", exact: true }).isEnabled(), false);
  modelReady = true;
  await page.reload();
  await localBackground.waitFor();
  assert.equal(await localBackground.isEnabled(), false, "an inconsistent ready flag cannot enable test models for employees");
  modelAuthMode = "demo";

  // Uploads remain serial, expose only acknowledged items, and retain earlier
  // successes after a later file fails. No extra catalog refresh is needed.
  user = { id: "synthetic-upload-user", username: "测试上传员工", role: "customer" };
  await page.reload();
  await page.getByRole("button", { name: "上传图案", exact: true }).waitFor();
  const uploadInput = page.locator("#ribbon-mount input[type=file]").first();
  const syntheticFiles = [1, 2, 3].map(index => ({ name: `synthetic-${index}.png`, mimeType: "image/png", buffer: Buffer.from(svg) }));
  const readsBeforeUpload = assetReads, attemptsBeforeUpload = uploadAttempts;
  uploadHoldAt = uploadAttempts + 2;
  uploadFailureAt = uploadAttempts + 3;
  await uploadInput.setInputFiles(syntheticFiles);
  await page.getByRole("img", { name: `上传图案${attemptsBeforeUpload + 1}`, exact: true }).waitFor();
  await page.getByText("已上传 1 / 3 张，正在上传第 2 张…", { exact: true }).waitFor();
  assert.equal(uploadAttempts, attemptsBeforeUpload + 2, "third upload waits for the second response");
  assert.equal(await page.getByRole("img", { name: `上传图案${attemptsBeforeUpload + 2}`, exact: true }).count(), 0, "an unacknowledged file is not shown as saved");
  await page.locator('[data-workspace="numbering"]').click();
  await page.locator('[data-workspace="ribbon"]').click();
  await page.getByRole("img", { name: `上传图案${attemptsBeforeUpload + 1}`, exact: true }).waitFor();
  assert.ok(releaseUpload);
  releaseUpload();
  await page.getByRole("alert").getByText(/已上传 2 个，其余未完成/).waitFor();
  assert.equal(uploadAttempts, attemptsBeforeUpload + 3, "a failed file is not retried automatically");
  assert.equal(assetReads, readsBeforeUpload, "upload responses update the catalog without another full read");
  assert.equal(await uploadInput.inputValue(), "", "the file input can select the same file again");
  const firstUploadedImage = page.getByRole("img", { name: `上传图案${attemptsBeforeUpload + 1}`, exact: true });
  assert.equal(await firstUploadedImage.getAttribute("src"), "/api/ribbon/synthetic-thumbnail.svg");
  assert.equal(await firstUploadedImage.getAttribute("decoding"), "async");
  await page.getByRole("button", { name: "素材库", exact: true }).click();
  const libraryImage = page.getByRole("dialog", { name: "图案素材库" }).getByRole("img", { name: `上传图案${attemptsBeforeUpload + 1}`, exact: true });
  assert.equal(await libraryImage.getAttribute("src"), "/api/ribbon/synthetic-thumbnail.svg");
  assert.equal(await libraryImage.getAttribute("loading"), "lazy");
  await page.getByRole("button", { name: "关闭弹窗", exact: true }).click();

  // A different employee identity unmounts the old controller. Its accepted
  // request may finish server-side, but it cannot send remaining old files.
  uploadFailureAt = 0;
  uploadHoldAt = uploadAttempts + 1;
  const attemptsBeforeIdentityChange = uploadAttempts;
  await uploadInput.setInputFiles(syntheticFiles);
  await page.getByText("正在上传第 1 / 3 张…", { exact: true }).waitFor();
  while (!releaseUpload) await new Promise(resolve => setTimeout(resolve, 10));
  user = { id: "synthetic-next-upload-user", username: "另一个合成员工", role: "customer" };
  await page.locator('[data-workspace="numbering"]').click();
  await page.locator('[data-workspace="ribbon"]').click();
  await page.getByRole("button", { name: "上传图案", exact: true }).waitFor();
  releaseUpload();
  await page.waitForTimeout(150);
  assert.equal(uploadAttempts, attemptsBeforeIdentityChange + 1, "old files stop at the identity boundary");
  assert.equal(await page.getByText(/其余未完成/).count(), 0, "old upload notices cannot overwrite a new employee workspace");
  await page.reload();
  await localBackground.waitFor();
  assert.equal(await localBackground.isEnabled(), true, "demo fixture mode is also available without a real API key");

  user = { id: "synthetic-admin", username: "测试管理员", role: "admin" };
  await page.goto(`${base}/#ribbon-admin`);
  await page.locator(".admin-tabs").waitFor({ timeout: 5000 }).catch(async error => {
    await page.screenshot({ path: path.join(output, "ribbon-admin-failure.png"), fullPage: true });
    console.error("Browser errors:", errors, await page.locator("#ribbon-mount").innerText());
    throw error;
  });
  await page.getByRole("button", { name: "排版模式", exact: true }).click();
  const ruleType = page.locator(".admin-form select");
  await ruleType.waitFor();
  assert.equal(await ruleType.locator("option").count(), 14);
  await ruleType.selectOption("fullwidth");
  assert.match(await page.locator(".template-rules-help").innerText(), /不使用 rows 或 step_ratio/);
  await ruleType.selectOption("bordered");
  assert.match(await page.locator(".template-rules-help").innerText(), /不使用 rows/);
  assert.match(await page.locator(".template-rules-help").innerText(), /step_ratio/);
  await page.screenshot({ path: path.join(output, "ribbon-admin.png"), fullPage: true });
  authorized = false;
  await page.reload();
  await page.getByText("登录已失效", { exact: true }).waitFor();
  assert.equal(await page.locator(".workspace-grid").count(), 0);
  assert.deepEqual(errors, []);
  assert.ok(writes.some(w => w.path.endsWith("/generate")));
  assert.ok(writes.some(w => w.path.endsWith("/refinements")));
  assert.ok(writes.some(w => w.path.endsWith("/rollback")));
  console.log("PASS built ShadowRoot workspace: serial upload progress and partial-success retention, thumbnail/lazy image paths, identity-bound upload cancellation; configured/unconfigured model handoff, original-size edit boundaries, 14 modes and examples, generation/refinement/rollback/download and 1366/1920/1100 layouts (synthetic HTTP only)");
} finally { releaseCatalog?.(); releaseUpload?.(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
