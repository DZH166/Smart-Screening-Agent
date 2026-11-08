'use strict';
/** Ribbon image settings. Writes stay revision-bound; a restored page rereads. */
(() => {
  const $ = id => document.getElementById(id);
  if (!$('ribbon-form')) return;
  const ROUTE = 'deepseek_seedream';
  let revision = null, busy = false, locked = false, suspended = false, epoch = 0, committedEnabled = false;
  const controllers = new Set();
  const current = ticket => ticket === epoch && !suspended;
  const message = (text, error = false) => {
    const node = $('ribbon-message');
    node.textContent = text;
    node.classList.toggle('hidden', !text);
    node.classList.toggle('error', error);
  };
  const status = text => { $('ribbon-model-state').textContent = text; };
  function hideModel() {
    $('ribbon-model').type = 'password';
    $('ribbon-model-reveal').textContent = '显示';
    $('ribbon-model-reveal').setAttribute('aria-pressed', 'false');
  }
  function clearInput() { $('ribbon-key').value = ''; hideModel(); }
  function controls() {
    const disabled = busy || locked || suspended || revision === null;
    ['ribbon-key', 'ribbon-model', 'ribbon-save', 'ribbon-remove',
     'ribbon-model-reveal', 'ribbon-model-copy', 'ribbon-enabled', 'ribbon-enable-save'].forEach(id => {
      if ($(id)) $(id).disabled = disabled || (id === 'ribbon-remove' && $('ribbon-remove').dataset.own !== '1');
    });
    $('ribbon-refresh').disabled = busy || suspended;
  }
  async function request(body, ticket) {
    const controller = new AbortController();
    controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/admin/ribbon-settings', {
        method: body ? 'POST' : 'GET', cache: 'no-store', credentials: 'same-origin', signal: controller.signal,
        headers: {'X-HSD-Token': window.HSD_TOKEN || '', ...(body ? {'Content-Type': 'application/json'} : {})},
        ...(body ? {body: JSON.stringify(body)} : {})});
      const data = await response.json().catch(() => ({}));
      if (!current(ticket)) { const error = new Error('页面已离开。'); error.obsolete = true; throw error; }
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          locked = true; revision = null; clearInput();
          $('ribbon-login').classList.remove('hidden');
        }
        const error = new Error(response.status === 409 ? '其他页面已更新配置，请刷新设置后重新保存。' :
          data.error || data.detail || '设置未完成，请重新登录或重试。');
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (!current(ticket)) error.obsolete = true;
      if (error.obsolete) throw error;
      if (error.name === 'AbortError') { const timeout = new Error('请求超时，请刷新设置核对结果。'); timeout.status = 408; throw timeout; }
      throw error;
    } finally { clearTimeout(timer); controllers.delete(controller); }
  }
  function display(data) {
    if (!data || !Number.isSafeInteger(data.revision) || data.revision < 0 ||
        typeof data.enabled !== 'boolean' || typeof data.ark_model !== 'string' || typeof data.ark_configured !== 'boolean')
      throw new Error('设置结果格式异常，请刷新设置后核对。');
    revision = data.revision;
    committedEnabled = !!data.enabled;
    $('ribbon-enabled').checked = committedEnabled;
    $('ribbon-model').value = data.ark_model || '';
    hideModel();
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
    if (busy || suspended) return;
    busy = true; clearInput(); controls(); const ticket = ++epoch;
    try {
      const data = await request(undefined, ticket);
      if (current(ticket)) { locked = false; $('ribbon-login').classList.add('hidden'); display(data); }
    } catch (error) { if (current(ticket) && !error.obsolete) message(error.message, true); }
    finally { if (current(ticket)) { busy = false; controls(); } }
  }
  function failedWrite(error, ticket) {
    if (!current(ticket) || error.obsolete) return;
    $('ribbon-enabled').checked = committedEnabled;
    if (![400,422].includes(error.status)) revision = null;
    message(error.status ? error.message : '保存结果未确认，请刷新设置核对后重试。', true);
  }
  async function save() {
    if (busy || locked || suspended || revision === null) return;
    const body = {expected_revision: revision, provider: ROUTE, ark_model: $('ribbon-model').value.trim()};
    const key = $('ribbon-key').value.trim();
    if (key) body.ark_api_key = key;
    clearInput(); busy = true; controls(); const ticket = ++epoch; message('正在保存…');
    try {
      const data = await request(body, ticket);
      if (current(ticket)) { display(data); message(data.warning || '配置已保存。', !!data.warning); }
    } catch (error) { failedWrite(error, ticket); }
    finally { delete body.ark_api_key; if (current(ticket)) { busy = false; controls(); } }
  }
  async function remove() {
    if (busy || locked || suspended || revision === null) return;
    clearInput(); busy = true; controls(); const ticket = ++epoch; message('正在删除…');
    try {
      const data = await request({expected_revision: revision, provider: ROUTE, clear_ark_key: true}, ticket);
      if (current(ticket)) { display(data); message(data.warning || '已删除丝带专用配置，回到沿用素材提取。', !!data.warning); }
    } catch (error) { failedWrite(error, ticket); }
    finally { if (current(ticket)) { busy = false; controls(); } }
  }
  async function toggle(event) {
    event.preventDefault();
    if (busy || locked || suspended || revision === null) return;
    busy = true; controls(); const ticket = ++epoch;
    try {
      const data = await request({expected_revision: revision, provider: ROUTE, enabled: $('ribbon-enabled').checked}, ticket);
      if (current(ticket)) { display(data); message(data.warning || '开关已保存。', !!data.warning); }
    } catch (error) { failedWrite(error, ticket); }
    finally { if (current(ticket)) { busy = false; controls(); } }
  }
  $('ribbon-form').addEventListener('submit', event => { event.preventDefault(); save(); });
  $('ribbon-remove').addEventListener('click', remove);
  $('ribbon-enable-form').addEventListener('submit', toggle);
  $('ribbon-refresh').addEventListener('click', load);
  $('ribbon-model-reveal').addEventListener('click', () => {
    if (busy || locked || suspended || revision === null) return;
    const show = $('ribbon-model').type === 'password';
    $('ribbon-model').type = show ? 'text' : 'password';
    $('ribbon-model-reveal').textContent = show ? '隐藏' : '显示';
    $('ribbon-model-reveal').setAttribute('aria-pressed', String(show));
  });
  $('ribbon-model-copy').addEventListener('click', async () => {
    if (busy || locked || suspended || revision === null) return;
    const value = $('ribbon-model').value, ticket = epoch;
    if (!value) return message('还没有填写丝带专用模型 ID。', true);
    try { await navigator.clipboard.writeText(value); if (current(ticket) && !locked) message('模型 ID 已复制。'); }
    catch (_) { if (current(ticket) && !locked) message('浏览器未允许复制，请显示后手动复制。', true); }
  });
  window.addEventListener('pagehide', () => {
    epoch++; suspended = true; locked = true; busy = false; revision = null;
    clearInput(); controllers.forEach(controller => controller.abort()); controls();
  });
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    epoch++; suspended = false; locked = false; busy = false; revision = null;
    clearInput(); $('ribbon-login').classList.add('hidden'); load();
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) hideModel(); });
  controls();
  load();
})();
