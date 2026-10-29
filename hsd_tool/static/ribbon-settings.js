'use strict';
(() => {
  const root = document.getElementById('ribbon-settings-panel');
  if (!root) return;
  root.innerHTML = `<details id="ribbon-settings-details"><summary>丝带设计 · 模型服务</summary>
    <form id="ribbon-settings-form" class="help-content">
      <p>仅影响丝带设计。首稿用原素材排版；AI 底图和文字精修使用下面选择的服务。</p>
      <label>调用路线 <select id="ribbon-provider"><option value="deepseek_seedream">DeepSeek ＋ Seedream（沿用现有配置）</option><option value="openai">OpenAI（独立配置）</option></select></label>
      <p id="ribbon-inherited-status"></p>
      <fieldset id="ribbon-openai-fields" hidden style="border:0;padding:0;margin:12px 0;display:grid;gap:12px">
        <label>OpenAI API Key <input id="ribbon-openai-key" type="password" autocomplete="new-password" placeholder="留空保留已存 Key" maxlength="512"></label>
        <label>语言模型 ID <span style="display:flex;gap:8px"><input id="ribbon-language-model" type="password" autocomplete="off" maxlength="128" placeholder="填写账号可调用的语言模型"><button type="button" class="button secondary" data-reveal="ribbon-language-model">显示</button><button type="button" class="button secondary" data-copy="ribbon-language-model">复制</button></span></label>
        <label>图片模型 ID <span style="display:flex;gap:8px"><input id="ribbon-image-model" type="password" autocomplete="off" maxlength="128" placeholder="填写支持图片编辑的模型"><button type="button" class="button secondary" data-reveal="ribbon-image-model">显示</button><button type="button" class="button secondary" data-copy="ribbon-image-model">复制</button></span></label>
        <label>图像质量 <select id="ribbon-image-quality"><option value="high">高</option><option value="medium">中</option><option value="low">低</option><option value="auto">模型自动选择</option></select></label>
        <label><input id="ribbon-clear-key" type="checkbox"> 删除已保存的 OpenAI Key</label>
      </fieldset>
      <label><input id="ribbon-enabled" type="checkbox"> 启用丝带 AI 底图和精修</label>
      <p id="ribbon-settings-state" role="status" aria-live="polite"></p>
      <div style="display:flex;gap:10px;margin-top:12px"><button type="submit" class="button primary">保存</button><button type="button" id="ribbon-settings-reload" class="button secondary">重新读取</button></div>
      <p class="muted">员工共用主机设置，不需要填写 Key。保存不会调用模型，也不代表接口已验证。</p>
    </form></details>`;
  const $ = id => root.querySelector(`#${id}`);
  let revision = null, busy = false, locked = false, epoch = 0;
  const message = (text, error = false) => { $('ribbon-settings-state').textContent = text; $('ribbon-settings-state').classList.toggle('error', error); };
  function clear() {
    $('ribbon-openai-key').value = ''; $('ribbon-clear-key').checked = false;
    root.querySelectorAll('[data-reveal]').forEach(button => { $(button.dataset.reveal).type = 'password'; button.textContent = '显示'; });
  }
  function mode() {
    const openai = $('ribbon-provider').value === 'openai';
    $('ribbon-openai-fields').hidden = !openai;
    $('ribbon-openai-fields').style.display = openai ? 'grid' : 'none';
    $('ribbon-inherited-status').hidden = openai;
  }
  function controls() { root.querySelectorAll('input,select,button').forEach(el => { el.disabled = busy || locked || revision === null && el.id !== 'ribbon-settings-reload'; }); }
  async function request(body) {
    const response = await fetch('/api/admin/ribbon-settings', {method:body ? 'POST':'GET', cache:'no-store', credentials:'same-origin', headers:{'X-HSD-Token':window.HSD_TOKEN || '', ...(body ? {'Content-Type':'application/json'}:{})}, ...(body ? {body:JSON.stringify(body)}:{})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) { locked = true; clear(); }
      throw new Error(data.error || data.detail || '设置未完成，请重新登录或重试。');
    }
    return data;
  }
  function display(data) {
    revision = data.revision;
    $('ribbon-provider').value = data.provider;
    $('ribbon-language-model').value = data.language_model || '';
    $('ribbon-image-model').value = data.image_model || '';
    $('ribbon-image-quality').value = data.image_quality || 'high';
    $('ribbon-enabled').checked = !!data.enabled;
    $('ribbon-openai-key').placeholder = data.openai_configured ? '已保存，留空保留' : '粘贴 OpenAI API Key';
    $('ribbon-inherited-status').textContent = data.inherited_ready ? '现有 DeepSeek 与火山方舟配置可使用；不会改动原功能的开关。' : '请先在 Key 账本中配置并启用 DeepSeek 与火山方舟，之后再使用这条路线。';
    clear(); mode();
    message(data.warning || (data.enabled && data.configured ? '配置已保存；真实接口效果仍需测试。' : '确定性首稿可用。AI 功能需配置并启用服务。'));
  }
  async function load() {
    if (busy || locked) return;
    busy = true; controls(); const ticket = ++epoch;
    try { const data = await request(); if (ticket === epoch) display(data); }
    catch (error) { if (ticket === epoch) message(error.message, true); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  $('ribbon-settings-details').addEventListener('toggle', () => { if ($('ribbon-settings-details').open && revision === null) load(); else if (!$('ribbon-settings-details').open) clear(); });
  $('ribbon-provider').addEventListener('change', () => {clear(); mode();});
  $('ribbon-settings-reload').addEventListener('click', load);
  document.getElementById('admin-refresh')?.addEventListener('click', () => {if ($('ribbon-settings-details').open) load();});
  document.getElementById('admin-logout')?.addEventListener('click', () => {epoch++;locked=true;busy=false;clear();controls();});
  window.addEventListener('pagehide', () => {epoch++;clear();});
  document.addEventListener('visibilitychange', () => {if (document.hidden) clear();});
  document.querySelectorAll('.admin-nav-item').forEach(link => link.addEventListener('click', () => {if (link.getAttribute('href') !== '#keys') {clear();$('ribbon-settings-details').open=false;}}));
  root.querySelectorAll('[data-reveal]').forEach(button => button.addEventListener('click', () => {const input=$(button.dataset.reveal);input.type=input.type==='password'?'text':'password';button.textContent=input.type==='password'?'显示':'隐藏';}));
  root.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {try {const value=$(button.dataset.copy).value;if (!value) return message('尚未填写模型 ID。');await navigator.clipboard.writeText(value);message('模型 ID 已复制。');}catch (_) {message('浏览器未允许复制，请显示后手动复制。',true);}}));
  $('ribbon-settings-form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || locked || revision === null) return;
    const body = {expected_revision:revision,provider:$('ribbon-provider').value,enabled:$('ribbon-enabled').checked,
      language_model:$('ribbon-language-model').value.trim(),image_model:$('ribbon-image-model').value.trim(),image_quality:$('ribbon-image-quality').value,
      api_key:$('ribbon-openai-key').value,clear_key:$('ribbon-clear-key').checked};
    clear(); busy=true;controls();const ticket=++epoch;message('正在保存…');
    try {const data=await request(body);if(ticket===epoch)display(data);}
    catch (error) {if(ticket===epoch)message(error.message,true);}
    finally {body.api_key='';if(ticket===epoch){busy=false;controls();}}
  });
  mode(); controls();
})();
