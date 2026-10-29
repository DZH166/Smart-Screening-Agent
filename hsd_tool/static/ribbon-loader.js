"use strict";
(() => {
  const host = document.getElementById("ribbon-mount");
  if (!host) return;
  let app = null, loading = null, selected = location.hash.slice(1);
  const isRibbon = name => name === "ribbon" || name === "ribbon-admin";
  function failure() {
    host.replaceChildren();
    const message = document.createElement("p");
    message.setAttribute("role", "alert");
    message.textContent = "丝带设计没有加载成功，请重试。已提交的任务仍在后台保存。";
    const retry = document.createElement("button");
    retry.className = "button button-secondary";
    retry.type = "button";
    retry.textContent = "重新加载";
    retry.addEventListener("click", () => activate(selected));
    host.append(message, retry);
  }
  async function activate(name) {
    selected = name;
    if (!isRibbon(name)) { app?.setView("ribbon", false); return; }
    if (app) { app.setView(name, true); return; }
    if (loading) return;
    loading = import("/static/ribbon/ribbon.js");
    try {
      const module = await loading;
      host.replaceChildren();
      app = module.mount(host, () => window.HSD_TOKEN || "");
      app.setView(isRibbon(selected) ? selected : "ribbon", isRibbon(selected));
    } catch (_) { failure(); }
    finally { loading = null; }
  }
  window.addEventListener("hsd-workspace-change", event => activate(event.detail.workspace));
  void activate(selected);
})();
