import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:a}=parseArgs({options:{out:{type:"string"},chrome:{type:"string"},frames:{type:"string",default:"30"},profile:{type:"boolean",default:false},world:{type:"boolean",default:false},headed:{type:"boolean",default:false},
  fixture:{type:"string",default:"_build/world-builder-m3/large-default-final/10k-review.rsdwproject.json"}}});
assert.ok(a.out,"Pass --out");const out=resolve(a.out);await mkdir(out,{recursive:true});
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:!a.headed,...(a.chrome?{executablePath:a.chrome}:{})});
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];
page.on("pageerror",e=>errors.push(String(e)));
const report={status:"running",world:a.world,headed:a.headed,fixture:a.fixture,samples:[],errors};
const percentile=(a,p)=>[...a].sort((a,b)=>a-b)[Math.min(a.length-1,Math.floor(a.length*p))];
try{
  const fixture=JSON.parse(await readFile(a.fixture,"utf8"));(fixture.workspace.world_build||fixture.workspace).world_enabled=false;
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1");
  await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),fixture);
  await page.evaluate(()=>{const d=worldBuilderDebug;d.focus();d.select(d.snapshot().placements.map(p=>p.id));});
  if(a.world){await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));
    await page.waitForFunction(()=>{const d=worldBuilderDebug,m=d.workspace.getOverviewMetrics();return m?.loaded===m?.total&&!d.workspace.layer.getStatus().pending.length&&!d.workspace.layer.resources.stats().jobs.running;},null,{timeout:240000});}
  for(const mode of ["translate","rotate","scale"]){
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    await page.keyboard.press({translate:"g",rotate:"r",scale:"s"}[mode]);
    if(mode==="scale")await page.getByRole("button",{name:"Click here to override.",exact:true}).click();
    await page.evaluate(async()=>{for(let i=0;i<30;i++)await new Promise(r=>requestAnimationFrame(r));});
    const cdp=a.profile?await page.context().newCDPSession(page):null;
    if(cdp){await cdp.send("Profiler.enable");await cdp.send("Profiler.start");}
    const values=await page.evaluate(async({mode,frames})=>{
      const d=worldBuilderDebug,g=d.gizmo(),cpu=[],intervals=[],passes=[],raf=()=>new Promise(r=>requestAnimationFrame(r));
      g.dispatchEvent({type:"dragging-changed",value:true});let previous=await raf();
      for(let i=0;i<frames;i++){
        const start=performance.now();
        if(mode==="translate")g.object.position.y+=.05;
        else if(mode==="rotate")g.object.rotation.y+=.005;
        else g.object.scale.y*=1.001;
        g.dispatchEvent({type:"objectChange"});cpu.push(performance.now()-start);
        const now=await raf();intervals.push(now-previous);previous=now;
        if(i%15===0)passes.push(d.workspace.layer.getRenderMetrics());
      }
      const start=performance.now();g.dispatchEvent({type:"dragging-changed",value:false});const release_ms=performance.now()-start;
      return {cpu,intervals,release_ms,passes,instances:d.performance()};
    },{mode,frames:Number(a.frames)});
    if(cdp){const {profile}=await cdp.send("Profiler.stop");await writeFile(resolve(out,`${mode}.cpuprofile`),JSON.stringify(profile));await cdp.detach();}
    const after=await page.evaluate(()=>worldBuilderDebug.snapshot());assert.notDeepEqual(after.placements,before.placements);
    for(let i=0;i<before.placements.length;i++)for(const k of mode==="rotate"?["scale_x","scale_y","scale_z"]:mode==="scale"?["pitch","yaw","roll"]:["pitch","yaw","roll","scale_x","scale_y","scale_z"])
      assert.equal(after.placements[i].state[k],before.placements[i].state[k]);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    const row={mode,cpu_p50:percentile(values.cpu,.5),cpu_p95:percentile(values.cpu,.95),frame_p95:percentile(values.intervals,.95),...values};
    report.samples.push(row);console.log(JSON.stringify({mode,cpu:row.cpu_p95,frame:row.frame_p95}));
  }
  assert.deepEqual(errors,[]);report.status="passed_contracts";
}catch(e){report.status="failed";report.error=String(e.stack||e);process.exitCode=1;}
finally{await writeFile(resolve(out,"Transforms.json"),JSON.stringify(report,null,2));await browser.close();}
