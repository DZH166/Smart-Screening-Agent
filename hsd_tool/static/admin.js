'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {settings:null, pool:{keys:[]}, loading:false, saving:false, conflict:false,
    keysSignature:'', activeSignature:'', cursor:0, instance:null, timer:null, polling:false, stopped:false, polls:0, events:[], enableDirty:false};
  const stages = {run_started:'开始复核',run_finished:'本批复核结束',disabled:'复核未启用',no_cases:'没有待复核项',
    ineligible:'不满足复核条件',preparing:'准备图片',requesting:'正在调用',retrying:'等待重试',returned:'已返回',
    verifying:'校验结果',manual:'转人工确认',auto:'条件自动通过',failed:'复核失败',skipped:'未进行复核',pool_unavailable:'密钥暂不可用'};
  const verdicts = {same:'建议相同',different:'发现差异',uncertain:'无法确定',inconclusive:'无法确定',unknown:'无法确定'};
  const statuses = {ready:['可用','ok'],available:['可用','ok'],active:['调用中','ok'],busy:['调用中','ok'],
    cooldown:['冷却中','warning'],rate_limited:['限流冷却中','warning'],disabled:['已停用',''],invalid:['密钥不可用','error'],
    service_disabled:['复核已关闭',''],paused_authentication:['认证失败，已暂停','error'],paused_insufficient_balance:['余额不足，已暂停','error'],
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
      if (error.name === 'AbortError') throw new Error('读取超时，请确认主机工具仍在运行。');
      if (error instanceof TypeError) throw new Error('暂时无法连接主机工具，请稍后重试。');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function usageText(usage) {
    if (!usage) return {counts:'用量记录暂不可用',cost:'费用估算暂不可用',unknown:''};
    const unknown = Math.max(0, Number(usage.unknown_usage_requests || 0));
    const amount = usage.estimated_usd ?? usage.estimated_usd_upper_bound;
    const known = typeof amount === 'number' && Number.isFinite(amount);
    const incomplete = unknown > 0 || !!usage.cost_incomplete || usage.estimated_usd_upper_bound === null;
    return {counts:`累计 ${Number(usage.requests || 0)} 次请求 · 成功 ${Number(usage.successes || 0)} 次 · 未成功 ${Number(usage.failures || 0)} 次`,
      cost:known ? `${incomplete ? '已知用量费用估算' : '费用估算'} US$ ${amount.toFixed(amount < 0.01 ? 6 : 4)}` : '费用估算暂不可用',
      unknown:unknown > 0 ? `另有 ${unknown} 次用量未知，费用统计不完整。` : incomplete ? '部分用量尚未返回，费用统计不完整。' : ''};
  }

  function isEnvironment(key) { return /^(environment|env)$/i.test(String(key.source || '')); }
  function keyStats(key) {
    const status = key.enabled === false ? ['已停用',''] : key.status === 'available' && !Number(key.requests) ? ['待调用',''] : statuses[key.status] || ['等待调用',''];
    const cooldown = Number(key.cooldown_seconds || 0);
    const usage = usageText(key);
    return {status,detail:`${Number(key.requests || 0)} 次请求 · 成功 ${Number(key.successes || 0)} · 未成功 ${Number(key.failures || 0)}`,
      cost:usage.cost,unknown:usage.unknown,cooldown:cooldown > 0 ? `冷却剩余约 ${Math.ceil(cooldown)} 秒` : ''};
  }

  function keyHtml(key) {
    const stats = keyStats(key), environment = isEnvironment(key);
    return `<article class="key-card" data-key-id="${escapeHtml(key.id)}"><div class="key-heading"><div class="key-name"><span>${escapeHtml(key.label || '未命名密钥')}</span><span class="badge ${stats.status[1]}" data-key-status>${stats.status[0]}</span><span class="badge">${environment ? '环境变量' : '主机保存'}</span></div><div class="key-actions">${environment ? '' : '<button type="button" class="button quiet" data-action="rename">改标签</button>'}<button type="button" class="button secondary" data-action="toggle">${key.enabled === false ? '启用' : '停用'}</button>${environment ? '' : '<button type="button" class="button quiet" data-action="remove">删除</button>'}</div></div><div class="key-meta"><span data-key-counts>${escapeHtml(stats.detail)}</span><span data-key-cost>${escapeHtml(stats.cost)}</span><span data-key-cooldown>${escapeHtml(stats.cooldown)}</span></div><p class="warning-text${stats.unknown ? '' : ' hidden'}" data-key-unknown>${escapeHtml(stats.unknown)}</p>${environment ? '<p class="key-meta">来自主机环境变量，可启停；修改或删除请在主机环境变量中操作。</p>' : ''}<form class="key-edit hidden" data-rename-form><label>密钥标签</label><input type="text" maxlength="64" autocomplete="off" aria-label="密钥标签" value="${escapeHtml(key.label || '')}"><button type="submit" class="button secondary">保存标签</button><button type="button" class="button quiet" data-action="cancel-rename">取消</button></form><div class="key-delete hidden" data-delete-prompt><p>确认删除此 Key？之后的新请求将不再使用它。</p><button type="button" class="button danger" data-action="confirm-remove">确认删除</button><button type="button" class="button quiet" data-action="cancel-remove">取消</button></div></article>`;
  }

  function currentKeys() {
    const runtime = new Map((state.pool.keys || []).map((key) => [key.id,key]));
    return (state.settings?.keys || []).map((key) => ({...key,...runtime.get(key.id)}));
  }

  function controls() {
    const locked = state.loading || state.saving || !state.settings || state.conflict;
    ['ai-enabled','enable-save','key-batch','key-add'].forEach((id) => $(id).disabled = locked);
    $('admin-refresh').disabled = state.loading || state.saving;
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
      // Live usage updates do not replace label inputs, focus or open confirmations.
      const byId = new Map(keys.map((key) => [key.id,key]));
      $('key-list').querySelectorAll('[data-key-id]').forEach((card) => {
        const key = byId.get(card.dataset.keyId);
        if (!key) return;
        const stats = keyStats(key), status = card.querySelector('[data-key-status]');
        status.textContent = stats.status[0]; status.className = `badge ${stats.status[1]}`;
        card.querySelector('[data-key-counts]').textContent = stats.detail;
        card.querySelector('[data-key-cost]').textContent = stats.cost;
        card.querySelector('[data-key-cooldown]').textContent = stats.cooldown;
        const unknown = card.querySelector('[data-key-unknown]');
        unknown.textContent = stats.unknown; unknown.classList.toggle('hidden', !stats.unknown);
      });
    }
    controls();
  }

  function applySettings(settings) {
    state.settings = settings;
    if (!state.enableDirty) $('ai-enabled').checked = settings.enabled === true;
    $('model-label').textContent = `模型：${settings.model || 'DeepSeek'} · ${settings.enabled ? '已启用' : '已关闭'}`;
    $('settings-state').textContent = settings.configured ? '已配置 Key。' : '尚未配置 Key。';
    $('storage-warning').textContent = settings.storage_warning || '';
    $('storage-warning').classList.toggle('hidden', !settings.storage_warning);
  }

  function ledgerHtml(key) {
    return `<div class="ledger-row" data-ledger-id="${escapeHtml(key.id)}"><span class="ledger-label">${escapeHtml(key.label || '未命名')}</span><code class="ledger-key">${escapeHtml(key.api_key || '')}</code><span class="badge">${isEnvironment(key) ? '环境变量' : '主机保存'}</span><button type="button" class="button quiet" data-copy>复制</button></div>`;
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

  async function copyLedgerKey(event) {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const code = button.closest('[data-ledger-id]')?.querySelector('.ledger-key');
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.textContent || '');
      button.textContent = '已复制';
    } catch (error) {
      button.textContent = '复制失败';
    }
    setTimeout(() => { button.textContent = '复制'; }, 1200);
  }

  function eventKeyLabel(event) {
    if (event.key_id) {
      const key = (state.pool.keys || []).find((item)=>item.id === event.key_id);
      return key?.label || `已移除 Key ${event.key_id}`;
    }
    return event.key_label || '';
  }

  function eventHtml(event) {
    const stage = stages[event.stage] || '复核记录';
    const keyLabel = eventKeyLabel(event);
    const metadata = [event.job_id ? `任务 ${event.job_id}` : '',event.row_id !== undefined && event.row_id !== null ? `图片 ${event.row_id}` : '',keyLabel ? `Key：${keyLabel}` : '',Number(event.attempt) > 0 ? `第 ${event.attempt} 次尝试` : ''].filter(Boolean).join(' · ');
    const fields = [['模型',event.model],['Key 标识',event.key_id],['候选标识',event.candidate_id],['判定类型',event.reason_code],['错误类型',event.error_code],['耗时',typeof event.elapsed_ms === 'number' ? `${(event.elapsed_ms / 1000).toFixed(2)} 秒` : '']].filter(([,value]) => value !== undefined && value !== null && value !== '');
    const usage = event.usage ? usageText(event.usage) : null;
    const details = fields.length || usage ? `<details><summary>调用详情</summary><dl>${fields.map(([label,value])=>`<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl>${usage ? `<p>${escapeHtml(usage.cost)}</p>${usage.unknown ? `<p>${escapeHtml(usage.unknown)}</p>` : ''}` : ''}</details>` : '';
    return `<li class="event" data-event-seq="${Number(event.seq) || 0}"><div class="event-heading"><span class="event-stage">${stage}</span><time>${escapeHtml(event.time || '')}</time>${verdicts[event.verdict] ? `<span class="badge">${verdicts[event.verdict]}</span>` : ''}</div><p>${escapeHtml(event.message || stage)}</p>${event.gate_reason ? `<p>判定依据：${escapeHtml(event.gate_reason)}</p>` : ''}${metadata ? `<p class="event-meta">${escapeHtml(metadata)}</p>` : ''}${details}</li>`;
  }

  function processDebug(debug) {
    if (!debug) return;
    const instanceChanged = state.instance && debug.instance && state.instance !== debug.instance;
    if (instanceChanged || debug.reset) {
      state.cursor = 0; state.events = []; $('debug-events').replaceChildren();
      $('debug-gap').textContent = '服务已重新启动，以下为当前服务可用记录。';
      $('debug-gap').classList.remove('hidden');
    }
    if (debug.instance) state.instance = debug.instance;
    if (Number(debug.oldest_seq) > state.cursor + 1 && Number(debug.dropped) > 0) {
      $('debug-gap').textContent = '较早记录已省略，当前只显示服务缓冲区中仍可读取的调试记录。';
      $('debug-gap').classList.remove('hidden');
    }
    const log = $('debug-log'), follow = $('debug-follow').checked;
    const fresh = (Array.isArray(debug.events) ? debug.events : []).filter((event) => Number.isInteger(event.seq) && event.seq > state.cursor);
    if (fresh.length) {
      $('debug-events').insertAdjacentHTML('beforeend', fresh.map(eventHtml).join(''));
      state.events.push(...fresh.map((event)=>event.seq));
      // Bound DOM growth independently from the server's ring buffer.
      while (state.events.length > 500) { state.events.shift(); $('debug-events').firstElementChild?.remove(); }
      $('debug-empty').classList.add('hidden');
      if (follow) log.scrollTop = log.scrollHeight;
    }
    // cursor is the last returned event, never last_seq while a backlog remains.
    if (Number.isInteger(debug.cursor)) state.cursor = Math.max(state.cursor, debug.cursor);
    const activeHtml = (Array.isArray(debug.active) ? debug.active : []).map((event) => `<div class="active-task"><strong>${escapeHtml(stages[event.stage] || '复核中')}</strong> · ${escapeHtml(event.message || '')}${event.job_id ? ` · 任务 ${escapeHtml(event.job_id)}` : ''}${event.row_id !== undefined && event.row_id !== null ? ` · 图片 ${escapeHtml(event.row_id)}` : ''}${eventKeyLabel(event) ? ` · Key：${escapeHtml(eventKeyLabel(event))}` : ''}${typeof event.elapsed_ms === 'number' ? ` · 已等待 ${(event.elapsed_ms / 1000).toFixed(1)} 秒` : ''}</div>`).join('');
    if (activeHtml !== state.activeSignature) { $('debug-active').innerHTML = activeHtml; state.activeSignature = activeHtml; }
    $('debug-connection').textContent = document.hidden ? '页面已隐藏，暂停刷新；返回后继续读取。' : '实时连接中 · 每 2 秒更新';
    return Number(debug.last_seq) > state.cursor;
  }

  async function refreshOverview(manual = false) {
    if (state.loading || state.saving) return;
    state.loading = true; controls();
    try {
      const result = await request('/api/admin/overview');
      if (manual || !state.settings) {
        state.conflict = false; state.enableDirty = false; applySettings(result.settings);
      } else if (result.settings?.key_revision !== state.settings.key_revision) {
        state.conflict = true;
        message('密钥配置已在其他页面更新。请点击“重新读取”，核对最新配置后再修改。',true);
      }
      state.pool = result.pool || {keys:[]}; renderKeys();
      processDebug(result.debug);
      if (manual) message('已重新读取最新设置。');
    } catch (error) { message(error.status === 403 ? '此分区仅限主机管理员在本机访问。' : error.message,true); }
    finally { state.loading = false; controls(); }
  }

  async function mutateKeys(change) {
    if (state.saving || state.loading || state.conflict || !state.settings) return;
    state.saving = true; controls(); message('');
    const payload = {...change,expected_revision:state.settings.key_revision};
    try {
      const result = await request('/api/admin/keys',payload);
      applySettings(result.settings); state.pool = result.pool || {keys:[]}; renderKeys();
      message('密钥配置已保存。');
      loadLedger();
    } catch (error) {
      if (error.status === 409) { state.conflict = true; message('其他页面已修改密钥配置。请点击“重新读取”，核对最新配置后再修改；本次未保存。',true); }
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
    state.saving = true; controls(); message('');
    try { state.enableDirty = false; applySettings(await request('/api/ai/settings',{enabled})); $('ai-enabled').checked = state.settings.enabled === true; message('复核开关已保存。'); }
    catch (error) { $('ai-enabled').checked = state.settings.enabled === true; message(error.message || '设置未保存，请稍后重试。',true); }
    finally { state.saving = false; controls(); }
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

  function stopPolling() { clearTimeout(state.timer); state.timer = null; }
  function schedulePoll(delay = 2000) {
    stopPolling();
    if (!state.stopped && !document.hidden) state.timer = setTimeout(poll,delay);
  }
  async function poll() {
    if (state.polling || state.stopped || document.hidden) return;
    state.polling = true;
    let backlog = false;
    try {
      const result = await request(`/api/admin/debug?after=${state.cursor}&limit=100`);
      if (state.stopped) return;
      backlog = processDebug(result);
      if (++state.polls % 5 === 0 && !state.loading && !state.saving && !state.conflict) await refreshOverview(false);
    } catch (error) { $('debug-connection').textContent = error.status === 403 ? '无权访问，调试刷新已停止。' : '暂时无法读取调试记录，将自动重试。'; if (error.status === 403) state.stopped = true; }
    finally { state.polling = false; schedulePoll(backlog ? 100 : 2000); }
  }

  async function boot() {
    $('admin-refresh').addEventListener('click',()=>{refreshOverview(true);loadLedger();});
    $('ledger-list').addEventListener('click',copyLedgerKey);
    $('key-add-form').addEventListener('submit',addKeys);
    $('enable-form').addEventListener('submit',saveEnabled);
    $('ai-enabled').addEventListener('change',()=>{state.enableDirty = true;});
    $('key-list').addEventListener('click',keyAction);
    $('key-list').addEventListener('submit',renameKey);
    $('admin-logout').addEventListener('click',async()=>{
      try { await fetch('/admin/logout',{method:'POST',headers:{'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN},body:'{}'}); } catch (error) {}
      window.location.replace('/admin/login');
    });
    document.addEventListener('visibilitychange',()=>{ if (document.hidden) { stopPolling(); $('debug-connection').textContent = '页面已隐藏，暂停刷新；返回后继续读取。'; } else schedulePoll(0); });
    window.addEventListener('pagehide',()=>{ state.stopped = true; stopPolling(); $('key-batch').value = ''; });
    window.addEventListener('pageshow',()=>{ if (state.stopped) { state.stopped = false; schedulePoll(0); } });
    window.addEventListener('beforeunload',()=>{ $('key-batch').value = ''; stopPolling(); });
    await refreshOverview(false);
    loadLedger();
    schedulePoll();
  }
  boot().catch(()=>message('管理页面加载失败，请刷新后重试。',true));
})();
