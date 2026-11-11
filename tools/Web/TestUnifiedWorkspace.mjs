import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string",default:"_build/world-builder-m4/acceptance"},"skip-builds":{type:"boolean",default:false}}});
const {chromium}=createRequire(import.meta.url)("playwright"), sharp=createRequire(import.meta.url)("sharp");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true});
const page=await context.newPage(),errors=[],requests=[];
page.setDefaultTimeout(180000);page.on("pageerror",e=>errors.push(String(e)));
page.on("request",r=>{if(/world-region|\/world\//.test(r.url()))requests.push(r.url());});
const report={schema:"RSDW.UnifiedWorkspaceAcceptance.v1",status:"running",checks:[],errors};
const url="http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?debug=1&milestone=4";
const ready=()=>page.waitForFunction(()=>window.worldBuilderDebug&&!worldBuilderDebug.busy()&&document.querySelector("#stage-loading").hidden);
const snapshot=()=>page.evaluate(()=>worldBuilderDebug.snapshot());
const capture=()=>page.evaluate(()=>worldBuilderDebug.workspace.capture());
const exported=()=>page.evaluate(()=>worldBuilderDebug.export());
async function step(name,fn){const start=performance.now(),detail=await fn();report.checks.push({name,ms:Math.round(performance.now()-start),detail});console.log(name+": passed");await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));}
async function downloadBuild(choice){const waiting=page.waitForEvent("download");await page.click("#export-json");await page.getByText("Delivery Location",{exact:true}).waitFor();await page.getByRole("button",{name:choice,exact:true}).click();const dl=await waiting;const json=JSON.parse(await readFile(await dl.path(),"utf8"));delete json.generated_unix;return json;}
async function screen(name){const png=await page.locator("#builder-stage canvas").first().screenshot();const stats=await sharp(png).stats();assert.ok(stats.channels.slice(0,3).some(c=>c.stdev>10),"Blank canvas");await page.screenshot({path:resolve(out,name+".png"),fullPage:true});}
async function restore(){await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");await ready();}
async function importFile(path,here=false,append=false){await page.click("#import-json");await page.click(append?"#collection-dialog-secondary":"#collection-dialog-submit");await page.setInputFiles("#file-input",path);await page.getByText("Import Location",{exact:true}).waitFor();await page.click(here?"#collection-dialog-secondary":"#collection-dialog-submit");if(here)await page.waitForFunction(()=>worldBuilderDebug.preview()?.buildCount>0);else await ready();}
async function previewPoint(){const rect=await page.locator("#builder-stage canvas").first().boundingBox();for(const [x,y]of [[.5,.5],[.5,.6],[.4,.55],[.6,.55],[.5,.7],[.3,.6]]){const p={x:rect.x+rect.width*x,y:rect.y+rect.height*y};await page.mouse.move(p.x,p.y);if(await page.evaluate(()=>worldBuilderDebug.preview()?.canDrop))return p;}throw Error("No preview contact");}
function compareRows(actual,expected){for(const kind of ["pieces","items","actors"]){assert.equal(actual[kind].length,expected[kind]?.length||0);for(let i=0;i<actual[kind].length;i++)for(const key of ["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"]){const precision=key.startsWith("scale")?1e6:1e3;assert.equal(actual[kind][i][key],Math.round(expected[kind][i][key]*precision)/precision,`${kind} ${i} ${key}`);}}}
function compareCamera(a,b){assert.equal(a.projection,b.projection);assert.equal(a.size,b.size);for(const k of ["position_cm","target_cm"])for(let i=0;i<3;i++)assert.ok(Math.abs(a[k][i]-b[k][i])<.01,`Camera ${k} ${i}: ${a[k][i]} vs ${b[k][i]}`);}
try {
  await page.route("**/world-region/**",r=>r.abort());await page.goto(url);await ready();
  await step("Free startup has no world-data requests",async()=>{assert.equal(requests.length,0);const p=await capture();assert.equal(p.workspace.authoring_mode,"free");assert.equal(p.dataset.world_sha256,null);assert.equal(p.workspace.world_build,null);assert.ok(await page.locator("#project-workspace").isVisible());return {world_requests:0};});
  const fixture=await page.evaluate(()=>{
    const d=worldBuilderDebug,p=d.workspace.capture(),targets=d.catalog.targets;
    const piece=targets.find(t=>t.target_id==="085_DA_T1_Foundation_Medium"),item=targets.find(t=>t.asset_kind==="item"),bp=targets.find(t=>t.asset_stem==="BP_NPC_Doric_Dowdun_C");
    p.build.build_name="Milestone 4 mixed";p.build.ui_collections=[{id:"collection_1",name:"Mixed build",order:0,collapsed:false}];
    const state={x:1200,y:2400,z:-500,pitch:17,roll:-23,yaw:37,scale_x:-1,scale_y:.7,scale_z:1.2};
    p.build.placements=[piece,item,bp,piece].map((t,i)=>({id:`obj_${i+1}`,target_id:t.target_id,state:{...state,x:state.x+i*500},metadata:{...(t.asset_kind==="building_piece"?{piece_id:i+1}:{}),item_count:3},hidden:i===3,ui_collection_id:"collection_1"}));
    p.build.anchor_piece_id=1;p.build.selected_ids=[];p.build.next_object_id=5;p.build.next_piece_id=5;p.build.next_ui_collection_id=2;
    p.workspace.free_build.plane_z_cm=-500;return p;
  });
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),fixture);await ready();
  const mixed=await snapshot(),mixedJson=await exported();
  await step("Both delivery intents keep canonical JSON and hidden exclusion",async()=>{
    const a=await downloadBuild("Saved World Location"),b=await downloadBuild("Place Using Anchor");assert.deepEqual(a,b);
    const expected={...mixedJson};delete expected.generated_unix;assert.deepEqual(a,expected);assert.equal(a.pieces.length,1);assert.equal(a.items.length,1);assert.equal(a.actors.length,1);assert.equal(a.anchor_piece_id,1);
    assert.equal(a.actors[0].pitch,-17);assert.equal(a.actors[0].roll,23);assert.equal(a.actors[0].scale_x,-1);
    assert.ok(!JSON.stringify(a).includes("collection"));await writeFile(resolve(out,"mixed-expected.json"),JSON.stringify(a,null,2));return true;
  });
  await step("Free plane and project recovery",async()=>{
    assert.equal(await page.inputValue("#free-plane-z"),"-500");await page.fill("#free-plane-z","-700");await page.locator("#free-plane-z").blur();
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());const p=await capture();assert.equal(p.workspace.free_build.plane_z_cm,-700);
    await page.reload();await restore();assert.deepEqual(await snapshot(),mixed);assert.equal((await capture()).workspace.free_build.plane_z_cm,-700);assert.equal(requests.length,0);await screen("free-perspective");
    await page.keyboard.press("Numpad5");await screen("free-orthographic");await page.keyboard.press("Numpad5");await page.keyboard.press("t");await screen("free-solid");await page.keyboard.press("t");return true;
  });
  await page.unroute("**/world-region/**");
  await step("Workspace switching retains authored data and independent cameras",async()=>{
    const freeCamera=(await capture()).workspace.camera;
    await page.evaluate(()=>worldBuilderDebug.workspace.setMode("world"));await page.waitForFunction(()=>worldBuilderDebug.workspace.getOverviewMetrics()?.loaded>0);
    const worldCamera=(await capture()).workspace.camera;assert.deepEqual(await snapshot(),mixed);assert.deepEqual(await exported(),mixedJson);
    assert.equal(await page.evaluate(()=>worldBuilderDebug.renderer.capabilities.logarithmicDepthBuffer),true);
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("unload"));
    await page.evaluate(()=>worldBuilderDebug.workspace.setMode("free"));compareCamera((await capture()).workspace.camera,freeCamera);
    const resources=[];
    for(let i=0;i<25;i++){
      await page.evaluate(()=>worldBuilderDebug.workspace.setMode("world"));compareCamera((await capture()).workspace.camera,worldCamera);
      await page.evaluate(()=>worldBuilderDebug.workspace.setMode("free"));assert.deepEqual(await snapshot(),mixed);assert.deepEqual(await exported(),mixedJson);
      resources.push(await page.evaluate(()=>({...worldBuilderDebug.renderer.info.memory,canvas:document.querySelectorAll("#builder-stage canvas").length,roots:worldBuilderDebug.scene.children.filter(o=>o.name==="Read-only World").length})));
    }
    assert.ok(resources.every(r=>r.canvas===1&&r.roots===1));assert.ok(resources.at(-1).geometries<=resources[0].geometries+2);assert.ok(resources.at(-1).textures<=resources[0].textures+2);
    return {switches:52,paused_world_cycles:25,resources};
  });
  await step("Queued workspace switch waits for preview cancellation",async()=>{
    await page.evaluate(()=>worldBuilderDebug.select(["obj_2"]));await page.locator("#builder-stage").click({position:{x:30,y:150}});await page.evaluate(()=>worldBuilderDebug.select(["obj_2"]));await page.keyboard.press("e");
    await page.waitForFunction(()=>worldBuilderDebug.preview());await page.evaluate(()=>worldBuilderDebug.workspace.setMode("world"));assert.equal((await capture()).workspace.authoring_mode,"free");
    await page.keyboard.press("Escape");await page.waitForFunction(()=>worldBuilderDebug.workspace.mode()==="world");assert.deepEqual((await snapshot()).placements,mixed.placements);await page.evaluate(()=>worldBuilderDebug.workspace.setMode("free"));return true;
  });
  await step("V2 download, revision conflict, Save Copy and quota fallback",async()=>{
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    const tab2=await context.newPage();tab2.setDefaultTimeout(120000);await tab2.goto(url);await tab2.getByText("Restore project?",{exact:true}).waitFor();await tab2.click("#collection-dialog-submit");
    await tab2.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
    await tab2.evaluate(()=>worldBuilderDebug.workspace.saveNow());await tab2.close();
    await page.evaluate(async()=>{const w=worldBuilderDebug.workspace;w.markChanged();try{await w.saveNow();throw Error("Expected conflict");}catch(e){if(e.name!=="RevisionConflict")throw e;}});
    assert.match(await page.textContent("#project-save-status"),/another tab/);
    await page.locator("#project-workspace > .project-menu summary").click();const pending=page.waitForEvent("download");await page.click("#project-copy");const dl=await pending;await page.waitForFunction(()=>document.querySelector("#project-save-status").textContent==="Saved");
    const copy=JSON.parse(await readFile(await dl.path(),"utf8"));assert.equal(copy.schema,"RSDWBaseBuilder.Project.v2");
    await page.evaluate(()=>{const w=worldBuilderDebug.workspace;window.originalCommit=w.store.commit;w.store.commit=async()=>{throw new DOMException("Test quota exceeded","QuotaExceededError");};w.markChanged();return w.saveNow().catch(()=>{});});
    assert.match(await page.textContent("#project-save-status"),/Save Failed/);
    const fallback=page.waitForEvent("download");await page.click("#project-save");assert.equal(JSON.parse(await readFile(await (await fallback).path(),"utf8")).build.placements.length,4);
    await page.evaluate(()=>{worldBuilderDebug.workspace.store.commit=originalCommit;});await page.locator("#project-workspace > .project-menu summary").click();
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),copy);assert.deepEqual((await snapshot()).placements,mixed.placements);return true;
  });
  await step("Both legacy recoveries migrate once, without overwriting sources",async()=>{
    const legacyContext=await browser.newContext({viewport:{width:1600,height:1000}}),p=await legacyContext.newPage();p.setDefaultTimeout(120000);
    await p.goto(url);await p.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
    const sources=await p.evaluate(async fixture=>{
      const free={schema:"RSDWBaseBuilder.Autosave.v1",snapshot:fixture.build};localStorage.setItem("RSDWBaseBuilder.autosave.v1",JSON.stringify(free));
      const {openProjectStore,LEGACY_DB_NAME}=await import("./basebuilder-project-store.js"),old=openProjectStore(indexedDB,LEGACY_DB_NAME);
      const world=structuredClone(fixture);world.schema="RSDWBaseBuilder.Project.v1";world.project_id="legacy-world";world.revision=0;delete world.delivery;
      world.workspace={render_origin_cm:[0,0,0],world_enabled:false,requested_section_id:"x3_y1",visible_world_layers:{terrain:true},orientation:"world",camera:world.workspace.camera};
      const saved=await old.commit(world.project_id,0,world);await old.close();return {free:JSON.stringify(free),world:saved};
    },fixture);
    await p.reload();await p.getByText("Restore project?",{exact:true}).waitFor();const labels=await p.locator("#collection-dialog-choice option").allTextContents();assert.ok(labels.some(x=>x.includes("Free"))&&labels.some(x=>x.includes("World")));
    const check=()=>p.evaluate(async()=>{const {openProjectStore,LEGACY_DB_NAME}=await import("./basebuilder-project-store.js");const old=openProjectStore(indexedDB,LEGACY_DB_NAME);const world=(await old.records())[0].current;await old.close();return {world,free:localStorage.getItem("RSDWBaseBuilder.autosave.v1"),records:(await worldBuilderDebug.workspace.store.records()).length};});
    const a=await check();assert.deepEqual(a.world,sources.world);assert.equal(a.free,sources.free);
    await p.reload();await p.getByText("Restore project?",{exact:true}).waitFor();assert.equal((await check()).records,a.records);
    await legacyContext.close();return {choices:labels,records:a.records,sources_retained:true};
  });
  await step("Reference attachments are explicitly unsaved and excluded from JSON",async()=>{
    const vertices=new Float32Array([0,0,0,1,0,0,0,1,0]);const gltf={asset:{version:"2.0"},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0}}]}],
      buffers:[{byteLength:vertices.byteLength,uri:"data:application/octet-stream;base64,"+Buffer.from(vertices.buffer).toString("base64")}],bufferViews:[{buffer:0,byteOffset:0,byteLength:vertices.byteLength}],
      accessors:[{bufferView:0,componentType:5126,count:3,type:"VEC3",min:[0,0,0],max:[1,1,0]}]};
    const file=resolve(out,"reference.gltf");await writeFile(file,JSON.stringify(gltf));const before=await exported();
    await page.setInputFiles("#reference-file-input",file);await page.waitForFunction(()=>document.querySelector("#project-save-status").textContent.includes("Reference models not saved"));
    assert.deepEqual(await exported(),before);await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());await page.reload();await restore();assert.deepEqual(await exported(),before);
    assert.ok(!(await page.textContent("#project-save-status")).includes("Reference models"));return true;
  });
  await step("Unavailable world retains authored work and Free Build fallback",async()=>{
    const c=await browser.newContext(),p=await c.newPage();p.setDefaultTimeout(120000);await p.route("**/world-region/**",r=>r.abort());await p.goto(url);
    await p.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
    await p.evaluate(fixture=>worldBuilderDebug.workspace.openDocument(fixture,{confirm:false}),fixture);
    const before=await p.evaluate(()=>worldBuilderDebug.snapshot());await p.evaluate(()=>worldBuilderDebug.workspace.setMode("world"));
    assert.deepEqual(await p.evaluate(()=>worldBuilderDebug.snapshot()),before);assert.match(await p.textContent("#world-load-status"),/fetch|load|unavailable|HTTP/i);
    assert.equal(await p.evaluate(async()=>{const T=await import("three");return worldBuilderDebug.surface(new T.Ray(new T.Vector3(0,100,0),new T.Vector3(0,-1,0)));}),null);
    await p.evaluate(()=>worldBuilderDebug.workspace.setMode("free"));assert.deepEqual(await p.evaluate(()=>worldBuilderDebug.snapshot()),before);await c.close();return true;
  });
  const realFiles=["C:/Users/NZXT/Downloads/Grand_Exchange.json","C:/Users/NZXT/Downloads/Looter_Paradise_3.json"];
  for(const mode of args["skip-builds"]?[]:["free","world"]){
    await page.evaluate(mode=>worldBuilderDebug.workspace.setMode(mode),mode);
    if(mode==="world"){await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x3_y1"));}
    for(const file of realFiles){
      await step(`${mode}: ${file.split("/").at(-1)} Original Location and Place Here`,async()=>{
        const input=JSON.parse(await readFile(file,"utf8"));await importFile(file);compareRows(await exported(),input);
        const before=await snapshot();assert.equal(before.ui_collections.length,1);
        if(mode==="world") { await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x3_y1")); }
        else await page.evaluate(()=>worldBuilderDebug.focus());
        await importFile(file,true);const point=await previewPoint();assert.deepEqual(await snapshot(),before);
        await page.keyboard.press("f");await page.mouse.wheel(0,-100);const preview=await page.evaluate(()=>worldBuilderDebug.preview());assert.equal(preview.state.yaw,195);
        await page.mouse.click(point.x,point.y);await ready();const after=await snapshot();assert.equal(after.placements.length,input.pieces.length);assert.equal(after.ui_collections.length,1);
        const {relocateBuildState}=await import("../../website/basebuilder-build-import.js");for(let i=0;i<after.placements.length;i++){const expected=relocateBuildState(before.placements[i].state,preview.pivot,preview.state);for(const key of ["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"])assert.ok(Math.abs(after.placements[i].state[key]-expected[key])<1e-4,`${i} ${key}`);}
        await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snapshot(),before);
        await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());await page.reload();await restore();assert.deepEqual(await snapshot(),before);
        return {objects:before.placements.length};
      });
    }
  }
  await step("Place Build transforms hidden actors, preserves identities, cancels and undoes",async()=>{
    const p=structuredClone(fixture);p.workspace.authoring_mode="world";p.workspace.world_build=(await capture()).workspace.world_build;p.dataset.world_sha256=(await capture()).dataset.world_sha256;
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),p);await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));const before=await snapshot();
    await page.evaluate(()=>worldBuilderDebug.placeBuild());await previewPoint();assert.deepEqual(await snapshot(),before);await page.keyboard.press("Escape");assert.deepEqual(await snapshot(),before);
    await page.evaluate(()=>worldBuilderDebug.placeBuild());const point=await previewPoint();await page.mouse.wheel(0,-100);const preview=await page.evaluate(()=>worldBuilderDebug.preview());await page.mouse.click(point.x,point.y);await ready();
    const after=await snapshot();const {relocateBuildState}=await import("../../website/basebuilder-build-import.js");for(let i=0;i<after.placements.length;i++){const expected=relocateBuildState(before.placements[i].state,preview.pivot,preview.state);assert.deepEqual({...after.placements[i],state:before.placements[i].state},before.placements[i]);for(const k of ["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"])assert.ok(Math.abs(after.placements[i].state[k]-expected[k])<1e-4);}
    assert.deepEqual(after.ui_collections,before.ui_collections);assert.equal(after.anchor_piece_id,before.anchor_piece_id);
    await writeFile(resolve(out,"world-mixed.rsdwproject.json"),JSON.stringify(await capture(),null,2));await writeFile(resolve(out,"world-mixed-expected.json"),JSON.stringify(await exported(),null,2));await screen("world-mixed");
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snapshot(),before);return {hidden_transformed:true,one_undo:true};
  });
  await step("Narrow workspace controls and nonblank canvas",async()=>{await page.setViewportSize({width:430,height:932});await screen("mobile");assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),430);return true;});
  assert.deepEqual(errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=String(error.stack||error);console.error(report.error);process.exitCode=1;}
finally{await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));await browser.close();}
