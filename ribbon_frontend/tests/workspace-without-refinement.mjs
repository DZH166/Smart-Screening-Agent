// Synthetic HTTP/browser contract: no external services or business images.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const {chromium}=createRequire(import.meta.url)(process.env.HSD_PLAYWRIGHT_MODULE || 'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url));
const image='/api/ribbon/synthetic-work.svg', svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520"><rect width="1200" height="520" fill="#e5eee8"/><circle cx="220" cy="250" r="120" fill="#e6aa76"/><text x="400" y="260">SYNTHETIC ONLY</text></svg>';
const profile={id:'fixture',version:2,name:'Synthetic current profile',width:1200,height:520,dpi:300,is_demo:true};
const styles=[{id:'classic',label:'经典等距',hint:'合成经典'},{id:'hierarchy',label:'主辅层级',hint:'合成主辅'},{id:'airy',label:'留白高级',hint:'合成留白'}];
function version(id,work,seq=0,parent=null){return {id,design_id:work,parent_version_id:parent,sequence:seq,prompt:seq?'NEVER DISPLAY THIS OLD EDIT REQUEST':'',render_kind:'layered',provider:'test',created_at:'2026-11-08',
  snapshot:{asset_refs:['pattern'],background_ref:'background',template_id:'grid',template_mode:'grid',template_version:1,pattern_slots:['slot-1'],layout_engine:'seamless-unit-v3',design_style:'classic',design_density:'balanced',background_tone:'original',params:{},output_profile:profile,
    edit_plan:{request_receipt:{protocol:'ribbon-request-v2',coverage:'checked'}},loop:{engine:'seamless-unit-v3',width:1200,height:520,status:'checked',issues:[],kind:'sequence'}},
  preview_url:image+'?version='+id,download_url:'/api/ribbon/versions/'+id+'/download'};}
const work=(id,versions)=>({id,name:'合成作品 '+id,current_version_id:versions.at(-1)?.id || null,successful_refinement_count:2,active_job_id:null,active_job:null,revision:0,versions});
const original=work('old',[version('old-0','old'),version('old-1','old',1,'old-0')]);
const other=work('other',[version('other-0','other')]);
const works=[original,other],jobs=new Map(),writes=[],reads=[],keys=new Map(),errors=[];
let next=0,legacyMode='ok', removeOnGenerate=false;
const starterAssets=[
 {id:'pattern',name:'合成图案',kind:'pattern',is_demo:true,shared:true,url:image},
 {id:'background',name:'合成底纹',kind:'background',is_demo:true,shared:true,url:image},
 {id:'demo-flower',name:'合成默认图案',kind:'pattern',is_demo:true,shared:true,url:image},
 {id:'demo-bg-sage',name:'合成默认底纹',kind:'background',is_demo:true,shared:true,url:image},
];
let assetCatalog=starterAssets;
const assetError='素材不存在、类型不符或无权使用';
const server=createServer(async(req,res)=>{
 const p=new URL(req.url,'http://localhost').pathname;
 const json=(v,status=200)=>{if(!res.destroyed){res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(v));}};
 try{
  if(p==='/'){let html=await readFile(path.join(root,'hsd_tool/static/index.html'),'utf8');html=html.replace('__HSD_TOKEN__',JSON.stringify('synthetic-token')).replace('__HSD_ACCESS__','{}').replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g,'');res.writeHead(200,{'Content-Type':'text/html'});res.end(html);return;}
  if(p.startsWith('/static/')){res.writeHead(200,{'Content-Type':p.endsWith('.webp')?'image/webp':p.endsWith('.css')?'text/css':'text/javascript'});res.end(await readFile(path.join(root,'hsd_tool',p)));return;}
  if(p===image || p.endsWith('/download')){res.writeHead(200,{'Content-Type':'image/svg+xml'});res.end(svg);return;}
  reads.push({method:req.method,path:p});
  let body={};if(req.method==='POST'){let raw='';for await(const chunk of req)raw+=chunk;body=JSON.parse(raw||'{}');writes.push({path:p,body});}
  if(p==='/api/ribbon/auth/me')return json({id:'synthetic-no-refine',username:'合成员工',role:'employee'});
  // Deliberately expose legacy capabilities: the frontend must never show edits.
  if(p==='/api/ribbon/config')return json({provider:'deepseek_seedream',ai_ready:true,ai_draft_available:true,output_profile:profile,max_refinements:2,editing:{allowed_operations:['parameters','edit_background']}});
  if(p==='/api/ribbon/assets')return json(assetCatalog);
  if(p==='/api/ribbon/templates')return json([{id:'grid',name:'整齐平铺',mode:'grid',version:1,enabled:true,thumbnail_url:image,rules:{}}]);
  if(p==='/api/ribbon/design-styles')return json(styles);
  if(p==='/api/ribbon/designs'){
   if(req.method==='POST'){const d=work('new-'+(++next),[]);d.name=body.name;works.push(d);return json(d);}
   return json(works.filter(w=>!w.deleted_at).map(w=>({...w,versions:[]})));
  }
  if(p==='/api/ribbon/candidates/one')return json({style:body.style,label:body.style,hint:'合成新作品试排',image:'data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64'),width:profile.width,height:profile.height});
  if(p.startsWith('/api/ribbon/jobs/by-request/')){
   if(legacyMode==='missing')return json({detail:'unknown'},404);
   if(legacyMode==='expired')return json({detail:'expired'},410);
   if(legacyMode==='unauthorized')return json({detail:'session expired'},401);
   const recovered={id:'legacy',design_id:legacyMode==='mismatch'?'other':'old',kind:legacyMode==='wrongkind'?'generate':'refine',status:'SUCCEEDED',phase:'completed',result_version_id:'old-1'};jobs.set(recovered.id,recovered);return json(recovered);
  }
  const match=/^\/api\/ribbon\/designs\/([^/]+)(?:\/(generate|rollback|refinements))?$/.exec(p);
  if(match){const d=works.find(w=>w.id===match[1]);if(!d)return json({detail:'missing'},404);
   if(match[2]==='refinements')throw new Error('FORBIDDEN: ribbon refinement requested');
   if(match[2]==='rollback'){assert.equal(body.expected_version_id,d.current_version_id);d.current_version_id=d.versions.find(v=>v.id===d.current_version_id).parent_version_id;return json(d);}
   if(match[2]==='generate'){
    if(removeOnGenerate){
     removeOnGenerate=false;
     assetCatalog=assetCatalog.filter(asset=>asset.id!=='draft-5');
    }
    const references=[...body.asset_ids.map(id=>[id,'pattern']),[body.background_id,'background'],
      ...Object.values(body.zone_background_refs||{}).map(id=>[id,'background']),
      ...(body.border_ref?[[body.border_ref,'pattern']]:[])];
    if(references.some(([id,kind])=>!assetCatalog.some(asset=>asset.id===id&&asset.kind===kind)))
     return json({detail:assetError,code:'asset_selection_unavailable'},404);
    let job=keys.get(body.idempotency_key);
    if(!job){assert.equal(d.current_version_id,null,'generate only targets a separate empty work');const v=version(d.id+'-v0',d.id);v.snapshot.design_style=body.design_style;d.versions.push(v);d.current_version_id=v.id;job={id:'job-'+d.id,design_id:d.id,kind:'generate',status:'SUCCEEDED',phase:'completed',result_version_id:v.id};keys.set(body.idempotency_key,job);jobs.set(job.id,job);}
    return json(job);
   }
   return json(d);
  }
  if(p.startsWith('/api/ribbon/jobs/'))return json(jobs.get(p.split('/').at(-1)));
  return json({detail:'synthetic route missing '+p},404);
 }catch(e){errors.push(String(e));json({detail:String(e)},500);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:process.env.HSD_BROWSER_CHANNEL||'chrome',headless:true});
const url='http://127.0.0.1:'+server.address().port+'/#ribbon';
async function checkAssetRecovery(){
 const patterns=Array.from({length:5},(_,index)=>({id:'draft-'+(index+1),name:'合成草稿图案 '+(index+1),
  kind:'pattern',is_demo:true,shared:true,url:image}));
 const valid=patterns.slice(0,4).map(asset=>asset.id), chosen=patterns.map(asset=>asset.id);
 const assetReads=()=>reads.filter(r=>r.method==='GET'&&r.path==='/api/ribbon/assets').length;
 const generations=()=>writes.filter(w=>w.path.endsWith('/generate'));
 const recoveryChecks=[];
 for(const scenario of ['stale-saved-selection','removed-after-catalog-read']){
  const staleSaved=scenario==='stale-saved-selection';
  const draft=work(scenario,[]);
  works.push(draft);
  assetCatalog=[...starterAssets,...(staleSaved?patterns.slice(0,4):patterns)];
  const page=await browser.newPage({viewport:{width:1366,height:768}});
  page.setDefaultTimeout(5000);
  page.on('pageerror',error=>errors.push(String(error)));
  try{
   const initialWrites=generations().length;
   let backgroundReads=0;
   await page.route('**/api/ribbon/jobs/asset-recovery-background',route=>{
    backgroundReads++;
    return staleSaved
     ? route.fulfill({status:404,json:{detail:'合成底图任务已过期'}})
     : route.fulfill({json:{id:'asset-recovery-background',kind:'background',status:'SUCCEEDED',result_asset_id:'expired-background-asset'}});
   });
   await page.addInitScript(({id,chosen})=>{
    localStorage.setItem('ribbon:synthetic-no-refine:design',JSON.stringify(id));
    localStorage.setItem('ribbon:synthetic-no-refine:backgroundJob',JSON.stringify('asset-recovery-background'));
    localStorage.setItem('ribbon:synthetic-no-refine:backgroundTarget',JSON.stringify({design_id:id}));
    localStorage.setItem('ribbon:synthetic-no-refine:selection',JSON.stringify({design_id:id,base_version_id:null,value:{
     asset_ids:chosen,background_id:'background',template_id:'grid',design_style:'hierarchy',background_tone:'soft',design_density:'balanced',
    }}));
   },{id:draft.id,chosen});
   await page.goto(url);
   await page.getByRole('heading',{name:draft.name,exact:true}).waitFor();
   const generate=page.getByRole('button',{name:'生成首稿',exact:true});
   await generate.waitFor();
   await page.getByText(staleSaved?/上次的底图任务已不可用/:/上次生成的底图已不可用/).waitFor();
   assert.equal(backgroundReads,1,'restore the prior background task only once');
   assert.deepEqual(await page.evaluate(()=>{
    const prefix='ribbon:synthetic-no-refine:';
    return [JSON.parse(localStorage.getItem(prefix+'backgroundJob')),
      JSON.parse(localStorage.getItem(prefix+'backgroundTarget')),
      JSON.parse(localStorage.getItem(prefix+'selection')).value.background_id];
   }),[null,null,'background'],'expired task/result cleanup preserves the currently selected valid background');
   assert.equal(generations().length,initialWrites,'startup recovery never submits a first draft');
   const initialReads=assetReads();
   if(!staleSaved){
    assert.equal(await page.locator('.selected-patterns .pattern-tile').count(),5);
    assert.equal(await generate.isEnabled(),true);
    // The catalog was valid when rendered. Invalidate only when the next
    // generate request reaches the server so this exercises the race/404.
    removeOnGenerate=true;
    await generate.click();
   }
   const notice=page.getByText(/所选素材有变动/).first();
   await notice.waitFor();
   const remove=page.getByRole('button',{name:'移除不可用素材',exact:true});
   const refresh=page.getByRole('button',{name:'刷新素材库',exact:true});
   await remove.waitFor();await refresh.waitFor();
   assert.equal(await generate.isEnabled(),false,'unavailable selections block generate until the employee changes them');
   await page.locator('.selected-patterns').getByText(/不可用/).first().waitFor();
   const beforeRecovery=initialWrites+(staleSaved?0:1);
   assert.equal(generations().length,beforeRecovery,'catalog recovery cannot silently replay generation');
   if(!staleSaved)assert.ok(assetReads()>initialReads,'the typed 404 refreshes the current catalog');
   const beforeRefresh=assetReads();
   await Promise.all([page.waitForResponse(r=>r.request().method()==='GET' && new URL(r.url()).pathname==='/api/ribbon/assets'),refresh.click()]);
   assert.ok(assetReads()>beforeRefresh,'manual refresh reads the catalog again');
   assert.equal(generations().length,beforeRecovery,'manual catalog refresh cannot generate');
   await remove.click();
   assert.equal(await page.locator('.selected-patterns .pattern-tile').count(),4);
   await generate.click();
   await page.getByRole('link',{name:'下载循环单元',exact:true}).waitFor();
   const accepted=generations().at(-1).body;
   assert.equal(generations().length,beforeRecovery+1);
   assert.deepEqual(accepted.asset_ids,valid,'preserve the other four selected patterns in order');
   assert.equal(accepted.background_id,'background');
   assert.equal(accepted.template_id,'grid');
   assert.equal(accepted.design_style,'hierarchy');
   assert.equal(accepted.background_tone,'soft');
   recoveryChecks.push({scenario,background_recovery:staleSaved?'expired_job_cleared':'unavailable_result_not_selected',valid_choices_preserved:true,no_automatic_resubmit:true});
  }finally{
   removeOnGenerate=false;
   await page.close();
  }
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({source:'synthetic_asset_recovery',checks:recoveryChecks,real_model_calls:0}));
}
async function assertNoRefinement(page){
 assert.equal(await page.locator('.refinement-panel,#refinement,.refinement-result,.target-overlay,.remaining-edits').count(),0);
 const text=await page.locator('#ribbon-mount').evaluate(el=>el.shadowRoot.textContent);
 assert.equal(/精修|NEVER DISPLAY THIS OLD EDIT REQUEST/.test(text),false);
 assert.equal(writes.some(w=>w.path.endsWith('/refinements')),false);
}
async function checkLocalPolicyRecovery(){
 const generatePath=id=>'/api/ribbon/designs/'+id+'/generate';
 const chosen={asset_ids:['pattern','demo-flower'],background_id:'background',template_id:'grid',
  design_style:'hierarchy',background_tone:'soft',design_density:'balanced'};
 const policyText='AI 搭配结果未通过审核';
 const failures=[
  {id:'output-policy',error:'合成审核失败',recovery_action:'compose_locally'},
  {id:'provider-failure',error:'合成服务暂时不可用'},
  {id:'unknown-outcome',error:'合成调用结果未确认'},
 ];
 for(const failure of failures){
  const {id,error,recovery_action}=failure;
  const draft=work(id,[]), jobId='ai-'+id, submitted=[];
  works.push(draft);
  const beforeWorks=works.length, beforeCreates=writes.filter(write=>write.path==='/api/ribbon/designs').length;
  const page=await browser.newPage({viewport:{width:1366,height:768}});
  page.setDefaultTimeout(8000);
  page.on('pageerror',e=>errors.push(String(e)));
  try{
   await page.addInitScript(({id,chosen})=>{
    const prefix='ribbon:synthetic-no-refine:';
    if(!localStorage.getItem(prefix+'design'))localStorage.setItem(prefix+'design',JSON.stringify(id));
    if(!localStorage.getItem(prefix+'selection'))
     localStorage.setItem(prefix+'selection',JSON.stringify({design_id:id,base_version_id:null,value:chosen}));
   },{id,chosen});
   const referenceImage='/api/ribbon/layout-examples/synthetic/image';
   await page.route('**'+referenceImage,route=>route.fulfill({contentType:'image/svg+xml',body:svg}));
   await page.route('**/api/ribbon/layout-examples',route=>route.fulfill({json:{
    modes:[{mode:'grid',name:'整齐平铺',summary:'合成排版',note:'合成说明',example_ids:['synthetic']}],
    examples:[{id:'synthetic',title:'合成案例',code:'QA-SYNTHETIC',description:'合成测试',
     look_for:'等距',mode_tags:['grid'],reference_only:false,width:1200,height:520,image_url:referenceImage,
     available:true,mode_notes:{grid:{look_for:'等距',difference:'合成对照',fit:'direct'}}}],
    source_name:'合成素材',note:'仅用于测试',
   }}));
   let loseLocalResponse=true;
   await page.route('**'+generatePath(id),async route=>{
    const body=route.request().postDataJSON();
    submitted.push(body);
    if(body.ai_assisted){
     const queued={id:jobId,design_id:id,kind:'generate',status:'QUEUED',phase:'queued'};
     jobs.set(jobId,queued);
     draft.active_job_id=jobId;
     draft.active_job=queued;
     return route.fulfill({json:queued});
    }
    if(loseLocalResponse){
     loseLocalResponse=false;
     await route.fetch();
     return route.abort('connectionreset');
    }
    return route.continue();
   });
   await page.goto(url);
   await page.getByRole('heading',{name:draft.name,exact:true}).waitFor();
   const aiOption=page.getByRole('checkbox',{name:'AI搭配底纹与装饰',exact:true});
   const selectReference=async()=>{
    await page.getByRole('button',{name:'选择案例参考',exact:true}).click();
    await page.getByRole('button',{name:'用于AI首稿参考',exact:true}).click();
    await page.getByRole('button',{name:'取消案例参考',exact:true}).waitFor();
   };
   if(recovery_action)await selectReference();
   const local=page.getByRole('button',{name:'改用本地合成',exact:true});
   const generate=page.getByRole('button',{name:'生成首稿',exact:true});
   await generate.click();
   await page.getByRole('button',{name:'正在生成…',exact:true}).waitFor();
   assert.equal(submitted.length,1);
   assert.equal(submitted[0].ai_assisted,true);
   if(recovery_action)assert.equal(submitted[0].reference_code,'QA-SYNTHETIC');
   assert.equal(await local.count(),0,'a queued AI attempt never offers local recovery');
   jobs.set(jobId,{id:jobId,design_id:id,kind:'generate',status:'FAILED',phase:'failed',error,recovery_action});
   Object.assign(draft,{active_job_id:null,active_job:null,recovery_action});
   if(recovery_action){
    await page.getByText(policyText,{exact:true}).waitFor();
    await local.waitFor();
    assert.equal(await aiOption.isChecked(),true,'the failed AI job never changes the chosen mode');
    await page.reload();
    await page.getByRole('heading',{name:draft.name,exact:true}).waitFor();
    await local.waitFor();
    await selectReference();
    assert.equal(submitted.length,1,'failed/reopened draft recovery waits for an explicit click');
    await local.click();
    const recover=page.getByRole('button',{name:'恢复提交',exact:true});
    await recover.waitFor();
    assert.equal(await local.count(),0,'uncertain local receipt is recovered using its existing key');
    assert.equal(submitted.length,2);
    const [ai,firstLocal]=submitted;
    assert.notEqual(firstLocal.idempotency_key,ai.idempotency_key);
    assert.deepEqual(firstLocal,{...ai,idempotency_key:firstLocal.idempotency_key,ai_assisted:false,reference_code:null},
     'local recovery only changes the request key, AI mode and case reference');
    for(const [field,value] of Object.entries(chosen))assert.deepEqual(firstLocal[field],value);
    await recover.click();
    await page.getByRole('link',{name:'下载循环单元',exact:true}).waitFor();
    assert.equal(submitted.length,3);
    assert.deepEqual(submitted[2],firstLocal,'a lost local receipt reuses the identical request');
    assert.equal(draft.versions.length,1);
    assert.equal(await local.count(),0);
   }else{
    await page.getByText(error,{exact:true}).waitFor();
    assert.equal(await local.count(),0,'unrelated or uncertain provider failure cannot offer local recovery');
    assert.equal(await page.getByText(policyText,{exact:true}).count(),0);
    assert.equal(submitted.length,1);
   }
   assert.equal(works.length,beforeWorks);
   assert.equal(writes.filter(write=>write.path==='/api/ribbon/designs').length,beforeCreates,
    'never create a different work for local recovery');
  }finally{
   await page.close();
  }
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({source:'synthetic_local_policy_recovery',checks:['terminal-and-reopened-draft',
  'explicit-local-same-draft-and-selection','lost-local-receipt-same-key','ordinary-and-unknown-no-offer'],real_model_calls:0}));
}
async function choose(page,id){await page.getByRole('button',{name:'我的作品',exact:false}).click();await page.locator('.design-list-item').filter({has:page.getByText('合成作品 '+id,{exact:true})}).click();await page.getByRole('heading',{name:'合成作品 '+id,exact:true}).waitFor();}
try{
 const page=await browser.newPage({viewport:{width:1366,height:768}});page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(url);await page.getByRole('heading',{name:'合成作品 old',exact:true}).waitFor();
 await assertNoRefinement(page);
 if(process.argv.includes('--asset-recovery-only')){
  await page.close();
  await checkAssetRecovery();
 }else if(process.argv.includes('--local-policy-recovery-only')){
  await page.close();
  await checkLocalPolicyRecovery();
 }else if(process.argv.includes('--creation-fence-only')){
  await page.close();
  for(const trigger of ['generate','newDesign']){
   const p=await browser.newPage({viewport:{width:1366,height:768}});await p.goto(url);
   await p.getByRole('heading',{name:'合成作品 old',exact:true}).waitFor();
   await p.locator('.style-chips button').filter({hasText:'主辅层级'}).click();
   await p.locator('.background-prompt-box > summary').click();await p.locator('#background-prompt').fill('创建结果未知也保留底图输入');
   const beforeCreate=writes.filter(w=>w.path==='/api/ribbon/designs').length;
   let once=true;await p.route('**/api/ribbon/designs',async route=>{if(route.request().method()==='POST'&&once){once=false;await route.fetch();return route.abort('connectionreset');}return route.continue();});
   await p.getByRole('button',{name:trigger==='generate'?'生成新作品':'新建作品',exact:true}).click();
   await p.getByText('作品可能已经建立，暂不重复创建。请打开“我的作品”，刷新后选择要继续的作品。',{exact:true}).waitFor();
   assert.equal(writes.filter(w=>w.path==='/api/ribbon/designs').length,beforeCreate+1);
   const accepted=works.at(-1), generatedBefore=writes.filter(w=>w.path.endsWith('/generate')).length;
   for(let i=0;i<3;i++)await p.locator('.generation-button').evaluate(button=>button.click());
   assert.equal(await p.getByRole('button',{name:'新建作品',exact:true}).isEnabled(),false);
   assert.equal(writes.filter(w=>w.path==='/api/ribbon/designs').length,beforeCreate+1);
   if(trigger==='generate')await p.evaluate(()=>localStorage.removeItem('ribbon:synthetic-no-refine:design'));
   await p.reload();await p.getByText('作品可能已经建立，暂不重复创建。请打开“我的作品”，刷新后选择要继续的作品。',{exact:true}).waitFor();
   await p.locator('.generation-button').waitFor();assert.equal(await p.locator('.generation-button').isEnabled(),false,'reload cannot clear unknown-creation fence');
   if(trigger==='generate')assert.equal(await p.locator('a[download]').count(),0,'without an explicit saved work, initialization cannot claim the first list row');
   assert.equal(await p.locator('.style-chips button').filter({hasText:'主辅层级'}).getAttribute('aria-pressed'),'true');
   assert.equal(await p.locator('#background-prompt').inputValue(),'创建结果未知也保留底图输入');
   await p.getByRole('button',{name:'我的作品',exact:false}).click();
   await p.getByText('正在更新作品列表…',{exact:true}).waitFor({state:'detached'});
   assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('ribbon:synthetic-no-refine:creationUncertain'))),true,'list refresh does not claim any work');
   await p.locator('.design-list-item').filter({has:p.getByText(accepted.name,{exact:true})}).click();
   await p.getByText('作品可能已经建立，暂不重复创建。请打开“我的作品”，刷新后选择要继续的作品。',{exact:true}).waitFor({state:'detached'});
   await p.getByRole('button',{name:'生成首稿',exact:true}).waitFor();
   assert.equal(await p.locator('.style-chips button').filter({hasText:'主辅层级'}).getAttribute('aria-pressed'),'true');
   await p.getByRole('button',{name:'生成首稿',exact:true}).click();await p.getByRole('button',{name:'生成新作品',exact:true}).waitFor();
   assert.equal(writes.filter(w=>w.path==='/api/ribbon/designs').length,beforeCreate+1,'recovery never creates another empty work');
   assert.equal(writes.filter(w=>w.path.endsWith('/generate')).length,generatedBefore+1);
   assert.equal(writes.findLast(w=>w.path.endsWith('/generate')).path,`/api/ribbon/designs/${accepted.id}/generate`);
   await p.close();
  }
  // Definite rejection is not an unknown accepted creation. Timeout/5xx are.
  for(const status of [401,403,422,408,503]){
   const p=await browser.newPage();await p.goto(url);await p.getByRole('heading',{name:'合成作品 old',exact:true}).waitFor();
   await p.route('**/api/ribbon/designs',route=>route.request().method()==='POST'?route.fulfill({status,contentType:'application/json',body:JSON.stringify({detail:'Synthetic rejection '+status})}):route.continue());
   await p.getByRole('button',{name:'新建作品',exact:true}).click();
   if([408,503].includes(status)){await p.getByRole('button',{name:'查看作品',exact:true}).waitFor();assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('ribbon:synthetic-no-refine:creationUncertain'))),true);}
   else{await p.getByText('Synthetic rejection '+status,{exact:true}).waitFor();assert.notEqual(await p.evaluate(()=>JSON.parse(localStorage.getItem('ribbon:synthetic-no-refine:creationUncertain'))),true);}
   await p.close();
  }
  legacyMode='wrongkind';const p=await browser.newPage();
  await p.addInitScript(()=>{localStorage.setItem('ribbon:synthetic-no-refine:design',JSON.stringify('old'));localStorage.setItem('ribbon:synthetic-no-refine:pending',JSON.stringify({path:'/designs/old/refinements',body:{idempotency_key:'old-job-key'},kind:'design',designId:'old'}));});
  await p.goto(url);await p.getByRole('button',{name:'重试读取任务',exact:true}).click();
  await p.getByText('旧任务类型或作品不一致，请刷新作品列表查看。',{exact:true}).waitFor();
  assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('ribbon:synthetic-no-refine:pending'))),null);
  assert.equal(writes.some(w=>w.path.endsWith('/refinements')),false);await p.close();assert.deepEqual(errors,[]);
  console.log(JSON.stringify({source:'synthetic_creation_guard_only',checks:['both-create-entry-fences','accepted-lost-create-no-duplicate-post','fence-and-input-survive-reload','no-default-list-claim-or-refresh-clear','explicit-empty-work-uses-original-id-once','401/403/422-rejection-vs-408/503-unknown','wrong-legacy-kind-rejected'],real_model_calls:0}));
 }else if(process.argv.includes('--screenshots-only')){
  const out=path.join(root,'tmp','ribbon-refinement-retired');await mkdir(out,{recursive:true});
  for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
   await page.setViewportSize(size);await page.locator('.loop-unit-view img').evaluate(img=>img.decode());
   await page.screenshot({path:path.join(out,`synthetic-two-column-${size.width}.png`),fullPage:false});
   const action=await page.getByRole('button',{name:'生成新作品',exact:true}).boundingBox();assert.ok(action.y+action.height<size.height);
  }
  console.log('PASS final synthetic 1366/1920 screenshots; main generation control stays visible');
 }else{
 await page.locator('.history-panel > summary').click();
 await page.locator('.version-card').filter({hasText:'首稿'}).click();
 assert.equal(await page.getByRole('link',{name:'下载所选版本',exact:true}).getAttribute('href'),'/api/ribbon/versions/old-0/download');
 await page.getByRole('button',{name:'返回当前版本',exact:true}).click();
 await page.getByRole('button',{name:'回退上一版',exact:true}).click();
 await page.locator('.stage-topline').filter({hasText:'V0'}).waitFor();
 assert.equal(original.current_version_id,'old-0');assert.equal(original.versions.length,2);
 const style=page.locator('.style-chips button').filter({hasText:'主辅层级'});await style.click();
 await page.reload();await page.getByRole('heading',{name:'合成作品 old',exact:true}).waitFor();
 assert.equal(await style.getAttribute('aria-pressed'),'true','new-work selections survive reload');
 await page.locator('.trial-box > summary').click();await page.getByRole('button',{name:/^试排这/}).click();
 await page.locator('.candidate-gallery img').nth(2).waitFor();
 assert.equal(reads.filter(r=>r.path.endsWith('/candidates/one')).every(r=>r.path==='/api/ribbon/candidates/one'),true,'new-work trials use current default profile, not historic work');
 await page.getByRole('button',{name:'收起试排',exact:true}).click();
 const oldVersions=JSON.stringify(original.versions),before=works.length;
 await page.getByRole('button',{name:'生成新作品',exact:true}).click();
 await page.locator('.stage-topline').filter({hasText:'V0'}).waitFor();
 await page.waitForFunction(()=>document.querySelector('#ribbon-mount').shadowRoot.querySelector('.preview-panel h2')?.textContent?.startsWith('丝带设计'));
 assert.equal(works.length,before+1);assert.equal(JSON.stringify(original.versions),oldVersions);
 const generated=writes.findLast(w=>w.path.endsWith('/generate'));
 assert.equal(generated.path,'/api/ribbon/designs/new-1/generate');assert.equal(generated.body.design_style,'hierarchy');assert.equal(generated.body.ai_assisted,true);
 assert.equal('prompt' in generated.body,false);assert.equal('base_version_id' in generated.body,false);
 // Accepted generation with a lost response: retain and recover the same key.
 let loseResponse=true;
 await page.route('**/api/ribbon/designs/*/generate',async route=>{if(loseResponse){loseResponse=false;await route.fetch();return route.abort('connectionreset');}return route.continue();});
 await page.getByRole('button',{name:'生成新作品',exact:true}).click();
 await page.getByRole('button',{name:'恢复提交',exact:true}).waitFor();
 const lost=writes.findLast(w=>w.path.endsWith('/generate'));await page.getByRole('button',{name:'恢复提交',exact:true}).click();
 await page.getByRole('button',{name:'恢复提交',exact:true}).waitFor({state:'detached'});
 assert.equal(writes.findLast(w=>w.path.endsWith('/generate')).body.idempotency_key,lost.body.idempotency_key);
 assert.equal(works.length,before+2);assert.equal(works.at(-1).versions.length,1);
 await assertNoRefinement(page);
 for(const size of [{width:1366,height:768},{width:1920,height:1080}]){
  await page.setViewportSize(size);await page.evaluate(()=>window.scrollTo(0,0));
  const box=await page.getByRole('button',{name:'生成新作品',exact:true}).boundingBox();assert.ok(box.y>=0 && box.y+box.height<size.height,'generation is visible without scrolling');
  const columns=await page.locator('.workspace-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' '));assert.equal(columns.length,2);assert.ok(parseFloat(columns[1])>parseFloat(columns[0]));
 }
 await page.evaluate(()=>document.querySelector('#ribbon-mount').style.zoom='1.15');
 const enlarged=await page.getByRole('button',{name:'生成新作品',exact:true}).boundingBox();assert.ok(enlarged.width>100 && enlarged.height>35);
 const out=path.join(root,'tmp','ribbon-refinement-retired');await mkdir(out,{recursive:true});await page.screenshot({path:path.join(out,'synthetic-two-column-1920.png'),fullPage:false});
 // Empty works still generate a first draft through the same public endpoint.
 await page.getByRole('button',{name:'新建作品',exact:true}).click();await page.getByRole('button',{name:'生成首稿',exact:true}).waitFor();
 const count=works.length;await page.getByRole('button',{name:'生成首稿',exact:true}).click();await page.getByRole('button',{name:'生成新作品',exact:true}).waitFor();assert.equal(works.length,count);
 await page.close();
 // Stored old requests can only read existing jobs, never replay the old POST.
 for(const mode of ['ok','disconnect','missing','expired','mismatch','unauthorized']){
  legacyMode=mode==='disconnect'?'ok':mode;const p=await browser.newPage({viewport:{width:1366,height:768}});
  await p.addInitScript(()=>{localStorage.setItem('ribbon:synthetic-no-refine:design',JSON.stringify('old'));localStorage.setItem('ribbon:synthetic-no-refine:pending',JSON.stringify({path:'/designs/old/refinements',body:{idempotency_key:'legacy-key',prompt:'must never resend'},kind:'design',designId:'old'}));});
  if(mode==='disconnect'){let once=true;await p.route('**/api/ribbon/jobs/by-request/*',route=>{if(once){once=false;return route.abort('connectionreset');}return route.continue();});}
  await p.goto(url);await p.getByRole('heading',{name:'合成作品 old',exact:true}).waitFor();
  await p.getByRole('button',{name:'重试读取任务',exact:true}).click();
  if(mode==='disconnect'){await p.getByText(/暂时无法读取旧任务状态/).waitFor();await p.getByRole('button',{name:'重试读取任务',exact:true}).click();}
  await p.getByRole('button',{name:'重试读取任务',exact:true}).waitFor({state:'detached'});
  if(mode==='mismatch')await p.getByText('旧任务类型或作品不一致，请刷新作品列表查看。',{exact:true}).waitFor();
  if(['missing','expired'].includes(mode))await p.getByText(/旧任务不存在或已过期/).waitFor();
  if(mode==='unauthorized')assert.equal(await p.evaluate(()=>!!JSON.parse(localStorage.getItem('ribbon:synthetic-no-refine:pending'))),true,'expired login retains read-only recovery key');
  await assertNoRefinement(p);await p.close();
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({source:'synthetic_http_browser',checks:['no-edit-UI-or-posts','old-version-download-and-rollback','new-work-not-overwrite','selection-reload','new-profile-trial','lost-generate-idempotency','first-draft','legacy-read-only-recovery-and-owner-check','1366/1920/115%-layout'],real_model_calls:0}));
 }
}catch(e){console.error(JSON.stringify({writes,errors}));throw e;}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}

