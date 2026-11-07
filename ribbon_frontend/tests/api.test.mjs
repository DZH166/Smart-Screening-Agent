import test from "node:test";
import assert from "node:assert/strict";
import { api, post, setRequestToken, ApiError, normalizedPatternRoles, snapshotPatternRoles, isDirectLayoutReference } from "../src/api.ts";

test("one company case can be direct for one layout and only partial for another", () => {
  const example={available:true,reference_only:false,mode_tags:["split","panels"],mode_notes:{split:{fit:"direct"},panels:{fit:"partial"}}};
  assert.equal(isDirectLayoutReference(example,"split"),true);
  assert.equal(isDirectLayoutReference(example,"panels"),false);
  assert.equal(isDirectLayoutReference(example,"scatter"),false);
  assert.equal(isDirectLayoutReference({...example,available:false},"split"),false);
  assert.equal(isDirectLayoutReference({...example,reference_only:true},"split"),false);
  assert.equal(isDirectLayoutReference({...example,mode_notes:undefined},"split"),false);
  assert.equal(isDirectLayoutReference({...example,mode_notes:{split:{fit:"unknown"}}},"split"),false);
});

test("pattern roles preserve stable ownership after replacement and discard stale scope", () => {
  assert.deepEqual(normalizedPatternRoles(["a","b","c"],"scene"),{a:"main",b:"support",c:"support"});
  assert.deepEqual(normalizedPatternRoles(["a","b"],"bordered"),{a:"main",b:"main"},"a second person never silently becomes trim");
  assert.deepEqual(normalizedPatternRoles(["a","b"],"scatter",{a:"main",b:"accent",removed:"border"}),{a:"main",b:"accent"});
  assert.deepEqual(normalizedPatternRoles(["a","b"],"bordered",{a:"main",b:"accent"}),{a:"main",b:"main"});
  assert.deepEqual(normalizedPatternRoles(["a","b"],"single",{a:"main",b:"accent"}),{});
  const snapshot={layout_engine:"seamless-unit-v3",template_mode:"scene",asset_refs:["edited-a","b","c"],pattern_slots:["slot-a","slot-b","slot-c"],pattern_roles:{"slot-a":"main","slot-b":"support","slot-c":"accent"}};
  assert.deepEqual(snapshotPatternRoles(snapshot),{"edited-a":"main",b:"support",c:"accent"},"derived asset keeps its stable slot's role");
  assert.deepEqual(snapshotPatternRoles({...snapshot,layout_engine:"seamless-unit-v2"}),{},"legacy snapshots cannot activate role controls");
});

test("same-origin gateway and fresh HSD token protect JSON and multipart writes", async () => {
  const original = globalThis.fetch, calls = [];
  let token = "synthetic-one";
  setRequestToken(() => token);
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ ok: true }), { status: 200 });
  };
  try {
    await api("/auth/me");
    assert.equal(calls[0].url, "/api/ribbon/auth/me");
    assert.equal(calls[0].options.credentials, "same-origin");
    assert.equal(calls[0].options.cache, "no-store");
    assert.equal(calls[0].options.headers.has("X-HSD-Token"), false);
    await post("/designs", { name: "合成测试" });
    assert.equal(calls[1].options.headers.get("X-HSD-Token"), token);
    assert.equal(calls[1].options.headers.get("Content-Type"), "application/json");
    token = "synthetic-two";
    await api("/assets", { method: "POST", body: new FormData() });
    assert.equal(calls[2].options.headers.get("X-HSD-Token"), token);
    assert.equal(calls[2].options.headers.has("Content-Type"), false);
    await api("/assets/a", { method: "DELETE" });
    assert.equal(calls[3].options.headers.get("X-HSD-Token"), token);
  } finally { globalThis.fetch = original; }
});

test("gateway and backend errors stay failures, never become demo results", async () => {
  const original = globalThis.fetch;
  try {
    for (const body of [{ error: "登录已失效" }, { detail: "模型未完成" }]) {
      globalThis.fetch = async () => new Response(JSON.stringify(body), { status: 403 });
      await assert.rejects(post("/designs/a/generate", {}), error =>
        error instanceof ApiError && error.status === 403 && error.message === (body.error || body.detail));
    }
  } finally { globalThis.fetch = original; }
});

test("read deadlines and explicit cancellation preserve mutation recovery", async () => {
  const originalFetch=globalThis.fetch, originalSet=globalThis.setTimeout, originalClear=globalThis.clearTimeout;
  let deadline, timerCalls=0;
  globalThis.setTimeout=(fn)=>{deadline=fn;timerCalls++;return 1;};
  globalThis.clearTimeout=()=>{};
  globalThis.fetch=(_url,options)=>new Promise((_resolve,reject)=>{
    options.signal?.addEventListener("abort",()=>reject(new DOMException("aborted","AbortError")),{once:true});
  });
  try {
    const read=api("/assets");assert.equal(timerCalls,1);deadline();
    await assert.rejects(read,e=>e instanceof ApiError && e.status===408);
    const caller=new AbortController(), cancelled=api("/assets",{signal:caller.signal});
    caller.abort();await assert.rejects(cancelled,e=>e.name==="AbortError");
    let writeSignal;
    globalThis.fetch=async(_url,options)=>{writeSignal=options.signal;return new Response("{}",{status:200});};
    const before=timerCalls;await post("/designs",{name:"synthetic"});
    assert.equal(timerCalls,before);assert.equal(writeSignal,undefined,"no timeout hides a write's uncertain result");
  } finally {
    globalThis.fetch=originalFetch;globalThis.setTimeout=originalSet;globalThis.clearTimeout=originalClear;
  }
});

test("only definite pre-acceptance page-token rejection refreshes and resends once", async () => {
  const original = globalThis.fetch, calls = [];
  setRequestToken(() => "synthetic-old-page");
  globalThis.fetch = async (url, options) => {
    calls.push({url, options});
    if (url.endsWith("/session")) return Response.json({token:"synthetic-new-page"});
    if (options.headers.get("X-HSD-Token") === "synthetic-old-page")
      return Response.json({code:"page_token_expired", error:"页面凭证已更新"}, {status:403});
    return Response.json({id:"synthetic-job"}, {status:202});
  };
  try {
    const body = {idempotency_key:"synthetic-once",prompt:"调整间距"};
    assert.equal((await post("/designs/a/refinements", body)).id,"synthetic-job");
    assert.equal(calls.length,3);
    assert.equal(calls[0].options.body,calls[2].options.body);
    assert.equal(calls[1].options.credentials,"same-origin");
    await post("/designs/a/refinements", body);
    assert.equal(calls.length,4,"recovered token is reused on next write");
    for (const status of [401,403,429,500,502]) {
      let attempts=0;
      globalThis.fetch=async()=>{attempts++;return Response.json({error:"ordinary failure"},{status});};
      await assert.rejects(post("/designs/a/refinements",body),e=>e.status===status);
      assert.equal(attempts,1);
    }
    let attempts=0;
    globalThis.fetch=async()=>{attempts++;throw new TypeError("connection lost");};
    await assert.rejects(post("/designs/a/refinements",body));
    assert.equal(attempts,1,"unknown result is never replayed");
  } finally {globalThis.fetch=original;setRequestToken(()=>"");}
});

test("page-token refresh does not bypass genuine expiry or retry forever", async () => {
  const original=globalThis.fetch;
  try {
    for (const sessionStatus of [200,401]) {
      let attempts=0;
      globalThis.fetch=async(url)=>{attempts++;return url.endsWith("/session")
        ? Response.json(sessionStatus===200?{token:"synthetic-fresh"}:{error:"登录过期"},{status:sessionStatus})
        : Response.json({code:"page_token_expired"},{status:403});};
      await assert.rejects(post("/designs/a/refinements",{idempotency_key:"synthetic-key"}),e=>e.status===(sessionStatus===401?401:403));
      assert.equal(attempts,sessionStatus===401?2:3);
    }
  } finally {globalThis.fetch=original;setRequestToken(()=>"");}
});
