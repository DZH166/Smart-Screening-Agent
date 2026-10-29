'use strict';
/**
 * Ribbon model service page.
 *
 * The ribbon workspace deliberately reuses the DeepSeek key pool and the 火山方舟
 * Seedream key configured for the material tool, so this page only shows which
 * models are inherited, whether they are ready, and one switch to enable the
 * paid calls. No keys are entered, copied or stored here.
 */
(() => {
  const root = document.getElementById('ribbon-settings-panel');
  if (!root) return;
  root.innerHTML = `
    <p id="ribbon-inherited-status" class="ribbon-inherit" role="status" aria-live="polite">正在读取模型…</p>
    <label class="ribbon-switch"><input id="ribbon-enabled" type="checkbox" disabled><span>启用丝带 AI 底图与精修</span></label>
    <p class="muted ribbon-note">启用后按实际调用计费；关闭后首稿排版照常可用。</p>
    <p id="ribbon-settings-state" role="status" aria-live="polite" class="ribbon-state"></p>
    <div class="ribbon-actions">
      <button id="ribbon-save" class="button primary" type="button" disabled>保存</button>
      <button id="ribbon-settings-reload" class="button secondary" type="button">重新读取</button>
    </div>`;
  const $ = id => root.querySelector(`#${id}`) || document.getElementById(id);
  const ROUTE = 'deepseek_seedream';
  let revision = null, busy = false, locked = false, epoch = 0;
  const message = (text, error = false) => {
    const node = $('ribbon-settings-state');
    node.textContent = text;
    node.classList.toggle('error', error);
  };
  function controls() {
    const disabled = busy || locked || revision === null;
    ['ribbon-enabled', 'ribbon-save'].forEach(id => { $(id).disabled = disabled; });
    $('ribbon-settings-reload').disabled = busy;
  }
  async function request(body) {
    const response = await fetch('/api/admin/ribbon-settings', {
      method: body ? 'POST' : 'GET', cache: 'no-store', credentials: 'same-origin',
      headers: {'X-HSD-Token': window.HSD_TOKEN || '', ...(body ? {'Content-Type': 'application/json'} : {})},
      ...(body ? {body: JSON.stringify(body)} : {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) locked = true;
      throw new Error(data.error || data.detail || '设置未完成，请重新登录或重试。');
    }
    return data;
  }
  function display(data) {
    revision = data.revision;
    $('ribbon-enabled').checked = !!data.enabled;
    const ready = !!data.inherited_ready;
    $('ribbon-inherited-status').textContent = ready
      ? `已就绪：${data.inherited_language_model || '未配置'} ＋ ${data.inherited_image_model || '未配置'}`
      : 'DeepSeek 或火山方舟配置不完整，请先在 Key 账本补齐。';
    $('ribbon-inherited-status').classList.toggle('warn', !ready);
    if (data.provider !== ROUTE) {
      message('当前保存的是另一条路线，保存会切回 DeepSeek ＋ Seedream。', true);
      return;
    }
    message(data.warning || (data.enabled ? '已启用。' : '未启用：首稿排版可用，AI 底图与精修不可用。'));
  }
  async function load() {
    if (busy) return;
    busy = true; controls(); const ticket = ++epoch;
    try { const data = await request(); if (ticket === epoch) display(data); }
    catch (error) { if (ticket === epoch) message(error.message, true); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  async function save() {
    if (busy || locked || revision === null) return;
    const body = {expected_revision: revision, provider: ROUTE, enabled: $('ribbon-enabled').checked};
    busy = true; controls(); const ticket = ++epoch; message('正在保存…');
    try { const data = await request(body); if (ticket === epoch) display(data); }
    catch (error) { if (ticket === epoch) message(error.message, true); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  $('ribbon-save').addEventListener('click', save);
  $('ribbon-settings-reload').addEventListener('click', load);
  document.getElementById('ribbon-refresh')?.addEventListener('click', load);
  window.addEventListener('pagehide', () => { epoch++; });
  controls();
  load();
})();
