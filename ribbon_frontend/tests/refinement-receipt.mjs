// Explicit synthetic HTTP fixture: version-bound request display, no model calls.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createHash } from 'node:crypto';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.HSD_PLAYWRIGHT_MODULE || 'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url));
const profile={id:'synthetic-profile',version:1,name:'合成测试规格',width:1200,height:520,dpi:300,is_demo:true};
const image='/api/ribbon/receipt-test.svg';
const source='🍀图案缩小一点。\n保持背景不变；字样 <b>原文</b> 不改。';
const snapshot={asset_refs:['pattern'],background_ref:'background',template_id:'single',template_mode:'single',template_version:1,
  output_profile:profile,params:{},layout_engine:'seamless-unit-v2',pattern_slots:['slot-1'],design_density:'balanced',background_tone:'original',
  loop:{engine:'seamless-unit-v2',width:1200,height:520,status:'checked',issues:[],kind:'sequence'}};
function version(id,sequence,prompt){return {id,design_id:'design',parent_version_id:sequence?'draft':null,sequence,prompt,
  snapshot:structuredClone(snapshot),render_kind:'layered',provider:'test',created_at:'2026-11-06',preview_url:image+'?id='+id,
  download_url:'/api/ribbon/versions/'+id+'/download'};}
const draft=version('draft',0,''),legacy=version('legacy',1,source),missing=version('missing',2,'');
const design={id:'design',name:'合成精修收据测试',current_version_id:legacy.id,successful_refinement_count:1,active_job_id:null,
  revision:2,versions:[draft,legacy,missing],active_job:null};
function receiptFor(v, requirements) {
  v.snapshot.edit_plan={request_receipt:{protocol:'ribbon-request-v2',source_sha256:createHash('sha256').update(v.prompt,'utf8').digest('hex'),
    coverage:'checked',verification_scope:'plan_and_geometry_only',image_effect_verified:false,requirements}};
  return v;
}
const split=Array.from(source).indexOf('\n');
const geometry={id:'r1',source_id:'s1',start:0,end:split+1,kind:'modify',target:'layout',method:'parameters',execution:'geometry_verified'};
const preserve={id:'r2',source_id:'s2',start:split+1,end:Array.from(source).length,kind:'preserve',target:'background',method:'preserve',execution:'constraint_forwarded'};
const checked=receiptFor(version('checked',3,source),[geometry,preserve]);
const imageGenerated=receiptFor(version('image-generated',4,source),[{...geometry,method:'image',execution:'image_generated_unverified'},preserve]);
const mismatch=structuredClone(checked);mismatch.id='hash-mismatch';mismatch.sequence=5;mismatch.snapshot.edit_plan.request_receipt.source_sha256='0'.repeat(64);
const malformed=structuredClone(checked);malformed.id='bad-range';malformed.sequence=6;malformed.snapshot.edit_plan.request_receipt.requirements[0].end=99999;
const onlyPreserve=receiptFor(version('only-preserve',7,source),[{...preserve,start:0}]);
const mixed=receiptFor(version('mixed',8,source),[geometry,{...preserve,kind:'modify',method:'image',execution:'image_generated_unverified'}]);
design.versions.push(checked,imageGenerated,mismatch,malformed,onlyPreserve,mixed);
const oldParameters=structuredClone(checked);oldParameters.id='old-parameters';oldParameters.sequence=9;
oldParameters.snapshot.layout_engine='design-rhythm-v2';delete oldParameters.snapshot.loop;
oldParameters.snapshot.edit_plan.request_receipt.requirements[0].execution='parameters_applied_unverified';
design.versions.push(oldParameters);
const v3Parameters=structuredClone(oldParameters);v3Parameters.id='v3-parameters';v3Parameters.sequence=14;
v3Parameters.snapshot.layout_engine='seamless-unit-v3';v3Parameters.snapshot.loop={...snapshot.loop,engine:'seamless-unit-v3'};
design.versions.push(v3Parameters);
for(const [i,mutate] of [
  r=>{r[1].source_id=r[0].source_id;},
  r=>{r[1].start=r[0].end-1;},
  r=>{r[1].start=r[0].end+1;},
  r=>{r[1].id=r[0].id;}
].entries()) {
  const invalid=structuredClone(checked);invalid.id='invalid-scope-'+i;invalid.sequence=10+i;
  mutate(invalid.snapshot.edit_plan.request_receipt.requirements);design.versions.push(invalid);
}
const calls=[];
const server=createServer(async(req,res)=>{
  const p=new URL(req.url,'http://localhost').pathname;
  calls.push({path:p,method:req.method});
  const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  try {
    if(p==='/') {let html=await readFile(path.join(root,'hsd_tool/static/index.html'),'utf8');
      html=html.replace('__HSD_TOKEN__',JSON.stringify('synthetic-token')).replace('__HSD_ACCESS__','{}').replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g,'');
      res.writeHead(200,{'Content-Type':'text/html'});res.end(html);return;}
    if(p.startsWith('/static/')){res.writeHead(200,{'Content-Type':p.endsWith('.webp')?'image/webp':p.endsWith('.css')?'text/css':'text/javascript'});res.end(await readFile(path.join(root,'hsd_tool',p)));return;}
    if(p===image || p.endsWith('/download')) {res.writeHead(200,{'Content-Type':'image/svg+xml'});res.end('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520"><rect width="1200" height="520" fill="#e5eee0"/><text x="100" y="200">SYNTHETIC ONLY</text></svg>');return;}
    if(p==='/api/ribbon/auth/me')return json({id:'synthetic-receipt',username:'合成员工',role:'employee'});
    if(p==='/api/ribbon/config')return json({provider:'test',auth_mode:'demo',ai_ready:true,output_profile:profile,max_refinements:2});
    if(p==='/api/ribbon/assets')return json([{id:'pattern',name:'合成图案',kind:'pattern',is_demo:true,shared:true,url:image},{id:'background',name:'合成底纹',kind:'background',is_demo:true,shared:true,url:image}]);
    if(p==='/api/ribbon/templates')return json([{id:'single',name:'单排重复',mode:'single',version:1,enabled:true,thumbnail_url:image,rules:{}}]);
    if(p==='/api/ribbon/design-styles')return json([{id:'classic',label:'经典等距',hint:'合成风格'}]);
    if(p==='/api/ribbon/designs')return json([design]);
    if(p==='/api/ribbon/designs/design')return json(design);
    return json({detail:'合成测试未配置此操作'},404);
  }catch{json({detail:'合成测试读取失败'},500);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:process.env.HSD_BROWSER_CHANNEL || 'chrome',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:'+server.address().port+'/#ribbon');
  const result=page.getByRole('region',{name:'本版本精修结果',exact:true});
  await result.getByText('已生成，效果请对照要求',{exact:true}).waitFor();
  assert.equal(await result.locator('details').getAttribute('open'),null);
  await result.getByText('查看本次要求',{exact:true}).click();
  assert.equal(await result.locator('.original-refinement-request').innerText(),source);
  assert.equal(await result.locator('b').count(),0,'request text is escaped, never interpreted as HTML');
  assert.equal(await page.getByRole('link',{name:'下载循环单元',exact:true}).count(),1,'download requires no new confirmation');
  await page.locator('.history-panel > summary').click();
  await page.locator('.version-card').filter({hasText:'精修 2'}).click();
  assert.equal(await result.locator('details').getAttribute('open'),null,'version changes reset the request disclosure');
  await result.getByText('查看本次要求',{exact:true}).click();
  await result.getByText('此旧版本没有保存修改原文。',{exact:true}).waitFor();
  await page.locator('.version-card').filter({hasText:'首稿'}).click();
  assert.equal(await page.getByRole('region',{name:'本版本精修结果',exact:true}).count(),0,'first draft does not invent a refinement request');
  const choose=async(sequence)=>{await page.locator('.version-card').filter({has:page.getByText('精修 '+sequence,{exact:true})}).click();};
  await choose(3);
  await result.getByText('参数调整已核对',{exact:true}).waitFor();
  assert.equal(await result.locator('details').getAttribute('open'),null);
  await result.getByText('查看本次要求',{exact:true}).click();
  assert.equal(await result.locator('.refinement-requirements li').count(),2);
  assert.equal(await result.locator('.refinement-requirements li').first().locator('span').last().textContent(),Array.from(source).slice(0,split+1).join(''),'Python Unicode codepoint ranges preserve emoji and the following characters');
  await result.getByText('保留要求 · 约束已传递',{exact:true}).waitFor();
  assert.equal(await result.getByText('已保留',{exact:true}).count(),0,'a forwarded preservation constraint does not claim unchanged image pixels');
  for(const sequence of [4,5,6,7,8]) {
    await choose(sequence);
    await result.getByText('已生成，效果请对照要求',{exact:true}).waitFor();
    await result.getByText('查看本次要求',{exact:true}).click();
    if([5,6].includes(sequence)) {
      await page.waitForTimeout(50);
      assert.equal(await result.locator('.refinement-requirements li').count(),0,'mismatched hashes and malformed ranges never display a checked receipt');
    } else await result.locator('.refinement-requirements li').first().waitFor();
    assert.equal(await result.getByText('参数调整已核对',{exact:true}).count(),0,'image/mixed/preservation-only requests never claim geometry verification of the complete request');
  }
  await choose(9);
  await result.getByText('已生成，效果请对照要求',{exact:true}).waitFor();
  await result.getByText('查看本次要求',{exact:true}).click();
  await result.getByText('参数已应用，效果需核对',{exact:true}).waitFor();
  assert.equal(await result.getByText('参数调整已核对',{exact:true}).count(),0);
  await choose(14);
  await result.getByText('已生成，效果请对照要求',{exact:true}).waitFor();
  await result.getByText('查看本次要求',{exact:true}).click();
  await result.getByText('参数已应用，效果需核对',{exact:true}).waitFor();
  assert.equal(await result.getByText('参数调整已核对',{exact:true}).count(),0,'v3 numeric-only receipt must not claim physical geometry verification');
  for(const sequence of [10,11,12,13]) {
    await choose(sequence);await result.getByText('查看本次要求',{exact:true}).click();
    await page.waitForTimeout(50);
    assert.equal(await result.locator('.refinement-requirements li').count(),0,'duplicate sources/IDs and overlapping or incomplete scopes stay conservative');
    assert.equal(await result.getByText('参数调整已核对',{exact:true}).count(),0);
  }
  assert.deepEqual(errors,[]);assert.equal(calls.filter(c=>c.method!=='GET').length,0);
  console.log('PASS synthetic version-bound raw request disclosure, no semantic-success or new confirmation gate');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
