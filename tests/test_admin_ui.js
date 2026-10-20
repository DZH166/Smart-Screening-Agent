// Synthetic admin UI checks. No browser storage, real server or provider is used.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.js'),'utf8');
const nodes = new Map(), timers = new Map(), calls = [], listeners = {};
let nextTimer = 1, response = {status:200,body:{}}, onFetch = null;
function element(id) {
  if (!nodes.has(id)) {
    const classes = new Set(), node = {id,value:'',checked:false,disabled:false,textContent:'',innerHTML:'',children:[],dataset:{},scrollTop:0,scrollHeight:1000,
      classList:{add(...v){v.forEach((x)=>classes.add(x));},remove(...v){v.forEach((x)=>classes.delete(x));},contains(v){return classes.has(v);},toggle(v,force){if(force===undefined)force=!classes.has(v);if(force)classes.add(v);else classes.delete(v);}},
      addEventListener(name,fn){(listeners[`${id}:${name}`] ||= []).push(fn);},querySelectorAll(){return [];},
      querySelector(selector){return element(`${id}:${selector}`);},focus(){sandbox.document.activeElement=this;},
      replaceChildren(){this.innerHTML='';this.children=[];},insertAdjacentHTML(position,html){this.innerHTML+=html;this.children.push({remove:()=>this.children.shift()});},
    };
    Object.defineProperty(node,'firstElementChild',{get(){return this.children[0];}});
    nodes.set(id,node);
  }
  return nodes.get(id);
}
const sandbox = {document:{hidden:false,getElementById:element,addEventListener(name,fn){listeners[name]=fn;}},
  window:{HSD_TOKEN:'synthetic-csrf',addEventListener(name,fn){listeners[`window:${name}`]=fn;}},AbortController,
  setTimeout(fn,delay){const id=nextTimer++;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
  fetch:async(url,options)=>{calls.push({url,options});if(onFetch)onFetch(url,options);return {ok:response.status>=200&&response.status<300,status:response.status,json:async()=>response.body};},
};
vm.runInNewContext(source.replace("  boot().catch(()=>message('管理页面加载失败，请刷新后重试。',true));",'  window.testAdmin={state,usageText,keyStats,keyHtml,eventHtml,processDebug,renderKeys,applySettings,refreshOverview,addKeys,saveEnabled,mutateKeys,schedulePoll,poll,boot};'),sandbox);
const ui=sandbox.window.testAdmin;
const initial={enabled:true,configured:true,model:'synthetic-model',mode:'evaluation',key_revision:4,key_persistence:'windows_dpapi',keys:[{id:'key-a',label:'主密钥',enabled:true,source:'saved'}]};
const stopEvent={preventDefault(){}};
function json(value){return JSON.parse(JSON.stringify(value));}

async function main(){
  const unknown=ui.usageText({requests:2,failures:1,unknown_usage_requests:1,estimated_usd_upper_bound:null});
  assert.equal(unknown.cost,'费用估算暂不可用');assert.ok(unknown.unknown.includes('用量未知'));
  assert.ok(ui.usageText({estimated_usd:0.003,unknown_usage_requests:1}).cost.includes('已知用量费用估算 US$'));
  assert.ok(ui.usageText({requests:0,estimated_usd:0}).cost.includes('0.000000'));
  const malicious=ui.keyHtml({id:'id"<x>',label:'<script>label</script>',enabled:true,status:'cooldown',cooldown_seconds:2.5,unknown_usage_requests:1,source:'saved'});
  assert.ok(malicious.includes('&lt;script&gt;label&lt;/script&gt;'));assert.ok(!malicious.includes('<script>'));
  assert.ok(malicious.includes('冷却剩余约 3 秒'));assert.ok(malicious.includes('费用估算暂不可用'));
  const environment=ui.keyHtml({id:'env',label:'环境密钥',enabled:true,source:'environment'});
  assert.ok(environment.includes('data-action="toggle"'));assert.ok(!environment.includes('data-action="remove"'));assert.ok(!environment.includes('data-action="rename"'));
  assert.ok(environment.includes('来自主机环境变量'));
  assert.ok(ui.keyHtml({id:'auth',enabled:true,status:'paused_authentication'}).includes('认证失败，已暂停'));
  assert.ok(ui.keyHtml({id:'balance',enabled:true,status:'paused_insufficient_balance'}).includes('余额不足，已暂停'));
  assert.ok(ui.keyHtml({id:'new',enabled:true,status:'available',requests:0}).includes('待调用'));
  const eventHtml=ui.eventHtml({seq:1,stage:'returned',message:'<unsafe>',key_label:'label<img>',verdict:'same',job_id:'job',row_id:0,gate_reason:'仍需核验',elapsed_ms:321,api_key:'synthetic-key-never-render',raw_response:'raw-never-render',reasoning_content:'hidden-never-render',request:{image:'image-never-render'}});
  assert.ok(eventHtml.includes('&lt;unsafe&gt;'));assert.ok(eventHtml.includes('建议相同'));assert.ok(eventHtml.includes('图片 0'));
  for (const value of ['synthetic-key-never-render','raw-never-render','hidden-never-render','image-never-render']) assert.ok(!eventHtml.includes(value));
  // A provider suggestion is never labelled as a server-confirmed result.
  assert.ok(!eventHtml.includes('已确认'));
  ui.state.pool={keys:[{id:'opaque-a',label:'当前主密钥'}]};
  const linkedEvent=ui.eventHtml({seq:9,stage:'requesting',key_id:'opaque-a'});
  assert.ok(linkedEvent.includes('Key：当前主密钥'));assert.ok(linkedEvent.includes('<dt>Key 标识</dt><dd>opaque-a</dd>'));
  assert.ok(ui.eventHtml({seq:10,stage:'returned',key_id:'removed-opaque'}).includes('已移除 Key removed-opaque'));

  ui.applySettings(json(initial));ui.state.pool={keys:[]};ui.renderKeys();
  assert.match(element('model-label').textContent,/已启用 AI 查找与复核/);
  ui.applySettings({...json(initial),enabled:false});assert.match(element('model-label').textContent,/AI 已关闭，使用本机匹配/);
  ui.applySettings(json(initial));
  assert.ok(element('qualification-state').textContent.includes('仍需人工确认'));
  element('debug-follow').checked=true;
  assert.equal(ui.processDebug({instance:'first',events:[{seq:1,stage:'requesting',message:'正在调用'}],cursor:1,last_seq:9,oldest_seq:1,dropped:0,active:[]}),true);
  assert.equal(ui.state.cursor,1,'do not skip backlog by jumping to last_seq');
  assert.equal(element('debug-log').scrollTop,1000);
  ui.processDebug({instance:'first',events:[{seq:1,message:'duplicate'},{seq:2,stage:'returned',message:'new'}],cursor:2,last_seq:9,oldest_seq:1,dropped:0,active:[]});
  assert.deepEqual(json(ui.state.events),[1,2]);assert.ok(!element('debug-events').innerHTML.includes('duplicate'));
  ui.processDebug({instance:'first',events:[{seq:5,stage:'manual',message:'人工'}],cursor:5,last_seq:5,oldest_seq:5,dropped:4,active:[]});
  assert.ok(element('debug-gap').textContent.includes('较早记录已省略'));
  ui.processDebug({instance:'second',reset:true,events:[{seq:1,stage:'preparing',message:'新服务'}],cursor:1,last_seq:1,oldest_seq:1,dropped:0,active:[{stage:'requesting',message:'正在调用',key_label:'合成 Key',elapsed_ms:400}]});
  assert.equal(ui.state.cursor,1);assert.deepEqual(json(ui.state.events),[1]);assert.ok(!element('debug-events').innerHTML.includes('new'));
  assert.ok(element('debug-gap').textContent.includes('重新启动'));assert.ok(element('debug-active').innerHTML.includes('合成 Key'));

  const synthetic='not-a-real-api-key-123';
  response={status:200,body:{settings:{...initial,key_revision:5,keys:[...initial.keys,{id:'key-b',label:'密钥 1',enabled:true,source:'saved'}]},pool:{keys:[]}}};
  element('key-batch').value=synthetic+'\n'+synthetic+'-second';
  onFetch=(url,options)=>{assert.equal(element('key-batch').value,'','clear secrets before sending');assert.equal(url,'/api/admin/keys');assert.equal(options.headers['X-HSD-Token'],'synthetic-csrf');};
  await ui.addKeys(stopEvent);onFetch=null;
  const payload=JSON.parse(calls.at(-1).options.body);
  assert.equal(payload.expected_revision,4);assert.equal(payload.add.length,2);assert.equal(payload.add[0].label,'密钥 1');
  assert.equal(element('key-batch').value,'');assert.equal(ui.state.settings.key_revision,5);
  assert.ok(element('admin-message').textContent.includes('已保存'));
  assert.ok(!element('key-list').innerHTML.includes(synthetic));
  response={status:409,body:{error:'配置版本冲突'}};
  await ui.mutateKeys({update:[{id:'key-a',enabled:false}]});
  assert.equal(ui.state.conflict,true);assert.equal(ui.state.settings.key_revision,5,'conflict cannot look successful');
  assert.ok(element('admin-message').textContent.includes('本次未保存'));assert.ok(element('key-add').disabled);
  const requestsBefore=calls.length;await ui.mutateKeys({remove:['key-a']});assert.equal(calls.length,requestsBefore,'conflict requires explicit reread');
  response={status:200,body:{settings:{...initial,key_revision:8},pool:{keys:[]},usage:{requests:2,unknown_usage_requests:1},debug:{instance:'second',cursor:1,last_seq:1,events:[],active:[]}}};
  await ui.refreshOverview(true);assert.equal(ui.state.conflict,false);assert.equal(ui.state.settings.key_revision,8);
  element('key-batch').value='short';await ui.addKeys(stopEvent);assert.equal(element('key-batch').value,'');assert.equal(calls.at(-1).url,'/api/admin/overview');
  element('key-batch').value=Array(101).fill(synthetic).join('\n');await ui.addKeys(stopEvent);assert.equal(element('key-batch').value,'');assert.ok(element('admin-message').textContent.includes('100'));
  response={status:500,body:{error:'保存失败'}};element('key-batch').value=synthetic;await ui.addKeys(stopEvent);
  assert.equal(element('key-batch').value,'');assert.ok(element('admin-message').textContent.includes('保存失败'));assert.ok(!element('admin-message').textContent.includes(synthetic));

  ui.schedulePoll();assert.equal(timers.get(ui.state.timer).delay,2000);
  sandbox.document.hidden=true;ui.schedulePoll();assert.equal(ui.state.timer,null);
  const beforeHidden=calls.length;await ui.poll();assert.equal(calls.length,beforeHidden,'hidden page makes no polling request');
  sandbox.document.hidden=false;ui.state.stopped=true;ui.schedulePoll();assert.equal(ui.state.timer,null);
  ui.state.stopped=false;ui.state.polls=0;
  response={status:200,body:{instance:'second',events:[{seq:2,stage:'returned',message:'返回'}],cursor:2,last_seq:5,oldest_seq:1,dropped:0,active:[]}};
  await ui.poll();assert.equal(timers.get(ui.state.timer).delay,100);assert.ok(calls.at(-1).url.includes('after=1&limit=100'));
  response={status:403,body:{error:'仅主机'}};await ui.poll();assert.equal(ui.state.stopped,true);assert.equal(ui.state.timer,null);
  assert.ok(element('debug-connection').textContent.includes('无权访问'));
  ui.state.stopped=false;response={status:200,body:{settings:initial,pool:{keys:[]},usage:null,debug:{instance:'second',events:[],cursor:2,last_seq:2,active:[]}}};
  await ui.boot();assert.ok(ui.state.timer);
  sandbox.document.hidden=true;listeners.visibilitychange();assert.equal(ui.state.timer,null);
  sandbox.document.hidden=false;listeners.visibilitychange();assert.equal(timers.get(ui.state.timer).delay,0);
  element('key-batch').value=synthetic;listeners['window:pagehide']();assert.equal(element('key-batch').value,'');assert.equal(ui.state.timer,null);assert.equal(ui.state.stopped,true);
  listeners['window:pageshow']();assert.equal(ui.state.stopped,false);assert.equal(timers.get(ui.state.timer).delay,0);
  assert.ok(!/localStorage|sessionStorage|console\./.test(source),'keys and debug are not persisted or logged by the UI');
  const html=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.html'),'utf8');
  assert.ok(html.includes('window.HSD_TOKEN = __HSD_TOKEN__'));assert.ok(html.includes('href="/"'));
  assert.ok(html.includes('发送可处理的表格图片和 AI 预览查找对应；同时由本机独立核验'));
  assert.ok(html.includes('模型建议不能解除文件硬异常'));
  assert.ok(!html.includes('仅对符合现有规则的疑难项发送'));
  const css=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.css'),'utf8');
  assert.ok(css.includes('#key-batch{-webkit-text-security:disc}'),'batch credentials default to masked input');
  console.log('Admin UI synthetic assertions passed');
}
main().catch((error)=>{console.error(error);process.exitCode=1;});
