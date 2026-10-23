"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const activeStatuses = new Set(["queued", "processing", "cancelling"]);
  const completed = item => ["ready", "confirmed"].includes(item.status);
  const state = {workspace:"numbering",config:null,job:null,files:[],objectUrls:[],busy:false,uploading:false,uncertain:false,retryUpload:false,stopRequested:false,uploadId:null,xhr:null,timer:null,polling:false,authLost:false,filter:"needs_review",newBatch:false,dialog:null,box:null,startPoint:null,sourcesSignature:"",items:new Map(),scroll:{numbering:0,material:0},epoch:0,selected:new Set(),stream:null,streamJob:null,streamErrors:0,streamDisabled:false,clockTimer:null,clockAnchor:null,renewTimer:null};
  const metrics = {cards_created:0,cards_updated:0,polls:0};
  function count(name) {metrics[name]++;document.documentElement.dataset.materialUiMetrics=JSON.stringify(metrics);}
  function stored(key) {try{return sessionStorage.getItem(key);}catch(_){return null;}}
  function remember(key,value) {try{if(value)sessionStorage.setItem(key,value);else sessionStorage.removeItem(key);}catch(_){}}
  function notify(message,error=false) {$("material-notice").textContent=message;$("material-notice").classList.toggle("hidden",!message);$("material-notice").classList.toggle("warning",error);}
  function lockAuth() {state.authLost=true;closeStream();clearTimeout(state.timer);state.epoch++;$("material-sign-in").classList.remove("hidden");notify("登录已失效，请在原浏览器重新登录后继续。",true);controls();}
  async function api(path,body,epoch=state.epoch) {
    const response=await fetch(path,{method:body===undefined?"GET":"POST",credentials:"same-origin",cache:"no-store",headers:{"X-HSD-Token":window.HSD_TOKEN||"",...(body===undefined?{}:{"Content-Type":"application/json"})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){if(epoch===state.epoch&&(response.status===401||(response.status===403&&/会话|登录/.test(data.error||""))))lockAuth();const error=new Error(data.error||"操作未完成，请检查网络后重试。");error.status=response.status;throw error;}
    return data;
  }
  function jobPath(suffix="") {return `/api/material/jobs/${encodeURIComponent(state.job.id)}${suffix}`;}
  function safeUrl(url) {const prefix=state.job?`/api/material/jobs/${encodeURIComponent(state.job.id)}/`:"";return typeof url==="string"&&prefix&&url.startsWith(prefix)&&!/[\\\r\n]/.test(url)?url:"";}
  function workspace(name,writeHash=false) {
    name=name==="material"?"material":"numbering";
    state.scroll[state.workspace]=window.scrollY||0;state.workspace=name;
    $("numbering-workspace").classList.toggle("hidden",name!=="numbering");$("material-workspace").classList.toggle("hidden",name!=="material");document.body.classList.toggle("material-active",name==="material");
    document.querySelectorAll("[data-workspace]").forEach(link=>{const active=link.dataset.workspace===name;link.classList.toggle("active",active);if(active)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");});
    if(writeHash)history.replaceState(null,"",`#${name}`);
    window.scrollTo({top:state.scroll[name],behavior:"instant"});
    if(name==="material"&&!state.config)loadConfig();else schedule();
  }
  function busy() {return state.busy||state.uploading||state.uncertain||activeStatuses.has(state.job?.status);}
  function controls() {
    const locked=busy()||state.authLost;
    $("material-files").disabled=locked;$("material-start").disabled=(locked&&!(state.uncertain&&state.retryUpload&&!state.busy&&!state.authLost))||!state.files.length||!state.config?.available;
    $("material-start").textContent=state.uploading?"正在上传…":state.busy?"正在提交…":state.uncertain&&state.retryUpload?"重试本次上传":"开始提取";
    $("material-new").disabled=locked;$("material-stop").disabled=state.busy||state.authLost||state.job?.status==="cancelling";
    $("material-stop").textContent=state.job?.status==="cancelling"?"正在停止…":state.uploading||state.uncertain?"停止上传":"停止本批";
    $("material-download-all").disabled=locked||!safeUrl(state.job?.download_url);
    $("material-recheck").disabled=state.busy||state.polling||state.authLost;
    $("material-upload-check").disabled=state.busy||state.authLost;
    $("material-grid").querySelectorAll("button,input").forEach(button=>{button.disabled=locked;});
    updateSelection();
    $("material-source-grid").querySelectorAll("button").forEach(button=>{button.disabled=locked;});
    $("material-detail-actions").querySelectorAll("button").forEach(button=>{button.disabled=locked;});
    const unknown=state.job?.sources.find(source=>source.id===state.dialog?.sourceId)?.submission_unknown===true;
    $("material-redo-submit").disabled=locked||!state.box||(unknown&&!$("material-unknown-ack").checked);
    $("material-selected-files").querySelectorAll("button").forEach(button=>{button.disabled=locked;});
  }
  async function loadConfig() {
    const epoch=state.epoch;
    try {
      const config=await api("/api/material/config");if(epoch!==state.epoch)return;state.config=config;
      if(!config.available)notify(config.unavailable_reason||config.reason||(config.configured?(config.enabled?"素材服务暂不可用，请联系管理员检查设置。":"素材提取尚未启用，请联系管理员打开开关。") :"素材提取尚未配置，请联系管理员。"),true);
      const pending=stored("hsd-material-upload");
      if(pending&&/^[0-9a-f-]{36}$/i.test(pending)){state.uploadId=pending;state.uncertain=true;showUpload();await recoverUpload();}
      else {const id=stored("hsd-material-job")||(!state.newBatch?config.active_job_id:null);if(id&&/^[a-zA-Z0-9_-]{1,100}$/.test(id))await loadJob(id);}
    }catch(error){if(epoch===state.epoch&&!state.authLost)notify(error.message||"无法读取素材设置，请稍后刷新。",true);}finally{if(epoch===state.epoch)controls();}
  }
  function releaseUrls() {state.objectUrls.forEach(url=>URL.revokeObjectURL(url));state.objectUrls=[];}
  function fileError(file) {if(!/\.(png|jpe?g|webp)$/i.test(file?.name||""))return "只支持 PNG、JPG、WebP 图片。";if(!file.size)return "所选图片为空，请换一张。";return "";}
  function selectFiles(files,append=false) {
    if(busy()||state.authLost)return;
    const incoming=[...files],error=incoming.map(fileError).find(Boolean);
    $("material-file-error").textContent=error||"";$("material-file-error").classList.toggle("hidden",!error);if(error)return;
    const unique=new Map((append?state.files:[]).map(file=>[`${file.name}:${file.size}:${file.lastModified}`,file]));
    incoming.forEach(file=>unique.set(`${file.name}:${file.size}:${file.lastModified}`,file));state.files=[...unique.values()];renderSelected();controls();
  }
  function renderSelected() {
    releaseUrls();$("material-selected-files").innerHTML=state.files.map((file,index)=>{const url=URL.createObjectURL(file);state.objectUrls.push(url);return `<li class="material-selected-file"><img src="${esc(url)}" alt="" decoding="async"><span>${esc(file.name)}<small>${formatBytes(file.size)}</small></span><button type="button" data-remove-file="${index}" aria-label="移除 ${esc(file.name)}">×</button></li>`;}).join("");
  }
  function formatBytes(bytes) {if(bytes<1024)return `${bytes} B`;if(bytes<1024*1024)return `${(bytes/1024).toFixed(1)} KiB`;return `${(bytes/1024/1024).toFixed(1)} MiB`;}
  function showUpload() {$("material-progress").classList.remove("hidden");$("material-upload-check").classList.toggle("hidden",!state.uncertain);$("material-stop").classList.remove("hidden");$("material-progress-title").textContent=state.uncertain?"正在核对上传结果":"正在上传图片";$("material-progress-message").textContent=state.uncertain?"连接中断，先确认服务器是否收到，避免重复处理。":"上传完成后自动开始提取。";$("material-progress-fill").classList.toggle("indeterminate",true);$("material-progress-detail").textContent="";}
  function clearUpload() {state.uploading=false;state.uncertain=false;state.retryUpload=false;state.stopRequested=false;state.uploadId=null;state.xhr=null;remember("hsd-material-upload",null);$("material-upload-check").classList.add("hidden");}
  function upload(files) {
    return new Promise((resolve,reject)=>{
      const form=new FormData();files.forEach(file=>form.append("files",file));
      const xhr=new XMLHttpRequest();state.xhr=xhr;xhr.open("POST","/api/material/jobs");xhr.timeout=0;xhr.setRequestHeader("X-HSD-Token",window.HSD_TOKEN||"");xhr.setRequestHeader("X-HSD-Upload-ID",state.uploadId);
      xhr.upload.addEventListener("progress",event=>{if(!state.uploading)return;const known=event.lengthComputable&&event.total>0;$("material-progress-fill").classList.toggle("indeterminate",!known);if(known){const percent=Math.min(100,Math.round(event.loaded/event.total*100));$("material-progress-fill").style.width=`${percent}%`;$("material-progress-detail").textContent=`上传 ${percent}% · ${formatBytes(event.loaded)} / ${formatBytes(event.total)}`;if(percent===100)$("material-progress-message").textContent="上传完成，正在检查图片，请稍候。";}});
      xhr.addEventListener("load",()=>{let data;try{data=JSON.parse(xhr.responseText);}catch(_){reject(new Error("上传结果未确认。"));return;}if(xhr.status<200||xhr.status>=300){const error=new Error(data.error||"上传未完成。");error.status=xhr.status;reject(error);return;}if(!data.id){reject(new Error("上传结果未确认。"));return;}resolve(data);});
      ["error","abort","timeout"].forEach(name=>xhr.addEventListener(name,()=>reject(new Error("上传连接中断，正在核对结果。"))));xhr.send(form);
    });
  }
  async function start(event) {
    event?.preventDefault();const retry=state.uncertain&&state.retryUpload&&!state.stopRequested;if((busy()&&!retry)||state.busy||state.uploading||state.authLost||!state.files.length||!state.config?.available)return;
    if(!window.crypto?.randomUUID){notify("请使用新版 Chrome 或 Edge 打开安全网址后重试。",true);return;}
    const epoch=state.epoch;
    if(!retry)state.uploadId=window.crypto.randomUUID();remember("hsd-material-upload",state.uploadId);state.retryUpload=false;state.uncertain=false;state.uploading=true;notify("");showUpload();controls();
    try{const data=await upload(state.files);if(epoch!==state.epoch)return;clearUpload();state.newBatch=false;remember("hsd-material-new",null);await loadJob(data.id);}
    catch(error){if(epoch!==state.epoch)return;state.uploading=false;if([400,413,415,422].includes(error.status)){clearUpload();$("material-progress").classList.add("hidden");notify(error.message,true);}else if(error.status===401){state.uncertain=true;lockAuth();}else{state.uncertain=true;showUpload();await recoverUpload();}}
    finally{if(epoch===state.epoch)controls();}
  }
  async function recoverUpload() {
    if(!state.uploadId||state.busy||state.authLost)return;const epoch=state.epoch;state.busy=true;controls();
    try{const data=await api(`/api/material/upload-status/${encodeURIComponent(state.uploadId)}`);if(epoch!==state.epoch)return;const id=data.job_id||data.id;if(id&&data.state==="completed"){const stop=state.stopRequested||data.cancellation_requested;clearUpload();await loadJob(id);if(epoch!==state.epoch)return;if(stop&&activeStatuses.has(state.job?.status)){const job=await api(jobPath("/cancel"),{expected_revision:state.job.revision});if(epoch===state.epoch)setJob(job);}}else if(data.state==="cancelled"){clearUpload();$("material-progress").classList.add("hidden");notify("上传已停止，可以重新选择图片。");}else if(data.state==="missing"){state.uncertain=true;state.retryUpload=!!state.files.length&&!state.stopRequested;showUpload();notify(state.retryUpload?"当前未找到已受理任务。可重试本次上传（沿用同一个请求），或先停止再更换图片。":"当前未找到已受理任务，请先停止本次上传，再重新选择图片。",true);}else{state.uncertain=true;state.retryUpload=false;showUpload();notify(data.cancellation_requested?"正在停止上传，请稍后查询最终结果。":"还在核对上传结果，请稍后点击“查询上传结果”。不要重复提交。",true);}}
    catch(error){if(epoch===state.epoch&&!state.authLost)notify(error.message||"无法查询上传结果，请稍后重试。",true);}finally{if(epoch===state.epoch){state.busy=false;controls();}}
  }
  async function loadJob(id=state.job?.id) {if(!id||state.authLost)return;const epoch=state.epoch,job=await api(`/api/material/jobs/${encodeURIComponent(id)}`);if(epoch===state.epoch&&!state.authLost)setJob(job);}
  function closeStream() {clearTimeout(state.clockTimer);clearTimeout(state.renewTimer);state.renewTimer=null;if(state.stream)state.stream.close();state.stream=null;state.streamJob=null;}
  function schedule() {
    clearTimeout(state.timer);
    if(!activeStatuses.has(state.job?.status)||state.authLost||document.hidden||state.workspace!=="material"){closeStream();return;}
    updateClock();
    if(state.renewTimer!==null)return;
    if(typeof window.EventSource==="function"&&!state.streamDisabled){openStream();return;}
    state.timer=setTimeout(poll,1500);
  }
  function updateClock() {
    clearTimeout(state.clockTimer);const p=state.job?.progress||{};
    if(!activeStatuses.has(state.job?.status)||document.hidden||state.workspace!=="material")return;
    if(Number(p.started_at)>0){const elapsed=Math.max(0,Math.floor((state.clockAnchor?.elapsed||0)+((window.performance?.now()||0)-(state.clockAnchor?.received||0))/1000));$("material-progress-detail").textContent=(state.job.status==="queued"&&p.queue_position?`当前排在第 ${p.queue_position} 位`:`已完成 ${Number(p.current)||0} / ${Number(p.total)||0} 张原图`)+` · 本阶段已用 ${elapsed} 秒`;state.clockTimer=setTimeout(updateClock,1000);}
  }
  function openStream() {
    const id=state.job.id,epoch=state.epoch;if(state.stream&&state.streamJob===id)return;closeStream();
    const stream=new window.EventSource(jobPath("/events"));state.stream=stream;state.streamJob=id;
    const current=()=>state.stream===stream&&state.job?.id===id&&state.epoch===epoch&&!state.authLost;
    stream.addEventListener("snapshot",event=>{if(!current())return;try{const job=JSON.parse(event.data);if(job.id!==id)throw new Error("task mismatch");state.streamErrors=0;$("material-stream-state").textContent="进度实时更新中";setJob(job);}catch(_){fallback();}});
    stream.addEventListener("renew",()=>{if(!current())return;closeStream();state.streamErrors=0;const timer=setTimeout(()=>{if(state.renewTimer!==timer)return;state.renewTimer=null;if(state.epoch===epoch&&state.job?.id===id)schedule();},1500);state.renewTimer=timer;updateClock();});
    stream.addEventListener("end",()=>{if(!current())return;closeStream();if(activeStatuses.has(state.job?.status))poll();});
    const fallback=()=>{if(!current())return;closeStream();state.streamDisabled=true;$("material-stream-state").textContent="实时连接暂不可用，正在自动刷新进度";clearTimeout(state.timer);state.timer=setTimeout(poll,0);};
    stream.addEventListener("unavailable",fallback);
    stream.onerror=()=>{if(!current())return;state.streamErrors++;$("material-stream-state").textContent="正在重新连接进度…";if(stream.readyState===2||state.streamErrors>=2)fallback();};
  }
  async function poll() {if(state.polling||state.authLost||!state.job)return;const epoch=state.epoch;state.polling=true;count("polls");try{await loadJob();}catch(error){if(epoch===state.epoch&&!state.authLost)notify("暂时无法获取进度，请检查网络；系统不会重复提交图片。",true);}finally{if(epoch===state.epoch){state.polling=false;controls();schedule();}}}
  function setJob(job) {
    if(!job||typeof job.id!=="string"||!Array.isArray(job.items)||!Array.isArray(job.sources))throw new Error("素材结果格式异常，请刷新页面后重试。");
    if(state.job?.id===job.id&&(Number(job.revision)<Number(state.job.revision)||(job.revision===state.job.revision&&Number(job.update_seq)<Number(state.job.update_seq))))return;
    const changed=state.job?.id!==job.id,finished=activeStatuses.has(state.job?.status)&&!activeStatuses.has(job.status);state.job=job;remember("hsd-material-job",job.id);
    if(changed){closeStream();state.streamDisabled=false;state.streamErrors=0;state.selected.clear();state.items.clear();$("material-grid").replaceChildren();state.sourcesSignature="";state.filterTouched=false;}
    const clockKey=JSON.stringify([job.id,job.progress?.stage_code,job.progress?.started_at,job.progress?.source_id]);
    if(state.clockAnchor?.key!==clockKey)state.clockAnchor={key:clockKey,elapsed:Math.max(0,Number(job.progress?.elapsed_seconds)||0),received:window.performance?.now()||0};
    if(changed||(finished&&!state.filterTouched))state.filter=job.items.some(item=>item.status==="needs_review")||activeStatuses.has(job.status)?"needs_review":"all";
    render();schedule();
  }
  function render() {
    const job=state.job;if(!job)return;const running=activeStatuses.has(job.status);
    $("material-upload-form").classList.add("hidden");$("material-results").classList.remove("hidden");$("material-new").classList.remove("hidden");$("material-progress").classList.toggle("hidden",!running);$("material-upload-check").classList.add("hidden");
    if(running){
      const progress=job.progress||{},total=Number(progress.total)||0,current=Number(progress.current)||0,queued=job.status==="queued";
      $("material-progress-title").textContent=job.status==="cancelling"?"正在停止本批":queued?"排队等待":progress.phase||"正在处理素材";
      $("material-progress-message").textContent=progress.message||"图片处理中，完成的结果会陆续显示。";
      // Count represents completed source images, never the upstream model's percentage.
      $("material-progress-fill").classList.toggle("indeterminate",!total||queued||current===0||progress.indeterminate===true);
      if(total&&!queued&&current>0)$("material-progress-fill").style.width=`${Math.min(100,current/total*100)}%`;
      const elapsed=Number(progress.elapsed_seconds)||0;
      $("material-progress-detail").textContent=(queued&&progress.queue_position?`当前排在第 ${progress.queue_position} 位`:total?`已完成 ${current} / ${total} 张原图`:"正在等待处理")+(elapsed?` · 本阶段已用 ${Math.floor(elapsed)} 秒`:"");
      const phase=String(progress.stage_code||progress.phase||"");const step=/clean|清理/.test(phase)?0:/locat|detect|识别/.test(phase)?1:/crop|sav|裁剪|保存/.test(phase)?2:-1;
      $("material-stage-list").innerHTML=["清理整图","识别设计","裁剪保存"].map((name,index)=>`<li${step===index?' class="current" aria-current="step"':""}>${index+1}. ${name}</li>`).join("");
    }
    if(job.status==="error")notify(job.error||"本批未能处理，请查看原图下的问题提示。",true);else if(job.status==="cancelled")notify("本批已停止。已经完成的素材仍可查看和下载。");
    const stats=job.stats||{},pending=job.items.filter(item=>item.status==="needs_review").length,ready=job.items.filter(completed).length,skipped=job.items.filter(item=>item.status==="skipped").length;
    $("material-summary").textContent=`${job.sources.length} 张原图 · ${job.items.length} 个素材 · ${pending} 个待确认 · ${ready} 个可下载${skipped?` · ${skipped} 个已跳过`:""}${stats.failed?` · ${stats.failed} 张处理失败`:""}`;
    $("material-result-title").textContent=running?"正在生成本批素材":pending?`还有 ${pending} 个素材需要确认`:"本批提取结果";$("material-review-count").textContent=String(pending);
    document.querySelectorAll("[data-material-filter]").forEach(button=>{const active=button.dataset.materialFilter===state.filter;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
    const shared=sharedWarnings();$("material-shared-warning").textContent=shared.join("；");$("material-shared-warning").classList.toggle("hidden",!shared.length);
    renderCards();renderSources();
    const warnings=[...(job.warnings||[]),...(job.sources||[]).filter(source=>source.error).map(source=>`${source.name}：${source.error}`)];
    $("material-batch-info").innerHTML=`<p>可下载 ${ready} 个；待确认 ${pending} 个；已跳过 ${skipped} 个。只导出已完成项。</p><p>长边目标 4096 像素，不代表恢复了原本看不清的细节。人工确认后的问题提示仍保留。</p>${warnings.map(warning=>`<p>${esc(warning)}</p>`).join("")}<p>云端副本保留三天，请将结果下载到自己的电脑。</p>`;
    controls();
  }
  function visibleItem(item) {return state.filter==="all"||(state.filter==="completed"&&completed(item))||state.filter===item.status;}
  let warningItems=null,warningCache=[];
  function sharedWarnings() {if(warningItems===state.job?.items)return warningCache;warningItems=state.job?.items;const counts=new Map();for(const item of state.job?.items||[])for(const warning of new Set(item.warnings||[]))counts.set(warning,(counts.get(warning)||0)+1);warningCache=[...counts].filter(([,count])=>count>1&&count===state.job.items.length).map(([warning])=>warning);return warningCache;}
  function selectableItems() {return (state.job?.items||[]).filter(item=>item.status==="needs_review"&&visibleItem(item)&&safeUrl(item.image_url));}
  function updateSelection() {
    const items=selectableItems(),ids=new Set(items.map(item=>item.id));for(const id of state.selected)if(!ids.has(id))state.selected.delete(id);
    const locked=busy()||state.authLost;$("material-undo-batch").classList.toggle("hidden",!state.job?.can_undo_batch);$("material-undo-batch").disabled=locked;const all=$("material-select-all");all.checked=!!items.length&&state.selected.size===items.length;all.indeterminate=state.selected.size>0&&!all.checked;all.disabled=locked||!items.length;
    $("material-selected-count").textContent=`已选 ${state.selected.size} 项`;
    $("material-confirm-selected").disabled=locked||!state.selected.size;$("material-confirm-selected").textContent=state.busy?"正在保存…":`确认所选可用${state.selected.size?`（${state.selected.size}）`:""}`;
    $("material-grid").querySelectorAll("[data-select-item]").forEach(input=>{input.checked=state.selected.has(input.dataset.selectItem);input.disabled=locked;});
  }
  function selectAllItems(checked) {state.selected.clear();if(checked)selectableItems().forEach(item=>state.selected.add(item.id));updateSelection();}
  async function confirmSelected() {
    if(busy()||state.authLost)return;const item_ids=selectableItems().filter(item=>state.selected.has(item.id)).map(item=>item.id);if(!item_ids.length)return;
    const success=await mutate("resolve-batch",{item_ids});if(success){state.selected.clear();notify(`已人工确认 ${item_ids.length} 个素材，可下载；可撤销本次批量确认或在“可下载”中逐项更正。`);updateSelection();$("material-download-all").focus({preventScroll:true});}
  }
  function itemHtml(item) {
    const done=completed(item),skipped=item.status==="skipped",warnings=item.warnings||[],shared=new Set(sharedWarnings()),specific=warnings.filter(w=>!shared.has(w));
    return `${item.status==="needs_review"?`<label class="material-item-select"><input type="checkbox" data-select-item="${esc(item.id)}" aria-label="选择 ${esc(item.name)}">选择</label>`:""}<button class="material-item-preview" data-material-action="compare" data-item-id="${esc(item.id)}" type="button" aria-label="放大对照 ${esc(item.name)}"><img src="${esc(safeUrl(item.image_url))}" alt="${esc(item.name)}" loading="lazy" decoding="async"></button><div class="material-item-info"><div class="material-item-heading"><strong class="material-item-name">${esc(item.name)}</strong><span class="material-item-badge ${done?"completed":skipped?"skipped":""}">${done?(item.status==="confirmed"?"人工确认":"可下载"):skipped?"已跳过":"待确认"}</span></div>${specific.length?`<p class="material-item-warning">${esc(specific[0])}</p>`:""}<details><summary>查看详情</summary><ul>${warnings.map(w=>`<li>${esc(w)}</li>`).join("")}</ul><p>${Number(item.width)||0} × ${Number(item.height)||0} 像素 · PNG</p></details><div class="material-item-actions">${!done?`<button class="button button-primary" type="button" data-material-action="confirm" data-item-id="${esc(item.id)}">${skipped?"恢复并确认":"确认"}</button>`:`<button class="button button-primary" type="button" data-material-action="download" data-item-id="${esc(item.id)}">下载</button>`}<button class="button button-secondary" type="button" data-material-action="correct" data-item-id="${esc(item.id)}">修改</button>${!skipped?`<button class="button button-quiet" type="button" data-material-action="skip" data-item-id="${esc(item.id)}">${done?"撤回完成":"跳过"}</button>`:""}</div></div>`;
  }
  function renderCards() {
    const grid=$("material-grid"),visible=[];
    for(const item of state.job.items){const key=JSON.stringify([item,sharedWarnings()]);let record=state.items.get(item.id);if(!record){const node=document.createElement("article");node.className="material-item";node.dataset.itemId=item.id;grid.append(node);record={node,key:null};state.items.set(item.id,record);count("cards_created");}if(record.key!==key){const open=record.node.querySelector("details")?.open;record.node.innerHTML=itemHtml(item);if(open&&record.node.querySelector("details"))record.node.querySelector("details").open=true;record.key=key;count("cards_updated");}const shown=visibleItem(item);record.node.classList.toggle("hidden",!shown);if(shown)visible.push(item);}
    const ids=new Set(state.job.items.map(item=>item.id));for(const [id,record]of state.items){if(!ids.has(id)){record.node.remove();state.items.delete(id);}}
    $("material-empty").classList.toggle("hidden",visible.length>0);$("material-empty").textContent=activeStatuses.has(state.job.status)?"完成的素材会陆续显示在这里。":state.filter==="needs_review"?"没有仍需确认的素材。可下载已完成项，或按需查看全部。":"这里暂无素材，请切换筛选，或从原图框选补提。";
  }
  function renderSources() {const signature=JSON.stringify(state.job.sources);if(signature===state.sourcesSignature)return;state.sourcesSignature=signature;$("material-source-grid").innerHTML=state.job.sources.map(source=>`<article class="material-source-card"><img src="${esc(safeUrl(source.image_url))}" alt="${esc(source.name)}" loading="lazy" decoding="async"><strong>${esc(source.name)}</strong>${source.error?`<p>${esc(source.error)}</p>`:""}<button class="button button-secondary" data-source-id="${esc(source.id)}" type="button">${source.error?"查看原图并重试":"框选补提"}</button></article>`).join("");if(state.job.sources.some(source=>source.error))$("material-source-details").open=true;}
  async function mutate(action,body) {
    if(state.busy||state.uploading||state.uncertain||(action!=="cancel"&&activeStatuses.has(state.job?.status))||state.authLost||!state.job)return false;const epoch=state.epoch;state.busy=true;state.lastConflict=false;notify("");controls();
    try{const result=await api(jobPath(`/${action}`),{expected_revision:state.job.revision,...body});if(epoch!==state.epoch)return false;if(result?.items)setJob(result);else await loadJob();return true;}
    catch(error){if(epoch!==state.epoch)return false;state.lastConflict=error.status===409;notify(error.status===409?"本批状态已更新，正在重新读取；请核对后再操作。":error.message,true);if(error.status===409)try{await loadJob();}catch(_){}return false;}
    finally{if(epoch===state.epoch){state.busy=false;controls();}}
  }
  async function stop() {
    if(state.busy||state.authLost)return;
    if(state.uploading||state.uncertain){const epoch=state.epoch;state.busy=true;state.stopRequested=true;state.retryUpload=false;controls();try{await api(`/api/material/upload-status/${encodeURIComponent(state.uploadId)}/cancel`,{});if(epoch!==state.epoch)return;state.xhr?.abort();state.uploading=false;state.uncertain=true;}catch(error){if(epoch===state.epoch)notify(error.message,true);}finally{if(epoch===state.epoch){state.busy=false;await recoverUpload();controls();}}return;}
    const stopped=await mutate("cancel",{});if(!stopped&&state.lastConflict&&activeStatuses.has(state.job?.status))await mutate("cancel",{});
  }
  function download(url) {const safe=safeUrl(url);if(!safe||busy()||state.authLost)return;const id=state.job.id,frame=$("material-download-frame");frame.onload=()=>{if(state.job?.id!==id)return;let text="";try{text=(frame.contentDocument?.body?.textContent||"").trim();}catch(_){text="无法读取下载结果。";}if(!text)return;let error;try{error=JSON.parse(text).error;}catch(_){}notify(error||"下载未能开始，请检查网络后重试。",true);if(/访问码|会话|登录/.test(error||""))lockAuth();};frame.onerror=()=>{if(state.job?.id===id)notify("下载连接中断，请检查网络后重试。",true);};frame.src=`${safe}${safe.includes("?")?"&":"?"}frame=1`;notify("已请求下载，请查看浏览器下载列表；未开始时可重试。");}
  async function itemAction(event) {
    const button=event.target.closest("[data-material-action]");if(!button||busy()||state.authLost)return;const item=state.job.items.find(item=>item.id===button.dataset.itemId);if(!item)return;
    const action=button.dataset.materialAction;
    if(action==="compare"||action==="correct"){openDetail(item.source_id,item,action==="correct");return;}
    if(action==="download"){download(item.download_url);return;}
    const result=await mutate("resolve",{item_id:item.id,action});if(result){const next=state.job.items.find(value=>value.status==="needs_review");if(state.dialog){if(next)openDetail(next.source_id,next,false);else $("material-detail-dialog").close();}else{const node=next?state.items.get(next.id)?.node:null;node?.querySelector("button")?.focus({preventScroll:true});}}
  }
  function openDetail(sourceId,item=null,redo=false) {
    const source=state.job.sources.find(value=>value.id===sourceId);if(!source)return;state.dialog={sourceId,itemId:item?.id||null,redo};state.box=null;state.startPoint=null;
    $("material-detail-title").textContent=redo?(item?"标记需要修改的位置":"框选完整设计"):item?.name||source.name;$("material-detail-note").textContent=source.name;
    $("material-detail-source").src=safeUrl(source.image_url);$("material-detail-output").src=item?safeUrl(item.image_url):"";$("material-detail-output-figure").classList.toggle("hidden",!item);$("material-detail-warning").textContent=(item?.warnings||[]).join("；");
    $("material-redo-controls").classList.toggle("hidden",!redo);$("material-selection-stage").classList.toggle("selecting",redo);$("material-selection-box").classList.add("hidden");$("material-box-note").textContent=item?"在原图拖动标记问题位置。只重做这张素材，不改动其他已完成项。":"在原图拖动框选一个完整设计，文字和装饰一起框入。";$("material-correction-kind").selectedIndex=0;$("material-correction-note").value="";$("material-dialog-message").classList.add("hidden");
    $("material-detail-actions").innerHTML=redo?"":item?`${!completed(item)?`<button class="button button-primary" type="button" data-material-action="confirm" data-item-id="${esc(item.id)}">确认可用</button>`:`<button class="button button-primary" type="button" data-material-action="download" data-item-id="${esc(item.id)}">下载 PNG</button>`}<button class="button button-secondary" type="button" data-material-action="correct" data-item-id="${esc(item.id)}">标记修改</button>${item.status!=="skipped"?`<button class="button button-quiet" type="button" data-material-action="skip" data-item-id="${esc(item.id)}">跳过</button>`:""}`:"";
    $("material-unknown-row").classList.toggle("hidden",!source.submission_unknown);$("material-unknown-ack").checked=false;$("material-redo-submit").textContent=source.submission_unknown?"重新提交，可能重复计费":"只重做框选范围";
    if(!$("material-detail-dialog").open)$("material-detail-dialog").showModal();controls();
  }
  function imagePoint(event) {
    const image=$("material-detail-source"),source=state.job?.sources.find(value=>value.id===state.dialog?.sourceId);if(!source||!image.complete||!image.naturalWidth)return null;const rect=image.getBoundingClientRect();if(!rect.width||!rect.height)return null;
    return {x:Math.max(0,Math.min(source.width,(event.clientX-rect.left)/rect.width*source.width)),y:Math.max(0,Math.min(source.height,(event.clientY-rect.top)/rect.height*source.height)),rect,width:source.width,height:source.height};
  }
  function selectionMove(event) {if(!state.startPoint||!state.dialog?.redo)return;const point=imagePoint(event);if(!point)return;const first=state.startPoint;const left=Math.round(Math.min(first.x,point.x)),top=Math.round(Math.min(first.y,point.y)),right=Math.round(Math.max(first.x,point.x)),bottom=Math.round(Math.max(first.y,point.y));state.box={x:left,y:top,width:right-left,height:bottom-top};const stage=$("material-selection-stage").getBoundingClientRect(),box=$("material-selection-box");Object.assign(box.style,{left:`${point.rect.left-stage.left+state.box.x/point.width*point.rect.width}px`,top:`${point.rect.top-stage.top+state.box.y/point.height*point.rect.height}px`,width:`${state.box.width/point.width*point.rect.width}px`,height:`${state.box.height/point.height*point.rect.height}px`});box.classList.remove("hidden");}
  async function redo() {
    if(!state.box||!state.dialog||busy())return;if(state.box.width<8||state.box.height<8){$("material-dialog-message").textContent="框选范围太小，请重新拖动框选。";$("material-dialog-message").classList.remove("hidden");return;}
    const dialog={...state.dialog};const source=state.job.sources.find(value=>value.id===dialog.sourceId);const unknown=source?.submission_unknown===true;if(unknown&&!$("material-unknown-ack").checked){$("material-dialog-message").textContent="请先确认重新提交可能重复计费，再继续。";$("material-dialog-message").classList.remove("hidden");return;}
    const box={...state.box};const instruction=[$("material-correction-kind").value,$("material-correction-note").value.trim()].filter(Boolean).join("；");const success=await mutate("redo",{source_id:dialog.sourceId,...(dialog.itemId?{item_id:dialog.itemId}:{}),box,instruction,...(unknown?{acknowledge_unknown:true}:{})});if(success)$("material-detail-dialog").close();else{$("material-dialog-message").textContent=$("material-notice").textContent;$("material-dialog-message").classList.remove("hidden");}
  }
  function reset() {if(busy()||state.authLost)return;state.epoch++;closeStream();clearTimeout(state.timer);state.selected.clear();state.polling=false;state.job=null;state.items.clear();state.sourcesSignature="";state.newBatch=true;state.files=[];releaseUrls();remember("hsd-material-job",null);remember("hsd-material-new","1");$("material-files").value="";$("material-selected-files").replaceChildren();$("material-grid").replaceChildren();$("material-upload-form").classList.remove("hidden");$("material-results").classList.add("hidden");$("material-progress").classList.add("hidden");$("material-new").classList.add("hidden");notify("");controls();$("material-files").focus();}
  function boot() {
    document.querySelectorAll("[data-workspace]").forEach(link=>link.addEventListener("click",event=>{event.preventDefault();workspace(link.dataset.workspace,true);}));window.addEventListener("hashchange",()=>workspace(location.hash.slice(1)));
    $("material-files").addEventListener("change",event=>selectFiles(event.target.files));$("material-upload-form").addEventListener("submit",start);$("material-selected-files").addEventListener("click",event=>{const button=event.target.closest("[data-remove-file]");if(!button||busy())return;state.files.splice(Number(button.dataset.removeFile),1);renderSelected();controls();});
    const drop=$("material-dropzone");drop.addEventListener("keydown",event=>{if(event.target===drop&&["Enter"," "].includes(event.key)){event.preventDefault();$("material-files").click();}});["dragenter","dragover"].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();if(!busy())drop.classList.add("dragging");}));["dragleave","drop"].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove("dragging");if(name==="drop")selectFiles(event.dataTransfer.files,true);}));
    $("material-undo-batch").addEventListener("click",async()=>{if(await mutate("undo-batch",{})){state.filter="needs_review";render();notify("已撤销本次批量确认。");}});
    $("material-select-all").addEventListener("change",event=>selectAllItems(event.target.checked));$("material-confirm-selected").addEventListener("click",confirmSelected);$("material-grid").addEventListener("change",event=>{const input=event.target.closest("[data-select-item]");if(!input||busy())return;if(input.checked)state.selected.add(input.dataset.selectItem);else state.selected.delete(input.dataset.selectItem);updateSelection();});
    $("material-stop").addEventListener("click",stop);$("material-upload-check").addEventListener("click",recoverUpload);$("material-new").addEventListener("click",reset);$("material-recheck").addEventListener("click",poll);$("material-download-all").addEventListener("click",()=>download(state.job?.download_url));$("material-grid").addEventListener("click",itemAction);$("material-detail-actions").addEventListener("click",itemAction);$("material-source-grid").addEventListener("click",event=>{const button=event.target.closest("[data-source-id]");if(button&&!busy())openDetail(button.dataset.sourceId,null,true);});
    $("material-filter").addEventListener("click",event=>{const button=event.target.closest("[data-material-filter]");if(button){state.filter=button.dataset.materialFilter;state.filterTouched=true;render();}});$("material-detail-close").addEventListener("click",()=>$("material-detail-dialog").close());$("material-detail-dialog").addEventListener("close",()=>{state.dialog=null;state.box=null;state.startPoint=null;});$("material-redo-submit").addEventListener("click",redo);$("material-unknown-ack").addEventListener("change",controls);
    const stage=$("material-selection-stage");stage.addEventListener("pointerdown",event=>{if(!state.dialog?.redo||busy())return;const point=imagePoint(event);if(!point)return;event.preventDefault();state.startPoint=point;stage.setPointerCapture(event.pointerId);selectionMove(event);});stage.addEventListener("pointermove",selectionMove);stage.addEventListener("pointerup",event=>{if(!state.startPoint)return;selectionMove(event);state.startPoint=null;if(state.box&&state.box.width>=8&&state.box.height>=8){$("material-box-note").textContent=`已框选 ${state.box.width} × ${state.box.height} 像素；可重新拖动修改范围。`;}else state.box=null;controls();});stage.addEventListener("pointercancel",()=>{state.startPoint=null;state.box=null;$("material-selection-box").classList.add("hidden");controls();});
    document.addEventListener("visibilitychange",()=>{if(document.hidden){clearTimeout(state.timer);closeStream();}else schedule();});window.addEventListener("pagehide",()=>{state.epoch++;closeStream();clearTimeout(state.timer);releaseUrls();});window.addEventListener("pageshow",event=>{if(event.persisted){state.epoch++;state.busy=false;state.polling=false;state.uploading=false;state.config=null;$("material-detail-dialog").close();state.dialog=null;if(state.files.length)renderSelected();if(state.workspace==="material")loadConfig();}});
    state.newBatch=stored("hsd-material-new")==="1";
    workspace(location.hash.slice(1));
  }
  boot();
})();
