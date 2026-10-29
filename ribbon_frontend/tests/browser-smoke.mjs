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
const exampleImageReads = [], badExampleImages = new Set();
const profile = { id: "synthetic-profile", version: 1, name: "合成测试规格", is_demo: true, width: 2400, height: 600, dpi: 150 };
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="150"><rect width="600" height="150" fill="#e7eee2"/><circle cx="120" cy="75" r="40" fill="#a4b989"/><text x="210" y="82" font-size="28">SYNTHETIC TEST</text></svg>';
const imageUrl = "/api/ribbon/synthetic.svg";
const assets = ["flower", "star", "ring"].map(name => ({ id: `demo-${name}`, name: `测试图案 ${name}`, kind: "pattern", source: "synthetic", is_demo: true, shared: true, url: imageUrl }));
assets.push({ id: "demo-bg-sage", name: "测试底图", kind: "background", source: "synthetic", is_demo: true, shared: true, url: imageUrl });
const templates = ["grid", "stagger", "scatter", "single", "ends", "panels"].map((mode, i) => ({ id: `t${i}`, name: ["整齐平铺", "错位平铺", "随机散点", "单排重复", "两端主图", "分区拼接"][i], version: 1, mode, thumbnail_url: imageUrl, enabled: true, rules: {} }));
const exampleCode = mode => `SYNTHETIC-${mode.toUpperCase()}`;
const modeNotes = {
  grid: "合成案例说明排列思路，行数和间距以当前模板为准。",
  stagger: "合成案例用于对照相邻行的错位。",
  scatter: "合成案例的小配饰需要自行选择素材。",
  single: "一个图案重复，多个图案依次排列。",
  ends: "案例中间留白；当前模板中间仍有小图。",
  panels: "案例为两段；当前模板按左中右三段生成。",
};
function exampleCatalog() {
  const examples = templates.map(template => {
    const code = exampleCode(template.mode), missing = exampleVariant === "missing" && template.mode === "grid";
    return { id: code, code, title: `合成${template.name}案例`, description: `明确标记的合成图片，仅测试 ${template.mode} 案例展示。`, look_for: `合成 ${template.mode} 排列`, mode_tags: [template.mode], reference_only: false, width: 1200, height: 150, available: !missing,
      image_url: missing ? null : exampleVariant === "unsafe" && template.mode === "grid" ? "https://example.invalid/unsafe-preview.svg" : `/api/ribbon/layout-examples/${code}/image?v=synthetic-${exampleImageRevision}` };
  });
  for (const [id, title] of [["SCENE", "场景参考"], ["BORDER", "边饰参考"], ["SHAPE", "整幅造型参考"]]) {
    const code = `SYNTHETIC-${id}`;
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
    if (pathname === imageUrl) { res.writeHead(200, { "Content-Type": "image/svg+xml" }); res.end(svg); return; }
    if (pathname === "/api/material/config") return json({ available: false, reason: "合成验收不调用素材模型" });
    if (!pathname.startsWith("/api/ribbon/")) return json({}, 404);
    if (!authorized) return json({ error: "登录已失效" }, 401);
    if (!["GET", "HEAD"].includes(req.method)) {
      assert.equal(req.headers["x-hsd-token"], "synthetic-token");
      let body = ""; for await (const chunk of req) body += chunk;
      writes.push({ path: pathname, body: JSON.parse(body || "{}") });
    }
    if (pathname.endsWith("/auth/me")) return json(user);
    if (pathname.endsWith("/config")) return json({ provider: "test", ai_ready: true, auth_mode: "hsd", output_profile: profile, max_refinements: 2 });
    if (pathname.endsWith("/assets")) return json(assets);
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
    const exampleImage = /^\/api\/ribbon\/layout-examples\/(SYNTHETIC-[A-Z]+)\/image$/.exec(pathname);
    if (exampleImage) {
      exampleImageReads.push(exampleImage[1]);
      res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "no-store" });
      res.end(badExampleImages.has(exampleImage[1]) ? "not an image: deliberate synthetic failure" : svg);
      return;
    }
    if (pathname.endsWith("/admin/overview")) return user.role === "admin" ? json({ jobs: [], templates, output_profiles: [profile], users: [user] }) : json({ detail: "仅管理员可维护" }, 403);
    if (pathname.endsWith("/designs")) {
      if (req.method === "POST") {
        owner = user.id;
        design = { id: "synthetic-design", name: "合成验收作品", current_version_id: null, successful_refinement_count: 0, active_job_id: null, revision: 0, versions: [], active_job: null };
        return json(design);
      }
      return json(design && owner === user.id ? [design] : []);
    }
    if (pathname.includes("/versions/")) { res.writeHead(200, { "Content-Type": "image/svg+xml", "Content-Disposition": 'attachment; filename="synthetic.svg"' }); res.end(svg); return; }
    if (pathname.includes("/jobs/")) { jobReads++; return json(job); }
    if (!design || owner !== user.id) return json({ detail: "作品不存在" }, 404);
    if (pathname.endsWith("/generate") || pathname.endsWith("/refinements")) {
      const sequence = design.versions.length, v = version(sequence, design.current_version_id);
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
  assert.equal(await page.getByRole("button", { name: "排版与规格", exact: true }).count(), 0);
  assert.equal(await page.locator("#ribbon-mount iframe").count(), 0);
  assert.match(await page.locator(".environment-strip").innerText(), /演示输出/);
  assert.match(await page.locator(".page-footer").innerText(), /保留 50 小时/);
  assert.equal(exampleCatalogReads, 0, "case catalog remains lazy before viewing");
  assert.equal(exampleImageReads.length, 0, "case images remain lazy before viewing");
  await page.getByRole("button", { name: "生成首稿", exact: true }).click();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  const text = page.locator(".refinement-body textarea");
  await text.fill("图案缩小一些");

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
  assert.equal(exampleImageReads.length, 6, "only the six requested case images loaded");
  await page.getByRole("button", { name: "查看全部案例", exact: true }).click();
  let caseDialog = page.getByRole("dialog", { name: "全部排版案例", exact: true });
  await caseDialog.locator(".layout-example").last().waitFor();
  assert.equal(await caseDialog.locator(".layout-reference-tag").count(), 3, "extensions remain reference-only");
  assert.equal(await caseDialog.locator(".layout-example-reference").count(), 3);
  for (const mode of ["ends", "panels"]) {
    const article = caseDialog.locator(".layout-example").filter({ hasText: exampleCode(mode) });
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
  user = { id: "synthetic-admin", username: "测试管理员", role: "admin" };
  await page.goto(`${base}/#ribbon-admin`);
  await page.locator(".admin-tabs").waitFor({ timeout: 5000 }).catch(async error => {
    await page.screenshot({ path: path.join(output, "ribbon-admin-failure.png"), fullPage: true });
    console.error("Browser errors:", errors, await page.locator("#ribbon-mount").innerText());
    throw error;
  });
  await page.screenshot({ path: path.join(output, "ribbon-admin.png"), fullPage: true });
  authorized = false;
  await page.reload();
  await page.getByText("登录已失效", { exact: true }).waitFor();
  assert.equal(await page.locator(".workspace-grid").count(), 0);
  assert.deepEqual(errors, []);
  assert.ok(writes.some(w => w.path.endsWith("/generate")));
  assert.ok(writes.some(w => w.path.endsWith("/refinements")));
  assert.ok(writes.some(w => w.path.endsWith("/rollback")));
  console.log("PASS built ShadowRoot workspace: existing workflow plus lazy read-only mode examples, custom template IDs, case cache/abort/identity boundaries, close/ESC/focus trap, busy read-only access, reference notes, zoom, catalog/image failure recovery and refused external images; 1366/1920/1100 layouts (synthetic HTTP only)");
} finally { releaseCatalog?.(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
