import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir, readFile, writeFile} from "node:fs/promises";
import {resolve, basename} from "node:path";
import {parseArgs} from "node:util";
import {execFileSync} from "node:child_process";
import {createHash} from "node:crypto";

const {values:args}=parseArgs({options:{file:{type:"string",multiple:true},out:{type:"string",default:"_build/world-build-import"}}});
if(args.file?.length!==2)throw Error("Pass --file twice for the two real build JSON files");
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp");
const files=await Promise.all(args.file.map(async path=>({path:resolve(path),data:JSON.parse(await readFile(path,"utf8"))})));
const out=resolve(args.out);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const context=await browser.newContext({viewport:{width:1600,height:1000},acceptDownloads:true});
const page=await context.newPage(),errors=[];page.on("pageerror",error=>errors.push(String(error)));
page.setDefaultTimeout(120000);
const report={status:"running",checks:[],errors};
async function step(name,run){const start=performance.now(),detail=await run();report.checks.push({name,ms:Math.round(performance.now()-start),detail});console.log(name+": passed");await writeFile(resolve(out,"ImportTests.json"),JSON.stringify(report,null,2));}
const snap=()=>page.evaluate(()=>worldBuilderDebug.snapshot());
const exported=()=>page.evaluate(()=>worldBuilderDebug.export());
const ready=()=>page.waitForFunction(()=>window.worldBuilderDebug&&!worldBuilderDebug.busy()&&document.querySelector("#stage-loading").hidden);
async function chooseFile(file,{append=false,here=false}={}){
  await page.click("#import-json");await page.click(append?"#collection-dialog-secondary":"#collection-dialog-submit");
  await page.setInputFiles("#file-input",file.path);
  await page.getByText("Import Location",{exact:true}).waitFor();
  await page.click(here?"#collection-dialog-secondary":"#collection-dialog-submit");
  if(here)await page.waitForFunction(()=>worldBuilderDebug.preview()?.buildCount>0);
  else await ready();
}
function assertExportRows(output,input,offset=0){
  for(let i=0;i<input.pieces.length;i++){
    const a=output.pieces[offset+i],b=input.pieces[i];
    assert.ok(a,`Missing piece ${i}`);
    for(const key of ["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"]){
      const precision=key.startsWith("scale")?1e6:1e3;
      assert.equal(a[key],Math.round(b[key]*precision)/precision,`Piece ${i} ${key}`);
    }
    assert.equal(a.class_name,b.class_name,`Class ${i}`);
    assert.equal(a.piece_data_name,b.piece_data_name,`Data asset ${i}`);
  }
  assert.equal(output.schema,"rsdwtools.buildings.v1");
  assert.equal(output.items.length,0);assert.equal(output.actors.length,0);
  assert.ok(!JSON.stringify(output).includes("collection"));
}
async function previewPoint(){
  // Search the real terrain raycasts, not a fabricated zero-height plane.
  const rect=await page.locator("#builder-stage canvas").first().boundingBox();
  for(const [x,y]of [[.5,.5],[.5,.6],[.4,.55],[.6,.55],[.5,.7],[.3,.6]]){
    const point={x:rect.x+rect.width*x,y:rect.y+rect.height*y};await page.mouse.move(point.x,point.y);
    if(await page.evaluate(()=>worldBuilderDebug.preview()?.canDrop))return point;
  }
  throw Error("No real surface found for whole-build preview");
}
try{
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1&buildImportTest=1");await ready();
  await page.waitForFunction(()=>worldBuilderDebug.workspace.getOverviewMetrics()?.loaded>0);
  // Limit test world residency to the selected section; never changes the user's browser.
  await page.click(".world-advanced-menu summary");await page.uncheck("#world-streaming");
  await page.click(".world-advanced-menu summary");
  await step("Grand Exchange at original coordinates",async()=>{
    await chooseFile(files[0]);const build=await snap(),json=await exported();
    assert.equal(build.placements.length,files[0].data.pieces.length);assertExportRows(json,files[0].data);
    assert.equal(build.ui_collections.length,1);assert.ok(build.placements.every(p=>p.ui_collection_id===build.ui_collections[0].id));
    assert.equal(build.anchor_piece_id,0);return {pieces:build.placements.length,collection:build.ui_collections[0].name};
  });
  const first=await snap();
  await step("Looter Paradise append at original coordinates",async()=>{
    await chooseFile(files[1],{append:true});const build=await snap(),json=await exported();
    assert.deepEqual(build.placements.slice(0,first.placements.length),first.placements);
    assert.equal(build.ui_collections.length,2);assert.equal(build.placements.length,14097);
    assertExportRows(json,files[0].data);assertExportRows(json,files[1].data,first.placements.length);
    const ids=build.placements.map(p=>p.metadata.piece_id);assert.equal(new Set(ids).size,ids.length);assert.ok(ids.every(id=>id>0));
    await writeFile(resolve(out,"original-location-export.json"),JSON.stringify(json));
    return {pieces:build.placements.length,collections:build.ui_collections.map(c=>c.name)};
  });
  await step("Append is one undo action",async()=>{await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snap(),first);});
  await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));
  await page.waitForFunction(()=>worldBuilderDebug.workspace.layer.getStatus().loadedSectionIds.includes("x3_y1"));
  const beforePreview=await snap();
  await step("Whole-build cancel leaves project and export unchanged",async()=>{
    const beforeExport=await exported();await chooseFile(files[0],{append:true,here:true});await previewPoint();
    assert.deepEqual(await snap(),beforePreview);assert.deepEqual(await exported(),beforeExport);
    await page.keyboard.press("x");await page.keyboard.press("Control+z");
    assert.deepEqual(await snap(),beforePreview);
    await page.keyboard.press("Escape");assert.equal(await page.evaluate(()=>worldBuilderDebug.preview()),null);
    assert.deepEqual(await snap(),beforePreview);assert.deepEqual(await exported(),beforeExport);
    assert.equal(await page.locator(".inspector").evaluate(el=>el.inert),false);
  });
  for(let fileIndex=0;fileIndex<files.length;fileIndex++){
    const file=files[fileIndex];
    await step(`${basename(file.path)} whole-build preview and placement`,async()=>{
      const before=await snap(),jsonBefore=await exported();
      await chooseFile(file,{append:true,here:true});const point=await previewPoint();
      await page.mouse.wheel(0,-100);await page.keyboard.press("r");await page.mouse.wheel(0,-100);
      await page.keyboard.down("Control");await page.mouse.wheel(0,-100);await page.keyboard.up("Control");
      await page.waitForFunction(()=>worldBuilderDebug.preview()?.state.yaw===16);
      const preview=await page.evaluate(()=>worldBuilderDebug.preview());
      assert.equal(preview.buildCount,file.data.pieces.length);assert.equal(preview.step,1);
      const ghost=await page.evaluate(()=>{
        const root=worldBuilderDebug.scene.getObjectByName("Whole build preview");let instances=0,meshes=0,translucent=true;
        root.traverse(o=>{if(!o.isMesh)return;meshes++;instances+=o.isInstancedMesh?o.count:1;
          translucent&&=[o.material].flat().every(m=>m.transparent&&m.opacity===.48);});
        return {visible:root.visible,instances,meshes,translucent};
      });assert.ok(ghost.visible&&ghost.translucent);assert.ok(ghost.instances>=file.data.pieces.length);assert.ok(ghost.meshes<500);
      assert.deepEqual(await exported(),jsonBefore);
      const screenshot=await page.screenshot({path:resolve(out,`preview-${fileIndex}.png`)});
      const stats=await sharp(screenshot).stats();assert.ok(stats.channels.some(c=>c.stdev>10),"Nonblank rendering");
      if(fileIndex===0){
        await page.setViewportSize({width:430,height:932});await page.screenshot({path:resolve(out,"preview-mobile.png")});
        await page.setViewportSize({width:1600,height:1000});await page.mouse.move(point.x,point.y);
      }
      // Pointer-down samples the same surface again; capture the final transform.
      const expectedPreview=await page.evaluate(()=>worldBuilderDebug.preview());
      await page.mouse.click(point.x,point.y);await ready();
      const after=await snap(),json=await exported(),start=before.placements.length;
      assert.equal(after.placements.length,start+file.data.pieces.length);
      assert.deepEqual(after.placements.slice(0,start),before.placements);
      assert.equal(after.ui_collections.length,before.ui_collections.length+1);
      const {relocateBuildState}=await import("../../website/basebuilder-build-import.js");
      for(let i=0;i<file.data.pieces.length;i++){
        const src=file.data.pieces[i],state={...src,pitch:-src.pitch,roll:-src.roll};
        const expected=relocateBuildState(state,expectedPreview.pivot,expectedPreview.state),actual=after.placements[start+i].state;
        for(const key of ["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"])
          assert.ok(Math.abs(actual[key]-expected[key])<1e-5,`${i} ${key}`);
        assert.equal(json.pieces[start+i].pitch,Math.round(src.pitch*1000)/1000);
        assert.equal(json.pieces[start+i].roll,Math.round(src.roll*1000)/1000);
      }
      assert.equal(await page.evaluate(()=>worldBuilderDebug.preview()),null);
      await writeFile(resolve(out,`placed-${fileIndex}.rsdwproject.json`),JSON.stringify(await page.evaluate(()=>worldBuilderDebug.workspace.capture())));
      await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snap(),before);
      return {...ghost,pieces:file.data.pieces.length};
    });
  }
  await step("Save, unload, reload preserve imports and collections",async()=>{
    await chooseFile(files[1],{append:true});const before=await snap(),json=await exported();
    await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("unload"));assert.deepEqual(await snap(),before);
    await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");await ready();
    assert.deepEqual(await snap(),before);assert.deepEqual(await exported(),json);
  });
  await step("Pre-update catalog projects still open; unknown identities fail",async()=>{
    const project=await page.evaluate(()=>worldBuilderDebug.workspace.capture()),before=await snap();
    const previous=JSON.parse(execFileSync("git",["show","HEAD:website/basebuilder-index.json"],{maxBuffer:50e6}));
    project.dataset.catalog_sha256=createHash("sha256").update(JSON.stringify(previous)).digest("hex");
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
    assert.deepEqual(await snap(),before);
    project.dataset.catalog_sha256="unknown";
    const rejected=await page.evaluate(async p=>{try{await worldBuilderDebug.workspace.openDocument(p,{confirm:false});return false;}catch{return true;}},project);
    assert.ok(rejected);assert.deepEqual(await snap(),before);
  });
  await step("Replace preview, mixed actors, anchor pivot and invalid surface",async()=>{
    await page.evaluate(()=>worldBuilderDebug.workspace.enterLocation("x3_y1"));
    const before=await snap(),originalExport=await exported();
    const fixture=await page.evaluate(()=>{
      const targets=worldBuilderDebug.catalog.targets,piece=targets.find(t=>t.asset_kind==="building_piece"),
        item=targets.find(t=>t.asset_kind==="item"),bp=targets.find(t=>t.asset_stem==="BP_NPC_Doric_Dowdun_C");
      const state={x:123,y:456,z:789,pitch:17,roll:-23,yaw:40,scale_x:-1,scale_y:.7,scale_z:1.2};
      return {schema:"rsdwtools.buildings.v1",name:"Mixed Anchor",anchor_piece_id:8,
        pieces:[{...piece.export,...state,piece_id:8,stability:3000}],items:[{...item.export,...state,x:623,count:3}],
        actors:[{...bp.export,...state,y:956}]};
    });
    await page.click("#import-json");await page.click("#collection-dialog-submit");
    await page.setInputFiles("#file-input",{name:"mixed.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(fixture))});
    await page.getByText("Import Location",{exact:true}).waitFor();
    await page.setViewportSize({width:430,height:932});
    await page.screenshot({path:resolve(out,"import-dialog-mobile.png")});
    const dialogBounds=await page.locator(".themed-dialog__panel").boundingBox().catch(()=>null);
    if(dialogBounds)assert.ok(dialogBounds.x>=0&&dialogBounds.x+dialogBounds.width<=430);
    await page.setViewportSize({width:1600,height:1000});
    await page.click("#collection-dialog-secondary");await page.waitForFunction(()=>worldBuilderDebug.preview()?.buildCount===3);
    const outside={x:0,y:0};await page.mouse.move(outside.x,outside.y);
    assert.equal(await page.evaluate(()=>worldBuilderDebug.preview().canDrop),false);
    assert.deepEqual(await snap(),before);assert.deepEqual(await exported(),originalExport);
    const point=await previewPoint();await page.mouse.wheel(0,-100);
    await page.waitForFunction(()=>worldBuilderDebug.preview().state.yaw===15);
    const preview=await page.evaluate(()=>worldBuilderDebug.preview());assert.deepEqual(preview.pivot,{x:123,y:456,z:789});
    // Independent matrix comparison catches a mismatch between ghost and committed transforms.
    await page.evaluate(async p=>{
      const T=await import("three"),m=await import("./basebuilder-transforms.js"),{relocateBuildState}=await import("./basebuilder-build-import.js");
      const offset=worldBuilderDebug.snapshot().view_offset,src={x:123,y:456,z:789,pitch:-17,roll:23,yaw:40,scale_x:-1,scale_y:.7,scale_z:1.2};
      const parent=m.ueTransformToThreeMatrix4(p.state,offset);
      const preview=parent.multiply(m.ueTransformToThreeMatrix4(src,p.pivot));
      const expected=m.ueTransformToThreeMatrix4(relocateBuildState(src,p.pivot,p.state),offset);
      if(preview.elements.some((v,i)=>Math.abs(v-expected.elements[i])>1e-8))throw Error("Preview matrix differs from placement");
    },preview);
    await page.mouse.click(point.x,point.y);await ready();
    const after=await snap(),json=await exported();assert.equal(after.placements.length,3);assert.equal(after.ui_collections.length,1);
    assert.equal(after.anchor_piece_id,8);assert.equal(json.anchor_piece_id,8);
    assert.equal(json.items.length,1);assert.equal(json.actors.length,1);assert.equal(json.pieces[0].stability,3000);
    for(const row of [...json.pieces,...json.items,...json.actors]){
      assert.equal(row.pitch,17);assert.equal(row.roll,-23);assert.equal(row.yaw,55);assert.equal(row.scale_x,-1);assert.equal(row.scale_z,1.2);
    }
    assert.equal(after.placements[0].state.x,preview.state.x);assert.equal(after.placements[0].state.y,preview.state.y);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await snap(),before);
  });
  await step("Unmapped import fails without losing existing work",async()=>{
    const before=await snap();
    await page.click("#import-json");await page.click("#collection-dialog-submit");
    await page.setInputFiles("#file-input",{name:"missing.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify({schema:"rsdwtools.buildings.v1",pieces:[{class_name:"BP_missing_C"}]}))});
    await page.waitForFunction(()=>document.querySelector("#asset-status").textContent.includes("unavailable targets"));
    assert.deepEqual(await snap(),before);
  });
  assert.deepEqual(errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=error.stack;process.exitCode=1;}
finally{await writeFile(resolve(out,"ImportTests.json"),JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();}
