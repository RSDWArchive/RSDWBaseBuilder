import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";

const {values:args}=parseArgs({options:{url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1"},out:{type:"string"},chrome:{type:"string"},cycles:{type:"string",default:"20"},large:{type:"boolean",default:false},"large-only":{type:"boolean",default:false},fixture:{type:"string"}}});
if(!args.out)throw Error("Pass --out with an ignored local directory");
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp");
const out=resolve(args.out);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true});
const page=await context.newPage();const errors=[];page.on("pageerror",e=>errors.push(String(e)));
const report={schema:"RSDW.WorldBuilderAcceptance.v1",started:new Date().toISOString(),status:"running",checks:[],manual_in_game:"pending"};
async function step(name,run){const start=performance.now();const detail=await run();report.checks.push({name,status:"passed",ms:Math.round(performance.now()-start),detail});console.log(name+": passed");await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));return detail;}
async function ready(){await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.layer.getStatus().phase==="ready",null,{timeout:120000});await page.waitForFunction(()=>document.querySelector("#stage-loading").hidden);}
async function snapshot(){return page.evaluate(()=>({build:worldBuilderDebug.snapshot(),export:worldBuilderDebug.export()}));}
async function unloadWorld(){if(!await page.locator("#world-unload-section").isVisible())await page.click(".world-advanced-menu summary");await page.click("#world-unload-section");}
async function changeSection(id){await page.evaluate(async id=>{document.querySelector("#world-section-select").value=id;await worldBuilderDebug.workspace.runWorld("load");},id);await page.waitForFunction(id=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionId===id,id,{timeout:120000});}
try {
  if(args["large-only"]){
    assert.ok(args.fixture,"Pass --fixture for the focused large-build suite");
    const project=JSON.parse(await readFile(args.fixture,"utf8"));(project.workspace.world_build||project.workspace).world_enabled=false;
    await page.goto(args.url);await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
    const {testLargeBuild}=await import("./WorldBuilderLargeChecks.mjs");await testLargeBuild({page,step,out,project});
  } else {
  await step("Local section startup",async()=>{await page.goto(args.url);await page.waitForFunction(()=>window.worldBuilderDebug?.workspace.getOverviewMetrics()?.loaded>0);
    await page.click(".world-advanced-menu summary");await page.uncheck("#world-streaming");await changeSection("x3_y1");await ready();return page.evaluate(()=>worldBuilderDebug.state());});
  await step("Serializer and transform contracts",async()=>page.evaluate(async()=>{
    const {serializeBuildingJson,editorTransformFromJson}=await import("./basebuilder-serialization.js");
    const transforms=await import("./basebuilder-transforms.js");
    const {ueMatrix}=await import("./world/world-transforms.js");
    const state={x:176400.25,y:-75600,z:83.5,pitch:17,yaw:45,roll:-23,scale_x:1.2,scale_y:0.8,scale_z:2};
    const mk=(id,kind,hidden=false)=>({id,state:{...state},metadata:{piece_id:1,item_count:3},hidden,target:{asset_kind:kind,asset_stem:"test",export:{piece_data_index:42,class_name:"test",item_asset_name:"item",actor_class:"BP_Test_C"}}});
    const rows=[mk("p","building_piece"),mk("i","item"),mk("b","bp"),mk("hidden","bp",true)];
    const result=serializeBuildingJson({placements:new Map(rows.map(r=>[r.id,r])),buildSchema:"rsdwtools.buildings.v1",buildName:"fixture",anchorPieceId:1,allocatePieceId:()=>99},123);
    if(result.pieces.length!==1||result.items.length!==1||result.actors.length!==1||result.anchor_piece_id!==1||result.generated_unix!==123)throw Error("Export shape changed");
    for(const row of [...result.pieces,...result.items,...result.actors]){
      if(row.pitch!==-17||row.roll!==23||row.yaw!==45||row.scale_z!==2||row.x!==176400.25)throw Error("Export transform changed");
      const roundtrip=editorTransformFromJson(row);for(const key of Object.keys(state))if(roundtrip[key]!==state[key])throw Error("Rotation round trip failed");
    }
    if(JSON.stringify(result).includes("collection"))throw Error("Editor metadata leaked");
    rows[0].hidden=true;
    if("anchor_piece_id" in serializeBuildingJson({placements:new Map(rows.map(r=>[r.id,r])),buildSchema:result.schema,buildName:"fixture",anchorPieceId:1,allocatePieceId:()=>99}))throw Error("Hidden anchor leaked");
    const matrix=transforms.ueMatrixFromTransform(state),origin={x:176400,y:75600,z:8000};
    const a=transforms.ueMatrixRowsToThreeMatrix4(matrix,origin),b=ueMatrix(matrix,[origin.x,origin.y,origin.z]);
    if(a.elements.some((v,i)=>Math.abs(v-b.elements[i])>1e-9))throw Error("World/editor matrix mismatch");
    return {mixed_json:true,pitch_roll:true,hidden_anchor:true,origin_matrix:true};
  }));
  const fixture=await step("Create mixed authored fixture",async()=>page.evaluate(async()=>{
    const d=worldBuilderDebug,T=await import("three");
    const targets=["Foundation","Wall","Floor","Roof"].map(name=>d.catalog.targets.find(t=>t.asset_kind==="building_piece"&&t.display_name.includes(name)&&!t.display_name.includes("Torch")));
    targets.push(d.catalog.targets.find(t=>t.asset_kind==="item"),d.catalog.targets.find(t=>t.asset_kind==="bp"&&t.asset_stem==="BP_NPC_Doric_Dowdun_C")||d.catalog.targets.find(t=>t.asset_kind==="bp"));
    const origin=d.snapshot().view_offset,hit=d.surface(new T.Ray(new T.Vector3((190400-origin.x)/100,1000,(65600-origin.y)/100),new T.Vector3(0,-1,0)));
    if(!hit)throw Error("No terrain at test location");
    for(let i=0;i<targets.length;i++)await d.add(targets[i].target_id,{x:190400+(i%3)*500,y:65600+Math.floor(i/3)*500,z:hit.point.y*100+origin.z,pitch:i<4?0:17,yaw:45,roll:i<4?0:-23,scale_x:1,scale_y:1,scale_z:i<4?1:1.2});
    d.select(["obj_1"]);d.anchor();d.select(["obj_5"]);d.hide();d.select(["obj_2","obj_3"]);d.focus();await d.workspace.saveNow();return {build:d.snapshot(),export:d.export()};
  }));
  await step("Themed collection UI",async()=>{
    await page.click("#placed-new-collection");await page.fill("#collection-dialog-input","World test walls");await page.click("#collection-dialog-submit");
    await page.waitForFunction(()=>worldBuilderDebug.snapshot().ui_collections.length===1);
    const value=await page.locator("#placed-collection-select option").last().getAttribute("value");
    await page.selectOption("#placed-collection-select",value);await page.click("#placed-move-selected");
    const b=await snapshot();assert.equal(b.build.placements.filter(p=>p.ui_collection_id===value).length,2);return value;
  });
  await step("Selection updates rows without replacing the placed tree",async()=>{
    const result=await page.evaluate(()=>{
      const row=document.querySelector('[data-placement-id="obj_1"]');
      worldBuilderDebug.select(["obj_1"]);
      return {same:row===document.querySelector('[data-placement-id="obj_1"]'),active:row.classList.contains("is-active"),
        selected:document.querySelector(".placed-collection.is-active .placed-group-select .placed-meta")?.textContent};
    });assert.ok(result.same&&result.active);assert.match(result.selected,/1 selected/);return result;
  });
  const baseline=await snapshot();
  await step("Unload and replacement do not mutate authored data",async()=>{
    await unloadWorld();assert.deepEqual(await snapshot(),baseline);
    await changeSection("x4_y3");assert.deepEqual(await snapshot(),baseline);
    await changeSection("x3_y1");assert.deepEqual(await snapshot(),baseline);return true;
  });
  await step("Edit and undo with world unloaded",async()=>{
    await unloadWorld();await page.evaluate(()=>worldBuilderDebug.select(["obj_1"]));
    const before=await snapshot();await page.fill('[data-transform="x"]',String(before.build.placements[0].state.x+25));await page.dispatchEvent('[data-transform="x"]',"change");
    assert.notEqual((await snapshot()).build.placements[0].state.x,before.build.placements[0].state.x);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snapshot(),before);return true;
  });
  const project=await page.evaluate(async()=>{await worldBuilderDebug.workspace.saveNow();return worldBuilderDebug.workspace.capture();});
  await writeFile(resolve(out,"sample.rsdwproject.json"),JSON.stringify(project,null,2));
  await writeFile(resolve(out,"sample-building.json"),JSON.stringify(fixture.export,null,2));
  await step("Save Project download and game export separation",async()=>{
    await page.locator(".project-menu").first().locator("summary").click();
    const pending=page.waitForEvent("download");await page.click("#project-save");const download=await pending;await download.saveAs(resolve(out,"downloaded.rsdwproject.json"));
    const exported=page.waitForEvent("download");await page.click("#export-json");await page.click("#collection-dialog-submit");const build=await exported;await build.saveAs(resolve(out,"downloaded-building.json"));
    await page.locator(".project-menu").first().locator("summary").click();
    return {project:download.suggestedFilename(),build:build.suggestedFilename()};
  });
  await step("Reload and recover committed project",async()=>{
    await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
    await page.waitForFunction(()=>worldBuilderDebug?.state().placements===6);
    assert.deepEqual((await snapshot()).build,project.build);assert.deepEqual((await snapshot()).export,baseline.export);return true;
  });
  await step("Invalid project rejection is nondestructive",async()=>page.evaluate(async input=>{
    const d=worldBuilderDebug,initial=JSON.stringify(d.snapshot());const rejected=[];
    for(const kind of ["target","id","version","transform","anchor","counter","origin"]){
      const p=structuredClone(input);
      if(kind==="target")p.build.placements[0].target_id="unavailable";
      if(kind==="id")p.build.placements[1].id=p.build.placements[0].id;
      if(kind==="version")p.dataset.game_version="wrong";
      if(kind==="transform")p.build.placements[0].state.x=null;
      if(kind==="anchor")p.build.anchor_piece_id=999999;
      if(kind==="counter")p.build.next_object_id=1;
      if(kind==="origin")p.workspace.render_origin_cm[0]+=1;
      let failed=false;try{await d.workspace.openDocument(p,{confirm:false});}catch{failed=true;}
      if(!failed||initial!==JSON.stringify(d.snapshot()))throw Error("Unsafe validation: "+kind);rejected.push(kind);
    }
    return rejected;
  },project));
  await step("Collection-only and item/BP-only projects",async()=>{
    const only=structuredClone(project);only.build.placements=only.build.placements.slice(-2);only.build.anchor_piece_id=0;only.build.selected_ids=[];
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),only);
    assert.equal((await snapshot()).build.placements.length,2);assert.equal((await snapshot()).export.pieces.length,0);
    const empty=structuredClone(only);empty.build.placements=[];
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),empty);
    assert.deepEqual((await snapshot()).build.ui_collections,empty.build.ui_collections);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);return true;
  });
  await step("Gizmo hotkeys, below-zero picking and undo persistence",async()=>{
    await page.evaluate(()=>worldBuilderDebug.select(["obj_6"]));
    for(const [key,mode] of [["g","translate"],["r","rotate"],["s","scale"]]){
      await page.keyboard.press(key);assert.equal(await page.evaluate(()=>worldBuilderDebug.state().gizmo),mode);
      await page.keyboard.press(key);assert.equal(await page.evaluate(()=>worldBuilderDebug.state().gizmo),"");
    }
    await page.fill('[data-transform="z"]',"-5000");await page.dispatchEvent('[data-transform="z"]',"change");
    await page.evaluate(()=>{const d=worldBuilderDebug,p=d.snapshot().placements.at(-1).state,o=d.snapshot().view_offset;d.controls.target.set((p.x-o.x)/100,(p.z-o.z)/100+1,(p.y-o.y)/100);d.camera().position.copy(d.controls.target).add({x:10,y:55,z:10});d.controls.update();});
    const picked=await page.evaluate(async()=>{
      const d=worldBuilderDebug,T=await import("three"),p=d.snapshot().placements.at(-1),o=d.snapshot().view_offset;
      const v=new T.Vector3((p.state.x-o.x)/100,(p.state.z-o.z)/100+1,(p.state.y-o.y)/100).project(d.camera());
      const r=document.querySelector("#builder-stage canvas").getBoundingClientRect();return d.pick({clientX:r.x+(v.x+1)*r.width/2,clientY:r.y+(1-v.y)*r.height/2});
    });assert.equal(picked,"obj_6");
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    await page.evaluate(()=>worldBuilderDebug.undo());
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    const saved=await page.evaluate(async()=>{const w=worldBuilderDebug.workspace;return (await w.store.read(w.capture().project_id)).current;});
    assert.equal(saved.build.placements.at(-1).state.z,project.build.placements.at(-1).state.z);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);return true;
  });
  await step("Failed authored model staging preserves live project and retries",async()=>{
    const replacement=await page.evaluate(p=>{
      const target=worldBuilderDebug.catalog.targets.find(t=>t.asset_stem==="BP_DragonKuldraHeart_Character_C");
      const input=structuredClone(p);input.build.placements.at(-1).target_id=target.target_id;
      return {input,path:target.components[0].gltf_path};
    },project);
    const before=await snapshot(),pattern="**/"+replacement.path;
    await page.route(pattern,route=>route.fulfill({status:503,body:"Injected missing model"}));
    const failure=await page.evaluate(async p=>{try{await worldBuilderDebug.workspace.openDocument(p,{confirm:false});return null;}catch(e){return e.message;}},replacement.input);
    assert.ok(failure);assert.deepEqual(await snapshot(),before);await page.unroute(pattern);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),replacement.input);
    assert.equal((await snapshot()).build.placements.at(-1).target_id,replacement.input.build.placements.at(-1).target_id);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);return failure;
  });
  await step("Build import and append keep absolute coordinates",async()=>{
    const payload=Buffer.from(JSON.stringify(baseline.export));
    await page.click("#import-json");await page.click("#collection-dialog-submit");
    await page.setInputFiles("#file-input",{name:"fixture.json",mimeType:"application/json",buffer:payload});
    await page.waitForFunction(()=>!worldBuilderDebug.busy()&&worldBuilderDebug.state().placements===5);
    assert.deepEqual((await snapshot()).export,baseline.export);
    await page.click("#import-json");await page.click("#collection-dialog-secondary");
    await page.setInputFiles("#file-input",{name:"fixture.json",mimeType:"application/json",buffer:payload});
    await page.waitForFunction(()=>!worldBuilderDebug.busy()&&worldBuilderDebug.state().placements===10);
    const appended=(await snapshot()).export;assert.equal(new Set(appended.pieces.map(p=>p.piece_id)).size,8);
    assert.equal(appended.anchor_piece_id,baseline.export.anchor_piece_id);
    assert.equal(appended.pieces[4].x,baseline.export.pieces[0].x);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual((await snapshot()).export,baseline.export);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);return true;
  });
  await step("Storage revision conflict preserves last good save",async()=>page.evaluate(async input=>{
    const {openProjectStore}=await import("./basebuilder-project-store.js"),a=openProjectStore(),b=openProjectStore();
    const id=crypto.randomUUID(),p={...input,project_id:id,revision:0};
    await a.commit(id,0,p);let rejected=false;try{await b.commit(id,0,p);}catch(e){rejected=e.name==="RevisionConflict";}
    if(!rejected||(await a.read(id)).current.revision!==1)throw Error("Conflict overwrote project");
    await a.commit(id,1,p);const record=await a.read(id);if(record.previous.revision!==1||record.current.revision!==2)throw Error("Recovery revision not atomic");return true;
  },project));
  await step("Storage failure is visible and keeps recovery data",async()=>page.evaluate(async()=>{
    const w=worldBuilderDebug.workspace;await w.saveNow();const p=w.capture(),before=await w.store.read(p.project_id),commit=w.store.commit;
    w.store.commit=async()=>{throw Error("Simulated quota failure");};w.markChanged();let failed=false;
    try{await w.saveNow();}catch{failed=true;}finally{w.store.commit=commit;}
    if(!failed||!document.querySelector("#project-save-status").textContent.startsWith("Save Failed"))throw Error("False Saved state");
    if(JSON.stringify(await w.store.read(p.project_id))!==JSON.stringify(before))throw Error("Recovery was damaged");return true;
  }));
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
  await step("Empty project restores empty, including collections",async()=>{
    await page.evaluate(()=>worldBuilderDebug.clear());await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
    await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
    assert.equal((await snapshot()).build.placements.length,0);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);return true;
  });
  await step("Unloaded world cannot supply a phantom ground surface",async()=>page.evaluate(async()=>{
    const T=await import("three"),d=worldBuilderDebug;await d.workspace.runWorld("unload");
    if(d.surface(new T.Ray(new T.Vector3(10000,1000,10000),new T.Vector3(0,-1,0))))throw Error("Stale world hit");return true;
  }));
  const cycleBaseline=await snapshot();
  await step("Repeated world disposal and stale load cancellation",async()=>{
    const resources=[];
    const memory=await context.newCDPSession(page);
    for(let i=0;i<Number(args.cycles);i++){
      await changeSection(i%2?"x4_y3":"x3_y1");
      // A restored world-disabled project has no overview until its first Load.
      if(i===0)await page.waitForFunction(()=>{
        const m=worldBuilderDebug.workspace.getOverviewMetrics();return m?.total>0&&m.loaded===m.total;
      },null,{timeout:240000});
      await unloadWorld();
      await page.evaluate(()=>worldBuilderDebug.workspace.layer.settled());
      assert.deepEqual(await snapshot(),cycleBaseline);
      await memory.send("HeapProfiler.collectGarbage");
      resources.push(await page.evaluate(()=>({...worldBuilderDebug.renderer.info.memory,roots:worldBuilderDebug.workspace.layer.getMetrics().worldRoots,
        heap_bytes:performance.memory?.usedJSHeapSize,programs:worldBuilderDebug.renderer.info.programs.length,
        depth:worldBuilderDebug.workspace.layer.getMetrics().depth,authored:worldBuilderDebug.performance(),
        cache:worldBuilderDebug.workspace.layer.getMetrics().cache,overview:worldBuilderDebug.workspace.getOverviewMetrics()})));
      await writeFile(resolve(out,"ResourceCycles.json"),JSON.stringify(resources,null,2));
      console.log(`Resource cycle ${i+1}: ${resources.at(-1).geometries} geometry / ${resources.at(-1).textures} textures`);
    }
    assert.ok(resources.every(r=>r.roots===0));
    assert.ok(resources.every(r=>r.cache.bundles.entries===0&&r.cache.textures.entries===0),"World detail leases remain after unload");
    assert.ok(resources.at(-1).geometries<=resources[1].geometries+2,"World geometry grows across unloads");
    assert.ok(resources.at(-1).textures<=resources[1].textures+2,"World textures grow across unloads");
    assert.ok(resources.at(-1).depth.variants<=resources[1].depth.variants+2,"Depth variants grow across unloads");
    await memory.detach();
    await page.evaluate(async()=>{document.querySelector("#world-section-select").value="x3_y1";const p=worldBuilderDebug.workspace.runWorld("load");await worldBuilderDebug.workspace.runWorld("unload");await p;});
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getMetrics().worldRoots),0);return resources;
  });
  await changeSection("x3_y1");
  await step("Terrain drag, preview shortcuts, E and move preview",async()=>{
    await page.evaluate(()=>{worldBuilderDebug.camera().position.set(165,40,-75);worldBuilderDebug.controls.target.set(140,15,-100);worldBuilderDebug.controls.update();});
    await page.fill("#asset-search","Foundation");
    const row=await page.locator(".asset-row").first().boundingBox(),stage=await page.locator("#builder-stage").boundingBox();
    const x=stage.x+stage.width/2,y=stage.y+stage.height/2;
    await page.mouse.move(row.x+32,row.y+32);await page.mouse.down();await page.mouse.move(x,y,{steps:12});
    await page.waitForFunction(()=>worldBuilderDebug.preview()?.canDrop);
    const start=await page.evaluate(()=>worldBuilderDebug.preview());
    await page.keyboard.press("r");await page.keyboard.press("f");await page.mouse.wheel(0,-100);
    await page.keyboard.down("Control");await page.mouse.wheel(0,-100);await page.keyboard.up("Control");
    const preview=await page.evaluate(()=>worldBuilderDebug.preview());
    assert.equal(preview.step,1);assert.equal(preview.state.yaw,181);assert.ok(Math.abs(preview.state.z-start.state.z-10)<0.01);
    assert.equal(await page.inputValue("#asset-search"),"Foundation");
    await page.mouse.up();await page.waitForFunction(()=>worldBuilderDebug.state().placements===7);
    await page.keyboard.press("e");await page.mouse.move(x+70,y);await page.waitForFunction(()=>worldBuilderDebug.preview()?.canDrop);
    await page.mouse.click(x+70,y);await page.waitForFunction(()=>worldBuilderDebug.state().placements===8);
    await page.keyboard.press("Escape");
    const contact=await page.evaluate(async()=>{
      await new Promise(resolve=>requestAnimationFrame(resolve));
      const d=worldBuilderDebug,T=await import("three"),snapshot=d.snapshot(),p=snapshot.placements.at(-1),o=snapshot.view_offset;
      const point=new T.Vector3((p.state.x-o.x)/100,(p.state.z-o.z)/100,(p.state.y-o.y)/100).project(d.camera());
      const rect=document.querySelector("#builder-stage canvas").getBoundingClientRect();
      const cx=rect.x+(point.x+1)*rect.width/2,cy=rect.y+(1-point.y)*rect.height/2;
      for(let dy=-40;dy<=40;dy+=4)for(let dx=-40;dx<=40;dx+=4){
        const event={clientX:cx+dx,clientY:cy+dy};
        if(d.pick(event,{allowScreenFallback:false})===p.id)return event;
      }
      return null;
    });
    assert.ok(contact,"New piece must be directly raycast-selectable");
    await page.mouse.move(contact.clientX,contact.clientY);await page.mouse.down();await page.mouse.move(contact.clientX+40,contact.clientY,{steps:12});
    await page.waitForFunction(()=>worldBuilderDebug.preview()?.canDrop);
    // A world unload request must wait for the active preview to finish.
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("unload"));
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().phase),"ready");
    await page.mouse.up();await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().phase==="unloaded");
    assert.equal(await page.evaluate(()=>worldBuilderDebug.state().placements),8);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);await changeSection("x3_y1");return true;
  });
  await step("World request failure and identity mismatch retain authored work",async()=>{
    const before=await snapshot();
    const pattern="**/sections/x4_y3.json";
    await page.route(pattern,route=>route.fulfill({status:503,body:"Injected unavailable section"}));
    if(!await page.locator("#world-section-select").isVisible())await page.click(".world-location-menu summary");
    await page.selectOption("#world-section-select","x4_y3");
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("load"));
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().phase),"partial");
    assert.equal(await page.evaluate(()=>worldBuilderDebug.workspace.layer.getStatus().failed[0].id),"x4_y3");
    assert.deepEqual(await snapshot(),before);await page.unroute(pattern);await changeSection("x4_y3");
    const mismatch=structuredClone(project);mismatch.dataset.world_sha256="mismatched";(mismatch.workspace.world_build||mismatch.workspace).world_enabled=true;
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),mismatch);
    assert.deepEqual((await snapshot()).build,project.build);assert.match(await page.textContent("#world-load-status"),/identity differs/);
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);await changeSection("x3_y1");return true;
  });
  await step("Desktop screenshot and camera projection",async()=>{
    await page.evaluate(()=>worldBuilderDebug.focus());await page.screenshot({path:resolve(out,"desktop.png")});
    const first=await page.locator("#builder-stage canvas").screenshot();
    await page.keyboard.press("Numpad5");const next=await page.locator("#builder-stage canvas").screenshot();assert.notDeepEqual(first,next);
    const stats=await sharp(first).stats();assert.ok(stats.channels.slice(0,3).some(c=>c.stdev>10));await page.keyboard.press("Numpad5");return stats.channels.slice(0,3).map(c=>c.stdev);
  });
  await step("Mobile viewport",async()=>{
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:resolve(out,"mobile.png"),fullPage:true});
    const sizes=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,canvases:document.querySelectorAll("#builder-stage canvas").length}));assert.equal(sizes.scroll,sizes.width);assert.equal(sizes.canvases,1);await page.setViewportSize({width:1600,height:1000});return sizes;
  });
  await step("Save Copy resolves an active revision conflict",async()=>{
    const old=await page.evaluate(async()=>{
      const w=worldBuilderDebug.workspace;await w.saveNow();const p=w.capture();
      await w.store.commit(p.project_id,p.revision,p);w.markChanged();
      let conflict=false;try{await w.saveNow();}catch(e){conflict=e.name==="RevisionConflict";}
      if(!conflict)throw Error("Active conflict was not surfaced");return p;
    });
    await page.locator(".project-menu").first().locator("summary").click();
    const pending=page.waitForEvent("download");await page.click("#project-copy");await pending;
    await page.waitForFunction(()=>document.querySelector("#project-save-status").textContent==="Saved");
    const result=await page.evaluate(async old=>{const w=worldBuilderDebug.workspace;return {id:w.capture().project_id,prior:(await w.store.read(old.project_id)).current.revision};},old);
    assert.notEqual(result.id,old.project_id);assert.equal(result.prior,old.revision+1);
    await page.locator(".project-menu").first().locator("summary").click();return true;
  });
  await step("Failed recovery retains last saved record until explicit New",async()=>{
    const isolated=await browser.newContext({viewport:{width:1600,height:1000}}),recovery=await isolated.newPage();
    await recovery.goto(args.url.split("?")[0]);await recovery.waitForFunction(()=>document.querySelector("#stage-loading").hidden);
    const corrupt=structuredClone(project);corrupt.project_id="recovery-failure-fixture";corrupt.revision=0;corrupt.build.placements[0].target_id="not-in-catalog";
    await recovery.evaluate(async p=>{const {openProjectStore}=await import("./basebuilder-project-store.js");await openProjectStore().commit(p.project_id,0,p);},corrupt);
    await recovery.goto(args.url);await recovery.getByText("Restore project?",{exact:true}).waitFor();await recovery.click("#collection-dialog-submit");
    await recovery.waitForFunction(()=>document.querySelector("#project-save-status").textContent.startsWith("Save Failed"));
    await recovery.waitForTimeout(600);
    assert.equal(await recovery.evaluate(async()=>(await worldBuilderDebug.workspace.store.last()).current.project_id),corrupt.project_id);
    await isolated.close();return true;
  });
  await step("Generate visible mixed sample for manual game review",async()=>{
    const manual=structuredClone(project);(manual.workspace.world_build||manual.workspace).world_enabled=true;(manual.workspace.world_build||manual.workspace).requested_section_id="x3_y1";
    manual.build.placements.forEach(p=>{p.hidden=false;});manual.build.selected_ids=[];
    manual.build.build_name="World Milestone 1 Review";
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),manual);
    const generated=await page.evaluate(()=>({project:worldBuilderDebug.workspace.capture(),building:worldBuilderDebug.export()}));
    assert.equal(generated.building.items.length,1);assert.equal(generated.building.actors.length,1);
    await writeFile(resolve(out,"manual-review.rsdwproject.json"),JSON.stringify(generated.project,null,2));
    await writeFile(resolve(out,"manual-review-building.json"),JSON.stringify(generated.building,null,2));return true;
  });
  await step("Free entry shares recovery and can start without world context",async()=>{
    const normal=await context.newPage();const localErrors=[];normal.on("pageerror",e=>localErrors.push(String(e)));
    await normal.goto(args.url.split("?")[0]);await normal.getByText("Restore project?",{exact:true}).waitFor();await normal.click("#collection-dialog-cancel");await normal.waitForFunction(()=>document.querySelector("#stage-loading").hidden);
    const result=await normal.evaluate(()=>({worldVisible:!document.querySelector("#world-workspace").hidden,referenceDisabled:document.querySelector("#import-reference").disabled,legacy:localStorage.getItem("RSDWBaseBuilder.autosave.v1")}));
    assert.equal(result.worldVisible,false);assert.equal(result.referenceDisabled,false);assert.equal(result.legacy,null);assert.deepEqual(localErrors,[]);await normal.close();return result;
  });
  if(args.large){const {testLargeBuild}=await import("./WorldBuilderLargeChecks.mjs");await testLargeBuild({page,step,out,project});}
  }
  assert.deepEqual(errors,[]);report.status="passed_pending_in_game_review";
}catch(error){report.status="failed";report.error=String(error.stack||error);console.error(error);process.exitCode=1;}
finally{report.finished=new Date().toISOString();report.errors=errors;await writeFile(resolve(out,"Acceptance.json"),JSON.stringify(report,null,2));await browser.close();}
