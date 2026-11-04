// Explicit synthetic browser fixture. No business images or external model calls.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.HSD_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const out = path.join(root, "ribbon_frontend/test-results");
await mkdir(out, { recursive: true });
const sourceProfile = { id: "synthetic-source", version: 1, name: "合成来源配置", width: 11811, height: 520, dpi: 300, is_demo: true };
const unitProfile = { ...sourceProfile, width: 1200 };
const editing = { allowed_operations: ["parameters", "edit_asset", "edit_background"], allowed_parameters: ["scale", "spacing"], composite_edit: false, composite_edit_reason: "合成测试：修改独立图案或底图后排版。", planner_sees_images: false };
const fixture = "/api/ribbon/synthetic-loop.svg";
const svg = (width = 1200, height = 520) => `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#e5eee0"/><circle cx="${width * .2}" cy="${height * .5}" r="${height * .25}" fill="#a9c68e"/><text x="${width * .4}" y="${height * .55}" font-size="${height * .1}">SYNTHETIC ONLY</text></svg>`;
const assets = ["flower", "star"].map(name => ({ id: `demo-${name}`, name: `合成图案 ${name}`, kind: "pattern", source: "synthetic", is_demo: true, shared: true, url: fixture, thumbnail_url: fixture }));
assets.push({ id: "demo-bg-sage", name: "合成底图", kind: "background", source: "synthetic", is_demo: true, shared: true, url: fixture, thumbnail_url: fixture });
const templates = ["stagger", "ends"].map(mode => ({ id: mode, name: mode, mode, version: 1, enabled: true, rules: {}, thumbnail_url: fixture }));
const makeVersion = (id, sequence, parent, engine = "seamless-unit-v1", mode = "stagger") => ({
  id, design_id: "LOOP", sequence, parent_version_id: parent, prompt: sequence ? "合成精修" : "", render_kind: "parameters", provider: "test", created_at: "2026-11-04", editing,
  preview_url: `${fixture}?version=${id}`, view_url: `/api/ribbon/versions/${id}/view`, download_url: `/api/ribbon/versions/${id}/download`,
  snapshot: { asset_refs: ["demo-flower", "demo-star"], background_ref: "demo-bg-sage", template_id: mode, template_mode: mode, template_version: 1,
    layout_engine: engine, design_density: "balanced", background_tone: "soft", params: {}, output_profile: engine === "seamless-unit-v1" ? unitProfile : sourceProfile,
    ...(engine === "seamless-unit-v1" ? { output_profile_source: sourceProfile, loop: { engine, width: 1200, height: 520, kind: "panel", status: "needs_review", issues: [{ code: "SYNTHETIC_REVIEW", severity: "warning", message: "合成提示：请复核接缝附近的留白。" }], mode_notice: "合成说明：本排法按完整区段循环。" } } : {}) },
});
const makeDesign = (id, version) => ({ id, name: `合成作品 ${id}`, current_version_id: version?.id || null, successful_refinement_count: 0, active_job_id: null, revision: 0, versions: version ? [version] : [], active_job: null });
const loopWork = makeDesign("LOOP", makeVersion("loop-0", 0, null));
const legacyV1 = makeDesign("V1", makeVersion("old-v1", 0, null, "design-rhythm-v1", "ends"));
const legacyV2 = makeDesign("V2", makeVersion("old-v2", 0, null, "design-rhythm-v2", "stagger"));
const works = [loopWork, legacyV1, legacyV2, makeDesign("SLOW", makeVersion("slow-0", 0, null)), makeDesign("EMPTY", null)];
const jobs = new Map(), writes = [], requests = [], errors = [];
let releaseSlow;
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost"), p = url.pathname;
  const json = (value, status = 200) => { if (!res.destroyed) { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }); res.end(JSON.stringify(value)); } };
  try {
    requests.push({ p, search: url.search, method: req.method });
    if (p === "/") {
      let html = await readFile(path.join(root, "hsd_tool/static/index.html"), "utf8");
      html = html.replace("__HSD_TOKEN__", JSON.stringify("synthetic-token")).replace("__HSD_ACCESS__", "{}").replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g, "");
      res.writeHead(200, { "Content-Type": "text/html" }); res.end(html); return;
    }
    if (p.startsWith("/static/")) { res.writeHead(200, { "Content-Type": p.endsWith(".css") ? "text/css" : "text/javascript" }); res.end(await readFile(path.join(root, "hsd_tool", p))); return; }
    if (p === fixture) { res.writeHead(200, { "Content-Type": "image/svg+xml", "Cache-Control": "private, no-cache, must-revalidate" }); res.end(svg(600, 260)); return; }
    if (p.endsWith("/view")) { res.writeHead(200, { "Content-Type": "image/svg+xml" }); res.end(svg(11811, 520)); return; }
    if (p.endsWith("/download")) { res.writeHead(200, { "Content-Type": "image/svg+xml", "Content-Disposition": 'attachment; filename="synthetic-unit.svg"' }); res.end(svg()); return; }
    if (p === "/api/ribbon/auth/me") return json({ id: "synthetic-loop-user", username: "合成员工", role: "employee" });
    if (p === "/api/ribbon/config") return json({ provider: "test", auth_mode: "demo", ai_ready: true, output_profile: sourceProfile, max_refinements: 2, editing });
    if (p === "/api/ribbon/assets") return json(assets);
    if (p === "/api/ribbon/templates") return json(templates);
    if (p === "/api/ribbon/designs") return json(works);
    if (p.startsWith("/api/ribbon/jobs/")) return json(jobs.get(p.split("/").at(-1)));
    const match = /^\/api\/ribbon\/designs\/([^/]+)(\/(?:refinements|rollback))?$/.exec(p);
    if (match) {
      const [, id, action] = match, work = works.find(item => item.id === id);
      if (!work) return json({ detail: "作品不存在" }, 404);
      if (req.method === "POST") {
        assert.equal(req.headers["x-hsd-token"], "synthetic-token");
        let body = ""; for await (const chunk of req) body += chunk;
        const data = JSON.parse(body); writes.push({ p, data });
        if (action === "/rollback") {
          assert.equal(data.expected_version_id, work.current_version_id);
          work.current_version_id = work.versions.find(item => item.id === work.current_version_id).parent_version_id;
          work.revision++; return json(work);
        }
        assert.equal(data.base_version_id, work.current_version_id);
        const sequence = work.versions.length, next = makeVersion(`loop-${sequence}`, sequence, work.current_version_id);
        next.snapshot.loop = { ...next.snapshot.loop, status: "checked", kind: "sequence", issues: [], mode_notice: undefined };
        work.versions.push(next); work.current_version_id = next.id; work.successful_refinement_count++; work.revision++;
        const job = { id: `synthetic-job-${sequence}`, design_id: id, kind: "refinement", status: "SUCCEEDED", phase: "completed", attempt: 1, provider: "test", error: null, result_version_id: next.id, needs_clarification: false };
        jobs.set(job.id, job); return json(job);
      }
      if (id === "SLOW") await new Promise(resolve => { releaseSlow = resolve; });
      return json(work);
    }
    return json({}, 404);
  } catch (error) { errors.push(String(error)); json({ detail: "synthetic fixture failure" }, 500); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ channel: process.env.HSD_BROWSER_CHANNEL || "chrome", headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  page.on("pageerror", error => errors.push(String(error)));
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = (input, init = {}) => String(input).includes("/api/ribbon/designs/") && (!init.method || init.method === "GET") ? original(input, { ...init, signal: undefined }) : original(input, init);
  });
  const unitDownload = () => page.getByRole("link", { name: "下载循环单元", exact: true });
  const choose = async id => {
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.locator(".design-list-item").filter({ has: page.getByText(`合成作品 ${id}`, { exact: true }) }).click();
  };
  const refresh = async id => {
    const response = page.waitForResponse(value => new URL(value.url()).pathname === `/api/ribbon/designs/${id}`);
    await page.evaluate(() => window.dispatchEvent(new Event("focus"))); await response;
    await page.waitForTimeout(60);
  };
  const assertUnit = async id => {
    await page.locator(`a[download][href="/api/ribbon/versions/${id}/download"]`).waitFor();
    assert.equal(await unitDownload().getAttribute("href"), `/api/ribbon/versions/${id}/download`);
    assert.equal(await page.locator(".loop-unit-view").isVisible(), true);
    assert.equal(await page.locator(".loop-continuity").isVisible(), false);
    assert.match(await page.locator(".loop-view-heading").innerText(), /1200×520px/);
  };
  await page.goto(`http://127.0.0.1:${server.address().port}/#ribbon`);
  await assertUnit("loop-0");
  await page.locator(".loop-unit-view img").evaluate(image => image.decode());
  await page.screenshot({ path: path.join(out, "loop-unit-1366.png"), fullPage: true });
  assert.equal(await page.locator(".loop-technical-details").getAttribute("open"), null);
  assert.equal(await page.getByText("合成提示：请复核接缝附近的留白。", { exact: true }).isVisible(), true);
  assert.equal(await page.getByText("合成说明：本排法按完整区段循环。", { exact: true }).isVisible(), true);
  assert.equal(await page.getByLabel("画面密度", { exact: true }).inputValue(), "balanced");
  const initialPreviewReads = requests.filter(r => r.p === fixture && r.search === "?version=loop-0").length;
  assert.equal(initialPreviewReads, 1, "all repeated elements share one immutable preview resource");
  await page.getByRole("button", { name: "查看连续效果", exact: true }).click();
  assert.equal(await page.locator(".loop-continuity").isVisible(), true);
  assert.equal(await page.locator(".loop-repeat img").count(), 3);
  assert.deepEqual(await page.locator(".loop-repeat img").evaluateAll(images => [...new Set(images.map(image => image.getAttribute("src")))]), [`${fixture}?version=loop-0`]);
  await page.getByRole("checkbox", { name: "显示接缝位置", exact: true }).check();
  assert.equal(await page.locator(".loop-continuity-track.show-seams").count(), 1);
  await refresh("LOOP");
  assert.equal(await page.getByRole("checkbox", { name: "显示接缝位置", exact: true }).isChecked(), true, "same-version polling preserves the view");
  for (const width of [1920, 1366, 640, 375]) {
    await page.setViewportSize({ width, height: width === 1920 ? 1080 : width === 1366 ? 768 : 900 });
    const sizes = await page.locator(".loop-continuity").evaluate(el => ({ scroll: el.scrollWidth, client: el.clientWidth }));
    assert.ok(sizes.scroll <= sizes.client + 1, `three previews fit at ${width}px`);
    await page.screenshot({ path: path.join(out, `loop-preview-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1366, height: 768 });
  assert.equal(requests.filter(r => r.p === fixture && r.search === "?version=loop-0").length, initialPreviewReads, "view, seams, resize and poll fetch no extra image bytes");
  assert.equal(requests.some(r => r.p.endsWith("/view") || r.p.endsWith("/download")), false, "loop preview never fetches a production master");
  assert.equal(writes.length, 0, "preview controls never create a version or spend quota");
  const downloadEvent = page.waitForEvent("download"); await unitDownload().click();
  const download = await downloadEvent;
  assert.match(await readFile(await download.path(), "utf8"), /width="1200" height="520"/, "download is the full-size single unit, not a three-unit strip");
  await page.locator(".loop-technical-details summary").click();
  assert.match(await page.locator(".loop-technical-details").innerText(), /11811×520px/);
  await page.locator(".refinement-body textarea").fill("图案缩小一些");
  await page.getByRole("button", { name: "开始精修", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/loop-1/download");
  await assertUnit("loop-1");
  assert.equal(await page.getByText("工程循环检查通过", { exact: true }).isVisible(), true);
  assert.equal(await page.getByText("画面与印刷效果仍需人工确认。", { exact: true }).isVisible(), true);
  assert.equal(await page.locator(".loop-check ul").count(), 0);
  await page.locator(".version-card").first().click();
  assert.equal(await page.getByRole("link", { name: "下载所选版本", exact: true }).getAttribute("href"), "/api/ribbon/versions/loop-0/download");
  assert.equal(await page.getByText("合成提示：请复核接缝附近的留白。", { exact: true }).isVisible(), true);
  assert.equal(await page.getByRole("button", { name: "开始精修", exact: true }).isEnabled(), false);
  await page.getByRole("button", { name: "返回当前版本", exact: true }).click();
  await page.getByRole("button", { name: "回退上一版", exact: true }).click();
  await assertUnit("loop-0");
  assert.equal(loopWork.successful_refinement_count, 1, "rollback does not refund quota");
  await page.locator(".refinement-body textarea").fill("图案缩小一些");
  await page.getByRole("button", { name: "开始精修", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector('a[download]')?.getAttribute("href") === "/api/ribbon/versions/loop-2/download");
  await assertUnit("loop-2");
  assert.equal(loopWork.versions.at(-1).parent_version_id, "loop-0", "new refinement follows the rollback parent");
  await page.getByRole("button", { name: "精修次数已用完", exact: true }).waitFor();
  const staleImage = await page.locator(".loop-unit-view img").elementHandle();
  await choose("SLOW");
  await page.getByText("正在打开作品…", { exact: true }).waitFor();
  assert.equal(await page.locator(".loop-preview").count(), 0);
  assert.equal(await page.locator("a[download]").count(), 0);
  await choose("V1");
  await page.locator(".ribbon-display.fit img").waitFor();
  await staleImage.evaluate(image => image.dispatchEvent(new Event("load")));
  releaseSlow?.(); await page.waitForTimeout(100);
  assert.equal(await page.locator(".loop-preview").count(), 0);
  assert.match(await page.locator(".ribbon-metrics").innerText(), /11811×520px/);
  assert.equal(await page.getByRole("link", { name: "下载当前图", exact: true }).getAttribute("href"), "/api/ribbon/versions/old-v1/download");
  await choose("V2");
  await page.locator(".ribbon-display.detail img").waitFor();
  assert.equal(await page.locator(".ribbon-display img").getAttribute("src"), "/api/ribbon/versions/old-v2/view", "legacy detail still uses its own full-resolution file");
  await choose("EMPTY");
  await page.getByRole("button", { name: "生成首稿", exact: true }).waitFor();
  assert.equal(await page.locator(".loop-preview, a[download]").count(), 0);
  assert.deepEqual(errors, []);
  const result = { fixture: "synthetic HTTP only; no business images, no model calls", initialPreviewReads, repeatControlsExtraReads: 0, loopDefault: "unit", repeatedCopies: 3, seams: true, warningsVisible: true, sourceDetailsCollapsed: true, pollingPreservesView: true, versionDownload: true, refinementRollbackBranch: true, legacyV1V2: true, switchingRejectsStaleImageAndResponse: true, responsiveWidths: [1920, 1366, 640, 375] };
  await writeFile(path.join(out, "loop-preview.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally { releaseSlow?.(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
