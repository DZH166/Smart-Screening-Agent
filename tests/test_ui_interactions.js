// Interaction invariants with a small DOM model. These are not browser timing measurements.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const staticDir=path.join(__dirname,'../hsd_tool/static');
const decode=(s)=>String(s).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
const camel=(s)=>s.replace(/-([a-z])/g,(_,c)=>c.toUpperCase());

class Element {
  constructor(tag='div',attributes={}){
    this.tagName=tag.toUpperCase();this.attributes={};this.dataset={};this.children=[];this.parentElement=null;
    this.style={setProperty:(key,value)=>{this.style[key]=value;},removeProperty:(key)=>delete this.style[key]};
    this.listeners={};this.scrollTop=0;this.value='';this.disabled=false;this.open=false;this.complete=true;
    this.naturalWidth=1280;this.naturalHeight=260;this._text='';this._html='';this.innerHTMLWrites=0;
    this.classList={contains:(v)=>this.classes.has(v),add:(...v)=>v.forEach(x=>this.classes.add(x)),remove:(...v)=>v.forEach(x=>this.classes.delete(x)),toggle:(v,force)=>{const next=force===undefined?!this.classes.has(v):!!force;if(next)this.classes.add(v);else this.classes.delete(v);return next;}};
    this.classes=new Set();Object.entries(attributes).forEach(([key,value])=>this.setAttribute(key,value));
  }
  get id(){return this.attributes.id||'';}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==='class')this.classes=new Set(String(value).split(/\s+/).filter(Boolean));if(key.startsWith('data-'))this.dataset[camel(key.slice(5))]=String(value);if(key==='open')this.open=true;if(key==='value')this.value=String(value);}
  getAttribute(key){return key==='class'?[...this.classes].join(' '):this.attributes[key]??null;}
  removeAttribute(key){delete this.attributes[key];if(key==='open')this.open=false;}
  get firstElementChild(){return this.children[0]||null;}
  get nextElementSibling(){if(!this.parentElement)return null;const list=this.parentElement.children;return list[list.indexOf(this)+1]||null;}
  get previousElementSibling(){if(!this.parentElement)return null;const list=this.parentElement.children;return list[list.indexOf(this)-1]||null;}
  get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  set textContent(value){this._text=String(value??'');this.replaceChildren();}
  get innerHTML(){return this._html;}
  set innerHTML(value){this.innerHTMLWrites++;this._html=String(value);this.replaceChildren();parseInto(this._html,this);}
  replaceChildren(...nodes){for(const node of this.children)node.parentElement=null;this.children=[];for(const node of nodes)this.appendChild(node);}
  appendChild(node){return this.insertBefore(node,null);}
  append(...nodes){for(const node of nodes)this.appendChild(node);}
  insertBefore(node,before){if(node===before)return node;if(node.parentElement)node.remove();const index=before?this.children.indexOf(before):-1;if(index<0)this.children.push(node);else this.children.splice(index,0,node);node.parentElement=this;return node;}
  replaceWith(other){const parent=this.parentElement;if(!parent)return;const index=parent.children.indexOf(this);if(other.parentElement)other.remove();parent.children.splice(index,1,other);this.parentElement=null;other.parentElement=parent;}
  remove(){if(!this.parentElement)return;const parent=this.parentElement;parent.children.splice(parent.children.indexOf(this),1);this.parentElement=null;}
  querySelectorAll(selector){return query(this,selector);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  matches(selector){return matches(this,selector);}
  closest(selector){let node=this;while(node){if(matches(node,selector))return node;node=node.parentElement;}return null;}
  contains(node){while(node){if(node===this)return true;node=node.parentElement;}return false;}
  addEventListener(name,callback){(this.listeners[name]??=[]).push(callback);}
  removeEventListener(name,callback){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x!==callback);}
  dispatch(name,event={}){event.currentTarget=this;event.target??=this;event.preventDefault??=()=>{};for(const callback of this.listeners[name]||[])callback(event);}
  focus(){this.ownerDocument.activeElement=this;}
  getBoundingClientRect(){return {top:150,bottom:650,height:500,width:800,left:0,right:800};}
  scrollIntoView(){}
  showModal(){this.open=true;}
  close(){this.open=false;this.dispatch('close');}
}
function parseInto(html,parent){
  const stack=[parent],voids=new Set(['INPUT','IMG','BR','META','LINK','HR','SOURCE','WBR','AREA','BASE']);
  for(const token of html.matchAll(/<[^>]+>|[^<]+/g)){
    const text=token[0];if(text.startsWith('<!--')||/^<!/.test(text))continue;
    if(text.startsWith('</')){if(stack.length>1)stack.pop();continue;}
    if(text.startsWith('<')){
      const match=text.match(/^<([\w-]+)/);if(!match)continue;
      const attrs={};for(const item of text.slice(match[0].length).matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[item[1]]=decode(item[2]??item[3]??item[4]??'');
      const node=new Element(match[1],attrs);node.ownerDocument=parent.ownerDocument;stack.at(-1).appendChild(node);
      if(!voids.has(node.tagName)&&!text.endsWith('/>'))stack.push(node);
    }else stack.at(-1)._text+=decode(text);
  }
}
function matches(node,selector){
  if(selector.includes(','))return selector.split(',').some(part=>matches(node,part.trim()));
  const parts=selector.trim().split(/\s+(?![^\[]*\])/);const own=parts.pop();
  if(!own)return false;
  const tag=own.match(/^[\w-]+/);if(tag&&node.tagName!==tag[0].toUpperCase())return false;
  for(const item of own.matchAll(/#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=["']?([^\]"']*)["']?)?\]/g)){
    if(item[1]&&node.id!==item[1])return false;if(item[2]&&!node.classes.has(item[2]))return false;
    if(item[3]){const value=item[3].startsWith('data-')?node.dataset[camel(item[3].slice(5))]:node.getAttribute(item[3]);if(value===undefined||value===null)return false;if(item[4]!==undefined&&String(value)!==item[4])return false;}
  }
  if(parts.length){let p=node.parentElement;while(p&&!matches(p,parts.join(' ')))p=p.parentElement;if(!p)return false;}
  return true;
}
function query(root,selector){const result=[];for(const child of root.children){if(matches(child,selector))result.push(child);result.push(...query(child,selector));}return result;}

function harness(){
  const document={documentElement:new Element('html'),listeners:{},activeElement:null,
    getElementById(id){return this.documentElement.querySelector('#'+id);},querySelectorAll(s){return this.documentElement.querySelectorAll(s);},querySelector(s){return this.querySelectorAll(s)[0]||null;},
    createElement(tag){const element=new Element(tag);element.ownerDocument=this;if(tag==='template'){element.content=element;}return element;},
    addEventListener(name,callback){(this.listeners[name]??=[]).push(callback);},dispatchEvent(){},
  };
  document.documentElement.ownerDocument=document;
  parseInto(fs.readFileSync(path.join(staticDir,'index.html'),'utf8').replace(/<script[^>]*>[\s\S]*?<\/script>/g,''),document.documentElement);
  document.body=document.querySelector('body');
  const timers=new Map();let timerId=0,clock=0;const requests=[];const preload=[];let fetchHandler;
  const setTimeout=(callback,delay=0)=>{const id=++timerId;timers.set(id,{callback,at:clock+delay});return id;};
  const clearTimeout=(id)=>timers.delete(id);
  const advance=(ms)=>{clock+=ms;for(const[id,timer]of[...timers])if(timer.at<=clock){timers.delete(id);timer.callback();}};
  const location={origin:'http://synthetic.invalid',assign(){}};
  const window={HSD_ACCESS:{lan:true,remote:true},HSD_TOKEN:'synthetic-token',setTimeout,clearTimeout,addEventListener(){},scrollTo(){},location,innerHeight:768,scrollY:0};
  const sandbox={window,document,location,setTimeout,clearTimeout,performance:{now:()=>clock},requestAnimationFrame:()=>1,cancelAnimationFrame(){},AbortController,
    CSS:{escape:(s)=>s},Image:class{set src(value){preload.push(value);}},HTMLImageElement:Element,
    sessionStorage:{setItem(){},getItem(){return null;},removeItem(){}},
    fetch:async(url,options={})=>{requests.push({url,options});return fetchHandler(url,options);},console,
  };
  const source=fs.readFileSync(path.join(staticDir,'app.js'),'utf8');
  const exposure='  window.testUI={state,init,renderJob,renderTable,renderPanel,renderCandidateView,selectRow,counts,filteredRows,resolveRow,undoLast,pollJob,schedulePoll,acceptJob,renderSummary,configureAccess,preloadImage,preloadNeighbours,cacheSnapshot:()=>({preloaded:[...preloaded],aspects:imageAspects.size,rowViews:rowViewState.size})};';
  assert.match(source,/  init\(\)\.catch\([^\n]+\);/,'test seam must replace only bootstrap');
  vm.runInNewContext(source.replace(/  init\(\)\.catch\([^\n]+\);/,exposure),sandbox);
  return {ui:window.testUI,document,window,requests,timers,preload,advance,setFetch(handler){fetchHandler=handler;},loadAI(){vm.runInNewContext(fs.readFileSync(path.join(staticDir,'ai-settings.js'),'utf8'),sandbox);},node:id=>document.getElementById(id)};
}
const response=(data,status=200)=>({ok:status<400,status,json:async()=>data});
const job=(count=4)=>({id:'synthetic-job',status:'ready',revision:1,can_undo:false,rows:Array.from({length:count},(_,i)=>({id:'r'+i,row_number:i+2,status:'review',number:'',file_id:null,reason:'两个文件图案接近',candidates:[{file_id:'f'+i,score:.9},{file_id:'g'+i,score:.8}]})),files:Array.from({length:count},(_,i)=>[{id:'f'+i,name:'原稿'+i+'.ai'},{id:'g'+i,name:'候选'+i+'.ai'}]).flat()});
const clone=(value)=>JSON.parse(JSON.stringify(value));
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};

async function main(){
  // A changed row must not recreate unaffected rows or their loaded images.
  const h=harness(),ui=h.ui;ui.state.job=job();ui.selectRow('r0',null,false);ui.renderTable();
  const original=h.node('rows-body').children[1];h.document.querySelector('.table-scroll').scrollTop=83;
  const updated=clone(ui.state.job);updated.revision++;updated.rows[0].status='confirmed';updated.rows[0].file_id='f0';
  ui.acceptJob(updated);ui.renderTable();
  assert.equal(h.node('rows-body').children.length,3);
  assert.ok(h.node('rows-body').children[0]===original,'unchanged record DOM and image must survive confirmation');
  assert.equal(h.document.querySelector('.table-scroll').scrollTop,83);
  ui.state.filter='all';ui.renderTable();const same=h.node('rows-body').children[1];ui.renderTable();assert.ok(h.node('rows-body').children[1]===same);
  const nextBatch=job();nextBatch.id='another-synthetic-job';ui.acceptJob(nextBatch);ui.renderTable();
  assert.ok(h.node('rows-body').children[1]!==same,'new batch must not reuse a previous task image node');
  assert.ok(h.node('rows-body').children[1].querySelector('img').getAttribute('src').startsWith('/api/jobs/another-synthetic-job/'));

  // Automatic and skipped rows are never pending; server classification drives the summary.
  const all=job(3);all.rows[0].status='auto';all.rows[0].file_id='f0';all.rows[0].planned_number='HSD0001';all.rows[1].status='skipped';all.rows[2].status='unmatched';
  ui.acceptJob(all);ui.state.filter='awaiting';assert.deepEqual([...ui.filteredRows()].map(x=>x.id),['r2']);
  assert.equal(ui.counts().localAuto,1);assert.equal(ui.counts().confirmed,0);assert.equal(ui.counts().skipped,1);assert.equal(ui.counts().awaiting,1);
  const automatic=clone(all);automatic.rows=automatic.rows.slice(0,1);ui.acceptJob(automatic);ui.state.showSummary=false;ui.state.forceReview=false;ui.renderJob();
  assert.ok(!h.node('summary-view').classList.contains('hidden'),'reliable batch goes straight to summary');
  assert.equal(h.node('summary-stats').children.length,3,'summary focuses on export, numbers and unresolved counts');
  assert.ok(h.node('summary-processing-details').contains(h.node('summary-breakdown')));
  assert.ok(h.node('summary-processing-details').contains(h.node('summary-ai-overview')));
  assert.ok(!h.node('summary-processing-details').open,'technical breakdown stays available on demand');
  assert.ok(h.node('done-details').contains(h.node('done-ai-overview')));
  // AI retrieval chooses candidates; only the server's verified final status
  // contributes an accepted row. Its usage and failures remain in details.
  const aiFirst=clone(automatic);aiFirst.matching_mode='ai_first';aiFirst.ai_retrieval={message:'AI 查找已完成，本机核验已完成。'};
  ui.acceptJob(aiFirst);ui.renderJob();
  assert.ok(!h.node('summary-view').classList.contains('hidden'));
  assert.match(h.node('summary-breakdown').textContent,/AI 查找对应图片 \+ 本机核验/);
  assert.match(h.node('summary-ai-overview').textContent,/AI 查找已完成/);
  assert.equal(ui.counts().localAuto,1);assert.equal(ui.counts().aiAuto,0,'retrieval is not conditional AI acceptance');
  const unresolved=clone(aiFirst);unresolved.rows[0].status='review';unresolved.rows[0].file_id=null;
  unresolved.ai_retrieval.message='AI 返回多个接近候选，需人工确认。';
  ui.acceptJob(unresolved);ui.state.showSummary=false;ui.state.forceReview=false;ui.renderJob();
  assert.ok(!h.node('review-view').classList.contains('hidden'));assert.equal(ui.counts().matched,0);
  assert.match(h.node('job-ai-overview').textContent,/需人工确认/);
  const fallback=clone(aiFirst);fallback.ai_retrieval.message='AI 请求失败，已由本机匹配继续处理。';
  ui.acceptJob(fallback);ui.renderJob();assert.match(h.node('summary-ai-overview').textContent,/请求失败.*本机匹配/);
  // Removing one task's details and restoring the same text on a later task
  // must not leave a stale dataset cache with an empty overview.
  ui.acceptJob(automatic);ui.renderJob();assert.ok(h.node('summary-ai-overview').classList.contains('hidden'));
  ui.acceptJob(fallback);ui.renderJob();assert.match(h.node('summary-ai-overview').textContent,/请求失败/);
  ui.configureAccess({lan:true,remote:true});assert.ok(h.node('host-management').classList.contains('hidden'));
  assert.ok(h.node('ai-settings-button').classList.contains('hidden'));assert.ok(h.node('shutdown-button').classList.contains('hidden'));
  ui.configureAccess({lan:false,remote:false});assert.ok(!h.node('host-management').classList.contains('hidden'));

  // Classification is mutually exclusive, existing numbers and unresolved rows don't take new numbers.
  const classified=job(8);
  ['auto','auto','auto','confirmed','confirmed','review','unmatched','skipped'].forEach((status,index)=>{
    const row=classified.rows[index];row.status=status;row.file_id='f'+index;
    if(index<5)row.planned_number='HSD'+String(index+1).padStart(4,'0');
    if(index===0||index===4)row.number='HSD'+String(index+1).padStart(4,'0');
  });
  classified.rows[1].ai_review={outcome:'auto_passed'};classified.rows[5].ai_review={outcome:'auto_passed'};
  ui.acceptJob(classified);let c=ui.counts();
  assert.equal(c.total,8);assert.equal(c.matched,5);assert.equal(c.localAuto,2);assert.equal(c.aiAuto,1);assert.equal(c.confirmed,2);
  assert.equal(c.awaiting,2);assert.equal(c.skipped,1);assert.equal(c.newNumbers,3);
  assert.equal(c.localAuto+c.aiAuto+c.confirmed+c.awaiting+c.skipped,c.total);
  ui.renderSummary();assert.deepEqual(h.node('summary-stats').children.map(x=>x.querySelector('strong').textContent),['5','3','3']);
  classified.rows[5].status='skipped';ui.acceptJob(classified);c=ui.counts();assert.equal(c.awaiting,1);assert.equal(c.skipped,2,'accepting same object still invalidates cached counts');

  // Preload is deduplicated per task and all visual/context caches clear on a new task.
  const cache=harness();cache.ui.acceptJob(job());cache.ui.selectRow('r0',null,false);cache.ui.renderJob();cache.ui.selectRow('r1');
  cache.ui.preloadNeighbours(cache.ui.state.job.rows[1]);const preloadCount=cache.preload.length;cache.ui.preloadNeighbours(cache.ui.state.job.rows[1]);
  assert.equal(cache.preload.length,preloadCount);assert.ok(preloadCount>0);assert.ok(cache.ui.cacheSnapshot().aspects>0);assert.ok(cache.ui.cacheSnapshot().rowViews>0);
  const otherTask=job();otherTask.id='isolated-task';cache.ui.acceptJob(otherTask);
  assert.equal(cache.ui.cacheSnapshot().preloaded.length,0);assert.equal(cache.ui.cacheSnapshot().aspects,0);assert.equal(cache.ui.cacheSnapshot().rowViews,0);
  cache.ui.preloadNeighbours(otherTask.rows[1]);assert.ok(cache.preload.slice(preloadCount).every(url=>url.startsWith('/api/jobs/isolated-task/')));

  // Retrieval and later pair review keep separate explanations and expanded
  // state when only the selected candidate changes. Neither changes status.
  const advice=harness();advice.loadAI();const dual=job(1);
  dual.matching_mode='ai_first';dual.rows[0].ai_retrieval={candidate_id:'f0',verdict:'same',outcome:'suggestion',reason:'AI 查找到接近的原稿。'};
  dual.rows[0].ai_review={candidate_id:'f0',verdict:'uncertain',outcome:'manual_review',reason:'局部颜色仍需判断。'};
  advice.ui.acceptJob(dual);advice.ui.selectRow('r0',null,false);advice.ui.renderJob();
  const adviceSlot=advice.node('ai-row-advice');
  assert.match(adviceSlot.textContent,/AI 查找建议 · 需人工确认/);
  assert.match(adviceSlot.textContent,/AI 无法确定 · 需人工确认/);
  adviceSlot.querySelectorAll('details[data-detail-key]').forEach((item)=>item.open=true);
  const tableImage=advice.node('review-panel').querySelector('.compare-grid img');
  advice.ui.state.selectedFileId='g0';advice.ui.renderCandidateView();
  assert.ok(adviceSlot.querySelectorAll('details[data-detail-key]').every((item)=>item.open));
  assert.equal(adviceSlot.querySelectorAll('details[data-detail-key]').length,2);
  assert.match(adviceSlot.textContent,/AI 建议与当前候选不同/);
  assert.match(adviceSlot.textContent,/AI 复核对象.*与当前选择不同/);
  assert.ok(advice.node('review-panel').querySelector('.compare-grid img')===tableImage);
  assert.equal(advice.ui.counts().matched,0);assert.equal(advice.ui.state.job.rows[0].status,'review');

  // One in-flight request, visible saving feedback, no optimistic success, stable failed choice.
  const a=harness();a.ui.acceptJob(job());a.ui.selectRow('r0','g0',false);a.ui.renderJob();
  assert.ok(a.node('export-button').disabled,'no exportable match must keep summary action disabled');
  assert.ok(a.node('undo-button').disabled,'no saved operation must keep undo disabled');
  a.ui.state.manualOpen=true;a.ui.state.manualQuery='候选';a.ui.state.candidatesOpen=true;
  let release;a.setFetch(()=>new Promise(resolve=>{release=resolve;}));
  const saving=a.ui.resolveRow('g0');await flush();
  assert.equal(a.ui.state.resolving,true);assert.equal(a.ui.state.job.rows[0].status,'review');
  await a.ui.resolveRow('g0');assert.equal(a.requests.length,1,'double submit must not create two requests');
  release(response({error:'模拟保存失败'},503));await saving;
  assert.equal(a.ui.state.job.rows[0].status,'review');assert.equal(a.ui.state.selectedFileId,'g0');
  assert.equal(a.ui.state.resolving,false);assert.match(a.node('notice-text').textContent,/模拟保存失败/);
  assert.ok(!a.node('confirm-row-button').disabled,'failure permits retry');
  assert.equal(a.ui.state.manualQuery,'候选');assert.equal(a.ui.state.candidatesOpen,true);

  // Successful skip moves to the next remaining row; undo restores the server-provided row.
  const skipped=job();skipped.revision=2;skipped.can_undo=true;skipped.rows[0].status='skipped';
  a.setFetch(async()=>response(skipped));await a.ui.resolveRow(null);
  assert.equal(a.ui.state.selectedRowId,'r1');assert.equal(a.ui.counts().skipped,1);
  const restored=job();restored.revision=3;restored.last_undone_row_id='r0';a.setFetch(async()=>response(restored));await a.ui.undoLast();
  assert.equal(a.ui.state.selectedRowId,'r0');assert.equal(a.ui.state.filter,'awaiting');assert.equal(a.ui.counts().skipped,0);

  // A 409 reloads server state and never presents the attempted choice as saved.
  const conflict=job();conflict.revision=8;let conflictCalls=0;
  a.setFetch(async(_url,options)=>{conflictCalls++;return options.method==='POST'?response({error:'其他页面已更新，请核对'},409):response(conflict);});
  await a.ui.resolveRow('f0');assert.equal(conflictCalls,2);assert.equal(a.ui.state.job.revision,8);assert.equal(a.ui.state.job.rows[0].status,'review');assert.match(a.node('notice-text').textContent,/其他页面已更新/);

  // Polling must stop after a terminal state, and must not schedule a new poll after stop.
  const p=harness();p.ui.acceptJob({...job(),status:'matching'});p.setFetch(async()=>response({...job(),status:'ready'}));
  await p.ui.pollJob();assert.equal(p.requests.length,1);assert.equal(p.timers.size,0);
  p.ui.state.stopped=true;p.ui.schedulePoll(100);assert.equal(p.timers.size,0);await p.ui.pollJob();assert.equal(p.requests.length,1);
  for(const status of [401,403,404]){
    const denied=harness();denied.ui.acceptJob({...job(),status:'matching'});denied.ui.schedulePoll(1000);
    denied.setFetch(async()=>response({error:'模拟会话或任务失效'},status));await denied.ui.pollJob();
    assert.equal(denied.ui.state.job,null);assert.equal(denied.timers.size,0);assert.equal(denied.requests.length,1);
    assert.ok(!denied.node('import-view').classList.contains('hidden'));assert.match(denied.node('notice-text').textContent,status===404?/任务已不存在/:/会话已失效/);
    await denied.ui.pollJob();assert.equal(denied.requests.length,1,'invalid session must not continue polling');
  }

  // Real event binding, synthetic config: rapid search should only render the final query.
  const s=harness();s.setFetch(async()=>response({version:'test',access:{lan:true,remote:true},active_job_id:null}));await s.ui.init();
  s.ui.acceptJob(job(20));s.ui.selectRow('r0',null,false);s.ui.renderJob();
  const manual=s.node('manual-search-details');manual.open=true;manual.dispatch('toggle');
  const manualInput=s.node('file-search');manualInput.value='候选';manualInput.dispatch('input');s.advance(250);manualInput.focus();
  const content=s.node('review-panel').querySelector('.panel-content');content.scrollTop=123;
  const queryImage=s.node('review-panel').querySelector('.compare-grid img');
  const candidate=s.node('manual-results').querySelector('[data-candidate-id="g0"]');assert.ok(candidate,'manual search should show candidate');
  s.node('review-panel').dispatch('click',{target:candidate});
  assert.equal(s.ui.state.selectedFileId,'g0');
  assert.ok(s.node('file-search')===manualInput,'candidate change must preserve manual-search input DOM');
  assert.ok(s.document.activeElement===manualInput,'candidate change must preserve current input focus');
  assert.ok(s.node('manual-search-details')===manual);assert.ok(manual.open);
  assert.ok(s.node('review-panel').querySelector('.compare-grid img')===queryImage,'candidate change must retain table image');
  assert.ok(s.node('review-panel').querySelector('.panel-content')===content);assert.equal(content.scrollTop,123);
  const evidence=s.node('candidate-comparison').querySelector('details');evidence.open=true;
  s.ui.selectRow('r1');s.ui.selectRow('r0');
  assert.equal(s.ui.state.selectedFileId,'g0');assert.equal(s.node('file-search').value,'候选');
  assert.ok(s.node('manual-search-details').open);assert.ok(s.node('candidate-comparison').querySelector('details').open);
  assert.equal(s.node('review-panel').querySelector('.panel-content').scrollTop,123,'returning to row restores its scroll context');
  const beforeSearch=JSON.parse(s.document.documentElement.dataset.hsdUiMetrics).table_renders;
  const input=s.node('row-search');input.focus();input.value='a';input.dispatch('input');input.value='ab';input.dispatch('input');input.value='abc';input.dispatch('input');
  assert.equal(JSON.parse(s.document.documentElement.dataset.hsdUiMetrics).table_renders,beforeSearch,'search should not rebuild on every keystroke');
  s.advance(250);assert.equal(JSON.parse(s.document.documentElement.dataset.hsdUiMetrics).table_renders,beforeSearch+1);assert.ok(s.document.activeElement===input);assert.equal(input.value,'abc');

  // Settings may change server retry availability without changing row decisions.
  // Refresh identical revisions without rebuilding images; changed revisions render fresh data.
  const settings=harness();settings.setFetch(async()=>response({version:'test',access:{lan:false,remote:false}}));await settings.ui.init();
  const initial=job();initial.ai_review={mode:'evaluation',reviewed:0,can_retry:false};settings.ui.acceptJob(initial);settings.ui.selectRow('r0','g0',false);settings.ui.renderJob();
  const onSettings=settings.document.listeners['hsd-ai-settings-updated'][0];assert.equal(typeof onSettings,'function');
  const unchangedPanel=settings.node('review-panel'),unchangedImage=unchangedPanel.querySelector('.compare-grid img');
  const detailWrites=unchangedPanel.innerHTMLWrites,tableRenders=JSON.parse(settings.document.documentElement.dataset.hsdUiMetrics).table_renders;
  const retryAvailable=clone(initial);retryAvailable.ai_review.can_retry=true;settings.setFetch(async()=>response(retryAvailable));await onSettings();
  assert.equal(settings.ui.state.job.ai_review.can_retry,true,'retry permission comes from refreshed server snapshot');
  assert.ok(settings.node('summary-ai-overview').querySelector('[data-ai-retry]'),'new server permission makes retry available');
  assert.ok(settings.node('review-panel').querySelector('.compare-grid img')===unchangedImage);
  assert.equal(settings.node('review-panel').innerHTMLWrites,detailWrites);assert.equal(settings.ui.state.selectedFileId,'g0');
  assert.equal(JSON.parse(settings.document.documentElement.dataset.hsdUiMetrics).table_renders,tableRenders);
  const newer=clone(retryAvailable);newer.revision=2;newer.rows[0].status='confirmed';newer.rows[0].file_id='f0';settings.setFetch(async()=>response(newer));await onSettings();
  assert.equal(settings.ui.state.job.revision,2);assert.equal(settings.ui.counts().confirmed,1);
  assert.ok(settings.node('review-panel').innerHTMLWrites>detailWrites,'different revision refreshes changed decisions');

  // A delayed settings reply must not overwrite a successful intervening save.
  settings.ui.selectRow('r1');let finishStale;
  settings.setFetch(()=>new Promise(resolve=>{finishStale=resolve;}));const pendingSettings=onSettings();await flush();
  const saved=clone(newer);saved.revision=3;saved.rows[1].status='confirmed';saved.rows[1].file_id='f1';saved.can_undo=true;
  settings.setFetch(async()=>response(saved));await settings.ui.resolveRow('f1');
  const selectedAfterSave=settings.ui.state.selectedRowId;
  finishStale(response(newer));await pendingSettings;
  assert.equal(settings.ui.state.job.revision,3);assert.equal(settings.ui.counts().confirmed,2);
  assert.equal(settings.ui.state.selectedRowId,selectedAfterSave);assert.equal(settings.ui.state.job.rows[1].status,'confirmed');
  const requestCount=settings.requests.length;settings.ui.state.resolving=true;await onSettings();settings.ui.state.resolving=false;
  assert.equal(settings.requests.length,requestCount,'settings event during a save must not race another snapshot fetch');
  settings.setFetch(()=>new Promise(resolve=>{finishStale=resolve;}));const previousTaskReply=onSettings();await flush();
  const another=job();another.id='another-settings-task';settings.ui.acceptJob(another);finishStale(response(saved));await previousTaskReply;
  assert.equal(settings.ui.state.job.id,'another-settings-task','late settings reply cannot replace a newer task');
  console.log('UI interaction invariants passed (synthetic DOM; no browser timing or AI validation)');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
