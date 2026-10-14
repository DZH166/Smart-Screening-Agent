'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const state = {
    job: null, sourceType: 'zip', filter: 'awaiting', search: '',
    selectedRowId: null, selectedFileId: null, manualOpen: false, manualQuery: '',
    resolving: false, starting: false, picking: false, pollTimer: null, pollFailures: 0,
    showDone: true, stopped: false, lastJobError: null,
    forceReview: false, candidatesOpen: false, history: [],
  };
  const statusNames = {auto:'自动通过', confirmed:'已确认', review:'待确认', unmatched:'未找到', skipped:'已跳过'};
  const matched = (row) => ['auto','confirmed'].includes(row.status) && !!row.file_id;
  const awaiting = (row) => ['review','unmatched'].includes(row.status);
  const isBusy = () => ['importing','matching','exporting'].includes(state.job?.status) || state.starting;
  const fileById = (id) => (state.job?.files || []).find((file) => file.id === id);
  const rowById = (id) => (state.job?.rows || []).find((row) => row.id === id);
  const ownerOf = (id, rowId) => (state.job?.rows || []).find((row) => row.id !== rowId && row.file_id === id && matched(row));
  const previewUrl = (type,id) => `/api/jobs/${encodeURIComponent(state.job.id)}/image/${type}/${encodeURIComponent(id)}`;
  const imageTag = (type,id,className,alt) => `<img src="${previewUrl(type,id)}" class="${className}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async">`;
  const numberFor = (row) => String(row.number || row.planned_number || '');

  async function api(path, {method='GET',body,timeout=30000} = {}) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {method, headers:method === 'POST' ? {'Content-Type':'application/json','X-HSD-Token':window.HSD_TOKEN || ''} : {}, body:body === undefined ? undefined : JSON.stringify(body), signal:controller.signal, cache:'no-store'});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error('工具未能返回有效结果，请确认程序仍在运行。'); }
      if (!response.ok) {
        const error = new Error(data.error || `操作未完成（${response.status}），请重试。`);
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('等待超时，请稍后重试。');
      if (error instanceof TypeError) throw new Error('暂时无法连接本机工具，请确认程序仍在运行。');
      throw error;
    } finally { window.clearTimeout(timer); }
  }

  function notice(message) { $('notice-text').textContent = message; $('notice').classList.remove('hidden'); }
  function clearNotice() { $('notice').classList.add('hidden'); }
  let toastTimer;
  function toast(message) { $('toast').textContent=message; $('toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),3500); }
  function rememberJob(id) { try { if (id) sessionStorage.setItem('hsd-active-job',id); else sessionStorage.removeItem('hsd-active-job'); } catch (_) {} }
  function storedJob() { try { return sessionStorage.getItem('hsd-active-job'); } catch (_) { return null; } }
  function showView(id, step) {
    document.querySelectorAll('.view').forEach((view)=>view.classList.toggle('hidden',view.id !== id));
    document.querySelectorAll('.step').forEach((element)=>{const n=Number(element.dataset.step);element.classList.toggle('active',n===step);element.classList.toggle('complete',n<step);element.querySelector('i').textContent=n<step?'✓':n;});
    $('shutdown-button').disabled=isBusy() || state.resolving || state.picking;
  }
  function setSourceType(type) {
    state.sourceType=type;
    document.querySelectorAll('[data-source-type]').forEach((button)=>{const active=button.dataset.sourceType===type;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});
    $('source-browse').dataset.pick=type;
    $('source-browse').textContent=type==='zip'?'选择压缩包':'选择文件夹';
    $('source-path').placeholder=type==='zip'?'选择包含 AI 文件的 ZIP 压缩包':'选择包含 AI 文件的文件夹';
  }
  function updateNumberExample() {
    const value=Number($('start-number').value);
    $('number-example').textContent=Number.isInteger(value)&&value>=1&&value<=9999?`HSD${String(value).padStart(4,'0')}`:'请输入 1–9999';
  }
  function setFormBusy(busy) {
    $('import-form').querySelectorAll('button,input').forEach((element)=>element.disabled=busy);
    $('start-button').textContent=state.starting?'正在创建任务…':'开始匹配 →';
    $('shutdown-button').disabled=busy || isBusy();
  }
  async function pick(button) {
    if (state.picking || state.starting) return;
    state.picking=true; setFormBusy(true); clearNotice();
    const label=button.textContent; button.textContent='请选择…';
    try {
      const data=await api('/api/pick',{method:'POST',body:{kind:button.dataset.pick},timeout:600000});
      if (data.path) $(button.dataset.target).value=data.path;
    } catch(error) {notice(error.message);} finally {state.picking=false;button.textContent=label;setFormBusy(false);}
  }
  async function startJob(event) {
    event.preventDefault();
    if (state.starting || state.picking) return;
    clearNotice();
    const fields=[['workbook-path','请先选择图片编号表。'],['source-path','请先选择 AI 压缩包或文件夹。'],['output-path','请先选择结果保存位置。']];
    for (const [id,message] of fields) {if (!$(id).value.trim()) {notice(message);$(id).focus();return;}}
    const start=Number($('start-number').value);
    if (!Number.isInteger(start)||start<1||start>9999) {notice('起始流水号应为 1 到 9999 之间的整数。');$('start-number').focus();return;}
    state.starting=true;setFormBusy(true);
    try {
      const data=await api('/api/jobs',{method:'POST',body:{workbook_path:$('workbook-path').value.trim(),source_path:$('source-path').value.trim(),output_root:$('output-path').value.trim(),start_number:start}});
      state.job={id:data.id,status:'importing',progress:{message:'正在读取编号表与 AI 文件',current:0,total:0},rows:[],files:[]};
      state.filter='awaiting';state.search='';state.selectedRowId=null;state.selectedFileId=null;state.showDone=true;state.pollFailures=0;state.lastJobError=null;
      state.forceReview=false;state.candidatesOpen=false;state.history=[];
      $('row-search').value='';rememberJob(data.id);renderJob();schedulePoll(100);
    } catch(error) {notice(error.message);} finally {state.starting=false;setFormBusy(false);$('shutdown-button').disabled=isBusy();}
  }
  function schedulePoll(delay=1000) {clearTimeout(state.pollTimer);if (!state.stopped) state.pollTimer=setTimeout(pollJob,delay);}
  async function pollJob() {
    if (!state.job || state.stopped) return;
    const id=state.job.id;
    try {
      const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (state.job?.id !== id || state.stopped) return;
      if (state.pollFailures) clearNotice();
      state.pollFailures=0;acceptJob(job);renderJob();
      if (isBusy()) schedulePoll();
    } catch(error) {
      if (state.stopped || state.job?.id !== id) return;
      state.pollFailures++;
      notice(`${error.message} ${error.status===404?'请重新导入文件。':'工具会自动重试。'}`);
      if (error.status===404) {state.job=null;rememberJob(null);showView('import-view',1);} else {schedulePoll(Math.min(5000,1000*state.pollFailures));}
    }
  }
  function acceptJob(job) {
    const previousStatus=state.job?.status;
    state.job=job;
    if (job.error && job.error !== state.lastJobError && job.status !== 'error') {notice(job.error);state.lastJobError=job.error;}
    if (!job.error) state.lastJobError=null;
    if (!rowById(state.selectedRowId) || (['importing','matching'].includes(previousStatus) && job.status==='ready')) {
      const first=(job.rows||[]).find(awaiting) || (job.rows||[]).find((row)=>!matched(row)) || job.rows?.[0];
      selectRow(first?.id,null,false);
    }
    if (previousStatus === 'exporting' && job.status === 'done') state.history = [];
  }
  function renderJob() {
    if (!state.job) {showView('import-view',1);return;}
    const job=state.job;
    if (['importing','matching','exporting'].includes(job.status)) {renderProgress();return;}
    if (job.status==='error') {$('job-error').textContent=job.error||'文件处理失败，请检查文件是否有效后再试。';showView('error-view',1);return;}
    if (job.status==='done'&&state.showDone) {renderDone();return;}
    if (job.status==='ready' && counts().awaiting===0 && !state.forceReview) {renderSummary();return;}
    renderReview();
  }
  function renderProgress() {
    const job=state.job;
    const exporting=job.status==='exporting';
    showView('processing-view',exporting?3:2);
    $('processing-eyebrow').textContent=exporting?'正在保存本批结果':'正在自动寻找对应图片';
    $('processing-title').textContent=exporting?'正在整理并导出…':job.status==='matching'?'正在比对图片…':'正在读取文件…';
    $('processing-message').textContent=job.progress?.message||'请稍候';
    const current=Math.max(0,Number(job.progress?.current)||0),total=Math.max(0,Number(job.progress?.total)||0);
    const percent=total?Math.min(100,Math.round(current/total*100)):0;
    $('progress-fill').style.width=total?`${percent}%`:'';
    $('progress-fill').classList.toggle('indeterminate',!total);
    $('progress-percent').textContent=total?`${percent}%`:'';
    $('progress-detail').textContent=total?`${current} / ${total}`:'准备中…';
  }
  function counts() {
    const rows=state.job?.rows||[];
    const by=(status)=>rows.filter((row)=>row.status===status).length;
    const review=by('review'),unmatched=by('unmatched');
    return {
      total:rows.length,
      auto:by('auto'),
      confirmed:by('confirmed'),
      matched:rows.filter(matched).length,
      review,unmatched,
      skipped:by('skipped'),
      awaiting:review+unmatched,
      newNumbers:rows.filter((row)=>matched(row)&&!row.number&&row.planned_number).length,
    };
  }
  function renderSummary() {
    showView('summary-view',2);
    const c=counts(),job=state.job;
    const skippedNote=c.skipped?`；其中 ${c.skipped} 行按你的选择跳过，保持原状`:'';
    $('summary-eyebrow').textContent='自动匹配完成';
    $('summary-title').textContent=c.skipped?'可靠匹配已全部通过。':'本批图片都已对应好了。';
    $('summary-subtitle').textContent=c.skipped
      ?'没有需要人工判断的疑问项，可以确认摘要并导出。'
      :'所有图片都找到了可靠的对应文件，不需要逐张检查。确认摘要后即可导出。';
    $('summary-stats').innerHTML=`<div class="done-stat"><strong>${c.total}</strong><span>本批图片</span></div><div class="done-stat"><strong>${c.auto}</strong><span>自动通过</span></div><div class="done-stat"><strong>${c.confirmed}</strong><span>人工确认</span></div><div class="done-stat"><strong>${c.newNumbers}</strong><span>新增编号</span></div>`;
    $('summary-output').textContent=job.output_target||job.output_dir||'导入时选择的位置';
    $('summary-detail').textContent=`导出会生成编号表格、${c.matched} 个按编号命名的 AI 文件以及处理清单${skippedNote}。原始表格和原 AI 文件保持不变。`;
    $('summary-export-button').disabled=state.resolving;
    $('summary-browse-button').disabled=state.resolving;
    $('summary-new-task-button').disabled=state.resolving;
  }
  function renderStats() {
    const c=counts(),done=state.job.status==='done';
    $('stats-bar').innerHTML=`<div class="stat"><div class="stat-label">表格图片<small>本批需对应的图片</small></div><strong class="stat-value">${c.total}</strong></div><div class="stat good"><div class="stat-label">已匹配<small>自动 ${c.auto} · 人工 ${c.confirmed}</small></div><strong class="stat-value">${c.matched}</strong></div><div class="stat attention"><div class="stat-label">需要处理<small>待确认 / 未找到</small></div><strong class="stat-value">${c.awaiting}</strong></div><div class="stat quiet"><div class="stat-label">已跳过<small>保持原状，不占新号</small></div><strong class="stat-value">${c.skipped}</strong></div><div class="stat blue"><div class="stat-label">${done?'新增编号':'预计新增编号'}<small>已有编号保留原样</small></div><strong class="stat-value">${c.newNumbers}</strong></div>`;
    $('filter-awaiting-count').textContent=c.awaiting;
    $('filter-all-count').textContent=c.total;
    $('filter-matched-count').textContent=c.matched;
    $('filter-skipped-count').textContent=c.skipped;
  }
  function renderReview() {
    showView('review-view',state.job.status==='done'?3:2);
    const job=state.job,c=counts(),done=job.status==='done';
    $('batch-caption').textContent=`${job.workbook_name||'图片编号表'}${job.sheet_name?` · ${job.sheet_name}`:''}  /  ${job.source_name||'AI 文件'}`;
    $('review-title').textContent=c.awaiting?'处理这几项，其余已自动通过。':'全部匹配已确认。';
    $('review-subtitle').textContent=done
      ?'本批结果已导出。以下记录供查看。'
      :c.awaiting?`${c.total} 张图片中 ${c.auto+c.confirmed} 张已自动通过，只有下面 ${c.awaiting} 项需要你判断。`
      :'没有需要判断的项目，可以直接导出结果。';
    $('export-button').textContent=done?'查看导出结果 ↗':`导出结果 (${c.matched}) ↗`;
    $('export-button').disabled=state.resolving||(!done&&c.matched===0);
    $('new-task-button').disabled=state.resolving;
    $('undo-button').classList.toggle('hidden',!state.history.length||done);
    $('undo-button').disabled=state.resolving;
    renderStats();
    const warnings=job.warnings||[];
    $('warnings').classList.toggle('hidden',!warnings.length);
    $('warnings-summary').textContent=`有 ${warnings.length} 条处理提示，点击查看`;
    $('warnings-list').innerHTML=warnings.map((item)=>`<li>${escapeHtml(item)}</li>`).join('');
    renderTable();renderPanel();
  }
  function filteredRows() {
    const term=state.search.trim().toLowerCase();
    return (state.job?.rows||[]).filter((row)=>{
      if (state.filter==='awaiting'&&!awaiting(row)) return false;
      if (state.filter==='matched'&&!matched(row)) return false;
      if (state.filter==='skipped'&&row.status!=='skipped') return false;
      const file=fileById(row.file_id);
      return !term||[row.number,row.planned_number,row.row_number,file?.name,file?.relative_path].some((value)=>String(value||'').toLowerCase().includes(term));
    });
  }
  function rowHtml(row) {
    const file=fileById(row.file_id),number=numberFor(row),existing=!!row.number;
    const label=existing?'原编号':state.job.status==='done'?'新编号':'预计新号';
    const reason=row.status==='review'||row.status==='unmatched'?`<div class="record-reason">${escapeHtml(row.reason||'')}</div>`:'';
    return `<tr data-row-id="${escapeHtml(row.id)}" class="${row.id===state.selectedRowId?'active':''}" tabindex="0" aria-label="第 ${row.row_number} 行，${escapeHtml(number||'暂未编号')}，${escapeHtml(statusNames[row.status]||row.status)}" aria-selected="${row.id===state.selectedRowId}"><td><div class="row-image-cell">${imageTag('row',row.id,'row-thumb',`第 ${row.row_number} 行图片`)}<span class="row-number">第 ${row.row_number}<br>行</span></div></td><td><div class="record-number ${number?'':'missing'}">${escapeHtml(number||'暂未编号')}${number?`<span class="number-tag ${existing?'existing':'new'}">${label}</span>`:''}</div><div class="record-file" title="${escapeHtml(file?.relative_path||row.reason||'')}">${escapeHtml(file?.name||row.reason||'等待选择对应文件')}</div>${reason}</td><td><span class="status-badge status-${escapeHtml(row.status)}">${escapeHtml(statusNames[row.status]||'待处理')}</span></td><td aria-hidden="true">›</td></tr>`;
  }
  function renderTable() {
    const rows=filteredRows();
    const scroll=document.querySelector('.table-scroll');
    const offset=scroll?scroll.scrollTop:0;
    document.querySelectorAll('[data-filter]').forEach((button)=>{const active=button.dataset.filter===state.filter;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
    $('rows-body').innerHTML=rows.map(rowHtml).join('');
    $('table-empty').classList.toggle('hidden',!!rows.length);
    $('table-empty').textContent=state.filter==='awaiting'?'没有需要人工处理的记录。':'没有符合条件的记录';
    $('table-count').textContent=`显示 ${rows.length} / ${state.job.rows.length} 条`;
    if (scroll) scroll.scrollTop=offset;
  }
  function refreshRow(row) {
    const element=document.querySelector(`#rows-body tr[data-row-id="${CSS.escape(row.id)}"]`);
    if (!element) return false;
    element.outerHTML=rowHtml(row);
    return true;
  }
  function selectRow(id,fileId=null,render=true) {
    state.selectedRowId=id||null;
    const row=rowById(id);
    const best=(row?.candidates||[]).find((candidate)=>!ownerOf(candidate.file_id,id));
    state.selectedFileId=fileId||row?.file_id||best?.file_id||null;
    state.manualOpen=false;state.manualQuery='';state.candidatesOpen=false;
    if(render){renderTable();renderPanel();}
  }
  function tuneCompareLayout() {
    const grid=$('review-panel')?.querySelector('.compare-grid');
    if (!grid) return;
    let stacked=false;
    grid.querySelectorAll('img').forEach((image)=>{
      if (image.naturalWidth&&image.naturalHeight&&image.naturalWidth/image.naturalHeight>=2.4) stacked=true;
    });
    grid.classList.toggle('stacked',stacked);
  }
  function renderPanel() {
    const row=rowById(state.selectedRowId);
    if (!row) {$('review-panel').innerHTML='<div class="panel-empty"><span>▧</span>选择左侧记录<br>查看表格图片与 AI 预览</div>';return;}
    const readonly=state.job.status!=='ready',selected=fileById(state.selectedFileId),owner=selected?ownerOf(selected.id,row.id):null;
    const candidate=(row.candidates||[]).find((item)=>item.file_id===selected?.id);
    const score=candidate?`相似度 ${(candidate.score*100).toFixed(1)}%`:'';
    const already=matched(row)&&row.file_id===selected?.id;
    const reason=owner?`此文件已对应第 ${owner.row_number} 行，不能重复使用。`:row.reason||'请对照画面，选择对应的 AI 文件。';
    const candidates=(row.candidates||[]).slice(0,5);
    const others=candidates.filter((item)=>item.file_id!==state.selectedFileId);
    const selected_=candidates.find((item)=>item.file_id===state.selectedFileId);
    const otherList=state.candidatesOpen&&others.length?`<div class="candidate-list">${others.map((item)=>{
      const file=fileById(item.file_id);if(!file)return '';
      const used=ownerOf(file.id,row.id);
      return `<button type="button" class="candidate" data-candidate-id="${escapeHtml(file.id)}" aria-pressed="false" title="相似度 ${(item.score*100).toFixed(1)}% · ${escapeHtml(file.relative_path||file.name)}" ${state.resolving?'disabled':''}>${imageTag('file',file.id,'',file.name)}<span class="candidate-name">${escapeHtml(file.name)}</span>${used?`<span class="candidate-unavailable">第 ${used.row_number} 行已使用</span>`:''}</button>`;
    }).join('')}</div>`:'';
    const otherToggle=others.length?`<button type="button" class="candidate-toggle" id="candidate-toggle" aria-expanded="${state.candidatesOpen}">${state.candidatesOpen?'收起其他候选':`其他候选（${others.length}）`}</button>`:'';
    $('review-panel').innerHTML=`<div class="panel-heading"><div><p class="eyebrow">图片比对</p><h2>第 ${row.row_number} 行 <small>${escapeHtml(numberFor(row)||'待生成编号')}</small></h2></div><span class="status-badge status-${escapeHtml(row.status)}">${escapeHtml(statusNames[row.status]||'待处理')}</span></div><div class="panel-status ${!matched(row)||owner?'attention':''}">${escapeHtml(reason)}</div><div class="compare-grid"><div><div class="compare-label"><span>表格图片 · 点图放大</span></div><div class="preview-frame">${imageTag('row',row.id,'',`表格第 ${row.row_number} 行图片`)}</div><div class="compare-filename">${escapeHtml(state.job.sheet_name||'工作表')} · B${row.row_number}</div></div><div><div class="compare-label"><span>AI 文件预览${selected_?' · 最可能的对应':''}</span>${score?`<details class="score-note"><summary>依据</summary><span>${escapeHtml(score)}</span></details>`:''}</div><div class="preview-frame">${selected?imageTag('file',selected.id,'',selected.name):'<span class="preview-placeholder">还没有选中的文件<br>可在下方查找</span>'}</div><div class="compare-filename" title="${escapeHtml(selected?.relative_path||'')}">${escapeHtml(selected?.name||'请选择对应文件')}</div></div></div>${selected?.issue?`<p class="panel-note">文件提示：${escapeHtml(selected.issue)}</p>`:''}${!readonly?`<details class="manual-search" id="manual-search-details" ${state.manualOpen?'open':''}><summary>查找其他 AI 文件</summary><label class="search-box"><span aria-hidden="true">⌕</span><input id="file-search" type="search" placeholder="按原文件名搜索" aria-label="搜索其他 AI 文件" value="${escapeHtml(state.manualQuery)}"></label><div id="manual-results" class="manual-results"></div></details>`:''}<div class="panel-actions">${readonly?'<span class="panel-note">本批已导出，匹配结果仅供查看。</span>':`<button type="button" class="button button-secondary" id="skip-row-button" ${state.resolving||row.status==='skipped'?'disabled':''}>暂时跳过</button><button type="button" class="button button-primary" id="confirm-row-button" ${state.resolving||!selected||owner||already?'disabled':''}>${state.resolving?'正在保存…':already?'此匹配已通过':'确认对应此文件 ✓'}</button>`}</div>${otherToggle}${otherList}<p class="panel-note">${readonly?'':'跳过的行保持原状，也不会再出现在需要处理的列表里。'}</p>`;
    $('review-panel').querySelectorAll('.preview-frame').forEach((frame)=>{
      frame.setAttribute('role','button');frame.setAttribute('tabindex','0');frame.setAttribute('aria-label','放大比对图片');frame.title='点击放大比对';
      frame.addEventListener('click',openCompare);
      frame.addEventListener('keydown',(event)=>{if(['Enter',' '].includes(event.key)){event.preventDefault();openCompare();}});
    });
    tuneCompareLayout();
    $('review-panel').querySelectorAll('img').forEach((image)=>{
      if (!image.complete) image.addEventListener('load',tuneCompareLayout,{once:true});
    });
    if (!readonly) {
      renderManualFiles();
      $('manual-search-details').addEventListener('toggle',(event)=>state.manualOpen=event.currentTarget.open);
      $('file-search').addEventListener('input',(event)=>{state.manualQuery=event.target.value;renderManualFiles();});
      $('confirm-row-button').addEventListener('click',()=>resolveRow(state.selectedFileId));
      $('skip-row-button').addEventListener('click',()=>resolveRow(null));
    }
    const toggle=$('candidate-toggle');
    if (toggle) toggle.addEventListener('click',()=>{state.candidatesOpen=!state.candidatesOpen;renderPanel();});
  }
  function renderManualFiles() {
    const container=$('manual-results');if(!container)return;
    const query=state.manualQuery.trim().toLowerCase();
    const files=(state.job.files||[]).filter((file)=>!query||`${file.name} ${file.relative_path||''}`.toLowerCase().includes(query));
    container.innerHTML=files.length?files.slice(0,50).map((file)=>{
      const used=ownerOf(file.id,state.selectedRowId);
      return `<button type="button" class="manual-file ${state.selectedFileId===file.id?'selected':''}" data-candidate-id="${escapeHtml(file.id)}" ${state.resolving?'disabled':''} title="${escapeHtml(file.relative_path||file.name)}">${imageTag('file',file.id,'',file.name)}<span><b>${escapeHtml(file.name)}</b><small>${escapeHtml(used?`第 ${used.row_number} 行已使用`:file.issue||file.relative_path||'可选择')}</small></span></button>`;
    }).join('')+(files.length>50?'<div class="manual-empty">显示前 50 个结果，请输入文件名缩小范围。</div>':''):'<div class="manual-empty">没有找到符合条件的 AI 文件</div>';
  }
  function openCompare() {
    const row=rowById(state.selectedRowId),file=fileById(state.selectedFileId);
    if(!row)return;
    $('enlarged-pair').innerHTML=`<section><h3>表格图片 · 第 ${row.row_number} 行</h3><div class="enlarged-image">${imageTag('row',row.id,'',`第 ${row.row_number} 行表格图片`)}</div><p>${escapeHtml(state.job.sheet_name||'工作表')} · B${row.row_number}</p></section><section><h3>AI 文件预览</h3><div class="enlarged-image">${file?imageTag('file',file.id,'',file.name):'<span class="preview-placeholder">尚未选择对应文件</span>'}</div><p>${escapeHtml(file?.relative_path||file?.name||'')}</p></section>`;
    const pair=$('enlarged-pair');
    pair.querySelectorAll('img').forEach((image)=>{
      if (!image.complete) image.addEventListener('load',()=>{
        const box=image.closest('.enlarged-image');
        if (box&&image.naturalWidth&&image.naturalHeight&&image.naturalWidth/image.naturalHeight>=2.4) box.classList.add('wide');
      },{once:true});
      if (image.complete&&image.naturalWidth&&image.naturalHeight&&image.naturalWidth/image.naturalHeight>=2.4) image.closest('.enlarged-image')?.classList.add('wide');
    });
    $('compare-dialog').showModal();
  }
  function preloadNeighbours(row) {
    const rows=filteredRows();
    const index=rows.findIndex((item)=>item.id===row?.id);
    if (index<0) return;
    [rows[index+1],rows[index-1]].forEach((neighbour)=>{
      if (!neighbour) return;
      const preview=new Image();preview.src=previewUrl('row',neighbour.id);
      const fileId=neighbour.file_id||neighbour.candidates?.[0]?.file_id;
      if (fileId) {const filePreview=new Image();filePreview.src=previewUrl('file',fileId);}
    });
  }
  async function resolveRow(fileId) {
    if(state.resolving||state.job?.status!=='ready')return;
    const rowId=state.selectedRowId;
    const before=rowById(rowId);
    if (!before) return;
    state.resolving=true;clearNotice();renderPanel();$('export-button').disabled=true;$('new-task-button').disabled=true;$('shutdown-button').disabled=true;
    try {
      const job=await api(`/api/jobs/${encodeURIComponent(state.job.id)}/resolve`,{method:'POST',body:{row_id:rowId,file_id:fileId}});
      acceptJob(job);
      state.history.push(rowId);
      const current=rowById(rowId);
      const rows=job.rows||[],index=rows.findIndex((row)=>row.id===rowId);
      const remaining=[...rows.slice(index+1),...rows.slice(0,index)].find(awaiting);
      if (remaining) selectRow(remaining.id,null,false);
      else selectRow(current?.id,null,false);
      toast(fileId?'已确认对应文件，可随时撤销':'已跳过，该行保持原状');
      renderReview();
      preloadNeighbours(rowById(state.selectedRowId));
    } catch(error){notice(error.message);} finally {state.resolving=false;renderReview();}
  }
  async function undoLast() {
    const rowId=state.history[state.history.length-1];
    if (!rowId||state.resolving||state.job?.status!=='ready') return;
    state.resolving=true;clearNotice();$('undo-button').disabled=true;
    try {
      const job=await api(`/api/jobs/${encodeURIComponent(state.job.id)}/resolve`,{method:'POST',body:{row_id:rowId,revert:true}});
      acceptJob(job);
      state.history.pop();
      selectRow(rowId,null,false);
      toast('已撤销上一步操作');
      renderReview();
    } catch(error){notice(error.message);} finally {state.resolving=false;renderReview();}
  }
  function askConfirmation({title,description,confirm='确认',cancel='取消'}) {
    return new Promise((resolve)=>{
      const dialog=$('confirm-dialog');
      $('dialog-title').textContent=title;$('dialog-description').textContent=description;$('dialog-confirm').textContent=confirm;
      dialog.querySelector('[value="cancel"]').textContent=cancel;
      dialog.returnValue='cancel';
      dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});
      dialog.showModal();
    });
  }
  async function exportJob() {
    if (state.job.status==='done') {state.showDone=true;renderDone();return;}
    if (state.resolving||state.job.status!=='ready')return;
    const c=counts();
    const question=c.awaiting
      ?{title:`还有 ${c.awaiting} 项需要处理，仍要导出？`,description:`已匹配 ${c.matched} 条，其中 ${c.newNumbers} 条将生成新编号。\n未处理的行保持原状，并列入待处理清单。`,confirm:'导出已匹配部分',cancel:'返回处理'}
      :{title:'确认导出本批结果？',description:`自动通过 ${c.auto} 条、人工确认 ${c.confirmed} 条，共 ${c.newNumbers} 条将生成新编号。\n结果将保存到新文件夹，原始文件不变。`,confirm:'确认导出',cancel:'返回检查'};
    if (!await askConfirmation(question))return;
    clearNotice();
    state.job.status='exporting';state.job.progress={message:'正在生成编号表格、AI 文件和待处理清单',current:0,total:0};state.showDone=true;
    renderJob();
    try {
      await api(`/api/jobs/${encodeURIComponent(state.job.id)}/export`,{method:'POST',body:{}});
      schedulePoll(100);
    } catch(error){state.job.status='ready';notice(error.message);renderReview();}
  }
  function renderDone() {
    showView('done-view',3);
    const c=counts();
    $('done-stats').innerHTML=`<div class="done-stat"><strong>${c.matched}</strong><span>AI 文件已整理</span></div><div class="done-stat"><strong>${c.newNumbers}</strong><span>新增编号</span></div><div class="done-stat"><strong>${c.awaiting}</strong><span>留待处理</span></div><div class="done-stat"><strong>${c.skipped}</strong><span>已跳过</span></div>`;
    $('output-directory').textContent=state.job.output_dir||'保存位置尚未返回';
    $('done-summary').textContent=c.awaiting?`结果包含更新后的 Excel 表格、${c.matched} 个按编号命名的 AI 文件，以及待处理清单。剩余 ${c.awaiting} 行保持原状，请根据清单继续核对。`:`结果包含更新后的 Excel 表格、${c.matched} 个按编号命名的 AI 文件及处理清单。全部表格图片均已对应。`;
    $('open-output-button').disabled=!state.job.output_dir;
  }
  async function openOutput() {
    $('open-output-button').disabled=true;
    try {await api(`/api/jobs/${encodeURIComponent(state.job.id)}/open-output`,{method:'POST',body:{}});toast('已打开结果文件夹');} catch(error){notice(error.message);} finally {$('open-output-button').disabled=false;}
  }
  async function resetTask() {
    if(state.resolving||isBusy())return;
    if(state.job?.status==='ready'&&!await askConfirmation({title:'重新导入一批文件？',description:'当前匹配结果尚未导出。重新导入后需要重新检查匹配。原始文件保持不变。',confirm:'重新导入',cancel:'继续检查'}))return;
    clearTimeout(state.pollTimer);state.job=null;state.selectedRowId=null;state.selectedFileId=null;state.showDone=true;state.lastJobError=null;
    state.forceReview=false;state.candidatesOpen=false;state.history=[];state.filter='awaiting';
    rememberJob(null);clearNotice();showView('import-view',1);window.scrollTo({top:0,behavior:'smooth'});
  }
  async function shutdown() {
    if (isBusy()||state.resolving||state.picking||state.stopped)return;
    if (!await askConfirmation({title:'退出图号助手？',description:state.job?.status==='ready'?'当前匹配结果尚未导出，退出后需要重新处理。原始文件不受影响。':'退出后可以关闭此页面，下次使用时重新打开图号助手。',confirm:'退出工具',cancel:'继续使用'}))return;
    $('shutdown-button').disabled=true;
    try {
      await api('/api/shutdown',{method:'POST',body:{}});
      state.stopped=true;clearTimeout(state.pollTimer);rememberJob(null);clearNotice();showView('processing-view',3);
      $('shutdown-button').disabled=true;
      document.querySelector('.processing-symbol').innerHTML='<span style="color:var(--teal);font-size:28px">✓</span>';
      $('processing-eyebrow').textContent='本次使用已结束';$('processing-title').textContent='工具已退出';$('processing-message').textContent='可以关闭此页面。下次使用时，请重新打开图号助手。';
      document.querySelector('.progress-track').classList.add('hidden');document.querySelector('.progress-caption').classList.add('hidden');document.querySelector('.processing-footnote').classList.add('hidden');
    } catch(error){notice(error.message);$('shutdown-button').disabled=false;}
  }
  async function init() {
    setFormBusy(true);
    $('notice-close').addEventListener('click',clearNotice);
    document.querySelectorAll('.browse').forEach((button)=>button.addEventListener('click',()=>pick(button)));
    document.querySelectorAll('[data-source-type]').forEach((button)=>button.addEventListener('click',()=>setSourceType(button.dataset.sourceType)));
    $('start-number').addEventListener('input',updateNumberExample);$('import-form').addEventListener('submit',startJob);
    document.querySelectorAll('[data-filter]').forEach((button)=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;renderTable();}));
    $('row-search').addEventListener('input',(event)=>{state.search=event.target.value;renderTable();});
    $('rows-body').addEventListener('click',(event)=>{const row=event.target.closest('[data-row-id]');if(row&&!state.resolving)selectRow(row.dataset.rowId);});
    $('rows-body').addEventListener('keydown',(event)=>{if(['Enter',' '].includes(event.key)){const row=event.target.closest('[data-row-id]');if(row&&!state.resolving){event.preventDefault();selectRow(row.dataset.rowId);}}});
    $('review-panel').addEventListener('click',(event)=>{const candidate=event.target.closest('[data-candidate-id]');if(candidate&&!state.resolving){state.selectedFileId=candidate.dataset.candidateId;renderPanel();}});
    $('export-button').addEventListener('click',exportJob);$('open-output-button').addEventListener('click',openOutput);
    $('undo-button').addEventListener('click',undoLast);
    $('summary-export-button').addEventListener('click',exportJob);
    $('summary-browse-button').addEventListener('click',()=>{state.forceReview=true;renderReview();});
    ['new-task-button','next-task-button','retry-task-button','summary-new-task-button'].forEach((id)=>$(id).addEventListener('click',resetTask));
    $('back-results-button').addEventListener('click',()=>{state.showDone=false;state.forceReview=true;renderReview();});
    $('shutdown-button').addEventListener('click',shutdown);
    document.addEventListener('error',(event)=>{if(event.target instanceof HTMLImageElement)event.target.classList.add('image-broken');},true);
    try {
      const config=await api('/api/config');
      $('workbook-path').value=config.last_workbook||'';$('source-path').value=config.last_source||'';$('output-path').value=config.last_output||'';
      $('start-number').value=config.last_start||1;$('app-version').textContent=config.version||'1.0.0';
      if (config.last_source) setSourceType(/\.zip$/i.test(config.last_source)?'zip':'folder');
      updateNumberExample();
    } catch(error){notice(error.message);}
    const jobId=storedJob();
    if(jobId) {
      try {const job=await api(`/api/jobs/${encodeURIComponent(jobId)}`);acceptJob(job);renderJob();if(isBusy())schedulePoll();}
      catch(error){rememberJob(null);if(error.status!==404)notice(error.message);}
    }
    setFormBusy(false);
  }
  init().catch((error)=>notice(error.message||'界面加载遇到问题，请刷新页面重试。'));
})();
