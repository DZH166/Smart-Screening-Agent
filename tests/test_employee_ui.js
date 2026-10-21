// Employee upload/download checks use a small DOM/XHR stub; no network or key access.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = new Map();
function element(id) {
  if (!nodes.has(id)) {
    const classes = new Set();
    const node={id, value:'', files:[], disabled:false, innerHTML:'', writes:{text:0,width:0}, attributes:{},
      previousElementSibling:{textContent:''}, dataset:{}, style:{setProperty(){}},
      classList:{add(...values){values.forEach((value)=>classes.add(value));},remove(...values){values.forEach((value)=>classes.delete(value));},contains(value){return classes.has(value);},toggle(value,force){if(force===undefined)force=!classes.has(value);if(force)classes.add(value);else classes.delete(value);}},
      querySelectorAll(){return [];},querySelector(selector){return element(`${id}:${selector}`);},
      addEventListener(){},replaceChildren(){},setAttribute(name,value){this.attributes[name]=String(value);},focus(){sandbox.document.activeElement=this;},
    };
    let text='',width='';
    Object.defineProperty(node,'textContent',{get(){return text;},set(value){this.writes.text++;text=String(value);}});
    Object.defineProperty(node.style,'width',{get(){return width;},set(value){node.writes.width++;width=value;}});
    nodes.set(id,node);
  }
  return nodes.get(id);
}
const xhrs = [];
class FakeXHR {
  constructor(){this.listeners={};this.upload={addEventListener:(name,callback)=>{this.progress=callback;}};this.headers={};xhrs.push(this);}
  open(method,url){this.method=method;this.url=url;}
  setRequestHeader(name,value){this.headers[name]=value;}
  addEventListener(name,callback){this.listeners[name]=callback;}
  send(data){this.data=data;}
  abort(){this.aborted=true;this.listeners.abort?.();}
  load(status,response){this.status=status;this.responseText=JSON.stringify(response);this.listeners.load();}
}
const location={origin:'http://192.168.1.2:8805',assign(url){location.assigned=url;}};
const storage=new Map(),calls=[],timers=new Map();let nextTimer=0,nextUploadId=0,fetchHandler=async()=>({ok:true,status:200,json:async()=>({ready:true})});
const setTimer=(callback,delay)=>{timers.set(++nextTimer,{callback,delay});return nextTimer;};
const clearTimer=(id)=>timers.delete(id);
const sandbox={document:{getElementById:element,querySelectorAll(selector){
  if(selector!=='.step')return [];
  return [1,2,3].map((number)=>{const node=element(`step-${number}`);node.dataset.step=String(number);return node;});
},body:{classList:{toggle(){}}},documentElement:{dataset:{}}},
  window:{HSD_ACCESS:{lan:true,remote:true},HSD_TOKEN:'session-token',location,setTimeout:setTimer,clearTimeout:clearTimer,scrollTo(){},crypto:{randomUUID:()=>`00000000-0000-4000-8000-${String(++nextUploadId).padStart(12,'0')}`}},
  location, performance:{now:()=>0},setTimeout:setTimer,clearTimeout:clearTimer,AbortController,
  sessionStorage:{setItem:(key,value)=>storage.set(key,value),getItem:(key)=>storage.get(key)||null,removeItem:(key)=>storage.delete(key)},
  fetch:async(url,options)=>{calls.push({url,options});return fetchHandler(url,options);},
  FormData:class{constructor(){this.parts=[];}append(...part){this.parts.push(part);}},XMLHttpRequest:FakeXHR,
};
const source=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/app.js'),'utf8');
assert.ok(source.includes('init().catch('));
vm.runInNewContext(source.replace(/  init\(\)\.catch\([^\n]+\);/, '  window.testUI={state,validateUploadFiles,configureAccess,setFormBusy,uploadFiles,isBusy,renderProgress,renderSummary,renderDone,openOutput,formatBytes,updateUploadSelection,startJob,recoverUpload,rememberUpload,storedUpload,stopUpload,stopJob,pollJob,renderJob,resetTask};'),sandbox);
const ui=sandbox.window.testUI;
const MiB=1024*1024;
const workbook={name:'员工表格.XLSX',size:2*MiB};
const zip={name:'原稿.ZIP',size:20*MiB};
// File metadata only: these checks allocate no multi-gigabyte input.
const largeWorkbook={name:'large.xlsx',size:5*1024*MiB};
const largeZip={name:'large.zip',size:2*1024*1024*MiB};

async function main(){
  assert.equal(ui.validateUploadFiles(workbook,zip),'');
  assert.match(ui.validateUploadFiles(null,zip),/表/);
  assert.match(ui.validateUploadFiles({name:'a.xls',size:1},zip),/xlsx/);
  assert.match(ui.validateUploadFiles(workbook,null),/ZIP/);
  assert.match(ui.validateUploadFiles(workbook,{name:'a.rar',size:1}),/zip/);
  assert.match(ui.validateUploadFiles(workbook,{name:'a.zip',size:0}),/为空/);
  assert.equal(ui.validateUploadFiles(largeWorkbook,largeZip),'','no hardcoded default byte ceiling');
  ui.configureAccess({lan:true,remote:true,upload_limits:{workbook_bytes:100*MiB,source_bytes:1900*MiB,total_bytes:10*MiB}});
  assert.match(ui.validateUploadFiles({name:'a.xlsx',size:101*MiB},zip),/100\.0 MiB/,'only a finite limit actually supplied by the server is honoured');
  assert.match(ui.validateUploadFiles(workbook,{name:'a.zip',size:1901*MiB}),/1\.86 GiB/);
  assert.match(ui.validateUploadFiles(workbook,zip),/合计/);
  ui.configureAccess({lan:true,remote:true,upload_limits:{workbook_bytes:null,source_bytes:null,total_bytes:null}});
  assert.equal(ui.validateUploadFiles(largeWorkbook,largeZip),'','null clears earlier finite limits instead of converting to zero or restoring old caps');
  ui.configureAccess({lan:true,remote:true,upload_limits:{workbook_bytes:1,source_bytes:1,total_bytes:2}});
  ui.configureAccess({lan:true,remote:true});
  assert.equal(ui.validateUploadFiles(largeWorkbook,largeZip),'','missing limits do not preserve a previous legacy ceiling');
  element('source-upload').files=[largeZip];ui.updateUploadSelection('source-upload');
  assert.match(element('source-upload-name').textContent,/2\.00 TiB/);
  assert.equal(element('source-upload-error').textContent,'');
  assert.equal(ui.formatBytes(0),'0 B');assert.equal(ui.formatBytes(1),'1 B');assert.equal(ui.formatBytes(1023),'1023 B');
  assert.equal(ui.formatBytes(1024),'1.0 KiB');assert.equal(ui.formatBytes(2*MiB),'2.0 MiB');
  assert.equal(ui.formatBytes(1024*MiB),'1.00 GiB');assert.equal(ui.formatBytes(-1),'大小未知');
  ui.setFormBusy(false);
  assert.ok(element('local-workbook-field').classList.contains('hidden'));
  assert.ok(element('local-source-field').classList.contains('hidden'));
  assert.ok(element('local-output-field').classList.contains('hidden'));
  assert.ok(!element('upload-fields').classList.contains('hidden'));
  assert.ok(element('workbook-path').disabled && element('source-path').disabled && element('output-path').disabled);
  assert.ok(!element('workbook-upload').disabled && !element('source-upload').disabled);
  assert.ok(element('ai-settings-button').classList.contains('hidden'));
  assert.ok(!element('open-output-button').classList.contains('hidden'));
  assert.ok(element('lan-note').classList.contains('hidden'));
  assert.ok(element('host-management').classList.contains('hidden'));
  assert.ok(element('shutdown-button').classList.contains('hidden'));
  assert.ok(!element('lan-note').textContent.includes('素材目录'));

  const pending=ui.uploadFiles(workbook,zip,12);
  const xhr=xhrs.at(-1);
  assert.equal(xhr.method,'POST');assert.equal(xhr.url,'/api/jobs/upload');
  assert.equal(xhr.timeout,0,'large uploads have no fixed browser time ceiling');
  assert.equal(xhr.headers['X-HSD-Token'],'session-token');
  assert.ok(!Object.keys(xhr.headers).some((key)=>key.toLowerCase()==='content-type'));
  assert.equal(xhr.data.parts.length,3);
  assert.equal(xhr.data.parts[0][0],'workbook');assert.equal(xhr.data.parts[0][1],workbook);
  assert.equal(xhr.data.parts[1][0],'source');assert.equal(xhr.data.parts[1][1],zip);
  assert.equal(xhr.data.parts[2][0],'start_number');assert.equal(xhr.data.parts[2][1],'12');
  xhr.progress({lengthComputable:true,loaded:25,total:100});
  assert.equal(element('upload-progress-percent').textContent,'25%');
  assert.match(element('upload-progress-detail').textContent,/25 B \/ 100 B/);
  const textWrites=()=>['upload-progress-percent','upload-progress-label','upload-progress-detail'].reduce((sum,id)=>sum+element(id).writes.text,0);
  const previousTextWrites=textWrites(),previousWidthWrites=element('upload-progress-fill').writes.width;
  for(let index=0;index<100;index++)xhr.progress({lengthComputable:true,loaded:25,total:100});
  assert.equal(textWrites(),previousTextWrites,'duplicate visible progress must not reset text nodes');
  assert.equal(element('upload-progress-fill').writes.width,previousWidthWrites,'duplicate progress must not reassign width');
  xhr.progress({lengthComputable:true,loaded:100,total:100});
  assert.ok(element('upload-progress-label').textContent.includes('正在检查'));
  xhr.load(200,{id:'employee-job'});
  assert.equal((await pending).id,'employee-job');
  const failure=ui.uploadFiles(workbook,zip,1);
  xhrs.at(-1).load(413,{error:'主机无法保存文件，请检查磁盘后重试'});
  await assert.rejects(failure,/检查磁盘/,'server errors remain authoritative');
  for(const [event,message] of [['error',/连接中断/],['abort',/已中止/],['timeout',/超时/]]){
    const rejected=ui.uploadFiles(workbook,zip,1);xhrs.at(-1).listeners[event]();
    await assert.rejects(rejected,message);
  }
  element('workbook-upload').files=[largeWorkbook];element('source-upload').files=[largeZip];element('start-number').value='0';
  const requestsBeforeInvalid=xhrs.length;
  await ui.startJob({preventDefault(){}});
  assert.equal(xhrs.length,requestsBeforeInvalid);assert.match(element('start-number-error').textContent,/1 到 9999/);
  assert.equal(sandbox.document.activeElement,element('start-number'),'start-number validation and error focus remain required');

  function assertStep(active){
    for(const number of [1,2,3]){
      const step=element(`step-${number}`);
      assert.equal(step.classList.contains('active'),number===active,`step ${number} active`);
      assert.equal(step.classList.contains('complete'),number<active,`step ${number} complete`);
      assert.equal(step.querySelector('i').textContent,number<active?'✓':String(number));
    }
  }
  for(const [stage,label,step] of [[undefined,'处理',2],['cpu','本机处理',2],['ai','AI 复核',2],['export','导出',3]]){
    ui.state.job={id:'my-job',status:'queued',queue_stage:stage,queue_position:2,progress:{current:8,total:20}};
    assert.ok(ui.isBusy());ui.renderProgress();
    assert.equal(element('processing-eyebrow').textContent,'排队中');
    assert.equal(element('processing-title').textContent,`等待${label}…`);
    assert.equal(element('processing-message').textContent,`${label}队列第 2 位，轮到后会自动开始。`);
    assert.equal(element('progress-percent').textContent,'','queued work must not display a stale stage percentage');
    assert.equal(element('progress-detail').textContent,'等待开始');
    assert.equal(element('progress-fill').style.width,'');
    assert.ok(element('progress-fill').classList.contains('indeterminate'));
    assertStep(step);
    ui.state.job.queue_position=0;ui.renderProgress();
    assert.equal(element('processing-message').textContent,`正在等待${label}，轮到后会自动开始。`,'unknown position must not imply zero jobs ahead');
  }
  for(const [status,eyebrow,title,step] of [
    ['importing','读取文件','正在读取文件…',2],
    ['matching','匹配图片','正在比对图片…',2],
    ['ai_review','复核疑难项','正在复核有疑问的图片…',2],
    ['exporting','导出结果','正在整理并导出…',3],
  ]){
    ui.state.job={id:'my-job',status,progress:{current:3,total:8,message:'阶段处理说明'}};
    assert.ok(ui.isBusy());ui.renderProgress();
    assert.equal(element('processing-eyebrow').textContent,eyebrow);
    assert.equal(element('processing-title').textContent,title);
    assert.equal(element('progress-percent').textContent,'38%');
    assert.equal(element('progress-detail').textContent,'当前阶段 3 / 8','progress describes its own stage, not whole-batch completion');
    assert.equal(element('progress-fill').style.width,'38%');
    assert.ok(!element('progress-fill').classList.contains('indeterminate'));
    assertStep(step);
    ui.state.job.progress={current:0,total:0};ui.renderProgress();
    assert.equal(element('progress-percent').textContent,'');
    assert.equal(element('progress-detail').textContent,'准备中…');
    assert.ok(element('progress-fill').classList.contains('indeterminate'));
  }
  // AI-first phases describe the current stage, never claim local matching has
  // finished while the model is still searching the complete preview library.
  for(const status of ['matching','ai_review']){
    ui.state.job={id:'ai-first-job',status,matching_mode:'ai_first',progress:{phase:'ai_retrieval',current:2,total:5,message:'正在查找第 2 组图片'}};
    ui.renderProgress();
    assert.equal(element('processing-eyebrow').textContent,'AI 查找');
    assert.equal(element('processing-title').textContent,'AI 正在查找对应图片…');
    assert.equal(element('processing-message').textContent,'正在查找第 2 组图片');
    assert.equal(element('progress-detail').textContent,'当前阶段 2 / 5');
    assert.equal(element('progress-percent').textContent,'40%');assertStep(2);
    ui.state.job.progress={phase:'local_verification',current:4,total:5,message:'AI 暂时无法连接，正在使用本机匹配继续处理。'};
    ui.renderProgress();
    assert.equal(element('processing-eyebrow').textContent,'本机核验');
    assert.equal(element('processing-title').textContent,'正在核验图案与文件…');
    assert.match(element('processing-message').textContent,/无法连接.*本机匹配/);
    assert.equal(element('progress-percent').textContent,'80%');
  }
  ui.state.job={id:'ai-first-queued',status:'queued',matching_mode:'ai_first',queue_stage:'ai',queue_position:3};
  ui.renderProgress();assert.equal(element('processing-title').textContent,'等待AI 查找…');
  assert.equal(element('processing-message').textContent,'AI 查找队列第 3 位，轮到后会自动开始。');
  assert.equal(element('progress-percent').textContent,'');
  ui.state.job={id:'ai-first-unmeasured',status:'ai_review',matching_mode:'ai_first',progress:{phase:'ai_retrieval'}};
  ui.renderProgress();assert.match(element('processing-message').textContent,/查找候选.*汇总本机核验/);
  assert.equal(element('progress-percent').textContent,'','unknown AI work must not imply a whole-batch percentage');
  ui.state.job={id:'parallel-job',status:'ai_review',matching_mode:'ai_first',progress:{phase:'parallel_verification',current:8,total:10,message:'AI 查找 2 / 6 组；本机已核验 12 / 60 张。'}};
  ui.renderProgress();
  assert.equal(element('processing-eyebrow').textContent,'同时处理');
  assert.equal(element('processing-title').textContent,'AI 查找与本机核验进行中…');
  assert.equal(element('processing-message').textContent,'AI 查找 2 / 6 组；本机已核验 12 / 60 张。');
  assert.equal(element('progress-detail').textContent,'两项进度分别计数');
  assert.equal(element('progress-percent').textContent,'','independent denominators must never create a summed batch percentage');
  assert.equal(element('progress-fill').style.width,'');assertStep(2);
  ui.state.job.progress={phase:'local_verification',current:36,total:60,message:'AI 查找已结束，本机正在核验图案与文件…'};
  ui.renderProgress();
  assert.equal(element('progress-percent').textContent,'60%');
  assert.equal(element('processing-eyebrow').textContent,'本机核验');
  assert.equal(element('progress-detail').textContent,'当前阶段 36 / 60');
  ui.state.job.progress={phase:'ai_retrieval',current:5,total:6,message:'本机核验完成，正在等待 AI 查找结果…'};
  ui.renderProgress();assert.equal(element('progress-percent').textContent,'83%');
  assert.equal(element('processing-eyebrow').textContent,'AI 查找');
  assert.equal(element('progress-detail').textContent,'当前阶段 5 / 6');
  ui.state.job={id:'my/job',status:'done',rows:[],download_ready:true};
  ui.renderDone();
  assert.match(element('output-directory').textContent,/仅包含编号表格与 AI 文件/);
  assert.ok(!element('output-directory').textContent.includes('清单'),'employee ZIP does not contain host-only audit records');
  assert.equal(element('open-output-button').textContent,'下载结果 ZIP ↓');
  assert.ok(!element('open-output-button').disabled);
  await ui.openOutput();
  assert.equal(element('result-download-frame').src,'/api/jobs/my%2Fjob/download?frame=1');
  assert.equal(location.assigned,undefined,'download must never navigate away from the employee page');
  assert.ok(calls.at(-1).url.endsWith('/download-status'),'the server validates before the browser streams the ZIP');
  element('result-download-frame').contentDocument={body:{textContent:JSON.stringify({error:'下载结果发生变化，请重新处理。'})}};
  element('result-download-frame').onload();assert.match(element('notice-text').textContent,/下载结果发生变化/);
  assert.equal(ui.state.downloading,false);assert.ok(!element('open-output-button').disabled);
  element('result-download-frame').contentDocument={body:{textContent:''}};
  ui.state.job.download_ready=false;ui.renderDone();
  assert.ok(element('open-output-button').disabled);
  ui.state.job={id:'summary',status:'ready',rows:[],output_root:'private-host-path'};
  ui.renderSummary();
  assert.match(element('summary-output').textContent,/下载.*电脑/);
  assert.ok(!element('summary-output').textContent.includes('private-host-path'));

  // A committed upload whose response is lost is recovered without a second POST.
  const reply=(body,status=200)=>({ok:status<400,status,json:async()=>body});
  const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
  element('workbook-upload').files=[workbook];element('source-upload').files=[zip];element('start-number').value='12';
  fetchHandler=async(url)=>{assert.match(url,/upload-status/);return reply({state:'completed',job_id:'recovered-job'});};
  const firstCount=xhrs.length,lost=ui.startJob({preventDefault(){}}),lostRequest=xhrs.at(-1);
  assert.ok(lostRequest.headers['X-HSD-Upload-ID']);assert.ok(storage.has('hsd-pending-upload'));
  lostRequest.listeners.error();await lost;
  assert.equal(xhrs.length,firstCount+1);assert.equal(ui.state.job.id,'recovered-job');assert.equal(storage.get('hsd-active-job'),'recovered-job');
  assert.equal(storage.has('hsd-pending-upload'),false);

  // A missing status is not proof that the original request can never arrive.
  // Lock its inputs and retry with exactly the same request ID.
  ui.state.job=null;fetchHandler=async()=>reply({state:'missing'});
  const missing=ui.startJob({preventDefault(){}}),missingRequest=xhrs.at(-1),originalId=missingRequest.headers['X-HSD-Upload-ID'];
  missingRequest.listeners.error();await missing;
  assert.equal(ui.state.uploadUncertain,true);assert.equal(ui.state.uploadRetryAllowed,true);
  assert.ok(element('workbook-upload').disabled);assert.equal(element('start-button').textContent,'重试本次上传');
  const retry=ui.startJob({preventDefault(){}}),retryRequest=xhrs.at(-1);
  assert.equal(retryRequest.headers['X-HSD-Upload-ID'],originalId);
  retryRequest.load(200,{id:'same-upload-job',reused:true});await retry;assert.equal(ui.state.job.id,'same-upload-job');

  // Browser abort is only a transfer interruption; confirmation comes from the server.
  ui.state.job=null;let cancellationRecorded=false;
  fetchHandler=async(url,options)=>{if(options.method==='POST'){assert.match(url,/upload-status\/.*\/cancel$/);cancellationRecorded=true;return reply({state:'cancelled'});}return reply({state:cancellationRecorded?'cancelled':'pending'});};
  const uploading=ui.startJob({preventDefault(){}}),toAbort=xhrs.at(-1);
  const stopping=ui.stopUpload();await uploading;await stopping;await flush();
  assert.equal(toAbort.aborted,true);assert.equal(ui.state.uploadRequest,null);assert.equal(ui.state.uploadUncertain,false);
  assert.match(element('notice-text').textContent,/服务器已确认/);

  // A stop remains busy until the server reports that all work has ended.
  ui.state.job={id:'stop-job',status:'matching',revision:1,rows:[],files:[]};
  let finishStop;fetchHandler=()=>new Promise((resolve)=>{finishStop=resolve;});
  const stop=ui.stopJob();await flush();const sent=calls.length;await ui.stopJob();assert.equal(calls.length,sent,'duplicate stop requests are blocked');
  assert.equal(JSON.parse(calls.at(-1).options.body).expected_revision,1,'employee cancellation must satisfy server revision checks');
  finishStop(reply({id:'stop-job',status:'cancelling',revision:2,cancel_requested:true,rows:[],files:[]}));await stop;
  assert.equal(ui.state.job.status,'cancelling');assert.ok(ui.isBusy());assert.equal(element('stop-job-button').disabled,true);
  assert.match(element('processing-message').textContent,/等待返回或超时/);
  fetchHandler=async()=>reply({id:'stop-job',status:'matching',revision:1,rows:[],files:[]});await ui.pollJob();
  assert.equal(ui.state.job.status,'cancelling','an old poll response cannot undo an accepted stop request');
  fetchHandler=async()=>reply({id:'stop-job',status:'cancelled',revision:3,rows:[],files:[]});await ui.pollJob();
  assert.equal(ui.isBusy(),false);assert.match(element('cancelled-message').textContent,/服务器已结束/);
  await ui.resetTask();assert.equal(ui.state.job,null);

  // A newly accepted upload placeholder must read its real revision first.
  ui.state.job={id:'fresh-upload',status:'queued',rows:[],files:[]};
  const placeholderCalls=[];
  fetchHandler=async(url,options)=>{placeholderCalls.push({url,options});return options.method==='POST'?reply({id:'fresh-upload',status:'cancelled',revision:5,rows:[],files:[]}):reply({id:'fresh-upload',status:'matching',revision:4,rows:[],files:[]});};
  await ui.stopJob();assert.equal(placeholderCalls.length,2);assert.equal(placeholderCalls[0].options.method,'GET');
  assert.equal(JSON.parse(placeholderCalls[1].options.body).expected_revision,4);assert.equal(ui.state.job.status,'cancelled');

  // A failed old download preflight must not overwrite the next batch's notice.
  ui.state.job={id:'old-download',status:'done',download_ready:true,rows:[]};
  let failPreflight;fetchHandler=()=>new Promise((_resolve,reject)=>{failPreflight=reject;});
  const oldDownload=ui.openOutput();await flush();await ui.resetTask();
  element('notice-text').textContent='下一批的提示';failPreflight(new TypeError('模拟旧下载断网'));await oldDownload;
  assert.equal(ui.state.job,null);assert.equal(element('notice-text').textContent,'下一批的提示');assert.equal(ui.state.downloading,false);

  // Expired download authentication keeps the task ID for re-login recovery.
  ui.state.job={id:'auth-job',status:'done',download_ready:true,rows:[]};storage.set('hsd-active-job','auth-job');
  fetchHandler=async()=>reply({error:'请先输入员工访问码。'},401);await ui.openOutput();
  assert.equal(ui.state.authExpired,true);assert.equal(storage.get('hsd-active-job'),'auth-job');
  assert.equal(location.assigned,undefined);assert.equal(element('notice-action').textContent,'重新登录');
  ui.state.authExpired=false;ui.state.job=null;

  ui.configureAccess({lan:false,remote:false});ui.setFormBusy(false);
  assert.ok(!element('local-workbook-field').classList.contains('hidden'));
  assert.ok(!element('workbook-path').disabled);
  assert.ok(element('workbook-upload').disabled);
  assert.ok(element('upload-fields').classList.contains('hidden'));
  console.log('Employee upload/download UI assertions passed');
}
main().catch((error)=>{console.error(error);process.exitCode=1;});
