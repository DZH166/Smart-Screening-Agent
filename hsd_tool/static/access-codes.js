"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  const state = {snapshot:null, pending:false, locked:false, refreshRequired:false, generation:0};
  const controllers = new Set();
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[char]));

  function message(text, error = false) {
    el("access-message").textContent = text;
    el("access-message").classList.toggle("hidden", !text);
    el("access-message").classList.toggle("error", error);
  }
  function clearCode() {
    el("access-code").value = "";
    el("access-code").type = "password";
    el("access-reveal").textContent = "显示";
    el("access-reveal").setAttribute("aria-pressed", "false");
  }
  function blocked() { return state.pending || state.locked || state.refreshRequired || state.snapshot?.supported !== true; }
  function controls() {
    for (const id of ["access-label", "access-code", "access-reveal", "access-add"]) el(id).disabled = blocked();
    el("access-list").querySelectorAll("button").forEach((button) => {button.disabled = blocked();});
    el("access-refresh").disabled = state.pending || state.locked;
    el("access-refresh").textContent = state.pending ? "读取或保存中…" : "刷新列表";
    el("access-add").textContent = state.pending ? "请稍候…" : "增加访问码";
  }
  function lock() {
    state.locked = true;
    clearCode();
    el("access-label").value = "";
    el("access-login").classList.remove("hidden");
    controls();
  }
  async function request(payload, generation) {
    const controller = new AbortController();
    controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch("/api/admin/access-codes", {
        method: payload ? "POST" : "GET", credentials:"same-origin", cache:"no-store", signal:controller.signal,
        headers:{"X-HSD-Token":window.HSD_TOKEN, ...(payload ? {"Content-Type":"application/json"} : {})},
        ...(payload ? {body:JSON.stringify(payload)} : {})
      });
      if (generation !== state.generation) throw Object.assign(new Error(), {obsolete:true});
      if (response.status === 401 || response.status === 403) {
        lock();
        throw Object.assign(new Error("登录已失效，请重新登录管理员页面。"), {status:response.status});
      }
      const result = await response.json().catch(() => ({}));
      if (generation !== state.generation) throw Object.assign(new Error(), {obsolete:true});
      if (!response.ok) throw Object.assign(new Error(result.error || "操作未完成，请稍后重试。"), {status:response.status});
      if (result.supported !== false && (result.supported !== true || !Number.isInteger(result.revision) || result.revision < 0 || !Array.isArray(result.codes) || !Number.isInteger(result.min_length) || result.min_length < 1 || result.max_length !== 64 || result.min_length > result.max_length || result.codes.some((code) => !code || typeof code.id !== "string" || typeof code.label !== "string" || typeof code.enabled !== "boolean" || !["configured", "saved"].includes(code.source)))) {
        throw new Error("设置结果未能确认，请刷新列表后核对。");
      }
      return result;
    } catch (error) {
      if (generation !== state.generation) error.obsolete = true;
      if (error.name === "AbortError") throw Object.assign(new Error("等待时间较长，结果还未确认。请刷新列表后核对。"), {obsolete:error.obsolete});
      if (error instanceof TypeError) throw Object.assign(new Error("暂时连不上服务器，请检查网络后刷新列表。"), {obsolete:error.obsolete});
      throw error;
    } finally {clearTimeout(timer); controllers.delete(controller);}
  }
  function cardHtml(code) {
    const configured = code.source === "configured";
    return `<article class="access-row" data-access-id="${escapeHtml(code.id)}"><div class="access-row-heading"><div class="access-row-name"><span class="access-name">${escapeHtml(configured ? "原有访问码" : code.label || "未备注访问码")}</span><span class="badge${code.enabled ? " good" : ""}">${code.enabled ? "可用" : "已停用"}</span></div>${configured ? "" : `<div class="access-actions"><button type="button" class="button secondary" data-action="toggle">${code.enabled ? "停用" : "启用"}</button><button type="button" class="button quiet" data-action="remove">删除</button></div>`}</div>${configured ? '<p class="muted access-readonly">由服务器原先的设置保留，不能在此修改。</p>' : '<div class="access-delete hidden" data-delete-prompt><p>确认删除这个访问码？删除后不能用于新的登录。</p><button type="button" class="button danger" data-action="confirm-remove">确认删除</button><button type="button" class="button quiet" data-action="cancel-remove">取消</button></div>'}</article>`;
  }
  function render(snapshot) {
    state.snapshot = snapshot;
    if (!snapshot.supported) {
      el("access-state").textContent = "当前为本机模式，不需要员工访问码。";
      el("access-count").textContent = "";
      el("access-list").innerHTML = "";
      return;
    }
    const codes = snapshot.codes;
    el("access-state").textContent = "员工输入任意一个已启用的访问码即可进入。";
    el("access-count").textContent = `${codes.filter((code) => code.enabled).length} 个可用 · ${codes.filter((code) => !code.enabled).length} 个已停用`;
    el("access-list").innerHTML = codes.length ? codes.map(cardHtml).join("") : '<p class="empty">还没有访问码，请在下面增加。</p>';
    el("access-code-help").textContent = `请设置 ${snapshot.min_length}～${snapshot.max_length} 位英文字母、数字或英文符号，不含空格。先自行保存；保存后不显示原码。`;
  }
  async function refresh() {
    if (state.pending || state.locked) return;
    const generation = ++state.generation;
    state.pending = true; controls();
    try {
      const result = await request(null, generation);
      if (generation !== state.generation) return;
      state.refreshRequired = false;
      render(result); message("");
    } catch (error) {
      if (!error.obsolete) {state.refreshRequired = true; message(error.message, true);}
    } finally {if (generation === state.generation) {state.pending = false; controls();}}
  }
  async function save(change, added = false) {
    if (blocked()) return;
    const generation = ++state.generation;
    const payload = {...change, expected_revision:state.snapshot.revision};
    state.pending = true; message(""); controls();
    try {
      const result = await request(payload, generation);
      if (generation !== state.generation) return;
      render(result);
      if (added) el("access-label").value = "";
      message(added ? "访问码已增加，可以告诉员工使用。" : "访问码设置已保存。");
    } catch (error) {
      if (error.obsolete) return;
      if (error.status === 409) {
        state.refreshRequired = true;
        message("其他页面已改过访问码，本次没有保存。请点击“刷新列表”核对后再操作。备注和当前列表已保留，新访问码请重新填写。", true);
      } else {
        if (error.status !== 400 && error.status !== 401 && error.status !== 403) state.refreshRequired = true;
        message(error.message, true);
      }
    } finally {
      for (const entry of payload.add || []) delete entry.code;
      if (generation === state.generation) {state.pending = false; controls();}
    }
  }
  function add(event) {
    event.preventDefault();
    if (blocked()) {clearCode(); return;}
    const code = el("access-code").value;
    const label = el("access-label").value.trim();
    clearCode();
    const length = Array.from(code).length;
    if (length < state.snapshot.min_length || length > state.snapshot.max_length || !/^[\x21-\x7e]+$/.test(code)) {
      message(`请填写 ${state.snapshot.min_length}～${state.snapshot.max_length} 位英文字母、数字或英文符号，不含空格或中文。输入已清空，请重新填写。`, true);
      el("access-code").focus(); return;
    }
    if (Array.from(label).length > 40 || (label && label.includes(code))) {
      message("备注最多 40 个字，不要把访问码写进备注；也可以不填备注。访问码输入已清空，请重新填写。", true);
      el("access-label").focus(); return;
    }
    save({add:[{code, ...(label ? {label} : {})}]}, true);
  }
  function action(event) {
    if (blocked()) return;
    const button = event.target.closest("[data-action]");
    const card = button?.closest("[data-access-id]");
    if (!card) return;
    const code = state.snapshot.codes.find((item) => item.id === card.dataset.accessId);
    if (!code || code.source === "configured") return;
    const selected = button.dataset.action;
    if (selected === "toggle") save({update:[{id:code.id, enabled:!code.enabled}]});
    if (selected === "remove" || selected === "cancel-remove") {
      const prompt = card.querySelector("[data-delete-prompt]");
      prompt.classList.toggle("hidden", selected === "cancel-remove");
      if (selected === "remove") prompt.querySelector("button").focus();
    }
    if (selected === "confirm-remove") save({remove:[code.id]});
  }
  el("access-form").addEventListener("submit", add);
  el("access-refresh").addEventListener("click", refresh);
  el("access-list").addEventListener("click", action);
  el("access-reveal").addEventListener("click", () => {
    if (blocked()) return;
    const show = el("access-code").type === "password";
    el("access-code").type = show ? "text" : "password";
    el("access-reveal").textContent = show ? "隐藏" : "显示";
    el("access-reveal").setAttribute("aria-pressed", String(show));
    el("access-code").focus();
  });
  window.addEventListener("pagehide", () => {
    state.generation++; state.locked = true; state.pending = false; clearCode();
    controllers.forEach((controller) => controller.abort());
    controls();
  });
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    state.locked = false; state.snapshot = null; state.refreshRequired = true;
    el("access-login").classList.add("hidden");
    refresh();
  });
  refresh();
})();
