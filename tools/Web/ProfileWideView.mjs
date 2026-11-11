import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile,copyFile,readdir,access} from "node:fs/promises";
import {resolve,dirname,relative} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string",default:"_build/world-builder-wide/profile"},
  fixture:{type:"string",default:"_build/world-builder-m4/performance-final/sample-10000.rsdwproject.json"},
  frames:{type:"string",default:"180"},repetitions:{type:"string",default:"3"},
  source:{type:"string"},snapshot:{type:"boolean",default:false},views:{type:"string",default:"full,orthographic"},
  profile:{type:"boolean",default:false}}});
assert.ok(Number(args.frames)>=60&&Number(args.repetitions)>=1,"Use at least 60 frames and one repetition");
assert.ok(args.views.split(",").every(v=>["full","orthographic"].includes(v)),"Unsupported view");
const {chromium}=createRequire(import.meta.url)("playwright"),out=resolve(args.out);await mkdir(out,{recursive:true});
const sourceRoot=resolve("website");
if(args.snapshot){
  const destination=resolve(out,"source");
  async function saveTree(path){for(const entry of await readdir(path,{withFileTypes:true})){const file=resolve(path,entry.name);
    if(entry.isDirectory()&&entry.name==="world")await saveTree(file);
    else if(entry.isFile()&&/\.(js|css|html)$/.test(entry.name)){const target=resolve(destination,relative(sourceRoot,file));await mkdir(dirname(target),{recursive:true});await copyFile(file,target);}}}
  await saveTree(sourceRoot);
}
const fixture=JSON.parse(await readFile(args.fixture,"utf8"));
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const report={status:"running",source:args.source||"current",fixture:args.fixture,frames:Number(args.frames),samples:[],errors:[]};
const save=()=>writeFile(resolve(out,"Profile.json"),JSON.stringify(report,null,2));await save();
try{
  const page=await browser.newPage({viewport:{width:1600,height:1060}});page.setDefaultTimeout(240000);
  page.on("pageerror",e=>report.errors.push(String(e)));
  if(args.source)await page.route("**/RSDWBaseBuilder/website/**",async route=>{
    const path=decodeURIComponent(new URL(route.request().url()).pathname.split("/website/")[1]);
    if(!/\.(js|css|html)$/.test(path)||path.includes(".."))return route.continue();
    const file=resolve(args.source,path);try{await access(file);}catch{return route.continue();}
    return route.fulfill({path:file});
  });
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?debug=1&wideProfile=1");
  await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),fixture);
  console.log("10k fixture ready; loading world");
  await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));
  await page.waitForFunction(()=>{const d=worldBuilderDebug,m=d.workspace.getOverviewMetrics(),s=d.workspace.layer.getStatus();
    return m?.loaded===m?.total&&s.pending.length===0&&d.workspace.layer.resources.stats().jobs.running===0;});
  await page.evaluate(()=>{const input=document.querySelector("#world-streaming");input.checked=false;input.dispatchEvent(new Event("change"));});
  const before=await page.evaluate(()=>worldBuilderDebug.export());
  report.renderer=await page.evaluate(()=>{const d=worldBuilderDebug,gl=d.renderer.getContext(),ext=gl.getExtension("WEBGL_debug_renderer_info");
    return {gpu:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),buffer:[d.renderer.domElement.width,d.renderer.domElement.height],world:d.workspace.layer.getMetrics(),authored:d.performance()};});
  assert.equal(report.renderer.world.phase,"ready","World detail must be ready before profiling");
  const cdp=await page.context().newCDPSession(page);
  for(const view of args.views.split(","))for(let repetition=0;repetition<Number(args.repetitions);repetition++){
    await page.evaluate(({camera,view})=>{const d=worldBuilderDebug;d.select([]);d.controls.enabled=true;
      d.workspace.capture();const origin=d.snapshot().view_offset;
      d.camera().position.set((camera.position_cm[0]-origin.x)/100,(camera.position_cm[2]-origin.z)/100,(camera.position_cm[1]-origin.y)/100);
      d.controls.target.set((camera.target_cm[0]-origin.x)/100,(camera.target_cm[2]-origin.z)/100,(camera.target_cm[1]-origin.y)/100);d.controls.update();
    },{camera:fixture.workspace.camera,view});
    if(view==="orthographic")await page.keyboard.press("Numpad5");
    await page.waitForTimeout(1000);
    if(args.profile&&repetition===0){await cdp.send("Profiler.enable");await cdp.send("Profiler.start");}
    const sample=await page.evaluate(async({frames,view})=>{
      const d=worldBuilderDebug,T=await import("three"),times=[],passes=[],cpu=[];
      const oldRender=d.workspace.render;
      d.workspace.render=function(scene){const start=performance.now();oldRender(scene);cpu.push(performance.now()-start);};
      const raf=()=>new Promise(r=>requestAnimationFrame(r)),q=(a,p)=>[...a].sort((a,b)=>a-b)[Math.min(a.length-1,Math.floor(a.length*p))]||0;
      const camera={world:d.camera().matrixWorld.toArray(),projection:d.camera().projectionMatrix.toArray()};
      try{let previous=await raf();for(let i=0;i<frames;i++){
        d.camera().position.sub(d.controls.target).applyAxisAngle(new T.Vector3(0,1,0),.001).add(d.controls.target);d.controls.update();
        const now=await raf();times.push(now-previous);previous=now;
        if(i%30===0)passes.push(d.workspace.layer.getRenderMetrics());
      }}finally{d.workspace.render=oldRender;}
      return {view,camera,frame_p50:q(times,.5),frame_p95:q(times,.95),frame_p99:q(times,.99),render_cpu_p50:q(cpu,.5),render_cpu_p95:q(cpu,.95),passes};
    },{frames:Number(args.frames),view});
    if(args.profile&&repetition===0){const {profile}=await cdp.send("Profiler.stop");await writeFile(resolve(out,`${view}.cpuprofile`),JSON.stringify(profile));
      const byId=new Map(profile.nodes.map(n=>[n.id,n])),totals=new Map();
      for(let i=0;i<profile.samples.length;i++){const node=byId.get(profile.samples[i]),f=node.callFrame,key=`${f.functionName} | ${f.url}:${f.lineNumber+1}`;totals.set(key,(totals.get(key)||0)+profile.timeDeltas[i]);}
      sample.profile_top=[...totals].sort((a,b)=>b[1]-a[1]).slice(0,35).map(([fn,us])=>({fn,ms:us/1000}));
    }
    sample.repetition=repetition;report.samples.push(sample);await save();console.log(JSON.stringify({view,repetition,p95:sample.frame_p95,cpu:sample.render_cpu_p95}));
    if(repetition===0)await page.screenshot({path:resolve(out,`${view}.png`)});
    if(view==="orthographic")await page.keyboard.press("Numpad5");
  }
  assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.export()),before,"Profiling changed game export");
  await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
  assert.deepEqual(report.errors,[]);report.status="passed_contracts";await cdp.detach();
}catch(error){report.status="failed";report.error=String(error.stack||error);console.error(report.error);process.exitCode=1;}
finally{await save();await browser.close();}
