'use strict';
/**
 * 丝带设计 · 模型配置
 *
 * The ribbon workspace may reuse the material tool's 火山方舟 key/model, or hold
 * its own copy. Empty fields mean "inherit"; saving both fields switches this
 * workspace to its own configuration, deleting them switches back. DeepSeek is
 * always the shared pool and is configured on /admin/deepseek.
 */
(() => {
  const $ = id => document.getElementById(id);
  if (!$('ribbon-form')) return;
  const ROUTE = 'deepseek_seedream';
  let revision = null, busy = false, locked = false, epoch = 0;
  const message = (text, error = false) => {
    const node = $('ribbon-message');
    node.textContent = text;
    node.classList.toggle('hidden', !text);
    node.classList.toggle('error', error);
  };
  const status = text => { $('ribbon-model-state').textContent = text; };
  function controls() {
    const disabled = busy || locked || revision === null;
    ['ribbon-key', 'ribbon-model', 'ribbon-save', 'ribbon-remove',
     'ribbon-model-reveal', 'ribbon-model-copy', 'ribbon-enabled', 'ribbon-enable-save'].forEach(id => {
      if ($(id)) $(id).disabled = disabled || (id === 'ribbon-remove' && $('ribbon-remove').dataset.own !== '1');
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
    $('ribbon-model').value = data.ark_model || '';
    const own = !!data.ark_configured;
    const inheritedModel = data.inherited_image_model || '未配置';
    status(own
      ? `使用丝带专用配置 · 图片模型 ${data.ark_model || '未填写'} · ${data.enabled ? '已启用' : '未启用'}`
      : `沿用素材提取的配置 · 图片模型 ${inheritedModel} · ${data.enabled ? '已启用' : '未启用'}`);
    $('ribbon-key-value').textContent = own ? '已保存丝带专用 Key' : '未保存丝带专用 Key（沿用素材提取）';
    $('ribbon-remove').dataset.own = own ? '1' : '0';
    controls();
    message(data.warning || '');
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
    const body = {expected_revision: revision, provider: ROUTE, ark_model: $('ribbon-model').value.trim()};
    const key = $('ribbon-key').value.trim();
    if (key) body.ark_api_key = key;
    busy = true; controls(); const ticket = ++epoch; message('正在保存…');
    try {
      const data = await request(body);
      $('ribbon-key').value = '';
      if (ticket === epoch) { message('配置已保存。'); display(data); }
    } catch (error) {
      if (ticket === epoch) message(error.message, true);
    } finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  async function remove() {
    if (busy || locked || revision === null) return;
    busy = true; controls(); const ticket = ++epoch; message('正在删除…');
    try {
      const data = await request({expected_revision: revision, provider: ROUTE, clear_ark_key: true});
      if (ticket === epoch) { message('已删除丝带专用配置，回到沿用素材提取。'); display(data); }
    } catch (error) {
      if (ticket === epoch) message(error.message, true);
    } finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  async function toggle(event) {
    event.preventDefault();
    if (busy || locked || revision === null) return;
    busy = true; controls(); const ticket = ++epoch;
    try {
      const data = await request({expected_revision: revision, provider: ROUTE, enabled: $('ribbon-enabled').checked});
      if (ticket === epoch) { message('开关已保存。'); display(data); }
    } catch (error) {
      if (ticket === epoch) message(error.message, true);
    } finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  $('ribbon-form').addEventListener('submit', event => { event.preventDefault(); save(); });
  $('ribbon-remove').addEventListener('click', remove);
  $('ribbon-enable-form').addEventListener('submit', toggle);
  $('ribbon-refresh').addEventListener('click', load);
  $('ribbon-model-reveal').addEventListener('click', () => {
    const input = $('ribbon-model');
    input.type = input.type === 'password' ? 'text' : 'password';
    $('ribbon-model-reveal').textContent = input.type === 'password' ? '显示' : '隐藏';
    $('ribbon-model-reveal').setAttribute('aria-pressed', String(input.type === 'text'));
  });
  $('ribbon-model-copy').addEventListener('click', async () => {
    const value = $('ribbon-model').value;
    if (!value) return message('还没有填写丝带专用模型 ID。', true);
    try { await navigator.clipboard.writeText(value); message('模型 ID 已复制。'); }
    catch (_) { message('浏览器未允许复制，请显示后手动复制。', true); }
  });
  window.addEventListener('pagehide', () => { epoch++; });
  document.addEventListener('visibilitychange', () => { if (document.hidden) $('ribbon-model').type = 'password'; });
  controls();
  load();
})();
