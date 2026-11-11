import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,writeFile} from "node:fs/promises";
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const page=await browser.newPage();const errors=[];page.on("pageerror",e=>errors.push(String(e)));
try{
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/basebuilder-project-store.js");
  const result=await page.evaluate(async()=>{
    const {openProjectStore}=await import("/RSDWBaseBuilder/website/basebuilder-project-store.js");
    const store=openProjectStore(),doc={project_id:"fixture",revision:0,build:{value:1}};
    await store.commit("fixture",0,doc);doc.build.value=99;
    const immutable=(await store.read("fixture")).current.build.value===1;
    await store.commit("fixture",1,{...doc,build:{value:2}});
    const previous=(await store.read("fixture")).previous.build.value===1;
    let conflict=false;try{await store.commit("fixture",1,doc);}catch(e){conflict=e.name==="RevisionConflict";}
    const record={current:{...doc,project_id:"legacy-fixture",revision:1},previous:null},put=IDBObjectStore.prototype.put;
    let interrupted=false,armed=true;
    IDBObjectStore.prototype.put=function(value,key){const request=put.call(this,value,key);if(armed&&this.name==="meta"&&key==="migration:restart"){armed=false;this.transaction.abort();}return request;};
    try{await store.migrate(record,"restart");}catch{interrupted=true;}finally{IDBObjectStore.prototype.put=put;}
    const noPartial=await store.read("legacy-fixture")===null;
    await store.migrate(record,"restart");const count=(await store.records()).length;await store.migrate(record,"restart");
    const restartable=(await store.records()).length===count;
    const before=JSON.stringify(await store.read("fixture"));let failed=false;armed=true;
    IDBObjectStore.prototype.put=function(value,key){const request=put.call(this,value,key);if(armed&&this.name==="projects"&&key==="fixture"){armed=false;this.transaction.abort();}return request;};
    try{await store.commit("fixture",2,doc);}catch{failed=true;}finally{IDBObjectStore.prototype.put=put;}
    const retained=JSON.stringify(await store.read("fixture"))===before;
    const fake={open(){const request={};queueMicrotask(()=>request.onblocked());return request;}};
    let blocked=false;try{await openProjectStore(fake).last();}catch(e){blocked=/blocked/.test(e.message);}
    await store.close();return {immutable,previous,conflict,interrupted,noPartial,restartable,failed,retained,blocked};
  });
  assert.ok(Object.values(result).every(Boolean));assert.deepEqual(errors,[]);
  await mkdir("_build/world-builder-m4/storage",{recursive:true});await writeFile("_build/world-builder-m4/storage/Storage.json",JSON.stringify({status:"passed",checks:result,errors},null,2));
  console.log("Project storage: immutable revisions, previous save, conflicts, interrupted migration restart, transaction rollback and blocked-store errors passed");
}finally{await browser.close();}
