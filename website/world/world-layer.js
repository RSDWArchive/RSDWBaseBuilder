import * as THREE from "three";
import { createSceneDepth } from "./world-depth.js";
import { uePoint } from "./world-transforms.js";
import { createWorldResources, estimateResources, collectResources } from "./world-resources.js";
import { intersectsXY, sectionFocus, STREAM_POLICY } from "./world-streaming.js";
import { createWorkBudget } from "./world-work-budget.js";

const layerNames=["terrain","trees","buildings","roads","scenery","helpers","bounds"];
const cancelled=()=>new DOMException("World load cancelled","AbortError");

export async function readWorldDataset(config, version) {
  const read=async path=>{const r=await fetch(new URL(path,config.root));if(!r.ok)throw Error(`${path}: HTTP ${r.status}`);return r.json();};
  const index=await read("WorldIndex.json"),shared=await read(index.shared || "WorldShared.json");
  if(index.schema!=="RSDW.WorldIndex.v1" || shared.schema!=="RSDW.WorldShared.v1" || index.version!==version || shared.version!==version || config.version!==version)
    throw Error("World and builder dataset versions do not match");
  const spanning=await read(index.spanning);
  return {config,index,shared,spanning};
}

export function createWorldLayer({renderer,root,getCamera,originCm,onStatus=()=>{},isBusy=()=>false}) {
  const depth=createSceneDepth(renderer),resources=createWorldResources(renderer);
  const resident=new Map(),units=new Map(),manifests=new Map(),failures=new Map();
  const placementRecords=new Map(),meshRows=new Map();
  const warmedTextures=new WeakSet();
  const visibility=Object.fromEntries(layerNames.map(n=>[n,!["helpers","bounds"].includes(n)]));
  const placementsRoot=new THREE.Group();placementsRoot.name="Shared world placements";
  const placementLayers=makeLayers(placementsRoot);
  let dataset=null,assetMap=new Map(),spanIds=new Set(),wanted=[],requested=null,staging=null,queue=null,epoch=0,disposed=false,lastRender=null,budgetDeferred=[];
  let status={phase:"unloaded",sectionId:null,loadedSectionId:null,loadedSectionIds:[],placements:0};
  const idle=async token=>{while(isBusy()){if(token!==epoch || disposed)throw cancelled();await new Promise(r=>setTimeout(r,40));}if(token!==epoch || disposed)throw cancelled();};
  function publish(extra={}) {
    const placements=new Set();for(const g of resident.values())for(const id of g.placementIds)placements.add(id);
    status={...status,...extra,loadedSectionIds:[...resident.keys()],loadedSectionId:resident.has(requested)?requested:null,
      sectionId:requested,placements:placements.size,pending:wanted.filter(id=>!resident.has(id)&&!failures.has(id)&&!budgetDeferred.includes(id)),
      failed:[...failures].filter(([id])=>wanted.includes(id)).map(([id,error])=>({id,error})),deferred:[...budgetDeferred]};
    onStatus({...status});
  }
  function makeLayers(group) {
    return Object.fromEntries(layerNames.map(name=>{const g=new THREE.Group();g.name=name;g.visible=visibility[name];group.add(g);return [name,g];}));
  }
  function surfaceRows(group) {
    const rows=[];group.updateMatrixWorld(true);
    for(const layer of group.children)if(["terrain","buildings","scenery"].includes(layer.name))layer.traverse(o=>{
      if(o.isMesh && ![o.material].flat().some(m=>m.transparent || ["water","foam","foliage"].includes(m.userData.sourceSettings?.family)))
        rows.push({object:o,bounds:new THREE.Box3().setFromObject(o)});
    });return rows;
  }
  function disposeInstances(group) {group.removeFromParent();group.traverse(o=>{if(o.isInstancedMesh)o.dispose();});}
  function disposeUnit(entry) {
    if(entry.owners.size || !entry.settled || entry.disposed)return;
    entry.disposed=true;if(units.get(entry.key)===entry)units.delete(entry.key);
    if(entry.unit)disposeInstances(entry.unit.group);else if(entry.pendingGroup)disposeInstances(entry.pendingGroup);
    resources.release(entry);
  }
  async function sharedUnit(key,g,build) {
    let entry=units.get(key);
    if(!entry) {
      entry={key,owners:new Set(),committed:new Set(),settled:false,disposed:false};units.set(key,entry);
      entry.promise=Promise.resolve().then(()=>build(entry)).then(unit=>{entry.unit=unit;return unit;})
        .catch(error=>{if(units.get(key)===entry)units.delete(key);throw error;})
        .finally(()=>{entry.settled=true;disposeUnit(entry);});
    }
    entry.owners.add(g);g.units.add(entry);return entry.promise;
  }
  function releaseSection(g) {
    if(g.released)return;g.released=true;disposeInstances(g.group);resources.release(g);
    if(g.committed) {
      const changed=new Set();
      for(const id of g.normalIds){const record=placementRecords.get(id);if(!record)continue;record.owners.delete(g);
        if(!record.owners.size){placementRecords.delete(id);for(const mesh of record.meshes)changed.add(mesh);}}
      const matrix=new THREE.Matrix4();
      for(const mesh of changed) {
        const row=meshRows.get(mesh),ids=mesh.userData.placementIds,keep=[];
        for(let i=0;i<ids.length;i++)if(placementRecords.has(ids[i])){mesh.getMatrixAt(i,matrix);mesh.setMatrixAt(keep.length,matrix);keep.push(ids[i]);}
        mesh.userData.placementIds=keep;mesh.count=keep.length;
        if(keep.length){mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingBox();mesh.computeBoundingSphere();row.bounds.setFromObject(mesh);}
        else {mesh.removeFromParent();mesh.dispose();meshRows.delete(mesh);row.assetOwner.meshes--;if(!row.assetOwner.meshes)resources.release(row.assetOwner);}
      }
      if(!meshRows.size)placementsRoot.removeFromParent();
    } else for(const owner of g.assetOwners)resources.release(owner);
    for(const entry of g.units){entry.owners.delete(g);entry.committed.delete(g);if(!entry.committed.size)entry.unit?.group.removeFromParent();disposeUnit(entry);}
  }
  function evict(id) {const g=resident.get(id);if(g){resident.delete(id);releaseSection(g);}}
  async function readSection(row,signal) {
    if(manifests.has(row.id))return manifests.get(row.id);
    const r=await fetch(new URL(row.path,dataset.config.root),{signal});if(!r.ok)throw Error(`Section ${row.id}: HTTP ${r.status}`);
    const part=await r.json();if(!Array.isArray(part.placements)||!Array.isArray(part.terrain))throw Error("Invalid section "+row.id);
    manifests.set(row.id,part);if(manifests.size>STREAM_POLICY.manifestLimit)manifests.delete(manifests.keys().next().value);
    return part;
  }
  async function buildSection(row,token) {
    const g={row,group:new THREE.Group(),units:new Set(),abort:new AbortController(),placementIds:new Set(),normalIds:new Set(),assetOwners:new Set(),released:false,committed:false};
    staging=g;g.group.name=row.name;g.layers=makeLayers(g.group);
    const active=()=>{if(epoch!==token || g.abort.signal.aborted || !wanted.includes(row.id) || disposed)throw cancelled();};
    try {
      const part=await readSection(row,g.abort.signal);active();
      const spanning=dataset.spanning.filter(p=>intersectsXY({min:p.bounds[0],max:p.bounds[1]},row.bounds_cm));
      const checkpoint=createWorkBudget();
      const byAsset=new Map();for(const p of part.placements){g.placementIds.add(p.id);if(p.baked_road||spanIds.has(p.id))continue;g.normalIds.add(p.id);
        if(placementRecords.has(p.id))continue;if(!byAsset.has(p.asset))byAsset.set(p.asset,[]);byAsset.get(p.asset).push(p);
        const pause=checkpoint();if(pause){await pause;active();}}
      for(const p of spanning)g.placementIds.add(p.id);
      const tasks=[...part.terrain.map(tile=>()=>sharedUnit("terrain:"+tile.source,g,async owner=>{
        const group=new THREE.Group(),layers=makeLayers(group);
        const model=await resources.model(new URL(tile.path,dataset.config.root),owner);
        const object=model.scene.clone(true);object.position.add(uePoint(dataset.shared.region.origin_cm,originCm));layers.terrain.add(object);
        return {group,layers,surfaces:surfaceRows(group),terrain:tile.source};
      })),...spanning.filter(p=>!p.baked_road).map(p=>()=>sharedUnit("span:"+p.id,g,async owner=>{
        const group=new THREE.Group(),layers=makeLayers(group);owner.pendingGroup=group;
        const asset=assetMap.get(p.asset);if(!asset)throw Error("Missing spanning asset "+p.asset);
        await resources.addAsset({asset,placements:[p],owner,dataset,originCm,depth,layers,active});
        return {group,layers,surfaces:surfaceRows(group)};
      })),...[...byAsset].map(([id,placements])=>async()=>{
        const asset=assetMap.get(id);if(!asset)throw Error("Missing world asset "+id);
        const owner={asset:id,meshes:0};g.assetOwners.add(owner);
        await resources.addAsset({asset,placements,owner,dataset,originCm,depth,layers:g.layers,active});
      })];
      const results=await Promise.allSettled(tasks.map(task=>resources.jobs.run(async()=>{active();await task();active();},10)));
      const error=results.find(r=>r.status==="rejected");if(error)throw error.reason;
      // Spread texture uploads across frames and compile against the host lighting
      // before the detail swap, rather than stalling the first visible frame.
      const compileRoot=new THREE.Group();compileRoot.add(g.group);
      for(const entry of g.units)if(!entry.committed.size)compileRoot.add(entry.unit.group);
      let uploadStart=performance.now();
      await idle(token);
      for(const texture of collectResources([compileRoot]).textures)if(!warmedTextures.has(texture)) {
        active();renderer.initTexture(texture);warmedTextures.add(texture);
        if(performance.now()-uploadStart>6){await new Promise(r=>requestAnimationFrame(r));await idle(token);uploadStart=performance.now();}
      }
      active();await renderer.compileAsync(compileRoot,getCamera(),root.parent);active();
      active();g.surfaces=surfaceRows(g.group);g.bounds=new THREE.Box3(uePoint(row.bounds_cm.min,originCm),uePoint(row.bounds_cm.max,originCm));
      g.focus=sectionFocus(row,part.terrain);await idle(token);active();
      for(const id of g.normalIds){if(!placementRecords.has(id))placementRecords.set(id,{owners:new Set(),meshes:new Set()});placementRecords.get(id).owners.add(g);}
      const eligible=new Set(g.surfaces.map(r=>r.object));
      const ownersByAsset=new Map([...g.assetOwners].map(owner=>[owner.asset,owner]));
      for(const layer of g.group.children)for(const mesh of [...layer.children]) {
        const assetOwner=ownersByAsset.get(mesh.userData.asset);assetOwner.meshes++;
        placementLayers[layer.name].add(mesh);mesh.updateMatrixWorld(true);
        meshRows.set(mesh,{object:mesh,bounds:new THREE.Box3().setFromObject(mesh),eligible:eligible.has(mesh),assetOwner});
        for(const id of mesh.userData.placementIds)placementRecords.get(id).meshes.add(mesh);
      }
      for(const owner of g.assetOwners)if(!owner.meshes)resources.release(owner);
      g.committed=true;resident.set(row.id,g);root.add(placementsRoot);
      for(const entry of g.units){entry.committed.add(g);for(const name of layerNames)entry.unit.layers[name].visible=visibility[name];root.add(entry.unit.group);}
      return g;
    } catch(error){releaseSection(g);throw error;}
    finally {if(staging===g)staging=null;}
  }
  function launch() {
    if(queue)return queue;
    queue=(async()=>{
      const token=epoch;
      while(token===epoch && !disposed) {
        await idle(token);
        const next=wanted.find(id=>!resident.has(id)&&!failures.has(id)&&!budgetDeferred.includes(id));
        if(!next)break;
        // Keep the old destination until one new section commits; preserve shared neighbors.
        if(resident.size>=STREAM_POLICY.maxSections)for(const id of [...resident.keys()])if(!wanted.includes(id)){evict(id);break;}
        if(resident.size && wanted[0]!==next && estimateResources([...root.children]).estimatedBytes>=STREAM_POLICY.estimatedBytes){budgetDeferred.push(next);continue;}
        publish({phase:"loading",error:null});
        try {await buildSection(dataset.index.sections.find(s=>s.id===next),token);}
        catch(error){if(error.name!=="AbortError"&&token===epoch)failures.set(next,error.message);}
        if(token!==epoch)break;
        await idle(token);
        if(resident.has(wanted[0]))for(const id of [...resident.keys()])if(!wanted.includes(id))evict(id);
        publish();
      }
      if(token===epoch){await idle(token);if(!wanted.length||resident.has(wanted[0]))for(const id of [...resident.keys()])if(!wanted.includes(id))evict(id);
        publish({phase:failures.size?(resident.size?"partial":"error"):resident.size?"ready":"unloaded",error:null});}
    })().catch(error=>{if(error.name!=="AbortError")publish({phase:"error",error:error.message});}).finally(()=>{queue=null;});
    return queue;
  }
  async function setSections({dataset:input,sectionIds,sectionId=sectionIds[0] || null,retry=false}) {
    if(disposed)throw Error("World layer disposed");
    for(const id of sectionIds)if(!input.index.sections.some(s=>s.id===id))throw Error("Unknown world section: "+id);
    if(dataset&&dataset!==input){unload();manifests.clear();}
    if(dataset!==input){assetMap=new Map(input.shared.assets.map(a=>[a.id,a]));spanIds=new Set(input.spanning.map(p=>p.id));}
    dataset=input;requested=sectionId;wanted=[...new Set(sectionIds)].slice(0,STREAM_POLICY.maxSections);budgetDeferred=[];
    if(retry){failures.clear();for(const id of wanted)if(!resident.has(id))manifests.delete(id);}
    else for(const id of failures.keys())if(!wanted.includes(id))failures.delete(id);
    if(staging&&!wanted.includes(staging.row.id))staging.abort.abort();
    await launch();
    if(wanted.some(id=>!resident.has(id)&&!failures.has(id)&&!budgetDeferred.includes(id)))await launch();
    return {...status};
  }
  function unload() {
    epoch++;wanted=[];requested=null;failures.clear();budgetDeferred=[];
    staging?.abort.abort();for(const id of [...resident.keys()])evict(id);
    publish({phase:"unloaded",error:null});
  }
  function surface(ray) {
    const caster=new THREE.Raycaster();caster.ray.copy(ray);let best=null;const visited=new Set();
    const candidates=[...meshRows.values()].filter(r=>r.eligible);
    for(const entry of units.values())if(entry.committed.size)candidates.push(...entry.unit.surfaces);
    for(const {object,bounds} of candidates) {
      if(visited.has(object))continue;visited.add(object);
      let visible=true;for(let p=object;p;p=p.parent)if(!p.visible)visible=false;
      if(!visible || !ray.intersectsBox(bounds))continue;
      const hit=caster.intersectObject(object,false)[0];if(hit&&(!best||hit.distance<best.distance))best=hit;
    }return best;
  }
  return {setSections,unload,resources,
    prepareEditable:(root,scene)=>depth.prepareEditable(root,getCamera(),scene),
    loadSection:async options=>{const result=await setSections({...options,sectionIds:[options.sectionId],retry:true});if(result.failed.length)throw Error(result.failed[0].error);return result;},
    setOrigin(value){unload();originCm.splice(0,3,...value);},
    setLayerVisible(name,value){if(!(name in visibility))return;visibility[name]=!!value;
      placementLayers[name].visible=!!value;
      for(const g of [...resident.values(),...(staging?[staging]:[])])g.layers[name].visible=!!value;
      for(const e of units.values())if(e.unit)e.unit.layers[name].visible=!!value;},
    getVisibility:()=>({...visibility}),getStatus:()=>({...status}),
    getBounds(){if(!resident.size)return null;const box=new THREE.Box3();for(const g of resident.values())box.union(g.bounds);return box;},
    getFocus:()=>{const g=resident.get(requested)||resident.values().next().value;return g?uePoint(g.focus,originCm):null;},
    getTerrainIds:()=>new Set([...units.values()].filter(e=>e.committed.size&&e.unit?.terrain).map(e=>e.unit.terrain)),
    getRenderMetrics:()=>({depth:depth.stats(),render:lastRender}),
    getMetrics:()=>({phase:status.phase,worldRoots:root.children.length,resident:[...resident.keys()],surfaces:meshRows.size,uniquePlacements:placementRecords.size,
      ...estimateResources([...root.children]),cache:resources.stats(),depth:depth.stats(),render:lastRender}),
    raycastSurface:surface,
    render(scene){depth.render(scene,getCamera());lastRender={...renderer.info.render};},
    async dispose(){disposed=true;unload();await queue;depth.dispose();resources.dispose();},
    settled:()=>queue || Promise.resolve(),
  };
}
