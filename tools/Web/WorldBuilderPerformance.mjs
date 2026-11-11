import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import os from "node:os";

const legacyTargets=["085_DA_T1_Foundation_Medium","072_DA_T3_Wall_Large_Special_Windowed_1",
  "324_DA_T3_Type2_Floor_Medium","007_DA_T2_Roof_Medium_Diagonal",
  "072_DA_T3_Wall_Large_Special_Windowed_1","716_BUILDPIECE_Stairs_45","011_DA_T3_Beam_Thick_Large_Vertical"];
const mixedTargets=[...legacyTargets,"bp:BP_NPC_Doric_Dowdun_C","bp:BP_NPC_HighLightingTheProblem_Statue_C",
  "item:RSDragonwilds/Content/Gameplay/Character/Player/Equipment/Ammo/ITEM_Ammo_Arrows_Bone_Bleed.json"];

export async function runPerformanceSuite(args) {
  const {chromium}=createRequire(import.meta.url)("playwright"),out=resolve(args.out);
  await mkdir(out,{recursive:true});
  const counts=args.counts.split(",").map(Number),repetitions=Number(args.repetitions),frames=Number(args.frames);
  const views=args.views.split(","),worlds=args.worlds.split(",").map(v=>v==="true");
  assert.ok(views.every(v=>["full","close","orthographic"].includes(v)));
  assert.ok(counts.every(n=>Number.isInteger(n)&&n>0&&n<=100000)&&repetitions>=1&&frames>=60);
  const report={schema:"RSDW.WorldBuilderBenchmark.v2",date:new Date().toISOString(),status:"running",
    cpu:os.cpus()[0].model,logical_processors:os.cpus().length,memory_gib:os.totalmem()/2**30,
    viewport:{width:1600,height:Number(args["viewport-height"]||1000)},headless:!args.headed,options:args,samples:[],errors:[]};
  const save=()=>writeFile(resolve(out,"Performance.json"),JSON.stringify(report,null,2));
  await save();
  const browser=await chromium.launch({headless:!args.headed,...(args.chrome?{executablePath:args.chrome}:{})});
  try {
    const context=await browser.newContext({viewport:report.viewport,acceptDownloads:true});
    const page=await context.newPage();page.on("pageerror",e=>report.errors.push(String(e)));
    page.on("console",m=>{if(m.type()==="error")report.errors.push(m.text());});
    await page.addInitScript(()=>{
      performance.setResourceTimingBufferSize(30000);window.performanceTasks=[];
      new PerformanceObserver(list=>performanceTasks.push(...list.getEntries().map(e=>({start:e.startTime,ms:e.duration})))).observe({type:"longtask"});
    });
    const url=new URL(args.url);url.searchParams.set("world","1");url.searchParams.set("debug","1");
    url.searchParams.set("performance",args.backend);url.searchParams.set("instanceCell",args.cell);
    await page.goto(url.href);
    await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0,null,{timeout:120000});
    await page.evaluate(()=>{
      window.measuredClicks=[];let down=0;const canvas=worldBuilderDebug.renderer.domElement;
      canvas.addEventListener("pointerdown",e=>{down=e.timeStamp;},true);
      canvas.addEventListener("pointerup",()=>{const start=down;requestAnimationFrame(()=>measuredClicks.push(performance.now()-start));},true);
    });
    await page.evaluate(section=>worldBuilderDebug.workspace.enterLocation(section),args.section);
    await settled(page);
    report.startup_tasks=await page.evaluate(()=>performanceTasks.splice(0));
    report.renderer=await page.evaluate(()=>{
      const d=worldBuilderDebug,gl=d.renderer.getContext(),ext=gl.getExtension("WEBGL_debug_renderer_info");
      return {gpu:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
        gpu_timer_available:!!gl.getExtension("EXT_disjoint_timer_query_webgl2"),pixel_ratio:d.renderer.getPixelRatio(),
        buffer:[d.renderer.domElement.width,d.renderer.domElement.height],dataset:d.workspace.capture().dataset};
    });
    for(const count of counts) {
      const ids=args.fixture==="repeated"?legacyTargets.slice(0,1):args.fixture==="legacy"?legacyTargets:mixedTargets;
      const prepared=await page.evaluate(async({count,ids,section,renderOrigin})=>{
        const T=await import("three"),d=worldBuilderDebug,p=d.workspace.capture(),targets=ids.map(id=>d.catalog.targets.find(t=>t.target_id===id));
        if(targets.some(t=>!t))throw Error("Benchmark target unavailable");
        const origin=renderOrigin || p.workspace.render_origin_cm,cols=Math.ceil(Math.sqrt(count));
        p.workspace.render_origin_cm=[...origin];p.build.view_offset={x:origin[0],y:origin[1],z:origin[2]};
        p.workspace.world_build.world_enabled=false;p.workspace.world_build.navigation.mode="build";p.workspace.world_build.navigation.streaming_enabled=true;
        p.workspace.world_build.requested_section_id=section;
        p.workspace.camera.projection="perspective";p.workspace.camera.size=12;
        p.build={...p.build,build_name:`10k performance ${count}`,placements:[],selected_ids:[],ui_collections:[],closed_placed_group_ids:[],
          anchor_piece_id:1,next_object_id:count+1,next_piece_id:count+1,next_ui_collection_id:1};
        for(let i=0;i<count;i++)p.build.placements.push({id:`obj_${i+1}`,target_id:targets[i%targets.length].target_id,
          state:{x:origin[0]+14000+(i%cols-cols/2)*400,y:origin[1]-10000+(Math.floor(i/cols)-cols/2)*400,z:18000,
            pitch:0,yaw:0,roll:0,scale_x:1,scale_y:1,scale_z:1},metadata:{piece_id:i+1},hidden:false,ui_collection_id:""});
        performanceTasks.length=0;const start=performance.now();await d.workspace.openDocument(p,{confirm:false});
        const restore_ms=performance.now()-start;
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        d.focus();
        const distance=d.camera().position.distanceTo(d.controls.target);
        d.camera().position.copy(d.controls.target).add(new T.Vector3(26,30,36).normalize().multiplyScalar(distance));d.controls.update();
        return {restore_ms,project:d.workspace.capture(),load_tasks:performanceTasks.splice(0),exported:d.export()};
      },{count,ids,section:args.section,renderOrigin:args["render-origin"]?.split(",").map(Number)});
      await writeFile(resolve(out,`sample-${count}.rsdwproject.json`),JSON.stringify(prepared.project));
      await writeFile(resolve(out,`sample-${count}-building.json`),JSON.stringify(prepared.exported));
      const camera=await page.evaluate(()=>worldBuilderDebug.workspace.capture().workspace.camera);
      for(const world of worlds) {
        await page.evaluate(()=>{performanceTasks.length=0;});
        const loadStart=performance.now();
        if(world){await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));await settled(page);}
        const world_load_ms=world?performance.now()-loadStart:0;
        const world_load_tasks=await page.evaluate(()=>performanceTasks.splice(0));
        const coverage=await page.evaluate(()=>({world:worldBuilderDebug.workspace.layer.getMetrics(),overview:worldBuilderDebug.workspace.getOverviewMetrics(),network:performance.getEntriesByType("resource").length}));
        for(const view of views)for(let repetition=0;repetition<repetitions;repetition++) {
          await page.evaluate(({camera,view})=>{
            const d=worldBuilderDebug,c=d.camera(),o=d.snapshot().view_offset;
            d.select([]);const p=camera.position_cm,t=camera.target_cm;
            c.position.set((p[0]-o.x)/100,(p[2]-o.z)/100,(p[1]-o.y)/100);
            d.controls.target.set((t[0]-o.x)/100,(t[2]-o.z)/100,(t[1]-o.y)/100);
            if(view==="close")c.position.copy(d.controls.target).add({x:25,y:35,z:45});
            d.controls.update();performanceTasks.length=0;
          },{camera,view});
          if(view==="orthographic")await page.keyboard.press("Numpad5");
          await page.waitForTimeout(500);
          const metrics=await page.evaluate(async frames=>{
            const d=worldBuilderDebug,T=await import("three"),times=[],passes=[],raf=()=>new Promise(r=>requestAnimationFrame(r));
            const q=(a,n)=>[...a].sort((a,b)=>a-b)[Math.min(a.length-1,Math.floor(a.length*n))]||0;
            const view_camera={world:[...d.camera().matrixWorld.elements],projection:[...d.camera().projectionMatrix.elements],
              buffer:[d.renderer.domElement.width,d.renderer.domElement.height],orbit_step_radians:.001,frames};
            performanceTasks.length=0;let previous=await raf();
            for(let i=0;i<frames;i++){
              const delta=d.camera().position.clone().sub(d.controls.target).applyAxisAngle(new T.Vector3(0,1,0),.001);
              d.camera().position.copy(d.controls.target).add(delta);d.controls.update();
              const now=await raf();times.push(now-previous);previous=now;
              if(i%30===0)passes.push({...d.workspace.layer.getRenderMetrics(),
                authored:d.performance?.()||window.__RSDW_BASE_BUILDER_DEBUG__.instanceStats()});
            }
            return {frame_ms_p50:q(times,.5),frame_ms_p95:q(times,.95),frame_ms_p99:q(times,.99),frame_ms_max:Math.max(...times),
              orbit_tasks:performanceTasks.splice(0),passes,view_camera};
          },frames);
          const hits=await page.evaluate(async()=>{
            const d=worldBuilderDebug,T=await import("three"),s=d.snapshot(),r=d.renderer.domElement.getBoundingClientRect(),points=[];
            for(const p of s.placements){
              const v=new T.Vector3((p.state.x-s.view_offset.x)/100,(p.state.z-s.view_offset.z)/100+.2,(p.state.y-s.view_offset.y)/100).project(d.camera());
              if(Math.abs(v.x)>.9||Math.abs(v.y)>.9||v.z< -1||v.z>1)continue;
              const e={clientX:r.x+(v.x+1)*r.width/2,clientY:r.y+(1-v.y)*r.height/2};
              if(document.elementFromPoint(e.clientX,e.clientY)!==d.renderer.domElement)continue;
              const start=performance.now(),id=d.pick(e);
              if(id)points.push({x:e.clientX,y:e.clientY,id,pick_ms:performance.now()-start});if(points.length===12)break;
            }return points;
          });
          assert.ok(hits.length,`No interactive hits: ${count}/${view}`);
          await page.evaluate(()=>{measuredClicks.length=0;});
          const cdp=args["profile-clicks"]&&repetition===0?await context.newCDPSession(page):null;
          const programsBefore=cdp?await page.evaluate(()=>worldBuilderDebug.renderer.info.programs.map(p=>({id:p.id,name:p.name,key:p.cacheKey}))):[];
          if(cdp){await cdp.send("Profiler.enable");await cdp.send("Profiler.start");}
          const transportTimes=[];
          for(const [i,hit]of hits.entries()){const start=performance.now();await page.mouse.click(hit.x,hit.y);
            await page.waitForFunction(n=>measuredClicks.length>n,i);transportTimes.push(performance.now()-start);}
          if(cdp){const {profile}=await cdp.send("Profiler.stop");await writeFile(resolve(out,`${count}-${world}-${view}-clicks.cpuprofile`),JSON.stringify(profile));await cdp.detach();}
          const clicks=await page.evaluate(()=>measuredClicks);
          const programsAdded=cdp?await page.evaluate(ids=>worldBuilderDebug.renderer.info.programs.filter(p=>!ids.includes(p.id)).map(p=>({id:p.id,name:p.name,key:p.cacheKey})),programsBefore.map(p=>p.id)):[];
          const end=await page.evaluate(async()=>{
            const d=worldBuilderDebug;d.select([]);let start=performance.now();const exported=d.export(),export_ms=performance.now()-start;
            start=performance.now();d.workspace.markChanged();await d.workspace.saveNow();
            return {export_ms,save_ms:performance.now()-start,exported,interaction_tasks:performanceTasks.splice(0),
              heap_bytes:performance.memory?.usedJSHeapSize,resources:{...d.renderer.info.memory},save_metrics:d.workspace.saveMetrics?.()||null};
          });
          assert.deepEqual(end.exported,prepared.exported,"Performance actions changed export");delete end.exported;
          clicks.sort((a,b)=>a-b);
          const sample={count,world,view,repetition,targets:ids,restore_ms:prepared.restore_ms,world_load_ms,
            load_tasks:prepared.load_tasks,world_load_tasks,coverage,camera,...metrics,...end,click_ms_p95:clicks[Math.floor(clicks.length*.95)],
            click_ms:clicks,automation_roundtrip_ms:transportTimes,pick_ms: hits.map(h=>h.pick_ms),programsAdded};
          report.samples.push(sample);await save();
          if(repetition===0)await page.screenshot({path:resolve(out,`${count}-${world?"world":"plain"}-${view}.png`)});
          console.log(JSON.stringify({count,world,view,repetition,frame:sample.frame_ms_p95,click:sample.click_ms_p95}));
          if(view==="orthographic")await page.keyboard.press("Numpad5");
        }
      }
    }
    report.selection_lifecycle=await page.evaluate(async()=>{
      const d=worldBuilderDebug,id=d.snapshot().placements.find(p=>p.target_id.includes("Doric"))?.id;
      if(!id)return {skipped:"Fixture has no Doric"};
      const resources=[],frame=()=>new Promise(r=>requestAnimationFrame(r));
      for(let i=0;i<50;i++){
        d.select([id]);await frame();await frame();d.select([]);await frame();await frame();resources.push({...d.renderer.info.memory});
      }return {cycles:resources.length,resources};
    });
    if(report.selection_lifecycle.resources){const rows=report.selection_lifecycle.resources;
      assert.ok(rows.at(-1).textures<=rows[0].textures,"NPC promotion/demotion leaked skeleton textures");}
    assert.deepEqual(report.errors,[]);
    report.status=report.samples.every(s=>s.frame_ms_p95<=33.3&&s.frame_ms_p99<=50&&s.click_ms_p95<=100)?"within_frame_input_targets":"performance_target_miss";
    report.note="Frame/input result only; full milestone also requires lifecycle, visual and large-action acceptance.";
  } catch(error){report.status="failed";report.error=String(error.stack||error);process.exitCode=1;}
  finally{await save();await browser.close();}
}

async function settled(page){
  await page.waitForFunction(()=>{const d=worldBuilderDebug,m=d.workspace.getOverviewMetrics();return m?.loaded===m?.total&&d.workspace.layer.getStatus().pending.length===0&&d.workspace.layer.resources.stats().jobs.running===0;},null,{timeout:240000});
}
