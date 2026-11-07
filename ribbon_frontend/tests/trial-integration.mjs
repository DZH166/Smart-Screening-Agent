// Synthetic local HTTP/UI integration. No credentials, business images or models.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.HSD_PLAYWRIGHT_MODULE || 'playwright');
const root=fileURLToPath(new URL('../../',import.meta.url));
const image='/api/ribbon/synthetic-trial.svg';
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="520"><rect width="1200" height="520" fill="#dceadd"/><text x="100" y="200">SYNTHETIC ONLY</text></svg>';
const profile={id:'fixture',version:1,name:'Synthetic',width:1200,height:520,dpi:300,is_demo:true};
const styles=[{id:'classic',label:'经典等距',hint:'合成经典'},{id:'hierarchy',label:'主辅层级',hint:'合成主辅'},{id:'airy',label:'留白高级',hint:'合成留白'}];
const selection={asset_refs:['pattern'],background_ref:'background',template_id:'grid',template_mode:'grid',template_version:1,
  pattern_slots:['slot-1'],layout_engine:'seamless-unit-v3',design_style:'classic',design_density:'balanced',background_tone:'original',params:{},output_profile:profile,
  loop:{engine:'seamless-unit-v3',width:1200,height:520,status:'checked',issues:[],kind:'sequence'}};
const works=['A','B'].map(id=>({id,name:'合成作品 '+id,current_version_id:'v-'+id,successful_refinement_count:0,active_job_id:null,revision:0,active_job:null,
  versions:[{id:'v-'+id,design_id:id,parent_version_id:null,sequence:0,prompt:'',render_kind:'layered',provider:'test',created_at:'2026-11-07',snapshot:structuredClone(selection),
    preview_url:image+'?work='+id,download_url:'/api/ribbon/versions/v-'+id+'/download'}]}));
let hold=null, release=null, scope="A";
const calls=[],writes=[],jobs=new Map();
const server=createServer(async(req,res)=>{
  const p=new URL(req.url,'http://localhost').pathname;
  const json=(v,status=200)=>{if(!res.destroyed){res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(v));}};
  try {
    if(p==='/') {let html=await readFile(path.join(root,'hsd_tool/static/index.html'),'utf8');
      html=html.replace('__HSD_TOKEN__',JSON.stringify('synthetic-token')).replace('__HSD_ACCESS__','{}').replace(/\s*<script src="\/static\/(?:app|ai-settings)\.js" defer><\/script>/g,'');
      res.writeHead(200,{'Content-Type':'text/html'});res.end(html);return;}
    if(p.startsWith('/static/')){res.writeHead(200,{'Content-Type':p.endsWith('.webp')?'image/webp':p.endsWith('.css')?'text/css':'text/javascript'});res.end(await readFile(path.join(root,'hsd_tool',p)));return;}
    if(p===image || p.endsWith('/download')) {res.writeHead(200,{'Content-Type':'image/svg+xml'});res.end(svg);return;}
    if(p==='/api/ribbon/auth/me')return json({id:'synthetic-trial',username:'合成员工',role:'employee'});
    if(p==='/api/ribbon/config')return json({provider:'test',auth_mode:'demo',ai_ready:true,output_profile:profile,max_refinements:2});
    if(p==='/api/ribbon/assets')return json([{id:'pattern',name:'合成图案',kind:'pattern',is_demo:true,shared:true,url:image},{id:'background',name:'合成底纹',kind:'background',is_demo:true,shared:true,url:image}]);
    if(p==='/api/ribbon/templates')return json([{id:'grid',name:'整齐平铺',mode:'grid',version:1,enabled:true,thumbnail_url:image,rules:{}}]);
    if(p==='/api/ribbon/design-styles')return json(styles);
    if(p==='/api/ribbon/designs')return json(works);
    const candidate=p==='/api/ribbon/candidates/one' ? [p,scope] : null;
    if(candidate){let text='';for await(const part of req)text+=part;const body=JSON.parse(text);calls.push({id:candidate[1],...body});
      assert.equal(req.headers['x-hsd-token'],'synthetic-token');
      if(hold===candidate[1]+':'+body.style)await new Promise(resolve=>{release=resolve;});
      return json({style:body.style,label:candidate[1]+' '+body.style,hint:'合成试排',image:'data:image/svg+xml;base64,'+Buffer.from(svg).toString('base64'),width:1200,height:520});}
    const design=/^\/api\/ribbon\/designs\/([^/]+)$/.exec(p);
    if(design){const work=works.find(w=>w.id===design[1]);return work ? json(work) : json({detail:'missing'},404);}
    if(p.startsWith('/api/ribbon/jobs/'))return json(jobs.get(p.split('/').at(-1)));
    return json({detail:'synthetic route missing'},404);
  }catch(error){json({detail:String(error)},500);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:process.env.HSD_BROWSER_CHANNEL || 'chrome',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  // Simulate a transport that delivers a late response even after cancellation.
  await page.addInitScript(()=>{const original=window.fetch.bind(window);window.fetch=(input,init={})=>String(input).includes('/candidates/one')?original(input,{...init,signal:undefined}):original(input,init);});
  await page.goto('http://127.0.0.1:'+server.address().port+'/#ribbon');
  await page.getByRole('heading',{name:'合成作品 A',exact:true}).waitFor();
  const style=id=>page.locator('.style-chips button').filter({hasText:styles.find(s=>s.id===id).label});
  const run=()=>page.getByRole('button',{name:/^试排这/});
  const choose=async id=>{scope=id;await page.getByRole('button',{name:'我的作品',exact:false}).click();await page.locator('.design-list-item').filter({has:page.getByText('合成作品 '+id,{exact:true})}).click();await page.getByRole('heading',{name:'合成作品 '+id,exact:true}).waitFor();};
  await style('hierarchy').click();
  assert.equal(await style('hierarchy').getAttribute('aria-pressed'),'true');
  assert.equal(await page.getByRole('button',{name:'生成新作品',exact:true}).isEnabled(),true,'style-only change can create a separate work');
  await page.reload();
  await page.getByRole('heading',{name:'合成作品 A',exact:true}).waitFor();
  assert.equal(await style('hierarchy').getAttribute('aria-pressed'),'true','unsaved employee style survives reload');
  await page.locator('.trial-box > summary').click();
  hold='A:hierarchy';
  await run().click();
  await page.locator('.candidate-gallery img').first().waitFor();
  await page.locator('.trial-progress[aria-valuenow="1"]').waitFor();
  assert.equal(calls.filter(c=>c.id==='A').length,2,'one request per style, second is in flight');
  await choose('B');
  hold=null;release?.();release=null;
  await page.waitForTimeout(100);
  assert.equal(await page.locator('.candidate-gallery').count(),0,'old-work candidate cannot enter the selected work');
  assert.equal(calls.filter(c=>c.id==='A').length,2,'cancelled queue never sends the remaining old-work style');
  await page.locator('.trial-box > summary').click();
  await page.locator('.trial-chips button').filter({hasText:'留白高级'}).click();
  await run().click();
  await page.locator('.candidate-gallery img').nth(1).waitFor();
  await page.locator('.trial-progress').waitFor({state:'detached'});
  assert.deepEqual(calls.filter(c=>c.id==='B').map(c=>c.style),['classic','hierarchy'],'employees retain their chosen trial styles');
  await page.getByRole('button',{name:'收起试排',exact:true}).click();
  await page.locator('.trial-box > summary').click();
  hold='B:classic';
  await run().click();
  await page.locator('.trial-progress').waitFor();
  await page.getByRole('combobox',{name:'画面密度',exact:true}).selectOption('airy');
  hold=null;release?.();release=null;
  await page.waitForTimeout(100);
  assert.equal(await page.locator('.candidate-gallery').count(),0,'selection change clears old trial results');
  assert.equal(calls.filter(c=>c.id==='B').length,3,'selection change stops the remaining old-selection queue');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({source:'synthetic_http_browser',checks:['new-work-style-selection','unsaved-style-reload','progressive-trial','employee-style-choice','stale-work-and-selection'],requests:calls.length,real_model_calls:0}));
}finally{hold=null;release?.();await browser.close();await new Promise(resolve=>server.close(resolve));}
