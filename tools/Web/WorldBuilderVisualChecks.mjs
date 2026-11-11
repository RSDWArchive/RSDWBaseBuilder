import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFile,writeFile} from "node:fs/promises";
import {resolve} from "node:path";

export async function compareBuilderImages({browser,out,url}) {
  const sharp=createRequire(import.meta.url)("sharp");
  const project=JSON.parse(await readFile("_build/world-builder-m3/acceptance-performance-v2/sample-100.rsdwproject.json","utf8"));
  const images=new Map(),cases=[];
  for(const backend of ["legacy","optimized"]){
    const context=await browser.newContext({viewport:{width:1600,height:1000}}),page=await context.newPage(),errors=[];
    page.on("pageerror",e=>errors.push(String(e)));
    try{
      const entry=new URL("index.html",url);entry.search=`?world=1&debug=1&performance=${backend}`;
      await page.goto(entry.href);await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden,null,{timeout:120000});
      await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),project);
      for(const world of [false,true]){
        if(world){await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));
          await page.waitForFunction(()=>{const w=worldBuilderDebug.workspace,m=w.getOverviewMetrics();return m?.loaded===m?.total&&!w.layer.getStatus().pending.length;},null,{timeout:240000});}
        for(const view of ["perspective","orthographic","selected","solid"]){
          if(view==="orthographic")await page.keyboard.press("Numpad5");
          if(view==="selected")await page.evaluate(()=>worldBuilderDebug.select(["obj_8","obj_9","obj_10"]));
          if(view==="solid")await page.keyboard.press("t");
          await page.waitForTimeout(500);
          const data=await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>resolve(worldBuilderDebug.renderer.domElement.toDataURL("image/png")))));
          const png=Buffer.from(data.split(",")[1],"base64"),key=`${world?"world":"plain"}-${view}`;
          await writeFile(resolve(out,`${backend}-${key}.png`),png);
          const {data:pixels,info}=await sharp(png).ensureAlpha().raw().toBuffer({resolveWithObject:true});
          assert.ok((await sharp(png).stats()).channels.slice(0,3).some(c=>c.stdev>10),"Blank builder capture");
          if(backend==="legacy")images.set(key,{pixels,info});else{
            const before=images.get(key);assert.deepEqual(info,before.info);let different=0,max=0,total=0;
            for(let i=0;i<pixels.length;i++){const delta=Math.abs(pixels[i]-before.pixels[i]);if(delta>3)different++;max=Math.max(max,delta);total+=delta;}
            const result={world,view,different_fraction:different/pixels.length,max_channel_delta:max,mean_channel_delta:total/pixels.length};
            cases.push(result);await writeFile(resolve(out,"BuilderImages.json"),JSON.stringify(cases,null,2));
            assert.ok(result.different_fraction<=.001,`Builder image mismatch: ${JSON.stringify(result)}`);
          }
          if(view==="orthographic")await page.keyboard.press("Numpad5");
          if(view==="selected")await page.evaluate(()=>worldBuilderDebug.select([]));
          if(view==="solid")await page.keyboard.press("t");
        }
      }
      const selectionResources=await page.evaluate(async()=>{
        const d=worldBuilderDebug,rows=[],frame=()=>new Promise(r=>requestAnimationFrame(r));
        for(let i=0;i<50;i++){
          d.select(["obj_8"]);await frame();await frame();d.select([]);await frame();await frame();
          rows.push({...d.renderer.info.memory});
        }return rows;
      });
      assert.ok(selectionResources.at(-1).textures<=selectionResources[0].textures,"NPC selection leaked skeleton textures");
      await writeFile(resolve(out,`${backend}-selection-resources.json`),JSON.stringify(selectionResources,null,2));
      assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.export()),JSON.parse(await readFile("_build/world-builder-m3/acceptance-performance-v2/sample-100-building.json","utf8")));
      assert.deepEqual(errors,[]);
    }finally{await context.close();}
  }
  return cases;
}
