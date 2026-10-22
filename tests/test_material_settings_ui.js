// Synthetic DOM and fetch only. These tests do not contact a server/provider,
// render a browser, measure performance, or demonstrate extraction quality.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(
  path.join(__dirname, "../hsd_tool/static/material-settings.js"), "utf8"
);
const MODEL = "doubao-seedream-synthetic-test";
const KEY = "synthetic-ark-credential-for-ui-only";
const flush = () => new Promise(setImmediate);

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function responseBody(revision = 4, configured = false, enabled = false) {
  return {
    settings: { provider: "volcengine_ark", model_id: configured ? MODEL : "", revision, configured, enabled, warning: "", key_persistence: "linux_aesgcm" },
    deepseek: { enabled: true, configured: true },
  };
}

function harness() {
  const nodes = new Map(), windowListeners = new Map(), calls = [], copied = [];
  const clipboard = {writeText: async value => {copied.push(value);}};
  function node(id) {
    if (!nodes.has(id)) {
      const classes = new Set(
        ["material-message", "material-login"].includes(id) ? ["hidden"] : []
      );
      const listeners = new Map();
      nodes.set(id, {
        id, value: "", textContent: "", checked: false, disabled: false, open: false,
        classList: {
          add(...values) { for (const value of values) classes.add(value); },
          remove(...values) { for (const value of values) classes.delete(value); },
          contains(value) { return classes.has(value); },
          toggle(value, force) {
            const next = force === undefined ? !classes.has(value) : force;
            if (next) classes.add(value); else classes.delete(value);
            return !!next;
          },
        },
        addEventListener(name, fn) {
          if (!listeners.has(name)) listeners.set(name, []);
          listeners.get(name).push(fn);
        },
        emit(name) {
          const event = { target: this, currentTarget: this, preventDefault() {} };
          for (const fn of listeners.get(name) || []) fn(event);
        },
      });
    }
    return nodes.get(id);
  }
  const window = {
    HSD_TOKEN: "synthetic-material-csrf",
    addEventListener(name, fn) {
      if (!windowListeners.has(name)) windowListeners.set(name, []);
      windowListeners.get(name).push(fn);
    },
  };
  const sandbox = {
    window, document: { getElementById: node }, navigator: {clipboard},
    fetch(url, options) {
      const pending = deferred();
      const call = { url, options, pending };
      calls.push(call);
      return pending.promise;
    },
  };
  // Execute the actual source unchanged, including its normal boot GET.
  vm.runInNewContext(source, sandbox, { filename: "material-settings.js" });
  return {
    node, calls, copied, clipboard,
    emit(name, event = {}) {
      for (const fn of windowListeners.get(name) || []) fn(event);
    },
    async reply(index, body = responseBody(), status = 200) {
      calls[index].pending.resolve({
        ok: status >= 200 && status < 300, status, json: async () => body,
      });
      await flush();
    },
    async ready(body = responseBody()) { await this.reply(0, body); return this; },
    submit(key = KEY) {
      node("material-key").value = key;
      node("material-model").value = MODEL;
      node("material-form").emit("submit");
    },
    payload(index) { return JSON.parse(calls[index].options.body); },
    displayedText() { return [...nodes.values()].map((item) => item.textContent).join("\n"); },
  };
}

const tests = [];
function test(name, run) { tests.push({ name, run }); }

test("boot reads only safe settings and renders configuration after the response", async () => {
  const h = harness();
  assert.equal(h.calls.length, 1);
  const request = h.calls[0];
  assert.equal(request.url, "/api/admin/material-settings");
  assert.equal(request.options.method, "GET");
  assert.equal(request.options.credentials, "same-origin");
  assert.equal(request.options.cache, "no-store");
  assert.equal(request.options.headers["X-HSD-Token"], "synthetic-material-csrf");
  assert.equal(request.options.body, undefined);
  assert.equal(h.node("material-key").disabled, true);
  await h.ready();
  assert.equal(h.node("material-key").disabled, false);
  assert.equal(h.node("material-remove").disabled, true);
  assert.match(h.node("material-ark").textContent, /尚未配置/);
  assert.match(h.node("material-deepseek").textContent, /已启用/);
  assert.equal(h.node("material-enabled").checked, false);
  h.node("material-refresh").emit("click");
  await h.reply(1, responseBody(8, true, true));
  assert.equal(h.node("material-enabled").checked, true);
  assert.equal(h.node("material-remove").disabled, false);
  assert.match(h.node("material-ark").textContent, /尚待验证/);
  assert.ok(!h.calls.some(({ url }) => /ledger|debug|usage/.test(url)));
});

test("save clears the Key immediately, awaits acknowledgement and prevents duplicate mutations", async () => {
  const h = await harness().ready();
  h.submit();
  assert.equal(h.node("material-key").value, "", "clear secret before the first await");
  assert.deepEqual(h.payload(1), { action: "set_config", api_key: KEY, model_id: MODEL, provider: "volcengine_ark", expected_revision: 4 });
  assert.equal(h.calls[1].options.method, "POST");
  assert.equal(h.calls[1].options.headers["Content-Type"], "application/json");
  assert.equal(h.node("material-save").disabled, true);
  assert.ok(!/已保存/.test(h.node("material-message").textContent));
  assert.match(h.node("material-ark").textContent, /尚未配置/);
  h.submit("synthetic-second-key-ui-only");
  h.node("material-enabled").checked = true;
  h.node("material-enable-form").emit("submit");
  h.node("material-remove").emit("click");
  h.node("material-refresh").emit("click");
  assert.equal(h.calls.length, 2, "pending work cannot double-submit or refresh");
  await h.reply(1, responseBody(5, true, false));
  assert.match(h.node("material-message").textContent, /设置已保存/);
  assert.equal(h.node("material-save").disabled, false);
  assert.equal(h.node("material-key").value, "");
  assert.ok(!h.displayedText().includes(KEY));
  h.node("material-enable-form").emit("submit");
  assert.deepEqual(h.payload(2), { action: "set_enabled", enabled: false, provider: "volcengine_ark", expected_revision: 5 });
  await h.reply(2, responseBody(6, true, false));
});

test("409 never advances revision or claims success and requires an explicit refresh", async () => {
  const h = await harness().ready(responseBody(4, true, false));
  h.submit();
  await h.reply(1, { error: "synthetic version conflict" }, 409);
  assert.match(h.node("material-message").textContent, /其他页面.*刷新/);
  assert.ok(h.node("material-message").classList.contains("warning"));
  assert.ok(!/已保存/.test(h.node("material-message").textContent));
  assert.equal(h.node("material-key").value, "");
  assert.equal(h.node("material-save").disabled, true);
  const beforeRetry = h.calls.length;
  h.submit();
  h.node("material-remove").emit("click");
  h.node("material-enable-form").emit("submit");
  assert.equal(h.calls.length, beforeRetry, "conflict cannot write again until refreshed");
  h.node("material-refresh").emit("click");
  const refreshing = h.calls.length - 1;
  assert.equal(h.calls[refreshing].options.method, "GET");
  await h.reply(refreshing, responseBody(9, true, false));
  h.submit();
  assert.equal(h.payload(h.calls.length - 1).expected_revision, 9);
  await h.reply(h.calls.length - 1, responseBody(10, true, false));
});

for (const status of [401, 403]) {
  for (const method of ["GET", "POST"]) {
    test(`${status} on ${method} clears inputs and locks mutation controls`, async () => {
      const h = harness();
      let index = 0;
      if (method === "POST") {
        await h.ready(responseBody(4, true, false));
        h.submit();
        index = 1;
      }
      h.node("material-key").value = KEY;
      await h.reply(index, { error: "synthetic authentication lost" }, status);
      assert.equal(h.node("material-key").value, "");
      assert.ok(!h.node("material-login").classList.contains("hidden"));
      assert.match(h.node("material-message").textContent, /重新登录/);
      for (const id of ["material-key", "material-save", "material-enabled",
                        "material-enable-save", "material-remove"])
        assert.equal(h.node(id).disabled, true, `${id} must lock after auth loss`);
      const before = h.calls.length;
      h.submit();
      h.node("material-enable-form").emit("submit");
      h.node("material-remove").emit("click");
      assert.equal(h.calls.length, before);
    });
  }
}

test("pagehide clears the Key and a late GET cannot restore settings", async () => {
  const h = harness();
  h.node("material-key").value = KEY;
  h.emit("pagehide");
  assert.equal(h.node("material-key").value, "");
  const before = h.node("material-ark").textContent;
  await h.reply(0, responseBody(99, true, true));
  assert.equal(h.node("material-ark").textContent, before);
  assert.equal(h.node("material-enabled").checked, false);
  assert.equal(h.node("material-save").disabled, true);
});

test("pagehide suppresses a late successful POST", async () => {
  const h = await harness().ready();
  h.submit();
  h.emit("pagehide");
  await h.reply(1, responseBody(5, true, true));
  assert.match(h.node("material-ark").textContent, /尚未配置/);
  assert.ok(!/已保存/.test(h.node("material-message").textContent));
  assert.equal(h.node("material-enabled").checked, false);
  assert.equal(h.node("material-save").disabled, true);
});

test("BFCache restoration revalidates completed pages before unlocking", async () => {
  const h = await harness().ready();
  h.emit("pagehide");
  h.emit("pageshow", { persisted: true });
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].options.method, "GET");
  assert.equal(h.node("material-save").disabled, true);
  await h.reply(1, responseBody(10, true, false));
  assert.equal(h.node("material-save").disabled, false);
  h.submit();
  assert.equal(h.payload(2).expected_revision, 10);
  await h.reply(2, responseBody(11, true, false));
});

for (const oldReturnsFirst of [true, false]) {
  test(`BFCache pending GET refresh survives ${oldReturnsFirst ? "old" : "new"} response first`, async () => {
    const h = harness();
    h.emit("pagehide");
    h.emit("pageshow", { persisted: true });
    assert.equal(h.calls.length, 2, "restoring during an old GET must start a fresh authenticated read");
    assert.equal(h.node("material-save").disabled, true);
    if (oldReturnsFirst) {
      await h.reply(0, responseBody(2, true, true));
      assert.equal(h.node("material-save").disabled, true, "old completion must not finish the new load");
      assert.ok(!/已加密保存/.test(h.node("material-ark").textContent));
      await h.reply(1, responseBody(20, true, false));
    } else {
      await h.reply(1, responseBody(20, true, false));
      await h.reply(0, responseBody(2, true, true));
    }
    assert.equal(h.node("material-save").disabled, false);
    assert.equal(h.node("material-enabled").checked, false, "late old state must not replace the fresh read");
    h.submit();
    assert.equal(h.payload(2).expected_revision, 20);
    await h.reply(2, responseBody(21, true, false));
  });
}

for (const oldReturnsFirst of [true, false]) {
  test(`an old ${oldReturnsFirst ? "early" : "late"} 401 cannot relock the restored page`, async () => {
    const h = harness();
    h.emit("pagehide");
    h.emit("pageshow", { persisted: true });
    if (oldReturnsFirst) {
      await h.reply(0, {}, 401);
      assert.equal(h.node("material-save").disabled, true);
      await h.reply(1, responseBody(20, true, false));
    } else {
      await h.reply(1, responseBody(20, true, false));
      await h.reply(0, {}, 401);
    }
    assert.ok(h.node("material-login").classList.contains("hidden"));
    assert.equal(h.node("material-save").disabled, false);
    assert.ok(!/登录已失效/.test(h.node("material-message").textContent));
  });
}

test("a validation rejection restores the committed switch and allows a corrected retry", async () => {
  const h = await harness().ready(responseBody(4, true, false));
  h.node("material-enabled").checked = true;
  h.node("material-enable-form").emit("submit");
  await h.reply(1, { error: "合成设置不符合要求。" }, 400);
  assert.match(h.node("material-message").textContent, /不符合要求/);
  assert.ok(!/已保存/.test(h.node("material-message").textContent));
  assert.equal(h.node("material-enabled").checked, false);
  assert.equal(h.node("material-enable-save").disabled, false);
  h.node("material-enable-form").emit("submit");
  assert.equal(h.payload(2).expected_revision, 4);
  await h.reply(2, responseBody(5, true, false));
});

test("an uncertain failed save restores the switch and requires a refresh before retry", async () => {
  const h = await harness().ready(responseBody(4, true, false));
  h.node("material-enabled").checked = true;
  h.node("material-enable-form").emit("submit");
  await h.reply(1, { error: "合成保存失败，请刷新核对。" }, 500);
  assert.match(h.node("material-message").textContent, /保存失败/);
  assert.ok(!/已保存/.test(h.node("material-message").textContent));
  assert.equal(h.node("material-enabled").checked, false);
  assert.equal(h.node("material-enable-save").disabled, true);
  h.node("material-enable-form").emit("submit");
  assert.equal(h.calls.length, 2);
  h.node("material-refresh").emit("click");
  await h.reply(2, responseBody(8, true, true));
  assert.equal(h.node("material-enabled").checked, true);
  h.node("material-enable-form").emit("submit");
  assert.equal(h.payload(3).expected_revision, 8);
  await h.reply(3, responseBody(9, true, true));
});

test("an existing Key can be kept while editing the model", async () => {
  const h = await harness().ready(responseBody(4, true, false));
  h.node("material-model").value = "ep-synthetic-image";
  h.node("material-form").emit("submit");
  assert.equal(h.payload(1).api_key, "");
  assert.equal(h.payload(1).model_id, "ep-synthetic-image");
  assert.equal(h.payload(1).provider, "volcengine_ark");
  assert.equal(h.node("material-model").disabled, true);
  await h.reply(1, {...responseBody(5, true, false), settings: {...responseBody(5, true, false).settings, model_id:"ep-synthetic-image"}});
  assert.equal(h.node("material-model").value, "ep-synthetic-image");
});

test("a model is required before a configuration submission", async () => {
  const h = await harness().ready();
  h.node("material-key").value = KEY;
  h.node("material-form").emit("submit");
  assert.equal(h.calls.length, 1);
  assert.equal(h.node("material-key").value, "");
  assert.match(h.node("material-message").textContent, /模型 ID/);
});

test("an old provider snapshot cannot unlock Ark settings", async () => {
  const h = harness();
  const body = responseBody(); delete body.settings.provider;
  await h.reply(0, body);
  assert.equal(h.node("material-save").disabled, true);
  assert.equal(h.node("material-model").disabled, true);
});


function openKey(h) { h.node("material-key-details").open = true; h.node("material-key-details").emit("toggle"); }
function keyBody(revision=4) {return {provider:"volcengine_ark",revision,api_key:KEY};}

test("opening the key panel never fetches or reveals a secret", async () => {
  const h = await harness().ready(responseBody(4,true,false)); openKey(h);
  assert.equal(h.calls.length,1);
  assert.equal(h.node("material-key-value").textContent,"••••••••");
});

test("show is explicit and fresh, hide erases the visible key without another request", async () => {
  const h = await harness().ready(responseBody(4,true,false)); openKey(h);
  h.node("material-key-reveal").emit("click");
  assert.equal(h.calls[1].url,"/api/admin/material-key?revision=4");
  assert.equal(h.calls[1].options.cache,"no-store");
  assert.equal(h.node("material-key-reveal").disabled,true);
  h.node("material-key-reveal").emit("click"); assert.equal(h.calls.length,2);
  assert.ok(!h.displayedText().includes(KEY));
  await h.reply(1,keyBody()); assert.equal(h.node("material-key-value").textContent,KEY);
  h.node("material-key-reveal").emit("click");
  assert.equal(h.node("material-key-value").textContent,"••••••••"); assert.equal(h.calls.length,2);
  h.node("material-key-reveal").emit("click"); await h.reply(2,keyBody());
  assert.equal(h.calls.length,3);
});

test("copy fetches a fresh key but leaves its text masked", async () => {
  const h = await harness().ready(responseBody(4,true,false)); openKey(h);
  h.node("material-key-copy").emit("click"); await h.reply(1,keyBody());
  assert.deepEqual(h.copied,[KEY]); assert.match(h.node("material-message").textContent,/已复制/);
  assert.ok(!h.displayedText().includes(KEY));
});

test("copy success waits for clipboard acknowledgement", async () => {
  const h = await harness().ready(responseBody(4,true,false)); openKey(h);
  const d=deferred(); h.clipboard.writeText=()=>d.promise;
  h.node("material-key-copy").emit("click"); await h.reply(1,keyBody());
  assert.ok(!/已复制/.test(h.node("material-message").textContent));
  assert.equal(h.node("material-key-copy").disabled,true);
  d.resolve(); await flush(); assert.match(h.node("material-message").textContent,/已复制/);
});

test("clipboard failure never echoes its exception or claims success", async () => {
  const h = await harness().ready(responseBody(4,true,false)); openKey(h);
  h.clipboard.writeText=async()=>{throw new Error(KEY);};
  h.node("material-key-copy").emit("click"); await h.reply(1,keyBody());
  assert.match(h.node("material-message").textContent,/复制未完成/);
  assert.ok(!h.displayedText().includes(KEY)); assert.ok(!/已复制/.test(h.node("material-message").textContent));
});

for (const action of ["material-key-copy","material-key-reveal"]) {
  test(`closing the panel suppresses a late ${action} response`, async()=>{
    const h=await harness().ready(responseBody(4,true,false)); openKey(h);
    h.node(action).emit("click"); h.node("material-key-details").open=false;
    h.node("material-key-details").emit("toggle"); await h.reply(1,keyBody());
    assert.ok(!h.displayedText().includes(KEY)); assert.deepEqual(h.copied,[]);
  });
}

for (const status of [401,403,409]) {
  test(`${status} on a key read never exposes a secret and requires recovery`,async()=>{
    const h=await harness().ready(responseBody(4,true,false)); openKey(h);
    h.node("material-key-copy").emit("click"); await h.reply(1,{error:"synthetic rejection"},status);
    assert.ok(!h.displayedText().includes(KEY)); assert.equal(h.node("material-save").disabled,true);
    assert.equal(h.node("material-key-copy").disabled,true);
    assert.deepEqual(h.copied,[]);
  });
}

test("leaving and BFCache recovery ignore a late plaintext response",async()=>{
  const h=await harness().ready(responseBody(4,true,false)); openKey(h);
  h.node("material-key-copy").emit("click"); h.emit("pagehide");
  h.emit("pageshow",{persisted:true}); await h.reply(2,responseBody(5,true,false));
  await h.reply(1,keyBody()); assert.ok(!h.displayedText().includes(KEY)); assert.deepEqual(h.copied,[]);
  assert.equal(h.node("material-key-details").open,false);
});

test("refresh and mutation erase any displayed key before awaiting their response",async()=>{
  const h=await harness().ready(responseBody(4,true,false)); openKey(h);
  h.node("material-key-reveal").emit("click"); await h.reply(1,keyBody());
  h.node("material-refresh").emit("click"); assert.ok(!h.displayedText().includes(KEY));
  await h.reply(2,responseBody(4,true,false)); openKey(h);
  h.node("material-key-reveal").emit("click"); await h.reply(3,keyBody());
  h.submit(); assert.ok(!h.displayedText().includes(KEY));
  await h.reply(4,responseBody(5,true,false));
});

for (const bad of [{...keyBody(),provider:"fal"},{...keyBody(),revision:9},{...keyBody(),api_key:"short"}]) {
  test(`invalid reveal response ${JSON.stringify(Object.keys(bad))} is never displayed or copied`,async()=>{
    const h=await harness().ready(responseBody(4,true,false)); openKey(h);
    h.node("material-key-copy").emit("click"); await h.reply(1,bad);
    assert.ok(!h.displayedText().includes(KEY)); assert.deepEqual(h.copied,[]);
  });
}

async function main() {
  let failures = 0;
  for (const item of tests) {
    try {
      await item.run();
      console.log(`PASS ${item.name}`);
    } catch (error) {
      failures++;
      console.error(`FAIL ${item.name}\n${error.stack}`);
    }
  }
  console.log(`${tests.length - failures} passed, ${failures} failed (synthetic material-settings UI)`);
  if (failures) process.exitCode = 1;
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
