"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  let revision = null, configured = false, pending = false, authenticated = true;
  let committedEnabled = false;
  let generation = 0;
  function message(text, error = false) {
    const target = el("material-message");
    target.textContent = text;
    target.classList.toggle("hidden", !text);
    target.classList.toggle("warning", error);
  }
  function controls() {
    const blocked = pending || !authenticated || revision === null;
    for (const id of ["material-key", "material-model", "material-save", "material-enabled", "material-enable-save"])
      el(id).disabled = blocked;
    el("material-remove").disabled = blocked || !configured;
    el("material-refresh").disabled = pending;
    el("material-save").textContent = "保存配置";
  }
  async function call(method = "GET", payload = null, current = generation) {
    const response = await fetch("/api/admin/material-settings", {
      method, credentials: "same-origin", cache: "no-store",
      headers: {"X-HSD-Token": window.HSD_TOKEN, ...(payload ? {"Content-Type": "application/json"} : {})},
      ...(payload ? {body: JSON.stringify(payload)} : {})
    });
    if (response.status === 401 || response.status === 403) {
      if (current === generation) {
        authenticated = false; revision = null;
        el("material-key").value = "";
        el("material-login").classList.remove("hidden");
        controls();
      }
      throw new Error("登录已失效，请重新登录管理员页面。");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(response.status === 409 ? "其他页面已更新配置，请刷新后重新保存。" : data.error || "操作没有完成，请检查网络后重试。");
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function render(data) {
    if (data.settings.provider !== "volcengine_ark" || typeof data.settings.model_id !== "string")
      throw new Error("配置版本已更新，请刷新页面后重试。");
    revision = data.settings.revision;
    configured = data.settings.configured;
    committedEnabled = data.settings.enabled;
    el("material-enabled").checked = committedEnabled;
    el("material-model").value = data.settings.model_id || "";
    el("material-ark").textContent = data.settings.warning || (configured ? (data.settings.model_id ? "配置已保存 · 真实接口及图片效果尚待验证" : "Key 已保存，请补充图片模型 ID") : "尚未配置火山方舟 Key");
    el("material-deepseek").textContent = data.deepseek.enabled && data.deepseek.configured ? "DeepSeek 已启用，沿用现有 Key" : "请先在管理员首页配置并启用 DeepSeek";
    controls();
  }
  async function load() {
    if (pending) return;
    const current = ++generation;
    pending = true; controls();
    try { const data = await call(); if (current === generation && authenticated) {render(data); message("");} }
    catch (error) { if (current === generation) message(error.status || !authenticated ? error.message : "无法读取设置，请检查网络后刷新。", true); }
    finally { if (current === generation) {pending = false; controls();} }
  }
  async function save(payload) {
    if (pending || revision === null || !authenticated) return;
    const current = ++generation;
    pending = true; controls();
    try {
      const data = await call("POST", {...payload, provider: "volcengine_ark", expected_revision: revision}, current);
      if (current === generation && authenticated) {render(data); message("设置已保存。真实接口及图片效果仍需验证。");}
    } catch (error) {
      if (current === generation) {
        el("material-enabled").checked = committedEnabled;
        if (error.status !== 400) revision = null;
        message(error.status || !authenticated ? error.message : "保存结果未确认，请刷新设置后核对。", true);
      }
    }
    finally { if (current === generation) {pending = false; controls();} }
  }
  el("material-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const key = el("material-key").value.trim();
    el("material-key").value = "";
    const model = el("material-model").value.trim();
    if (!key && !configured) {message("请先填写火山方舟 API Key。", true); return;}
    if (!model) {message("请先填写图片模型 ID。", true); return;}
    save({action: "set_config", api_key: key, model_id: model});
  });
  el("material-enable-form").addEventListener("submit", (event) => {event.preventDefault(); save({action: "set_enabled", enabled: el("material-enabled").checked});});
  el("material-remove").addEventListener("click", () => save({action: "remove_key"}));
  el("material-refresh").addEventListener("click", load);
  window.addEventListener("pagehide", () => {generation++; authenticated = false; el("material-key").value = "";});
  window.addEventListener("pageshow", (event) => {if (event.persisted) {generation++; pending = false; authenticated = true; revision = null; load();}});
  load();
})();
