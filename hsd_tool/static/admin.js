'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {settings:null, pool:{keys:[]}, loading:false, saving:false, refreshing:false, conflict:false,
    keysSignature:'', timer:null, polling:false, stopped:false, enableDirty:false, locked:false,
    epoch:0, ledgerEpoch:0, ledgerLoading:false, loggingOut:false, suspended:false, authLost:false};
  const controllers = new Set();
  const statuses = {ready:['可用','ok'],available:['可用','ok'],active:['调用中','ok'],busy:['调用中','ok'],
    cooldown:['冷却中','warning'],rate_limited:['限流冷却中','warning'],disabled:['已停用',''],invalid:['密钥不可用','error'],
    service_disabled:['AI 已关闭',''],paused_authentication:['认证失败，已暂停','error'],paused_insufficient_balance:['余额不足，已暂停','error'],
    unauthorized:['密钥不可用','error'],unavailable:['暂不可用','warning'],failed:['调用失败','error'],idle:['待调用','']};

  function message(text, error = false) {
    $('admin-message').textContent = text;
    $('admin-message').classList.toggle('hidden', !text);
    $('admin-message').classList.toggle('error', error);
  }

  function clearLedger() {
    state.ledgerEpoch += 1; state.ledgerLoading = false;
    // Remove data-value attributes as well as visible text; masking alone retains secrets.
    $('ledger-list').replaceChildren();
    $('ledger-state').textContent = '';
  }

  function clearSecrets() {
    clearLedger(); $('ledger-details').open = false;
    $('key-batch').value = ''; $('key-batch').classList.remove('key-plain');
    $('key-reveal').textContent = '显示'; $('key-reveal').setAttribute('aria-pressed','false');
  }

  function lockPage(text, authLost = true) {
    state.locked = true; state.stopped = true; state.epoch += 1;
    state.loading = false; state.saving = false; state.refreshing = false; state.polling = false;
    state.authLost = state.authLost || authLost;
    stopPolling(); clearSecrets();
    controllers.forEach((controller)=>controller.abort());
    $('admin-login').classList.toggle('hidden', !authLost);
    if (text) message(text,true);
    controls();
  }

  async function request(path, payload, allowLocked = false) {
    if (state.locked && !allowLocked) { const error = new Error('请重新登录。'); error.obsolete = true; throw error; }
    const epoch = state.epoch;
    const controller = new AbortController();
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method:payload === undefined ? 'GET' : 'POST',
        headers:{'X-HSD-Token':window.HSD_TOKEN || '',...(payload === undefined ? {} : {'Content-Type':'application/json'})},
        body:payload === undefined ? undefined : JSON.stringify(payload),cache:'no-store',signal:controller.signal});
      if (epoch !== state.epoch) { const error = new Error('页面状态已变化。'); error.obsolete = true; throw error; }
      if (response.status === 401 || response.status === 403) {
        const text = response.status === 401 ? '登录已过期，请重新登录。' : '管理员权限或页面凭证已失效，请重新登录。';
        lockPage(text);
        const error = new Error(text); error.status = response.status; error.obsolete = true; throw error;
      }
      const result = await response.json();
      if (epoch !== state.epoch) { const error = new Error('页面状态已变化。'); error.obsolete = true; throw error; }
      if (!response.ok) {
        const error = new Error(result.error || '管理服务暂不可用，请稍后重试。');
        error.status = response.status;
        throw error;
      }
      return result;
    } catch (error) {
      if (epoch !== state.epoch) error.obsolete = true;
      if (error.obsolete) throw error;
      if (error.name === 'AbortError') throw new Error('请求超时，请刷新设置确认结果。');
      if (error instanceof TypeError) throw new Error('暂时无法连接主机工具，请稍后重试。');
      throw error;
    } finally { clearTimeout(timeout); controllers.delete(controller); }
  }

  function isEnvironment(key) { return /^(environment|env)$/i.test(String(key.source || '')); }
  function keyStats(key) {
    const status = key.enabled === false ? ['已停用',''] : key.status === 'available' && !Number(key.requests) ? ['待验证',''] : statuses[key.status] || ['待验证',''];
    const cooldown = Number(key.cooldown_seconds || 0);
    const note = cooldown > 0 ? `冷却剩余约 ${Math.ceil(cooldown)} 秒` :
      key.status === 'paused_authentication' ? '请检查 Key，修复后先停用再启用。' :
      key.status === 'paused_insufficient_balance' ? '请在 DeepSeek 补充余额后，先停用再启用。' : '';
    return {status,note};
  }

  function keyHtml(key) {
    const stats = keyStats(key), environment = isEnvironment(key);
    return `<article class="key-card" data-key-id="${escapeHtml(key.id)}"><div class="key-heading"><div class="key-name"><span>${escapeHtml(key.label || '未命名密钥')}</span><span class="badge ${stats.status[1]}" data-key-status>${stats.status[0]}</span>${environment ? '<span class="badge">环境变量</span>' : ''}</div><div class="key-actions">${environment ? '' : '<button type="button" class="button quiet" data-action="rename">改标签</button>'}<button type="button" class="button secondary" data-action="toggle">${key.enabled === false ? '启用' : '停用'}</button>${environment ? '' : '<button type="button" class="button quiet" data-action="remove">删除</button>'}</div></div><p class="key-note${stats.note ? '' : ' hidden'}" data-key-note>${escapeHtml(stats.note)}</p>${environment ? '<p class="muted">来自主机环境变量；修改或删除请在主机操作。</p>' : ''}<form class="key-edit hidden" data-rename-form><label>密钥标签</label><input type="text" maxlength="64" autocomplete="off" aria-label="密钥标签" value="${escapeHtml(key.label || '')}"><button type="submit" class="button secondary">保存标签</button><button type="button" class="button quiet" data-action="cancel-rename">取消</button></form><div class="key-delete hidden" data-delete-prompt><p>确认删除此 Key？新请求将不再使用它。</p><button type="button" class="button danger" data-action="confirm-remove">确认删除</button><button type="button" class="button quiet" data-action="cancel-remove">取消</button></div></article>`;
  }

  function currentKeys() {
    const runtime = new Map((state.pool.keys || []).map((key) => [key.id,key]));
    return (state.settings?.keys || []).map((key) => ({...key,...runtime.get(key.id)}));
  }

  function controls() {
    const locked = state.locked || state.loading || state.saving || !state.settings || state.conflict;
    ['ai-enabled','enable-save','key-batch','key-add','key-reveal'].forEach((id) => $(id).disabled = locked);
    $('admin-refresh').disabled = state.locked || state.loading || state.saving || state.refreshing;
    $('admin-logout').disabled = state.loggingOut;
    $('admin-logout').textContent = state.loggingOut ? '正在退出…' : '退出登录';
    $('ledger-refresh').disabled = state.locked || state.ledgerLoading;
    $('admin-refresh').textContent = state.refreshing ? '刷新中…' : '刷新设置';
    $('key-add').textContent = state.saving ? '正在保存…' : '添加 Key';
    $('key-list').querySelectorAll('button,input').forEach((node) => node.disabled = locked);
  }

  function renderKeys() {
    const keys = currentKeys();
    $('key-count').textContent = `（${keys.length} 个）`;
    const signature = JSON.stringify(keys.map(({id,label,enabled,source}) => ({id,label,enabled,source})));
    if (signature !== state.keysSignature) {
      state.keysSignature = signature;
      $('key-list').innerHTML = keys.length ? keys.map(keyHtml).join('') : '<p class="empty">尚未配置 Key，可在上方批量添加。</p>';
    } else {
      // Status refreshes preserve label inputs, focus and open confirmations.
      const byId = new Map(keys.map((key) => [key.id,key]));
      $('key-list').querySelectorAll('[data-key-id]').forEach((card) => {
        const key = byId.get(card.dataset.keyId);
        if (!key) return;
        const stats = keyStats(key), status = card.querySelector('[data-key-status]');
        status.textContent = stats.status[0]; status.className = `badge ${stats.status[1]}`;
        const note = card.querySelector('[data-key-note]');
        note.textContent = stats.note; note.classList.toggle('hidden', !stats.note);
      });
    }
    controls();
  }

  function applySettings(settings) {
    state.settings = settings;
    if (!state.enableDirty) $('ai-enabled').checked = settings.enabled === true;
    $('settings-state').textContent = !settings.enabled ? '图号助手使用本机匹配；素材提取需启用 DeepSeek。' : settings.configured ? '已启用，导入后自动运行。' : '请添加并启用 Key，才能使用 AI。';
    $('qualification-state').textContent = settings.mode === 'validated' ? '当前 AI 复核已通过使用验证；只有符合全部条件的结果才可自动通过，其余仍需人工确认。' : '当前 AI 复核建议仍需人工确认。AI 找到的图片只有通过系统独立核对，才能自动通过；增加 Key 不会放宽要求。';
    $('persistence-state').textContent = settings.key_persistence === 'windows_dpapi' ? 'Key 加密保存在这台电脑的当前 Windows 用户下，重启后可继续使用。' : settings.key_persistence === 'linux_aesgcm' ? 'Key 加密保存在服务器上，员工不用重新填写。' : '当前环境只在本次运行期间保留 Key，重启后需重新填写。';
    $('storage-warning').textContent = settings.storage_warning || '';
    $('storage-warning').classList.toggle('hidden', !settings.storage_warning);
  }

  async function refreshOverview(manual = false) {
    if (state.locked || state.refreshing || state.loading || state.saving) return;
    const epoch = state.epoch;
    const revision = state.settings?.key_revision;
    const blocking = manual || !state.settings;
    state.refreshing = true; if (blocking) state.loading = true; controls();
    try {
      const result = await request('/api/admin/keys');
      // A background read must not replace a mutation that started or finished meanwhile.
      if (state.saving || (!manual && state.settings?.key_revision !== revision)) return;
      if (manual || !state.settings) {
        state.conflict = false; state.enableDirty = false; applySettings(result.settings);
      } else if (result.settings?.key_revision !== state.settings.key_revision) {
        state.conflict = true;
        clearLedger();
        message('配置已在其他页面更新。请刷新设置，核对后再修改。',true);
        return;
      }
      state.pool = result.pool || {keys:[]}; renderKeys();
      if (manual) { state.stopped = false; message('已读取最新设置。'); clearLedger(); loadLedger(); }
    } catch (error) {
      if (!error.obsolete) message(error.message,true);
    } finally { if (epoch === state.epoch) { state.refreshing = false; if (blocking) state.loading = false; } controls(); }
  }

  async function mutateKeys(change) {
    if (state.locked || state.saving || state.loading || state.conflict || !state.settings) return;
    const epoch = state.epoch;
    state.saving = true; clearLedger(); controls(); message('');
    const payload = {...change,expected_revision:state.settings.key_revision};
    try {
      const result = await request('/api/admin/keys',payload);
      applySettings(result.settings); state.pool = result.pool || {keys:[]}; renderKeys();
      message('已保存 Key，接口将在处理任务时验证。');
      loadLedger();
    } catch (error) {
      if (error.obsolete) return;
      if (error.status === 409) { state.conflict = true; message('其他页面已修改密钥配置。请刷新设置，核对后再修改；本次未保存。',true); }
      else message(error.message || '配置未保存，请稍后重试。',true);
    } finally {
      for (const key of payload.add || []) delete key.api_key;
      if (epoch === state.epoch) { $('key-batch').value = ''; state.saving = false; }
      controls();
    }
  }

  async function addKeys(event) {
    event.preventDefault();
    const text = $('key-batch').value;
    // Clear before validation and before the first asynchronous operation.
    $('key-batch').value = '';
    const values = text.split(/\r?\n/).map((line)=>line.trim()).filter(Boolean);
    if (!values.length) { message('请每行填写一个 API Key。',true); return; }
    if (values.length > 100) { message('一次最多添加 100 个 Key，请分批添加。输入已清空。',true); return; }
    if (values.some((value)=>value.length < 10 || value.length > 512 || !/^[\x21-\x7e]+$/.test(value))) { message('存在格式不正确的 Key，请检查空格、长度或不可见字符后重新填写。输入已清空。',true); return; }
    const labels = new Set((state.settings?.keys || []).map((key)=>key.label));
    let index = 1;
    const add = values.map((api_key)=>{while(labels.has(`密钥 ${index}`)) index++; const label=`密钥 ${index++}`; labels.add(label); return {label,api_key};});
    await mutateKeys({add});
    // Do not retain a second reference to submitted secret strings in callbacks.
    add.forEach((key)=>delete key.api_key); values.fill('');
  }

  async function saveEnabled(event) {
    event.preventDefault();
    if (state.locked || state.saving || state.loading || !state.settings || state.conflict) return;
    const epoch = state.epoch;
    const enabled = $('ai-enabled').checked;
    let saved = false;
    state.saving = true; controls(); message('');
    try {
      state.enableDirty = false;
      const result = await request('/api/admin/settings',{enabled,expected_revision:state.settings.key_revision});
      applySettings(result.settings);
      $('ai-enabled').checked = state.settings.enabled === true;
      // Pool health was measured before this switch changed. Do not present it as current.
      state.pool = {keys:[]}; renderKeys();
      saved = true; message('AI 开关已保存。');
    }
    catch (error) {
      if (error.obsolete) return;
      if (error.status === 409) {
        state.conflict = true; state.enableDirty = true;
        message((error.message || '设置已在其他页面更新。') + ' 本次未保存，请点击“刷新设置”核对。',true);
      } else {
        $('ai-enabled').checked = state.settings.enabled === true;
        message(error.message || '设置结果未确认，请刷新设置后重试。',true);
      }
    }
    finally { if (epoch === state.epoch) state.saving = false; controls(); }
    if (saved) await refreshOverview(false);
  }

  function keyAction(event) {
    const button = event.target.closest('[data-action]'), card = button?.closest('[data-key-id]');
    if (!button || !card || state.locked || state.saving || state.loading || state.conflict) return;
    const key = currentKeys().find((item)=>item.id === card.dataset.keyId);
    if (!key) return;
    const action = button.dataset.action;
    if (action === 'toggle') { mutateKeys({update:[{id:key.id,enabled:key.enabled === false}]}); return; }
    if (isEnvironment(key)) return;
    if (action === 'rename' || action === 'cancel-rename') { card.querySelector('[data-rename-form]').classList.toggle('hidden',action === 'cancel-rename'); if (action === 'rename') card.querySelector('input').focus(); }
    if (action === 'remove' || action === 'cancel-remove') card.querySelector('[data-delete-prompt]').classList.toggle('hidden',action === 'cancel-remove');
    if (action === 'confirm-remove') mutateKeys({remove:[key.id]});
  }

  function renameKey(event) {
    const form = event.target.closest('[data-rename-form]');
    if (!form) return;
    event.preventDefault();
    const card = form.closest('[data-key-id]'), label = form.querySelector('input').value.trim();
    if (!label) { message('请填写便于辨认的密钥标签。',true); form.querySelector('input').focus(); return; }
    mutateKeys({update:[{id:card.dataset.keyId,label}]});
  }

  function maskKey(value) {
    return value ? '••••••••' : '';
  }

  function ledgerHtml(key) {
    return `<div class="ledger-row" data-ledger-id="${escapeHtml(key.id)}"><span class="ledger-label">${escapeHtml(key.label || '未命名')}</span><code class="ledger-key" data-value="${escapeHtml(key.api_key || '')}" data-shown="false">${escapeHtml(maskKey(key.api_key || ''))}</code><span class="badge">${isEnvironment(key) ? '环境变量' : '主机保存'}</span><button type="button" class="button quiet" data-reveal>显示</button><button type="button" class="button quiet" data-copy>复制</button></div>`;
  }

  async function loadLedger() {
    if (state.locked || !$('ledger-details').open || state.ledgerLoading) return;
    const stateLine = $('ledger-state'), list = $('ledger-list');
    clearLedger();
    const version = state.ledgerEpoch;
    state.ledgerLoading = true; stateLine.textContent = '正在读取…'; controls();
    try {
      const payload = await request('/api/admin/ledger');
      if (state.locked || version !== state.ledgerEpoch || !$('ledger-details').open) return;
      const keys = Array.isArray(payload.keys) ? payload.keys : [];
      list.innerHTML = keys.length ? keys.map(ledgerHtml).join('') : '<p class="empty">暂未添加 Key。</p>';
      stateLine.textContent = keys.length ? `${keys.length} 个` : '';
    } catch (error) {
      if (!error.obsolete && version === state.ledgerEpoch) stateLine.textContent = '读取失败，请点击“重新读取”重试。';
    } finally { if (version === state.ledgerEpoch) { state.ledgerLoading = false; controls(); } }
  }

  function ledgerClick(event) {
    if (state.locked || !$('ledger-details').open) return;
    const row = event.target.closest('[data-ledger-id]');
    const code = row?.querySelector('.ledger-key');
    if (!code) return;
    if (event.target.closest('[data-reveal]')) {
      const shown = code.dataset.shown === 'true';
      code.textContent = shown ? maskKey(code.dataset.value) : (code.dataset.value || '');
      code.dataset.shown = String(!shown);
      event.target.closest('[data-reveal]').textContent = shown ? '显示' : '隐藏';
      return;
    }
    if (event.target.closest('[data-copy]')) {
      const button = event.target.closest('[data-copy]');
      if (!navigator.clipboard?.writeText) { message('当前浏览器无法复制，请显示 Key 后手动复制。',true); return; }
      const version = state.ledgerEpoch;
      navigator.clipboard.writeText(code.dataset.value || '').then(() => {
        if (state.locked || version !== state.ledgerEpoch) return;
        button.textContent = '已复制';
        setTimeout(() => { if (version === state.ledgerEpoch) button.textContent = '复制'; }, 1200);
      }).catch(() => { if (!state.locked && version === state.ledgerEpoch) button.textContent = '复制失败'; });
    }
  }

  async function logout() {
    if (state.loggingOut) return;
    state.loggingOut = true;
    // Clear secrets immediately, but report success only after server revocation.
    lockPage('正在退出登录…',false);
    try {
      const result = await request('/admin/logout',{},true);
      if (result.ok !== true) throw new Error('退出结果未确认。');
      window.location.replace('/admin/login');
    } catch (error) {
      message('退出请求未完成，本页密钥已清空。请重试“退出登录”，或重新登录确认会话状态。',true);
      $('admin-login').classList.remove('hidden');
    } finally { state.loggingOut = false; controls(); }
  }

  function suspend() {
    state.suspended = true;
    lockPage('',false);
  }

  async function resume() {
    if (!state.suspended || state.authLost || state.loggingOut) return;
    state.suspended = false; state.locked = false; state.stopped = false;
    // A restored page must reauthenticate before its controls can be enabled.
    state.settings = null; state.conflict = false; state.enableDirty = false;
    await refreshOverview(true);
    schedulePoll();
  }

  function stopPolling() { clearTimeout(state.timer); state.timer = null; }
  function schedulePoll(delay = 30000) {
    stopPolling();
    if (!state.stopped && !state.locked && !document.hidden) state.timer = setTimeout(poll,delay);
  }
  async function poll() {
    if (state.polling || state.stopped || state.locked || document.hidden) return;
    const epoch = state.epoch;
    state.polling = true;
    try { await refreshOverview(false); }
    finally { if (epoch === state.epoch) { state.polling = false; schedulePoll(); } }
  }

  async function boot() {
    $('admin-refresh').addEventListener('click',()=>refreshOverview(true));
    $('key-add-form').addEventListener('submit',addKeys);
    $('enable-form').addEventListener('submit',saveEnabled);
    $('ai-enabled').addEventListener('change',()=>{state.enableDirty = true;});
    $('key-list').addEventListener('click',keyAction);
    $('key-list').addEventListener('submit',renameKey);
    $('key-reveal').addEventListener('click',()=>{
      if (state.locked) return;
      const area = $('key-batch'), button = $('key-reveal');
      const show = !area.classList.contains('key-plain');
      area.classList.toggle('key-plain', show);
      button.textContent = show ? '隐藏' : '显示';
      button.setAttribute?.('aria-pressed', show ? 'true' : 'false');
      area.focus();
    });
    $('ledger-list').addEventListener('click',ledgerClick);
    $('ledger-details').addEventListener('toggle',()=>{
      if ($('ledger-details').open) {
        if (state.locked) $('ledger-details').open = false;
        else loadLedger();
      } else clearLedger();
    });
    $('ledger-refresh').addEventListener('click',loadLedger);
    $('admin-logout').addEventListener('click',logout);
    document.addEventListener('visibilitychange',()=>{ if (document.hidden) stopPolling(); else schedulePoll(0); });
    window.addEventListener('pagehide',suspend);
    window.addEventListener('pageshow',resume);
    window.addEventListener('beforeunload',suspend);
    await refreshOverview(false);
    schedulePoll();
  }
  boot().catch(()=>message('管理页面加载失败，请刷新后重试。',true));
})();
