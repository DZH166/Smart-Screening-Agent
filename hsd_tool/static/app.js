'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const isLan = () => window.HSD_ACCESS?.lan === true;
  // null means no application byte cap. Never restore an old fallback limit.
  const uploadLimits = {workbook:null,source:null,total:null};
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const state = {
    job: null, sourceType: 'zip', filter: 'awaiting', search: '',
    selectedRowId: null, selectedFileId: null, manualOpen: false, manualQuery: '',
    resolving: false, starting: false, uploading: false, picking: false, pollTimer: null, pollFailures: 0,
    showDone: true, stopped: false, lastJobError: null,
    forceReview: false, showSummary: false, candidatesOpen: false, history: [],
  };
  const uiMetrics={table_renders:0,detail_renders:0,row_selections:0};
  function uiMeasure(name,start){uiMetrics[name]=(uiMetrics[name]||0)+1;uiMetrics[name+'_ms']=Math.round((performance.now()-start)*100)/100;document.documentElement.dataset.hsdUiMetrics=JSON.stringify(uiMetrics);}
  function uiCount(name,amount=1){uiMetrics[name]=(uiMetrics[name]||0)+amount;document.documentElement.dataset.hsdUiMetrics=JSON.stringify(uiMetrics);}
  let indexedJob=null,indexedJobId=null,countedJob=null,countedValue=null;
  let filesIndex=new Map(),rowsIndex=new Map(),ownersIndex=new Map();
  const preloaded=new Set(),imageAspects=new Map(),rowViewState=new Map();
  function ensureIndexes(){
    if(indexedJob===state.job)return;
    if(indexedJobId!==state.job?.id){preloaded.clear();imageAspects.clear();rowViewState.clear();}
    indexedJobId=state.job?.id;
    indexedJob=state.job;
    filesIndex=new Map((state.job?.files||[]).map((file)=>[file.id,file]));
    rowsIndex=new Map((state.job?.rows||[]).map((row)=>[row.id,row]));
    ownersIndex=new Map();for(const row of state.job?.rows||[]){if(matched(row)){if(!ownersIndex.has(row.file_id))ownersIndex.set(row.file_id,[]);ownersIndex.get(row.file_id).push(row);}}
  }
  const statusNames = {auto:'自动通过', confirmed:'已确认', review:'待确认', unmatched:'未找到', skipped:'已跳过'};
  const matched = (row) => ['auto','confirmed'].includes(row.status) && !!row.file_id;
  const awaiting = (row) => ['review','unmatched'].includes(row.status);
  const isBusy = () => ['queued','importing','matching','ai_review','exporting'].includes(state.job?.status) || state.starting;
  const fileById = (id) => {ensureIndexes();return filesIndex.get(id);};
  const rowById = (id) => {ensureIndexes();return rowsIndex.get(id);};
  const ownerOf = (id,rowId) => {ensureIndexes();return ownersIndex.get(id)?.find((row)=>row.id!==rowId)||null;};
  const previewUrl = (type,id) => `/api/jobs/${encodeURIComponent(state.job.id)}/image/${type}/${encodeURIComponent(id)}`;
  const imageTag = (type,id,className,alt) => `<img src="${previewUrl(type,id)}${className==='row-thumb'||className==='candidate-thumb'?'?size=thumb':''}" class="${className}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async">`;
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
    document.body.classList.toggle('review-active',id==='review-view');
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
    ['workbook-path','source-path','output-path'].forEach((id)=>$(id).disabled=busy||isLan());
    ['workbook-upload','source-upload'].forEach((id)=>$(id).disabled=busy||!isLan());
    $('start-button').textContent=state.uploading?'正在上传…':state.starting?'正在创建任务…':isLan()?'上传并自动处理 →':'开始自动处理 →';
    $('shutdown-button').disabled=busy || isBusy();
  }
  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)||bytes<0) return '大小未知';
    const units=['B','KiB','MiB','GiB','TiB','PiB'];
    let amount=bytes,index=0;
    while(amount>=1024&&index<units.length-1){amount/=1024;index++;}
    return `${index===0?amount.toFixed(0):amount.toFixed(index>=3?2:1)} ${units[index]}`;
  }
  function uploadFileError(kind,file) {
    const workbook=kind==='workbook';
    if (!file) return workbook?'请先选择你电脑上的图片编号表。':'请先选择包含 AI 文件的 ZIP 压缩包。';
    if (!(workbook?/\.xlsx$/i:/\.zip$/i).test(file.name)) return workbook?'图片编号表需要是 .xlsx 文件。':'AI 文件请先压缩成 .zip 文件后上传。';
    if (!file.size) return '所选文件为空，请重新选择。';
    const limit=uploadLimits[kind];
    if (limit!==null&&file.size>limit) return `${workbook?'图片编号表':'AI 压缩包'}不能超过 ${formatBytes(limit)}。`;
    return '';
  }
  function updateUploadSelection(id) {
    const input=$(id),file=input.files?.[0];
    $(id+'-name').textContent=file?`${file.name} · ${formatBytes(file.size)}`:'未选择文件';
    const kind=id==='workbook-upload'?'workbook':'source';
    fieldError(id,file?uploadFileError(kind,file):'');
  }
  function fieldError(id,message){const target=$(id+'-error');if(target){target.textContent=message;target.classList.toggle('hidden',!message);}$(id)?.setAttribute?.('aria-invalid',String(!!message));}
  function clearFieldErrors(){['workbook-upload','source-upload','start-number','local-workbook','local-source','local-output'].forEach((id)=>{const target=$(id+'-error');if(target){target.textContent='';target.classList.add('hidden');}});}
  function validateUploadFiles(workbook,source) {
    const error=uploadFileError('workbook',workbook)||uploadFileError('source',source);
    if (error) return error;
    if (uploadLimits.total!==null&&workbook.size+source.size>uploadLimits.total) return `表格和 ZIP 合计不能超过 ${formatBytes(uploadLimits.total)}。`;
    return '';
  }
  function renderUploadProgress(event) {
    const known=event?.lengthComputable&&event.total>0;
    const percent=known?Math.min(100,Math.round(event.loaded/event.total*100)):0;
    $('upload-progress').classList.remove('hidden');
    const fill=$('upload-progress-fill'),width=known?`${percent}%`:'';
    if(fill.style.width!==width)fill.style.width=width;
    fill.classList.toggle('indeterminate',!known);
    for(const [id,text] of [
      ['upload-progress-percent',known?`${percent}%`:''],
      ['upload-progress-label',known&&event.loaded>=event.total?'上传完成，正在检查文件…':'正在上传文件…'],
      ['upload-progress-detail',known?`${formatBytes(event.loaded)} / ${formatBytes(event.total)} · 请保持页面打开，上传完成后自动处理。`:'请保持此页面打开，上传完成后自动处理。'],
    ]){
      const element=$(id);
      if(element.textContent!==text)element.textContent=text;
    }
  }
  function uploadFiles(workbook,source,start) {
    return new Promise((resolve,reject)=>{
      const data=new FormData();
      data.append('workbook',workbook);data.append('source',source);data.append('start_number',String(start));
      const request=new XMLHttpRequest();
      request.open('POST','/api/jobs/upload');
      request.setRequestHeader('X-HSD-Token',window.HSD_TOKEN||'');
      // Large transfers can take longer than 30 minutes; connection and abort
      // events still fail visibly without an artificial browser time ceiling.
      request.timeout=0;
      request.upload.addEventListener('progress',renderUploadProgress);
      request.addEventListener('load',()=>{
        let result;
        try {result=JSON.parse(request.responseText);} catch (_) {reject(new Error('上传未能返回有效结果，请确认主机仍在运行后重试。'));return;}
        if (request.status<200||request.status>=300) {const error=new Error(result.error||`上传未完成（${request.status}），请重试。`);error.status=request.status;reject(error);return;}
        if (!result.id) {reject(new Error('上传结果缺少批次编号，请重试。'));return;}
        resolve(result);
      });
      request.addEventListener('error',()=>reject(new Error('上传连接中断，请确认与主机处于同一局域网后重试。')));
      request.addEventListener('timeout',()=>reject(new Error('上传超时，请检查网络或拆分压缩包后重试。')));
      request.addEventListener('abort',()=>reject(new Error('上传已中止，请重新上传。')));
      renderUploadProgress();request.send(data);
    });
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
    clearNotice();clearFieldErrors();
    const workbook=$('workbook-upload').files?.[0],source=$('source-upload').files?.[0];
    if (isLan()) {
      const error=validateUploadFiles(workbook,source);
      if (error) {const id=uploadFileError('workbook',workbook)?'workbook-upload':'source-upload';fieldError(id,error);$(id).focus();return;}
    } else {
      const fields=[['workbook-path','请先选择图片编号表。'],['source-path','请先选择 AI 压缩包或文件夹。'],['output-path','请先选择结果保存位置。']];
      for (const [id,message] of fields) {if (!$(id).value.trim()) {const target=$('local-'+id.replace('-path','')+'-error');if(target){target.textContent=message;target.classList.remove('hidden');}$(id).focus();return;}}
    }
    const start=Number($('start-number').value);
    if (!Number.isInteger(start)||start<1||start>9999) {fieldError('start-number','请输入 1 到 9999 的整数。');$('start-number').focus();return;}
    state.starting=true;state.uploading=isLan();setFormBusy(true);
    try {
      const data=isLan()?await uploadFiles(workbook,source,start):await api('/api/jobs',{method:'POST',body:{workbook_path:$('workbook-path').value.trim(),source_path:$('source-path').value.trim(),output_root:$('output-path').value.trim(),start_number:start}});
      state.job={id:data.id,status:isLan()?'queued':'importing',progress:{message:isLan()?'文件已上传，正在准备处理':'正在读取编号表与 AI 文件',current:0,total:0},rows:[],files:[]};
      state.filter='awaiting';state.search='';state.selectedRowId=null;state.selectedFileId=null;state.showDone=true;state.pollFailures=0;state.lastJobError=null;
      state.forceReview=false;state.showSummary=false;state.candidatesOpen=false;state.history=[];
      $('row-search').value='';rememberJob(data.id);renderJob();schedulePoll(100);
    } catch(error) {notice(error.message);} finally {state.starting=false;state.uploading=false;$('upload-progress').classList.add('hidden');setFormBusy(false);$('shutdown-button').disabled=isBusy();}
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
      if ([401,403,404].includes(error.status)) {clearTimeout(state.pollTimer);state.job=null;rememberJob(null);showView('import-view',1);notice(error.status===404?'任务已不存在，请重新导入文件。':'员工会话已失效，请刷新页面重新进入。');} else {schedulePoll(Math.min(5000,1000*state.pollFailures));}
    }
  }
  function acceptJob(job) {
    const previousStatus=state.job?.status;
    state.job=job;indexedJob=null;countedJob=null;
    if (job.error && job.error !== state.lastJobError && job.status !== 'error') {notice(job.error);state.lastJobError=job.error;}
    if (!job.error) state.lastJobError=null;
    if (!rowById(state.selectedRowId) || (['queued','importing','matching','ai_review'].includes(previousStatus) && job.status==='ready')) {
      const first=(job.rows||[]).find(awaiting) || (job.rows||[]).find((row)=>!matched(row)) || job.rows?.[0];
      selectRow(first?.id,null,false);
    }
    if (previousStatus === 'ai_review' && job.status === 'ready') {state.showSummary=false;state.forceReview=false;state.filter='awaiting';}
    if (previousStatus === 'exporting' && job.status === 'done') state.history = [];
  }
  function renderJob() {
    if (!state.job) {showView('import-view',1);return;}
    const job=state.job;
    if (['queued','importing','matching','ai_review','exporting'].includes(job.status)) {renderProgress();return;}
    if (job.status==='error') {$('job-error').textContent=job.error||'文件处理失败，请检查文件是否有效后再试。';showView('error-view',1);return;}
    if (job.status==='done'&&state.showDone) {renderDone();return;}
    if (job.status==='ready' && (state.showSummary || (counts().review===0 && !state.forceReview))) {renderSummary();return;}
    renderReview();
  }
  function renderProgress() {
    const job=state.job;
    const exporting=job.status==='exporting';
    const queued=job.status==='queued';
    const phase=job.progress?.phase;
    const retrieving=phase==='ai_retrieval',verifying=phase==='local_verification',parallel=phase==='parallel_verification';
    const queueStage={cpu:'本机处理',ai:job.matching_mode==='ai_first'?'AI 查找':'AI 复核',export:'导出'}[job.queue_stage]||'处理';
    showView('processing-view',exporting||(queued&&job.queue_stage==='export')?3:2);
    $('processing-eyebrow').textContent=queued?'排队中':exporting?'导出结果':parallel?'同时处理':retrieving?'AI 查找':verifying?'本机核验':job.status==='ai_review'?'复核疑难项':job.status==='matching'?'匹配图片':'读取文件';
    $('processing-title').textContent=queued?`等待${queueStage}…`:exporting?'正在整理并导出…':parallel?'AI 查找与本机核验进行中…':retrieving?'AI 正在查找对应图片…':verifying?'正在核验图案与文件…':job.status==='ai_review'?'正在复核有疑问的图片…':job.status==='matching'?'正在比对图片…':'正在读取文件…';
    $('processing-message').textContent=queued?(job.queue_position?`${queueStage}队列第 ${job.queue_position} 位，轮到后会自动开始。`:`正在等待${queueStage}，轮到后会自动开始。`):job.progress?.message||(parallel?'AI 查找候选与本机核验同时进行，完成后自动汇总结果。':retrieving?'正在查找候选，完成后自动汇总本机核验结果。':verifying?'正在核验图案、颜色和文件归属，只有验证可靠的匹配才会通过。':job.status==='ai_review'?'正在复核可处理的疑难图片，完成后会自动进入下一步。':'完成后会自动进入下一步。');
    const current=queued||parallel?0:Math.max(0,Number(job.progress?.current)||0),total=queued||parallel?0:Math.max(0,Number(job.progress?.total)||0);
    const percent=total?Math.min(100,Math.round(current/total*100)):0;
    $('progress-fill').style.width=total?`${percent}%`:'';
    $('progress-fill').classList.toggle('indeterminate',!total);
    $('progress-percent').textContent=total?`${percent}%`:'';
    $('progress-detail').textContent=total?`当前阶段 ${current} / ${total}`:queued?'等待开始':parallel?'两项进度分别计数':'准备中…';
  }
  function counts() {
    if(countedJob===state.job&&countedValue)return countedValue;
    const result={total:0,auto:0,aiAuto:0,localAuto:0,confirmed:0,matched:0,review:0,unmatched:0,skipped:0,awaiting:0,newNumbers:0};
    let aiRows=0;
    for(const row of state.job?.rows||[]){
      result.total++;
      if(Object.hasOwn(result,row.status))result[row.status]++;
      if(matched(row)){result.matched++;if(!row.number&&row.planned_number)result.newNumbers++;}
      if(row.status==='auto'&&row.ai_review?.outcome==='auto_passed')aiRows++;
    }
    result.aiAuto=Math.min(result.auto,Number(state.job?.stats?.ai_auto??aiRows));
    result.localAuto=Math.max(0,result.auto-result.aiAuto);
    result.awaiting=result.review+result.unmatched;
    countedJob=state.job;countedValue=result;return result;
  }
  function renderSummary() {
    showView('summary-view',3);state.showSummary=true;
    const c=counts(),job=state.job,pending=c.awaiting+c.skipped;
    $('summary-eyebrow').textContent='处理完成';
    $('summary-title').textContent=c.matched?'确认本批结果':'暂无可导出结果';
    $('summary-subtitle').textContent=pending?'未处理和跳过的项目不计入可导出文件。':'没有需要人工判断的项目。';
    $('summary-stats').innerHTML=`<div class="done-stat"><strong>${c.matched}</strong><span>可导出</span></div><div class="done-stat"><strong>${c.newNumbers}</strong><span>新增编号</span></div><div class="done-stat"><strong>${pending}</strong><span>未处理 / 跳过</span></div>`;
    const breakdown=$('summary-breakdown');
    if(breakdown)breakdown.innerHTML=`<dl class="processing-breakdown"><div><dt>处理方式</dt><dd>${job.matching_mode==='ai_first'?'AI 查找对应图片 + 本机核验':'本机匹配'}</dd></div><div><dt>本批图片</dt><dd>${c.total}</dd></div><div><dt>本机自动通过</dt><dd>${c.localAuto}</dd></div><div><dt>AI 条件通过</dt><dd>${c.aiAuto}</dd></div><div><dt>员工确认</dt><dd>${c.confirmed}</dd></div><div><dt>待审核 / 无法处理 / 已跳过</dt><dd>${c.review} / ${c.unmatched} / ${c.skipped}</dd></div></dl>`;
    $('summary-output').textContent=isLan()?'导出完成后下载 ZIP 到你的电脑':job.output_target||job.output_root||job.output_dir||'导入时选择的位置';
    $('summary-detail').textContent=pending?`待审核 ${c.review} 项、无法处理 ${c.unmatched} 项、已跳过 ${c.skipped} 项，原始行保持原状，不填写新号。`:'';
    $('summary-detail').classList.toggle('hidden',!pending);
    $('summary-export-button').disabled=state.resolving||c.matched===0;
    $('summary-browse-button').disabled=state.resolving;
    $('summary-continue-button').classList.toggle('hidden',c.awaiting===0);
    $('summary-continue-button').disabled=state.resolving;
    $('summary-new-task-button').disabled=state.resolving;
    $('summary-undo-button').classList.toggle('hidden',!(job.can_undo??state.history.length));$('summary-undo-button').disabled=state.resolving;
    renderAiOverview();
  }
  function renderAiOverview() {
    const info=state.job?.ai_review;
    const retrieval=state.job?.ai_retrieval;
    const aiFirst=state.job?.matching_mode==='ai_first';
    const targets=['job-ai-overview','summary-ai-overview','done-ai-overview'];
    for(const id of targets){
      const element=$(id);
      if(!info&&!aiFirst){element.classList.add('hidden');element.replaceChildren();delete element.dataset.content;continue;}
      element.classList.remove('hidden');
      let retrievalHtml='';
      if(aiFirst){
        const usage=window.HSDAI?.usageText(retrieval?.usage);
        retrievalHtml=`<div><strong>DeepSeek 查找对应图片</strong><p>${escapeHtml(retrieval?.message||'由 AI 查找候选，本机核验图案、颜色和文件归属后决定是否通过。')}</p>${usage?`<p class="ai-job-cost">${escapeHtml(usage.cost)}${usage.unknown?` · ${escapeHtml(usage.unknown)}`:''}</p>`:''}</div>`;
      }
      if(!info){if(element.dataset.content!==retrievalHtml){element.innerHTML=retrievalHtml;element.dataset.content=retrievalHtml;}continue;}
      const evaluation=info.mode!=='validated';
      const reviewed=Number(info.reviewed||0),same=Number(info.suggested_same||0),passed=Number(info.auto_passed||0);
      const title=evaluation?'DeepSeek 二次复核 · 评估运行':'DeepSeek 二次复核 · 经验证模式';
      const summary=reviewed?(evaluation?`已复核 ${reviewed} 项，建议相同 ${same} 项；建议仍需人工确认。`:`已复核 ${reviewed} 项，${passed} 项满足条件自动通过，其余由人工处理。`):(info.message||'本批尚未调用 AI 复核。');
      const usage=window.HSDAI?.usageText(info.usage);
      const cost=usage?`<p class="ai-job-cost">${escapeHtml(usage.cost)}${usage.unknown?` · ${escapeHtml(usage.unknown)}`:''}</p>`:'';
      const html=`${retrievalHtml}<div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(summary)}</p>${cost}</div>${state.job.status==='ready'&&info.can_retry===true?`<button type="button" class="button button-secondary" data-ai-retry ${state.resolving?'disabled':''}>对此批运行 AI 复核</button>`:''}`;
      if(element.dataset.content!==html){element.innerHTML=html;element.dataset.content=html;}
    }
  }
  async function retryAiReview(){
    if(state.resolving||isBusy()||state.job?.status!=='ready'||state.job.ai_review?.can_retry!==true)return;
    clearNotice();state.job.status='ai_review';state.job.progress={message:'正在准备符合条件的图片复核',current:0,total:0};state.forceReview=false;state.showSummary=false;renderJob();
    try{await api(`/api/jobs/${encodeURIComponent(state.job.id)}/ai-review`,{method:'POST',body:{}});schedulePoll(100);}
    catch(error){state.job.status='ready';try{acceptJob(await api(`/api/jobs/${encodeURIComponent(state.job.id)}`));}catch(_){}notice(error.message);renderJob();if(isBusy())schedulePoll();}
  }
  function renderStats() {
    const c=counts();
    $('stats-bar').innerHTML=`<strong>剩余 ${c.awaiting} 项需要处理</strong><span>已完成 ${c.matched} / ${c.total}</span>${c.skipped?`<span>已跳过 ${c.skipped}</span>`:''}`;
    $('filter-awaiting-count').textContent=c.awaiting;$('filter-all-count').textContent=c.total;
    $('filter-matched-count').textContent=c.matched;$('filter-skipped-count').textContent=c.skipped;
  }
  function renderReview() {
    showView('review-view',state.job.status==='done'?3:2);
    const job=state.job,c=counts(),done=job.status==='done';
    $('batch-caption').textContent=`${job.workbook_name||'图片编号表'}${job.sheet_name?` · ${job.sheet_name}`:''}  /  ${job.source_name||'AI 文件'}`;
    $('review-title').textContent=done?'本批记录':'处理疑难项';
    $('review-subtitle').textContent=done?'已导出，仅供查看。':c.awaiting?'对照图片后确认，无法确定可以跳过。':'可以直接查看摘要并导出。';
    $('export-button').textContent=done?'查看导出结果 ↗':'查看结果摘要 →';
    $('export-button').disabled=state.resolving||(!done&&c.matched===0);
    $('new-task-button').disabled=state.resolving;
    $('undo-button').classList.toggle('hidden',!(state.job.can_undo ?? state.history.length)||done);
    $('undo-button').disabled=state.resolving;
    renderStats();
    const warnings=job.warnings||[];
    $('warnings').classList.toggle('hidden',!warnings.length);
    $('warnings-summary').textContent=`有 ${warnings.length} 条处理提示，点击查看`;
    $('warnings-list').innerHTML=warnings.map((item)=>`<li>${escapeHtml(item)}</li>`).join('');
    renderTable();renderPanel();renderAiOverview();scheduleReviewLayout();
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
    const reason='';
    return `<tr data-row-id="${escapeHtml(row.id)}" class="${row.id===state.selectedRowId?'active':''}" tabindex="0" aria-label="第 ${row.row_number} 行，${escapeHtml(number||'暂未编号')}，${escapeHtml(statusNames[row.status]||row.status)}" aria-selected="${row.id===state.selectedRowId}"><td><div class="row-image-cell">${imageTag('row',row.id,'row-thumb',`第 ${row.row_number} 行图片`)}<span class="row-number">第 ${row.row_number}<br>行</span></div></td><td><div class="record-number ${number?'':'missing'}">${escapeHtml(number||'暂未编号')}${number?`<span class="number-tag ${existing?'existing':'new'}">${label}</span>`:''}</div><div class="record-file" title="${escapeHtml(file?.relative_path||row.reason||'')}">${escapeHtml(file?.name||'等待选择对应文件')}</div>${reason}</td><td><span class="status-badge status-${escapeHtml(row.status)}">${escapeHtml(statusNames[row.status]||'待处理')}</span></td><td aria-hidden="true">›</td></tr>`;
  }
  function renderTable() {
    const renderStarted=performance.now(),rows=filteredRows(),body=$('rows-body');
    const scroll=document.querySelector('.table-scroll'),offset=scroll?.scrollTop||0;
    document.querySelectorAll('[data-filter]').forEach((button)=>{const active=button.dataset.filter===state.filter;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
    if(body.dataset.jobId!==state.job.id){body.replaceChildren();body.dataset.jobId=state.job.id;uiCount('table_full_rebuilds');}
    const existing=new Map(Array.from(body.children).map((node)=>[node.dataset.rowId,node]));
    const visibleIds=new Set(rows.map((row)=>row.id));
    for(const [id,node] of existing){if(!visibleIds.has(id)){node.remove();existing.delete(id);}}
    let cursor=body.firstElementChild;
    for(const row of rows){
      let node=existing.get(row.id);existing.delete(row.id);
      const file=fileById(row.file_id);
      const key=JSON.stringify([row.status,row.number,row.planned_number,row.reason,file?.name,file?.relative_path,state.job.status==='done']);
      if(!node||node.dataset.renderKey!==key){
        const template=document.createElement('template');template.innerHTML=rowHtml(row);const replacement=template.content.firstElementChild;
        replacement.dataset.renderKey=key;
        if(node){if(cursor===node)cursor=replacement;node.replaceWith(replacement);}node=replacement;uiCount('table_rows_patched');
      }
      const active=row.id===state.selectedRowId;if(node.classList.contains('active')!==active)node.classList.toggle('active',active);if(node.getAttribute('aria-selected')!==String(active))node.setAttribute('aria-selected',String(active));
      if(node===cursor)cursor=cursor.nextElementSibling;else body.insertBefore(node,cursor);
    }
    for(const node of existing.values())node.remove();
    $('table-empty').classList.toggle('hidden',!!rows.length);
    $('table-empty').textContent=state.filter==='awaiting'?'没有需要处理的项目。':'没有符合条件的记录';
    $('table-count').textContent=`显示 ${rows.length} / ${state.job.rows.length} 条`;
    if(scroll)scroll.scrollTop=offset;
    uiMeasure('table_renders',renderStarted);
  }
  function rememberPanel() {
    const panel=$('review-panel'),id=panel.dataset.rowId;
    if(!id)return;
    rowViewState.set(id,{scroll:panel.querySelector('.panel-content')?.scrollTop||0,
      details:Array.from(panel.querySelectorAll('details[data-detail-key]')).filter((item)=>item.open).map((item)=>item.dataset.detailKey),
      manualOpen:state.manualOpen,manualQuery:state.manualQuery,candidatesOpen:state.candidatesOpen,selectedFileId:state.selectedFileId});
  }
  function selectRow(id,fileId=null,render=true) {
    const selectionStarted=performance.now();
    if(render)rememberPanel();
    state.selectedRowId=id||null;
    const row=rowById(id);
    const best=(row?.candidates||[]).find((candidate)=>!ownerOf(candidate.file_id,id));
    const view=rowViewState.get(id);
    state.selectedFileId=fileId||row?.file_id||(fileById(view?.selectedFileId)?view.selectedFileId:null)||best?.file_id||null;
    state.manualOpen=view?.manualOpen||false;state.manualQuery=view?.manualQuery||'';state.candidatesOpen=view?.candidatesOpen||false;
    if(render){document.querySelectorAll('#rows-body tr').forEach((element)=>{const active=element.dataset.rowId===state.selectedRowId;if(element.classList.contains('active')!==active)element.classList.toggle('active',active);if(element.getAttribute('aria-selected')!==String(active))element.setAttribute('aria-selected',String(active));});renderPanel();}
    uiMeasure('row_selections',selectionStarted);
  }
  function tuneCompareLayout() {
    const grid=$('review-panel')?.querySelector('.compare-grid');
    if (!grid) return;
    let stacked=false,known=true;
    grid.querySelectorAll('img').forEach((image)=>{
      const ratio=image.naturalWidth&&image.naturalHeight?image.naturalWidth/image.naturalHeight:imageAspects.get(image.getAttribute('src'));
      if(ratio){imageAspects.set(image.getAttribute('src'),ratio);if(ratio>=2.4)stacked=true;}else known=false;
    });
    grid.classList.toggle('stacked',stacked||!known);
  }
  let reviewLayoutFrame = null;
  function scheduleReviewLayout() {
    if (reviewLayoutFrame !== null) return;
    reviewLayoutFrame = requestAnimationFrame(() => {
      reviewLayoutFrame = null;
      const panel=$('review-panel');
      if (!panel || $('review-view').classList.contains('hidden')) return;
      // Account for the actual header, notice and AI summary height. The action
      // footer occupies its own row; scrolling content never sits behind it.
      const height=Math.max(180,Math.floor(window.innerHeight-panel.getBoundingClientRect().top-14));
      if(panel.style.getPropertyValue?.('--review-panel-height')!==`${height}px`){
        panel.style.setProperty('--review-panel-height',`${height}px`);
        panel.closest('.review-layout')?.style.setProperty('--review-panel-height',`${height}px`);
      }
      const actions=panel.querySelector('.panel-actions');
      if (actions) {
        const bounds=actions.getBoundingClientRect();
        document.documentElement.dataset.hsdReviewLayout=JSON.stringify({viewport_height:window.innerHeight,panel_height:height,actions_top:Math.round(bounds.top),actions_bottom:Math.round(bounds.bottom),actions_visible:bounds.top>=0&&bounds.bottom<=window.innerHeight});
      }
    });
  }
  function renderPanel() {
    const panelStarted=performance.now();
    const row=rowById(state.selectedRowId);
    if (!row) {$('review-panel').innerHTML='<div class="panel-empty"><span>▧</span>选择左侧记录<br>查看表格图片与 AI 预览</div>';return;}
    const panel=$('review-panel');
    if(panel.dataset.rowId===row.id)rememberPanel();
    const view=rowViewState.get(row.id);
    panel.dataset.rowId=row.id;
    const readonly=state.job.status!=='ready';
    panel.innerHTML=`<div class="panel-heading"><div><h2>第 ${row.row_number} 行 <small>${escapeHtml(numberFor(row)||'待生成编号')}</small></h2></div><span class="status-badge status-${escapeHtml(row.status)}">${escapeHtml(statusNames[row.status]||'待处理')}</span></div>
      <div class="panel-content" tabindex="0" aria-label="图片、复核建议与其他候选">
        <div class="panel-status"></div>
        <div id="candidate-issue"></div><div id="ai-row-advice"></div><div id="other-candidates-slot"></div>
        <div class="compare-grid stacked"><div><div class="compare-label"><span>表格图片 · 点图放大</span></div><div class="preview-frame">${imageTag('row',row.id,'',`表格第 ${row.row_number} 行图片`)}</div></div><div id="candidate-comparison"></div></div>
        ${!readonly?`<details class="manual-search" id="manual-search-details" ${state.manualOpen?'open':''}><summary>查找其他 AI 文件</summary><label class="search-box"><span aria-hidden="true">⌕</span><input id="file-search" type="search" placeholder="按原文件名搜索" aria-label="搜索其他 AI 文件" value="${escapeHtml(state.manualQuery)}"></label><div id="manual-results" class="manual-results"></div></details>`:''}
      </div>
      <div class="panel-footer"><div class="panel-actions">${readonly?'<span class="panel-note">本批已导出，匹配结果仅供查看。</span>':'<button type="button" class="button button-secondary" id="skip-row-button">暂时跳过</button><button type="button" class="button button-primary" id="confirm-row-button">确认对应此文件 ✓</button>'}</div></div>`;
    renderCandidateView();
    panel.querySelectorAll('details[data-detail-key]').forEach((item)=>item.open=(view?.details||[]).includes(item.dataset.detailKey));
    panel.querySelector('.panel-content').scrollTop=view?.scroll||0;
    bindPreviewFrames(panel);
    if (!readonly) {
      if(state.manualOpen)renderManualFiles();
      $('manual-search-details').addEventListener('toggle',(event)=>{state.manualOpen=event.currentTarget.open;if(state.manualOpen)renderManualFiles();});
      $('file-search').addEventListener('input',(event)=>{state.manualQuery=event.target.value;clearTimeout(manualSearchTimer);manualSearchTimer=setTimeout(renderManualFiles,120);});
      $('confirm-row-button').addEventListener('click',()=>resolveRow(state.selectedFileId));
      $('skip-row-button').addEventListener('click',()=>resolveRow(null));
    }
    scheduleReviewLayout();uiMeasure('detail_renders',panelStarted);
  }
  function bindPreviewFrames(container) {
    container.querySelectorAll('.preview-frame').forEach((frame)=>{
      if(frame.dataset.bound)return;frame.dataset.bound='true';
      frame.setAttribute('role','button');frame.setAttribute('tabindex','0');frame.setAttribute('aria-label','放大比对图片');frame.title='点击放大比对';
      frame.addEventListener('click',openCompare);
      frame.addEventListener('keydown',(event)=>{if(['Enter',' '].includes(event.key)){event.preventDefault();openCompare();}});
    });
    tuneCompareLayout();
    container.querySelectorAll('.compare-grid img, #candidate-comparison img').forEach((image)=>{
      if (!image.complete) image.addEventListener('load',tuneCompareLayout,{once:true});
    });
  }
  function renderCandidateView() {
    const started=performance.now(),row=rowById(state.selectedRowId);if(!row)return;
    const selected=fileById(state.selectedFileId),owner=selected?ownerOf(selected.id,row.id):null;
    const candidate=(row.candidates||[]).find((item)=>item.file_id===selected?.id);
    const reason=owner?`此文件已对应第 ${owner.row_number} 行，不能重复使用。`:row.reason||'请对照画面，选择对应的 AI 文件。';
    const status=$('review-panel').querySelector('.panel-status');status.textContent=reason;status.classList.toggle('attention',!matched(row)||!!owner);
    const evidenceOpen=$('candidate-comparison').querySelector('details')?.open;
    $('candidate-comparison').innerHTML=`<div class="compare-label"><span>候选：<b class="compare-filename">${escapeHtml(selected?.name||'请选择对应文件')}</b> · 点图放大</span><details class="score-note" data-detail-key="evidence" ${evidenceOpen?'open':''}><summary>依据</summary><p>${candidate?`相似度 ${(candidate.score*100).toFixed(1)}%`:'手动选择的文件'}</p><p>${escapeHtml(selected?.relative_path||'尚未选择文件')}</p></details></div><div class="preview-frame">${selected?imageTag('file',selected.id,'',selected.name):'<span class="preview-placeholder">尚未选择文件，请在下方查找</span>'}</div>`;
    $('candidate-issue').innerHTML=selected?.issue?`<p class="panel-note attention">文件提示：${escapeHtml(selected.issue)}</p>`:'';
    const retrievalHtml=window.HSDAI?.retrievalHtml?.(row,fileById(row.ai_retrieval?.candidate_id)?.name,state.selectedFileId)||'';
    const aiSlot=$('ai-row-advice'),aiHtml=retrievalHtml+(window.HSDAI?.rowHtml(row,fileById(row.ai_review?.candidate_id)?.name,state.selectedFileId)||'');
    if(aiSlot.dataset.content!==aiHtml){const openKeys=new Set([...aiSlot.querySelectorAll('details[data-detail-key]')].filter((item)=>item.open).map((item)=>item.dataset.detailKey));aiSlot.innerHTML=aiHtml;aiSlot.dataset.content=aiHtml;aiSlot.querySelectorAll('details[data-detail-key]').forEach((item)=>item.open=openKeys.has(item.dataset.detailKey));}
    renderOtherCandidates();setReviewBusy();bindPreviewFrames($('candidate-comparison'));
    $('manual-results')?.querySelectorAll('[data-candidate-id]').forEach((item)=>item.classList.toggle('selected',item.dataset.candidateId===state.selectedFileId));
    uiMeasure('candidate_updates',started);
  }
  function renderOtherCandidates() {
    const row=rowById(state.selectedRowId);if(!row)return;
    const others=(row.candidates||[]).slice(0,5).filter((item)=>item.file_id!==state.selectedFileId);
    $('other-candidates-slot').innerHTML=others.length?`<button type="button" class="candidate-toggle" id="candidate-toggle" aria-expanded="${state.candidatesOpen}" ${state.resolving?'disabled':''}>${state.candidatesOpen?'收起其他候选':`换候选（${others.length}）`}</button>${state.candidatesOpen?`<div class="candidate-list">${others.map((item)=>{
      const file=fileById(item.file_id);if(!file)return '';const used=ownerOf(file.id,row.id);
      return `<button type="button" class="candidate" data-candidate-id="${escapeHtml(file.id)}" aria-pressed="false" ${state.resolving?'disabled':''}>${imageTag('file',file.id,'candidate-thumb',file.name)}<span class="candidate-name">${escapeHtml(file.name)}</span>${used?`<span class="candidate-unavailable">第 ${used.row_number} 行已使用</span>`:''}</button>`;
    }).join('')}</div>`:''}`:'';
    $('candidate-toggle')?.addEventListener('click',()=>{state.candidatesOpen=!state.candidatesOpen;renderOtherCandidates();});
  }
  function setReviewBusy() {
    const row=rowById(state.selectedRowId),file=fileById(state.selectedFileId);
    const already=matched(row||{})&&row.file_id===file?.id;
    const button=$('confirm-row-button');
    if(button){button.disabled=state.resolving||!file||!!ownerOf(file?.id,row?.id)||already;button.textContent=state.resolving?'正在保存…':already?'此匹配已通过':'确认对应此文件 ✓';}
    if($('skip-row-button'))$('skip-row-button').disabled=state.resolving||row?.status==='skipped';
    $('review-panel').setAttribute('aria-busy',String(state.resolving));
    $('review-panel').querySelectorAll('[data-candidate-id],#candidate-toggle,#file-search').forEach((item)=>item.disabled=state.resolving);
    ['new-task-button','shutdown-button'].forEach((id)=>{if($(id))$(id).disabled=state.resolving||isBusy();});
    $('export-button').disabled=state.resolving||isBusy()||(state.job?.status!=='done'&&counts().matched===0);
    ['undo-button','summary-undo-button'].forEach((id)=>$(id).disabled=state.resolving||isBusy()||!(state.job?.can_undo??state.history.length));
  }
  let manualSearchTimer=null,rowSearchTimer=null;
  function selectCandidate(id){if(state.resolving)return;const scroll=$('review-panel').querySelector('.panel-content');const offset=scroll?.scrollTop||0;state.selectedFileId=id;renderCandidateView();if(scroll)scroll.scrollTop=offset;}
  function renderManualFiles() {
    const container=$('manual-results');if(!container)return;
    const query=state.manualQuery.trim().toLowerCase();
    const files=(state.job.files||[]).filter((file)=>!query||`${file.name} ${file.relative_path||''}`.toLowerCase().includes(query));
    container.innerHTML=files.length?files.slice(0,50).map((file)=>{
      const used=ownerOf(file.id,state.selectedRowId);
      return `<button type="button" class="manual-file ${state.selectedFileId===file.id?'selected':''}" data-candidate-id="${escapeHtml(file.id)}" ${state.resolving?'disabled':''} title="${escapeHtml(file.relative_path||file.name)}">${imageTag('file',file.id,'candidate-thumb',file.name)}<span><b>${escapeHtml(file.name)}</b><small>${escapeHtml(used?`第 ${used.row_number} 行已使用`:file.issue||'可选择')}</small></span></button>`;
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
      preloadImage(previewUrl('row',neighbour.id));
      const fileId=neighbour.file_id||neighbour.candidates?.[0]?.file_id;
      if (fileId) preloadImage(previewUrl('file',fileId));
    });
  }
  function preloadImage(url){if(preloaded.has(url))return;if(preloaded.size>=200)preloaded.delete(preloaded.values().next().value);preloaded.add(url);const preview=new Image();preview.src=url;}
  async function resolveRow(fileId) {
    if(state.resolving||state.job?.status!=='ready')return;
    const rowId=state.selectedRowId;
    const before=rowById(rowId);
    if (!before) return;
    rememberPanel();state.resolving=true;clearNotice();setReviewBusy();let updated=false;
    try {
      const job=await api(`/api/jobs/${encodeURIComponent(state.job.id)}/resolve`,{method:'POST',body:{row_id:rowId,file_id:fileId,expected_revision:state.job.revision}});
      acceptJob(job);
      updated=true;
      state.history.push(rowId);
      const current=rowById(rowId);
      const rows=job.rows||[],index=rows.findIndex((row)=>row.id===rowId);
      const remaining=[...rows.slice(index+1),...rows.slice(0,index)].find(awaiting);
      if (remaining) selectRow(remaining.id,null,false);
      else selectRow(current?.id,null,false);
      state.forceReview=false;state.showSummary=counts().review===0;
      toast(fileId?'已确认对应文件，可随时撤销':'已跳过，该行保持原状');
      preloadNeighbours(rowById(state.selectedRowId));
    } catch(error){updated=await refreshConflict(error);notice(error.message);} finally {state.resolving=false;if(updated){renderJob();if(!$('review-view').classList.contains('hidden'))$('confirm-row-button')?.focus({preventScroll:true});}else setReviewBusy();}
  }
  async function undoLast() {
    const canUndo=state.job?.can_undo??!!state.history.length;
    if(!canUndo||state.resolving||state.job?.status!=='ready')return;
    const rowId=state.history[state.history.length-1];
    rememberPanel();state.resolving=true;clearNotice();setReviewBusy();let updated=false;
    try {
      const useServer=state.job.can_undo!==undefined;
      const job=await api(`/api/jobs/${encodeURIComponent(state.job.id)}/${useServer?'undo':'resolve'}`,{method:'POST',body:useServer?{expected_revision:state.job.revision}:{row_id:rowId,revert:true,expected_revision:state.job.revision}});
      acceptJob(job);updated=true;state.history.pop();state.showSummary=false;state.forceReview=true;
      const restored=job.last_undone_row_id||rowId;
      selectRow(restored,null,false);state.filter=awaiting(rowById(restored)||{})?'awaiting':'all';
      toast('已撤销上一步操作');
    }catch(error){updated=await refreshConflict(error);notice(error.message);}finally{state.resolving=false;if(updated)renderJob();else setReviewBusy();}
  }
  async function refreshConflict(error) {
    if (error.status===409 && state.job) {
      try {acceptJob(await api(`/api/jobs/${encodeURIComponent(state.job.id)}`));state.history=[];return true;} catch (_) {}
    }
    return false;
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
    if(state.resolving||state.job?.status!=='ready'||counts().matched===0)return;
    const revision=state.job.revision;
    clearNotice();state.job.status='exporting';state.job.progress={message:'正在生成编号表格与 AI 文件',current:0,total:0};state.showDone=true;renderJob();
    try{await api(`/api/jobs/${encodeURIComponent(state.job.id)}/export`,{method:'POST',body:revision===undefined?{}:{expected_revision:revision}});schedulePoll(100);}
    catch(error){state.job.status='ready';try{acceptJob(await api(`/api/jobs/${encodeURIComponent(state.job.id)}`));}catch(_){}state.showSummary=true;notice(error.message);renderJob();if(isBusy())schedulePoll();}
  }
  function renderDone() {
    showView('done-view',3);
    const c=counts();
    $('done-stats').innerHTML=`<div class="done-stat"><strong>${c.matched}</strong><span>已导出</span></div><div class="done-stat"><strong>${c.newNumbers}</strong><span>新增编号</span></div><div class="done-stat"><strong>${c.awaiting+c.skipped}</strong><span>未处理或跳过</span></div><p>本机自动 ${c.localAuto} · AI 条件通过 ${c.aiAuto} · 员工确认 ${c.confirmed}</p>`;
    if (isLan()) {
      $('output-directory').previousElementSibling.textContent='结果下载';
      $('output-directory').textContent=state.job.download_ready?'结果压缩包已准备好，仅包含编号表格与 AI 文件。':'结果压缩包尚未就绪，请稍后刷新。';
      $('open-output-button').textContent='下载结果 ZIP ↓';
    } else $('output-directory').textContent=state.job.output_dir||'保存位置尚未返回';
    $('done-summary').textContent=(c.awaiting+c.skipped)?`${c.awaiting+c.skipped} 项未处理或已跳过，原始行保持原状，可查看本批匹配记录。`:'';
    $('done-summary').classList.toggle('hidden',!(c.awaiting+c.skipped));
    $('open-output-button').disabled=isLan()?!state.job.download_ready:!state.job.output_dir;renderAiOverview();
  }
  async function openOutput() {
    if (isLan()) {
      if (!state.job?.download_ready) {notice('结果压缩包尚未就绪，请稍后重试。');return;}
      window.location.assign(`/api/jobs/${encodeURIComponent(state.job.id)}/download`);
      toast('已发起下载，请在浏览器下载列表中查看。');return;
    }
    $('open-output-button').disabled=true;
    try {await api(`/api/jobs/${encodeURIComponent(state.job.id)}/open-output`,{method:'POST',body:{}});toast('已打开结果文件夹');} catch(error){notice(error.message);} finally {$('open-output-button').disabled=false;}
  }
  async function resetTask() {
    if(state.resolving||isBusy())return;
    if(state.job?.status==='ready'&&!await askConfirmation({title:'重新导入一批文件？',description:'当前匹配结果尚未导出。重新导入后需要重新检查匹配。原始文件保持不变。',confirm:'重新导入',cancel:'继续检查'}))return;
    clearTimeout(state.pollTimer);clearTimeout(rowSearchTimer);clearTimeout(manualSearchTimer);state.job=null;indexedJob=null;indexedJobId=null;countedJob=null;preloaded.clear();imageAspects.clear();rowViewState.clear();state.selectedRowId=null;state.selectedFileId=null;state.showDone=true;state.lastJobError=null;
    state.forceReview=false;state.showSummary=false;state.candidatesOpen=false;state.history=[];state.filter='awaiting';state.search='';$('row-search').value='';
    rememberJob(null);clearNotice();showView('import-view',1);window.scrollTo({top:0,behavior:'smooth'});
    if (isLan()) {['workbook-upload','source-upload'].forEach((id)=>{$(id).value='';updateUploadSelection(id);});}
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
      $('processing-view').querySelector('.progress-track').classList.add('hidden');document.querySelector('.progress-caption').classList.add('hidden');document.querySelector('.processing-footnote').classList.add('hidden');
    } catch(error){notice(error.message);$('shutdown-button').disabled=false;}
  }
  async function init() {
    configureAccess(window.HSD_ACCESS);
    setFormBusy(true);
    window.addEventListener('beforeunload',(event)=>{if(state.uploading){event.preventDefault();event.returnValue='';}});
    window.addEventListener('resize',scheduleReviewLayout,{passive:true});
    if ('ResizeObserver' in window) {
      const observer=new ResizeObserver(scheduleReviewLayout);
      ['job-ai-overview','stats-bar','warnings','notice'].forEach((id)=>observer.observe($(id)));
    }
    $('notice-close').addEventListener('click',clearNotice);
    document.querySelectorAll('.browse').forEach((button)=>button.addEventListener('click',()=>pick(button)));
    document.querySelectorAll('[data-source-type]').forEach((button)=>button.addEventListener('click',()=>setSourceType(button.dataset.sourceType)));
    $('start-number').addEventListener('input',updateNumberExample);$('import-form').addEventListener('submit',startJob);
    ['workbook-upload','source-upload'].forEach((id)=>$(id).addEventListener('change',()=>updateUploadSelection(id)));
    document.querySelectorAll('[data-filter]').forEach((button)=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;renderTable();}));
    $('row-search').addEventListener('input',(event)=>{state.search=event.target.value;clearTimeout(rowSearchTimer);rowSearchTimer=setTimeout(()=>{if(state.job)renderTable();},120);});
    $('rows-body').addEventListener('click',(event)=>{const row=event.target.closest('[data-row-id]');if(row&&!state.resolving)selectRow(row.dataset.rowId);});
    $('rows-body').addEventListener('keydown',(event)=>{if(['Enter',' '].includes(event.key)){const row=event.target.closest('[data-row-id]');if(row&&!state.resolving){event.preventDefault();selectRow(row.dataset.rowId);}}});
    $('review-panel').addEventListener('click',(event)=>{const candidate=event.target.closest('[data-candidate-id]');if(candidate&&!state.resolving)selectCandidate(candidate.dataset.candidateId);});
    $('export-button').addEventListener('click',()=>{if(state.job?.status==='done'){state.showDone=true;renderDone();}else{state.showSummary=true;renderSummary();}});$('open-output-button').addEventListener('click',openOutput);
    $('undo-button').addEventListener('click',undoLast);$('summary-undo-button').addEventListener('click',undoLast);
    $('summary-export-button').addEventListener('click',exportJob);
    $('summary-browse-button').addEventListener('click',()=>{state.forceReview=true;state.showSummary=false;state.filter='all';renderReview();});
    $('summary-continue-button').addEventListener('click',()=>{state.forceReview=true;state.showSummary=false;state.filter='awaiting';selectRow((state.job.rows||[]).find(awaiting)?.id,null,false);renderReview();});
    ['new-task-button','next-task-button','retry-task-button','summary-new-task-button'].forEach((id)=>$(id).addEventListener('click',resetTask));
    $('back-results-button').addEventListener('click',()=>{state.showDone=false;state.forceReview=true;state.showSummary=false;state.filter='all';renderReview();});
    $('shutdown-button').addEventListener('click',shutdown);
    document.addEventListener('click',(event)=>{if(event.target.closest('[data-ai-retry]'))retryAiReview();});
    document.addEventListener('hsd-ai-settings-updated',async()=>{
      if(state.job?.status!=='ready'||state.resolving)return;
      const id=state.job.id,revision=state.job.revision;
      try{
        const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
        if(state.job?.id!==id||state.job.status!=='ready'||state.resolving||state.job.revision!==revision)return;
        acceptJob(job);
        // Retry availability is computed by the server from current settings.
        // A settings refresh alone must not rebuild the open image comparison.
        if(job.revision===revision)renderAiOverview();else renderJob();
      }catch(error){notice(`未能更新本批复核状态：${error.message} 可在主机管理中重新读取设置。`);}
    });
    document.addEventListener('error',(event)=>{if(event.target instanceof HTMLImageElement)event.target.classList.add('image-broken');},true);
    let config=null;
    try {
      config=await api('/api/config');
      configureAccess(config.access);
      $('workbook-path').value=config.last_workbook||'';$('source-path').value=config.last_source||'';$('output-path').value=config.last_output||'';
      $('start-number').value=config.last_start||1;$('app-version').textContent=config.version||'1.0.0';
      if (config.last_source) setSourceType(/\.zip$/i.test(config.last_source)?'zip':'folder');
      updateNumberExample();
    } catch(error){notice(error.message);}
    const jobId=isLan()?config?.active_job_id||null:storedJob();
    if(jobId) {
      try {const job=await api(`/api/jobs/${encodeURIComponent(jobId)}`);acceptJob(job);renderJob();if(isBusy())schedulePoll();}
      catch(error){rememberJob(null);if(error.status!==404)notice(error.message);}
    }
    setFormBusy(false);
  }
  function configureAccess(access) {
    if (access) window.HSD_ACCESS=access;
    for (const [key,field] of [['workbook','workbook_bytes'],['source','source_bytes'],['total','total_bytes']]) {
      const limit=access?.upload_limits?.[field];
      uploadLimits[key]=Number.isSafeInteger(limit)&&limit>0?limit:null;
    }
    const lan=isLan();
    ['local-workbook-field','local-source-field','local-output-field'].forEach((id)=>$(id).classList.toggle('hidden',lan));
    $('upload-fields').classList.toggle('hidden',!lan);
    $('number-settings-title').textContent='本批起始流水号';
    $('host-management')?.classList.toggle('hidden',access?.remote===true);
    if (!lan) return;
    const note=$('lan-note');
    note.textContent=!access.remote&&access.code?`员工分享地址：${location.origin}；访问码：${access.code}`:'';
    note.classList.toggle('hidden',!note.textContent);
    if (access.remote) ['shutdown-button','ai-settings-button'].forEach((id)=>$(id).classList.add('hidden'));
    $('open-output-button').classList.remove('hidden');
    $('summary-output').previousElementSibling.textContent='结果获取方式';
    $('open-output-button').textContent='下载结果 ZIP ↓';
  }
  init().catch((error)=>notice(error.message||'界面加载遇到问题，请刷新页面重试。'));
})();
