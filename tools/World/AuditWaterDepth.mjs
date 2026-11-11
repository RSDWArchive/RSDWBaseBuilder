import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string"},chrome:{type:"string"},
  url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/"}}});
if(!args.out)throw new Error("Pass --out with an ignored local audit directory");
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});
const page=await browser.newPage({viewport:{width:640,height:480}}),errors=[];
page.on("pageerror",e=>errors.push(String(e)));
page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
await page.route("**/depth-test.html",route=>route.fulfill({contentType:"text/html",body:
  '<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.184.0/build/three.module.js"}}</script>'}));
try {
  await page.goto(new URL("depth-test.html",args.url).href);
  const result=await page.evaluate(async()=>{
    const THREE=await import("three");
    const {createSceneDepth,applyDepthEffect,applyWaterDepth}=await import("./world-depth.js");
    const {applyFoamMaterial}=await import("./world-foam.js");
    const rows=[];
    for(const logarithmicDepthBuffer of [false,true])for(const perspective of [false,true]) {
      const renderer=new THREE.WebGLRenderer({logarithmicDepthBuffer});
      renderer.setSize(64,64);renderer.outputColorSpace=THREE.LinearSRGBColorSpace;
      const depth=createSceneDepth(renderer),scene=new THREE.Scene();
      const camera=perspective?new THREE.PerspectiveCamera(50,1,.1,50000):new THREE.OrthographicCamera(-4,4,4,-4,.1,50000);
      camera.position.z=10;camera.updateMatrixWorld();
      const geometry=new THREE.PlaneGeometry(8,8);
      const ground=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:0x00ff00}));scene.add(ground);
      const material=new THREE.MeshBasicMaterial({color:0xff0000,opacity:.8});
      applyDepthEffect(material,depth,"diffuseColor.a*=clamp(depthGap/2.0,0.0,1.0);","test");
      const surface=new THREE.InstancedMesh(geometry,material,1);
      surface.setMatrixAt(0,new THREE.Matrix4());scene.add(surface);
      function pixel() {
        depth.render(scene,camera);
        const gl=renderer.getContext(),p=new Uint8Array(4);
        gl.readPixels(renderer.domElement.width/2,renderer.domElement.height/2,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);
        return [...p];
      }
      for(const gap of [.05,.5,1,3]) {
        ground.position.z=-gap;
        rows.push({logarithmicDepthBuffer,perspective,gap,pixel:pixel(),expectedRed:.8*Math.min(1,gap/2)*255});
      }
      renderer.setSize(96,80);pixel();
      const resized=depth.stats();
      if(resized.width!==96 || resized.height!==80)throw new Error("Depth target did not resize");
      ground.visible=false;
      rows.push({logarithmicDepthBuffer,perspective,background:true,pixel:pixel(),expectedRed:.8*255});
      if(ground.visible)throw new Error("Depth pass revealed a hidden object");
      ground.visible=true;
      const mask=new THREE.DataTexture(new Uint8Array([0,0,0,0]),1,1);mask.needsUpdate=true;
      ground.material.map=mask;ground.material.alphaTest=.5;ground.material.needsUpdate=true;
      rows.push({logarithmicDepthBuffer,perspective,alphaCutout:true,pixel:pixel(),expectedRed:.8*255});
      ground.material.map=null;ground.material.alphaTest=0;ground.material.needsUpdate=true;
      ground.position.z=0;
      surface.setMatrixAt(0,new THREE.Matrix4().makeTranslation(0,0,1));surface.instanceMatrix.needsUpdate=true;
      surface.computeBoundingSphere();
      rows.push({logarithmicDepthBuffer,perspective,translatedInstance:true,pixel:pixel(),expectedRed:.4*255});
      surface.setMatrixAt(0,new THREE.Matrix4());surface.instanceMatrix.needsUpdate=true;surface.computeBoundingSphere();
      ground.position.z=-1;
      const helper=new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-3,0,1),new THREE.Vector3(3,0,1)]),new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:0,depthTest:false,depthWrite:true}));scene.add(helper);
      rows.push({logarithmicDepthBuffer,perspective,nonDepthHelper:true,pixel:pixel(),expectedRed:.4*255});
      // A stable camera reuses opaque depth; edits must invalidate it immediately.
      pixel();pixel();const stable=depth.stats().captures;pixel();
      if(depth.stats().captures!==stable)throw Error("Unchanged opaque depth was recaptured");
      ground.position.z=-.5;
      rows.push({logarithmicDepthBuffer,perspective,cacheTransform:true,pixel:pixel(),expectedRed:.2*255});
      if(depth.stats().captures!==stable+1)throw Error("Transformed occluder reused stale depth");
      ground.material.onBeforeCompile=shader=>{shader.vertexShader=shader.vertexShader.replace("#include <begin_vertex>","#include <begin_vertex>\ntransformed.z -= 0.5;");};
      ground.material.customProgramCacheKey=()=>"depth-test-deform";ground.material.needsUpdate=true;
      rows.push({logarithmicDepthBuffer,perspective,customDeformationFallback:true,pixel:pixel(),expectedRed:.4*255});
      ground.material.onBeforeCompile=THREE.Material.prototype.onBeforeCompile;
      ground.material.customProgramCacheKey=THREE.Material.prototype.customProgramCacheKey;ground.material.needsUpdate=true;
      ground.position.z=-1;
      const river=new THREE.MeshBasicMaterial({color:0xff0000,opacity:.8});
      applyWaterDepth(river,{depth:{mode:"river",fade_m:2,color_m:2,shallow_color:[0,0,1],shallow_opacity:0}},depth);
      surface.material=river;
      rows.push({logarithmicDepthBuffer,perspective,river:true,pixel:pixel(),expectedRed:.2*255,expectedBlue:.2*255});
      mask.image.data.set([128,0,0,255]);mask.needsUpdate=true;
      const foam=new THREE.MeshBasicMaterial();
      await applyFoamMaterial(foam,{textures:{foam_mask:"fixture"},settings:{foam:{color:[1,0,0],opacity:.5,
        uv_scale:[1,1],mask_mult:[1,0,0,0],mask_sub:[0,0,0,0],mask_gain:1,mask_bias:0,rgb_mask:true,depth_fade_m:2}}},async()=>mask,depth);
      surface.material=foam;
      rows.push({logarithmicDepthBuffer,perspective,foam:true,pixel:pixel(),expectedRed:32});
      renderer.setViewport(2,3,60,50);renderer.setScissor(4,5,48,40);renderer.setScissorTest(true);
      depth.render(scene,camera);
      if(!renderer.getViewport(new THREE.Vector4()).equals(new THREE.Vector4(2,3,60,50)) ||
         !renderer.getScissor(new THREE.Vector4()).equals(new THREE.Vector4(4,5,48,40)) || !renderer.getScissorTest()) {
        throw new Error("Depth pass leaked host viewport/scissor state");
      }
      surface.visible=false;const before=depth.stats().captures;pixel();
      if(depth.stats().captures!==before)throw new Error("Depth pass ran without an effect surface");
      helper.geometry.dispose();helper.material.dispose();mask.dispose();ground.material.dispose();material.dispose();river.dispose();foam.dispose();surface.dispose();geometry.dispose();depth.dispose();renderer.dispose();
    }
    return rows;
  });
  for(const row of result) {
    assert.ok(Math.abs(row.pixel[0]-row.expectedRed)<4,JSON.stringify(row));
    if(row.expectedBlue!==undefined)assert.ok(Math.abs(row.pixel[2]-row.expectedBlue)<4,JSON.stringify(row));
  }
  assert.deepEqual(errors,[]);
  const shaders={};
  for(const name of ["world-depth.js","world-foam.js","/RSDWBaseBuilder/website/world/world-depth.js","/RSDWBaseBuilder/website/world/world-foam.js"]) {
    const response=await fetch(new URL(name,args.url));
    assert.ok(response.ok,`Cannot fingerprint ${name}`);
    shaders[name]=createHash("sha256").update(await response.text()).digest("hex");
  }
  await mkdir(resolve(args.out),{recursive:true});
  const audit_sha256=createHash("sha256").update(await readFile(new URL(import.meta.url))).digest("hex");
  await writeFile(resolve(args.out,"WaterDepthValidation.json"),JSON.stringify({status:"passed",checked_at:new Date().toISOString(),shaders,audit_sha256,cases:result,errors},null,2));
  console.log(`Passed ${result.length} GPU pixel cases: standard/log depth, perspective/orthographic, instancing, resize, alpha cutouts, river color, foam masks.`);
} finally {await browser.close();}
