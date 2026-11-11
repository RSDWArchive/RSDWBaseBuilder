import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string",default:"_build/world-builder-m2/cross-section"},fixture:{type:"string",default:"_build/world-builder-m1/acceptance-final/manual-review.rsdwproject.json"}}});
const {chromium}=createRequire(import.meta.url)("playwright");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
page.on("pageerror",e=>errors.push(String(e)));
const report={status:"running",steps:[],errors};
const snapshot=()=>page.evaluate(()=>({build:worldBuilderDebug.snapshot(),export:worldBuilderDebug.export()}));
try {
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1");
  await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0,null,{timeout:120000});
  const project=JSON.parse(await readFile(args.fixture,"utf8"));
  // A deliberately spread-out test fixture, not a prefab intended to remain together.
  project.build.placements.forEach((p,i)=>{if(i>=2&&i<4)p.state.x+=51200;if(i>=4)p.state.y+=102400;});
  project.build.placements[4].hidden=true;
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
  const before=await snapshot();assert.equal(before.build.placements.length,6);
  for(const id of ["x3_y1","x4_y1","x3_y3"]){
    await page.evaluate(id=>worldBuilderDebug.workspace.enterLocation(id),id);
    assert.deepEqual(await snapshot(),before);report.steps.push(id);
  }
  await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("unload"));assert.deepEqual(await snapshot(),before);
  await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
  const saved=await page.evaluate(()=>worldBuilderDebug.workspace.capture());
  await writeFile(resolve(out,"cross-section.rsdwproject.json"),JSON.stringify(saved,null,2));
  await writeFile(resolve(out,"cross-section-building.json"),JSON.stringify(before.export,null,2));
  await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
  await page.waitForFunction(()=>worldBuilderDebug.state().placements===6,null,{timeout:120000});assert.deepEqual(await snapshot(),before);
  assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.length),0);
  report.steps.push("unload-save-reload-exact");assert.deepEqual(errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=error.stack;process.exitCode=1;}
finally{await writeFile(resolve(out,"Journey.json"),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();}
