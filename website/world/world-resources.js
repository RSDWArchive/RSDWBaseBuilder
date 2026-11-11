import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { createLeaseCache, createJobPool, STREAM_POLICY } from "./world-streaming.js";
import { createWorldAssetRenderer } from "./world-assets.js";
import { createWorkBudget } from "./world-work-budget.js";

export function collectResources(roots) {
  const geometries=new Set(),materials=new Set(),textures=new Set();
  for(const root of roots)root.traverse(o=>{
    if(o.geometry)geometries.add(o.geometry);
    for(const m of [o.material].flat().filter(Boolean))materials.add(m);
  });
  for(const m of materials)for(const value of [...Object.values(m),...Object.values(m.userData || {})])if(value?.isTexture)textures.add(value);
  return {geometries,materials,textures};
}
export function disposeModel(model) {
  const resources=collectResources([model.scene]);
  for(const set of Object.values(resources))for(const resource of set)resource.dispose();
  // Texture.dispose releases GPU storage, but GLTF ImageBitmaps also own decoded memory.
  for(const image of new Set([...resources.textures].map(t=>t.image)))image?.close?.();
}
export function estimateResources(roots) {
  const {geometries,textures}=collectResources(roots);let bytes=0;
  for(const g of geometries) {
    const arrays=new Set(Object.values(g.attributes).map(a=>a.array || a.data?.array));if(g.index)arrays.add(g.index.array);
    for(const array of arrays)bytes+=array?.byteLength || 0;
  }
  for(const t of textures){const i=t.image;bytes+=(i?.width || 0)*(i?.height || 0)*4*(t.generateMipmaps?4/3:1);}
  for(const root of roots)root.traverse(o=>{if(o.instanceMatrix)bytes+=o.instanceMatrix.array.byteLength;});
  return {estimatedBytes:Math.ceil(bytes),geometries:geometries.size,textures:textures.size};
}

export function createWorldResources(renderer) {
  const draco=new DRACOLoader().setDecoderPath("https://www.gstatic.com/draco/versioned/decoders/1.5.7/").setWorkerLimit(4);
  const loader=new GLTFLoader().setDRACOLoader(draco),textures=new THREE.TextureLoader();
  const models=createLeaseCache(),images=createLeaseCache(),bundles=createLeaseCache();
  const jobs=createJobPool(STREAM_POLICY.maxAssetJobs);
  const checkpoint=createWorkBudget();
  const model=(url,owner)=>models.acquire(String(url),owner,()=>loader.loadAsync(String(url)),disposeModel);
  function texture(url,color,owner) {
    return images.acquire(String(url)+":"+color,owner,async()=>{
      const t=await textures.loadAsync(String(url));t.colorSpace=color?THREE.SRGBColorSpace:THREE.NoColorSpace;
      t.flipY=false;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());return t;
    },t=>t.dispose());
  }
  async function addAsset({asset,placements,owner,dataset,originCm,depth,layers,active}) {
    const key=dataset.config.root.href+":"+originCm.join(",")+":"+asset.id;
    const bundle=await bundles.acquire(key,owner,()=>({owner:Symbol(key),materials:new Map(),mirrors:new Map()}),b=>{
      // Successful/failed section jobs settle before releasing the owning bundle.
      for(const m of b.resolvedMaterials || [])m.dispose();
      for(const g of b.mirrors.values())g.dispose();
      models.release(b.owner);images.release(b.owner);
    });
    const data={...dataset.shared,region:{...dataset.shared.region,origin_cm:[...originCm]}};
    const assets=createWorldAssetRenderer({getData:()=>data,modelRoot:dataset.config.models,regionRoot:dataset.config.root,
      loadModel:url=>model(url,bundle.owner),loadTexture:(path,color=false)=>texture(new URL(path,dataset.config.root),color,bundle.owner),
      materialCache:bundle.materials,mirrorCache:bundle.mirrors,sceneDepth:depth,layers,onAssetAdded:active,checkpoint,active});
    try {active();await assets.addAsset(asset,placements);active();}
    finally {bundle.resolvedMaterials=(await Promise.allSettled(bundle.materials.values())).filter(r=>r.status==="fulfilled").map(r=>r.value);}
  }
  return {jobs,model,texture,addAsset,
    release(owner){bundles.release(owner);models.release(owner);images.release(owner);},
    stats:()=>({models:models.stats(),textures:images.stats(),bundles:bundles.stats(),jobs:jobs.stats()}),
    dispose:()=>draco.dispose()};
}
