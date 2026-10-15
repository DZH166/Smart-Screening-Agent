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
const {rowHtml,usageText} = sandbox.window.HSDAI;
const review = {verdict:'same',candidate_id:'f<1',outcome:'auto_passed',
  reason:'图案说明'.repeat(40)+'<script>unsafe</script>', differences:['<extra>'],
  gate_failures:[{reason:'资格未完成'},{reason:'覆盖不足'},{reason:'覆盖不足'}],
  protocol_diagnostics:{inconsistent:true}, checks:{content_same:true}};
const html = rowHtml({status:'review',ai_review:review},'a" onmouseover="bad','other');
assert.ok(!html.includes('条件验证后自动通过'));
assert.ok(html.includes('仅供参考，仍需人工确认'));
assert.ok(html.includes('（与当前选择不同）'));
assert.ok(html.includes('data-candidate-id="f&lt;1"'));
assert.ok(!html.includes('<script>') && !html.includes('<extra>'));
assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
assert.ok(!html.includes('<details open'));
assert.equal((html.match(/<li>覆盖不足<\/li>/g)||[]).length,1);
assert.ok(html.includes('模型回答存在矛盾'));
assert.ok(html.indexOf('资格未完成') > html.indexOf('<details'));
assert.ok(rowHtml({status:'auto',ai_review:review},'', 'f<1').includes('条件验证后自动通过'));
assert.equal(rowHtml({status:'auto'},'',null),'');
const unknown = usageText({requests:1,failures:1,unknown_usage_requests:1,
  estimated_usd_upper_bound:null,cost_incomplete:true});
assert.equal(unknown.cost,'费用估算暂不可用');
assert.ok(unknown.unknown.includes('1 次用量未知'));
assert.ok(!unknown.cost.includes('0.000'));
assert.ok(usageText({requests:1,estimated_usd:0.003,unknown_usage_requests:1}).cost.includes('已知用量'));
console.log('AI UI rendering assertions passed');
