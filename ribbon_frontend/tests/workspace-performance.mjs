// Explicit synthetic fixture: browser timing and race coverage, no model calls.
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
const baseline = process.argv.includes("--baseline");
const previewOnly = process.argv.includes("--preview-only");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${previewOnly ? 2400 : 600}" height="${previewOnly ? 106 : 150}"><rect width="100%" height="100%" fill="#c5dcc0"/><text x="100" y="80" font-size="30">SYNTHETIC ONLY</text></svg>`;
const image = "/api/ribbon/fixture.svg";
const assets = Array.from({ length: 3000 }, (_, i) => ({ id: i === 0 ? "demo-flower" : i === 1 ? "demo-star" : i === 2 ? "demo-ring" : i === 2000 ? "demo-bg-sage" : `asset-${i}`, name: `合成素材 ${i}`, kind: i < 2000 ? "pattern" : "background", source: "synthetic", is_demo: true, shared: i % 2 === 0, url: image, thumbnail_url: image }));
const modes = ["grid", "stagger", "scatter", "single", "ends", "panels", "bordered", "scene", "fullwidth", "alternating", "ends_open", "split", "stacked", "opposed"];
const templates = modes.map(mode => ({ id: mode, name: mode, mode, version: 1, enabled: true, thumbnail_url: image, rules: {} }));
const profile = { id: "synthetic", version: 1, name: "合成测试规格", width: previewOnly ? 11811 : 2400, height: previewOnly ? 520 : 600, dpi: 150, is_demo: true };
function work(id) {
  const v = { id: `v-${id}`, design_id: id, parent_version_id: null, sequence: 0, prompt: "", render_kind: "parameters", snapshot: { asset_refs: ["demo-flower"], background_ref: "demo-bg-sage", template_id: "stagger", template_mode: "stagger", template_version: 1, layout_engine: "design-rhythm-v2", output_profile: profile, params: {} }, preview_url: `${image}?work=${id}`, download_url: `/api/ribbon/versions/v-${id}/download`, created_at: "2026-11-03", provider: "test" };
  return { id, name: `合成作品 ${id}`, current_version_id: v.id, successful_refinement_count: 0, active_job_id: null, revision: 0, versions: [v], active_job: null };
}
const works = (previewOnly ? ["A", "B", "C", "D", "FAIL"] : ["A", "B", "C", "FAIL"]).map(work);
if (previewOnly) for (const [id, mode] of [["C", "ends"], ["D", "ends_open"]]) {
  const snapshot = works.find(item => item.id === id).versions[0].snapshot;
  snapshot.template_id = mode;
  snapshot.template_mode = mode;
}
let assetReads = 0, holdA = false, pendingA, releaseA, releaseB, deleted = new Set();
const errors = [], requests = [];
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost"), p = url.pathname;
  const json = (value, status = 200) => { if (!res.destroyed) { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }); res.end(JSON.stringify(value)); } };
  try {
    if (p === "/") {
      let html = await readFile(path.join(root, "hsd_tool/static/index.html"), "utf8");
      html = html.replace("__HSD_TOKEN__", JSON.stringify("synthetic-token")).replace("__HSD_ACCESS__", "{}").replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g, "");
      res.writeHead(200, { "Content-Type": "text/html" }); res.end(html); return;
    }
    if (p.startsWith("/static/")) { res.writeHead(200, { "Content-Type": p.endsWith(".css") ? "text/css" : "text/javascript" }); res.end(await readFile(path.join(root, "hsd_tool", p))); return; }
    if (p === image || p.includes("/download")) { res.writeHead(200, { "Content-Type": "image/svg+xml" }); res.end(svg); return; }
    requests.push({ p, method: req.method });
    if (p === "/api/ribbon/auth/me") return json({ id: "synthetic-performance", username: "合成员工", role: "employee" });
    if (p === "/api/ribbon/config") return json({ provider: "test", auth_mode: "demo", ai_ready: true, output_profile: profile, max_refinements: 2, retention_hours: 50 });
    if (p === "/api/ribbon/assets") { assetReads++; return json(assets); }
    if (p === "/api/ribbon/templates") return json(templates);
    if (p === "/api/ribbon/designs") return json(works.filter(w => deleted.has(w.id) === (url.searchParams.get("deleted") === "true")));
    const match = /^\/api\/ribbon\/designs\/([^/]+)(\/restore)?$/.exec(p);
    if (match) {
      const [, id, restore] = match, d = works.find(w => w.id === id);
      if (!d) return json({ detail: "作品不存在" }, 404);
      if (req.method === "DELETE") { assert.equal(req.headers["x-hsd-token"], "synthetic-token"); deleted.add(id); return json({ ok: true, id, deleted_at: "2026-11-03" }); }
      if (restore) { deleted.delete(id); return json({ ...d, deleted_at: null }); }
      if (deleted.has(id) || id === "FAIL") return json({ detail: "合成：作品暂不可用" }, 404);
      if (id === "A" && holdA) { holdA = false; pendingA?.(); await new Promise(resolve => { releaseA = resolve; }); }
      if (id === "B") await new Promise(resolve => { releaseB = resolve; });
      return json(d);
    }
    return json({}, 404);
  } catch (error) { errors.push(String(error)); json({ detail: "fixture failure" }, 500); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ channel: process.env.HSD_BROWSER_CHANNEL || "chrome", headless: true });
const metrics = { fixture: "synthetic HTTP only; 2000 patterns + 1000 backgrounds; no AI", baseline };
try {
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  page.on("pageerror", e => errors.push(String(e)));
  if (!baseline) await page.addInitScript(() => {
    // Deliberately deliver obsolete GETs even after AbortController.abort():
    // sequence and identity guards must independently reject their responses.
    const fetchNormally = window.fetch.bind(window);
    window.fetch = (input, init = {}) => String(input).includes("/api/ribbon/designs/") && (!init.method || init.method === "GET")
      ? fetchNormally(input, { ...init, signal: undefined }) : fetchNormally(input, init);
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/#ribbon`);
  await page.getByRole("heading", { name: "合成作品 A", exact: true }).waitFor();
  await page.getByRole("link", { name: "下载当前图", exact: true }).waitFor();
  if (previewOnly) {
    const staleImage = await page.locator(".ribbon-display img").elementHandle();
    const chooseWork = async id => {
      await page.getByRole("button", { name: "我的作品", exact: false }).click();
      await page.locator(".design-list-item").filter({ has: page.getByText(`合成作品 ${id}`, { exact: true }) }).click();
    };
    const assertFit = async id => {
      await page.getByRole("heading", { name: `合成作品 ${id}`, exact: true }).waitFor();
      await page.locator(".ribbon-display.fit img").waitFor();
      await page.waitForFunction(() => {
        const image = document.querySelector("#ribbon-mount").shadowRoot.querySelector(".ribbon-display.fit img");
        return image?.complete && image.naturalWidth > 0;
      });
      const size = await page.locator(".ribbon-display.fit img").evaluate(image => ({ image: image.getBoundingClientRect().width, viewer: image.parentElement.clientWidth }));
      assert.ok(size.image <= size.viewer + 1, `whole-strip preview fits the viewer: ${JSON.stringify(size)}`);
      assert.equal(await page.getByRole("button", { name: "整条", exact: true }).getAttribute("aria-pressed"), "true");
    };
    const refreshWork = async id => {
      const response = page.waitForResponse(value => new URL(value.url()).pathname === `/api/ribbon/designs/${id}` && value.request().method() === "GET");
      await page.evaluate(() => window.dispatchEvent(new Event("focus")));
      await response;
      await page.waitForTimeout(60);
    };
    await chooseWork("B");
    await page.getByText("正在打开作品…", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "生成首稿", exact: true }).isEnabled(), false, "opening a target locks generation");
    await staleImage.evaluate(image => image.dispatchEvent(new Event("load")));
    assert.equal(await page.locator(".ribbon-display img").count(), 0, "late load on the old detached image cannot restore its preview");
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    const deleteButtons = page.locator(".delete-design-button");
    for (let index = 0; index < await deleteButtons.count(); index++) assert.equal(await deleteButtons.nth(index).isEnabled(), false, "opening a target locks deletion in the work list");
    await page.locator(".design-list-item").filter({ has: page.getByText("合成作品 C", { exact: true }) }).click();
    await assertFit("C");
    await page.getByRole("button", { name: "细节", exact: true }).click();
    await refreshWork("C");
    assert.equal(await page.locator(".ribbon-display.detail").count(), 1, "same-version polling preserves manual detail zoom");
    const c = works.find(item => item.id === "C"), parent = c.versions[0];
    const next = { ...parent, id: "v-C-1", parent_version_id: parent.id, sequence: 1, preview_url: `${image}?work=C&version=1`, download_url: "/api/ribbon/versions/v-C-1/download" };
    c.versions.push(next); c.current_version_id = next.id; c.revision++;
    await refreshWork("C");
    await page.waitForFunction(() => document.querySelector("#ribbon-mount").shadowRoot.querySelector("a[download]")?.getAttribute("href") === "/api/ribbon/versions/v-C-1/download");
    await assertFit("C");
    await chooseWork("D");
    await assertFit("D");
    await staleImage.evaluate(image => image.dispatchEvent(new Event("load")));
    releaseB?.();
    await page.waitForTimeout(150);
    await assertFit("D");
    assert.equal(await page.locator('.ribbon-display img[src*="work=D"]').count(), 1, "a late image event and the obsolete B response cannot replace D");
    await page.getByRole("button", { name: "细节", exact: true }).click();
    await refreshWork("D");
    assert.equal(await page.locator(".ribbon-display.detail").count(), 1, "ends_open polling also preserves manual detail zoom");
    metrics.preview = { endsDefault: "fit", endsOpenDefault: "fit", manualZoomRetained: true, newVersionResetsDefault: true, obsoleteLoadsAndResponsesRejected: true, openingLocksGenerationAndDeletion: true };
  } else {
  const measureLibrary = async (button, title) => {
    const before = assetReads;
    const start = performance.now();
    await page.getByRole("button", { name: button, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: title, exact: true });
    await dialog.locator(".library-card").first().waitFor();
    const result = { elapsedMs: +(performance.now() - start).toFixed(1), cards: await dialog.locator(".library-card").count(), newCatalogRequests: assetReads - before };
    await dialog.getByRole("button", { name: "关闭弹窗", exact: true }).click();
    return result;
  };
  metrics.pattern = await measureLibrary("素材库", "图案素材库");
  metrics.background = await measureLibrary("底图库", "底图素材库");
  metrics.patternRepeat = await measureLibrary("素材库", "图案素材库");
  if (!baseline) {
    assert.ok(metrics.pattern.cards <= 36); assert.ok(metrics.background.cards <= 36); assert.equal(metrics.patternRepeat.newCatalogRequests, 0);
    await page.getByRole("button", { name: "素材库", exact: true }).click();
    const library = page.getByRole("dialog", { name: "图案素材库", exact: true });
    await library.getByRole("button", { name: "下一页", exact: true }).click();
    const extra = library.locator(".library-card").filter({ has: page.getByRole("img", { name: "合成素材 36", exact: true }) });
    await extra.click();
    await library.getByRole("button", { name: "上一页", exact: true }).click();
    assert.equal(await library.locator(".library-card").count(), 36);
    await library.getByLabel("搜索素材", { exact: true }).fill("合成素材 36");
    assert.equal(await library.locator(".library-card").filter({ has: page.getByRole("img", { name: "合成素材 36", exact: true }) }).getAttribute("aria-pressed"), "true", "selection persists across page and search changes");
    await library.getByRole("button", { name: "完成选择", exact: true }).click();
    assert.equal(await page.getByRole("img", { name: "合成素材 36", exact: true }).count(), 1);
  }
  await page.getByRole("button", { name: "我的作品", exact: false }).click();
  await page.locator(".design-list-item").filter({ hasText: "合成作品 B" }).click();
  await page.waitForTimeout(120);
  metrics.duringSwitch = await page.locator("#ribbon-mount").evaluate(host => ({ oldImageVisible: !!host.shadowRoot.querySelector('.ribbon-display img[src*="work=A"]'), downloadCount: host.shadowRoot.querySelectorAll('a[download]').length, loadingText: host.shadowRoot.textContent.includes("正在打开作品") }));
  if (baseline) {
    releaseB?.();
    await page.getByRole("heading", { name: "合成作品 B", exact: true }).waitFor();
  } else {
    assert.equal(metrics.duringSwitch.oldImageVisible, false);
    assert.equal(metrics.duringSwitch.downloadCount, 0);
    assert.equal(metrics.duringSwitch.loadingText, true);
    // A newer target must win over a slow earlier request.
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.locator(".design-list-item").filter({ hasText: "合成作品 C" }).click();
    await page.getByRole("heading", { name: "合成作品 C", exact: true }).waitFor();
    releaseB?.(); await page.waitForTimeout(150);
    assert.equal(await page.getByRole("heading", { name: "合成作品 B", exact: true }).count(), 0);
    // Failure stays blank and can be retried, instead of presenting the old work.
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.locator(".design-list-item").filter({ hasText: "合成作品 FAIL" }).click();
    await page.getByRole("alert").filter({ hasText: "作品暂不可用" }).waitFor();
    assert.equal(await page.getByRole("link", { name: "下载当前图", exact: true }).count(), 0);
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.locator(".design-list-item").filter({ hasText: "合成作品 A" }).click();
    await page.getByRole("heading", { name: "合成作品 A", exact: true }).waitFor();
    const oldPollStarted = new Promise(resolve => { pendingA = resolve; });
    holdA = true;
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await oldPollStarted;
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.locator(".design-list-item").filter({ hasText: "合成作品 C" }).click();
    await page.getByRole("heading", { name: "合成作品 C", exact: true }).waitFor();
    releaseA(); await page.waitForTimeout(150);
    assert.equal(await page.getByRole("heading", { name: "合成作品 A", exact: true }).count(), 0);
    await page.getByRole("button", { name: "我的作品", exact: false }).click();
    await page.getByRole("button", { name: "删除合成作品 C", exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await page.getByRole("button", { name: "已删除作品", exact: false }).click();
    await page.getByRole("button", { name: "恢复合成作品 C", exact: true }).click();
    assert.equal(deleted.has("C"), false);
    await page.getByRole("button", { name: "关闭弹窗", exact: true }).click();
    for (const size of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }, { width: 1100, height: 768 }, { width: 1093, height: 614 }]) {
      await page.setViewportSize(size);
      await page.evaluate(() => window.scrollTo(0, 0));
      const mainAction = await page.locator('.preview-panel > .generate-area button').boundingBox();
      assert.ok(mainAction && mainAction.y >= 0 && mainAction.y + mainAction.height <= size.height, `main action visible at ${size.width}x${size.height}: ${JSON.stringify(mainAction)}`);
      const heightBeforePicker = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.getByRole("button", { name: /更多排法/ }).click();
      const dialog = page.getByRole("dialog", { name: "选择排版模式", exact: true });
      await dialog.waitFor();
      assert.equal(await dialog.locator(".template-card").count(), 14);
      const boxes = await dialog.evaluate(el => ({ top: el.getBoundingClientRect().top, bottom: el.getBoundingClientRect().bottom, h: innerHeight, footer: el.querySelector(".modal-footer").getBoundingClientRect().bottom }));
      assert.ok(boxes.top >= 0 && boxes.bottom <= boxes.h && boxes.footer <= boxes.h, JSON.stringify(boxes));
      await dialog.locator(".template-card").filter({ hasText: "opposed" }).click();
      assert.equal(await dialog.locator(".template-card").filter({ hasText: "opposed" }).getAttribute("aria-pressed"), "true");
      await page.screenshot({ path: path.join(out, `workspace-${size.width}.png`) });
      await dialog.getByRole("button", { name: "完成选择", exact: true }).click();
      assert.equal(await page.locator(".chosen-layout").filter({ hasText: "opposed" }).count(), 1);
      assert.equal(await page.locator(".layout-picker-modal").count(), 0);
      const heightAfterPicker = await page.evaluate(() => document.documentElement.scrollHeight);
      assert.ok(Math.abs(heightAfterPicker - heightBeforePicker) < 70, "extended layout adds a compact summary instead of eight inline cards");
    }
  }
  }
  if (!baseline && !previewOnly) {
    const result = {};
const url="http://127.0.0.1:"+server.address().port+"/#ribbon";
const json=(route, data,status=200)=>route.fulfill({status,contentType:"application/json",json:data});
async function run(name,fn){const p=await browser.newPage({viewport:{width:1366,height:768}});p.setDefaultTimeout(4500);try{result[name]=await fn(p)}catch(e){result[name]={error:String(e).slice(0,600)}}finally{await p.close()}}
const heading=(p,id="A")=>p.getByRole("heading",{name:"合成作品 "+id,exact:true});
await run("background",async p=>{
 let loaded=0, posts=0;await p.route("**/api/ribbon/background-jobs",r=>{posts++;return json(r,{id:"qa-bg",kind:"background",status:"RUNNING"})});
 await p.route("**/api/ribbon/jobs/qa-bg",async r=>{await new Promise(ok=>setTimeout(ok,100));await json(r,{id:"qa-bg",kind:"background",status:"SUCCEEDED",result_asset_id:"asset-2001"})});
 await p.route("**/api/ribbon/assets",async r=>{loaded++;await new Promise(ok=>setTimeout(ok,70));await json(r,assets)});
 await p.goto(url);await heading(p).waitFor();await p.waitForTimeout(200);const start=loaded;
 await p.getByRole("button",{name:"生成测试底图",exact:true}).click();
 await p.waitForFunction(()=>JSON.parse(localStorage.getItem("ribbon:synthetic-performance:selection")||"null")?.value?.background_id==="asset-2001");
 return {requestsAfterSuccess:loaded-start,posts};
});
await run("initRetry",async p=>{
 let count=0;await p.route("**/api/ribbon/assets",r=>++count===1?json(r,{detail:"合成素材读取失败"},503):json(r,assets));
 await p.goto(url);await p.waitForTimeout(400);
 const btn=p.getByRole("button",{name:/重试|重新加载|重新读取|重新载入/}).first();
 const visible=await btn.isVisible();if(visible)await btn.click();
 return {retry:visible,reads:count,loaded:await heading(p).isVisible()||await heading(p).waitFor({timeout:3000}).then(()=>true,()=>false)};
});
await run("idleDisconnect",async p=>{
 let fail=false, seen=false, after=0;
 await p.route("**/api/ribbon/designs/A",r=>{if(fail){fail=false;seen=true;return json(r,{detail:"合成暂时断开"},503)}if(seen)after++;return json(r,works[0])});
 await p.goto(url);await heading(p).waitFor();await p.waitForTimeout(200);fail=true;
 const err=p.waitForResponse(r=>r.url().endsWith("/api/ribbon/designs/A")&&r.status()===503);await p.evaluate(()=>window.dispatchEvent(new Event("focus")));await err;
 await p.waitForTimeout(4200);const btn=p.getByRole("button",{name:/重连|重新连接|重试/}).first(),manual=await btn.isVisible();
 if(after===0&&manual){await btn.click();await p.waitForTimeout(200)}
 return {recovered:after>0,recoveryReads:after,manual};
});
await run("failedPreview",async p=>{
 let failed=0;await p.route("**/api/ribbon/fixture.svg*work=A*",r=>++failed===1?r.fulfill({status:503,body:"temporary preview failure"}):r.continue());
 await p.goto(url);await heading(p).waitFor();await p.waitForTimeout(200);
 const box=p.locator(".preview-panel"),btn=box.getByRole("button",{name:/重试|重新加载|重新读取/}).first(),visible=await btn.isVisible();
 if(visible)await btn.click();await p.waitForTimeout(150);
 return {retry:visible,reads:failed,visibleOk:await box.locator(".ribbon-display img").first().evaluate(im=>im.complete&&im.naturalWidth>0).catch(()=>false)};
});
await run("worksList",async p=>{
 let done=false,list=0;const j={id:"qa-jA",kind:"refine",status:"RUNNING"},A=()=>({...works[0],active_job_id:done?null:j.id,active_job:done?null:j});
 await p.route("**/api/ribbon/designs*",r=>{list++;return json(r,[A(),...works.slice(1)])});
 await p.route("**/api/ribbon/designs/A",r=>json(r,A()));
 await p.route("**/api/ribbon/jobs/qa-jA",r=>json(r,{...j,status:done?"SUCCEEDED":"RUNNING"}));
 await p.goto(url);await heading(p).waitFor();await p.getByRole("button",{name:/我的作品/}).click();await p.locator(".design-list-item").filter({has:p.getByText("合成作品 C",{exact:true})}).click();
 await heading(p,"C").waitFor();done=true;const before=list;
 await p.getByRole("button",{name:/我的作品/}).click();await p.waitForTimeout(150);
 return {newReads:list-before,deleteEnabled:await p.getByRole("button",{name:"删除合成作品 A",exact:true}).isEnabled()};
});
await run("lostSubmit",async p=>{
 const keys=[]; await p.route("**/api/ribbon/designs/A/refinements",r=>{keys.push(r.request().postDataJSON().idempotency_key);return keys.length===1?r.abort("connectionreset"):json(r,{detail:"受控终态：父版本已变化"},409)});
 await p.goto(url);await heading(p).waitFor();await p.locator("#refinement").fill("把图案缩小一点");await p.locator(".refine-button").click();
 await p.getByRole("button",{name:/恢复提交/}).click(); await p.waitForTimeout(100);
 return {posts:keys.length,same:keys.length===2&&keys[0]===keys[1],retainsVersion:await p.getByRole("link",{name:"下载当前图",exact:true}).isVisible()};
});

    assert.deepEqual(result.background, {requestsAfterSuccess:1,posts:1});
    assert.equal(result.initRetry.retry,true);assert.equal(result.initRetry.loaded,true);
    assert.equal(result.idleDisconnect.recovered,true);
    assert.equal(result.failedPreview.retry,true);assert.equal(result.failedPreview.visibleOk,true);
    assert.deepEqual(result.worksList,{newReads:1,deleteEnabled:true});
    assert.deepEqual(result.lostSubmit,{posts:2,same:true,retainsVersion:true});
    metrics.recovery=result;
  }
  assert.deepEqual(errors, []);
  await writeFile(path.join(out, previewOnly ? "workspace-preview.json" : baseline ? "workspace-before.json" : "workspace-after.json"), JSON.stringify(metrics, null, 2));
  console.log(JSON.stringify(metrics));
} finally { releaseA?.(); releaseB?.(); await browser.close(); await new Promise(resolve => server.close(resolve)); }
