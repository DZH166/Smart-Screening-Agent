'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let settings = null;
  let loading = false;

  async function refresh() {
    if (loading) return settings;
    loading = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/ai/settings', {cache:'no-store',signal:controller.signal});
      if (!response.ok) return settings;
      settings = await response.json();
      const active = !!settings.enabled && !!settings.configured;
      $('processing-mode-label').textContent = active ? 'AI 查找对应图片 + 本机核验' : '本机匹配';
      $('import-processing-note').textContent = active ? 'DeepSeek 查找候选与本机核验同时进行，只有本机验证可靠的匹配才会通过；原文件保留。' : '本机匹配，原文件保留';
      document.dispatchEvent(new CustomEvent('hsd-ai-settings-updated', {detail:settings}));
    } catch (_) { /* Keep employee workflow usable when settings cannot be read. */ }
    finally { clearTimeout(timer); loading = false; }
    return settings;
  }

  function open() { if (!window.HSD_ACCESS?.remote) window.location.assign('/admin'); }

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

  function retrievalHtml(row, candidateName, selectedId) {
    const retrieval=row?.ai_retrieval;
    if(!retrieval)return '';
    const title=retrieval.outcome==='error'?'AI 查找未完成':retrieval.outcome==='skipped'?'本项未进行 AI 查找':'AI 查找建议';
    const action=row.status==='auto'?'本机核验已通过':row.status==='confirmed'?'本项已由员工确认':row.status==='skipped'?'本项已跳过':'需人工确认';
    const reason=String(retrieval.reason||'').trim();
    const differentSelection=!!retrieval.candidate_id&&retrieval.candidate_id!==selectedId;
    const objectName=candidateName||retrieval.candidate_id||'';
    const warning=differentSelection?`<p class="ai-candidate-label ai-selection-warning">AI 建议与当前候选不同，以本机核验或员工选择为准。建议文件：${escapeHtml(objectName)}</p><button type="button" class="text-button" data-candidate-id="${escapeHtml(retrieval.candidate_id)}">查看 AI 建议的文件</button>`:'';
    // The native pending reason stays above the images. Do not repeat it as a
    // model explanation or invent comparison checks from retrieval's verdict.
    const distinctReason=reason&&reason!==String(row.reason||'').trim();
    const sentence=reason.match(/^[^。！？\n]+[。！？]?/u)?.[0]||reason;
    const brief=distinctReason?(Array.from(reason).length<=100?reason:Array.from(sentence).length<=100?sentence:'完整查找理由请展开下方说明。'):'';
    const details=objectName||distinctReason?`<details class="ai-check-details" data-detail-key="ai-retrieval"><summary>AI 查找说明</summary>${objectName?`<p>建议文件：${escapeHtml(objectName)}</p>`:''}${distinctReason&&reason!==brief?`<p>${escapeHtml(reason)}</p>`:''}<p>查找建议不代表匹配通过，最终状态以本机核验或员工确认结果为准。</p></details>`:'';
    return `<section class="ai-row-note"><strong>${escapeHtml(title)} · ${escapeHtml(action)}</strong>${warning}${brief?`<p class="ai-row-summary">${escapeHtml(brief)}</p>`:''}${details}</section>`;
  }

  function rowHtml(row, candidateName, selectedId) {
    const review = row?.ai_review;
    if (!review) return '';
    const labels = {same:'AI 建议相同',different:'AI 发现差异',uncertain:'AI 无法确定',inconclusive:'AI 无法确定',unknown:'AI 无法确定'};
    // Only the server's effective row status grants export eligibility. A model
    // verdict or stale outcome must never turn a review row into an accepted one.
    const auto = row.status === 'auto' && review.outcome === 'auto_passed';
    const resolved = row.status === 'confirmed' || row.status === 'skipped';
    const title = auto ? 'AI 复核 · 条件验证后自动通过' : review.outcome === 'error' ? 'AI 复核未完成' : review.outcome === 'skipped' ? '本项未进行 AI 复核' : labels[review.verdict] || 'AI 复核建议';
    const action = auto ? '' : row.status === 'confirmed' ? '本项已由员工确认' : row.status === 'skipped' ? '本项已跳过' : '需人工确认';
    const differenceItems = Array.isArray(review.differences) ? review.differences : typeof review.differences === 'string' ? [review.differences] : [];
    const differences = [...new Set(differenceItems.map((item)=>String(item ?? '').trim()).filter(Boolean))].join('；');
    const differentSelection = review.candidate_id && review.candidate_id !== selectedId;
    const objectName = candidateName || review.candidate_id || '';
    const candidate = differentSelection ? `<p class="ai-candidate-label ai-selection-warning">AI 复核对象：${escapeHtml(objectName)}（与当前选择不同）</p><button type="button" class="text-button" data-candidate-id="${escapeHtml(review.candidate_id)}">查看 AI 复核的候选</button>` : '';
    const checks = {content_same:'图案内容相同',colors_same:'颜色相同',complete_coverage:'内容覆盖完整',extra_content_absent:'没有额外内容',unique_candidate:'候选唯一'};
    const checksHtml = review.checks && typeof review.checks === 'object' ? `<ul>${Object.entries(checks).filter(([key])=>typeof review.checks[key]==='boolean').map(([key,label])=>`<li>${label}：${review.checks[key]?'认为满足':'未确认满足'}</li>`).join('')}</ul>` : '';
    const reason = String(review.reason || '').trim();
    const failures = Array.isArray(review.gate_failures) ? review.gate_failures : [];
    const failureCodes = new Set(failures.map((item)=>String(item?.code || '')));
    if (review.reason_code) failureCodes.add(review.reason_code);
    const inconsistent = review.protocol_diagnostics?.inconsistent === true || review.protocol_diagnostics?.protocol_inconsistent === true || failureCodes.has('model_protocol_inconsistent');
    const warnings = [];
    if (inconsistent) warnings.push('模型回答存在矛盾，请对照图片判断。');
    if (failureCodes.has('local_evidence_conflict')) warnings.push('本地检测到图案或颜色差异，不能按 AI 建议直接通过。');
    if (failureCodes.has('source_changed') || failureCodes.has('stale_case')) warnings.push('复核图片或原文件已变化，请重新导入。');
    const warningHtml = warnings.length ? `<p class="ai-gate-note ai-visible-warning">${warnings.map(escapeHtml).join(' ')}</p>` : '';
    // Specific differences stay readable; no character slicing or visual clamp.
    // A long general explanation is available once under the explicit detail entry.
    const sentence = reason.match(/^[^。！？\n]+[。！？]?/u)?.[0] || reason;
    const brief = differences || (Array.from(reason).length <= 140 ? reason : Array.from(sentence).length <= 140 ? sentence.trim() : '完整判断理由请展开下方说明。');
    const gateReasons = !auto ? [...new Set(failures.map((item)=>String(item?.reason || '').trim()).filter(Boolean))] : [];
    if (!auto && review.gate_reason && !gateReasons.includes(review.gate_reason)) gateReasons.push(review.gate_reason);
    const gatesHtml = gateReasons.length ? `<div class="ai-gate-details"><p>未自动通过的依据</p><ul>${gateReasons.map((value)=>`<li>${escapeHtml(value)}</li>`).join('')}</ul></div>` : '';
    const objectDetails = objectName ? `<p>复核对象：${escapeHtml(objectName)}</p>` : '';
    const protocolHtml = inconsistent ? '<p>协议检查：模型结论与检查项不一致。</p>' : '';
    const details = objectDetails || reason || differences || gatesHtml || checksHtml || protocolHtml ? `<details class="ai-check-details" data-detail-key="ai-review"><summary>完整 AI 复核说明</summary>${objectDetails}${reason && reason !== brief ? `<p>${escapeHtml(reason)}</p>` : ''}${protocolHtml}${gatesHtml}${checksHtml}</details>` : '';
    return `<section class="ai-row-note${resolved?' ai-resolved-note':''}"><strong>${escapeHtml(title)}${action ? ` · ${escapeHtml(action)}` : ''}</strong>${candidate}${brief ? `<p class="ai-row-summary">${differences ? '差异：' : ''}${escapeHtml(brief)}</p>` : ''}${warningHtml}${details}</section>`;
  }

  window.HSDAI = Object.freeze({open, refresh, usageText, retrievalHtml, rowHtml, getSettings:()=>settings});
  if (window.HSD_ACCESS?.remote) $('ai-settings-button').classList.add('hidden');
  else $('ai-settings-button').addEventListener('click', open);
  // A return from the separate admin page refreshes the employee-mode hint.
  window.addEventListener?.('pageshow', () => refresh());
  refresh();
})();
