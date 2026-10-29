/*
 * Detect that the open page is older than the running release.
 *
 * The page embeds the build it was rendered from; /healthz reports the build the
 * server is running. Hash navigation never reloads a document, so an old admin
 * tab can look broken while the deployed files are already new.
 */
"use strict";
(() => {
  const own = window.HSD_BUILD;
  if (!own) return;
  let shown = false;
  function banner() {
    if (shown || document.getElementById("hsd-stale-banner")) return;
    shown = true;
    const node = document.createElement("div");
    node.id = "hsd-stale-banner";
    node.setAttribute("role", "alert");
    node.style.cssText = [
      "position:fixed", "z-index:2147483647", "left:50%", "top:14px",
      "transform:translateX(-50%)", "max-width:min(92vw,560px)",
      "padding:11px 16px", "border-radius:10px", "font:14px/1.5 system-ui,sans-serif",
      "background:#3b2f12", "color:#fff8e6", "box-shadow:0 8px 24px #0003",
      "display:flex", "gap:12px", "align-items:center",
    ].join(";");
    const text = document.createElement("span");
    text.textContent = "系统已更新，当前页面是旧版本，请刷新后再操作。";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "立即刷新";
    button.style.cssText = "border:0;border-radius:6px;padding:6px 12px;background:#f4d58d;color:#3b2f12;font-weight:600;cursor:pointer";
    button.addEventListener("click", () => location.reload());
    node.append(text, button);
    document.body.append(node);
  }
  async function check() {
    try {
      const response = await fetch("/healthz", { cache: "no-store", credentials: "same-origin" });
      const build = response.headers.get("X-HSD-Build");
      if (build && build !== own) banner();
    } catch (_) {
      /* offline or blocked; the next tick retries */
    }
  }
  check();
  setInterval(check, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) check();
  });
})();
