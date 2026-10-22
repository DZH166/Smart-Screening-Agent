// Synthetic DOM and API responses only. No real codes, browser storage or server calls.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../hsd_tool/static/access-codes.js"), "utf8");
const CODE = "SYNTHETIC-ACCESS-CODE-ONLY";
const flush = () => new Promise(setImmediate);
function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => {resolve = done; reject = fail;});
  return {promise, resolve, reject};
}
function snapshot(revision = 4, changes = {}) {
  return {supported:true, revision, min_length:8, max_length:64, codes:[
    {id:"configured", label:"原有访问码", enabled:true, source:"configured"},
    {id:"saved-a", label:"设计组", enabled:true, source:"saved"}
  ], ...changes};
}
function harness() {
  const nodes = new Map(), windowListeners = new Map(), calls = [], timers = new Map();
  let nextTimer = 0;
  function node(id) {
    if (!nodes.has(id)) {
      const classes = new Set(["access-message", "access-login"].includes(id) ? ["hidden"] : []);
      const listeners = new Map();
      nodes.set(id, {id, value:"", type:id === "access-code" ? "password" : "text", textContent:"", innerHTML:"", disabled:false, dataset:{}, controls:[],
        classList:{add(...values) {values.forEach((value) => classes.add(value));}, remove(...values) {values.forEach((value) => classes.delete(value));}, contains(value) {return classes.has(value);}, toggle(value, force) {const next = force === undefined ? !classes.has(value) : force; if (next) classes.add(value); else classes.delete(value); return !!next;}},
        addEventListener(name, handler) {if (!listeners.has(name)) listeners.set(name, []); listeners.get(name).push(handler);},
        emit(name, target = this) {for (const handler of listeners.get(name) || []) handler({target, preventDefault() {}});},
        focus() {sandbox.document.activeElement = this;},
        setAttribute(name, value) {this[name] = value;},
        querySelectorAll() {return this.controls;}, querySelector(selector) {return node(`${id}:${selector}`);}
      });
    }
    return nodes.get(id);
  }
  const window = {HSD_TOKEN:"synthetic-access-csrf", addEventListener(name, handler) {if (!windowListeners.has(name)) windowListeners.set(name, []); windowListeners.get(name).push(handler);}};
  const sandbox = {window, document:{getElementById:node, activeElement:null}, AbortController, TypeError,
    setTimeout(handler, delay) {const id = ++nextTimer; timers.set(id, {handler, delay}); return id;}, clearTimeout(id) {timers.delete(id);},
    fetch(url, options) {const pending = deferred(); calls.push({url, options, pending}); return pending.promise;}
  };
  vm.runInNewContext(source, sandbox, {filename:"access-codes.js"});
  return {node, calls, timers,
    emit(name, event = {}) {for (const handler of windowListeners.get(name) || []) handler(event);},
    async reply(index, body = snapshot(), status = 200) {calls[index].pending.resolve({ok:status >= 200 && status < 300, status, json:async () => body}); await flush();},
    async reject(index) {calls[index].pending.reject(new TypeError("synthetic network failure")); await flush();},
    async ready(body = snapshot()) {await this.reply(0, body); return this;},
    submit(code = CODE, label = "设计二组") {node("access-code").value = code; node("access-label").value = label; node("access-form").emit("submit");},
    action(id, action) {
      const card = node(`card:${id}`); card.dataset.accessId = id;
      const button = {dataset:{action}, closest(selector) {return selector === "[data-action]" ? this : selector === "[data-access-id]" ? card : null;}};
      node("access-list").emit("click", button); return card;
    },
    payload(index) {return JSON.parse(calls[index].options.body);},
    displayed() {return [...nodes.values()].map((item) => `${item.textContent}\n${item.innerHTML}`).join("\n");}
  };
}
const tests = [];
function test(name, run) {tests.push({name, run});}

test("boot authenticates one safe read, never polls or reads a secret ledger", async () => {
  const h = harness();
  assert.equal(h.calls.length, 1);
  assert.equal(h.node("access-code").disabled, true);
  const request = h.calls[0];
  assert.equal(request.url, "/api/admin/access-codes");
  assert.equal(request.options.method, "GET");
  assert.equal(request.options.credentials, "same-origin");
  assert.equal(request.options.cache, "no-store");
  assert.equal(request.options.headers["X-HSD-Token"], "synthetic-access-csrf");
  assert.equal(request.options.body, undefined);
  await h.ready();
  assert.equal(h.timers.size, 0, "no polling after the initial read");
  assert.equal(h.node("access-code").disabled, false);
  assert.match(h.node("access-count").textContent, /2 个可用/);
  assert.match(h.node("access-code-help").textContent, /8～64/);
  assert.equal(h.node("access-code").type, "password");
});

test("adding clears the code before waiting, prevents duplicate writes and waits for server success", async () => {
  const h = await harness().ready();
  h.node("access-reveal").emit("click");
  assert.equal(h.node("access-code").type, "text");
  assert.equal(h.node("access-reveal")["aria-pressed"], "true");
  h.submit();
  assert.equal(h.node("access-code").value, "");
  assert.equal(h.node("access-code").type, "password");
  assert.equal(h.node("access-reveal")["aria-pressed"], "false");
  assert.deepEqual(h.payload(1), {add:[{code:CODE, label:"设计二组"}], expected_revision:4});
  assert.equal(h.calls[1].options.headers["Content-Type"], "application/json");
  assert.equal(h.calls[1].options.method, "POST");
  assert.equal(h.node("access-add").disabled, true);
  assert.ok(!/已增加/.test(h.node("access-message").textContent));
  h.submit(); h.action("saved-a", "toggle"); h.node("access-refresh").emit("click");
  assert.equal(h.calls.length, 2);
  await h.reply(1, snapshot(5, {codes:[...snapshot().codes, {id:"saved-b", label:"设计二组", enabled:true, source:"saved"}]}));
  assert.match(h.node("access-message").textContent, /已增加/);
  assert.equal(h.node("access-label").value, "");
  assert.equal(h.node("access-code").disabled, false);
  assert.ok(!h.displayed().includes(CODE));
});

test("invalid codes are rejected without silently trimming or requesting a save", async () => {
  const h = await harness().ready();
  for (const code of ["short", " synthetic-long-enough", "synthetic-long-enough ", "synthetic has space", "中文中文中文中文", "line\nbreak-long", "x".repeat(65)]) {
    h.submit(code);
    assert.equal(h.calls.length, 1);
    assert.equal(h.node("access-code").value, "");
    assert.match(h.node("access-message").textContent, /重新填写/);
  }
  h.submit(CODE, "");
  assert.deepEqual(h.payload(1), {add:[{code:CODE}], expected_revision:4});
  await h.reply(1, snapshot(5));
});

test("remarks cannot be too long or contain the submitted code, including a one-character code", async () => {
  const h = await harness().ready();
  for (const label of ["字".repeat(41), `设计组 ${CODE}`]) {
    h.submit(CODE, label);
    assert.equal(h.calls.length, 1);
    assert.equal(h.node("access-code").value, "");
    assert.equal(h.node("access-label").value, label);
    assert.match(h.node("access-message").textContent, /备注最多 40 个字.*不要把访问码写进备注/);
  }
  const short = await harness().ready(snapshot(4, {min_length:1}));
  short.submit("A", "A组");
  assert.equal(short.calls.length, 1);
  assert.equal(short.node("access-code").value, "");
  short.submit("A", "");
  assert.deepEqual(short.payload(1), {add:[{code:"A"}], expected_revision:4});
  await short.reply(1, snapshot(5, {min_length:1}));
});

test("configured codes remain readonly, while saved codes can toggle only after acknowledgement", async () => {
  const h = await harness().ready();
  const configuredHtml = h.node("access-list").innerHTML.split('data-access-id="configured"')[1].split('</article>')[0];
  assert.ok(!configuredHtml.includes("data-action"));
  h.action("configured", "toggle"); h.action("configured", "confirm-remove");
  assert.equal(h.calls.length, 1);
  const before = h.node("access-list").innerHTML;
  h.action("saved-a", "toggle");
  assert.deepEqual(h.payload(1), {update:[{id:"saved-a", enabled:false}], expected_revision:4});
  assert.equal(h.node("access-list").innerHTML, before, "no optimistic status replacement");
  await h.reply(1, snapshot(5, {codes:[snapshot().codes[0], {...snapshot().codes[1], enabled:false}]}));
  assert.match(h.node("access-count").textContent, /1 个可用 · 1 个已停用/);
  h.action("saved-a", "toggle");
  assert.deepEqual(h.payload(2), {update:[{id:"saved-a", enabled:true}], expected_revision:5});
  await h.reply(2, snapshot(6));
});

test("delete requires an inline confirmation and cancel does not send a request", async () => {
  const h = await harness().ready();
  const card = h.action("saved-a", "remove");
  assert.equal(h.calls.length, 1);
  assert.equal(card.querySelector("[data-delete-prompt]").classList.contains("hidden"), false);
  h.action("saved-a", "cancel-remove");
  assert.equal(card.querySelector("[data-delete-prompt]").classList.contains("hidden"), true);
  assert.equal(h.calls.length, 1);
  h.action("saved-a", "remove"); h.action("saved-a", "confirm-remove");
  assert.deepEqual(h.payload(1), {remove:["saved-a"], expected_revision:4});
  await h.reply(1, snapshot(5, {codes:[snapshot().codes[0]]}));
  assert.ok(!h.node("access-list").innerHTML.includes('data-access-id="saved-a"'));
});

test("a conflict preserves remarks and list, locks writes and requires an explicit refresh", async () => {
  const h = await harness().ready();
  const before = h.node("access-list").innerHTML;
  h.submit(); await h.reply(1, {error:"safe synthetic conflict"}, 409);
  assert.equal(h.node("access-list").innerHTML, before);
  assert.equal(h.node("access-label").value, "设计二组");
  assert.equal(h.node("access-code").value, "");
  assert.equal(h.node("access-add").disabled, true);
  assert.match(h.node("access-message").textContent, /没有保存.*刷新列表/);
  h.action("saved-a", "toggle"); h.submit(); assert.equal(h.calls.length, 2);
  h.node("access-refresh").emit("click"); await h.reply(2, snapshot(9));
  h.submit(); assert.equal(h.payload(3).expected_revision, 9); await h.reply(3, snapshot(10));
});

for (const status of [401, 403]) {
  for (const method of ["GET", "POST"]) {
    test(`${status} on ${method} clears sensitive input and locks the page`, async () => {
      const h = harness(); let index = 0;
      if (method === "POST") {await h.ready(); h.submit(); index = 1;}
      h.node("access-code").value = CODE;
      await h.reply(index, {}, status);
      assert.equal(h.node("access-code").value, "");
      assert.equal(h.node("access-add").disabled, true);
      assert.equal(h.node("access-refresh").disabled, true);
      assert.equal(h.node("access-login").classList.contains("hidden"), false);
      assert.match(h.node("access-message").textContent, /重新登录/);
      const before = h.calls.length;
      h.submit(); h.action("saved-a", "toggle"); h.node("access-refresh").emit("click");
      assert.equal(h.calls.length, before);
    });
  }
}

test("local mode disables additions and lists no access codes", async () => {
  const h = await harness().ready({supported:false});
  assert.equal(h.node("access-add").disabled, true);
  assert.equal(h.node("access-list").innerHTML, "");
  assert.match(h.node("access-state").textContent, /本机模式.*不需要/);
  h.submit(); assert.equal(h.calls.length, 1);
});

test("a rejected value allows a corrected retry but a lost save response requires refresh", async () => {
  const h = await harness().ready();
  h.submit(); await h.reply(1, {error:"这个访问码已经存在，请换一个。"}, 400);
  assert.equal(h.node("access-add").disabled, false);
  assert.ok(!/已增加/.test(h.node("access-message").textContent));
  h.submit(); assert.equal(h.payload(2).expected_revision, 4);
  await h.reject(2);
  assert.equal(h.node("access-add").disabled, true);
  assert.match(h.node("access-message").textContent, /刷新列表/);
  h.node("access-refresh").emit("click"); await h.reply(3, snapshot(8));
  assert.equal(h.node("access-add").disabled, false);
});

test("API labels are escaped and secret-looking unexpected response fields are never rendered", async () => {
  const h = await harness().ready(snapshot(4, {codes:[{id:'saved"<id>', label:'<img src=x onerror="unsafe">', enabled:true, source:"saved", code:CODE}]}));
  const html = h.node("access-list").innerHTML;
  assert.ok(html.includes("&lt;img")); assert.ok(!html.includes("<img"));
  assert.ok(html.includes("saved&quot;&lt;id&gt;")); assert.ok(!h.displayed().includes(CODE));
});

for (const oldFirst of [true, false]) {
  test(`restored pages ignore ${oldFirst ? "early" : "late"} stale responses and reauthenticate before enabling`, async () => {
    const h = harness();
    h.node("access-code").value = CODE; h.emit("pagehide");
    assert.equal(h.node("access-code").value, "");
    h.emit("pageshow", {persisted:true});
    assert.equal(h.calls.length, 2); assert.equal(h.node("access-add").disabled, true);
    if (oldFirst) {await h.reply(0, {}, 401); await h.reply(1, snapshot(20));}
    else {await h.reply(1, snapshot(20)); await h.reply(0, {}, 401);}
    assert.equal(h.node("access-login").classList.contains("hidden"), true);
    assert.equal(h.node("access-add").disabled, false);
    h.submit(); assert.equal(h.payload(2).expected_revision, 20); await h.reply(2, snapshot(21));
  });
}

test("leaving during a save prevents late success from changing the page", async () => {
  const h = await harness().ready(); const before = h.node("access-list").innerHTML;
  h.submit(); h.emit("pagehide"); await h.reply(1, snapshot(5, {codes:[]}));
  assert.equal(h.node("access-list").innerHTML, before);
  assert.ok(!/已增加/.test(h.node("access-message").textContent));
  assert.equal(h.node("access-add").disabled, true);
});

test("malformed success responses do not enable controls or claim a successful write", async () => {
  const h = harness(); await h.reply(0, {supported:true, revision:0});
  assert.equal(h.node("access-add").disabled, true);
  assert.match(h.node("access-message").textContent, /未能确认/);
});

(async () => {
  let failures = 0;
  for (const item of tests) {
    try {await item.run(); console.log(`PASS ${item.name}`);}
    catch (error) {failures++; console.error(`FAIL ${item.name}\n${error.stack}`);}
  }
  console.log(`${tests.length - failures} passed, ${failures} failed (synthetic access-code UI)`);
  if (failures) process.exitCode = 1;
})().catch((error) => {console.error(error); process.exitCode = 1;});
