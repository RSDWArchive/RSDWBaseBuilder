import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";
const {values:args}=parseArgs({options:{sections:{type:"string"},out:{type:"string",default:"_build/world-builder-m2/area-audit"}}});
const {chromium}=createRequire(import.meta.url)("playwright");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const index=JSON.parse(await readFile("_build/world-region/1.0.0.5/whole-world/WorldIndex.json","utf8"));
const entries=args.sections?args.sections.split(",").map(id=>index.sections.find(s=>s.id===id)):[...new Set(index.sections.map(s=>s.biome))].map(area=>index.sections.filter(s=>s.biome===area&&(s.visible_placements||s.terrain)).sort((a,b)=>(b.terrain>0)-(a.terrain>0)||(b.visible_placements||0)-(a.visible_placements||0))[0]);
assert.ok(entries.every(Boolean),"Unknown section");
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[],results=[];
page.on("pageerror",e=>errors.push(String(e)));let active="startup",traceBusy=false;
const trace=setInterval(async()=>{if(traceBusy)return;traceBusy=true;try {
  const state=await page.evaluate(()=>window.worldBuilderDebug?{busy:worldBuilderDebug.busy(),status:worldBuilderDebug.workspace.layer.getStatus(),cache:worldBuilderDebug.workspace.layer.resources.stats()}:null);
  await writeFile(resolve(out,"Trace.json"),JSON.stringify({active,state,errors},null,2));console.log(active+": "+JSON.stringify(state?.status));
}catch{}finally{traceBusy=false;}},10000);
try {
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1");
  await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0,null,{timeout:120000});
  for(const row of entries){active=row.name;console.log("Entering "+active);const start=performance.now();
    await page.evaluate(id=>{worldBuilderDebug.workspace.enterLocation(id).catch(e=>console.error(e));},row.id);
    await page.waitForFunction(id=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes(id),row.id,{timeout:150000});
    await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().pending.length===0,null,{timeout:150000});
    const metrics=await page.evaluate(()=>worldBuilderDebug.workspace.layer.getMetrics());assert.equal(metrics.phase,"ready");
    const snapshot=await page.evaluate(()=>worldBuilderDebug.snapshot());assert.equal(snapshot.placements.length,0);
    await page.screenshot({path:resolve(out,`${row.id}.png`)});results.push({id:row.id,area:row.biome,ms:performance.now()-start,metrics});
    await writeFile(resolve(out,"Areas.json"),JSON.stringify({status:"running",results,errors},null,2));
  }
  assert.deepEqual(errors,[]);await writeFile(resolve(out,"Areas.json"),JSON.stringify({status:"passed",results,errors},null,2));
}catch(error){console.error(error);await page.screenshot({path:resolve(out,"failure.png")}).catch(()=>{});await writeFile(resolve(out,"Areas.json"),JSON.stringify({status:"failed",active,error:error.stack,results,errors},null,2));process.exitCode=1;}
finally{clearInterval(trace);await browser.close();}
