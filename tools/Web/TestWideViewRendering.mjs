import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,readFile,writeFile,access} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string",default:"_build/world-builder-wide/images"},
  source:{type:"string",default:"_build/world-builder-wide/baseline/source"},
  fixture:{type:"string",default:"_build/world-builder-m4/performance-final/sample-10000.rsdwproject.json"},
  "unit-only":{type:"boolean",default:false}}});
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp"),out=resolve(args.out);
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const report={status:"running",checks:[],errors:[]};
try {
  const unit=await browser.newPage();
  unit.on("pageerror",e=>report.errors.push(String(e)));
  await unit.route("**/wide-render-test.html",r=>r.fulfill({contentType:"text/html",body:
    '<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.184.0/build/three.module.js"}}</script>'}));
  await unit.route("**/before-depth.js",r=>r.fulfill({path:resolve(args.source,"world/world-depth.js")}));
  await unit.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/world/wide-render-test.html");
  const cases=await unit.evaluate(async()=>{
    const T=await import("three"),current=await import("./world-depth.js"),before=await import("./before-depth.js"),rows=[];
    for(const projection of ["perspective","orthographic"])for(const callback of ["none","manual","scene","object","material"]){
      function run(module,fail=false){
        const renderer=new T.WebGLRenderer({logarithmicDepthBuffer:true});renderer.setSize(96,96);
        const scene=new T.Scene(),depth=module.createSceneDepth(renderer),camera=projection==="perspective"?new T.PerspectiveCamera(50,1,.1,1000):new T.OrthographicCamera(-5,5,5,-5,.1,1000);
        camera.position.z=10;camera.updateMatrixWorld();
        const geometry=new T.BoxGeometry(1,1,1),material=new T.MeshBasicMaterial({color:0x669944});
        const front=new T.Mesh(geometry,material);front.position.x=-1;scene.add(front);
        const outside=new T.Mesh(geometry,material);outside.position.x=500;scene.add(outside);
        const parent=new T.Mesh(geometry,material);parent.position.x=100;
        const child=new T.Mesh(geometry,new T.MeshBasicMaterial({color:0x3355ee}));child.position.x=-100;parent.add(child);scene.add(parent);
        const hidden=new T.Mesh(geometry,material);hidden.visible=false;scene.add(hidden);
        const noCull=new T.Mesh(geometry,material);noCull.position.x=2;noCull.frustumCulled=false;scene.add(noCull);
        const instances=new T.InstancedMesh(geometry,material,2);instances.setMatrixAt(0,new T.Matrix4().makeTranslation(1,-2,0));instances.setMatrixAt(1,new T.Matrix4().makeTranslation(-1,2,0));scene.add(instances);
        const water=new T.MeshBasicMaterial({color:0x5577ff,opacity:.7});module.applyDepthEffect(water,depth,"diffuseColor.a*=clamp(depthGap/2.0,0.0,1.0);","test");
        const surface=new T.Mesh(new T.PlaneGeometry(8,8),water);surface.position.z=1;scene.add(surface);
        let callbacks=0,updates=0;
        if(callback==="manual")scene.matrixWorldAutoUpdate=false;
        if(callback==="scene")scene.onBeforeRender=()=>{callbacks++;front.position.x+=.1;};
        if(callback==="object")front.onBeforeRender=()=>{callbacks++;child.position.y+=.1;};
        if(callback==="material")material.onBeforeRender=()=>{callbacks++;child.position.y+=.1;};
        const originalUpdate=scene.updateMatrixWorld;scene.updateMatrixWorld=function(...a){updates++;return originalUpdate.apply(this,a);};
        const flags=()=>{const values=[];scene.traverse(o=>values.push([o.id,o.visible,o.frustumCulled]));return JSON.stringify(values);};
        const initial=flags(),auto=scene.matrixWorldAutoUpdate;
        if(fail)renderer.render=()=>{throw Error("Injected render failure");};
        let failed=false;try{depth.render(scene,camera);}catch(e){if(!fail)throw e;failed=true;}
        if(flags()!==initial||scene.matrixWorldAutoUpdate!==auto)throw Error("Render leaked visibility/culling/matrix flags");
        const pixels=new Uint8Array(96*96*4);if(!fail){const gl=renderer.getContext();gl.readPixels(0,0,96,96,gl.RGBA,gl.UNSIGNED_BYTE,pixels);}
        depth.dispose();scene.traverse(o=>{o.geometry?.dispose();for(const m of [o.material].flat().filter(Boolean))m.dispose();});renderer.dispose();renderer.forceContextLoss();
        return {pixels,updates,callbacks,failed};
      }
      const a=run(before),b=run(current);let differences=0,maxDelta=0;
      for(let i=0;i<a.pixels.length;i++){const d=Math.abs(a.pixels[i]-b.pixels[i]);if(d)differences++;maxDelta=Math.max(maxDelta,d);}
      if(differences)throw Error(`${projection}/${callback}: ${differences} changed channels, delta ${maxDelta}`);
      if(callback==="none"&&!(a.updates===3&&b.updates===1))throw Error(`Expected 3 -> 1 matrix traversals, got ${a.updates} -> ${b.updates}`);
      if(callback!=="none"&&!(b.updates===a.updates&&b.callbacks===a.callbacks))throw Error("Manual or callback matrix updates changed");
      const failure=run(current,true);if(!failure.failed)throw Error("Expected render exception");
      rows.push({projection,callback,changed_channels:differences,before_updates:a.updates,after_updates:b.updates,callback_count:b.callbacks,exception_restores_flags:true});
    }
    return rows;
  });
  report.checks.push({name:"Depth/color pixels, render callbacks, parent/child culling and exception restoration",cases});await unit.close();
  console.log(`${cases.length} focused render/flag cases passed`);
  if(!args["unit-only"]){
    const fixture=JSON.parse(await readFile(args.fixture,"utf8")),images=new Map();
    for(const variant of ["before","after"]){
      const context=await browser.newContext({viewport:{width:1600,height:1060}}),page=await context.newPage();page.setDefaultTimeout(240000);
      page.on("pageerror",e=>report.errors.push(String(e)));
      if(variant==="before")await page.route("**/RSDWBaseBuilder/website/**",async route=>{
        const path=decodeURIComponent(new URL(route.request().url()).pathname.split("/website/")[1]);
        if(!/\.(js|css|html)$/.test(path)||path.includes(".."))return route.continue();
        const file=resolve(args.source,path);try{await access(file);}catch{return route.continue();}return route.fulfill({path:file});
      });
      await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/index.html?debug=1&wideImages=1");
      await page.waitForFunction(()=>window.worldBuilderDebug&&document.querySelector("#stage-loading").hidden);
      await page.evaluate(p=>worldBuilderDebug.workspace.openDocument(p,{confirm:false}),fixture);
      await page.evaluate(()=>worldBuilderDebug.workspace.runWorld("resume"));
      await page.waitForFunction(()=>{const w=worldBuilderDebug.workspace,m=w.getOverviewMetrics(),s=w.layer.getStatus();return m?.loaded===m?.total&&!s.pending.length&&!w.layer.resources.stats().jobs.running;});
      await page.evaluate(()=>{const input=document.querySelector("#world-streaming");input.checked=false;input.dispatchEvent(new Event("change"));});
      const exported=await page.evaluate(()=>worldBuilderDebug.export());
      for(const view of ["perspective","orthographic"]){
        await page.evaluate(camera=>{const d=worldBuilderDebug,origin=d.snapshot().view_offset;
          d.camera().position.set((camera.position_cm[0]-origin.x)/100,(camera.position_cm[2]-origin.z)/100,(camera.position_cm[1]-origin.y)/100);
          d.controls.target.set((camera.target_cm[0]-origin.x)/100,(camera.target_cm[2]-origin.z)/100,(camera.target_cm[1]-origin.y)/100);d.controls.update();
        },fixture.workspace.camera);
        if(view==="orthographic")await page.keyboard.press("Numpad5");
        await page.waitForTimeout(500);
        const image=await page.locator("#builder-stage canvas").first().screenshot();await writeFile(resolve(out,`${variant}-${view}.png`),image);
        const {data,info}=await sharp(image).raw().toBuffer({resolveWithObject:true}),stats=await sharp(image).stats();
        assert.ok(stats.channels.slice(0,3).some(c=>c.stdev>10),"Blank viewport");
        const camera=await page.evaluate(()=>({world:worldBuilderDebug.camera().matrixWorld.toArray(),projection:worldBuilderDebug.camera().projectionMatrix.toArray()}));
        if(variant==="before")images.set(view,{data,info,camera});else{
          const old=images.get(view);assert.deepEqual(info,old.info);assert.deepEqual(camera,old.camera);
          let differences=0,maxDelta=0;for(let i=0;i<data.length;i++){const delta=Math.abs(data[i]-old.data[i]);if(delta>3)differences++;maxDelta=Math.max(maxDelta,delta);}
          const fraction=differences/data.length;assert.ok(fraction<.001,`${view}: ${fraction} changed channels`);
          report.checks.push({name:`10k + world: ${view} image parity`,width:info.width,height:info.height,changed_channel_fraction:fraction,max_delta:maxDelta});
        }
        assert.deepEqual(await page.evaluate(()=>worldBuilderDebug.export()),exported,"Render changed game export");
        if(view==="orthographic")await page.keyboard.press("Numpad5");
        console.log(`${variant} ${view} captured`);
      }
      await context.close();
    }
  }
  assert.deepEqual(report.errors,[]);report.status="passed";
}catch(error){report.status="failed";report.error=String(error.stack||error);console.error(report.error);process.exitCode=1;}
finally{await writeFile(resolve(out,"Rendering.json"),JSON.stringify(report,null,2));await browser.close();}
