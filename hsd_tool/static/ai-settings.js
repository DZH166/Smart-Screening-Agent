'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let settings = null;
  let saving = false;
  let loading = false;

  async function request(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {
        method: payload === undefined ? 'GET' : 'POST',
        headers: payload === undefined ? {} : {'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN || ''},
        body: payload === undefined ? undefined : JSON.stringify(payload),
        cache: 'no-store', signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '设置服务暂不可用。');
      return result;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('读取超时，请确认本机工具仍在运行。');
      if (error instanceof TypeError) throw new Error('暂时无法连接本机工具。');
      throw error;
    } finally { clearTimeout(timer); }
  }

  function usageText(usage) {
    if (!usage) return {cost:'费用估算暂不可用', unknown:'', counts:'用量记录暂不可用'};
    const requests = Number(usage.requests || 0);
    const unknown = Math.max(0, Number(usage.unknown_usage_requests || 0));
    const amount = usage.estimated_usd ?? usage.estimated_usd_upper_bound;
    const known = typeof amount === 'number' && Number.isFinite(amount);
    const incomplete = unknown > 0 || !!usage.cost_incomplete || usage.estimated_usd_upper_bound === null;
    const cost = known ? `${incomplete ? '已知用量费用估算' : '费用估算'} US$ ${amount.toFixed(amount < 0.01 ? 6 : 4)}` : '费用估算暂不可用';
    return {
      cost,
      unknown: unknown > 0 ? `另有 ${unknown} 次用量未知，费用统计不完整。` : incomplete ? '部分用量尚未返回，费用统计不完整。' : '',
      counts: `累计 ${requests} 次请求 · 成功 ${Number(usage.successes || 0)} 次 · 未成功 ${Number(usage.failures || 0)} 次`,
    };
  }

  function controls() {
    const locked = loading || saving || !settings;
    ['ai-enabled','ai-api-key','ai-clear-key','ai-settings-save'].forEach((id) => $(id).disabled = locked);
    $('ai-api-key').disabled = locked || $('ai-clear-key').checked;
    $('ai-settings-reload').disabled = loading || saving;
    $('ai-settings-save').textContent = saving ? '正在保存…' : '保存设置';
  }

  function updateSettings(value) {
    settings = value;
    $('ai-enabled').checked = !!value.enabled;
    $('ai-clear-key').checked = false;
    $('ai-api-key').value = '';
    $('ai-key-status').textContent = value.configured ? '已配置（不回显）' : '尚未配置';
    $('ai-api-key').placeholder = value.configured ? '留空保留现有密钥；粘贴可更换' : '粘贴 DeepSeek API Key';
    const environmentKey = /env/i.test(String(value.key_source || ''));
    $('ai-key-hint').textContent = environmentKey ? '当前密钥来自环境变量；清除本机保存的密钥不会删除环境变量。' : value.configured ? '留空保存不会更改已有密钥。保存与关闭窗口时，输入内容都会清空。' : '仅保存到本机设置服务，不在页面、日志或结果文件中显示。';
    $('ai-model-label').textContent = `模型：${value.model || 'deepseek-flash'}`;
    $('ai-mode-note').textContent = value.mode === 'validated' ? '已进入经验证模式：仅满足全部条件的复核结果可自动通过，其余仍需人工确认。' : '验证未完成，AI 先给出复核建议，仍需人工确认。';
    const active = !!value.enabled && !!value.configured;
    $('processing-mode-label').textContent = active ? '本机匹配 + AI 复核' : '本机匹配';
    $('import-processing-note').textContent = active ? '已启用 DeepSeek 预览复核' : '本机匹配，原文件保留';
    document.dispatchEvent(new CustomEvent('hsd-ai-settings-updated', {detail:value}));
    controls();
  }

  function message(text, error = false) {
    $('ai-settings-message').textContent = text;
    $('ai-settings-message').classList.toggle('hidden', !text);
    $('ai-settings-message').classList.toggle('error', error);
  }

  async function refreshUsage() {
    $('ai-usage-refresh').disabled = true;
    try {
      const usage = await request('/api/ai/usage');
      const text = usageText(usage);
      $('ai-usage-counts').textContent = text.counts;
      $('ai-usage-cost').textContent = text.cost;
      $('ai-usage-unknown').textContent = text.unknown;
      $('ai-usage-unknown').classList.toggle('hidden', !text.unknown);
    } catch (_) {
      $('ai-usage-counts').textContent = '暂时无法读取调用记录，可稍后刷新。';
      $('ai-usage-cost').textContent = '费用估算暂不可用';
      $('ai-usage-unknown').classList.add('hidden');
    } finally { $('ai-usage-refresh').disabled = false; }
  }

  async function refresh(visible = false) {
    if (loading || saving) return settings;
    loading = true; controls();
    if (visible) message('');
    try { updateSettings(await request('/api/ai/settings')); }
    catch (_) { if (visible) message('暂时无法读取 AI 设置，请确认程序仍在运行后重新读取。', true); }
    finally { loading = false; controls(); }
    return settings;
  }

  async function open() {
    $('ai-api-key').value = '';
    $('ai-clear-key').checked = false;
    message('');
    $('ai-settings-dialog').showModal();
    await Promise.allSettled([refresh(true), refreshUsage()]);
  }

  async function save(event) {
    event.preventDefault();
    if (saving || loading || !settings) return;
    const payload = {enabled:$('ai-enabled').checked};
    if ($('ai-clear-key').checked) payload.clear_key = true;
    else if ($('ai-api-key').value.trim()) payload.api_key = $('ai-api-key').value.trim();
    // Credentials are cleared before awaiting the request, including every error path.
    $('ai-api-key').value = '';
    saving = true; controls(); message('');
    try {
      updateSettings(await request('/api/ai/settings', payload));
      message(settings.enabled && !settings.configured ? '设置已保存，但尚无可用密钥；请填写密钥后启用复核。' : '设置已保存。密钥不会在界面中回显。');
    } catch (_) {
      message('设置未保存。请确认本机工具仍在运行，重新填写密钥后再试。', true);
    } finally {
      delete payload.api_key;
      $('ai-api-key').value = '';
      saving = false; controls();
    }
  }

  function rowHtml(row, candidateName, selectedId) {
    const review = row?.ai_review;
    if (!review) return '';
    const labels = {same:'建议为同一张图',different:'发现图案差异',uncertain:'仍无法确定',inconclusive:'仍无法确定',unknown:'仍无法确定',error:'本次复核未完成'};
    const auto = row.status === 'auto' && review.outcome === 'auto_passed';
    const hasDecision = ['same','different','uncertain'].includes(review.verdict);
    const title = auto ? 'AI 复核 · 条件验证后自动通过' : review.outcome === 'error' ? 'AI 复核未完成 · 继续人工处理' : review.outcome === 'skipped' ? '本项未进行 AI 复核' : `AI 复核建议 · ${labels[review.verdict] || '请结合画面确认'}`;
    const differences = Array.isArray(review.differences) ? review.differences.join('；') : typeof review.differences === 'string' ? review.differences : '';
    const differentSelection = review.candidate_id && review.candidate_id !== selectedId;
    const candidate = review.candidate_id ? `<p class="ai-candidate-label" title="${escapeHtml(candidateName || review.candidate_id)}">复核对象：${escapeHtml(candidateName || review.candidate_id)}${differentSelection ? '（与当前选择不同）' : ''}</p>` : '';
    const checks = {content_same:'图案内容相同',colors_same:'颜色相同',complete_coverage:'内容覆盖完整',extra_content_absent:'没有额外内容',unique_candidate:'候选唯一'};
    const checksHtml = review.checks && typeof review.checks === 'object' ? `<ul>${Object.entries(checks).filter(([key])=>typeof review.checks[key]==='boolean').map(([key,label])=>`<li>${label}：${review.checks[key]?'认为满足':'未确认满足'}</li>`).join('')}</ul>` : '';
    const reason = String(review.reason || '');
    const brief = Array.from(reason).slice(0,64).join('') + (Array.from(reason).length > 64 ? '…' : '');
    const gateReasons = Array.isArray(review.gate_failures) ? [...new Set(review.gate_failures.map((item)=>String(item?.reason||'')).filter(Boolean))] : [];
    const gatesHtml = !auto && gateReasons.length ? `<ul class="ai-gate-note">${gateReasons.map((value)=>`<li>${escapeHtml(value)}</li>`).join('')}</ul>` : !auto&&review.gate_reason ? `<p class="ai-gate-note">未自动通过：${escapeHtml(review.gate_reason)}</p>` : '';
    const inconsistent = review.protocol_diagnostics?.inconsistent === true || review.protocol_diagnostics?.protocol_inconsistent === true;
    const protocolHtml = inconsistent ? '<p class="ai-gate-note">模型回答存在矛盾，本项保留人工判断。</p>' : '';
    const details = reason || differences || gatesHtml || checksHtml || protocolHtml ? `<details class="ai-check-details"><summary>查看差异与完整复核说明</summary>${reason ? `<p>${escapeHtml(reason)}</p>` : ''}${differences ? `<p>需注意：${escapeHtml(differences)}</p>` : ''}${protocolHtml}${gatesHtml}${checksHtml}</details>` : '';
    return `<section class="ai-row-note"><strong>${escapeHtml(title)}</strong>${candidate}${brief ? `<p class="ai-row-summary">${escapeHtml(brief)}</p>` : ''}${differentSelection ? `<button type="button" class="text-button" data-candidate-id="${escapeHtml(review.candidate_id)}">查看 AI 复核的候选</button>` : ''}${hasDecision&&!auto ? '<small>仅供参考，仍需人工确认。</small>' : ''}${details}</section>`;
  }

  window.HSDAI = Object.freeze({open, refresh, usageText, rowHtml, getSettings:()=>settings});
  if (window.HSD_ACCESS?.remote) {
    $('ai-settings-button').classList.add('hidden');
    refresh(false);
    return;
  }
  $('ai-settings-button').addEventListener('click', open);
  $('ai-settings-close').addEventListener('click', () => $('ai-settings-dialog').close());
  $('ai-settings-dialog').addEventListener('close', () => { $('ai-api-key').value = ''; $('ai-clear-key').checked = false; });
  $('ai-clear-key').addEventListener('change', () => { if ($('ai-clear-key').checked) $('ai-api-key').value = ''; controls(); });
  $('ai-settings-form').addEventListener('submit', save);
  $('ai-settings-reload').addEventListener('click', () => refresh(true));
  $('ai-usage-refresh').addEventListener('click', refreshUsage);
  refresh(false);
})();
