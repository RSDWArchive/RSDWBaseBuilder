import assert from "node:assert/strict";
import {writeFile} from "node:fs/promises";
import {resolve} from "node:path";

export async function testLargeBuild({page,step,out,project}) {
  await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
  await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
  await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
  const expected=await step("10k mixed project with hidden actors and collections",async()=>{
    const fixture=structuredClone(project),world=fixture.workspace.world_build||fixture.workspace;world.world_enabled=false;
    world.navigation.mode="build";fixture.build.build_name="10k World Builder Review";
    fixture.build.selected_ids=[];fixture.build.placements=Array.from({length:10000},(_,i)=>{
      const row=structuredClone(project.build.placements[i%project.build.placements.length]);
      row.id=`obj_${i+1}`;row.metadata.piece_id=i+1;row.hidden=i>0&&i%101===0;
      row.state.x=fixture.workspace.render_origin_cm[0]+(i%100-50)*400;
      row.state.y=fixture.workspace.render_origin_cm[1]+(Math.floor(i/100)-50)*400;row.state.z=18000;
      return row;
    });fixture.build.anchor_piece_id=1;fixture.build.next_object_id=10001;fixture.build.next_piece_id=10001;
    await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),fixture);
    await page.evaluate(()=>worldBuilderDebug.focus());
    const result=await page.evaluate(()=>({project:worldBuilderDebug.workspace.capture(),exported:worldBuilderDebug.export()}));
    assert.deepEqual(result.project.build,fixture.build);
    await writeFile(resolve(out,"10k-review.rsdwproject.json"),JSON.stringify(result.project));
    await writeFile(resolve(out,"10k-review-building.json"),JSON.stringify(result.exported));
    return result;
  });
  await step("10k select-all and selection outline rendering",async()=>{
    const start=performance.now();const cpu_ms=await page.evaluate(()=>{const ids=worldBuilderDebug.snapshot().placements.map(p=>p.id),start=performance.now();worldBuilderDebug.select(ids);return performance.now()-start;});
    const selected=await page.evaluate(()=>{const d=worldBuilderDebug;return {count:d.state().selected.length,promoted:__RSDW_BASE_BUILDER_DEBUG__.instanceStats().promoted,
      lines:d.scene.children.filter(o=>o.name==="Selection Boxes").map(o=>o.geometry.drawRange.count)};});
    assert.equal(selected.count,10000);assert.equal(selected.promoted,0);assert.equal(selected.lines.length,1);
    await page.screenshot({path:resolve(out,"10k-selected.png")});return {...selected,cpu_ms,elapsed_ms:performance.now()-start};
  });
  await step("10k rotate/scale pivot edits and undo",async()=>{
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot()),timings={};
    for(const mode of ["rotate","scale"]){
      await page.keyboard.press(mode==="rotate"?"r":"s");
      if(mode==="scale")await page.getByRole("button",{name:"Click here to override.",exact:true}).click();
      timings[mode]=await page.evaluate(mode=>{const g=worldBuilderDebug.gizmo(),start=performance.now();
        g.dispatchEvent({type:"dragging-changed",value:true});
        if(mode==="rotate")g.object.rotation.y+=.2;else g.object.scale.y*=1.1;
        g.dispatchEvent({type:"objectChange"});g.dispatchEvent({type:"dragging-changed",value:false});return performance.now()-start;
      },mode);
      const after=await page.evaluate(()=>worldBuilderDebug.snapshot());
      for(let i=0;i<10000;i++){
        const a=after.placements[i].state,b=before.placements[i].state;
        for(const k of mode==="scale"?["pitch","yaw","roll"]:["scale_x","scale_y","scale_z"])assert.equal(a[k],b[k]);
      }
      assert.notDeepEqual(after.placements,before.placements);
      await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    }
    return timings;
  });
  await step("10k duplicate and delete each remain one undo action",async()=>{
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    const duplicate_ms=await page.evaluate(async()=>{const start=performance.now();await worldBuilderDebug.duplicate();return performance.now()-start;});
    const copies=await page.evaluate(()=>worldBuilderDebug.snapshot());assert.equal(copies.placements.length,20000);
    assert.equal(new Set(copies.placements.map(p=>p.id)).size,20000);
    const pieceIds=copies.placements.map(p=>p.metadata.piece_id).filter(Number.isFinite);
    assert.equal(new Set(pieceIds).size,pieceIds.length,"Bulk ID allocation introduced a collision");
    for(let i=0;i<10000;i++)assert.deepEqual(copies.placements[i+10000].state,before.placements[i].state);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    await page.keyboard.press("x");assert.equal(await page.evaluate(()=>worldBuilderDebug.state().placements),0);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    return {duplicate_ms};
  });
  await step("10k marquee and Ctrl-deselect use the same logical actors",async()=>{
    const results=await page.evaluate(()=>{
      const d=worldBuilderDebug,r=d.renderer.domElement.getBoundingClientRect(),g={startX:r.left,startY:r.top,currentX:r.right,currentY:r.bottom};
      d.select([]);let start=performance.now();d.marquee(g);const selected=d.state().selected.length,cpu_ms=performance.now()-start;
      start=performance.now();d.marquee({...g,subtract:true});return {selected,cpu_ms,deselect_ms:performance.now()-start,remaining:d.state().selected.length};
    });
    assert.equal(results.selected,expected.project.build.placements.filter(p=>!p.hidden).length);assert.equal(results.remaining,0);
    await page.evaluate(()=>worldBuilderDebug.select(worldBuilderDebug.snapshot().placements.map(p=>p.id)));return results;
  });
  await step("10k group transform and undo preserves every rotation/scale",async()=>{
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    await page.keyboard.press("g");
    await page.evaluate(()=>{const g=worldBuilderDebug.gizmo();g.dispatchEvent({type:"dragging-changed",value:true});
      g.object.position.y+=.1;g.dispatchEvent({type:"objectChange"});g.dispatchEvent({type:"dragging-changed",value:false});});
    const after=await page.evaluate(()=>worldBuilderDebug.snapshot());
    assert.equal(after.placements.length,10000);
    for(let i=0;i<10000;i++){
      assert.ok(Math.abs(after.placements[i].state.z-before.placements[i].state.z-10)<.001);
      for(const k of ["pitch","yaw","roll","scale_x","scale_y","scale_z"])assert.equal(after.placements[i].state[k],before.placements[i].state[k]);
    }
    const scrolled=await page.evaluate(()=>{
      const list=document.querySelector("#placed-list"),rows=list.querySelectorAll("[data-placement-id]"),row=rows[rows.length-1];
      const scroll=list.scrollTop;row.scrollIntoView({block:"center"});return {id:row.dataset.placementId,scroll};
    });
    await page.waitForFunction(async id=>{
      const p=worldBuilderDebug.snapshot().placements.find(p=>p.id===id),{roundValue}=await import("./basebuilder-transforms.js");
      return document.querySelector(`[data-placement-id="${id}"] .placed-meta`).textContent===`${roundValue(p.state.x)}, ${roundValue(p.state.y)}, ${roundValue(p.state.z)}`;
    },scrolled.id);
    await page.evaluate(scroll=>{document.querySelector("#placed-list").scrollTop=scroll;},scrolled.scroll);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    return {transforms:10000};
  });
  await step("10k hide/show excludes export without losing saved actors",async()=>{
    await page.evaluate(()=>worldBuilderDebug.hide());
    const hidden=await page.evaluate(()=>({build:worldBuilderDebug.snapshot(),json:worldBuilderDebug.export()}));
    assert.ok(hidden.build.placements.every(p=>p.hidden));assert.equal(hidden.json.pieces.length+hidden.json.items.length+hidden.json.actors.length,0);
    await page.evaluate(()=>worldBuilderDebug.undo());
    assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.export()),expected.exported);return true;
  });
  await step("10k scene warm snap and directional duplicate",async()=>{
    await page.evaluate(()=>worldBuilderDebug.select(["obj_1"]));
    const snap_ms=[];
    for(let i=0;i<5;i++){
      const before=await page.evaluate(()=>({snapshot:worldBuilderDebug.snapshot(),undo:worldBuilderDebug.state().undo}));
      snap_ms.push(await page.evaluate(async()=>{const start=performance.now();await worldBuilderDebug.snap();return performance.now()-start;}));
      if(await page.evaluate(()=>worldBuilderDebug.state().undo)>before.undo)await page.evaluate(()=>worldBuilderDebug.undo());
      assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before.snapshot);
    }
    await page.evaluate(()=>worldBuilderDebug.select(["obj_1","obj_2"]));
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    await page.keyboard.down("d");await page.keyboard.press("ArrowRight");await page.keyboard.up("d");
    await page.waitForFunction(()=>worldBuilderDebug.state().placements===10002&&!worldBuilderDebug.busy());
    const after=await page.evaluate(()=>worldBuilderDebug.snapshot());
    assert.deepEqual(after.placements.slice(0,10000),before.placements);
    assert.notEqual(after.placements[10000].state.x,before.placements[0].state.x);
    await page.evaluate(()=>worldBuilderDebug.undo());assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    return {snap_ms};
  });
  await step("10k save/reload survives unloaded world",async()=>{
    await page.evaluate(()=>worldBuilderDebug.select([]));await page.evaluate(()=>worldBuilderDebug.workspace.saveNow());
    const before=await page.evaluate(()=>worldBuilderDebug.snapshot());
    await page.reload();await page.getByText("Restore project?",{exact:true}).waitFor();await page.click("#collection-dialog-submit");
    await page.waitForFunction(()=>worldBuilderDebug?.state().placements===10000&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
    assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.snapshot()),before);
    assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.export()),expected.exported);
    return true;
  });
}
