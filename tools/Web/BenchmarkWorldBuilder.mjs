import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import os from "node:os";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html" },
  out: { type: "string" }, chrome: { type: "string" },
  streaming: {type:"boolean",default:false}, stress: {type:"boolean",default:false},
  "four-sections":{type:"boolean",default:false},
  milestone3:{type:"boolean",default:false}, counts:{type:"string",default:"100,1000,5000,10000"},
  repetitions:{type:"string",default:"3"}, frames:{type:"string",default:"360"},
  fixture:{type:"string",default:"mixed"}, backend:{type:"string",default:"optimized"},
  cell:{type:"string",default:"64"}, headed:{type:"boolean",default:false},
  "profile-clicks":{type:"boolean",default:false},
  views:{type:"string",default:"full,close,orthographic"}, worlds:{type:"string",default:"false,true"},
  section:{type:"string",default:"x3_y1"},
  "render-origin":{type:"string"},
  "viewport-height":{type:"string",default:"1000"},
} });
if (!args.out) throw Error("Pass --out with an ignored local directory");
if(args.milestone3) {
  const {runPerformanceSuite}=await import("./WorldBuilderPerformance.mjs");
  await runPerformanceSuite(args);
} else {
const { chromium } = createRequire(import.meta.url)("playwright");
const out = resolve(args.out); await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(args.chrome ? { executablePath: args.chrome } : {}) });
const report = { schema: "RSDW.WorldBuilderBenchmark.v1", date: new Date().toISOString(),
  cpu: os.cpus()[0].model, logical_processors: os.cpus().length, memory_gib: os.totalmem() / 2 ** 30,
  viewport: { width: 1600, height: 1000 }, headless: true, samples: [], errors: [] };
try {
  const context = await browser.newContext({ viewport: report.viewport });
  const page = await context.newPage(); page.on("pageerror", e => report.errors.push(String(e)));
  report.status="running";await writeFile(resolve(out,"Performance.json"),JSON.stringify(report,null,2));
  await page.addInitScript(()=>{
    window.worldLoadTasks=[];
    new PerformanceObserver(list=>window.worldLoadTasks.push(...list.getEntries().map(e=>({start:e.startTime,ms:e.duration})))).observe({type:"longtask"});
  });
  const loadStart = performance.now();
  await page.goto(args.url + "?world=1&debug=1");
  await page.waitForFunction(() => window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0, null, { timeout: 120000 });
  report.first_map_ms=performance.now()-loadStart;
  await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));
  report.cold_section_ms = performance.now() - loadStart;
  report.cold_load_tasks=await page.evaluate(()=>window.worldLoadTasks.splice(0));
  console.log(`First map: ${Math.round(report.first_map_ms)} ms; cold destination: ${Math.round(report.cold_section_ms)} ms`);
  report.gpu = await page.evaluate(() => {
    const gl = worldBuilderDebug.renderer.getContext(), ext = gl.getExtension("WEBGL_debug_renderer_info");
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  });
  const cases=args["four-sections"]?[{count:100,nearby:true,focus:[206000,155000]},{count:1000,nearby:true,focus:[206000,155000]}]:args.streaming?[{count:100,nearby:true},{count:1000,nearby:false},{count:1000,nearby:true},...(args.stress?[{count:10000,nearby:true}]:[])]:[{count:100,nearby:false},{count:1000,nearby:false}];
  for (const {count,nearby,focus} of cases) {
    console.log(`Benchmark ${count} authored / ${nearby?"nearby":"single"} sections`);
    const creation = await page.evaluate(async ({count,nearby,focus}) => {
      const d = worldBuilderDebug, p = d.workspace.capture();
      const target = d.catalog.targets.find(t => t.asset_kind === "building_piece" && t.display_name === "Medium Square Foundation");
      const targets=nearby?[target,...["Wall","Floor","Roof","Window","Stairs","Beam"].map(name=>d.catalog.targets.find(t=>t.asset_kind==="building_piece"&&t.display_name.includes(name)&&!t.display_name.includes("Torch")))].filter(Boolean):[target];
      const origin = p.workspace.render_origin_cm, cols = Math.ceil(Math.sqrt(count));
      const center=focus||[origin[0]+14000,origin[1]-10000];
      p.workspace.world_build.world_enabled = false;
      p.workspace.world_build.navigation.mode="build";p.workspace.world_build.navigation.streaming_enabled=nearby;
      p.build = { ...p.build, placements: [], selected_ids: [], ui_collections: [], anchor_piece_id: 1,
        next_object_id: count + 1, next_piece_id: count + 1, next_ui_collection_id: 1 };
      for (let i = 0; i < count; i++) p.build.placements.push({ id: `obj_${i + 1}`, target_id: targets[i%targets.length].target_id,
        state: { x: center[0] + (i % cols - cols / 2) * 400, y: center[1] + (Math.floor(i / cols) - cols / 2) * 400,
          z: 18000, pitch: 0, yaw: 0, roll: 0, scale_x: 1, scale_y: 1, scale_z: 1 },
        metadata: { piece_id: i + 1 }, hidden: false, ui_collection_id: "" });
      const start = performance.now(); await d.workspace.openDocument(p, { confirm: false });
      const restoreMs = performance.now() - start;
      d.focus();const worldStart = performance.now(); await d.workspace.runWorld(nearby?"resume":"load"); const worldMs = performance.now() - worldStart;
      return { restore_ms: restoreMs, warm_section_ms: worldMs, target: target.target_id,distinct_targets:targets.length,world:d.workspace.layer.getMetrics() };
    }, {count,nearby,focus});
    assert.equal(creation.world.phase,"ready","Benchmark requires ready world detail");
    if(args["four-sections"])assert.equal(creation.world.resident.length,4,"Four-section benchmark needs four ready sections");
    await page.waitForFunction(()=>{
      const d=worldBuilderDebug,m=d.workspace.getOverviewMetrics();
      return m?.loaded===m?.total&&d.workspace.layer.getStatus().pending.length===0&&d.workspace.layer.resources.stats().jobs.running===0;
    },null,{timeout:240000});
    creation.load_tasks=await page.evaluate(()=>window.worldLoadTasks.splice(0));
    creation.network=await page.evaluate(()=>{
      const entries=performance.getEntriesByType("resource");performance.clearResourceTimings();
      return {requests:entries.length,unique_urls:new Set(entries.map(e=>e.name)).size,transfer_bytes:entries.reduce((n,e)=>n+e.transferSize,0),cached:entries.filter(e=>e.transferSize===0&&e.decodedBodySize>0).length};
    });
    await page.waitForTimeout(1500);
    const metrics = await page.evaluate(async () => {
      const d = worldBuilderDebug, T = await import("three"), frameTimes = [], tasks = [], samples = [];
      const observer = new PerformanceObserver(list => tasks.push(...list.getEntries().map(e => e.duration)));
      observer.observe({ type: "longtask" });
      const raf = () => new Promise(resolve => requestAnimationFrame(resolve));
      const percentile = (values, fraction) => [...values].sort((a,b) => a-b)[Math.min(values.length - 1, Math.floor(values.length * fraction))] || 0;
      let previous = await raf();
      for (let i = 0; i < 180; i++) {
        const delta = d.camera().position.clone().sub(d.controls.target);
        delta.applyAxisAngle(new T.Vector3(0,1,0), 0.001);
        d.camera().position.copy(d.controls.target).add(delta); d.controls.update();
        const now = await raf(); frameTimes.push(now - previous); previous = now;
      }
      const state = d.snapshot(), origin = state.view_offset;
      const box = document.querySelector("#builder-stage canvas").getBoundingClientRect();
      let hits = 0;const pickTimes=[],selectTimes=[];
      for (const p of state.placements.filter((_,i) => i % Math.max(1,Math.floor(state.placements.length / 30)) === 0).slice(0,30)) {
        const point = new T.Vector3((p.state.x-origin.x)/100, (p.state.z-origin.z)/100+0.1, (p.state.y-origin.y)/100).project(d.camera());
        const event = { clientX: box.x+(point.x+1)*box.width/2, clientY: box.y+(1-point.y)*box.height/2 };
        const start = performance.now(), id = d.pick(event);
        const picked=performance.now();pickTimes.push(picked-start);
        if (id) { d.select([id]); hits++; }
        selectTimes.push(performance.now()-picked);
        await raf(); samples.push(performance.now()-start);
      }
      d.select([]);
      const surfaces = [];
      for (let i=0; i<30; i++) { const start=performance.now(); d.surface(new T.Ray(new T.Vector3(130+i,1000,-100),new T.Vector3(0,-1,0))); surfaces.push(performance.now()-start); }
      let start = performance.now(); const exported = d.export(); const exportMs = performance.now()-start;
      start = performance.now(); d.workspace.markChanged(); await d.workspace.saveNow(); const saveMs = performance.now()-start;
      observer.disconnect();
      return { frame_ms_p50:percentile(frameTimes,.5),frame_ms_p95:percentile(frameTimes,.95),frame_ms_max:Math.max(...frameTimes),
        click_ms_p95:percentile(samples,.95),click_hits:hits,surface_ms_p95:percentile(surfaces,.95),
        pick_ms_p95:percentile(pickTimes,.95),select_cpu_ms_p95:percentile(selectTimes,.95),
        long_task_ms:tasks,export_ms:exportMs,save_ms:saveMs,count:exported.pieces.length,
        render:d.workspace.layer.getMetrics().render,depth:d.workspace.layer.getMetrics().depth,resources:{...d.renderer.info.memory},
        heap_bytes:performance.memory?.usedJSHeapSize,instances:window.__RSDW_BASE_BUILDER_DEBUG__.instanceStats() };
    });
    assert.equal(metrics.count,count); assert.ok(metrics.click_hits > 0);
    report.samples.push({ count,nearby, ...creation, ...metrics });
    await page.screenshot({ path: resolve(out, `world-${count}-${nearby?"nearby":"single"}.png`) });
    await writeFile(resolve(out,"Performance.json"),JSON.stringify(report,null,2));
    console.log(JSON.stringify({count,nearby,frame_p95:metrics.frame_ms_p95,click_p95:metrics.click_ms_p95,save_ms:metrics.save_ms,load_ms:creation.warm_section_ms}));
  }
  await context.close();
  const normal = await browser.newPage({ viewport:report.viewport });
  await normal.goto(args.url+"?benchmark=1000&target="+encodeURIComponent(report.samples[0].target));
  await normal.waitForFunction(()=>window.__RSDW_BASE_BUILDER_DEBUG__?.objectCount()===1000 && document.querySelector("#stage-loading").hidden);
  report.normal_builder_idle = await normal.evaluate(async()=>{
    const times=[];let previous;
    for(let i=0;i<181;i++){const now=await new Promise(resolve=>requestAnimationFrame(resolve));if(previous)times.push(now-previous);previous=now;}
    times.sort((a,b)=>a-b);return {frame_ms_p50:times[90],frame_ms_p95:times[171],instances:__RSDW_BASE_BUILDER_DEBUG__.instanceStats()};
  });
  assert.deepEqual(report.errors,[]);
  report.status = report.samples.filter(s=>s.count<=1000).every(s=>s.frame_ms_p95<=33 && s.click_ms_p95<=100) ? "within_provisional_targets" : "performance_target_miss";
} catch (error) { report.status="failed";report.error=String(error.stack||error);process.exitCode=1; }
finally { await writeFile(resolve(out,"Performance.json"),JSON.stringify(report,null,2));await browser.close(); }
}
