'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {settings:null, pool:{keys:[]}, loading:false, saving:false, refreshing:false, conflict:false,
    keysSignature:'', timer:null, polling:false, stopped:false, enableDirty:false};
  const statuses = {ready:['可用','ok'],available:['可用','ok'],active:['调用中','ok'],busy:['调用中','ok'],
    cooldown:['冷却中','warning'],rate_limited:['限流冷却中','warning'],disabled:['已停用',''],invalid:['密钥不可用','error'],
    service_disabled:['AI 已关闭',''],paused_authentication:['认证失败，已暂停','error'],paused_insufficient_balance:['余额不足，已暂停','error'],
    unauthorized:['密钥不可用','error'],unavailable:['暂不可用','warning'],failed:['调用失败','error'],idle:['待调用','']};

  function message(text, error = false) {
    $('admin-message').textContent = text;
    $('admin-message').classList.toggle('hidden', !text);
    $('admin-message').classList.toggle('error', error);
  }

  async function request(path, payload) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method:payload === undefined ? 'GET' : 'POST',
        headers:payload === undefined ? {} : {'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN || ''},
        body:payload === undefined ? undefined : JSON.stringify(payload),cache:'no-store',signal:controller.signal});
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(result.error || '管理服务暂不可用，请稍后重试。');
        error.status = response.status;
        throw error;
      }
      return result;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时，请刷新设置确认结果。');
      if (error instanceof TypeError) throw new Error('暂时无法连接主机工具，请稍后重试。');
      throw error;
    } finally { clearTimeout(timeout); }
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
    const locked = state.loading || state.saving || !state.settings || state.conflict;
    ['ai-enabled','enable-save','key-batch','key-add'].forEach((id) => $(id).disabled = locked);
    $('admin-refresh').disabled = state.loading || state.saving || state.refreshing;
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
    $('settings-state').textContent = !settings.enabled ? '已关闭 AI，使用本机匹配。' : settings.configured ? '员工共用主机配置，无需填写 Key。' : '请添加并启用 Key，才能使用 AI。';
    $('qualification-state').textContent = settings.mode === 'validated' ? 'AI 二次复核已进入经验证模式：仅符合全部条件的结果可自动通过，其余仍需人工确认。' : 'AI 二次复核尚未取得条件自动通过资格，复核建议仍需人工确认。AI 查找到的候选只有通过本机独立核验，才能按本机规则自动通过；增加 Key 不会放宽判定。';
    $('persistence-state').textContent = settings.key_persistence === 'windows_dpapi' ? '主机使用当前 Windows 用户的 DPAPI 加密保存密钥。' : '当前环境只在本次服务运行期间保留密钥，重启后需重新填写。';
    $('storage-warning').textContent = settings.storage_warning || '';
    $('storage-warning').classList.toggle('hidden', !settings.storage_warning);
  }

  async function refreshOverview(manual = false) {
    if (state.refreshing || state.loading || state.saving) return;
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
        message('配置已在其他页面更新。请刷新设置，核对后再修改。',true);
        return;
      }
      state.pool = result.pool || {keys:[]}; renderKeys();
      if (manual) { state.stopped = false; message('已读取最新设置。'); loadLedger(); }
    } catch (error) {
      if (error.status === 403) { state.stopped = true; state.conflict = true; }
      message(error.status === 403 ? '仅限主机管理员在本机访问。' : error.message,true);
    } finally { state.refreshing = false; if (blocking) state.loading = false; controls(); }
  }

  async function mutateKeys(change) {
    if (state.saving || state.loading || state.conflict || !state.settings) return;
    state.saving = true; controls(); message('');
    const payload = {...change,expected_revision:state.settings.key_revision};
    try {
      const result = await request('/api/admin/keys',payload);
      applySettings(result.settings); state.pool = result.pool || {keys:[]}; renderKeys();
      message('已保存 Key，接口将在处理任务时验证。');
      loadLedger();
    } catch (error) {
      if (error.status === 409) { state.conflict = true; message('其他页面已修改密钥配置。请刷新设置，核对后再修改；本次未保存。',true); }
      else message(error.message || '配置未保存，请稍后重试。',true);
    } finally {
      for (const key of payload.add || []) delete key.api_key;
      $('key-batch').value = '';
      state.saving = false; controls();
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
    if (state.saving || state.loading || !state.settings || state.conflict) return;
    const enabled = $('ai-enabled').checked;
    let saved = false;
    state.saving = true; controls(); message('');
    try {
      state.enableDirty = false;
      applySettings(await request('/api/ai/settings',{enabled}));
      $('ai-enabled').checked = state.settings.enabled === true;
      // Pool health was measured before this switch changed. Do not present it as current.
      state.pool = {keys:[]}; renderKeys();
      saved = true; message('AI 开关已保存。');
    }
    catch (error) { $('ai-enabled').checked = state.settings.enabled === true; message(error.message || '设置未保存，请稍后重试。',true); }
    finally { state.saving = false; controls(); }
    if (saved) await refreshOverview(false);
  }

  function keyAction(event) {
    const button = event.target.closest('[data-action]'), card = button?.closest('[data-key-id]');
    if (!button || !card || state.saving || state.loading || state.conflict) return;
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
    const stateLine = $('ledger-state'), list = $('ledger-list');
    try {
      const response = await fetch('/api/admin/ledger', {headers:{'X-HSD-Token':window.HSD_TOKEN}});
      if (!response.ok) {
        stateLine.textContent = response.status === 401 ? '登录已失效，请重新登录。' : '读取失败。';
        return;
      }
      const payload = await response.json();
      const keys = Array.isArray(payload.keys) ? payload.keys : [];
      list.innerHTML = keys.length ? keys.map(ledgerHtml).join('') : '<p class="empty">暂未添加 Key。</p>';
      stateLine.textContent = keys.length ? `${keys.length} 个` : '';
    } catch (error) {
      stateLine.textContent = '读取失败。';
    }
  }

  function ledgerClick(event) {
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
      navigator.clipboard.writeText(code.dataset.value || '').then(() => {
        button.textContent = '已复制';
        setTimeout(() => { button.textContent = '复制'; }, 1200);
      }).catch(() => { button.textContent = '复制失败'; });
    }
  }

  function stopPolling() { clearTimeout(state.timer); state.timer = null; }
  function schedulePoll(delay = 30000) {
    stopPolling();
    if (!state.stopped && !document.hidden) state.timer = setTimeout(poll,delay);
  }
  async function poll() {
    if (state.polling || state.stopped || document.hidden) return;
    state.polling = true;
    try { await refreshOverview(false); }
    finally { state.polling = false; schedulePoll(); }
  }

  async function boot() {
    $('admin-refresh').addEventListener('click',()=>refreshOverview(true));
    $('key-add-form').addEventListener('submit',addKeys);
    $('enable-form').addEventListener('submit',saveEnabled);
    $('ai-enabled').addEventListener('change',()=>{state.enableDirty = true;});
    $('key-list').addEventListener('click',keyAction);
    $('key-list').addEventListener('submit',renameKey);
    $('key-reveal').addEventListener('click',()=>{
      const area = $('key-batch'), button = $('key-reveal');
      const show = !area.classList.contains('key-plain');
      area.classList.toggle('key-plain', show);
      button.textContent = show ? '隐藏' : '显示';
      button.setAttribute?.('aria-pressed', show ? 'true' : 'false');
      area.focus();
    });
    $('ledger-list').addEventListener('click',ledgerClick);
    $('admin-logout').addEventListener('click',async()=>{
      try { await fetch('/admin/logout',{method:'POST',headers:{'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN},body:'{}'}); } catch (error) {}
      window.location.replace('/admin/login');
    });
    document.addEventListener('visibilitychange',()=>{ if (document.hidden) stopPolling(); else schedulePoll(0); });
    window.addEventListener('pagehide',()=>{ state.stopped = true; stopPolling(); $('key-batch').value = ''; });
    window.addEventListener('pageshow',()=>{ if (state.stopped) { state.stopped = false; schedulePoll(0); } });
    window.addEventListener('beforeunload',()=>{ $('key-batch').value = ''; stopPolling(); });
    await refreshOverview(false);
    loadLedger();
    schedulePoll();
  }
  boot().catch(()=>message('管理页面加载失败，请刷新后重试。',true));
})();
