import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {mkdir,writeFile} from "node:fs/promises";
import {resolve} from "node:path";
import {parseArgs} from "node:util";

const {values:args}=parseArgs({options:{out:{type:"string"},chrome:{type:"string"},builder:{type:"boolean",default:false},url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/website/"}}});
assert.ok(args.out);const out=resolve(args.out);await mkdir(out,{recursive:true});
const {chromium}=createRequire(import.meta.url)("playwright");
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});
const report={status:"running",cases:[],errors:[]};
try {
  const page=await browser.newPage({viewport:{width:800,height:600}});
  page.on("pageerror",e=>report.errors.push(String(e)));page.on("console",m=>{if(m.type()==="error")report.errors.push(m.text());});
  await page.route("**/instance-test.html",r=>r.fulfill({contentType:"text/html",body:'<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.184.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.184.0/examples/jsm/"}}</script>'}));
  await page.goto(new URL("instance-test.html",args.url).href);
  report.transforms=await page.evaluate(async()=>{
    const T=await import("three"),m=await import("./basebuilder-transforms.js");
    let seed=42,maxError=0,maxRotationError=0;const random=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/2**32);
    for(let i=0;i<2000;i++){
      const state={x:random()*1e6,y:random()*1e6,z:random()*1e5,pitch:random()*360-180,yaw:random()*720-360,roll:random()*360-180,
        scale_x:random()*4-2,scale_y:random()*4-2,scale_z:random()*4-2};
      const offset={x:123456,y:-654321,z:43521};
      const old=m.ueMatrixRowsToThreeMatrix4(m.ueMatrixFromTransform(state),offset),next=m.ueTransformToThreeMatrix4(state,offset);
      const position=new T.Vector3(),rotation=new T.Quaternion(),scale=new T.Vector3();old.decompose(position,rotation,scale);old.compose(position,rotation,scale);
      for(let j=0;j<16;j++)maxError=Math.max(maxError,Math.abs(old.elements[j]-next.elements[j]));
      const e=new T.Matrix4().makeRotationFromQuaternion(rotation).elements,pitch=Math.asin(Math.max(-1,Math.min(1,-e[1]))),cp=Math.cos(pitch);
      const expected={pitch:m.normalizeDegrees(m.radToDeg(pitch)),yaw:m.normalizeDegrees(m.radToDeg(Math.abs(cp)>1e-6?Math.atan2(e[2],e[0]):Math.atan2(-e[8],e[10]))),roll:m.normalizeDegrees(m.radToDeg(Math.abs(cp)>1e-6?Math.atan2(e[9],e[5]):0))};
      const actual=m.ueRotatorFromThreeQuaternion(rotation);
      for(const key of ["pitch","yaw","roll"])maxRotationError=Math.max(maxRotationError,Math.abs(actual[key]-expected[key]));
    }
    if(maxError>1e-10)throw Error("Transform matrix contract changed: "+maxError);
    if(maxRotationError>1e-10)throw Error("Quaternion rotation contract changed: "+maxRotationError);
    return {cases:2000,maxError,maxRotationError};
  });
  report.cases=await page.evaluate(async()=>{
    const T=await import("three"),{createInstanceStore}=await import("./basebuilder-instances.js");
    const renderer=new T.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setSize(256,256);document.body.append(renderer.domElement);
    const scene=new T.Scene();scene.background=new T.Color("#20272a");scene.add(new T.HemisphereLight(0xffffff,0x888888,2));
    const light=new T.DirectionalLight(0xffffff,3);light.position.set(4,10,5);scene.add(light);
    const geometry=new T.BoxGeometry(2,3,2);geometry.computeBoundingBox();
    const material=new T.MeshStandardMaterial({color:0xa2a4a4}),transparent=new T.MeshBasicMaterial({color:0x77bbcc,transparent:true,opacity:.4});
    const componentOffset=new T.Vector3(.3,.2,.4);
    const templates=[material,transparent].map((material,i)=>({key:String(i),eligible:true,bounds:geometry.boundingBox.clone().translate(componentOffset),descriptors:[{geometry,material,localMatrix:new T.Matrix4().makeTranslation(...componentOffset)}]}));
    const rows=Array.from({length:100},(_,i)=>({id:String(i),target:i%11===0?1:0,state:{x:(i%10-5)*350,y:(Math.floor(i/10)-5)*350,z:0,yaw:i*.15},visual:{},hidden:false}));
    rows.push({id:"offscreen",target:0,state:{x:500000,y:500000,z:0,yaw:0},visual:{},hidden:false});
    const matrix=p=>new T.Matrix4().compose(new T.Vector3(p.state.x/100,p.state.z/100,p.state.y/100),new T.Quaternion().setFromAxisAngle(new T.Vector3(0,1,0),p.state.yaw),new T.Vector3(p.id==="1"?-1:1,1.2,.8));
    const cases=[];
    for(const orthographic of [false,true])for(const cellCm of [1600,3200,6400]) {
      const camera=orthographic?new T.OrthographicCamera(-26,26,26,-26,.1,1000):new T.PerspectiveCamera(50,1,.1,1000);
      camera.position.set(24,45,36);camera.lookAt(0,0,0);camera.updateMatrixWorld();
      const capture=legacy=>{
        const root=new T.Group();scene.add(root);const placements=structuredClone(rows);
        const store=createInstanceStore({root,cellCm,legacy,templateForTarget:id=>templates[id],matrixForPlacement:matrix,isVisible:p=>!p.hidden});
        store.reserve(placements);for(const p of placements)store.add(p);store.flush(camera);scene.updateMatrixWorld(true);
        renderer.render(scene,camera);const gl=renderer.getContext(),pixels=new Uint8Array(256*256*4);gl.readPixels(0,0,256,256,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        const stats=store.stats(camera);
        const moved=placements[10];moved.state.x+=10;moved.state.y+=30;moved.state.z+=20;
        store.translate(moved,new T.Vector3(.1,.2,.3));store.flush(camera);
        const componentMatrix=new T.Matrix4();store.candidates([moved])[0].getMatrixAt(moved.visual.instanceSlot,componentMatrix);
        const expectedMatrix=matrix(moved).multiply(templates[moved.target].descriptors[0].localMatrix);
        if(componentMatrix.elements.some((v,i)=>Math.abs(v-expectedMatrix.elements[i])>1e-5))throw Error("Translated component matrix changed");
        moved.state.x+=9000;store.update(moved);store.flush(camera);
        const ray=new T.Raycaster(new T.Vector3(moved.state.x/100,100,moved.state.y/100),new T.Vector3(0,-1,0));
        const hit=ray.intersectObjects(store.candidates([moved]),false)[0];if(store.hitId(hit)!==moved.id)throw Error("Cross-cell pick mapping");
        moved.hidden=true;store.update(moved);store.flush(camera);
        if(ray.intersectObjects(store.candidates([moved]),false).length)throw Error("Hidden actor remains pickable");
        store.remove(placements[0]);store.remove(moved);store.flush(camera);
        // Recreating a cell in one action must not reuse its previous upload signature.
        moved.hidden=false;store.add(moved);store.flush(camera);
        store.remove(moved);moved.state.x+=200;store.add(moved);store.flush(camera);
        const recreated=new T.Raycaster(new T.Vector3(moved.state.x/100,100,moved.state.y/100),new T.Vector3(0,-1,0));
        if(store.hitId(recreated.intersectObjects(store.candidates([moved]),false)[0])!==moved.id)throw Error("Recreated cell pick mapping");
        store.remove(moved);
        for(const p of placements.filter(p=>p!==moved&&p!==placements[0]))store.remove(p);
        store.flush(camera);if(store.stats().instances||root.children.length)throw Error("Instance ownership leak");
        store.dispose();root.removeFromParent();return {pixels,stats};
      };
      const before=capture(true),after=capture(false);let different=0,max=0;
      for(let i=0;i<before.pixels.length;i++){const delta=Math.abs(before.pixels[i]-after.pixels[i]);max=Math.max(max,delta);if(delta>3)different++;}
      if(different>before.pixels.length*.001)throw Error(`Rendering changed: ${different}, max ${max}`);
      if(after.stats.submitted_instances>=rows.length)throw Error("Offscreen culling inactive");
      cases.push({orthographic,cellCm,different,max,before:before.stats,after:after.stats});
    }
    geometry.dispose();material.dispose();transparent.dispose();renderer.dispose();return cases;
  });
  report.depthBatches=await page.evaluate(async()=>{
    const T=await import("three"),{createInstanceStore}=await import("./basebuilder-instances.js");
    const {createSceneDepth,applyDepthEffect}=await import("./world/world-depth.js");
    const renderer=new T.WebGLRenderer({antialias:true});renderer.setSize(128,128);renderer.outputColorSpace=T.LinearSRGBColorSpace;
    const geometry=new T.BoxGeometry(1,1,.5);geometry.computeBoundingBox();
    const material=new T.MeshBasicMaterial({color:0x00ff00});
    const template={key:"fixture",eligible:true,bounds:geometry.boundingBox.clone(),descriptors:[{geometry,material,localMatrix:new T.Matrix4()}]};
    const rows=Array.from({length:100},(_,i)=>({id:String(i),target:0,hidden:false,visual:{},state:{x:(i%10-5)*200,y:(Math.floor(i/10)-5)*200,z:i%3?-100:-500}}));
    const result=[];
    for(const perspective of [false,true]){
      const images=[];
      for(const legacy of [true,false]){
        const scene=new T.Scene(),root=new T.Group();scene.add(root);
        const camera=perspective?new T.PerspectiveCamera(50,1,.1,100):new T.OrthographicCamera(-12,12,12,-12,.1,100);
        camera.position.z=20;camera.updateMatrixWorld();
        const depth=createSceneDepth(renderer,{legacy});
        const waterMaterial=new T.MeshBasicMaterial({color:0xff0000,opacity:.8});
        applyDepthEffect(waterMaterial,depth,"diffuseColor.a*=clamp(depthGap/2.0,0.0,1.0);","test-region",2);
        const water=new T.Mesh(new T.PlaneGeometry(3,3),waterMaterial);water.position.z=1;scene.add(water);
        const store=createInstanceStore({root,legacy,cellCm:200,templateForTarget:()=>template,isVisible:p=>!p.hidden,
          matrixForPlacement:p=>new T.Matrix4().makeTranslation(p.state.x/100,p.state.y/100,p.state.z/100)});
        for(const p of structuredClone(rows))store.add(p);store.flush(camera);
        depth.render(scene,camera);
        const gl=renderer.getContext(),pixels=new Uint8Array(128*128*4);gl.readPixels(0,0,128,128,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        images.push({pixels,depth:depth.stats()});
        if(root.children.some(m=>m.name==="Authored water depth instances"))throw Error("Depth-only instances leaked into color scene");
        store.dispose();if(root.children.length)throw Error("Depth buffers retained after store disposal");
        depth.dispose();waterMaterial.dispose();water.geometry.dispose();
      }
      let different=0,max=0;for(let i=0;i<images[0].pixels.length;i++){const delta=Math.abs(images[0].pixels[i]-images[1].pixels[i]);if(delta>3)different++;max=Math.max(max,delta);}
      if(different>images[0].pixels.length*.001)throw Error("Water depth batch image changed");
      if(images[1].depth.triangles>=images[0].depth.triangles)throw Error("Water instance filtering did not save geometry");
      result.push({perspective,different,max,before:images[0].depth,after:images[1].depth});
    }
    geometry.dispose();material.dispose();renderer.dispose();return result;
  });
  report.poses=await page.evaluate(async()=>{
    const T=await import("three"),{GLTFLoader}=await import("three/addons/loaders/GLTFLoader.js"),{DRACOLoader}=await import("three/addons/loaders/DRACOLoader.js");
    const {prepareStaticPoses,staticPoseGeometry,prepareEditablePoseRaycasts}=await import("./basebuilder-static-pose.js");
    const SkeletonUtils=await import("three/addons/utils/SkeletonUtils.js");
    const index=await (await fetch("./basebuilder-index.json")).json();
    const draco=new DRACOLoader().setDecoderPath("https://www.gstatic.com/draco/versioned/decoders/1.5.7/");
    const loader=new GLTFLoader().setDRACOLoader(draco),renderer=new T.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    renderer.setSize(256,256);const scene=new T.Scene();scene.background=new T.Color("#303b40");scene.add(new T.HemisphereLight(0xffffff,0x777777,2));
    const light=new T.DirectionalLight(0xffffff,3);light.position.set(5,10,8);scene.add(light);
    const camera=new T.PerspectiveCamera(50,1,.01,10000),results=[];
    const pixels=()=>{renderer.render(scene,camera);const gl=renderer.getContext(),v=new Uint8Array(256*256*4);gl.readPixels(0,0,256,256,gl.RGBA,gl.UNSIGNED_BYTE,v);return v;};
    for(const stem of ["BP_NPC_Doric_Dowdun_C","BP_NPC_HighLightingTheProblem_Statue_C","BP_PlayerCharacter_C"]) {
      const target=index.targets.find(t=>t.asset_stem===stem);if(!target)throw Error("Missing pose fixture "+stem);
      const path=new URL(`../../RSDWModel/${index.version}/WebAssets/${target.components[0].gltf_path}`,location.href);
      const model=await loader.loadAsync(path.href),root=model.scene;scene.add(root);root.updateMatrixWorld(true);
      const box=new T.Box3().setFromObject(root),center=box.getCenter(new T.Vector3()),radius=box.getSize(new T.Vector3()).length();
      camera.position.copy(center).add(new T.Vector3(.8,.5,1).normalize().multiplyScalar(radius*1.3));camera.lookAt(center);camera.updateMatrixWorld();
      const before=pixels();await prepareStaticPoses(root);
      const frozen=new T.Group();root.traverse(o=>{if(!o.isMesh)return;const mesh=new T.Mesh(staticPoseGeometry(o)||o.geometry,o.material);
        mesh.matrixAutoUpdate=false;mesh.matrix.copy(o.matrixWorld);frozen.add(mesh);});
      root.removeFromParent();scene.add(frozen);const after=pixels();let different=0,max=0,nonblank=0;
      for(let i=0;i<before.length;i++){const delta=Math.abs(before[i]-after[i]);if(delta>3)different++;max=Math.max(max,delta);if(i>4&&before[i]!==before[i%4])nonblank++;}
      if(different>before.length*.001||nonblank<100)throw Error(`Pose mismatch ${stem}: ${different}, max ${max}`);
      frozen.removeFromParent();
      root.position.set(4,2,3);root.rotation.set(.2,.3,.1);root.scale.set(-1,1.2,.8);root.updateMatrixWorld(true);
      const editable=SkeletonUtils.clone(root);prepareEditablePoseRaycasts(root,editable);editable.updateMatrixWorld(true);
      const movedBox=new T.Box3().setFromObject(root),movedCenter=movedBox.getCenter(new T.Vector3());
      camera.position.copy(movedCenter).add(new T.Vector3(.8,.5,1).normalize().multiplyScalar(radius*1.5));camera.lookAt(movedCenter);camera.updateMatrixWorld();
      let checkedRays=0,rayHits=0;
      for(let x=-.4;x<=.4;x+=.13)for(let y=-.4;y<=.4;y+=.13){
        const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2(x,y),camera);
        const a=ray.intersectObject(root,true)[0],b=ray.intersectObject(editable,true)[0];checkedRays++;
        if(Boolean(a)!==Boolean(b)||a&&Math.abs(a.distance-b.distance)>Math.max(1,a.distance)*1e-4)throw Error(`Pose picking mismatch ${stem}`);
        if(b){rayHits++;let parent=b.object;while(parent.parent)parent=parent.parent;if(parent!==editable)throw Error("Pose picking lost editable identity");}
      }
      if(!rayHits)throw Error("Pose rays missed every model");
      results.push({stem,different,max,nonblank,checkedRays,rayHits});
    }
    draco.dispose();renderer.dispose();return results;
  });
  if(args.builder){await page.close();const {compareBuilderImages}=await import("./WorldBuilderVisualChecks.mjs");report.builder=await compareBuilderImages({browser,out,url:args.url});}
  assert.deepEqual(report.errors,[]);report.status="passed";console.log(`Passed ${report.cases.length} rendering/cell-migration/visibility/disposal cases`);
}catch(e){report.status="failed";report.error=String(e.stack||e);console.error(e);process.exitCode=1;}
finally{await writeFile(resolve(out,"InstanceValidation.json"),JSON.stringify(report,null,2));await browser.close();}
