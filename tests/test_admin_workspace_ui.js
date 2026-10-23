// Navigation-only regression: credentials are not fetched by changing sections.
"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const code=fs.readFileSync(path.join(__dirname,"../hsd_tool/static/admin-workspace.js"),"utf8");
function element(name){const classes=new Set(),listeners={};return{dataset:{adminSection:name},open:false,attributes:{href:`#${name}`},classList:{toggle(key,value){if(value)classes.add(key);else classes.delete(key);},contains:key=>classes.has(key)},getAttribute(key){return this.attributes[key];},setAttribute(key,value){this.attributes[key]=value;},removeAttribute(key){delete this.attributes[key];},addEventListener(name,fn){listeners[name]=fn;},click(){listeners.click?.({preventDefault(){}});}};}
const names=["keys","functions","help"],sections=names.map(element),links=names.map(element),ledger=element("ledger"),listeners={};
let fetches=0;
const context={document:{querySelectorAll:selector=>selector===".admin-nav-item"?links:sections,getElementById:()=>ledger},location:{hash:"#functions"},history:{replaceState(_a,_b,value){context.location.hash=value;}},window:{addEventListener(name,fn){listeners[name]=fn;}},fetch(){fetches++;throw new Error("navigation must not fetch");}};
vm.runInNewContext(code,context);
assert.equal(sections[0].classList.contains("hidden"),true);assert.equal(sections[1].classList.contains("hidden"),false);assert.equal(sections[2].classList.contains("hidden"),true);
assert.equal(links[1].attributes["aria-current"],"page");
links[0].click();ledger.open=true;links[2].click();
assert.equal(ledger.open,false,"leaving Key management closes the secret ledger");
assert.equal(sections[2].classList.contains("hidden"),false);assert.equal(sections[0].classList.contains("hidden"),true);assert.equal(links[0].attributes["aria-current"],undefined);
context.location.hash="#invalid";listeners.hashchange();assert.equal(sections[0].classList.contains("hidden"),false);assert.equal(fetches,0);
console.log("Admin section navigation assertions passed");
