import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";
const {values:args}=parseArgs({options:{url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1"},out:{type:"string",default:"_build/world-builder-m2/acceptance"},cycles:{type:"string",default:"2"},areas:{type:"boolean",default:false}}});
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true});
const page=await context.newPage(),errors=[],checks=[];page.on("pageerror",e=>errors.push(String(e)));
const report={schema:"RSDW.WorldBuilderStreamingAcceptance.v1",checks,status:"running",manual_in_game:"pending"};
async function step(name,run){const start=performance.now();const detail=await run();checks.push({name,ms:Math.round(performance.now()-start),detail});console.log(name+": passed");await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));return detail;}
const state=()=>page.evaluate(()=>({build:worldBuilderDebug.snapshot(),export:worldBuilderDebug.export()}));
async function settled(){await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.layer.getStatus().pending?.length===0,null,{timeout:240000});}
async function screenshot(name){await page.screenshot({path:resolve(out,name),fullPage:true});
  const pixels=await sharp(await page.locator("#builder-stage canvas").screenshot()).stats();
  assert.ok(pixels.channels.some(c=>c.stdev>5),"Blank viewport");}
try {
  await step("Whole-world startup",async()=>{await page.goto(args.url);await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0,null,{timeout:120000});
    await page.waitForFunction(()=>!document.querySelector("#stage-loading").hidden===false);assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.isMap()),true);
    await page.waitForFunction(()=>worldBuilderDebug.workspace.getOverviewMetrics()?.loaded===worldBuilderDebug.workspace.getOverviewMetrics()?.total,null,{timeout:240000});
    await screenshot("overview-desktop.png");return page.evaluate(()=>worldBuilderDebug.workspace.getOverviewMetrics());});
  await step("Map marker click navigates without selecting authored objects",async()=>{
    const point=await page.evaluate(async()=>{
      const T=await import("three"),{sectionFocus}=await import("./world/world-streaming.js");
      const {LOCAL_WORLD}=await import("./world/local-config.js");
      const index=await (await fetch(new URL("WorldIndex.json",LOCAL_WORLD.root))).json(),shared=await (await fetch(new URL("WorldShared.json",LOCAL_WORLD.root))).json();
      const d=worldBuilderDebug,origin=d.workspace.capture().workspace.render_origin_cm,p=sectionFocus(index.sections.find(s=>s.id==="x3_y1"),shared.overview);
      const v=new T.Vector3((p[0]-origin[0])/100,(p[2]-origin[2])/100,(p[1]-origin[1])/100).project(d.camera());
      const r=document.querySelector("#builder-stage canvas").getBoundingClientRect();return {x:r.x+(v.x+1)*r.width/2,y:r.y+(1-v.y)*r.height/2};
    });await page.mouse.click(point.x,point.y);await page.waitForFunction(()=>!worldBuilderDebug.workspace.isMap());await settled();
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.capture().workspace.requested_section_id),"x3_y1");return point;
  });
  await step("Location picker enters detailed building view",async()=>{
    await page.click(".world-location-menu summary");await page.fill("#world-search","Dowdun Reach [3, 1]");await page.selectOption("#world-section-select","x3_y1");await page.click("#world-load-section");
    await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x3_y1"),null,{timeout:240000});await settled();
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.isMap()),false);await screenshot("destination-desktop.png");return page.evaluate(()=>worldBuilderDebug.workspace.layer.getMetrics());});
  const sample=JSON.parse(await readFile("_build/world-builder-m1/acceptance-final/manual-review.rsdwproject.json","utf8"));
  await step("Old project preserves authored transforms",async()=>{
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),sample);await settled();
    assert.deepEqual((await state()).build,sample.build);return page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus());});
  const baseline=await state();
  await step("Camera boundary crossing streams neighbors without duplication",async()=>{
    await page.evaluate(()=>{
      const d=worldBuilderDebug,o=d.snapshot().view_offset,target=d.controls.target,dx=(203000-o.x)/100-target.x,dz=(65600-o.y)/100-target.z;
      target.x+=dx;target.z+=dz;d.camera().position.x+=dx;d.camera().position.z+=dz;d.controls.update();
    });
    await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().sectionId==="x4_y1"&&worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x4_y1"),null,{timeout:240000});await settled();
    assert.deepEqual(await state(),baseline);
    const result=await page.evaluate(()=>{
      const d=worldBuilderDebug,seen=new Set();let duplicates=0;
      d.scene.traverse(o=>{if(!o.userData.sourceMesh)return;for(const id of o.userData.placementIds || []){
        const key=[o.userData.asset,o.userData.sourceMesh,id].join(":");if(seen.has(key))duplicates++;seen.add(key);
      }});return {duplicates,metrics:d.workspace.layer.getMetrics()};
    });assert.equal(result.duplicates,0);assert.ok(result.metrics.resident.length>=2);assert.ok(result.metrics.resident.length<=4);return result;
  });
  await step("Map and nearby navigation retain authored build",async()=>{
    await page.click("#world-map");await settled();assert.deepEqual(await state(),baseline);
    await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x4_y3"));await settled();assert.deepEqual(await state(),baseline);
    await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));await settled();assert.deepEqual(await state(),baseline);
    return true;});
  await step("Save and reload with navigation",async()=>{
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());const project=await page.evaluate(()=>worldBuilderDebug.workspace.capture());
    await writeFile(resolve(out,"manual-review.rsdwproject.json"),JSON.stringify(project,null,2));
    await writeFile(resolve(out,"manual-review-building.json"),JSON.stringify(baseline.export,null,2));
    await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
    await page.waitForFunction(()=>window.worldBuilderDebug?.state().placements===6,null,{timeout:240000});await settled();assert.deepEqual(await state(),baseline);return project.workspace.world_build.navigation;});
  await step("Manual unload stays unloaded after camera movement",async()=>{
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("unload"));
    await page.evaluate(()=>{worldBuilderDebug.camera().position.x+=20;worldBuilderDebug.controls.update();});
    await page.waitForTimeout(1000);assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.length),0);assert.deepEqual(await state(),baseline);
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));await settled();return true;});
  await step("Missing destination retains build and retry succeeds",async()=>{
    const pattern="**/sections/x-10_y-10.json";
    await page.route(pattern,r=>r.fulfill({status:503,body:"Injected missing section"}));
    await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x-10_y-10"));await settled();
    assert.ok(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().failed.some(r=>r.id==="x-10_y-10")));
    assert.deepEqual(await state(),baseline);await page.unroute(pattern);
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));await settled();
    assert.ok(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x-10_y-10")));
    assert.deepEqual(await state(),baseline);return true;
  });
  if(args.areas)await step("All area categories have useful destinations",async()=>{
    const destinations=await page.evaluate(async()=>{
      const {LOCAL_WORLD}=await import("./world/local-config.js"),index=await (await fetch(new URL("WorldIndex.json",LOCAL_WORLD.root))).json();
      return [...new Set(index.sections.map(s=>s.biome))].map(area=>({area,id:index.sections.filter(s=>s.biome===area&&(s.visible_placements||s.terrain)).sort((a,b)=>(b.terrain>0)-(a.terrain>0)||(b.visible_placements||0)-(a.visible_placements||0))[0].id}));
    });const rows=[];
    for(const entry of destinations){console.log("Area entry: "+entry.area+" "+entry.id);
      await page.evaluate(id=>{worldBuilderDebug.workspace.enterLocation(id).catch(e=>console.error(e));},entry.id);
      await page.waitForFunction(id=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes(id),entry.id,{timeout:180000});await settled();
      const s=await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus());assert.ok(s.loadedSectionIds.includes(entry.id),JSON.stringify(s));assert.equal(s.failed.length,0);
      assert.deepEqual(await state(),baseline);rows.push({...entry,loaded:s.loadedSectionIds,placements:s.placements});}
    return rows;
  });
  await step("Orthographic navigation and responsive layouts",async()=>{
    await page.evaluate(()=>worldBuilderDebug.focus());await page.keyboard.press("Numpad5");
    assert.equal(await page.evaluate(()=>worldBuilderDebug.camera().isOrthographicCamera),true);await page.click("#world-map");await settled();await screenshot("overview-orthographic.png");
    for(const [width,height] of [[1000,900],[390,844]]){
      await page.setViewportSize({width,height});await page.keyboard.press("Digit0");await page.evaluate(()=>scrollTo(0,0));await screenshot(`overview-${width}.png`);
      const layout=await page.evaluate(()=>{
        const a=document.querySelector(".workspace").getBoundingClientRect(),b=document.querySelector(".inspector").getBoundingClientRect();
        const header=document.querySelector(".rsdw-header").getBoundingClientRect(),assets=document.querySelector(".asset-panel").getBoundingClientRect();
        return {scroll:document.documentElement.scrollWidth,width:innerWidth,height:document.documentElement.scrollHeight,headerOverlap:header.bottom>assets.top,
          overlap:Math.min(a.right,b.right)>Math.max(a.left,b.left)&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)};
      });assert.equal(layout.scroll,width);assert.equal(layout.overlap,false);
      assert.equal(layout.headerOverlap,false);assert.ok(layout.height<3000,"Unbounded panel height");
      const placed=await page.evaluate(()=>{
        const inspector=document.querySelector(".inspector");inspector.scrollTop=inspector.scrollHeight;
        const a=inspector.getBoundingClientRect(),b=document.querySelector("#placed-new-collection").getBoundingClientRect();
        return b.top>=a.top&&b.bottom<=a.bottom;
      });assert.ok(placed,"Placed actions must remain reachable on narrow screens");
    }
    await page.setViewportSize({width:1600,height:1000});await page.click("#world-return-build");await settled();await page.keyboard.press("Numpad5");assert.deepEqual(await state(),baseline);return true;
  });
  await step("Repeated transitions retain resources and build",async()=>{
    const rows=[];for(let i=0;i<Number(args.cycles);i++){
      await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x4_y3"));await settled();
      await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));await settled();
      assert.deepEqual(await state(),baseline);rows.push(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getMetrics()));
    }return rows;});
  await step("No console errors",async()=>{assert.deepEqual(errors,[]);return errors;});
  report.status="passed";
}catch(error){report.status="failed";report.error=error.stack;console.error(error);await page.screenshot({path:resolve(out,"failure.png"),fullPage:true}).catch(()=>{});process.exitCode=1;}
finally{report.errors=errors;await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));await browser.close();}
