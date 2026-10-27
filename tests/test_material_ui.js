// Execute the actual employee controller with synthetic DOM/HTTP. No provider
// calls, quality claims, browser rendering, or performance claims are made here.
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const source=fs.readFileSync(path.join(__dirname,"../hsd_tool/static/material.js"),"utf8");
const flush=()=>new Promise(setImmediate);
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};}
function harness(){
  const nodes=new Map(),requests=[],xhrs=[],timers=new Map(),storage=new Map(),revoked=[];let serial=0,blobSerial=0;
  function node(id){if(!nodes.has(id)){const classes=new Set(),listeners={};let html="";const n={id,value:"",textContent:"",disabled:false,open:false,style:{},dataset:{},files:[],children:[],writes:0,type:"",complete:true,naturalWidth:1000,
    classList:{contains:v=>classes.has(v),add(...v){v.forEach(x=>classes.add(x));},remove(...v){v.forEach(x=>classes.delete(x));},toggle(v,force){const next=force===undefined?!classes.has(v):force;if(next)classes.add(v);else classes.delete(v);return next;}},
    querySelectorAll(){return[];},querySelector(selector){
      if(selector==="[data-material-content]"&&html.includes("<div data-material-content>"))return node(id+"-content");
      if(selector===".material-item-preview img"&&html.includes("material-item-preview"))return node(id+"-image");
      if(selector===".material-item-preview"&&html.includes("material-item-preview"))return node(id+"-preview");
      if(selector==="details"&&html.includes("<details>"))return node(id+"-details");
      return null;
    },append(child){this.insertBefore(child,null);},insertBefore(child,reference){if(reference!==null&&!this.children.includes(reference))throw new Error("insertBefore anchor is not a child");if(child===reference)return child;if(child.parentNode){const previous=child.parentNode.children;previous.splice(previous.indexOf(child),1);}const index=reference===null?this.children.length:this.children.indexOf(reference);this.children.splice(index,0,child);child.parentNode=this;return child;},replaceChildren(){this.children.forEach(child=>{child.parentNode=null;});this.children=[];this.innerHTML="";},remove(){if(this.parentNode){const siblings=this.parentNode.children;siblings.splice(siblings.indexOf(this),1);this.parentNode=null;}this.removed=true;},setAttribute(k,v){this[k]=v;},getAttribute(k){return this[k]??null;},removeAttribute(k){delete this[k];},focus(){n.focused=true;},scrollIntoView(options){n.scrolled=options;},addEventListener(k,fn){listeners[k]=fn;},emit(k,event={}){listeners[k]?.({preventDefault(){},target:n,...event});},getBoundingClientRect(){return{left:10,top:20,width:500,height:250};},showModal(){n.open=true;},close(){n.open=false;},setPointerCapture(){}};Object.defineProperty(n,"innerHTML",{get:()=>{const content=nodes.get(id+"-content");return content?html.replace(/(<div data-material-content>)[\s\S]*<\/div>$/,(_,start)=>start+content.innerHTML+"</div>"):html;},set:value=>{html=String(value);n.writes++;const match=html.match(/<div data-material-content>([\s\S]*)<\/div>$/);if(match)node(id+"-content").innerHTML=match[1];const src=html.match(/class="material-item-preview"[\s\S]*?<img src="([^"]*)"/);if(src)node(id+"-image").src=src[1];}});nodes.set(id,n);}return nodes.get(id);}
  const nav=["numbering","material"].map(v=>{const n=node(`nav-${v}`);n.dataset.workspace=v;return n;});
  const sandbox={document:{getElementById:node,querySelectorAll:q=>q==="[data-workspace]"?nav:[],createElement:tag=>node(`${tag}-${++serial}`),documentElement:{dataset:{}},body:node("body"),hidden:false},window:{HSD_TOKEN:"synthetic-token",crypto:{randomUUID:()=>"12345678-1234-4123-8123-123456789abc"},scrollY:30,scrollTo(){},addEventListener(){},setTimeout:fn=>{timers.set(++serial,fn);return serial;},clearTimeout:id=>timers.delete(id)},history:{replaceState(){}},location:{hash:""},URL:{createObjectURL:()=>`blob:synthetic-${++blobSerial}`,revokeObjectURL:v=>revoked.push(v)},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},setTimeout:fn=>{timers.set(++serial,fn);return serial;},clearTimeout:id=>timers.delete(id),fetch:(url,options)=>{const d=deferred();requests.push({url,options,...d});return d.promise;},FormData:class{constructor(){this.parts=[];}append(...args){this.parts.push(args);}},XMLHttpRequest:class{constructor(){this.listeners={};this.upload={addEventListener:(k,fn)=>this.progress=fn};this.headers={};xhrs.push(this);}open(method,url){this.method=method;this.url=url;}setRequestHeader(k,v){this.headers[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}send(data){this.data=data;}abort(){this.listeners.abort?.();}reply(status,data){this.status=status;this.responseText=JSON.stringify(data);this.listeners.load();}}};
  // Browser Image exists in production. Keep callbacks manually controlled so
  // tests exercise pending, failed and out-of-order full-image downloads.
  const images=[];
  class ControlledImage {
    constructor(){this.naturalWidth=0;this.naturalHeight=0;images.push(this);}
    succeed(width=2048,height=1024){this.naturalWidth=width;this.naturalHeight=height;this.onload?.();}
    fail(){this.naturalWidth=0;this.naturalHeight=0;this.onerror?.();}
  }
  sandbox.Image=sandbox.window.Image=ControlledImage;
  vm.runInNewContext(source.replace("  boot();","  window.testMaterial={state,workspace,fileError,selectFiles,formatBytes,safeUrl,setJob,loadJob,render,renderCards,renderSources,mutate,start,recoverUpload,stop,reset,openDetail,imagePoint,selectionMove,redo,metrics,controls,itemAction,acknowledgeRefine,showBatchRecords,itemContent,itemWarnings,download,schedule,closeStream,updateClock};"),sandbox);
  return{ui:sandbox.window.testMaterial,node,requests,xhrs,timers,storage,revoked,sandbox,images,async reply(index,data,status=200){requests[index].resolve({ok:status>=200&&status<300,status,json:async()=>data});await flush();}};
}
function job(overrides={}){return{id:"a".repeat(32),revision:3,status:"ready",progress:{phase:"完成",current:1,total:1},sources:[{id:"s1",name:"原图.png",width:1000,height:500,image_url:`/api/material/jobs/${"a".repeat(32)}/source/s1`}],items:[{id:"i1",source_id:"s1",name:"完整设计",status:"generated",downloadable:true,refined:false,warnings:["请核对文字与颜色"],image_url:`/api/material/jobs/${"a".repeat(32)}/item/i1`,download_url:`/api/material/jobs/${"a".repeat(32)}/download/i1`,width:4096,height:2048}],stats:{total:1,ready:0,downloadable:1,needs_review:0,skipped:0,failed:0},download_url:null,...overrides};}
function actionEvent(action,id="i1") {return {target:{closest:()=>({dataset:{materialAction:action,itemId:id}})}};}
const tests=[];const test=(name,run)=>tests.push({name,run});
test("same-page navigation preserves numbering DOM and material state",()=>{const h=harness();h.ui.state.config={available:true};h.node("workbook-path").value="unchanged numbering draft";h.ui.state.files=[{name:"draft.png"}];h.ui.workspace("material",true);assert.ok(h.node("numbering-workspace").classList.contains("hidden"));assert.equal(h.node("workbook-path").value,"unchanged numbering draft");h.ui.workspace("numbering",true);assert.equal(h.ui.state.files[0].name,"draft.png");assert.equal(h.requests.length,0);});
test("safe image URLs cannot point to another job or remote origin",()=>{const h=harness();h.ui.state.job=job();assert.equal(h.ui.safeUrl("https://example.org/image.png"),"");assert.equal(h.ui.safeUrl("/api/material/jobs/other/item/i1"),"");assert.equal(h.ui.safeUrl("/api/material/jobs/"+"a".repeat(32)+"/item/i1"),h.ui.state.job.items[0].image_url);assert.equal(h.ui.safeUrl("/api/material/jobs/"+"a".repeat(32)+"/\\evil"),"");});
test("batch selection rejects invalid inputs atomically and has no byte cap",()=>{const h=harness();h.ui.state.config={available:true};const big={name:"large.PNG",size:5*1024**3,lastModified:1};h.ui.selectFiles([big]);assert.equal(h.ui.state.files.length,1);h.ui.selectFiles([{name:"bad.gif",size:9}],true);assert.equal(h.ui.state.files.length,1);assert.match(h.node("material-file-error").textContent,/PNG/);h.ui.selectFiles([big,{name:"next.webp",size:1,lastModified:2}],true);assert.equal(h.ui.state.files.length,2);assert.ok(h.revoked.length>0);});
test("repeated snapshots and filter changes do not recreate unchanged result cards",()=>{const h=harness();h.ui.setJob(job());const before={...h.ui.metrics};h.ui.setJob(job());h.ui.state.filter="all";h.ui.render();assert.equal(h.ui.metrics.cards_created,before.cards_created);assert.equal(h.ui.metrics.cards_updated,before.cards_updated);assert.equal(h.ui.state.items.size,1);});
test("newly generated results stay visible without a confirmation queue",()=>{const h=harness();h.ui.setJob(job({status:"processing",items:[]}));assert.equal(h.ui.state.filter,"available");h.ui.setJob(job());assert.equal(h.ui.state.filter,"available");assert.equal(h.ui.state.items.get("i1").node.classList.contains("hidden"),false);assert.ok(!h.node("material-summary").textContent.includes("待确认"));assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes('data-material-action="confirm"'));});
test("a filter explicitly selected by the employee survives processing completion",()=>{const h=harness();h.ui.setJob(job({status:"processing",items:[]}));h.ui.state.filter="all";h.ui.state.filterTouched=true;h.ui.setJob(job());assert.equal(h.ui.state.filter,"all");});
test("discard waits for server acceptance and prevents duplicate submissions",async()=>{const h=harness();h.ui.setJob(job());const pending=h.ui.itemAction(actionEvent("skip"));assert.equal(h.ui.state.job.items[0].status,"generated");assert.equal(h.ui.state.busy,true);const body=JSON.parse(h.requests[0].options.body);assert.deepEqual(body,{expected_revision:3,item_id:"i1",action:"skip"});assert.equal(h.requests[0].options.headers["X-HSD-Token"],"synthetic-token");await h.ui.itemAction(actionEvent("skip"));assert.equal(h.requests.length,1);await h.reply(0,job({revision:4,items:[{...job().items[0],status:"skipped",downloadable:false}]}));await pending;assert.equal(h.ui.state.job.items[0].status,"skipped");assert.equal(h.ui.state.busy,false);assert.equal(h.ui.state.items.get("i1").node.classList.contains("hidden"),true);});
test("a rejected discard refreshes the revision and keeps the original item",async()=>{const h=harness();h.ui.setJob(job());const pending=h.ui.itemAction(actionEvent("skip"));await h.reply(0,{error:"conflict"},409);assert.equal(h.requests.length,2);assert.equal(h.ui.state.job.items[0].status,"generated");await h.reply(1,job({revision:8}));await pending;assert.equal(h.ui.state.job.revision,8);assert.equal(h.ui.state.job.items[0].status,"generated");assert.match(h.node("material-notice").textContent,/状态已更新/);});
test("auth rejection locks employee controls and cannot expose administration",async()=>{const h=harness();h.ui.setJob(job());const pending=h.ui.mutate("resolve",{item_id:"i1",action:"confirm"});await h.reply(0,{error:"登录失效"},401);assert.equal(await pending,false);assert.equal(h.ui.state.authLost,true);assert.equal(h.node("material-start").disabled,true);assert.equal(h.requests.length,1);});
test("upload is multipart, no browser timeout, one logical request and no duplicate submit",async()=>{const h=harness();h.ui.state.config={available:true};h.ui.state.files=[{name:"a.png",size:2}];const pending=h.ui.start();await h.ui.start();assert.equal(h.xhrs.length,1);const xhr=h.xhrs[0];assert.equal(xhr.url,"/api/material/jobs");assert.equal(xhr.timeout,0);assert.equal(xhr.headers["X-HSD-Upload-ID"],"12345678-1234-4123-8123-123456789abc");assert.equal(xhr.headers["X-HSD-Token"],"synthetic-token");assert.equal(xhr.data.parts[0][0],"files");xhr.reply(200,{id:"a".repeat(32)});await flush();assert.equal(h.requests.length,1);await h.reply(0,job());await pending;assert.equal(h.ui.state.job.id,"a".repeat(32));assert.equal(h.ui.state.uncertain,false);});
test("missing upload keeps the same ID for a safe retry instead of creating a second batch",async()=>{const h=harness();h.ui.state.config={available:true};h.ui.state.files=[{name:"a.png",size:2}];h.ui.state.uploadId="old-request";h.ui.state.uncertain=true;const check=h.ui.recoverUpload();await h.reply(0,{state:"missing"});await check;assert.equal(h.ui.state.uploadId,"old-request");assert.equal(h.ui.state.retryUpload,true);const retry=h.ui.start();assert.equal(h.xhrs[0].headers["X-HSD-Upload-ID"],"old-request");h.xhrs[0].reply(400,{error:"synthetic failure"});await retry;assert.equal(h.ui.state.uncertain,false);});
test("a cancelled upload only becomes stopped after server confirmation",async()=>{const h=harness();h.ui.state.uploadId="request";h.ui.state.uncertain=true;const pending=h.ui.stop();assert.equal(h.ui.state.stopRequested,true);assert.equal(h.ui.state.uncertain,true);await h.reply(0,{state:"pending",cancellation_requested:true});assert.equal(h.requests.length,2);await h.reply(1,{state:"cancelled"});await pending;assert.equal(h.ui.state.uncertain,false);assert.match(h.node("material-notice").textContent,/已停止/);});
test("terminal jobs stop polling and skipped items leave the default queue",()=>{const h=harness();h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));assert.equal(h.timers.size,2);h.ui.setJob(job({items:[{...job().items[0],status:"skipped"}]}));assert.equal(h.timers.size,0);h.ui.state.filter="available";h.ui.render();const node=h.ui.state.items.get("i1").node;assert.ok(node.classList.contains("hidden"));assert.match(h.node("material-summary").textContent,/1 个已舍弃/);});
test("stop can cancel a running job and waits for backend convergence",async()=>{const h=harness();h.ui.setJob(job({status:"processing"}));const stop=h.ui.stop();assert.equal(h.requests.length,1);assert.ok(h.requests[0].url.endsWith("/cancel"));assert.equal(h.ui.state.job.status,"processing");await h.reply(0,job({status:"cancelling",revision:4}));await stop;assert.equal(h.ui.state.job.status,"cancelling");assert.equal(h.node("material-stop").disabled,true);assert.match(h.node("material-progress-title").textContent,/正在停止/);});
test("stop retries once with a refreshed revision when background progress races",async()=>{const h=harness();h.ui.setJob(job({status:"processing"}));const stop=h.ui.stop();await h.reply(0,{error:"progress changed"},409);await h.reply(1,job({status:"processing",revision:4}));assert.equal(h.requests.length,3);assert.equal(JSON.parse(h.requests[2].options.body).expected_revision,4);await h.reply(2,job({status:"cancelling",revision:5}));await stop;assert.equal(h.ui.state.job.status,"cancelling");});
test("source-pixel crop coordinates preserve image geometry",()=>{const h=harness();h.ui.setJob(job());h.ui.openDetail("s1",null,true);const point=h.ui.imagePoint({clientX:260,clientY:145});assert.equal(point.x,500);assert.equal(point.y,250);h.ui.state.startPoint=h.ui.imagePoint({clientX:60,clientY:45});h.ui.selectionMove({clientX:260,clientY:145});assert.equal(h.ui.state.box.x,100);assert.equal(h.ui.state.box.y,50);assert.equal(h.ui.state.box.width,400);assert.equal(h.ui.state.box.height,200);});
test("unknown submissions require an explicit acknowledgement before a new paid request",async()=>{const h=harness();const base=job();h.ui.setJob(job({sources:[{...base.sources[0],submission_unknown:true}]}));h.ui.openDetail("s1",null,true);h.ui.state.box={x:0,y:0,width:200,height:200};h.ui.controls();assert.equal(h.node("material-redo-submit").disabled,true);await h.ui.redo();assert.equal(h.requests.length,0);assert.match(h.node("material-dialog-message").textContent,/重复计费/);h.node("material-unknown-ack").checked=true;h.ui.controls();assert.equal(h.node("material-redo-submit").disabled,false);const pending=h.ui.redo();const payload=JSON.parse(h.requests[0].options.body);assert.equal(payload.acknowledge_unknown,true);await h.reply(0,job({status:"queued",revision:4}));await pending;});
test("displayed filenames and warnings are escaped instead of becoming markup",()=>{const h=harness();h.ui.setJob(job({items:[{...job().items[0],name:'<script>x</script>',warnings:['<img onerror=x>']}]}));const html=h.ui.state.items.get("i1").node.innerHTML;assert.ok(html.includes("&lt;script&gt;"));assert.ok(!html.includes("<script>"));assert.ok(html.includes("&lt;img onerror=x&gt;"));});
test("a delayed refresh cannot restore an old batch after choosing the next batch",async()=>{const h=harness();h.ui.setJob(job());const refresh=h.ui.loadJob();h.ui.reset();await h.reply(0,job());await refresh;assert.equal(h.ui.state.job,null);assert.ok(!h.node("material-upload-form").classList.contains("hidden"));});
test("a mutation response from a previous page lifecycle cannot overwrite the restored state",async()=>{const h=harness();h.ui.setJob(job());const pending=h.ui.mutate("resolve",{item_id:"i1",action:"confirm"});h.ui.state.epoch++;h.ui.state.busy=false;h.ui.setJob(job({revision:9}));await h.reply(0,job({revision:4,items:[{...job().items[0],status:"confirmed"}]}));assert.equal(await pending,false);assert.equal(h.ui.state.job.revision,9);assert.equal(h.ui.state.job.items[0].status,"generated");});
test("a delayed upload response leaves recovery ID intact after leaving the page",async()=>{const h=harness();h.ui.state.config={available:true};h.ui.state.files=[{name:"a.png",size:2}];const pending=h.ui.start();const id=h.ui.state.uploadId;h.ui.state.epoch++;h.xhrs[0].reply(200,{id:"a".repeat(32)});await pending;assert.equal(h.requests.length,0);assert.equal(h.ui.state.uploadId,id);assert.equal(h.storage.get("hsd-material-upload"),id);});
test("reset releases previews and leaves numbering state untouched",()=>{const h=harness();h.ui.state.config={available:true};h.ui.selectFiles([{name:"one.png",size:1}]);h.node("workbook-path").value="numbering draft";h.ui.setJob(job());h.ui.reset();assert.equal(h.ui.state.job,null);assert.equal(h.ui.state.files.length,0);assert.equal(h.revoked.length,1);assert.equal(h.node("workbook-path").value,"numbering draft");assert.ok(!h.node("material-upload-form").classList.contains("hidden"));});
test("generated output downloads directly without confirmation or a state mutation",async()=>{const h=harness();h.ui.setJob(job());const html=h.ui.state.items.get("i1").node.innerHTML;assert.ok(html.includes('data-material-action="download"'));assert.ok(html.includes('data-material-action="refine"'));assert.ok(html.includes('data-material-action="skip"'));assert.ok(!html.includes('data-material-action="confirm"'));assert.ok(!html.includes('data-select-item'));assert.ok(!html.includes("人工确认"));await h.ui.itemAction(actionEvent("download"));assert.equal(h.requests.length,0);assert.equal(h.ui.state.job.items[0].status,"generated");assert.match(h.node("material-download-frame").src,/download\/i1\?frame=1$/);});
test("a rejected discard preserves the image and shows the server error",async()=>{const h=harness();h.ui.setJob(job());const before=h.ui.state.job.items[0].image_url,pending=h.ui.itemAction(actionEvent("skip"));await h.reply(0,{error:"output integrity failed"},422);await pending;assert.equal(h.ui.state.job.items[0].status,"generated");assert.equal(h.ui.state.job.items[0].image_url,before);assert.match(h.node("material-notice").textContent,/integrity/);});
test("task switches clear unknown-refinement acknowledgement context",()=>{const h=harness();h.ui.setJob(job({items:[{...job().items[0],refine_submission_unknown:true}]}));h.ui.state.refineAcks.add("i1");h.ui.setJob(job({id:"different",items:[{...job().items[0],refine_submission_unknown:true}]}));assert.equal(h.ui.state.refineAcks.size,0);});
test("stream snapshots are task scoped, stop at terminal and reject older sequences",()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(url){this.url=url;this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing",update_seq:4}));assert.equal(streams.length,1);assert.ok(streams[0].url.endsWith("/events"));const receive=value=>streams[0].listeners.snapshot({data:JSON.stringify(value)});receive(job({status:"processing",update_seq:3}));assert.equal(h.ui.state.job.update_seq,4);receive(job({status:"ready",update_seq:5}));assert.equal(h.ui.state.job.status,"ready");assert.equal(streams[0].closed,true);assert.equal(h.timers.size,0);receive(job({status:"processing",revision:9}));assert.equal(h.ui.state.job.status,"ready");});
test("stream repeated failures use polling and leaving workspace closes connection",()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(url){this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.config={available:true};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));streams[0].onerror();assert.equal(h.ui.state.streamDisabled,false);streams[0].onerror();assert.equal(h.ui.state.streamDisabled,true);assert.equal(h.timers.size,1);h.ui.workspace("numbering");assert.equal(h.timers.size,0);assert.equal(streams[0].closed,true);});
test("shared warnings appear once outside cards while specific differences remain visible",()=>{const h=harness(),base=job().items[0];h.ui.setJob(job({items:[{...base,warnings:["请核对颜色","字样模糊"]},{...base,id:"i2",warnings:["请核对颜色"]}]}));assert.equal(h.node("material-shared-warning").textContent,"请核对颜色");const html=h.ui.state.items.get("i1").node.innerHTML;assert.match(html,/<p class="material-item-warning">字样模糊<\/p>/);assert.ok(!html.includes('<p class="material-item-warning">请核对颜色</p>'));});
test("a permanently closed stream falls back immediately and discovers expired authentication",async()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(){this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));streams[0].readyState=2;streams[0].onerror();assert.equal(streams[0].closed,true);assert.equal(h.ui.state.streamDisabled,true);const callback=[...h.timers.values()][0];callback();assert.equal(h.requests.length,1);await h.reply(0,{error:"登录已失效"},401);assert.equal(h.ui.state.authLost,true);assert.equal(h.ui.state.stream,null);});
test("stream unavailable events request a fresh authorized snapshot",()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(){this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));streams[0].listeners.unavailable();assert.equal(streams[0].closed,true);assert.equal(h.ui.state.streamDisabled,true);assert.equal(h.timers.size,1);});
test("a repeated warning affecting only some designs stays attached to those designs",()=>{const h=harness(),base=job().items[0];h.ui.setJob(job({items:[{...base,warnings:["存在范围重叠"]},{...base,id:"i2",warnings:["存在范围重叠"]},{...base,id:"i3",warnings:[]}]}));assert.equal(h.node("material-shared-warning").textContent,"");assert.ok(h.ui.state.items.get("i1").node.innerHTML.includes('<p class="material-item-warning">存在范围重叠</p>'));assert.ok(!h.ui.state.items.get("i3").node.innerHTML.includes('存在范围重叠'));});
test("crop rounding never extends past the original image edge",()=>{const h=harness();h.ui.setJob(job({sources:[{...job().sources[0],width:32,height:32}]}));h.ui.openDetail("s1",null,true);h.ui.state.startPoint={x:.5,y:.5};h.ui.selectionMove({clientX:510,clientY:270});assert.equal(h.ui.state.box.x+h.ui.state.box.width,32);assert.equal(h.ui.state.box.y+h.ui.state.box.height,32);assert.ok(h.ui.state.box.width>0);});
test("saving phase highlights the generate and save step",()=>{const h=harness();h.ui.setJob(job({status:"processing",progress:{stage_code:"saving",phase:"保存结果",current:0,total:1}}));assert.ok(h.node("material-stage-list").innerHTML.includes('<li class="current" aria-current="step">3. 生成并保存</li>'));});
test("batch elapsed time uses one server run and monotonic time across stages and source images",()=>{const h=harness();let monotonic=2000;h.sandbox.window.performance={now:()=>monotonic};h.sandbox.Date={now:()=>9999999999999};h.ui.state.workspace="material";const progress={run_id:"run1",run_started_at:10,stage_code:"cleanup",started_at:10,source_id:"s1",elapsed_seconds:12,task_elapsed_seconds:12,current:0,total:2};h.ui.setJob(job({status:"processing",progress}));assert.match(h.node("material-progress-detail").textContent,/本批累计用时 12 秒/);monotonic=5500;h.ui.updateClock();assert.match(h.node("material-progress-detail").textContent,/本批累计用时 15 秒/);const anchor=h.ui.state.clockAnchor;h.ui.setJob(job({status:"processing",progress:{...progress,stage_code:"locating",started_at:30,elapsed_seconds:1,task_elapsed_seconds:15},update_seq:5}));assert.equal(h.ui.state.clockAnchor,anchor,'stage changes do not reset the batch clock');h.ui.setJob(job({status:"processing",progress:{...progress,source_id:"s2",current:1,started_at:40,elapsed_seconds:0,task_elapsed_seconds:15},update_seq:6}));assert.equal(h.ui.state.clockAnchor,anchor,'the next source retains the same batch clock');assert.match(h.node("material-progress-detail").textContent,/本批累计用时 15 秒/);assert.ok(!h.node("material-progress-detail").textContent.includes("本阶段"));});
test("a fresh run resets the clock and terminal duration is frozen by the server",()=>{const h=harness();let monotonic=1000;h.sandbox.window.performance={now:()=>monotonic};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing",progress:{run_id:"first",task_elapsed_seconds:130}}));assert.match(h.node("material-progress-detail").textContent,/2 分 10 秒/);h.ui.setJob(job({status:"processing",update_seq:4,progress:{run_id:"second",task_elapsed_seconds:2}}));assert.match(h.node("material-progress-detail").textContent,/本批累计用时 2 秒/);monotonic=9000;h.ui.setJob(job({status:"ready",update_seq:5,progress:{run_id:"second",task_elapsed_seconds:7}}));assert.match(h.node("material-summary").textContent,/本批累计用时 7 秒/);assert.equal(h.timers.size,0);monotonic=999000;h.ui.render();assert.match(h.node("material-summary").textContent,/本批累计用时 7 秒/);});
test("a lagging server duration cannot move an active batch clock backwards",()=>{const h=harness();let monotonic=1000;h.sandbox.window.performance={now:()=>monotonic};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing",progress:{run_id:"same",task_elapsed_seconds:40}}));monotonic=5000;h.ui.setJob(job({status:"processing",update_seq:4,progress:{run_id:"same",task_elapsed_seconds:41}}));assert.match(h.node("material-progress-detail").textContent,/本批累计用时 44 秒/);h.ui.setJob(job({status:"processing",update_seq:5,progress:{run_id:"same",task_elapsed_seconds:49}}));assert.match(h.node("material-progress-detail").textContent,/本批累计用时 49 秒/);});
test("real generation counts show a scoped percent instead of an indeterminate strip",()=>{const h=harness();h.ui.state.workspace="material";const progress={run_id:"run",stage_code:"designs",source_id:"s1",current:0,total:1,designs_completed:39,designs_total:41,task_elapsed_seconds:182,indeterminate:true};h.ui.setJob(job({status:"processing",progress}));assert.equal(h.node("material-progress-percent").textContent,"95%");assert.equal(h.node("material-progress-fill").style.width,"95%");assert.equal(h.node("material-progress-track")["aria-valuenow"],"95");assert.equal(h.node("material-progress-fill").classList.contains("indeterminate"),false);assert.equal(h.node("material-progress-label").textContent,"本张素材生成进度");assert.match(h.node("material-progress-message").textContent,/已处理 39 \/ 41 个素材/);assert.ok(h.node("material-stage-list").innerHTML.includes('<li class="current" aria-current="step">3. 生成并保存</li>'));h.ui.setJob(job({status:"processing",update_seq:4,progress:{...progress,designs_completed:41}}));assert.equal(h.node("material-progress-percent").textContent,"100%");h.ui.setJob(job({status:"processing",update_seq:5,progress:{run_id:"run",stage_code:"saving",source_id:"s1",current:0,total:1,task_elapsed_seconds:190}}));assert.equal(h.node("material-progress-percent").textContent,"100%");assert.match(h.node("material-progress-message").textContent,/正在保存/);});
test("unknown denominators show actual stages without inventing a batch percent",()=>{const h=harness();h.ui.setJob(job({status:"processing",progress:{run_id:"run",stage_code:"locating",source_id:"s1",current:0,total:2,task_elapsed_seconds:8}}));assert.equal(h.node("material-progress-meter").classList.contains("hidden"),true);assert.equal(h.node("material-progress-percent").textContent,"");assert.equal(h.node("material-progress-track")["aria-valuenow"],undefined);assert.match(h.node("material-progress-detail").textContent,/已处理 0 \/ 2 张原图/);assert.ok(h.node("material-stage-list").innerHTML.includes('<li class="current" aria-current="step">2. 识别设计</li>'));});
test("per-source progress stays scoped when the next source has a different design count",()=>{const h=harness(),sources=[job().sources[0],{...job().sources[0],id:"s2"}];const p={run_id:"run",source_id:"s1",stage_code:"designs",current:0,total:2,designs_completed:8,designs_total:8,task_elapsed_seconds:50};h.ui.setJob(job({sources,status:"processing",progress:p}));assert.match(h.node("material-progress-label").textContent,/第 1 \/ 2 张原图/);h.ui.setJob(job({sources,status:"processing",update_seq:4,progress:{...p,stage_code:"source_done",current:1}}));assert.match(h.node("material-progress-label").textContent,/第 1 \/ 2 张原图/);h.ui.setJob(job({sources,status:"processing",update_seq:5,progress:{...p,source_id:"s2",stage_code:"locating",current:1,designs_total:null,designs_completed:null}}));assert.equal(h.node("material-progress-meter").classList.contains("hidden"),true);h.ui.setJob(job({sources,status:"processing",update_seq:6,progress:{...p,source_id:"s2",current:1,designs_completed:0,designs_total:12}}));assert.equal(h.node("material-progress-percent").textContent,"0%");assert.match(h.node("material-progress-label").textContent,/第 2 \/ 2 张原图/);});

test("normal stream renewal reconnects quietly and is cancelled when the workspace is hidden",()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(){this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.config={available:true};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));h.node("material-stream-state").textContent="进度实时更新中";streams[0].listeners.renew();assert.equal(streams[0].closed,true);assert.equal(h.ui.state.streamDisabled,false);assert.equal(h.node("material-stream-state").textContent,"进度实时更新中");const renewal=h.ui.state.renewTimer;h.ui.schedule();assert.equal(streams.length,1,'snapshot refresh must not bypass renewal delay');h.timers.get(renewal)();assert.equal(streams.length,2);streams[1].listeners.renew();h.ui.workspace("numbering");assert.equal(h.ui.state.renewTimer,null);assert.equal(h.ui.state.stream,null);});
test("a late renewal timer cannot reconnect the previous task",()=>{const h=harness(),streams=[];h.sandbox.window.EventSource=class{constructor(){this.listeners={};streams.push(this);}addEventListener(name,fn){this.listeners[name]=fn;}close(){this.closed=true;}};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing"}));streams[0].listeners.renew();const previous=h.timers.get(h.ui.state.renewTimer);h.ui.setJob(job({id:"b".repeat(32),status:"processing"}));const count=streams.length;previous();assert.equal(streams.length,count);assert.equal(h.ui.state.streamJob,"b".repeat(32));});
test("the cumulative clock ticks while a newly opened event stream waits for its first snapshot",()=>{const h=harness();h.sandbox.window.EventSource=class{addEventListener(){}close(){}};let monotonic=1000;h.sandbox.window.performance={now:()=>monotonic};h.ui.state.workspace="material";h.ui.setJob(job({status:"processing",progress:{run_id:"same",task_elapsed_seconds:10}}));assert.ok(h.timers.has(h.ui.state.clockTimer));monotonic=4000;h.timers.get(h.ui.state.clockTimer)();assert.match(h.node("material-progress-detail").textContent,/本批累计用时 13 秒/);h.sandbox.document.hidden=true;h.ui.schedule();assert.equal(h.timers.size,0);});
test("result cards use task-scoped thumbnails and only the compare dialog loads originals",()=>{const h=harness(),base=job(),item={...base.items[0],thumbnail_url:base.items[0].image_url+"?variant=thumb&v=abc"},source={...base.sources[0],thumbnail_url:base.sources[0].image_url+"?variant=thumb&v=def"};h.ui.setJob(job({items:[item],sources:[source]}));const card=h.ui.state.items.get(item.id);assert.ok(card.node.innerHTML.includes(item.thumbnail_url.replaceAll("&","&amp;")));assert.ok(!card.node.innerHTML.includes(`src="${item.image_url}"`));assert.ok(card.node.innerHTML.includes('loading="lazy"'));assert.ok(card.node.innerHTML.includes('width="640" height="640"'));h.ui.openDetail(source.id,item,false);assert.equal(h.node("material-detail-source").src,source.thumbnail_url);assert.equal(h.node("material-detail-output").src,item.thumbnail_url);assert.equal(h.images.length,2);assert.ok(h.node("material-detail-output").classList.contains("image-loading"));h.images.forEach(image=>image.succeed());assert.equal(h.node("material-detail-source").src,source.image_url);assert.equal(h.node("material-detail-output").src,item.image_url);assert.equal(h.node("material-detail-output").classList.contains("image-loading"),false);});
test("a refinement label update preserves the preview DOM and expanded details",()=>{const h=harness(),item=job().items[0];h.ui.setJob(job());const record=h.ui.state.items.get(item.id),image=record.node.querySelector(".material-item-preview img"),writes=record.node.writes,loaded=h.ui.metrics.previews_loaded;record.contentNode.querySelector("details").open=true;h.ui.setJob(job({revision:4,items:[{...item,refined:true}]}));assert.equal(record.node.writes,writes);assert.equal(record.node.querySelector(".material-item-preview img"),image);assert.equal(h.ui.metrics.previews_loaded,loaded);assert.equal(record.contentNode.querySelector("details").open,true);assert.match(record.contentNode.innerHTML,/已精修/);});
test("nonvisual result metadata never rebuilds card content or reloads its thumbnail",()=>{const h=harness(),item=job().items[0];h.ui.setJob(job());const record=h.ui.state.items.get(item.id),before={...h.ui.metrics},writes=record.contentNode.writes;h.ui.setJob(job({revision:4,items:[{...item,review:{at:123,method:"employee"},quality:{evidence:"updated"}}]}));assert.equal(h.ui.metrics.cards_updated,before.cards_updated);assert.equal(h.ui.metrics.previews_loaded,before.previews_loaded);assert.equal(record.contentNode.writes,writes);});
test("new thumbnail content preserves the preview node and expanded details",()=>{const h=harness(),base=job(),item={...base.items[0],thumbnail_url:base.items[0].image_url+"?variant=thumb&v=one"};h.ui.setJob(job({items:[item]}));const record=h.ui.state.items.get(item.id),image=record.node.querySelector(".material-item-preview img"),before={...h.ui.metrics},writes=record.node.writes;record.contentNode.querySelector("details").open=true;const next={...item,thumbnail_url:item.image_url+"?variant=thumb&v=two"};h.ui.setJob(job({revision:4,items:[next]}));assert.equal(record.node.writes,writes);assert.equal(record.node.querySelector(".material-item-preview img"),image);assert.equal(image.src,next.thumbnail_url);assert.equal(h.ui.metrics.previews_loaded,before.previews_loaded+1);assert.equal(record.contentNode.querySelector("details").open,true);});
test("unsafe or foreign-task thumbnail URLs cannot replace a valid original",()=>{const h=harness(),item=job().items[0];for(const url of ["https://example.org/private.png","/api/material/jobs/other/item/i1?variant=thumb"]){h.ui.setJob(job({items:[{...item,thumbnail_url:url}]}));assert.ok(h.ui.state.items.get(item.id).node.innerHTML.includes(`src="${item.image_url}"`));assert.ok(!h.ui.state.items.get(item.id).node.innerHTML.includes(url));}});
test("original-image drawer builds thumbnails only when opened and ignores metadata-only snapshots",()=>{const h=harness(),base=job(),source={...base.sources[0],thumbnail_url:base.sources[0].image_url+"?variant=thumb&v=one"};h.ui.setJob(job({sources:[source]}));assert.equal(h.node("material-source-grid").innerHTML,"");h.node("material-source-details").open=true;h.ui.renderSources();const writes=h.node("material-source-grid").writes;assert.ok(h.node("material-source-grid").innerHTML.includes("variant=thumb"));h.ui.setJob(job({revision:4,sources:[{...source,status:"done",attempts:[{state:"returned"}]}]}));assert.equal(h.node("material-source-grid").writes,writes);});
test("source failures remain visible and open the original-image drawer",()=>{const h=harness(),source={...job().sources[0],error:"图片服务未完成，请重试"};h.ui.setJob(job({sources:[source]}));assert.equal(h.node("material-source-details").open,true);assert.match(h.node("material-source-grid").innerHTML,/图片服务未完成/);});
test("changing or resetting a batch clears old source thumbnails and the open drawer",()=>{const h=harness();h.ui.setJob(job());h.node("material-source-details").open=true;h.ui.renderSources();h.ui.setJob(job({id:"b".repeat(32),sources:[]}));assert.equal(h.node("material-source-grid").innerHTML,"");assert.equal(h.node("material-source-details").open,false);h.node("material-source-grid").innerHTML="old";h.ui.reset();assert.equal(h.node("material-source-grid").innerHTML,"");});
function thumbnailJob(id="a".repeat(32)) {
  const base=job({id});
  const sources=base.sources.map(value=>({...value,image_url:`/api/material/jobs/${id}/source/${value.id}`}));
  const items=[base.items[0],{...base.items[0],id:"i2",name:"第二张设计"}].map(value=>({...value,image_url:`/api/material/jobs/${id}/item/${value.id}`}));
  return {...base,sources:sources.map(value=>({...value,thumbnail_url:value.image_url+"?variant=thumb&v=source"})),items:items.map(value=>({...value,thumbnail_url:value.image_url+"?variant=thumb&v="+value.id}))};
}
test("late full-image callbacks cannot replace the newly selected item",()=>{
  const h=harness(),batch=thumbnailJob();h.ui.setJob(batch);
  h.ui.openDetail("s1",batch.items[0]);h.ui.openDetail("s1",batch.items[1]);
  assert.equal(h.node("material-detail-output").src,batch.items[1].thumbnail_url);
  h.images[0].succeed();h.images[1].succeed();
  assert.equal(h.node("material-detail-output").src,batch.items[1].thumbnail_url);
  assert.ok(h.node("material-detail-output").classList.contains("image-loading"));
  h.images[2].succeed();h.images[3].succeed();h.images[1].succeed();
  assert.equal(h.node("material-detail-output").src,batch.items[1].image_url);
  assert.equal(h.node("material-detail-title").textContent,batch.items[1].name);
  assert.equal(h.ui.state.dialog.itemId,"i2");
  assert.equal(h.requests.length,0);
});
test("a failed full image keeps the current thumbnail without a second request",()=>{
  const h=harness(),batch=thumbnailJob();h.ui.setJob(batch);h.ui.openDetail("s1",batch.items[0]);
  h.images[1].fail();h.images[0].succeed();
  assert.equal(h.node("material-detail-output").src,batch.items[0].thumbnail_url);
  assert.equal(h.node("material-detail-output").classList.contains("image-loading"),false);
  assert.equal(h.node("material-detail-source").src,batch.sources[0].image_url);
  assert.equal(h.images.length,2);
});
test("identical preview and full URLs do not start redundant preloads",()=>{
  const h=harness(),batch=job();h.ui.setJob(batch);h.ui.openDetail("s1",batch.items[0]);
  assert.equal(h.images.length,0);
  assert.equal(h.node("material-detail-source").src,batch.sources[0].image_url);
  assert.equal(h.node("material-detail-output").classList.contains("image-loading"),false);
});
test("a new task selection is not overwritten by the previous task image callback",()=>{
  const h=harness(),first=thumbnailJob(),second=thumbnailJob("b".repeat(32));
  h.ui.setJob(first);h.ui.openDetail("s1",first.items[0]);
  h.ui.setJob(second);h.ui.openDetail("s1",second.items[0]);
  h.images[2].succeed();h.images[3].succeed();h.images[0].succeed();h.images[1].fail();
  assert.equal(h.node("material-detail-source").src,second.sources[0].image_url);
  assert.equal(h.node("material-detail-output").src,second.items[0].image_url);
  assert.equal(h.node("material-detail-output").classList.contains("image-loading"),false);
});
test("selection coordinates use the source size while a thumbnail is displayed",()=>{
  const h=harness(),batch=thumbnailJob();h.ui.setJob(batch);h.ui.openDetail("s1",batch.items[0],true);
  const image=h.node("material-detail-source");image.naturalWidth=640;image.naturalHeight=320;
  const center=h.ui.imagePoint({clientX:260,clientY:145});
  assert.equal(center.x,500);assert.equal(center.y,250);assert.equal(center.width,1000);assert.equal(center.height,500);
  h.ui.state.startPoint=h.ui.imagePoint({clientX:60,clientY:45});h.ui.selectionMove({clientX:360,clientY:195});
  assert.equal(JSON.stringify(h.ui.state.box),JSON.stringify({x:100,y:50,width:600,height:300}));
  h.images[0].succeed(1000,500);image.naturalWidth=1000;image.naturalHeight=500;
  assert.equal(h.ui.imagePoint({clientX:260,clientY:145}).x,500);
});
test("refine submits the current item once without a confirmation or custom instructions",async()=>{
  const h=harness(),base=job(),old=base.items[0];h.ui.state.config={available:false};h.ui.setJob(base);
  const pending=h.ui.itemAction(actionEvent("refine"));await h.ui.itemAction(actionEvent("refine"));
  assert.equal(h.requests.length,1);assert.ok(h.requests[0].url.endsWith("/refine"));
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{expected_revision:3,item_id:"i1"});
  assert.equal(h.ui.state.job.items[0].image_url,old.image_url);assert.equal(h.ui.state.job.items[0].refined,false);
  await h.reply(0,job({status:"queued",revision:4,items:[{...old,downloadable:false,download_url:null}],progress:{stage_code:"refining",phase:"精修素材",current:0,total:1}}));await pending;
  assert.equal(h.ui.state.job.items.length,1);assert.equal(h.ui.state.job.items[0].refined,false);
  assert.equal(h.node("material-progress-meter").classList.contains("hidden"),true);
  assert.match(h.node("material-stage-list").innerHTML,/精修当前素材/);
  assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes("已精修"));
});
test("successful refinement replaces the current preview and opens a before-and-after comparison",()=>{
  const h=harness(),base=thumbnailJob(),old=base.items[0];h.ui.setJob(base);
  const record=h.ui.state.items.get(old.id),preview=record.node.querySelector(".material-item-preview img"),created=h.ui.metrics.cards_created;
  const result={...old,refined:true,image_url:old.image_url+"?v=new",thumbnail_url:old.image_url+"?variant=thumb&v=new",previous_image:{image_url:old.image_url+"/before?v=old",thumbnail_url:old.image_url+"/before?variant=thumb&v=old",width:old.width,height:old.height}};
  h.ui.setJob({...base,revision:4,items:[result,base.items[1]]});
  assert.equal(h.ui.state.job.items.length,2);assert.equal(h.ui.metrics.cards_created,created);
  assert.equal(record.node.querySelector(".material-item-preview img"),preview);assert.equal(preview.src,result.thumbnail_url);
  assert.match(record.contentNode.innerHTML,/已精修/);assert.ok(!record.contentNode.innerHTML.includes("人工确认"));
  h.ui.openDetail("s1",result);
  assert.equal(h.node("material-detail-source-caption").textContent,"精修前");assert.equal(h.node("material-detail-output-caption").textContent,"精修后");
  assert.equal(h.node("material-detail-source").src,result.previous_image.thumbnail_url);assert.equal(h.node("material-detail-output").src,result.thumbnail_url);
  h.images.forEach(image=>image.succeed());
  assert.equal(h.node("material-detail-source").src,result.previous_image.image_url);assert.equal(h.node("material-detail-output").src,result.image_url);
  assert.equal(h.node("material-detail-guidance").textContent,"如需再次优化，可选择精修，或自行使用 GPT 图像模型处理。");
});
test("a rejected refinement preserves the current result and does not claim success",async()=>{
  const h=harness(),base=job(),old=base.items[0];h.ui.setJob(base);const pending=h.ui.itemAction(actionEvent("refine"));
  await h.reply(0,{error:"图片服务暂不可用，请稍后重试。"},422);await pending;
  assert.equal(h.ui.state.job.items[0].image_url,old.image_url);assert.equal(h.ui.state.job.items[0].refined,false);
  assert.match(h.node("material-notice").textContent,/暂不可用/);assert.equal(h.ui.state.busy,false);
  assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes("已精修"));
});
test("a background refinement failure keeps the old download and its own visible error",async()=>{
  const h=harness(),base=job(),old=base.items[0],message="精修未完成，已保留原结果。";
  h.ui.setJob(job({revision:4,items:[{...old,refine_error:message}]}));
  assert.match(h.ui.state.items.get("i1").node.innerHTML,/精修未完成/);
  assert.equal(h.ui.state.job.items[0].image_url,old.image_url);
  h.ui.openDetail("s1",h.ui.state.job.items[0]);assert.match(h.node("material-detail-warning").textContent,/精修未完成/);
  await h.ui.itemAction(actionEvent("download"));assert.equal(h.requests.length,0);assert.match(h.node("material-download-frame").src,/download\/i1\?frame=1$/);
});
test("an unknown prior refinement requires an explicit acknowledgement before another submission",async()=>{
  const h=harness(),old=job().items[0];h.ui.setJob(job({items:[{...old,refine_submission_unknown:true}]}));
  assert.match(h.ui.state.items.get("i1").node.innerHTML,/重新提交可能重复计费/);
  await h.ui.itemAction(actionEvent("refine"));assert.equal(h.requests.length,0);assert.match(h.node("material-notice").textContent,/先确认/);
  h.ui.acknowledgeRefine({target:{closest:()=>({dataset:{refineAck:"i1"},checked:true})}});
  const pending=h.ui.itemAction(actionEvent("refine"));assert.deepEqual(JSON.parse(h.requests[0].options.body),{expected_revision:3,item_id:"i1",acknowledge_unknown:true});
  assert.equal(h.ui.state.refineAcks.size,0);
  await h.reply(0,job({revision:4,status:"queued",items:[{...old,downloadable:false,download_url:null}]}));await pending;
  assert.equal(h.requests.length,1);
});
test("restoring a discarded item does not mark it reviewed",async()=>{
  const h=harness(),old=job().items[0];h.ui.setJob(job({items:[{...old,status:"skipped",downloadable:false,download_url:null}]}));h.ui.state.filter="skipped";h.ui.render();
  assert.match(h.ui.state.items.get("i1").node.innerHTML,/恢复素材/);const pending=h.ui.itemAction(actionEvent("restore"));
  assert.deepEqual(JSON.parse(h.requests[0].options.body),{expected_revision:3,item_id:"i1",action:"restore"});
  await h.reply(0,job({revision:4}));await pending;
  assert.equal(h.ui.state.job.items[0].status,"generated");assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes("人工确认"));
});
test("download permission comes from the server and is not inferred from a legacy confirmed status",async()=>{
  const h=harness(),old=job().items[0];h.ui.setJob(job({items:[{...old,status:"confirmed",downloadable:false,download_url:null}]}));
  await h.ui.itemAction(actionEvent("download"));assert.equal(h.node("material-download-frame").src,undefined);
  assert.equal(h.requests.length,0);assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes("人工确认"));
  h.ui.setJob(job({revision:4,items:[{...old,status:"needs_review",downloadable:true}]}));await h.ui.itemAction(actionEvent("download"));
  assert.match(h.node("material-download-frame").src,/download\/i1\?frame=1$/);assert.equal(h.ui.state.job.items[0].status,"needs_review");
});
test("another design's failure stays in batch records instead of this item's details",()=>{
  const h=harness(),base=job();h.ui.setJob(job({sources:[{...base.sources[0],warnings:["另一个设计生成失败。"]}],items:[{...base.items[0],warnings:["请核对文字、配色和设计是否完整；修补细节可能与原图不同。","本图文字仍有残留。"]}]}));
  const html=h.ui.state.items.get("i1").node.innerHTML;
  assert.ok(!html.includes("另一个设计生成失败"));assert.ok(!html.slice(0,html.indexOf("<details>")).includes("请核对文字、配色和设计是否完整"));
  assert.equal(html.split("本图文字仍有残留。").length-1,1);assert.equal(html.split("如需再次优化").length-1,1);
  assert.match(h.node("material-batch-info").innerHTML,/另一个设计生成失败/);
  h.ui.openDetail("s1",h.ui.state.job.items[0]);assert.equal(h.node("material-detail-warning").textContent,"本图文字仍有残留。");
});
test("foreign-task before images cannot replace the authorized comparison source",()=>{
  const h=harness(),base=job(),item={...base.items[0],refined:true,previous_image:{image_url:"/api/material/jobs/other/item/i1/before",thumbnail_url:"https://example.org/private.png"}};
  h.ui.setJob(job({items:[item]}));h.ui.openDetail("s1",item);
  assert.equal(h.node("material-detail-source").src,base.sources[0].image_url);assert.equal(h.node("material-detail-source-caption").textContent,"上传原图");
});
test("generation failure records have one visible batch link without polluting item details",()=>{
  const h=harness(),base=job();h.ui.setJob({...base,has_generation_failures:true});
  assert.equal(h.node("material-generation-warning").classList.contains("hidden"),false);
  assert.equal(h.node("material-batch-details").open,false);h.ui.showBatchRecords();
  assert.equal(h.node("material-batch-details").open,true);assert.equal(h.node("material-batch-details").scrolled.block,"nearest");
  assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes("未生成记录"));
  h.ui.openDetail("s1",base.items[0]);assert.ok(!h.node("material-detail-warning").textContent.includes("未生成记录"));
  h.ui.setJob({...base,revision:4,has_generation_failures:false,warnings:["普通模型提醒。"],sources:[{...base.sources[0],warnings:["普通图片提醒。"]}]});
  assert.equal(h.node("material-generation-warning").classList.contains("hidden"),true);
  h.ui.setJob({...base,revision:5});assert.equal(h.node("material-generation-warning").classList.contains("hidden"),true);
});
test("material HTML and rendered cards expose three direct actions without confirmation controls",()=>{
  const html=fs.readFileSync(path.join(__dirname,"../hsd_tool/static/index.html"),"utf8"),start=html.indexOf('<section id="material-workspace"'),workspace=html.slice(start,html.indexOf('</main>',start));
  assert.ok(start>=0);assert.ok(workspace.includes('id="material-download-all"'));assert.ok(workspace.includes('>下载全部素材</button>'));
  for(const obsolete of ['id="material-confirm-selected"','id="material-select-all"','id="material-undo-batch"','确认后下载','data-material-filter="needs_review"'])assert.ok(!workspace.includes(obsolete),obsolete);
  assert.match(workspace,/<button[^>]+id="material-generation-warning"[^>]+type="button">本批有未生成记录，查看本批记录<\/button>/);
  assert.ok(html.includes('id="material-detail-guidance"'));
  const h=harness();h.ui.setJob(job());const rendered=h.ui.itemContent(job().items[0]);
  const actions=[...rendered.matchAll(/<button\b[^>]*data-material-action="([^"]+)"[^>]*>([^<]+)<\/button>/g)].map(match=>[match[1],match[2]]);
  assert.deepEqual(actions,[["download","下载"],["refine","精修"],["skip","舍弃"]]);
  assert.ok(!rendered.includes('data-material-action="confirm"'));assert.ok(!rendered.includes('data-select-item'));
  assert.equal(rendered.split("如需再次优化，可选择精修，或自行使用 GPT 图像模型处理。").length-1,1);
});
test("a refined first item with a new ID keeps its position and preserves the second image node",()=>{
  const h=harness(),base=thumbnailJob();h.ui.setJob(base);
  const second=h.ui.state.items.get("i2"),secondImage=second.node.querySelector(".material-item-preview img"),oldFirst=h.ui.state.items.get("i1").node;
  const refined={...base.items[0],id:"refined-first",refined:true,image_url:base.items[0].image_url+"?v=refined",thumbnail_url:base.items[0].image_url+"?variant=thumb&v=refined"};
  h.ui.setJob({...base,revision:4,items:[refined,base.items[1]]});
  assert.deepEqual(h.node("material-grid").children.map(node=>node.dataset.itemId),["refined-first","i2"]);
  assert.equal(oldFirst.removed,true);assert.equal(h.ui.state.items.get("i2").node,second.node);
  assert.equal(second.node.querySelector(".material-item-preview img"),secondImage);
  h.ui.setJob({...base,revision:5,items:[refined,base.items[1]]});
  assert.deepEqual(h.node("material-grid").children.map(node=>node.dataset.itemId),["refined-first","i2"]);
});
test("known provider processing notes are collapsed while current image problems remain visible",()=>{
  const h=harness(),base=job(),notes=[
    "已保留模型返回的完整画布，系统没有裁剪或删除边缘内容。",
    "模型提取可能改变文字、配色或细节，请对照原图确认。",
    "精修内容由模型生成，文字、配色和完整性仍需对照确认。",
    "本设计只占原图约 2%，已放大局部参考图重画；清晰度仍受原图分辨率限制。"
  ],problems=[
    "图片服务未返回透明区域，已保留完整画布；请确认背景和设计内部底板。",
    "模型返回内容触及画布边缘，可能不完整；系统未再裁剪，请核对。",
    "设计在画布中占比偏小，请放大核对或重新框选完整设计。",
    "未知提示：模型提取可能改变本图局部，发现颜色差异。"
  ],item={...base.items[0],refine_error:"本次精修未完成，原结果保留。",warnings:[...notes,...problems]};
  h.ui.setJob(job({items:[item]}));h.ui.openDetail("s1",item);
  const visible=h.node("material-detail-warning").textContent,collapsed=h.node("material-detail-processing-notes-list").innerHTML;
  for(const warning of problems)assert.ok(visible.includes(warning),warning);
  assert.ok(visible.includes(item.refine_error));
  for(const note of notes){assert.ok(!visible.includes(note),note);assert.ok(collapsed.includes(note),note);}
  assert.equal(h.node("material-detail-processing-notes").open,false);
  assert.equal(h.node("material-detail-processing-notes").classList.contains("hidden"),false);
  assert.equal(h.node("material-detail-guidance").classList.contains("hidden"),false);
  assert.equal(h.node("material-detail-guidance").textContent,"如需再次优化，可选择精修，或自行使用 GPT 图像模型处理。");
  const card=h.ui.state.items.get("i1").node.innerHTML,summary=card.slice(0,card.indexOf("<details>"));
  for(const note of notes){assert.ok(!summary.includes(note));assert.ok(card.includes(note));}
  assert.ok(summary.includes(item.refine_error));
});
test("routine notes alone never become default warnings or replace the fixed short guidance",()=>{
  const h=harness(),base=job(),notes=["清理可能改变文字、配色或细节，请对照原图确认。","已按标记位置提出修改要求，模型仍可能改变其他区域，请对照确认。"],items=[base.items[0],{...base.items[0],id:"i2"}].map(item=>({...item,warnings:notes}));
  h.ui.setJob(job({items}));h.ui.openDetail("s1",items[0]);
  assert.equal(h.node("material-detail-warning").textContent,"");assert.equal(h.node("material-shared-warning").classList.contains("hidden"),true);
  assert.equal(h.node("material-detail-processing-notes").open,false);
  assert.ok(!h.ui.state.items.get("i1").node.innerHTML.includes('class="material-item-warning"'));
  h.ui.openDetail("s1",{...items[0],refine_error:notes[0]});
  assert.equal(h.node("material-detail-warning").textContent,notes[0],"a server error stays visible even if its text equals a known processing note");
});
async function main(){let failed=0;for(const t of tests){try{await t.run();console.log(`PASS ${t.name}`);}catch(e){failed++;console.error(`FAIL ${t.name}\n${e.stack}`);}}console.log(`${tests.length-failed} passed, ${failed} failed (synthetic material employee UI)`);if(failed)process.exitCode=1;}main();
