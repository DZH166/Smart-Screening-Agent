import test from "node:test";
import assert from "node:assert/strict";
import { api, post, setRequestToken, ApiError } from "../src/api.ts";

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
      await assert.rejects(post("/designs/a/refinements", {}), error =>
        error instanceof ApiError && error.status === 403 && error.message === (body.error || body.detail));
    }
  } finally { globalThis.fetch = original; }
});
