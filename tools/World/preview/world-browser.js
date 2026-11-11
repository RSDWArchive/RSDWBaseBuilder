import { createSectionMarkers } from "./world-section-markers.js";

const overlaps=(a,b)=>a.min[0]<=b.max[0] && a.max[0]>=b.min[0] && a.min[1]<=b.max[1] && a.max[1]>=b.min[1];
const boundsOf=rows=>({min:[0,1,2].map(i=>Math.min(...rows.map(r=>r.bounds_cm.min[i]))),max:[0,1,2].map(i=>Math.max(...rows.map(r=>r.bounds_cm.max[i])))});

export async function openWorldBrowser({root,data,controls,camera,scene,canvas,invalidate,initialSection,replaceOverview,replaceDetail,frame,status}) {
  const read=async path=>{const r=await fetch(new URL(path,root));if(!r.ok)throw new Error(`${path}: HTTP ${r.status}`);return r.json();};
  const index=await read("WorldIndex.json");
  if(index.schema!=="RSDW.WorldIndex.v1" || index.version!==data.version) throw new Error("World index/version mismatch");
  const spanning=await read(index.spanning);
  const assetLayers=new Map(data.assets.map(a=>[a.id,a.layer]));
  const container=document.querySelector("#world-browser"),biome=document.querySelector("#world-biome"),section=document.querySelector("#world-section");
  container.hidden=false;
  for(const name of [...new Set(index.sections.map(s=>s.biome))].sort())biome.add(new Option(name,name));
  let allowed=index.sections,requested=null,busy=false,applying=false,lastKey="",activeKey="",planningKey="",timer=0,revision=0,serial=0;
  let areaBounds=index.bounds_cm,coverage={},pinnedSection=null;
  const markers=createSectionMarkers({scene,camera,canvas,origin:data.region.origin_cm,invalidate,
    open:id=>load(id).catch(e=>status(String(e),true))});
  const cache=new Map();
  async function readSection(row) {
    if(!cache.has(row.id))cache.set(row.id,read(row.path).catch(error=>{cache.delete(row.id);throw error;}));
    const result=await cache.get(row.id);
    // Keep a small CPU-side window; GLTF/GPU resources have their own lifecycle.
    if(cache.size>12)cache.delete(cache.keys().next().value);
    return result;
  }
  function populate() {
    section.replaceChildren(new Option("All sections","all"));
    for(const row of index.sections.filter(s=>biome.value==="all" || s.biome===biome.value))section.add(new Option(row.name,row.id));
  }
  biome.addEventListener("change",populate);
  populate();
  if(initialSection) {
    if(!index.sections.some(s=>s.id===initialSection))throw new Error("Unknown requested world section");
    section.value=initialSection;
  }
  async function drain() {
    if(busy)return;
    busy=true;
    try {
      while(requested) {
        const request=requested;requested=null;activeKey=request.key;
        await replaceDetail(request);
        lastKey=request.key;coverage=request.coverage;
      }
    } catch(error) {lastKey="";coverage={...coverage,failed:1};throw error;}
    finally {busy=false;activeKey="";}
  }
  async function stream(force=false) {
    if(applying && !force)return;
    const distance=camera.position.distanceTo(controls.target);
    if(pinnedSection && distance>=1500)pinnedSection=null;
    if(pinnedSection && !overlaps(pinnedSection.bounds_cm,{min:[controls.target.x*100,controls.target.z*100],max:[controls.target.x*100,controls.target.z*100]}))pinnedSection=null;
    const isolated=allowed.length===1 || !!pinnedSection;
    const focused=pinnedSection || allowed[0];
    const center=isolated?[0,1].map(i=>(focused.bounds_cm.min[i]+focused.bounds_cm.max[i])/2):
      [Math.round(controls.target.x/200)*20000,Math.round(controls.target.z/200)*20000];
    const detailed=isolated || distance<1500;
    markers.setVisible(!detailed && allowed.length>1);
    const key=[revision,detailed, ...center].join(":");
    if(!force && (key===lastKey || key===requested?.key || key===activeKey || key===planningKey))return;
    planningKey=key;const currentSerial=++serial;
    const myRevision=revision;
    const bounds=isolated?focused.bounds_cm:
      {min:[center[0]-26000,center[1]-26000,-1e9],max:[center[0]+26000,center[1]+26000,1e9]};
    const rows=isolated?[focused]:detailed?allowed.filter(r=>overlaps(r.bounds_cm,bounds)):[];
    const sections=await Promise.all(rows.map(readSection)).catch(error=>{planningKey="";throw error;});
    if(myRevision!==revision || currentSerial!==serial)return;
    planningKey="";
    const placements=new Map(),terrain=new Map();
    for(const part of sections) {
      for(const p of part.placements)if(overlaps({min:p.bounds[0],max:p.bounds[1]},bounds))placements.set(p.id,p);
      for(const t of part.terrain)if(overlaps({min:t.bounds[0],max:t.bounds[1]},bounds))terrain.set(t.source,t);
    }
    if(detailed)for(const p of spanning)if(overlaps({min:p.bounds[0],max:p.bounds[1]},bounds))placements.set(p.id,p);
    const hidden=[...placements.values()].filter(p=>assetLayers.get(p.asset)==="helpers").length;
    const deferred=allowed.length-rows.length;
    requested={key,placements:[...placements.values()],terrain:[...terrain.values()],sectionIds:rows.map(r=>r.id),
      coverage:{loaded:placements.size,helper_placements:hidden,loaded_sections:rows.length,deferred_sections:deferred,failed:0},
      label:detailed?`${placements.size.toLocaleString()} loaded${isolated?" | "+focused.id:""} | ${hidden} blockouts | ${deferred} sections deferred`:
        `Overview | ${allowed.length} sections deferred | ${markers.count()} section markers`};
    await drain();
  }
  async function apply() {
    if(applying)return;
    applying=true;document.querySelector("#world-load").disabled=true;
    try {
    revision++;lastKey="";
    requested=null;clearTimeout(timer);
    while(busy)await new Promise(resolve=>setTimeout(resolve,100));
    allowed=index.sections.filter(s=>(biome.value==="all" || s.biome===biome.value) && (section.value==="all" || s.id===section.value));
    if(!allowed.length)return;
    const bounds=biome.value==="all" && section.value==="all"?index.bounds_cm:boundsOf(allowed);
    areaBounds=bounds;pinnedSection=null;markers.setSections(allowed);
    document.querySelector("#region-name").textContent=section.value!=="all"?section.selectedOptions[0].textContent:biome.selectedOptions[0].textContent;
    const overview=data.overview.filter(t=>allowed.some(r=>overlaps(r.bounds_cm,{min:t.bounds[0],max:t.bounds[1]})));
    let frameBounds=bounds;
    const noLandscape=allowed.every(row=>row.terrain===0);
    const entry=noLandscape?[...allowed].sort((a,b)=>(b.visible_placements??b.placements)-(a.visible_placements??a.placements))[0]:allowed[0];
    if((allowed.length===1 && !overview.length) || noLandscape) {
      const part=await readSection(entry);
      const content=part.placements.filter(p=>assetLayers.get(p.asset)!=="helpers");
      if(content.length) {
        frameBounds={min:[Infinity,Infinity,Infinity],max:[-Infinity,-Infinity,-Infinity]};
        for(const p of content)for(let i=0;i<3;i++) {
          frameBounds.min[i]=Math.min(frameBounds.min[i],p.bounds[0][i]);
          frameBounds.max[i]=Math.max(frameBounds.max[i],p.bounds[1][i]);
        }
        if(allowed.length>1)pinnedSection=entry;
      }
    }
    data.region.bounds_cm=frameBounds;
    data.region.focus_cm=frameBounds.min.map((v,i)=>(v+frameBounds.max[i])/2);
    // Underworld blockers can extend far below the traversable landscape. Frame
    // landscape height instead of putting the camera inside those volumes.
    const surface=overview.filter(t=>!/Cave|Sand_Vault/i.test(t.material));
    const elevations=(surface.length?surface:overview).map(t=>(t.height_min_cm+t.height_max_cm)/2).sort((a,b)=>a-b);
    if(elevations.length && !noLandscape)data.region.focus_cm[2]=elevations[Math.floor(elevations.length/2)];
    status(`Loading ${overview.length} terrain tiles`);
    await replaceOverview(overview);
    frame();
    await stream(true);
    } finally {applying=false;document.querySelector("#world-load").disabled=false;}
  }
  document.querySelector("#world-load").addEventListener("click",()=>apply().catch(e=>status(String(e),true)));
  async function overview() {
    if(applying || busy)return;
    pinnedSection=null;data.region.bounds_cm=areaBounds;
    data.region.focus_cm=areaBounds.min.map((v,i)=>(v+areaBounds.max[i])/2);
    frame();await stream(true);
  }
  document.querySelector("#world-overview").addEventListener("click",()=>overview().catch(e=>status(String(e),true)));
  controls.addEventListener("change",()=>{clearTimeout(timer);timer=setTimeout(()=>stream().catch(e=>status(String(e),true)),900);});
  await apply();
  async function load(id) {
    biome.value="all";populate();section.value=id;await apply();
  }
  return {index,load,overview,stream,metrics:()=>({sections:allowed.length,busy,cache_sections:cache.size,
    detail_key:lastKey,markers:markers.count(),coverage})};
}
