"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const activeStatuses = new Set(["queued", "processing", "cancelling"]);
  const downloadable = item => item?.downloadable===true&&!!safeUrl(item.download_url);
  const guidance = "如需再次优化，可选择精修，或自行使用 GPT 图像模型处理。";
  const routineNotes = new Set([
    "请核对文字、配色和设计是否完整；修补细节可能与原图不同。",
    "已保留模型返回的完整画布，系统没有裁剪或删除边缘内容。",
    "模型提取可能改变文字、配色或细节，请对照原图确认。",
    "精修内容由模型生成，文字、配色和完整性仍需对照确认。",
    "清理可能改变文字、配色或细节，请对照原图确认。",
    "已按标记位置提出修改要求，模型仍可能改变其他区域，请对照确认。"
  ]);
  const state = {workspace:"numbering",config:null,job:null,pendingJobId:null,files:[],objectUrls:[],busy:false,uploading:false,uncertain:false,retryUpload:false,stopRequested:false,uploadId:null,xhr:null,timer:null,polling:false,authLost:false,filter:"available",newBatch:false,dialog:null,box:null,startPoint:null,sourcesSignature:"",items:new Map(),scroll:{numbering:0,material:0},epoch:0,refineAcks:new Set(),stream:null,streamJob:null,streamErrors:0,streamDisabled:false,clockTimer:null,clockAnchor:null,progressCounts:null,renewTimer:null};
  const metrics = {cards_created:0,cards_updated:0,previews_loaded:0,polls:0};
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
  // Reading a finished result never has to wait for a model call: only writes
  // and the whole-page transitions are blocked while one item is refined.
  function softLocked() {return state.busy||state.uploading||state.uncertain||state.authLost;}
  function refiningId() {
    const job=state.job,progress=job?.progress||{};
    if(!job||!["queued","processing"].includes(job.status))return "";
    return typeof progress.item_id==="string"?progress.item_id:"";
  }
  function refineElapsed() {const started=Number(state.job?.progress?.started_at)||0;if(!started)return 0;return Math.min(3600,Math.max(0,Math.round(Date.now()/1000-started)));}
  function controls() {
    const locked=busy()||state.authLost,reading=softLocked();
    $("material-files").disabled=locked;$("material-start").disabled=(locked&&!(state.uncertain&&state.retryUpload&&!state.busy&&!state.authLost))||!state.files.length||!state.config?.available;
    $("material-start").textContent=state.uploading?"正在上传…":state.busy?"正在提交…":state.uncertain&&state.retryUpload?"重试本次上传":"开始提取";
    $("material-new").disabled=locked;$("material-stop").disabled=state.busy||state.authLost||state.job?.status==="cancelling";
    $("material-stop").textContent=state.job?.status==="cancelling"?"正在停止…":state.uploading||state.uncertain?"停止上传":"停止本批";
    $("material-download-all").disabled=reading||!safeUrl(state.job?.download_url);
    $("material-recheck").disabled=reading||state.polling;
    $("material-upload-check").disabled=state.busy||state.authLost;
    const itemControl=button=>{const item=state.job?.items.find(value=>value.id===button.dataset.itemId),action=button.dataset.materialAction,viewing=action==="download"||action==="compare";
      button.disabled=(viewing?reading:locked)||(action==="download"&&!downloadable(item))||(action==="refine"&&(!item||item.status==="skipped"||!safeUrl(item.image_url)||(item.refine_submission_unknown&&!state.refineAcks.has(item.id))));};
    $("material-grid").querySelectorAll("button").forEach(itemControl);
    const inputControl=input=>{input.disabled=locked;if(input.dataset.refineAck)input.checked=state.refineAcks.has(input.dataset.refineAck);};
    $("material-grid").querySelectorAll("input").forEach(inputControl);
    $("material-source-grid").querySelectorAll("button").forEach(button=>{button.disabled=locked;});
    $("material-detail-actions").querySelectorAll("button").forEach(itemControl);
    $("material-detail-actions").querySelectorAll("input").forEach(inputControl);
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
  function showUpload() {$("material-progress").classList.remove("hidden");$("material-upload-check").classList.toggle("hidden",!state.uncertain);$("material-stop").classList.remove("hidden");$("material-progress-title").textContent=state.uncertain?"正在核对上传结果":"正在上传图片";$("material-progress-message").textContent=state.uncertain?"连接中断，先确认服务器是否收到，避免重复处理。":"上传完成后自动开始提取。";$("material-progress-meter").classList.remove("hidden");$("material-progress-label").textContent="上传进度";$("material-progress-track").setAttribute("aria-label","上传进度");$("material-progress-percent").textContent="";$("material-progress-fill").classList.toggle("indeterminate",true);$("material-progress-track").removeAttribute("aria-valuenow");$("material-progress-detail").textContent="";}
  function clearUpload() {state.uploading=false;state.uncertain=false;state.retryUpload=false;state.stopRequested=false;state.uploadId=null;state.xhr=null;remember("hsd-material-upload",null);$("material-upload-check").classList.add("hidden");}
  function upload(files) {
    return new Promise((resolve,reject)=>{
      const form=new FormData();files.forEach(file=>form.append("files",file));
      const xhr=new XMLHttpRequest();state.xhr=xhr;xhr.open("POST","/api/material/jobs");xhr.timeout=0;xhr.setRequestHeader("X-HSD-Token",window.HSD_TOKEN||"");xhr.setRequestHeader("X-HSD-Upload-ID",state.uploadId);
      xhr.upload.addEventListener("progress",event=>{if(!state.uploading)return;const known=event.lengthComputable&&event.total>0;$("material-progress-fill").classList.toggle("indeterminate",!known);if(known){const percent=Math.min(100,Math.round(event.loaded/event.total*100));$("material-progress-fill").style.width=`${percent}%`;$("material-progress-percent").textContent=`${percent}%`;$("material-progress-track").setAttribute("aria-valuenow",String(percent));$("material-progress-detail").textContent=`上传 ${formatBytes(event.loaded)} / ${formatBytes(event.total)}`;if(percent===100)$("material-progress-message").textContent="上传完成，正在检查图片，请稍候。";}});
      xhr.addEventListener("load",()=>{let data;try{data=JSON.parse(xhr.responseText);}catch(_){reject(new Error("上传结果未确认。"));return;}if(xhr.status<200||xhr.status>=300){const error=new Error(data.error||"上传未完成。");error.status=xhr.status;reject(error);return;}if(!data.id){reject(new Error("上传结果未确认。"));return;}resolve(data);});
      ["error","abort","timeout"].forEach(name=>xhr.addEventListener(name,()=>reject(new Error("上传连接中断，正在核对结果。"))));xhr.send(form);
    });
  }
  async function start(event) {
    event?.preventDefault();const retry=state.uncertain&&state.retryUpload&&!state.stopRequested;if((busy()&&!retry)||state.busy||state.uploading||state.authLost||!state.files.length||!state.config?.available)return;
    if(!window.crypto?.randomUUID){notify("请使用新版 Chrome 或 Edge 打开安全网址后重试。",true);return;}
    const epoch=state.epoch;
    if(!retry)state.uploadId=window.crypto.randomUUID();remember("hsd-material-upload",state.uploadId);state.retryUpload=false;state.uncertain=false;state.uploading=true;notify("");showUpload();controls();
    try{const data=await upload(state.files);if(epoch!==state.epoch)return;
      // The batch exists on the server now. Remember its id before anything
      // else can fail, so a failed snapshot read is retryable instead of
      // leaving a cleared upload id and a dead "重新查询" button.
      state.pendingJobId=data.id;remember("hsd-material-job",data.id);clearUpload();state.newBatch=false;remember("hsd-material-new",null);
      try{await loadJob(data.id);}catch(error){if(epoch!==state.epoch)return;notify("任务已创建，但这次没取到进度；点“重新查询”即可继续。",true);}
    }
    catch(error){if(epoch!==state.epoch)return;state.uploading=false;if([400,413,415,422].includes(error.status)){clearUpload();$("material-progress").classList.add("hidden");notify(error.message,true);}else if(error.status===401){state.uncertain=true;lockAuth();}else{state.uncertain=true;showUpload();await recoverUpload();}}
    finally{if(epoch===state.epoch)controls();}
  }
  async function recoverUpload() {
    if(!state.uploadId||state.busy||state.authLost)return;const epoch=state.epoch;state.busy=true;controls();
    try{const data=await api(`/api/material/upload-status/${encodeURIComponent(state.uploadId)}`);if(epoch!==state.epoch)return;const id=data.job_id||data.id;if(id&&data.state==="completed"){const stop=state.stopRequested||data.cancellation_requested;clearUpload();await loadJob(id);if(epoch!==state.epoch)return;if(stop&&activeStatuses.has(state.job?.status)){const job=await api(jobPath("/cancel"),{expected_revision:state.job.revision});if(epoch===state.epoch)setJob(job);}}else if(data.state==="cancelled"){clearUpload();$("material-progress").classList.add("hidden");notify("上传已停止，可以重新选择图片。");}else if(data.state==="missing"){state.uncertain=true;state.retryUpload=!!state.files.length&&!state.stopRequested;showUpload();notify(state.retryUpload?"当前未找到已受理任务。可重试本次上传（沿用同一个请求），或先停止再更换图片。":"当前未找到已受理任务，请先停止本次上传，再重新选择图片。",true);}else{state.uncertain=true;state.retryUpload=false;showUpload();notify(data.cancellation_requested?"正在停止上传，请稍后查询最终结果。":"还在核对上传结果，请稍后点击“查询上传结果”。不要重复提交。",true);}}
    catch(error){if(epoch===state.epoch&&!state.authLost)notify(error.message||"无法查询上传结果，请稍后重试。",true);}finally{if(epoch===state.epoch){state.busy=false;controls();}}
  }
  async function loadJob(id=state.job?.id||state.pendingJobId) {if(!id||state.authLost)return;const epoch=state.epoch,job=await api(`/api/material/jobs/${encodeURIComponent(id)}`);if(epoch===state.epoch&&!state.authLost){setJob(job);state.pendingJobId=null;}}
  function closeStream() {clearTimeout(state.clockTimer);clearTimeout(state.renewTimer);state.renewTimer=null;if(state.stream)state.stream.close();state.stream=null;state.streamJob=null;}
  function schedule() {
    clearTimeout(state.timer);
    if(!activeStatuses.has(state.job?.status)||state.authLost||document.hidden||state.workspace!=="material"){closeStream();return;}
    updateClock();
    if(state.renewTimer!==null)return;
    if(typeof window.EventSource==="function"&&!state.streamDisabled){openStream();return;}
    state.timer=setTimeout(poll,1500);
  }
  function duration(seconds) {const value=Math.max(0,Math.floor(Number(seconds)||0)),s=value%60,m=Math.floor(value/60)%60,h=Math.floor(value/3600);return h?`${h} 小时 ${m} 分 ${s} 秒`:m?`${m} 分 ${s} 秒`:`${s} 秒`;}
  function elapsedSeconds() {if(!activeStatuses.has(state.job?.status))return Math.max(0,Number(state.job?.progress?.task_elapsed_seconds)||0);return Math.max(0,(state.clockAnchor?.elapsed||0)+((window.performance?.now()||0)-(state.clockAnchor?.received||0))/1000);}
  function progressDetail() {
    const p=state.job?.progress||{},total=Number(p.total)||0,current=Number(p.current)||0;
    const context=state.job?.status==="queued"&&p.queue_position?`排队第 ${p.queue_position} 位`:total>1?`已处理 ${Math.min(current,total)} / ${total} 张原图`:"";
    return `${context?context+" · ":""}本批累计用时 ${duration(elapsedSeconds())}`;
  }
  function updateClock() {
    clearTimeout(state.clockTimer);
    if(!activeStatuses.has(state.job?.status)||document.hidden||state.workspace!=="material")return;
    // The refined card keeps its own elapsed counter, so the batch view stays
    // usable while one picture is being redrawn.
    if(refiningId()){const timer=$("material-grid").querySelector?.("[data-refine-timer]");if(timer)timer.textContent=`精修中 ${refineElapsed()} 秒`;}
    $("material-progress-detail").textContent=progressDetail();state.clockTimer=setTimeout(updateClock,1000);
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
    updateClock();
  }
  async function poll() {if(state.polling||state.authLost||!(state.job||state.pendingJobId))return;const epoch=state.epoch;state.polling=true;count("polls");try{await loadJob();}catch(error){if(epoch===state.epoch&&!state.authLost)notify("暂时无法获取进度，请检查网络；系统不会重复提交图片。",true);}finally{if(epoch===state.epoch){state.polling=false;controls();schedule();}}}
  function setJob(job) {
    if(!job||typeof job.id!=="string"||!Array.isArray(job.items)||!Array.isArray(job.sources))throw new Error("素材结果格式异常，请刷新页面后重试。");
    if(state.job?.id===job.id&&(Number(job.revision)<Number(state.job.revision)||(job.revision===state.job.revision&&Number(job.update_seq)<Number(state.job.update_seq))))return;
    const changed=state.job?.id!==job.id;state.job=job;remember("hsd-material-job",job.id);
    if(changed){closeStream();state.streamDisabled=false;state.streamErrors=0;state.refineAcks.clear();state.items.clear();$("material-grid").replaceChildren();$("material-source-grid").replaceChildren();$("material-source-details").open=false;state.sourcesSignature="";state.filter="available";}
    for(const item of job.items)if(!item.refine_submission_unknown)state.refineAcks.delete(item.id);
    const clockKey=JSON.stringify([job.id,job.progress?.run_id||job.progress?.run_started_at||job.id]),now=window.performance?.now()||0,elapsed=Math.max(0,Number(job.progress?.task_elapsed_seconds)||0);
    if(state.clockAnchor?.key!==clockKey)state.clockAnchor={key:clockKey,elapsed,received:now};
    else if(elapsed>state.clockAnchor.elapsed+(now-state.clockAnchor.received)/1000){state.clockAnchor.elapsed=elapsed;state.clockAnchor.received=now;}
    const progressKey=JSON.stringify([clockKey,job.progress?.source_id]),done=job.progress?.designs_completed,total=job.progress?.designs_total;
    if(state.progressCounts?.key!==progressKey)state.progressCounts={key:progressKey,done:0,total:0};
    if(Number.isInteger(done)&&Number.isInteger(total)&&total>0&&done>=0&&done<=total){if(state.progressCounts.total!==total)state.progressCounts={key:progressKey,done,total};else state.progressCounts.done=Math.max(state.progressCounts.done,done);}
    render();schedule();
  }
  function render() {
    const job=state.job;if(!job)return;const running=activeStatuses.has(job.status),refining=!!refiningId();
    // A refinement is one card's work: keep the batch on screen instead of
    // replacing it with a full-page progress panel.
    $("material-upload-form").classList.add("hidden");$("material-results").classList.remove("hidden");$("material-new").classList.remove("hidden");$("material-progress").classList.toggle("hidden",!running||refining);$("material-upload-check").classList.add("hidden");
    if(running&&!refining){
      const progress=job.progress||{},total=Number(progress.total)||0,current=Number(progress.current)||0,queued=job.status==="queued",phase=String(progress.stage_code||progress.phase||""),counts=state.progressCounts||{};
      $("material-progress-title").textContent=job.status==="cancelling"?"正在停止本批":queued?"排队等待":progress.phase||"正在处理素材";
      $("material-progress-message").textContent=progress.message||"图片处理中，完成的结果会陆续显示。";
      // Only settled generation tasks have a known denominator. This is the
      // current source's generation count, never a model-internal or batch ETA.
      const known=counts.total>0&&!queued&&/designs|saving|source_done|cancelling/.test(phase),percent=known?Math.floor(counts.done/counts.total*100):0;
      $("material-progress-meter").classList.toggle("hidden",!known);$("material-progress-fill").classList.remove("indeterminate");
      const sourceIndex=job.sources.findIndex(source=>source.id===progress.source_id);
      $("material-progress-label").textContent=(total>1?`第 ${Math.min(sourceIndex>=0?sourceIndex+1:current+1,total)} / ${total} 张原图 · `:"")+"本张素材生成进度";
      $("material-progress-percent").textContent=known?`${percent}%`:"";$("material-progress-fill").style.width=known?`${percent}%`:"0%";
      $("material-progress-track").setAttribute("aria-label",$("material-progress-label").textContent);
      if(known){$("material-progress-track").setAttribute("aria-valuenow",String(percent));$("material-progress-message").textContent=`已处理 ${counts.done} / ${counts.total} 个素材${phase==="saving"?"，正在保存结果。":"。"}`;}else $("material-progress-track").removeAttribute("aria-valuenow");
      $("material-progress-detail").textContent=progressDetail();
      const step=/clean|清理/.test(phase)?0:/locat|detect|识别/.test(phase)?1:/design|crop|sav|生成|保存/.test(phase)?2:-1;
      const steps=phase==="refining"?'<li class="current" aria-current="step">精修当前素材</li>':["清理整图","识别设计","生成并保存"].map((name,index)=>`<li${step===index?' class="current" aria-current="step"':""}>${index+1}. ${name}</li>`).join("");if($("material-stage-list").innerHTML!==steps)$("material-stage-list").innerHTML=steps;
    }
    if(job.status==="error")notify(job.error||"本批未能处理，请查看原图下的问题提示。",true);else if(job.status==="cancelled")notify("本批已停止。已经完成的素材仍可查看和下载。");
    const stats=job.stats||{},ready=job.items.filter(downloadable).length,skipped=job.items.filter(item=>item.status==="skipped").length;
    $("material-summary").textContent=`${job.sources.length} 张原图 · ${job.items.length} 个素材${!running||refining?` · ${ready} 个可下载`:""}${skipped?` · ${skipped} 个已舍弃`:""}${stats.failed?` · ${stats.failed} 张处理失败`:""}${!running||refining?` · 本批累计用时 ${duration(elapsedSeconds())}`:""}`;
    $("material-result-title").textContent=running&&!refining?(job.progress?.stage_code==="refining"?"正在精修素材":"正在生成本批素材"):"本批提取结果";$("material-available-count").textContent=String(job.items.length-skipped);
    document.querySelectorAll("[data-material-filter]").forEach(button=>{const active=button.dataset.materialFilter===state.filter;button.classList.toggle("active",active);button.setAttribute("aria-pressed",String(active));});
    const shared=sharedWarnings();$("material-shared-warning").textContent=shared.join("；");$("material-shared-warning").classList.toggle("hidden",!shared.length);
    $("material-generation-warning").classList.toggle("hidden",job.has_generation_failures!==true);
    renderCards();renderSources();
    const warnings=[...new Set([...(job.warnings||[]),...(job.sources||[]).flatMap(source=>[source.error,...(source.warnings||[])].filter(Boolean).map(warning=>`${source.name}：${warning}`))])];
    $("material-batch-info").innerHTML=`<p>可下载 ${ready} 个${skipped?`；已舍弃 ${skipped} 个`:""}。舍弃及失败项不加入下载包。</p><p>图片可下载不表示画质已经过核验，请自行检查文字、配色和完整性。</p>${warnings.map(warning=>`<p>${esc(warning)}</p>`).join("")}<p>云端副本保留三天，请将结果下载到自己的电脑。</p>`;
    controls();
  }
  function visibleItem(item) {return state.filter==="all"||(state.filter==="skipped"?item.status==="skipped":item.status!=="skipped");}
  function itemWarnings(item) {return [...new Set([item.refine_error,...(item.warnings||[])].filter(Boolean))];}
  function routineWarning(warning) {return routineNotes.has(warning)||/^本设计只占原图约 \d+%，已放大局部参考图重画；清晰度仍受原图分辨率限制。$/.test(warning);}
  function specificWarnings(item) {return itemWarnings(item).filter(warning=>warning===item.refine_error||!routineWarning(warning));}
  function processingNotes(item) {return itemWarnings(item).filter(warning=>warning!==item.refine_error&&routineWarning(warning));}
  let warningItems=null,warningCache=[];
  function sharedWarnings() {if(warningItems===state.job?.items)return warningCache;warningItems=state.job?.items;const counts=new Map();for(const item of state.job?.items||[])for(const warning of specificWarnings(item))counts.set(warning,(counts.get(warning)||0)+1);warningCache=[...counts].filter(([,count])=>count>1&&count===state.job.items.length).map(([warning])=>warning);return warningCache;}
  function itemActions(item) {
    const skipped=item.status==="skipped",unknown=item.refine_submission_unknown===true,busyRefine=refiningId()===item.id;
    if(skipped)return `<button class="button button-secondary" type="button" data-material-action="restore" data-item-id="${esc(item.id)}">恢复素材</button>`;
    return `${unknown?`<label class="material-refine-ack"><input type="checkbox" data-refine-ack="${esc(item.id)}"${state.refineAcks.has(item.id)?" checked":""}>上次精修结果尚未确定。重新提交可能重复计费，我确认继续。</label>`:""}<button class="button button-primary" type="button" data-material-action="download" data-item-id="${esc(item.id)}"${downloadable(item)?"":" disabled"}>下载</button><button class="button button-secondary" type="button" data-material-action="refine" data-item-id="${esc(item.id)}"${busyRefine?" disabled":""}>${busyRefine?"精修中…":"精修"}</button><button class="button button-quiet" type="button" data-material-action="skip" data-item-id="${esc(item.id)}">舍弃</button>`;
  }
  function itemContent(item) {
    const skipped=item.status==="skipped",shared=new Set(sharedWarnings()),specific=specificWarnings(item).filter(w=>!shared.has(w)),inline=specific[0],remaining=[...specific.slice(1),...processingNotes(item)],busyRefine=refiningId()===item.id;
    return `<div class="material-item-info"><div class="material-item-heading"><strong class="material-item-name">${esc(item.name)}</strong>${busyRefine?`<span class="material-item-badge refining" data-refine-timer>精修中 ${refineElapsed()} 秒</span>`:skipped||item.refined?`<span class="material-item-badge ${skipped?"skipped":"completed"}">${skipped?"已舍弃":"已精修"}</span>`:""}</div>${busyRefine?`<p class="material-item-warning">只精修这一张，其他素材和下载仍可操作；完成后这张图会自动替换。</p>`:""}${inline?`<p class="material-item-warning">${esc(inline)}</p>`:""}<div class="material-item-actions">${itemActions(item)}</div><details><summary>详情</summary>${remaining.length?`<ul>${remaining.map(w=>`<li>${esc(w)}</li>`).join("")}</ul>`:""}<p>${Number(item.width)||0} × ${Number(item.height)||0} 像素 · PNG</p><p>${guidance}</p></details></div>`;
  }
  function previewUrl(value) {return safeUrl(value.thumbnail_url)||safeUrl(value.image_url);}
  function previewHtml(item) {return `<button class="material-item-preview" data-material-action="compare" data-item-id="${esc(item.id)}" type="button" aria-label="放大对照 ${esc(item.name)}"><img src="${esc(previewUrl(item))}" alt="${esc(item.name)}" width="640" height="640" loading="lazy" decoding="async" fetchpriority="low"></button>`;}
  function renderCards() {
    const grid=$("material-grid"),visible=[];
    const nextExisting=new Map();let anchor=null;
    for(let index=state.job.items.length-1;index>=0;index--){const item=state.job.items[index];nextExisting.set(item.id,anchor);if(state.items.has(item.id))anchor=state.items.get(item.id).node;}
    for(const item of state.job.items){
      const key=JSON.stringify([item.name,item.status,item.warnings,item.width,item.height,item.downloadable,item.refined,item.refine_error,item.refine_submission_unknown,sharedWarnings(),refiningId()===item.id]),preview=previewHtml(item);let record=state.items.get(item.id);
      const content=!record||record.key!==key?itemContent(item):record.content;
      if(!record){
        const node=document.createElement("article");node.className="material-item";node.dataset.itemId=item.id;
        node.innerHTML=preview+`<div data-material-content>${content}</div>`;grid.insertBefore(node,nextExisting.get(item.id)||null);
        record={node,key,content,preview,contentNode:node.querySelector("[data-material-content]")};state.items.set(item.id,record);count("cards_created");count("cards_updated");count("previews_loaded");
      }else{
        // Keep the image element when only review/status/details change. A new
        // img with the same private/no-store URL would download/decode again.
        if(record.preview!==preview){
          const image=record.node.querySelector(".material-item-preview img"),button=record.node.querySelector(".material-item-preview");
          if(image&&button){const url=previewUrl(item);if(image.getAttribute("src")!==url){image.src=url;count("previews_loaded");}image.alt=item.name;button.setAttribute("aria-label",`放大对照 ${item.name}`);}
          else{record.node.innerHTML=preview+`<div data-material-content>${content}</div>`;record.contentNode=record.node.querySelector("[data-material-content]");count("previews_loaded");}
          record.preview=preview;
        }
        if(record.content!==content){const target=record.contentNode,open=target?.querySelector("details")?.open;
          if(target){target.innerHTML=content;if(open&&target.querySelector("details"))target.querySelector("details").open=true;}
          else record.node.innerHTML=preview+`<div data-material-content>${content}</div>`;
          record.key=key;record.content=content;count("cards_updated");
        }
      }
      const shown=visibleItem(item);record.node.classList.toggle("hidden",!shown);if(shown)visible.push(item);
    }
    const ids=new Set(state.job.items.map(item=>item.id));for(const [id,record]of state.items){if(!ids.has(id)){record.node.remove();state.items.delete(id);}}
    $("material-empty").classList.toggle("hidden",visible.length>0);$("material-empty").textContent=activeStatuses.has(state.job.status)?"完成的素材会陆续显示在这里。":state.filter==="skipped"?"没有已舍弃的素材。":"这里暂无素材，请从原图框选补提，或查看已舍弃的素材。";
  }
  function sourceActions(source) {
    // A failed source gets a one-click retry: staff should not have to draw a
    // rectangle just because the locator was unlucky once.
    const retry=source.error&&!source.submission_unknown
      ?`<button class="button button-primary" data-retry-source="${esc(source.id)}" type="button">自动重试</button>`:"";
    return `<div class="material-source-actions">${retry}<button class="button button-secondary" data-source-id="${esc(source.id)}" type="button">${source.error?"框选补提":"框选补提"}</button></div>`;
  }
  function renderSources() {
    const details=$("material-source-details");if(state.job.sources.some(source=>source.error))details.open=true;
    // A closed original-image drawer must not compete with result previews.
    if(!details.open)return;
    const cards=state.job.sources.map(source=>`<article class="material-source-card"><img src="${esc(previewUrl(source))}" alt="${esc(source.name)}" width="640" height="640" loading="lazy" decoding="async" fetchpriority="low"><strong>${esc(source.name)}</strong>${source.error?`<p>${esc(source.error)}</p>`:""}${sourceActions(source)}</article>`).join("");
    if(cards===state.sourcesSignature)return;state.sourcesSignature=cards;$("material-source-grid").innerHTML=cards;
  }
  async function mutate(action,body) {
    if(state.busy||state.uploading||state.uncertain||(action!=="cancel"&&activeStatuses.has(state.job?.status))||state.authLost||!state.job)return false;const epoch=state.epoch;state.busy=true;state.lastConflict=false;notify("");controls();
    try{const result=await api(jobPath(`/${action}`),{expected_revision:state.job.revision,...body});if(epoch!==state.epoch)return false;if(result?.items)setJob(result);else await loadJob();return true;}
    catch(error){if(epoch!==state.epoch)return false;state.lastConflict=error.status===409;notify(error.status===409?"本批状态已更新，正在重新读取；请核对后再操作。":error.message,true);if(error.status===409)try{await loadJob();}catch(_){}return false;}
    finally{if(epoch===state.epoch){state.busy=false;controls();}}
  }
  async function retrySource(sourceId) {
    const source=state.job?.sources.find(value=>value.id===sourceId);
    if(!source||!source.error||busy()||state.authLost)return false;
    const done=await mutate("redo",{source_id:sourceId});
    if(done)notify("已重新自动识别这张原图，结果会显示在上方。");
    return done;
  }
  async function refineItem(itemId,acknowledge) {
    // One paid call for one card. It must not take the page hostage: the batch
    // stays readable and this card reports its own progress until it lands.
    if(state.busy||state.authLost||!state.job)return false;
    const epoch=state.epoch;state.busy=true;state.lastConflict=false;notify("");
    try{const result=await api(jobPath("/refine"),{expected_revision:state.job.revision,item_id:itemId,...(acknowledge?{acknowledge_unknown:true}:{})});if(epoch!==state.epoch)return false;if(result?.items)setJob(result);else await loadJob();return true;}
    catch(error){if(epoch!==state.epoch)return false;state.lastConflict=error.status===409;notify(error.status===409?"本批状态已更新，正在重新读取；请核对后再操作。":error.message,true);if(error.status===409)try{await loadJob();}catch(_){}return false;}
    finally{if(epoch===state.epoch){state.busy=false;render();controls();}}
  }
  async function stop() {
    if(state.busy||state.authLost)return;
    if(state.uploading||state.uncertain){const epoch=state.epoch;state.busy=true;state.stopRequested=true;state.retryUpload=false;controls();try{await api(`/api/material/upload-status/${encodeURIComponent(state.uploadId)}/cancel`,{});if(epoch!==state.epoch)return;state.xhr?.abort();state.uploading=false;state.uncertain=true;}catch(error){if(epoch===state.epoch)notify(error.message,true);}finally{if(epoch===state.epoch){state.busy=false;await recoverUpload();controls();}}return;}
    const stopped=await mutate("cancel",{});if(!stopped&&state.lastConflict&&activeStatuses.has(state.job?.status))await mutate("cancel",{});
  }
  function download(url) {const safe=safeUrl(url);if(!safe||softLocked())return;const id=state.job.id,frame=$("material-download-frame");frame.onload=()=>{if(state.job?.id!==id)return;let text="";try{text=(frame.contentDocument?.body?.textContent||"").trim();}catch(_){text="无法读取下载结果。";}if(!text)return;let error;try{error=JSON.parse(text).error;}catch(_){}notify(error||"下载未能开始，请检查网络后重试。",true);if(/访问码|会话|登录/.test(error||""))lockAuth();};frame.onerror=()=>{if(state.job?.id===id)notify("下载连接中断，请检查网络后重试。",true);};frame.src=`${safe}${safe.includes("?")?"&":"?"}frame=1`;notify("已请求下载，请查看浏览器下载列表；未开始时可重试。");}
  async function itemAction(event) {
    const button=event.target.closest("[data-material-action]");if(!button||state.authLost)return;const item=state.job.items.find(item=>item.id===button.dataset.itemId);if(!item)return;
    const action=button.dataset.materialAction;
    // Viewing and downloading a finished item stays available during a run.
    if(["compare","download","refine"].includes(action)?softLocked():busy())return;
    if(action==="compare"){openDetail(item.source_id,item,false);return;}
    if(action==="download"){if(downloadable(item))download(item.download_url);return;}
    if(action==="refine"){
      // The server refines one card at a time; do not stack a second paid call.
      if(refiningId()&&refiningId()!==item.id)return;
      if(item.status==="skipped"||!safeUrl(item.image_url))return;
      const unknown=item.refine_submission_unknown===true;if(unknown&&!state.refineAcks.has(item.id)){notify("上次精修结果尚未确定，请先确认重新提交可能重复计费。",true);return;}
      state.refineAcks.delete(item.id);
      if(await refineItem(item.id,unknown)){if(state.dialog?.itemId===item.id)$("material-detail-dialog").close();}
      return;
    }
    if(!["skip","restore"].includes(action))return;
    const result=await mutate("resolve",{item_id:item.id,action});if(result){if(state.dialog)$("material-detail-dialog").close();else{const next=state.job.items.find(value=>visibleItem(value)&&value.id!==item.id);state.items.get(next?.id)?.node.querySelector("button")?.focus({preventScroll:true});}notify(action==="skip"?"已舍弃，可在“已舍弃”中恢复。":"已恢复素材。");}
  }
  function acknowledgeRefine(event) {const input=event.target.closest("[data-refine-ack]");if(!input||busy()||state.authLost)return;const item=state.job?.items.find(value=>value.id===input.dataset.refineAck);if(!item?.refine_submission_unknown)return;if(input.checked)state.refineAcks.add(item.id);else state.refineAcks.delete(item.id);controls();}
  function showBatchRecords() {const details=$("material-batch-details");details.open=true;details.querySelector("summary")?.focus({preventScroll:true});details.scrollIntoView({block:"nearest",behavior:"smooth"});}
  function setLoading(el,loading) {
    // Mark the picture as still loading without dimming it: a translucent
    // overlay made the source and the result look grey and washed out.
    el.classList.toggle("image-loading",loading);
    const frame=el.parentElement;if(frame)frame.classList.toggle("image-loading",loading);
  }
  function swapImage(el,value) {
    // Show the already-cached thumbnail first, then swap in the full file once it
    // decodes. Without this the previous item's picture stays on screen while the
    // next multi-megabyte PNG downloads, which looks like a stuck dialog.
    const full=safeUrl(value&&value.image_url),thumb=safeUrl(value&&value.thumbnail_url)||full;
    el.dataset.imageToken=String((Number(el.dataset.imageToken||0)+1));
    const token=el.dataset.imageToken;
    if(!thumb){el.removeAttribute("src");setLoading(el,false);return;}
    if(el.getAttribute("src")!==thumb)el.src=thumb;
    if(!full||full===thumb){setLoading(el,false);return;}
    setLoading(el,true);
    const preload=new Image();
    preload.decoding="async";
    const settle=()=>{if(el.dataset.imageToken===token){if(preload.naturalWidth)el.src=full;setLoading(el,false);}};
    preload.onload=settle;preload.onerror=settle;preload.src=full;
  }
  function openDetail(sourceId,item=null,redo=false) {
    const source=state.job.sources.find(value=>value.id===sourceId);if(!source)return;state.dialog={sourceId,itemId:item?.id||null,redo};state.box=null;state.startPoint=null;
    const before=!redo&&item?.refined&&safeUrl(item.previous_image?.image_url)?item.previous_image:null;
    $("material-detail-title").textContent=redo?(item?"标记需要修改的位置":"框选完整设计"):item?.name||source.name;$("material-detail-note").textContent=redo?source.name:before?"精修前后对照":"查看生成结果";
    $("material-detail-source-caption").textContent=before?"精修前":"上传原图";$("material-detail-output-caption").textContent=before?"精修后":"当前结果";
    swapImage($("material-detail-source"),before||source);swapImage($("material-detail-output"),item);$("material-detail-output-figure").classList.toggle("hidden",!item);$("material-detail-warning").textContent=(item?specificWarnings(item):source.error?[source.error]:[]).join("；");
    $("material-detail-guidance").textContent=item?guidance:"";$("material-detail-guidance").classList.toggle("hidden",!item);
    const notes=item?processingNotes(item):[];$("material-detail-processing-notes").open=false;$("material-detail-processing-notes").classList.toggle("hidden",!notes.length);$("material-detail-processing-notes-list").innerHTML=notes.map(note=>`<li>${esc(note)}</li>`).join("");
    $("material-redo-controls").classList.toggle("hidden",!redo);$("material-selection-stage").classList.toggle("selecting",redo);$("material-selection-box").classList.add("hidden");$("material-box-note").textContent=item?"在原图拖动标记问题位置。只重做这张素材，不改动其他已完成项。":"在原图拖动框选一个完整设计，文字和装饰一起框入。";$("material-correction-kind").selectedIndex=0;$("material-correction-note").value="";$("material-dialog-message").classList.add("hidden");
    $("material-detail-actions").innerHTML=redo?"":item?itemActions(item):"";
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
  function reset() {if(busy()||state.authLost)return;state.epoch++;closeStream();clearTimeout(state.timer);state.refineAcks.clear();state.polling=false;state.job=null;state.pendingJobId=null;state.clockAnchor=null;state.progressCounts=null;state.items.clear();state.sourcesSignature="";state.newBatch=true;state.files=[];releaseUrls();remember("hsd-material-job",null);remember("hsd-material-new","1");$("material-files").value="";$("material-selected-files").replaceChildren();$("material-grid").replaceChildren();$("material-source-grid").replaceChildren();$("material-source-details").open=false;$("material-upload-form").classList.remove("hidden");$("material-results").classList.add("hidden");$("material-progress").classList.add("hidden");$("material-new").classList.add("hidden");notify("");controls();$("material-files").focus();}
  function boot() {
    document.querySelectorAll("[data-workspace]").forEach(link=>link.addEventListener("click",event=>{event.preventDefault();workspace(link.dataset.workspace,true);}));window.addEventListener("hashchange",()=>workspace(location.hash.slice(1)));
    $("material-files").addEventListener("change",event=>selectFiles(event.target.files));$("material-upload-form").addEventListener("submit",start);$("material-selected-files").addEventListener("click",event=>{const button=event.target.closest("[data-remove-file]");if(!button||busy())return;state.files.splice(Number(button.dataset.removeFile),1);renderSelected();controls();});
    const drop=$("material-dropzone");drop.addEventListener("keydown",event=>{if(event.target===drop&&["Enter"," "].includes(event.key)){event.preventDefault();$("material-files").click();}});["dragenter","dragover"].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();if(!busy())drop.classList.add("dragging");}));["dragleave","drop"].forEach(name=>drop.addEventListener(name,event=>{event.preventDefault();drop.classList.remove("dragging");if(name==="drop")selectFiles(event.dataTransfer.files,true);}));
    $("material-source-details").addEventListener("toggle",()=>{if(state.job){renderSources();controls();}});
    $("material-generation-warning").addEventListener("click",showBatchRecords);
    $("material-grid").addEventListener("change",acknowledgeRefine);$("material-detail-actions").addEventListener("change",acknowledgeRefine);
    $("material-stop").addEventListener("click",stop);$("material-upload-check").addEventListener("click",recoverUpload);$("material-new").addEventListener("click",reset);$("material-recheck").addEventListener("click",poll);$("material-download-all").addEventListener("click",()=>download(state.job?.download_url));$("material-grid").addEventListener("click",itemAction);$("material-detail-actions").addEventListener("click",itemAction);$("material-source-grid").addEventListener("click",event=>{const retry=event.target.closest("[data-retry-source]");if(retry){if(!busy())retrySource(retry.dataset.retrySource);return;}const button=event.target.closest("[data-source-id]");if(button&&!busy())openDetail(button.dataset.sourceId,null,true);});
    $("material-filter").addEventListener("click",event=>{const button=event.target.closest("[data-material-filter]");if(button){state.filter=button.dataset.materialFilter;render();}});$("material-detail-close").addEventListener("click",()=>$("material-detail-dialog").close());$("material-detail-dialog").addEventListener("close",()=>{state.dialog=null;state.box=null;state.startPoint=null;});$("material-redo-submit").addEventListener("click",redo);$("material-unknown-ack").addEventListener("change",controls);
    const stage=$("material-selection-stage");stage.addEventListener("pointerdown",event=>{if(!state.dialog?.redo||busy())return;const point=imagePoint(event);if(!point)return;event.preventDefault();state.startPoint=point;stage.setPointerCapture(event.pointerId);selectionMove(event);});stage.addEventListener("pointermove",selectionMove);stage.addEventListener("pointerup",event=>{if(!state.startPoint)return;selectionMove(event);state.startPoint=null;if(state.box&&state.box.width>=8&&state.box.height>=8){$("material-box-note").textContent=`已框选 ${state.box.width} × ${state.box.height} 像素；可重新拖动修改范围。`;}else state.box=null;controls();});stage.addEventListener("pointercancel",()=>{state.startPoint=null;state.box=null;$("material-selection-box").classList.add("hidden");controls();});
    document.addEventListener("visibilitychange",()=>{if(document.hidden){clearTimeout(state.timer);closeStream();}else schedule();});window.addEventListener("pagehide",()=>{state.epoch++;closeStream();clearTimeout(state.timer);releaseUrls();});window.addEventListener("pageshow",event=>{if(event.persisted){state.epoch++;state.busy=false;state.polling=false;state.uploading=false;state.config=null;$("material-detail-dialog").close();state.dialog=null;if(state.files.length)renderSelected();if(state.workspace==="material")loadConfig();}});
    state.newBatch=stored("hsd-material-new")==="1";
    workspace(location.hash.slice(1));
  }
  boot();
})();
