'use strict';
(() => {
  const root = document.getElementById('ribbon-settings-panel');
  if (!root) return;
  // Only the inherited route is exposed: 丝带 reuses the DeepSeek Key pool and the
  // 火山方舟 Seedream key already configured for the other tools. The OpenAI route
  // stays in the backend but is not offered here, so no preset can be picked by
  // accident; the server rejects enabling it without a saved key anyway.
  root.innerHTML = `<details id="ribbon-settings-details" open><summary>丝带设计 · 模型服务</summary>
    <form id="ribbon-settings-form" class="help-content">
      <p>仅影响丝带设计。首稿由原素材排版，不调用模型；AI 底图和文字精修使用下面这条路线。</p>
      <p><strong>调用路线：</strong>DeepSeek ＋ Seedream（沿用 Key 账本中已启用的 DeepSeek 和火山方舟配置，不复制、不改动它们的 Key）</p>
      <p id="ribbon-inherited-status" role="status" aria-live="polite"></p>
      <label><input id="ribbon-enabled" type="checkbox"> 启用丝带 AI 底图和精修</label>
      <p class="muted">启用后，员工每使用一次底图或精修会按实际调用计费（Seedream 按图、DeepSeek 按用量）。关闭后首稿排版照常可用，不产生费用。保存设置本身不会调用模型。</p>
      <p id="ribbon-settings-state" role="status" aria-live="polite"></p>
      <div style="display:flex;gap:10px;margin-top:12px"><button type="submit" class="button primary">保存</button><button type="button" id="ribbon-settings-reload" class="button secondary">重新读取</button></div>
      <p class="muted">员工共用主机设置，不需要填写 Key。真实接口效果仍需用实际样图确认。</p>
    </form></details>`;
  const $ = id => root.querySelector(`#${id}`);
  const ROUTE = 'deepseek_seedream';
  let revision = null, busy = false, locked = false, epoch = 0;
  const message = (text, error = false) => {
    $('ribbon-settings-state').textContent = text;
    $('ribbon-settings-state').classList.toggle('error', error);
  };
  function controls() {
    root.querySelectorAll('input,button').forEach(el => {
      el.disabled = busy || locked || (revision === null && el.id !== 'ribbon-settings-reload');
    });
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
    const language = data.inherited_language_model || '未配置';
    const image = data.inherited_image_model || '未配置';
    $('ribbon-inherited-status').textContent = ready
      ? `已就绪：语言模型 ${language}，图片模型 ${image}。` :
      '现有 DeepSeek 或火山方舟配置不完整（需要已启用 + 至少一把可用 Key + 模型 ID），请先在 Key 账本补齐。';
    if (data.provider !== ROUTE) {
      message('当前保存的是另一条路线，本页只维护 DeepSeek＋Seedream；保存即切回这条路线。', true);
      return;
    }
    message(data.warning || (data.enabled && data.configured ? '已启用；真实效果仍需样图确认。' : '未启用：首稿排版可用，AI 底图与精修不可用。'));
  }
  async function load() {
    if (busy || locked) return;
    busy = true; controls(); const ticket = ++epoch;
    try { const data = await request(); if (ticket === epoch) display(data); }
    catch (error) { if (ticket === epoch) message(error.message, true); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  $('ribbon-settings-details').addEventListener('toggle', () => {
    if ($('ribbon-settings-details').open && revision === null) load();
  });
  $('ribbon-settings-reload').addEventListener('click', load);
  document.getElementById('admin-refresh')?.addEventListener('click', () => {
    if ($('ribbon-settings-details').open) load();
  });
  document.getElementById('admin-logout')?.addEventListener('click', () => {
    epoch++; locked = true; busy = false; controls();
  });
  window.addEventListener('pagehide', () => { epoch++; });
  document.querySelectorAll('.admin-nav-item').forEach(link => link.addEventListener('click', () => {
    if (link.getAttribute('href') !== '#keys') $('ribbon-settings-details').open = false;
  }));
  $('ribbon-settings-form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || locked || revision === null) return;
    const body = {expected_revision: revision, provider: ROUTE, enabled: $('ribbon-enabled').checked};
    busy = true; controls(); const ticket = ++epoch; message('正在保存…');
    try { const data = await request(body); if (ticket === epoch) display(data); }
    catch (error) { if (ticket === epoch) message(error.message, true); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  });
  controls();
  // Rendered expanded so the block is visible on the ledger page instead of
  // hiding behind a summary; the toggle handler covers later collapses.
  if ($("ribbon-settings-details").open) load();
})();
