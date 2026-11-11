import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,writeFile} from "node:fs/promises";
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
page.on("pageerror",e=>errors.push(String(e)));page.setDefaultTimeout(120000);
const report={status:"running",checks:[],errors};
async function step(name,fn){const detail=await fn();report.checks.push({name,detail});console.log(name+": passed");}
try{
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?debug=1&saveScheduling=1");
  await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
  await page.evaluate(async()=>{const d=worldBuilderDebug;await d.add("085_DA_T1_Foundation_Medium",{x:0,y:0,z:0,pitch:0,yaw:0,roll:0,scale_x:1,scale_y:1,scale_z:1});await d.workspace.saveNow();});
  await step("In-flight autosave does not chain writes during continued camera edits",async()=>{
    const result=await page.evaluate(async()=>{
      const w=worldBuilderDebug.workspace,original=w.store.commit;let release,calls=0;
      const gate=new Promise(r=>release=r);
      w.store.commit=async(...args)=>{calls++;await gate;return original(...args);};
      try{
        w.markChanged();const pending=w.saveNow({background:true});
        await new Promise(r=>setTimeout(r,50));
        for(let i=0;i<6;i++)w.markChanged({cameraOnly:true});
        release();await pending;const label=document.querySelector("#project-save-status").textContent;
        await new Promise(r=>setTimeout(r,100));const early=calls;
        await w.saveNow();return {early,calls,label,saved:document.querySelector("#project-save-status").textContent};
      }finally{w.store.commit=original;}
    });
    assert.equal(result.early,1);assert.equal(result.calls,2);assert.equal(result.label,"Unsaved");assert.equal(result.saved,"Saved");return result;
  });
  await step("Explicit save waits for an older write then saves the newly edited build",async()=>{
    await page.evaluate(()=>worldBuilderDebug.select(["obj_1"]));
    await page.evaluate(()=>{
      const w=worldBuilderDebug.workspace;window.originalCommit=w.store.commit;window.writeCount=0;
      window.gate=new Promise(r=>window.releaseWrite=r);
      w.store.commit=async(...args)=>{window.writeCount++;await gate;return originalCommit(...args);};
      w.markChanged();window.pendingWrite=w.saveNow({background:true});
    });
    await page.waitForTimeout(50);await page.fill('[data-transform="x"]',"500");await page.dispatchEvent('[data-transform="x"]',"change");
    const result=await page.evaluate(async()=>{
      const w=worldBuilderDebug.workspace,pending=w.saveNow();releaseWrite();await pending;
      const current=(await w.store.read(w.capture().project_id)).current;
      w.store.commit=originalCommit;return {count:writeCount,x:current.build.placements[0].state.x,live:worldBuilderDebug.snapshot().placements[0].state.x,status:document.querySelector("#project-save-status").textContent};
    });assert.equal(result.count,2);assert.equal(result.x,500);assert.equal(result.live,500);assert.equal(result.status,"Saved");return result;
  });
  await step("New camera edits receive an automatic trailing save after the in-flight write",async()=>{
    await page.evaluate(()=>{
      const d=worldBuilderDebug,w=d.workspace;window.originalCommit=w.store.commit;window.writeCount=0;
      window.gate=new Promise(r=>window.releaseWrite=r);
      w.store.commit=async(...args)=>{window.writeCount++;await gate;return originalCommit(...args);};
      w.markChanged();window.pendingWrite=w.saveNow({background:true});
      d.camera().position.x+=1;d.controls.update();
    });
    await page.evaluate(async()=>{releaseWrite();await pendingWrite;});
    await page.waitForFunction(()=>document.querySelector("#project-save-status").textContent==="Saved");
    const result=await page.evaluate(async()=>{
      const w=worldBuilderDebug.workspace,live=w.capture(),saved=(await w.store.read(live.project_id)).current;
      w.store.commit=originalCommit;return {calls:writeCount,live:live.workspace.camera,saved:saved.workspace.camera};
    });assert.equal(result.calls,2);assert.deepEqual(result.saved,result.live);return result;
  });
  await step("Failed queued save leaves the acknowledged revision and live edits intact",async()=>{
    const result=await page.evaluate(async()=>{
      const w=worldBuilderDebug.workspace,p=w.capture(),record=await w.store.read(p.project_id),original=w.store.commit;
      w.store.commit=async()=>{throw Error("Injected storage failure");};w.markChanged();let failed=false;
      try{await w.saveNow();}catch{failed=true;}finally{w.store.commit=original;}
      return {failed,same:JSON.stringify(record)===JSON.stringify(await w.store.read(p.project_id)),x:worldBuilderDebug.snapshot().placements[0].state.x,status:document.querySelector("#project-save-status").textContent};
    });assert.ok(result.failed&&result.same);assert.equal(result.x,500);assert.match(result.status,/Save Failed/);return result;
  });
  assert.deepEqual(errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=String(error.stack||error);console.error(report.error);process.exitCode=1;}
finally{await mkdir("_build/world-builder-wide/autosave",{recursive:true});await writeFile("_build/world-builder-wide/autosave/Autosave.json",JSON.stringify(report,null,2));await browser.close();}
