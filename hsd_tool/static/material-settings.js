"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  let revision = null, configured = false, pending = false, authenticated = true;
  let committedEnabled = false;
  let generation = 0;
  let keyShown = false, keyReading = false, keyEpoch = 0;
  function hideModel() {
    el("material-model").type = "password";
    el("material-model-reveal").textContent = "显示";
    el("material-model-reveal").setAttribute?.("aria-pressed", "false");
  }
  function clearKeyView(close = true) {
    keyEpoch++; keyReading = false; keyShown = false;
    el("material-key-value").textContent = "••••••••";
    el("material-key-reveal").textContent = "显示 Key";
    if (close) el("material-key-details").open = false;
  }
  function message(text, error = false) {
    const target = el("material-message");
    target.textContent = text;
    target.classList.toggle("hidden", !text);
    target.classList.toggle("warning", error);
  }
  function controls() {
    const blocked = pending || keyReading || !authenticated || revision === null;
    for (const id of ["material-key", "material-model", "material-save", "material-enabled", "material-enable-save"])
      el(id).disabled = blocked;
    el("material-remove").disabled = blocked || !configured;
    el("material-refresh").disabled = pending || keyReading;
    for (const id of ["material-key-reveal", "material-key-copy"])
      el(id).disabled = blocked || !configured;
    el("material-model-reveal").disabled = blocked;
    el("material-model-copy").disabled = blocked || !el("material-model").value;
    el("material-save").textContent = "保存配置";
  }
  async function call(method = "GET", payload = null, current = generation, path = "/api/admin/material-settings") {
    const response = await fetch(path, {
      method, credentials: "same-origin", cache: "no-store",
      headers: {"X-HSD-Token": window.HSD_TOKEN, ...(payload ? {"Content-Type": "application/json"} : {})},
      ...(payload ? {body: JSON.stringify(payload)} : {})
    });
    if (response.status === 401 || response.status === 403) {
      if (current === generation) {
        authenticated = false; revision = null;
        el("material-key").value = "";
        hideModel();
        clearKeyView();
        el("material-login").classList.remove("hidden");
        message("登录已失效，请重新登录管理员页面。", true);
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
    hideModel();
    el("material-ark").textContent = data.settings.warning || (configured ? (data.settings.model_id ? (committedEnabled ? "配置已保存 · 素材提取已启用" : "配置已保存 · 素材提取未启用") : "Key 已保存，请补充图片模型 ID") : "尚未配置火山方舟 Key");
    el("material-deepseek").textContent = data.deepseek.enabled && data.deepseek.configured ? "DeepSeek 已启用，沿用现有 Key" : "请先在管理员首页配置并启用 DeepSeek";
    controls();
  }
  async function load() {
    if (pending || keyReading) return;
    clearKeyView();
    hideModel();
    const current = ++generation;
    pending = true; controls();
    try { const data = await call(); if (current === generation && authenticated) {render(data); message("");} }
    catch (error) { if (current === generation) message(error.status || !authenticated ? error.message : "无法读取设置，请检查网络后刷新。", true); }
    finally { if (current === generation) {pending = false; controls();} }
  }
  async function save(payload) {
    if (pending || keyReading || revision === null || !authenticated) return;
    clearKeyView();
    hideModel();
    const current = ++generation;
    pending = true; controls();
    try {
      const data = await call("POST", {...payload, provider: "volcengine_ark", expected_revision: revision}, current);
      if (current === generation && authenticated) {render(data); message("设置已保存。");}
    } catch (error) {
      if (current === generation) {
        el("material-enabled").checked = committedEnabled;
        if (error.status !== 400) revision = null;
        message(error.status || !authenticated ? error.message : "保存结果未确认，请刷新设置后核对。", true);
      }
    }
    finally { if (current === generation) {pending = false; controls();} }
  }
  async function keyAction(copy) {
    if (pending || keyReading || revision === null || !authenticated || !configured || !el("material-key-details").open) return;
    if (!copy && keyShown) {clearKeyView(false); controls(); return;}
    const current = generation, epoch = ++keyEpoch;
    const active = () => current === generation && epoch === keyEpoch && authenticated && el("material-key-details").open;
    keyReading = true; controls();
    let copying = false;
    try {
      // Fresh, revision-bound read for every show/copy; never cache in attributes.
      const data = await call("GET", null, current, `/api/admin/material-key?revision=${revision}`);
      if (!active()) return;
      if (data.provider !== "volcengine_ark" || data.revision !== revision ||
          typeof data.api_key !== "string" || data.api_key.length < 10 || data.api_key.length > 512 ||
          !/^[\x21-\x7e]+$/.test(data.api_key)) throw new Error("invalid_key_response");
      if (copy) {
        if (!navigator.clipboard?.writeText) {
          message("当前浏览器无法自动复制，请显示 Key 后手动复制。", true); return;
        }
        copying = true;
        await navigator.clipboard.writeText(data.api_key);
        if (active()) message("Key 已复制。");
      } else {
        el("material-key-value").textContent = data.api_key;
        el("material-key-reveal").textContent = "隐藏 Key";
        keyShown = true;
      }
    } catch (error) {
      if (active()) {
        clearKeyView(false);
        if (error.status === 409) revision = null;
        message(error.status ? error.message : copying ? "复制未完成，请显示 Key 后手动复制。" : "无法读取 Key，请刷新设置后重试。", true);
      }
    } finally { if (current === generation && epoch === keyEpoch) {keyReading = false; controls();} }
    // Error clearing invalidates this read; refresh control state explicitly.
    if (current === generation) controls();
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
  el("material-key-reveal").addEventListener("click", () => keyAction(false));
  el("material-key-copy").addEventListener("click", () => keyAction(true));
  el("material-model").addEventListener("input", controls);
  el("material-model-reveal").addEventListener("click", () => {
    if (pending || keyReading || !authenticated || revision === null) return;
    const show = el("material-model").type === "password";
    el("material-model").type = show ? "text" : "password";
    el("material-model-reveal").textContent = show ? "隐藏" : "显示";
    el("material-model-reveal").setAttribute?.("aria-pressed", String(show));
  });
  el("material-model-copy").addEventListener("click", async () => {
    if (pending || keyReading || !authenticated || revision === null || !el("material-model").value) return;
    const current = generation;
    if (!navigator.clipboard?.writeText) {message("当前浏览器无法自动复制，请显示模型 ID 后手动复制。", true); return;}
    try {
      await navigator.clipboard.writeText(el("material-model").value);
      if (current === generation && authenticated) message("模型 ID 已复制。");
    } catch (_) {if (current === generation && authenticated) message("复制未完成，请显示模型 ID 后手动复制。", true);}
  });
  el("material-key-details").addEventListener("toggle", () => {if (!el("material-key-details").open) {clearKeyView(false); controls();}});
  window.addEventListener("pagehide", () => {generation++; authenticated = false; el("material-key").value = ""; hideModel(); clearKeyView(); controls();});
  window.addEventListener("pageshow", (event) => {if (event.persisted) {generation++; pending = false; authenticated = true; revision = null; load();}});
  load();
})();
