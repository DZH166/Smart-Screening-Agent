// Pure rendering checks; no browser, server or network access is used.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = new Map();
const document = {
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, {addEventListener(){}, classList:{toggle(){},add(){}}});
    return nodes.get(id);
  },
  dispatchEvent(){},
};
const sandbox = {document, window:{}, AbortController, setTimeout, clearTimeout,
  CustomEvent:class {}, fetch:async()=>({ok:true,json:async()=>({configured:false,enabled:false})})};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../hsd_tool/static/ai-settings.js'),'utf8'),sandbox);
const {rowHtml,usageText,retrievalHtml} = sandbox.window.HSDAI;
const review = {verdict:'same',candidate_id:'f<1',outcome:'auto_passed',
  reason:'图案说明'.repeat(40)+'<script>unsafe</script>', differences:['<extra>'],
  gate_failures:[{code:'validation_required',reason:'资格未完成'},
    {code:'coverage_not_verified',reason:'覆盖不足'},{code:'coverage_not_verified',reason:'覆盖不足'},
    {code:'local_evidence_conflict',reason:'本地图案或颜色证据仍有差异'}],
  protocol_diagnostics:{inconsistent:true}, checks:{content_same:true}};
const html = rowHtml({status:'review',ai_review:review},'a" onmouseover="bad','other');
const visible = html.slice(0,html.indexOf('<details'));
assert.ok(!html.includes('条件验证后自动通过'));
assert.ok(visible.includes('AI 建议相同 · 需人工确认'));
assert.ok(visible.includes('（与当前选择不同）'));
assert.ok(visible.includes('AI 复核对象：a&quot; onmouseover=&quot;bad'));
assert.ok(visible.includes('data-candidate-id="f&lt;1"'));
assert.ok(!html.includes('<script>') && !html.includes('<extra>'));
assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
assert.ok(!html.includes('<details open'));
assert.ok(html.includes('data-detail-key="ai-review"'));
assert.equal((html.match(/<li>覆盖不足<\/li>/g)||[]).length,1);
assert.ok(visible.includes('模型回答存在矛盾'));
assert.ok(visible.includes('本地检测到图案或颜色差异'));
assert.ok(html.indexOf('资格未完成') > html.indexOf('<details'));
assert.ok(html.indexOf('图案内容相同：认为满足') > html.indexOf('<details'));
assert.equal(rowHtml({status:'auto'},'',null),'');

// The model's verdict and outcome cannot override the server's final status.
const plain = {verdict:'same',candidate_id:'f1',outcome:'evaluation_suggestion',reason:'图案和颜色一致。'};
assert.ok(rowHtml({status:'auto',ai_review:plain},'first.ai','f1').includes('需人工确认'));
const auto = rowHtml({status:'auto',ai_review:{...plain,outcome:'auto_passed'}},'first.ai','f1');
assert.ok(auto.includes('条件验证后自动通过'));
assert.ok(!auto.includes('需人工确认'));
const confirmed = rowHtml({status:'confirmed',ai_review:plain},'first.ai','f1');
assert.ok(confirmed.includes('AI 建议相同 · 本项已由员工确认'));
assert.ok(!confirmed.includes('需人工确认') && !confirmed.includes('条件验证后自动通过'));
const skipped = rowHtml({status:'skipped',ai_review:plain},'first.ai','f1');
assert.ok(skipped.includes('AI 建议相同 · 本项已跳过'));
assert.ok(!skipped.includes('需人工确认'));

// Same-object filenames remain in details; a changed selection is explicit.
const sameObject = rowHtml({status:'review',ai_review:plain},'first.ai','f1');
assert.ok(!sameObject.slice(0,sameObject.indexOf('<details')).includes('first.ai'));
assert.ok(sameObject.includes('复核对象：first.ai'));
assert.ok(!sameObject.includes('data-candidate-id='));
const mismatch = rowHtml({status:'review',ai_review:plain},'first.ai','f2');
assert.ok(mismatch.indexOf('复核对象：first.ai') < mismatch.indexOf('<details'));
assert.ok(mismatch.includes('data-candidate-id="f1"'));

// Specific differences remain visible in full after the former 64-character
// cut-off, and duplicate differences do not repeat.
const difference = '左侧蓝色条纹相同，但是右侧中间有一处红色花瓣与表格中的黄色花瓣不同。'.repeat(3)+'末端还有新增圆点';
const different = rowHtml({status:'review',ai_review:{...plain,verdict:'different',
  reason:'这里有详细比较说明。',differences:[difference,difference]}},'first.ai','f1');
const differentVisible = different.slice(0,different.indexOf('<details'));
assert.ok(differentVisible.includes('AI 发现差异 · 需人工确认'));
assert.ok(differentVisible.includes(difference));
assert.equal((different.match(/末端还有新增圆点/g)||[]).length,1);
assert.ok(!differentVisible.includes('这里有详细比较说明'));
assert.ok(different.includes('这里有详细比较说明'));

const failed = rowHtml({status:'review',ai_review:{outcome:'error',reason:'网络连接失败，请人工确认。'}},'',null);
assert.ok(failed.includes('AI 复核未完成 · 需人工确认'));
assert.ok(failed.includes('网络连接失败'));
const protocolGate = rowHtml({status:'review',ai_review:{...plain,
  gate_failures:[{code:'model_protocol_inconsistent',reason:'协议矛盾'}]}},'first.ai','f1');
assert.ok(protocolGate.indexOf('模型回答存在矛盾') < protocolGate.indexOf('<details'));
const stale = rowHtml({status:'review',ai_review:{...plain,reason_code:'source_changed'}},'first.ai','f1');
assert.ok(stale.indexOf('复核图片或原文件已变化') < stale.indexOf('<details'));

// Retrieval is a candidate suggestion, separate from pair review and its five
// checks / independent qualification. A model's "same" is never acceptance.
assert.equal(retrievalHtml({status:'review'},'',null),'');
const retrieval={candidate_id:'retrieval<1',verdict:'same',reason:'图案主体接近，需要本机继续核验。',outcome:'suggestion'};
const retrievalSuggestion=retrievalHtml({status:'review',ai_retrieval:retrieval},'suggested.ai','retrieval<1');
assert.ok(retrievalSuggestion.includes('AI 查找建议 · 需人工确认'));
assert.ok(!retrievalSuggestion.includes('条件验证后自动通过'));
assert.ok(!retrievalSuggestion.includes('认为满足'));
assert.ok(!retrievalSuggestion.includes('本机核验已通过'));
assert.ok(!retrievalSuggestion.includes('<details open'));
assert.ok(retrievalSuggestion.includes('data-detail-key="ai-retrieval"'));
const retrievalMismatch=retrievalHtml({status:'review',ai_retrieval:retrieval},'unsafe"<file>','different');
assert.ok(retrievalMismatch.indexOf('AI 建议与当前候选不同')<retrievalMismatch.indexOf('<details'));
assert.ok(retrievalMismatch.includes('以本机核验或员工选择为准'));
assert.ok(retrievalMismatch.includes('data-candidate-id="retrieval&lt;1"'));
assert.ok(retrievalMismatch.includes('unsafe&quot;&lt;file&gt;'));
const retrievalAuto=retrievalHtml({status:'auto',ai_retrieval:retrieval},'suggested.ai','other');
assert.ok(retrievalAuto.includes('本机核验已通过'));
assert.ok(retrievalAuto.includes('AI 建议与当前候选不同'),'local acceptance must not conceal the model choosing something else');
assert.ok(!retrievalAuto.includes('需人工确认'));
assert.ok(retrievalHtml({status:'confirmed',ai_retrieval:retrieval},'suggested.ai','retrieval<1').includes('本项已由员工确认'));
assert.ok(retrievalHtml({status:'skipped',ai_retrieval:retrieval},'suggested.ai','retrieval<1').includes('本项已跳过'));
assert.ok(retrievalHtml({status:'review',ai_retrieval:{outcome:'error',reason:'接口暂不可用。'}},'',null).includes('AI 查找未完成 · 需人工确认'));
const noRepeat=retrievalHtml({status:'review',reason:retrieval.reason,ai_retrieval:retrieval},'suggested.ai','retrieval<1');
assert.ok(!noRepeat.includes(retrieval.reason),'native pending reason is not duplicated as AI advice');
const longReason='开头简短说明。'+'详细原因<script>unsafe</script>'.repeat(20);
const fullRetrieval=retrievalHtml({status:'review',ai_retrieval:{...retrieval,reason:longReason}},'suggested.ai','retrieval<1');
assert.ok(fullRetrieval.slice(0,fullRetrieval.indexOf('<details')).includes('开头简短说明。'));
assert.ok(!fullRetrieval.includes('<script>'));
assert.ok(fullRetrieval.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
assert.ok(fullRetrieval.indexOf('详细原因')>fullRetrieval.indexOf('<details'));

// Unknown usage is not zero dollars; known partial totals stay labelled USD
// estimates and the missing usage is explained separately.
const unknown = usageText({requests:1,failures:1,unknown_usage_requests:1,
  estimated_usd_upper_bound:null,cost_incomplete:true});
assert.equal(unknown.cost,'费用估算暂不可用');
assert.ok(unknown.unknown.includes('1 次用量未知'));
assert.ok(!unknown.cost.includes('0.000'));
const partial = usageText({requests:1,estimated_usd:0.003,unknown_usage_requests:1});
assert.ok(partial.cost.includes('已知用量费用估算 US$'));
assert.ok(partial.unknown.includes('费用统计不完整'));
assert.ok(usageText({requests:0,estimated_usd:0}).cost.includes('US$ 0.000000'));
assert.equal(usageText(null).cost,'费用估算暂不可用');
async function settingsChecks(){
  // Let the initial asynchronous settings read complete before changing the
  // fixture. No real key or provider is accessed by either refresh.
  for(let index=0;index<8;index++)await Promise.resolve();
  sandbox.fetch=async()=>({ok:true,json:async()=>({configured:true,enabled:true})});
  await sandbox.window.HSDAI.refresh();
  assert.equal(nodes.get('processing-mode-label').textContent,'AI 查找对应图片 + 本机核验');
  assert.match(nodes.get('import-processing-note').textContent,/查找候选与本机核验同时进行/);
  sandbox.fetch=async()=>({ok:true,json:async()=>({configured:true,enabled:false})});
  await sandbox.window.HSDAI.refresh();
  assert.equal(nodes.get('processing-mode-label').textContent,'本机匹配');
  assert.equal(nodes.get('import-processing-note').textContent,'本机匹配，原文件保留');
  console.log('AI UI rendering assertions passed');
}
settingsChecks().catch((error)=>{console.error(error);process.exitCode=1;});
