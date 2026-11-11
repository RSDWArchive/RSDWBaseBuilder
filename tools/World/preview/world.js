import { createWorldAssetRenderer } from "../../../website/world/world-assets.js";
import { createOverviewTile } from "../../../website/world/world-navigation-visuals.js";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { ueMatrix, uePoint, worldPoint } from "./world-transforms.js";
import { openWorldBrowser } from "./world-browser.js";
import { applyWaterMaterial } from "./world-water.js";
import { createSceneDepth, applyWaterDepth } from "./world-depth.js";
import { applyFoamMaterial } from "./world-foam.js";
import { createVisualAudit } from "./world-visual-audit.js";
import { applySurfaceSettings, surfaceSettingsIssues } from "./world-surface.js";

const query = new URLSearchParams(location.search);
const worldRequested=query.has("world");
const regionRoot = new URL(query.get("region") || (worldRequested?"../../../_build/world-region/1.0.0.5/whole-world/":"../../../_build/world-region/1.0.0.5/fellhollow-road-ruins/"), location.href);
const modelRoot = new URL(query.get("models") || "../../../../RSDWModel/1.0.0.5/WebAssets/", location.href);
const viewport = document.querySelector("#viewport");
const phase = document.querySelector("#phase");
const progress = document.querySelector("#progress");
const renderer = new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:"high-performance",logarithmicDepthBuffer:worldRequested});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1;
const sceneDepth=createSceneDepth(renderer);
viewport.prepend(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x303b40);
const camera = new THREE.PerspectiveCamera(50,1,0.1,5000);
const controls = new OrbitControls(camera,renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.maxPolarAngle = Math.PI-0.01;
controls.mouseButtons = {LEFT:THREE.MOUSE.ROTATE, MIDDLE:THREE.MOUSE.ROTATE, RIGHT:THREE.MOUSE.PAN};
const pmrem = new THREE.PMREMGenerator(renderer);
const environment = new RoomEnvironment();
scene.environment = pmrem.fromScene(environment,0.04).texture;
scene.environmentIntensity = 0.55;
environment.dispose();
pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xe4efff,0x676058,1.4));
const sun = new THREE.DirectionalLight(0xfff3dd,2.4);
sun.position.set(-100,230,-80);
scene.add(sun);
const layers = Object.fromEntries(["terrain","trees","buildings","roads","scenery","helpers","bounds"].map(name => {
  const group = new THREE.Group(); group.name = name; scene.add(group); return [name,group];
}));
layers.bounds.visible = false;
layers.helpers.visible = query.get("helpers")==="1";
document.querySelector('[data-layer="helpers"]').checked=layers.helpers.visible;
const draco = new DRACOLoader();
draco.setDecoderPath("https://www.gstatic.com/draco/versioned/decoders/1.5.7/");
draco.setWorkerLimit(4);
const gltfLoader = new GLTFLoader().setDRACOLoader(draco);
const textureLoader = new THREE.TextureLoader();
const modelCache = new Map(), textureCache = new Map(), materialCache = new Map(), mirrorCache = new Map();
const terrainMaterials = [];
const timings = {started:performance.now(),frameMs:[],errors:[]};
let data, worldBrowser, ready=false, lastFrame=0, lastStats=0, frameCount=0, renderNeeded=true;
const overviewObjects=new Map();
controls.addEventListener("change",()=>{renderNeeded=true;});
let longTaskMax=0;
if (globalThis.PerformanceObserver) {
  try {new PerformanceObserver(list => {for(const e of list.getEntries()) longTaskMax=Math.max(longTaskMax,e.duration);}).observe({type:"longtask",buffered:true});} catch {}
}
function fail(error) {
  timings.errors.push(String(error));
  document.querySelector("#error").hidden=false;
  document.querySelector("#error").textContent=String(error);
  document.querySelector("#loading").hidden=true;
  console.error(error);
}
function loadModel(url) {
  const key=String(url);
  if(!modelCache.has(key)) modelCache.set(key,gltfLoader.loadAsync(key));
  return modelCache.get(key);
}
function loadTexture(path, color=false) {
  const key=path+color;
  if(!textureCache.has(key)) textureCache.set(key,textureLoader.loadAsync(new URL(path,regionRoot).href).then(t=>{
    t.colorSpace=color?THREE.SRGBColorSpace:THREE.NoColorSpace;
    t.flipY=false;
    t.wrapS=t.wrapT=THREE.RepeatWrapping;
    t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());
    return t;
  }));
  return textureCache.get(key);
}
const {addAsset}=createWorldAssetRenderer({getData:()=>data,modelRoot,regionRoot,loadModel,loadTexture,
  materialCache,mirrorCache,sceneDepth,layers,onAssetAdded:()=>{renderNeeded=true;}});
async function pool(rows,worker,limit=8) {
  let cursor=0,done=0;
  await Promise.all(Array.from({length:Math.min(limit,rows.length)},async()=>{
    while(cursor<rows.length) {const i=cursor++;await worker(rows[i],i);progress.value=++done/rows.length;}
  }));
}
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
function setView(kind="oblique") {
  if(!data) return;
  const center=uePoint(data.region.focus_cm || data.region.origin_cm,data.region.origin_cm);
  controls.target.copy(center);
  if(worldRequested) {
    const b=data.region.bounds_cm;
    const span=Math.max(b.max[0]-b.min[0],b.max[1]-b.min[1])/100;
    const focus=data.region.focus_cm || data.region.origin_cm;
    const radius=Math.hypot(...b.min.map((v,i)=>Math.max(Math.abs(v-focus[i]),Math.abs(b.max[i]-focus[i]))))/100;
    const halfFov=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(camera.aspect,1));
    const distance=Math.max(20,radius/Math.sin(halfFov)*1.08);
    camera.far=Math.max(50000,distance*10);camera.updateProjectionMatrix();
    const offset=kind==="overhead"?[0,distance,0.01]:kind==="road"?[0,Math.max(5,span*0.02),Math.max(40,span*0.1)]:[distance*.65,distance*.8,distance*.65];
    const direction=new THREE.Vector3(...offset);
    if(kind!=="road")direction.normalize().multiplyScalar(distance);
    camera.position.copy(center).add(direction);camera.up.set(0,1,0);controls.update();return;
  }
  const fit=Math.max(1,1/Math.max(camera.aspect,0.35));
  const preset=data.region.viewpoints?.[kind];
  if(preset) {
    controls.target.copy(uePoint(preset.target_cm,data.region.origin_cm));
    const offset=uePoint(preset.position_cm,data.region.origin_cm).sub(controls.target);
    camera.position.copy(controls.target).add(offset.multiplyScalar(kind==="road"?1:fit));
    camera.up.set(0,1,0);controls.update();return;
  }
  const views={oblique:[190*fit,180*fit,200*fit],overhead:[0,380*fit,0.01],road:[-15,7,30]};
  camera.position.copy(center).add(new THREE.Vector3().fromArray(views[kind]||views.oblique));
  if(kind==="road") controls.target.copy(center).add(new THREE.Vector3(0,0,-10));
  camera.up.set(0,1,0);controls.update();
}
function applyBookmark(bookmark) {
  if(!bookmark || [bookmark.position_cm,bookmark.target_cm].some(v=>!Array.isArray(v)||v.length!==3||!v.every(Number.isFinite))) return;
  if(bookmark.version!==data.version || bookmark.region!==data.region.id) return;
  camera.position.copy(uePoint(bookmark.position_cm,data.region.origin_cm));
  controls.target.copy(uePoint(bookmark.target_cm,data.region.origin_cm));
  controls.update();
}
function bookmark() {return {version:data.version,region:data.region.id,position_cm:worldPoint(camera.position,data.region.origin_cm),target_cm:worldPoint(controls.target,data.region.origin_cm)};}
async function start() {
  const response=await fetch(new URL(worldRequested?"WorldShared.json":"WorldRegion.json",regionRoot));
  if(!response.ok) throw new Error("Region manifest is unavailable. HTTP "+response.status);
  data=await response.json();
  if(worldRequested) {
    if(data.schema!=="RSDW.WorldShared.v1")throw new Error("Unsupported world schema");
    data.placements=[];data.terrain=[];
    if(query.has("materialAudit")) {
      document.body.classList.add("material-audit");
      window.worldVisualAudit=createVisualAudit({renderer,scene,camera,controls,layers,replaceDetail,
        render:()=>sceneDepth.render(scene,camera),auditMaterials});
      const indexResponse=await fetch(new URL("WorldIndex.json",regionRoot));
      if(!indexResponse.ok)throw new Error("Visual audit needs a matching world index");
      window.worldVisualAudit.scene_sha256=(await indexResponse.json()).scene_sha256;
      return;
    }
    document.title="RSDW World";
    document.querySelector("header strong").textContent="RSDW World";
    document.querySelector("#world-link").href="?sample=1";
    document.querySelector("#world-link").textContent="Sample";
    worldBrowser=await openWorldBrowser({root:regionRoot,data,camera,controls,scene,canvas:renderer.domElement,
      invalidate:()=>{renderNeeded=true;},initialSection:query.get("section"),replaceOverview,replaceDetail,frame:()=>setView(),status:worldStatus});
    if(location.hash.startsWith("#view=")) {
      try {applyBookmark(JSON.parse(decodeURIComponent(location.hash.slice(6))));await worldBrowser.stream();} catch(error) {worldStatus(String(error),true);}
    }
    ready=true;renderNeeded=true;timings.ready=performance.now()-timings.started;
    document.querySelector("#loading").hidden=true;
    window.worldRegionDebug={scene,camera,controls,data,renderer,layers,timings,setView,bookmark,auditMaterials,worldBrowser,metrics,render:()=>sceneDepth.render(scene,camera)};
    return;
  }
  if(data.schema!=="RSDW.WorldRegion.v1") throw new Error("Unsupported region schema");
  setView();
  phase.textContent="Loading terrain";
  await pool(data.terrain,async tile=>{
    const gltf=await loadModel(new URL(tile.path,regionRoot));
    gltf.scene.traverse(o=>{if(o.isMesh) terrainMaterials.push({material:o.material,tile});});
    layers.terrain.add(gltf.scene);
    renderNeeded=true;
  });
  timings.terrain=performance.now()-timings.started;
  const byAsset=new Map();
  for(const p of data.placements) {if(p.baked_road) continue;if(!byAsset.has(p.asset)) byAsset.set(p.asset,[]);byAsset.get(p.asset).push(p);}
  phase.textContent="Loading scenery";
  await pool(data.assets.filter(a=>byAsset.has(a.id)),async asset=>addAsset(asset,byAsset.get(asset.id)));
  const b=data.region.bounds_cm;
  const box=new THREE.Box3(uePoint(b.min,data.region.origin_cm),uePoint(b.max,data.region.origin_cm));
  layers.bounds.add(new THREE.Box3Helper(box,0xe0c896));
  phase.textContent="Preparing materials";
  await renderer.compileAsync(scene,camera);
  if(location.hash.startsWith("#view=")) {try {applyBookmark(JSON.parse(decodeURIComponent(location.hash.slice(6))));} catch {}}
  ready=true;renderNeeded=true;timings.ready=performance.now()-timings.started;
  document.querySelector("#loading").hidden=true;
  window.worldRegionDebug={scene,camera,controls,data,renderer,layers,timings,setView,bookmark,auditMaterials,metrics:()=>metrics(),render:()=>sceneDepth.render(scene,camera)};
}
function worldStatus(message,error=false) {
  document.querySelector("#world-status").textContent=message;
  if(error)fail(message);
}
function disposeObjects(roots) {
  const geometries=new Set(),materials=new Set(),textures=new Set();
  for(const root of roots)root.traverse(o=>{
    if(o.geometry)geometries.add(o.geometry);
    for(const m of [o.material].flat().filter(Boolean))materials.add(m);
    if(o.isInstancedMesh)o.dispose();
  });
  for(const m of materials){for(const value of Object.values(m))if(value?.isTexture)textures.add(value);m.dispose();}
  for(const t of textures)t.dispose();
  for(const g of geometries)g.dispose();
}
async function replaceOverview(tiles) {
  disposeObjects([...layers.bounds.children]);layers.bounds.clear();
  const bounds=data.region.bounds_cm;
  const outline=new THREE.Box3Helper(new THREE.Box3(uePoint(bounds.min,data.region.origin_cm),uePoint(bounds.max,data.region.origin_cm)),0xe0c896);
  outline.userData.overview=true;layers.bounds.add(outline);
  const wanted=new Set(tiles.map(t=>t.source));
  for(const [id,object] of overviewObjects)if(!wanted.has(id)){object.removeFromParent();disposeObjects([object]);overviewObjects.delete(id);}
  await pool(tiles.filter(t=>!overviewObjects.has(t.source)),async tile=>{
    const gltf=await gltfLoader.loadAsync(new URL(tile.overview_path,regionRoot).href);
    const object=createOverviewTile(gltf,tile,data.region.origin_cm,data.region.origin_cm);
    if(!layers.roads.visible)await overviewRoadTexture(object,false);
    overviewObjects.set(tile.source,object);layers.terrain.add(object);renderNeeded=true;
  });
}
async function replaceDetail(request) {
  worldStatus("Loading detail");document.querySelector("#loading").hidden=false;
  phase.textContent="Loading world section";
  const roots=[];
  for(const layer of Object.values(layers))for(const root of [...layer.children])if(!root.userData.overview){roots.push(root);root.removeFromParent();}
  for(const result of await Promise.allSettled(modelCache.values()))if(result.status==="fulfilled")roots.push(result.value.scene);
  disposeObjects(roots);
  for(const result of await Promise.allSettled(materialCache.values()))if(result.status==="fulfilled"){
    const m=result.value;for(const value of Object.values(m))if(value?.isTexture)value.dispose();m.dispose();
  }
  for(const result of await Promise.allSettled(textureCache.values()))if(result.status==="fulfilled")result.value.dispose();
  for(const geometry of mirrorCache.values())geometry.dispose();
  modelCache.clear();materialCache.clear();textureCache.clear();mirrorCache.clear();terrainMaterials.length=0;
  data.placements=request.placements;data.terrain=request.terrain;
  const terrainIds=new Set(request.terrain.map(t=>t.source));
  for(const [id,object] of overviewObjects)object.visible=!terrainIds.has(id);
  renderNeeded=true;
  await pool(request.terrain,async tile=>{
    const gltf=await loadModel(new URL(tile.path,regionRoot));
    const materials=[];
    gltf.scene.traverse(o=>{if(o.isMesh){terrainMaterials.push({material:o.material,tile});materials.push(o.material);}});
    if(!layers.roads.visible) {
      const map=await loadTexture(tile.base_texture,true);map.wrapS=map.wrapT=THREE.ClampToEdgeWrapping;
      for(const m of materials){m.map=map;m.needsUpdate=true;}
    }
    layers.terrain.add(gltf.scene);renderNeeded=true;
  });
  const byAsset=new Map();
  for(const p of request.placements){if(!byAsset.has(p.asset))byAsset.set(p.asset,[]);byAsset.get(p.asset).push(p);}
  await pool(data.assets.filter(a=>byAsset.has(a.id)),a=>addAsset(a,byAsset.get(a.id)));
  await renderer.compileAsync(scene,camera);renderNeeded=true;
  document.querySelector("#loading").hidden=true;worldStatus(request.label);
}
function auditMaterials() {
  const assets=new Map(data.assets.map(a=>[a.id,a])), rows=new Map();
  scene.traverse(o=>{
    const asset=assets.get(o.userData.asset);
    if(!o.isMesh || !asset) return;
    const slot=o.userData.materialSlot, ref=asset.materials[slot] || asset.default_materials[slot];
    const p=data.materials[ref], m=o.material, key=asset.id+":"+slot;
    if(rows.has(key)) {rows.get(key).instances+=o.count??1;return;}
    const issues=[], settings=p?.settings||{};
    const adapted=!!(asset.native || settings.surface_color || settings.emissive_enabled!==undefined || ["foliage","surface_maps","rock","water","foam"].includes(settings.family) || Object.keys(p?.linear_color_sources || {}).length>0 || /Additive|Modulate|AlphaComposite/.test(p?.properties?.BlendMode || "") || p?.projection || (asset.materials[slot] && asset.materials[slot]!==asset.default_materials[slot]));
    issues.push(...surfaceSettingsIssues(m,settings));
    for(const [role,field] of [["base_color","map"],["normal","normalMap"],["emissive","emissiveMap"]]) {
      if(!p?.textures[role] || (role==="normal" && p.projection==="triplanar")) continue;
      if(!m[field]) issues.push("Missing "+role+" texture");
      else if(adapted && m[field].image?.src!==new URL(p.textures[role],regionRoot).href) issues.push("Unexpected "+role+" texture");
    }
    if(settings.emissive_enabled===false && m.emissiveIntensity>0 && Math.max(...m.emissive.toArray())>0) issues.push("Source-disabled emission is active");
    if(settings.family==="water") {
      const water=settings.water;
      for(const field of ["roughness","opacity"]) if(Math.abs(m[field]-water[field])>0.00001) issues.push("Water "+field+" disagrees with descriptor");
      if(m.map || m.roughnessMap || m.vertexColors) issues.push("Stale cached water surface data is active");
      if(Math.abs(m.emissiveIntensity-water.emission)>0.00001) issues.push("Water emission disagrees with enabled flat-color branch");
      if(water.color.some((value,i)=>Math.abs(m.color.toArray()[i]-value)>0.00001)) issues.push("Water color proxy disagrees with descriptor");
      if(p.textures.water_normal_2 && m.userData.waterNormal2?.image?.src!==new URL(p.textures.water_normal_2,regionRoot).href) issues.push("Missing second water normal layer");
      if(water.depth && (!m.userData.sceneDepthEffect || !m.transparent || m.depthWrite)) issues.push("Missing water depth adapter");
    }
    if(settings.family==="foam") {
      if(m.userData.foamMask?.image?.src!==new URL(p.textures.foam_mask,regionRoot).href) issues.push("Missing foam mask");
      if(Math.abs(m.opacity-settings.foam.opacity)>0.00001 || !m.transparent || m.depthWrite) issues.push("Incorrect foam opacity state");
      if(settings.foam.depth_fade_m>0 && !m.userData.sceneDepthEffect) issues.push("Missing foam depth fade");
    }
    const constant=p?.vectors[settings.base_color_parameter];
    if(constant && !p.textures.base_color && (m.map || ["r","g","b"].some(c=>Math.abs(m.color[c]-constant[c.toUpperCase()])>0.00001))) {
      issues.push("Source constant base color is not applied");
    }
    if(settings.emissive_enabled===true && p.textures.emissive) {
      const expected=Math.max(0,p.scalars["Emissive Scale"]??p.scalars["Emissive Add"]??1);
      if(Math.abs(m.emissiveIntensity-expected)>0.00001)issues.push("Emission intensity disagrees with source override");
    }
    if(adapted && p?.properties.BlendMode) {
      const cutoff=settings.alpha_test_enabled!==false && p.properties.BlendMode.includes("Masked")?(p.properties.OpacityMaskClipValue??0.333):0;
      if(Math.abs(m.alphaTest-cutoff)>0.00001) issues.push("Alpha cutoff disagrees with source");
      if(m.side!==(p.properties.TwoSided?THREE.DoubleSide:THREE.FrontSide)) issues.push("Sidedness disagrees with source");
    }
    rows.set(key,{asset:asset.id,source:asset.source,slot,material:ref,instances:o.count??1,adapted,
      status:issues.length?(adapted?"mapping_mismatch":"needs_review"):"no_detected_gap",
      maps:{base_color:!!m.map,normal:!!m.normalMap,emissive:!!m.emissiveMap},issues});
  });
  const materials=[...rows.values()];
  return {schema:"RSDW.WorldMaterialRuntimeAudit.v1",scope:"Loaded mesh sections, not proof of in-game visual parity",
    checked_sections:materials.length,sections_with_issues:materials.filter(r=>r.issues.length).length,
    adapter_mismatches:materials.filter(r=>r.status==="mapping_mismatch").length,materials};
}
async function overviewRoadTexture(object,enabled) {
  const tile=object.userData.tile;
  const path=enabled?tile.road_overview_texture:tile.base_overview_texture;
  if(!path)return;
  const map=await textureLoader.loadAsync(new URL(path,regionRoot).href);
  map.colorSpace=THREE.SRGBColorSpace;map.flipY=false;
  object.traverse(o=>{if(o.isMesh){o.material.map?.dispose();o.material.map=map;o.material.needsUpdate=true;}});
}
async function layerChanged(event) {
  const input=event.target;
  const layer=input.dataset.layer;
  if(!layers[layer]) return;
  layers[layer].visible=input.checked;
  renderNeeded=true;
  if(layer==="roads")await pool([...overviewObjects.values()],o=>overviewRoadTexture(o,input.checked));
  if(layer==="roads") for(const {material,tile} of terrainMaterials) {
    material.map=await loadTexture(input.checked?tile.road_texture:tile.base_texture,true);
    material.map.wrapS=material.map.wrapT=THREE.ClampToEdgeWrapping;
    material.needsUpdate=true;
    renderNeeded=true;
  }
}
document.querySelector("#layers").addEventListener("change",e=>layerChanged(e).catch(fail));
document.querySelector("#frame").addEventListener("click",()=>setView(document.querySelector("#view").value));
document.querySelector("#view").addEventListener("change",e=>setView(e.target.value));
document.querySelector("#bookmark").addEventListener("click",()=>{
  if(!ready) return;
  location.hash="view="+encodeURIComponent(JSON.stringify(bookmark()));
  const a=document.createElement("a"),url=URL.createObjectURL(new Blob([JSON.stringify(bookmark(),null,2)],{type:"application/json"}));
  a.href=url;a.download=data.region.id+"-view.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
document.addEventListener("keydown",e=>{if(e.target.matches("input,select,textarea"))return;if(e.key==="Home"||e.key==="0"){e.preventDefault();setView();}});
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
let lastPointer=0;
renderer.domElement.addEventListener("pointermove",e=>{
  if(!ready||performance.now()-lastPointer<120||e.buttons) return;
  lastPointer=performance.now();
  const r=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);
  raycaster.setFromCamera(pointer,camera);
  const hit=raycaster.intersectObjects(layers.terrain.children,true)[0];
  if(hit) document.querySelector("#coordinates").textContent=worldPoint(hit.point,data.region.origin_cm).map((v,i)=>"XYZ"[i]+" "+v.toFixed(0)).join("   ");
});
new ResizeObserver(()=>{const w=viewport.clientWidth,h=viewport.clientHeight;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);renderNeeded=true;}).observe(viewport);
function metrics() {
  const f=timings.frameMs.slice(-180).sort((a,b)=>a-b);
  const depth=sceneDepth.stats();
  return {ready,load_ms:timings.ready,terrain_ms:timings.terrain,draw_calls:renderer.info.render.calls+depth.draw_calls,triangles:renderer.info.render.triangles+depth.triangles,
    median_frame_ms:f[Math.floor(f.length*.5)]||0,p95_frame_ms:f[Math.floor(f.length*.95)]||0,
    longest_task_ms:longTaskMax,geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,
    heap_bytes:performance.memory?.usedJSHeapSize??null,frames:frameCount,depth,errors:timings.errors};
}
renderer.setAnimationLoop(now=>{
  if(now-lastFrame>=16) {
    controls.update();
    if(renderNeeded) {
      if(ready && now-lastFrame<250) {timings.frameMs.push(now-lastFrame);if(timings.frameMs.length>600) timings.frameMs.shift();}
      sceneDepth.render(scene,camera);frameCount++;lastFrame=now;renderNeeded=false;
    }
  }
  if(now-lastStats>500) {lastStats=now;const m=metrics();document.querySelector("#stats").textContent=ready?
    `${data.placements.length.toLocaleString()} ${worldRequested?"detail placements":"placements"}${worldBrowser?" / "+worldBrowser.index.unique_placements.toLocaleString()+" world":""} | ${m.draw_calls} draws | ${(m.triangles/1e6).toFixed(2)}M triangles | ${(1000/Math.max(m.median_frame_ms,1)).toFixed(0)} FPS | ${(m.load_ms/1000).toFixed(1)}s load`:"Loading region";}
});
start().catch(fail);
