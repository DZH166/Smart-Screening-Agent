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
    nodes.set(id, {id, value:'', files:[], disabled:false, textContent:'', innerHTML:'',
      previousElementSibling:{textContent:''}, dataset:{}, style:{setProperty(){}},
      classList:{add(...values){values.forEach((value)=>classes.add(value));},remove(...values){values.forEach((value)=>classes.delete(value));},contains(value){return classes.has(value);},toggle(value,force){if(force===undefined)force=!classes.has(value);if(force)classes.add(value);else classes.delete(value);}},
      querySelectorAll(){return [];},querySelector(selector){return element(`${id}:${selector}`);},
      addEventListener(){},replaceChildren(){},focus(){},
    });
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
  load(status,response){this.status=status;this.responseText=JSON.stringify(response);this.listeners.load();}
}
const location={origin:'http://192.168.1.2:8805',assign(url){location.assigned=url;}};
const sandbox={document:{getElementById:element,querySelectorAll(){return [];},body:{classList:{toggle(){}}},documentElement:{dataset:{}}},
  window:{HSD_ACCESS:{lan:true,remote:true},HSD_TOKEN:'session-token',location,setTimeout(){return 1;},clearTimeout(){},scrollTo(){}},
  location, performance:{now:()=>0},setTimeout:()=>1,clearTimeout(){},AbortController,
  FormData:class{constructor(){this.parts=[];}append(...part){this.parts.push(part);}},XMLHttpRequest:FakeXHR,
};
const source=fs.readFileSync(path.join(__dirname,'../hsd_tool/static/app.js'),'utf8');
assert.ok(source.includes('init().catch('));
vm.runInNewContext(source.replace(/  init\(\)\.catch\([^\n]+\);/, '  window.testUI={state,validateUploadFiles,configureAccess,setFormBusy,uploadFiles,isBusy,renderProgress,renderSummary,renderDone,openOutput};'),sandbox);
const ui=sandbox.window.testUI;
const MiB=1024*1024;
const workbook={name:'员工表格.XLSX',size:2*MiB};
const zip={name:'原稿.ZIP',size:20*MiB};

async function main(){
  assert.equal(ui.validateUploadFiles(workbook,zip),'');
  assert.match(ui.validateUploadFiles(null,zip),/表/);
  assert.match(ui.validateUploadFiles({name:'a.xls',size:1},zip),/xlsx/);
  assert.match(ui.validateUploadFiles(workbook,null),/ZIP/);
  assert.match(ui.validateUploadFiles(workbook,{name:'a.rar',size:1}),/zip/);
  assert.match(ui.validateUploadFiles(workbook,{name:'a.zip',size:0}),/为空/);
  assert.match(ui.validateUploadFiles({name:'a.xlsx',size:101*MiB},zip),/100 MiB/);
  assert.match(ui.validateUploadFiles(workbook,{name:'a.zip',size:1901*MiB}),/1900 MiB/);
  ui.configureAccess({lan:true,remote:true,upload_limits:{workbook_bytes:100*MiB,source_bytes:1900*MiB,total_bytes:10*MiB}});
  assert.match(ui.validateUploadFiles(workbook,zip),/合计/);
  ui.configureAccess({lan:true,remote:true,upload_limits:{total_bytes:2*1024*MiB}});
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
  assert.equal(xhr.headers['X-HSD-Token'],'session-token');
  assert.ok(!Object.keys(xhr.headers).some((key)=>key.toLowerCase()==='content-type'));
  assert.equal(xhr.data.parts.length,3);
  assert.equal(xhr.data.parts[0][0],'workbook');assert.equal(xhr.data.parts[0][1],workbook);
  assert.equal(xhr.data.parts[1][0],'source');assert.equal(xhr.data.parts[1][1],zip);
  assert.equal(xhr.data.parts[2][0],'start_number');assert.equal(xhr.data.parts[2][1],'12');
  xhr.progress({lengthComputable:true,loaded:25,total:100});
  assert.equal(element('upload-progress-percent').textContent,'25%');
  xhr.progress({lengthComputable:true,loaded:100,total:100});
  assert.ok(element('upload-progress-label').textContent.includes('正在检查'));
  xhr.load(200,{id:'employee-job'});
  assert.equal((await pending).id,'employee-job');
  const failure=ui.uploadFiles(workbook,zip,1);
  xhrs.at(-1).load(413,{error:'文件过大'});
  await assert.rejects(failure,/文件过大/);

  ui.state.job={id:'my-job',status:'queued',queue_position:2,progress:{current:8,total:20}};
  assert.ok(ui.isBusy());ui.renderProgress();
  assert.equal(element('processing-title').textContent,'排队等待处理…');
  assert.ok(element('processing-message').textContent.includes('第 2 位'));
  assert.equal(element('progress-percent').textContent,'','queued work must not display a stale stage percentage');
  assert.equal(element('progress-detail').textContent,'等待开始');
  assert.equal(element('progress-fill').style.width,'');
  ui.state.job={id:'my/job',status:'done',rows:[],download_ready:true};
  ui.renderDone();
  assert.equal(element('open-output-button').textContent,'下载结果 ZIP ↓');
  assert.ok(!element('open-output-button').disabled);
  await ui.openOutput();
  assert.equal(location.assigned,'/api/jobs/my%2Fjob/download');
  ui.state.job.download_ready=false;ui.renderDone();
  assert.ok(element('open-output-button').disabled);
  ui.state.job={id:'summary',status:'ready',rows:[],output_root:'private-host-path'};
  ui.renderSummary();
  assert.match(element('summary-output').textContent,/下载.*电脑/);
  assert.ok(!element('summary-output').textContent.includes('private-host-path'));

  ui.configureAccess({lan:false,remote:false});ui.setFormBusy(false);
  assert.ok(!element('local-workbook-field').classList.contains('hidden'));
  assert.ok(!element('workbook-path').disabled);
  assert.ok(element('workbook-upload').disabled);
  assert.ok(element('upload-fields').classList.contains('hidden'));
  console.log('Employee upload/download UI assertions passed');
}
main().catch((error)=>{console.error(error);process.exitCode=1;});
