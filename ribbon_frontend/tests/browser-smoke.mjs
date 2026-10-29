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
const profile = { id: "synthetic-profile", version: 1, name: "合成测试规格", is_demo: true, width: 2400, height: 600, dpi: 150 };
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="150"><rect width="600" height="150" fill="#e7eee2"/><circle cx="120" cy="75" r="40" fill="#a4b989"/><text x="210" y="82" font-size="28">SYNTHETIC TEST</text></svg>';
const imageUrl = "/api/ribbon/synthetic.svg";
const assets = ["flower", "star", "ring"].map(name => ({ id: `demo-${name}`, name: `测试图案 ${name}`, kind: "pattern", source: "synthetic", is_demo: true, shared: true, url: imageUrl }));
assets.push({ id: "demo-bg-sage", name: "测试底图", kind: "background", source: "synthetic", is_demo: true, shared: true, url: imageUrl });
const templates = ["grid", "stagger", "scatter", "single", "ends", "panels"].map((mode, i) => ({ id: `t${i}`, name: ["整齐平铺", "错位平铺", "随机散点", "单排重复", "两端主图", "分区拼接"][i], version: 1, mode, thumbnail_url: imageUrl, enabled: true, rules: {} }));
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
  await page.getByRole("button", { name: "生成首稿", exact: true }).click();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  const text = page.locator(".refinement-body textarea");
  await text.fill("图案缩小一些");
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
  console.log("PASS built ShadowRoot workspace: lazy load, six modes, employee/admin UI, same-page draft, generate/refine/rollback/download, token writes, terminal polling, identity switch, auth expiry, 1366/1920/1100 layouts (synthetic HTTP only)");
} finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
