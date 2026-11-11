import * as THREE from "three";
import { uePoint, worldPoint } from "./world-transforms.js";
import { intersectsXY, sectionFocus } from "./world-streaming.js";
import {createOverviewTile,createMapPoints,projectedMarkerDistance} from "./world-navigation-visuals.js";

export function createWorldOverview({root,dataset,resources,originCm,getCamera,onStatus=()=>{},isBusy=()=>false}) {
  const tiles=new Map(),errors=new Map(),owners=new Set();let generation=0,loading=null,area="all",covered=new Set(),enabled=true,terrainVisible=true,markerVisible=true;
  const group=new THREE.Group();group.name="World Overview";root.add(group);
  const markers=createMapPoints();root.add(markers);
  const buildMarker=createMapPoints({size:15,color:"#8fdbcf"});buildMarker.renderOrder=101;root.add(buildMarker);buildMarker.visible=false;
  let rows=[],points=[],buildPoint=null;
  const allowed=()=>dataset.index.sections.filter(s=>area==="all"||s.biome===area);
  function publish(){onStatus({loaded:tiles.size,total:dataset.shared.overview.length,loading:!!loading,failed:[...errors].map(([source,error])=>({source,error}))});}
  function sync() {
    rows=allowed().filter(s=>(s.visible_placements??s.placements)>0||s.terrain>0);
    points=rows.map(r=>uePoint(sectionFocus(r,dataset.shared.overview),originCm));
    markers.geometry.dispose();markers.geometry=new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(points.flatMap(p=>p.toArray()),3));
    for(const [id,t] of tiles)t.object.visible=terrainVisible&&!covered.has(id)&&rows.some(r=>intersectsXY(r.bounds_cm,{min:t.tile.bounds[0],max:t.tile.bounds[1]}));
    group.visible=enabled;markers.visible=enabled&&markerVisible;buildMarker.visible=enabled&&markerVisible&&!!buildPoint;
  }
  async function load({retry=false}={}) {
    if(loading)return loading;if(retry)errors.clear();const token=generation;
    loading=(async()=>{
      await Promise.allSettled(dataset.shared.overview.filter(t=>!tiles.has(t.source)&&!errors.has(t.source)).map(tile=>resources.jobs.run(async()=>{
        if(token!==generation)return;
        const owner=Symbol(tile.source);owners.add(owner);
        try {
          const model=await resources.model(new URL(tile.overview_path,dataset.config.root),owner);
          while(isBusy()&&token===generation)await new Promise(r=>setTimeout(r,40));
          if(token!==generation){resources.release(owner);owners.delete(owner);return;}
          const object=createOverviewTile(model,tile,dataset.shared.region.origin_cm,originCm);
          object.visible=terrainVisible&&!covered.has(tile.source)&&allowed().some(r=>intersectsXY(r.bounds_cm,{min:tile.bounds[0],max:tile.bounds[1]}));
          tiles.set(tile.source,{tile,object,owner});group.add(object);publish();
          await new Promise(r=>requestAnimationFrame(r));
        }catch(error){resources.release(owner);owners.delete(owner);if(token===generation){errors.set(tile.source,error.message);publish();}}
      },0)));
    })().finally(()=>{loading=null;publish();});publish();return loading;
  }
  const projectedDistance=(point,event,rect)=>projectedMarkerDistance(point,event,rect,getCamera());
  function navigationPoint(row) {
    const focus=sectionFocus(row,dataset.shared.overview),caster=new THREE.Raycaster();
    if(!row.terrain)return focus;
    const candidates=[...tiles.values()].filter(t=>intersectsXY(row.bounds_cm,{min:t.tile.bounds[0],max:t.tile.bounds[1]}));
    const points=[focus,...candidates.map(t=>[0,1].map(i=>(Math.max(t.tile.bounds[0][i],row.bounds_cm.min[i])+Math.min(t.tile.bounds[1][i],row.bounds_cm.max[i]))/2))];
    group.updateMatrixWorld(true);
    for(const p of points){caster.ray.set(uePoint([p[0],p[1],Math.max(focus[2],row.bounds_cm.max[2])+100000],originCm),new THREE.Vector3(0,-1,0));
      const hit=caster.intersectObjects(candidates.map(t=>t.object),true)[0];if(hit)return worldPoint(hit.point,originCm);}
    return focus;
  }
  function hit(event,canvas,{terrain=true}={}) {
    if(!enabled)return null;const rect=canvas.getBoundingClientRect();
    if(markerVisible&&buildPoint&&projectedDistance(buildPoint,event,rect)<13)return {build:true,name:"Return to Build"};
    let best=null,distance=13;
    if(markerVisible)points.forEach((p,i)=>{const d=projectedDistance(p,event,rect);if(d<distance){distance=d;best={section:rows[i],name:rows[i].name};}});
    if(best&&terrain)best.point=navigationPoint(best.section);
    if(best)return best;if(!terrain)return null;
    const caster=new THREE.Raycaster();caster.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2),getCamera());
    const candidates=[...tiles.values()].filter(t=>t.object.visible).map(t=>t.object);group.updateMatrixWorld(true);
    const contact=caster.intersectObjects(candidates,true)[0];if(!contact)return null;
    const point=worldPoint(contact.point,originCm),matches=rows.filter(r=>intersectsXY(r.bounds_cm,{min:point,max:point}));
    return matches.length===1?{section:matches[0],point,name:matches[0].name}:matches.length?{choices:matches,point}:null;
  }
  sync();
  return {load,hit,navigationPoint,
    setArea(value){area=value;sync();},
    setVisible(value){enabled=value;group.visible=value;markers.visible=value&&markerVisible;buildMarker.visible=value&&markerVisible&&!!buildPoint;},
    setMarkersVisible(value){if(markerVisible!==value){markerVisible=value;markers.visible=enabled&&value;buildMarker.visible=enabled&&value&&!!buildPoint;}},
    setTerrainVisible(value){terrainVisible=value;sync();},
    setCoverage(ids){if(ids.size===covered.size&&[...ids].every(id=>covered.has(id)))return;covered=new Set(ids);sync();},
    setBuildPoint(point){const p=point?uePoint(point,originCm):null;if(p&&buildPoint?.equals(p))return;buildPoint=p;
      buildMarker.geometry.dispose();buildMarker.geometry=new THREE.BufferGeometry();if(p)buildMarker.geometry.setAttribute("position",new THREE.Float32BufferAttribute(p.toArray(),3));
      buildMarker.visible=enabled&&markerVisible&&!!p;},
    getBounds(){const a=allowed();if(!a.length)return null;return new THREE.Box3().setFromPoints(a.flatMap(s=>[uePoint(s.bounds_cm.min,originCm),uePoint(s.bounds_cm.max,originCm)]));},
    getMetrics:()=>({loaded:tiles.size,total:dataset.shared.overview.length,failed:errors.size,markers:rows.length}),
    async dispose(){generation++;group.removeFromParent();markers.removeFromParent();buildMarker.removeFromParent();await loading;
      for(const owner of owners)resources.release(owner);owners.clear();tiles.clear();
      for(const object of [markers,buildMarker]){object.geometry.dispose();object.material.map.dispose();object.material.dispose();}},
  };
}
