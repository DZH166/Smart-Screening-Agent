// Synthetic admin interactions: no real server, browser storage or provider calls.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.js'),'utf8');
const nodes = new Map(), timers = new Map(), calls = [], listeners = {};
let nextTimer = 1, response = {status:200,body:{}}, fetchHandler = null;
function element(id) {
  if (!nodes.has(id)) {
    const classes = new Set(), node = {id,value:'',checked:false,disabled:false,textContent:'',dataset:{},htmlWrites:0,cards:[],controls:[],
      classList:{add(...v){v.forEach((x)=>classes.add(x));},remove(...v){v.forEach((x)=>classes.delete(x));},contains(v){return classes.has(v);},toggle(v,force){if(force===undefined)force=!classes.has(v);if(force)classes.add(v);else classes.delete(v);}},
      addEventListener(name,fn){(listeners[`${id}:${name}`] ||= []).push(fn);},
      querySelectorAll(selector){return selector==='[data-key-id]'?this.cards:selector==='button,input'?this.controls:[];},
      querySelector(selector){return element(`${id}:${selector}`);},focus(){sandbox.document.activeElement=this;},
      replaceChildren(){this.innerHTML='';},setAttribute(name,value){this[name]=value;},
    };
    let html='';Object.defineProperty(node,'innerHTML',{get(){return html;},set(value){html=value;this.htmlWrites++;}});
    nodes.set(id,node);
  }
  return nodes.get(id);
}
const sandbox = {document:{hidden:false,activeElement:null,getElementById:element,addEventListener(name,fn){listeners[name]=fn;}},
  window:{HSD_TOKEN:'synthetic-csrf',location:{replacements:[],replace(url){this.replacements.push(url);}},addEventListener(name,fn){listeners[`window:${name}`]=fn;}},AbortController,
  setTimeout(fn,delay){const id=nextTimer++;timers.set(id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);},
  fetch:async(url,options)=>{calls.push({url,options});const result=fetchHandler?await fetchHandler(url,options):response;return {ok:result.status>=200&&result.status<300,status:result.status,json:async()=>result.body};},
};
vm.runInNewContext(source.replace("  boot().catch(()=>message('管理页面加载失败，请刷新后重试。',true));",'  window.testAdmin={state,keyStats,keyHtml,ledgerHtml,loadLedger,renderKeys,applySettings,refreshOverview,addKeys,saveEnabled,mutateKeys,keyAction,renameKey,stopPolling,schedulePoll,poll,logout,boot};'),sandbox);
const ui=sandbox.window.testAdmin;
const initial={enabled:true,configured:true,model:'synthetic-model',mode:'evaluation',key_revision:4,key_persistence:'windows_dpapi',keys:[{id:'key-a',label:'主密钥',enabled:true,source:'saved'}]};
const stopEvent={preventDefault(){}};
function json(value){return JSON.parse(JSON.stringify(value));}
function ready(settings=initial,pool={keys:[]}){
  Object.assign(ui.state,{loading:false,saving:false,refreshing:false,conflict:false,stopped:false,polling:false,enableDirty:false,locked:false,authLost:false,suspended:false,loggingOut:false});
  ui.applySettings(json(settings));ui.state.pool=json(pool);ui.renderKeys();
}
function keyResponse(settings=initial,pool={keys:[]}){return {status:200,body:{settings:json(settings),pool:json(pool)}};}
function deferred(){let resolve;const promise=new Promise((done)=>{resolve=done;});return {promise,resolve};}
function actionEvent(card,action){const button={dataset:{action},closest(selector){return selector==='[data-action]'?this:selector==='[data-key-id]'?card:null;}};return {target:button};}

async function main(){
  const malicious=ui.keyHtml({id:'id"<x>',label:'<script>label</script>',enabled:true,status:'cooldown',cooldown_seconds:2.5,source:'saved',api_key:'synthetic-never-render'});
  assert.ok(malicious.includes('&lt;script&gt;label&lt;/script&gt;'));assert.ok(!malicious.includes('<script>'));
  assert.ok(malicious.includes('id&quot;&lt;x&gt;'));assert.ok(!malicious.includes('synthetic-never-render'));assert.ok(malicious.includes('冷却剩余约 3 秒'));
  const environment=ui.keyHtml({id:'env',label:'环境密钥',enabled:true,source:'environment'});
  assert.ok(environment.includes('data-action="toggle"'));assert.ok(!environment.includes('data-action="remove"'));assert.ok(!environment.includes('data-action="rename"'));assert.ok(environment.includes('来自主机环境变量'));
  assert.ok(ui.keyHtml({id:'auth',enabled:true,status:'paused_authentication'}).includes('认证失败，已暂停'));
  assert.ok(ui.keyHtml({id:'auth',enabled:true,status:'paused_authentication'}).includes('修复后先停用再启用'));
  assert.ok(ui.keyHtml({id:'balance',enabled:true,status:'paused_insufficient_balance'}).includes('补充余额'));
  assert.ok(ui.keyHtml({id:'new',enabled:true,status:'available',requests:0}).includes('待验证'));
  assert.ok(ui.keyHtml({id:'disabled',enabled:false,status:'available',requests:1}).includes('已停用'));

  response=keyResponse();await ui.boot();const bootRead=calls.filter(({url})=>url==='/api/admin/keys').at(-1);assert.equal(bootRead.options.method,'GET');assert.equal(timers.get(ui.state.timer).delay,30000);
  assert.ok(!calls.some(({url})=>url==='/api/admin/ledger'),'the closed ledger must not fetch plaintext at boot');
  // The add-key box is masked by default and can be revealed on demand.
  assert.ok(!element('key-batch').classList.contains('key-plain'));
  listeners['key-reveal:click'][0]();
  assert.ok(element('key-batch').classList.contains('key-plain'));assert.equal(element('key-reveal').textContent,'隐藏');
  listeners['key-reveal:click'][0]();
  assert.ok(!element('key-batch').classList.contains('key-plain'));assert.equal(element('key-reveal').textContent,'显示');
  assert.equal(element('settings-state').textContent,'已启用，导入后自动运行。');assert.ok(element('qualification-state').textContent.includes('仍需人工确认'));assert.ok(element('persistence-state').textContent.includes('DPAPI'));
  ui.applySettings({...json(initial),key_persistence:'linux_aesgcm'});assert.ok(element('persistence-state').textContent.includes('服务器使用独立主密钥'));assert.ok(!element('persistence-state').textContent.includes('重启后需重新填写'));
  ui.applySettings({...json(initial),enabled:false});assert.match(element('settings-state').textContent,/已关闭 AI/);
  ui.applySettings({...json(initial),configured:false});assert.match(element('settings-state').textContent,/请添加并启用 Key/);
  ui.applySettings({...json(initial),storage_warning:'合成存储异常'});assert.equal(element('storage-warning').textContent,'合成存储异常');assert.ok(!element('storage-warning').classList.contains('hidden'));ready();assert.ok(element('storage-warning').classList.contains('hidden'));

  // Status-only updates preserve input, focus and an open delete confirmation.
  const card=element('test-card');card.dataset.keyId='key-a';element('key-list').cards=[card];
  const labelInput=card.querySelector('input');labelInput.value='正在编辑的标签';labelInput.focus();card.querySelector('[data-delete-prompt]').classList.remove('hidden');
  const listWrites=element('key-list').htmlWrites;
  ui.state.pool={keys:[{id:'key-a',label:'主密钥',enabled:true,source:'saved',status:'cooldown',cooldown_seconds:12}]};ui.renderKeys();
  assert.equal(element('key-list').htmlWrites,listWrites);assert.equal(labelInput.value,'正在编辑的标签');assert.equal(sandbox.document.activeElement,labelInput);assert.ok(!card.querySelector('[data-delete-prompt]').classList.contains('hidden'));
  assert.equal(card.querySelector('[data-key-status]').textContent,'冷却中');assert.equal(card.querySelector('[data-key-note]').textContent,'冷却剩余约 12 秒');
  Object.assign(ui.state.pool.keys[0],{status:'available',cooldown_seconds:0,requests:1});ui.renderKeys();assert.ok(card.querySelector('[data-key-note]').classList.contains('hidden'));

  // Background reads leave unsaved switches and editing controls alone.
  element('ai-enabled').checked=false;listeners['ai-enabled:change'][0]();assert.equal(ui.state.enableDirty,true);
  const read=deferred();fetchHandler=()=>read.promise;const reading=ui.refreshOverview(false);
  assert.equal(ui.state.refreshing,true);assert.equal(ui.state.loading,false);assert.equal(element('ai-enabled').disabled,false);assert.equal(element('key-batch').disabled,false);
  read.resolve(keyResponse());await reading;fetchHandler=null;
  assert.equal(element('ai-enabled').checked,false);assert.equal(ui.state.enableDirty,true);assert.equal(sandbox.document.activeElement,labelInput);assert.equal(element('key-list').htmlWrites,listWrites);

  // An external revision freezes edits until an explicit reload, without destroying them.
  const revised={...json(initial),key_revision:5,keys:[{...initial.keys[0],label:'其他页面的新标签'}]};
  response=keyResponse(revised,{keys:[{...revised.keys[0],status:'available',requests:1}]});await ui.refreshOverview(false);
  assert.equal(ui.state.conflict,true);assert.equal(ui.state.settings.key_revision,4);assert.ok(element('key-add').disabled);assert.ok(element('admin-message').textContent.includes('刷新设置'));
  assert.equal(element('key-list').htmlWrites,listWrites,'external edits must not destroy the unsaved label');assert.equal(labelInput.value,'正在编辑的标签');assert.equal(sandbox.document.activeElement,labelInput);
  const beforeLocked=calls.length;await ui.mutateKeys({remove:['key-a']});assert.equal(calls.length,beforeLocked);
  await ui.refreshOverview(true);assert.equal(ui.state.conflict,false);assert.equal(ui.state.settings.key_revision,5);assert.equal(ui.state.enableDirty,false);assert.equal(element('ai-enabled').checked,true);assert.ok(element('key-list').innerHTML.includes('其他页面的新标签'));

  const synthetic='not-a-real-api-key-123';ready();
  response=keyResponse({...json(initial),key_revision:5,keys:[...initial.keys,{id:'key-b',label:'密钥 1',enabled:true,source:'saved'}]});element('key-batch').value=synthetic+'\n'+synthetic+'-second';
  fetchHandler=(url,options)=>{if(url!=='/api/admin/keys')return {status:200,body:{keys:[]}};assert.equal(element('key-batch').value,'','clear secrets before awaiting');assert.equal(options.method,'POST');assert.equal(options.headers['X-HSD-Token'],'synthetic-csrf');return response;};await ui.addKeys(stopEvent);fetchHandler=null;
  const payload=JSON.parse(calls.filter(({url})=>url==='/api/admin/keys').at(-1).options.body);assert.equal(payload.expected_revision,4);assert.equal(payload.add.length,2);assert.equal(payload.add[0].label,'密钥 1');assert.equal(element('key-batch').value,'');assert.equal(ui.state.settings.key_revision,5);assert.ok(element('admin-message').textContent.includes('已保存 Key'));assert.ok(!element('key-list').innerHTML.includes(synthetic));
  response={status:409,body:{error:'配置版本冲突'}};await ui.mutateKeys({update:[{id:'key-a',enabled:false}]});assert.equal(ui.state.conflict,true);assert.equal(ui.state.settings.key_revision,5);assert.ok(element('admin-message').textContent.includes('本次未保存'));assert.ok(element('key-add').disabled);
  const requestsBefore=calls.length;await ui.mutateKeys({remove:['key-a']});assert.equal(calls.length,requestsBefore);
  response=keyResponse({...json(initial),key_revision:8});await ui.refreshOverview(true);assert.equal(ui.state.conflict,false);assert.equal(ui.state.settings.key_revision,8);
  const beforeInvalid=calls.length;element('key-batch').value='short';await ui.addKeys(stopEvent);assert.equal(element('key-batch').value,'');assert.equal(calls.length,beforeInvalid);
  element('key-batch').value=Array(101).fill(synthetic).join('\n');await ui.addKeys(stopEvent);assert.equal(element('key-batch').value,'');assert.ok(element('admin-message').textContent.includes('100'));assert.equal(calls.length,beforeInvalid);
  response={status:500,body:{error:'保存失败'}};element('key-batch').value=synthetic;await ui.addKeys(stopEvent);assert.equal(element('key-batch').value,'');assert.ok(element('admin-message').textContent.includes('保存失败'));assert.ok(!element('admin-message').textContent.includes(synthetic));assert.equal(ui.state.saving,false);

  // Key actions require explicit delete confirmation; environment keys permit only toggling.
  ready();ui.keyAction(actionEvent(card,'rename'));assert.ok(!card.querySelector('[data-rename-form]').classList.contains('hidden'));assert.equal(sandbox.document.activeElement,labelInput);
  ui.keyAction(actionEvent(card,'cancel-rename'));assert.ok(card.querySelector('[data-rename-form]').classList.contains('hidden'));
  const beforePrompt=calls.length;ui.keyAction(actionEvent(card,'remove'));assert.equal(calls.length,beforePrompt);assert.ok(!card.querySelector('[data-delete-prompt]').classList.contains('hidden'));ui.keyAction(actionEvent(card,'cancel-remove'));assert.ok(card.querySelector('[data-delete-prompt]').classList.contains('hidden'));
  const form=card.querySelector('[data-rename-form]');form.closest=()=>card;
  const renameEvent={target:{closest:()=>form},preventDefault(){}};
  form.querySelector('input').value='  ';ui.renameKey(renameEvent);assert.equal(calls.length,beforePrompt);assert.equal(sandbox.document.activeElement,form.querySelector('input'));
  const renaming=deferred();fetchHandler=()=>renaming.promise;form.querySelector('input').value=' 新标签 ';ui.renameKey(renameEvent);
  assert.deepEqual(JSON.parse(calls.at(-1).options.body),{expected_revision:4,update:[{id:'key-a',label:'新标签'}]});
  renaming.resolve(keyResponse({...json(initial),key_revision:5,keys:[{...initial.keys[0],label:'新标签'}]}));await new Promise(setImmediate);fetchHandler=null;
  const deleting=deferred();fetchHandler=()=>deleting.promise;ui.keyAction(actionEvent(card,'confirm-remove'));
  assert.deepEqual(JSON.parse(calls.at(-1).options.body),{expected_revision:5,remove:['key-a']});
  deleting.resolve(keyResponse({...json(initial),key_revision:6,keys:[]}));await new Promise(setImmediate);fetchHandler=null;assert.equal(ui.state.settings.keys.length,0);
  const envSettings={...json(initial),keys:[{id:'env',label:'环境密钥',enabled:true,source:'environment'}]};ready(envSettings);card.dataset.keyId='env';
  const beforeEnv=calls.length;for(const action of ['rename','remove','confirm-remove'])ui.keyAction(actionEvent(card,action));assert.equal(calls.length,beforeEnv);
  const toggle=deferred();fetchHandler=()=>toggle.promise;ui.keyAction(actionEvent(card,'toggle'));assert.equal(JSON.parse(calls.at(-1).options.body).update[0].enabled,false);
  toggle.resolve(keyResponse({...envSettings,key_revision:5,keys:[{...envSettings.keys[0],enabled:false}]}));await new Promise(setImmediate);fetchHandler=null;assert.equal(ui.state.settings.keys[0].enabled,false);card.dataset.keyId='key-a';

  // Neither arrival order permits a stale read to overwrite a simultaneous mutation.
  for(const readReturnsFirst of [true,false]){
    ready();const background=deferred(),save=deferred();fetchHandler=(url,options)=>options.method==='GET'?background.promise:save.promise;
    const backgroundWork=ui.refreshOverview(false),saveWork=ui.mutateKeys({update:[{id:'key-a',label:'新标签'}]});assert.equal(ui.state.saving,true);
    const afterSave={...json(initial),key_revision:5,keys:[{...initial.keys[0],label:'新标签'}]};
    if(readReturnsFirst){background.resolve(keyResponse());await backgroundWork;assert.equal(ui.state.settings.key_revision,4);assert.equal(ui.state.saving,true);save.resolve(keyResponse(afterSave));await saveWork;}
    else{save.resolve(keyResponse(afterSave));await saveWork;background.resolve(keyResponse());await backgroundWork;}
    assert.equal(ui.state.settings.key_revision,5);assert.equal(ui.state.settings.keys[0].label,'新标签');assert.equal(ui.state.conflict,false);fetchHandler=null;
  }

  ready();element('ai-enabled').checked=false;listeners['ai-enabled:change'][0]();const enabledSave=deferred();
  const disabledSettings={...json(initial),enabled:false,key_revision:5},disabledPool={keys:[{...initial.keys[0],status:'service_disabled',requests:7}]};
  fetchHandler=(url)=>url==='/api/admin/settings'?enabledSave.promise:keyResponse(disabledSettings,disabledPool);const savingEnabled=ui.saveEnabled(stopEvent);
  assert.equal(calls.at(-1).url,'/api/admin/settings');assert.equal(JSON.parse(calls.at(-1).options.body).enabled,false);assert.equal(JSON.parse(calls.at(-1).options.body).expected_revision,initial.key_revision);
  const beforeDuplicate=calls.length;await ui.saveEnabled(stopEvent);assert.equal(calls.length,beforeDuplicate);assert.ok(!element('admin-message').textContent.includes('已保存'));
  enabledSave.resolve(keyResponse(disabledSettings));await savingEnabled;fetchHandler=null;
  assert.equal(element('ai-enabled').checked,false);assert.ok(element('admin-message').textContent.includes('已保存'));assert.equal(ui.state.conflict,false);
  assert.equal(calls.at(-1).url,'/api/admin/keys');assert.equal(calls.at(-1).options.method,'GET');
  assert.equal(card.querySelector('[data-key-status]').textContent,'AI 已关闭');

  // A stale global switch edit cannot overwrite another administrator page.
  ready();element('ai-enabled').checked=false;listeners['ai-enabled:change'][0]();
  response={status:409,body:{error:'配置已在另一页面更新'}};await ui.saveEnabled(stopEvent);
  assert.equal(ui.state.conflict,true);assert.equal(ui.state.enableDirty,true);
  assert.equal(element('ai-enabled').checked,false);assert.ok(element('enable-save').disabled);
  assert.ok(element('admin-message').textContent.includes('本次未保存'));
  ready(disabledSettings,disabledPool);

  // Re-enabling cannot leave a stale "AI disabled" Key badge until the next poll.
  const updatedPool=deferred();element('ai-enabled').checked=true;listeners['ai-enabled:change'][0]();
  fetchHandler=(url)=>url==='/api/admin/settings'?keyResponse(json(initial)):updatedPool.promise;
  const enabling=ui.saveEnabled(stopEvent);await new Promise(setImmediate);
  assert.equal(ui.state.settings.enabled,true);assert.equal(element('ai-enabled').checked,true);
  assert.equal(card.querySelector('[data-key-status]').textContent,'待验证','clear old runtime status while reading the saved switch state');
  updatedPool.resolve(keyResponse(initial,{keys:[{...initial.keys[0],status:'available',requests:7}]}));await enabling;fetchHandler=null;
  assert.equal(card.querySelector('[data-key-status]').textContent,'可用');assert.equal(ui.state.conflict,false);

  // A failed status GET after a successful POST cannot undo or mislabel the saved switch.
  ready(disabledSettings,disabledPool);element('ai-enabled').checked=true;listeners['ai-enabled:change'][0]();
  const beforeReadFailure=calls.length;
  fetchHandler=(url)=>url==='/api/admin/settings'?keyResponse(json(initial)):{status:500,body:{error:'Key 状态读取失败，请稍后刷新。'}};
  await ui.saveEnabled(stopEvent);fetchHandler=null;
  assert.equal(calls.length,beforeReadFailure+2);assert.equal(ui.state.settings.enabled,true);assert.equal(element('ai-enabled').checked,true);
  assert.equal(card.querySelector('[data-key-status]').textContent,'待验证');assert.equal(ui.state.saving,false);
  assert.ok(element('admin-message').textContent.includes('读取失败'));assert.ok(!/未保存|开关保存失败/.test(element('admin-message').textContent));

  response={status:500,body:{error:'开关保存失败'}};element('ai-enabled').checked=false;const beforeFailedSave=calls.length;await ui.saveEnabled(stopEvent);
  assert.equal(calls.length,beforeFailedSave+1,'failed POST does not issue a follow-up status read');
  assert.equal(element('ai-enabled').checked,true);assert.ok(element('admin-message').textContent.includes('失败'));assert.equal(ui.state.saving,false);

  // Only small read-only Key requests run every 30 seconds while visible.
  ready();response=keyResponse();ui.schedulePoll();assert.equal(timers.get(ui.state.timer).delay,30000);
  const pollBefore=calls.length;await ui.poll();assert.equal(calls.length,pollBefore+1);assert.equal(calls.at(-1).url,'/api/admin/keys');assert.equal(calls.at(-1).options.method,'GET');assert.equal(timers.get(ui.state.timer).delay,30000);
  sandbox.document.hidden=true;listeners.visibilitychange();assert.equal(ui.state.timer,null);const beforeHidden=calls.length;await ui.poll();assert.equal(calls.length,beforeHidden);
  sandbox.document.hidden=false;listeners.visibilitychange();assert.equal(timers.get(ui.state.timer).delay,0);
  const pollRead=deferred();fetchHandler=()=>pollRead.promise;const inFlight=ui.poll();const beforeSecondPoll=calls.length;await ui.poll();assert.equal(calls.length,beforeSecondPoll);pollRead.resolve(keyResponse());await inFlight;fetchHandler=null;
  response={status:403,body:{error:'权限失效'}};await ui.poll();assert.equal(ui.state.stopped,true);assert.equal(ui.state.timer,null);assert.ok(element('admin-message').textContent.includes('重新登录'));assert.ok(!element('admin-message').textContent.includes('仅限主机'));
  const expiredCalls=calls.length;response=keyResponse();await ui.refreshOverview(true);assert.equal(calls.length,expiredCalls,'expired pages cannot unlock themselves by refreshing settings');
  await listeners['window:pageshow']();assert.equal(ui.state.locked,true,'pageshow cannot restore an expired administrator session');
  ready();element('key-batch').value=synthetic;listeners['window:pagehide']();assert.equal(element('key-batch').value,'');assert.equal(ui.state.timer,null);assert.equal(ui.state.stopped,true);assert.equal(ui.state.locked,true);const afterLeave=calls.length;await ui.poll();assert.equal(calls.length,afterLeave);
  const resumeRead=deferred();fetchHandler=()=>resumeRead.promise;const resuming=listeners['window:pageshow']();assert.equal(element('key-add').disabled,true,'restored pages recheck authentication before enabling edits');
  resumeRead.resolve(keyResponse());await resuming;fetchHandler=null;assert.equal(ui.state.stopped,false);assert.equal(timers.get(ui.state.timer).delay,30000);
  element('key-batch').value=synthetic;listeners['window:beforeunload']();assert.equal(element('key-batch').value,'');assert.equal(ui.state.timer,null);

  // Plaintext is only fetched on demand and is removed, including attributes, on close.
  const secret='sk-synthetic-ledger-for-ui-only';
  ready();response={status:200,body:{keys:[{id:'test-key',label:'测试密钥',api_key:secret}]}};
  element('ledger-details').open=true;await ui.loadLedger();
  assert.ok(element('ledger-list').innerHTML.includes(`data-value="${secret}"`));
  assert.equal(calls.at(-1).options.cache,'no-store');assert.equal(calls.at(-1).options.headers['X-HSD-Token'],'synthetic-csrf');
  element('ledger-details').open=false;listeners['ledger-details:toggle'][0]();assert.equal(element('ledger-list').innerHTML,'');
  const closedRead=deferred();fetchHandler=()=>closedRead.promise;element('ledger-details').open=true;const closingWork=ui.loadLedger();element('ledger-details').open=false;listeners['ledger-details:toggle'][0]();
  closedRead.resolve(response);await closingWork;fetchHandler=null;assert.equal(element('ledger-list').innerHTML,'','late plaintext cannot repopulate a closed ledger');

  // Every authenticated path must lock on 401/403, clear secrets and stop reads.
  for(const [operation,status] of [['overview',401],['ledger',403],['keys',401],['switch',403]]){
    ready();element('ledger-details').open=true;element('ledger-list').innerHTML=`<code data-value="${secret}">${secret}</code>`;element('key-batch').value=synthetic;
    element('key-batch').classList.add('key-plain');ui.schedulePoll();response={status,body:{error:'expired'}};
    if(operation==='overview')await ui.refreshOverview(false);
    if(operation==='ledger')await ui.loadLedger();
    if(operation==='keys')await ui.mutateKeys({update:[{id:'key-a',enabled:false}]});
    if(operation==='switch')await ui.saveEnabled(stopEvent);
    assert.equal(element('ledger-list').innerHTML,'',operation);assert.equal(element('ledger-details').open,false);assert.equal(element('key-batch').value,'');assert.ok(!element('key-batch').classList.contains('key-plain'));
    assert.equal(ui.state.locked,true);assert.equal(ui.state.timer,null);assert.equal(element('key-add').disabled,true);assert.equal(element('key-reveal').disabled,true);assert.ok(!element('admin-login').classList.contains('hidden'));
    const stoppedCalls=calls.length;await ui.poll();await ui.refreshOverview(true);assert.equal(calls.length,stoppedCalls);
  }

  // A successful response arriving after navigation cannot restore any plaintext.
  ready();element('ledger-details').open=true;const leavingRead=deferred();fetchHandler=()=>leavingRead.promise;const leavingWork=ui.loadLedger();
  listeners['window:pagehide']();leavingRead.resolve({status:200,body:{keys:[{id:'late',api_key:secret}]}});await leavingWork;fetchHandler=null;
  assert.equal(element('ledger-list').innerHTML,'');assert.equal(ui.state.locked,true);assert.equal(ui.state.timer,null);

  // Failed logout never pretends the server revoked its session; retry is explicit.
  ready();element('ledger-details').open=true;element('ledger-list').innerHTML=`<code data-value="${secret}">${secret}</code>`;element('key-batch').value=synthetic;
  const redirects=sandbox.window.location.replacements.length;response={status:500,body:{error:'synthetic logout failure'}};await ui.logout();
  assert.equal(sandbox.window.location.replacements.length,redirects);assert.ok(element('admin-message').textContent.includes('退出请求未完成'));assert.equal(element('ledger-list').innerHTML,'');assert.equal(element('key-batch').value,'');assert.equal(ui.state.locked,true);assert.equal(element('admin-logout').disabled,false);
  const retry=deferred();fetchHandler=()=>retry.promise;const retrying=ui.logout();const beforeDuplicateLogout=calls.length;await ui.logout();assert.equal(calls.length,beforeDuplicateLogout);assert.equal(element('admin-logout').disabled,true);
  retry.resolve({status:200,body:{ok:true}});await retrying;fetchHandler=null;assert.equal(sandbox.window.location.replacements.at(-1),'/admin/login');

  const html=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.html'),'utf8'),css=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/admin.css'),'utf8');
  assert.ok(html.includes('window.HSD_TOKEN = __HSD_TOKEN__'));assert.ok(html.includes('href="/"'));assert.equal((html.match(/<section\b/g)||[]).length,3,'AI settings, Key management and the Key ledger');
  assert.ok(html.includes('同时由本机独立核验'));assert.ok(html.includes('模型建议不能解除文件硬异常'));assert.ok(html.includes('<summary>使用说明</summary>'));assert.ok(html.includes('原始 XLSX、ZIP、AI 文件和本机路径不会发送'));
  assert.ok(html.includes('<details id="ledger-details">')&&!html.includes('<details id="ledger-details" open'),'the key ledger is closed until requested');
  assert.ok(html.includes('id="ledger-list"')&&html.includes('id="ledger-state"'),'the key ledger is present');
  const ledgerRow=ui.ledgerHtml({id:'ledger-a',label:'主密钥',api_key:'sk-ledger-visible-value'});
  assert.ok(ledgerRow.includes('data-value="sk-ledger-visible-value"'),'copy keeps the value');
  assert.ok(!/>sk-ledger-visible-value</.test(ledgerRow),'the value stays masked until revealed');
  assert.ok(ledgerRow.includes('data-reveal')&&ledgerRow.includes('data-copy'));
  for(const text of [source,html,css])assert.ok(!/debug|usage-panel|usage-cost|estimated_usd|费用|US\$|实时调试|累计用量/.test(text),'removed panels have no hidden UI or rendering code');
  assert.ok(calls.every(({url})=>url==='/api/admin/keys'||url==='/api/admin/settings'||url==='/api/admin/ledger'||url==='/admin/logout'),'no diagnostic or cumulative-cost request');
  assert.ok(html.includes('id="key-reveal"'),'the add-key input has a reveal toggle');
  assert.ok(!/localStorage|sessionStorage|console\./.test(source),'credentials are not persisted or logged');assert.ok(css.includes('#key-batch{-webkit-text-security:disc}'));
  assert.ok(css.includes('#key-batch.key-plain{-webkit-text-security:none}'),'the reveal toggle can unmask the input');
  console.log('Admin UI synthetic assertions passed');
}
main().catch((error)=>{console.error(error);process.exitCode=1;});
