import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string"},chrome:{type:"string"},
  url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html"}}});
assert.ok(args.out,"Pass --out with an ignored local directory");
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const report={status:"running",checks:[],errors:[]};
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true});
const page=await context.newPage();page.on("pageerror",e=>report.errors.push(String(e)));
const count=()=>page.evaluate(()=>__RSDW_BASE_BUILDER_DEBUG__.objectCount());
async function ready(n){await page.waitForFunction(n=>window.__RSDW_BASE_BUILDER_DEBUG__?.objectCount()===n&&document.querySelector("#stage-loading").hidden,n,{timeout:120000});}
async function step(name,run){const detail=await run();report.checks.push({name,detail});console.log(name+": passed");}
async function exportBuild(){
  await page.click("#export-json");await page.getByText("Delivery Location",{exact:true}).waitFor();
  const pending=page.waitForEvent("download");await page.click("#collection-dialog-submit");const download=await pending;
  const data=JSON.parse(await readFile(await download.path(),"utf8"));delete data.generated_unix;return data;
}
async function undo(n){await page.keyboard.press("Control+z");await ready(n);}
async function selectAll(){await page.keyboard.press("Escape");await page.keyboard.press("a");}
async function nonblank(name){
  const png=await page.locator("#builder-stage canvas").first().screenshot();
  const stats=await sharp(png).stats();assert.ok(stats.channels.slice(0,3).some(c=>c.stdev>10),"Blank viewport");
  await page.screenshot({path:resolve(out,`${name}.png`)});
}
try{
  const url=new URL(args.url);url.search="?benchmark=1000&target=085_DA_T1_Foundation_Medium";
  await page.goto(url.href);await ready(1000);const original=await exportBuild();
  assert.equal(original.schema,"rsdwtools.buildings.v1");assert.equal(original.pieces.length,1000);
  await step("Normal builder duplicate preserves source transforms and unique IDs",async()=>{
    await selectAll();await page.keyboard.press("Shift+d");await ready(2000);
    const doubled=await exportBuild();assert.equal(doubled.pieces.length,2000);
    assert.equal(new Set(doubled.pieces.map(p=>p.piece_id)).size,2000);
    const withoutId=({piece_id,...row})=>row;
    assert.deepEqual(doubled.pieces.slice(1000).map(withoutId),original.pieces.map(withoutId));
    await undo(1000);assert.deepEqual(await exportBuild(),original);return true;
  });
  await step("Normal builder hidden/delete export and undo",async()=>{
    await selectAll();await page.keyboard.press("h");
    assert.equal((await exportBuild()).pieces.length,0);assert.equal(await count(),1000);
    await undo(1000);assert.deepEqual(await exportBuild(),original);
    await selectAll();await page.keyboard.press("x");await ready(0);
    await undo(1000);assert.deepEqual(await exportBuild(),original);return true;
  });
  await step("Normal builder autosave recovery",async()=>{
    await page.waitForFunction(()=>document.querySelector("#project-save-status").textContent==="Saved",null,{timeout:15000});
    await page.goto(args.url);await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");await ready(1000);assert.deepEqual(await exportBuild(),original);return true;
  });
  await step("Normal builder desktop/mobile canvas",async()=>{
    await nonblank("desktop");await page.setViewportSize({width:430,height:932});await page.waitForTimeout(300);await nonblank("mobile");
    await page.setViewportSize({width:1600,height:1000});return true;
  });
  await step("Normal builder static NPC instances and editable undo",async()=>{
    await page.evaluate(()=>__RSDW_BASE_BUILDER_DEBUG__.generateSyntheticBuild({count:100,targetId:"bp:BP_NPC_Doric_Dowdun_C"}));
    await ready(100);const before=await exportBuild();assert.equal(before.actors.length,100);
    await selectAll();await page.keyboard.press("Shift+d");await ready(200);
    assert.equal((await exportBuild()).actors.length,200);await undo(100);assert.deepEqual(await exportBuild(),before);
    await nonblank("npc");return true;
  });
  assert.deepEqual(report.errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=String(error.stack||error);process.exitCode=1;}
finally{await writeFile(resolve(out,"AdapterValidation.json"),JSON.stringify(report,null,2));await browser.close();}
