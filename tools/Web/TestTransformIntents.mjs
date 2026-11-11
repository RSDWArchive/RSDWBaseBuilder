import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";
const {values:a}=parseArgs({options:{out:{type:"string"},chrome:{type:"string"}}});
assert.ok(a.out);const out=resolve(a.out);await mkdir(out,{recursive:true});
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:true,...(a.chrome?{executablePath:a.chrome}:{})});
const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[],report={status:"running",checks:[],errors};
page.on("pageerror",e=>errors.push(String(e)));
try{
  const project=JSON.parse(await readFile("_build/world-builder-m3/editor-final/manual-review.rsdwproject.json","utf8"));project.workspace.world_enabled=false;
  project.build.placements=Array.from({length:300},(_,i)=>{
    const row=structuredClone(project.build.placements[i%project.build.placements.length]);row.id=`obj_${i+1}`;row.metadata.piece_id=i+1;
    row.state={x:176400+(i%20)*600,y:76000+Math.floor(i/20)*600,z:18000,
      pitch:[0,25,-48,89.99999,90,-90,110][i%7],yaw:[0,32,-170,450][i%4],roll:[0,-24,160,220][i%4],
      scale_x:i%5===0?-1:1.2,scale_y:i%9===0?-.8:.8,scale_z:i%11===0?-1.4:1.4};
    return row;
  });project.build.selected_ids=[];project.build.next_object_id=301;project.build.next_piece_id=301;project.build.anchor_piece_id=1;
  await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?world=1&debug=1");
  await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
  await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
  await page.evaluate(()=>worldBuilderDebug.select(worldBuilderDebug.snapshot().placements.map(p=>p.id)));
  for(const mode of ["translate","rotate","scale"]){
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    await page.keyboard.press({translate:"g",rotate:"r",scale:"s"}[mode]);
    if(mode==="scale")await page.getByRole("button",{name:"Click here to override.",exact:true}).click();
    const result=await page.evaluate(async mode=>{
      const T=await import("three"),m=await import("./basebuilder-transforms.js"),d=worldBuilderDebug,g=d.gizmo(),snapshot=d.snapshot();
      const previous=g.object.matrixWorld.clone();g.dispatchEvent({type:"dragging-changed",value:true});
      if(mode==="translate")g.object.position.x+=100;
      else if(mode==="rotate")g.object.rotation.y+=.147;
      else g.object.scale.y*=1.1;
      g.object.updateMatrixWorld(true);const delta=g.object.matrixWorld.clone().multiply(previous.invert());
      const expected=snapshot.placements.map(row=>{
        const old=m.ueMatrixRowsToThreeMatrix4(m.ueMatrixFromTransform(row.state),snapshot.view_offset),object=new T.Object3D();
        old.decompose(object.position,object.quaternion,object.scale);object.updateMatrix();
        object.matrix.premultiply(delta).decompose(object.position,object.quaternion,object.scale);
        return m.updateStateFromObject(object,row.state,snapshot.view_offset,{updateRotation:mode==="rotate",updateScale:mode==="scale"});
      });
      g.dispatchEvent({type:"objectChange"});const actual=d.snapshot(),pending=d.pendingSpatialCount();
      if(mode==="translate"){
        if(!d.querySpatialCenter("obj_1").includes("obj_1"))throw Error("Lazy spatial query lost the moved placement");
        if(d.pendingSpatialCount())throw Error("Spatial query did not flush the pending index");
      }
      g.dispatchEvent({type:"dragging-changed",value:false});
      if(d.pendingSpatialCount())throw Error("Drag release left a stale spatial index");
      let maxError=0;for(let i=0;i<expected.length;i++)for(const key of Object.keys(expected[i])){
        // Euler representations at gimbal singularities can differ by 360 degrees.
        const difference=actual.placements[i].state[key]-expected[i][key];
        maxError=Math.max(maxError,Math.abs(["pitch","yaw","roll"].includes(key)?m.normalizeDegrees(difference):difference));
      }
      return {mode,maxError,pending};
    },mode);
    assert.equal(result.pending,300);assert.ok(result.maxError<1e-6,JSON.stringify(result));
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    report.checks.push(result);console.log(JSON.stringify(result));
  }
  assert.deepEqual(errors,[]);report.status="passed";
}catch(e){report.status="failed";report.error=String(e.stack||e);process.exitCode=1;}
finally{await writeFile(resolve(out,"TransformIntents.json"),JSON.stringify(report,null,2));await browser.close();}
