// All planner inputs are absolute UE centimeters; rendering origins never enter here.
export const STREAM_POLICY = Object.freeze({radiusCm:26000, retainCm:40000, maxSections:4,
  debounceMs:300, quantumCm:10000, maxAssetJobs:8, manifestLimit:12, estimatedBytes:2560*1024*1024});

export function intersectsXY(a, b) {
  return a.min[0]<=b.max[0] && a.max[0]>=b.min[0] && a.min[1]<=b.max[1] && a.max[1]>=b.min[1];
}
export function distanceToSection(point, row) {
  return Math.hypot(...[0,1].map(i=>Math.max(row.bounds_cm.min[i]-point[i],0,point[i]-row.bounds_cm.max[i])));
}
export function sectionFocus(row, overview=[]) {
  const b=row.content_bounds_cm || row.bounds_cm;
  const center=b.min.map((v,i)=>(v+b.max[i])/2);
  for(let i=0;i<2;i++)center[i]=Math.max(row.bounds_cm.min[i],Math.min(row.bounds_cm.max[i],center[i]));
  const tiles=overview.filter(t=>intersectsXY(row.bounds_cm,{min:t.bounds[0],max:t.bounds[1]}))
    .filter(t=>row.biome==="Caves" || row.biome==="Sand Vaults" || !/Cave|Sand_Vault/i.test(t.material));
  if(row.terrain && tiles.length) {
    const cell=row.bounds_cm.min.map((v,i)=>(v+row.bounds_cm.max[i])/2);
    const point=t=>[0,1].map(i=>(Math.max(t.bounds[0][i],row.bounds_cm.min[i])+Math.min(t.bounds[1][i],row.bounds_cm.max[i]))/2);
    const name=row.biome.replace(/\W/g,"").toLowerCase(),match=t=>t.material.replace(/\W/g,"").toLowerCase().includes(name);
    tiles.sort((a,b)=>Number(match(b))-Number(match(a)) || Math.hypot(...point(a).map((v,i)=>v-cell[i]))-Math.hypot(...point(b).map((v,i)=>v-cell[i])));
    const tile=tiles[0];center.splice(0,2,...point(tile));center[2]=tile.height_max_cm;
  }
  return center;
}
export function planSections({sections,focus,area="all",resident=[],destination=null,policy=STREAM_POLICY}) {
  const allowed=sections.filter(s=>area==="all" || s.biome===area);
  const scored=allowed.map(row=>({row,distance:distanceToSection(focus,row)}))
    .sort((a,b)=>Number(b.row.id===destination)-Number(a.row.id===destination) || a.distance-b.distance || a.row.id.localeCompare(b.row.id));
  const nearby=scored.filter(s=>s.distance<=policy.radiusCm || s.row.id===destination);
  const desired=nearby.slice(0,policy.maxSections).map(s=>s.row.id);
  // Retain warm neighbors only in unused slots; new near sections have priority.
  for(const s of scored)if(desired.length<policy.maxSections && resident.includes(s.row.id) && s.distance<=policy.retainCm && !desired.includes(s.row.id))desired.push(s.row.id);
  return {desired,deferred:nearby.filter(s=>!desired.includes(s.row.id)).map(s=>s.row.id),
    evict:resident.filter(id=>!desired.includes(id))};
}
export function detailViewSpan(camera, distance) {
  return camera.isOrthographicCamera ? (camera.top-camera.bottom)/camera.zoom :
    2*distance*Math.tan((camera.fov || 50)*Math.PI/360)/camera.zoom;
}
export function createJobPool(limit=8) {
  let running=0,serial=0; const queue=[];
  function drain() {
    queue.sort((a,b)=>b.priority-a.priority || a.serial-b.serial);
    while(running<limit && queue.length) {
      const job=queue.shift();running++;
      Promise.resolve().then(job.run).then(job.resolve,job.reject).finally(()=>{running--;drain();});
    }
  }
  return {run(run,priority=0){return new Promise((resolve,reject)=>{queue.push({run,priority,serial:serial++,resolve,reject});drain();});},
    stats:()=>({running,queued:queue.length})};
}

// Dependencies may have their own leases. Destruction waits for noncancelable decodes.
export function createLeaseCache() {
  const entries=new Map();let destroyed=0;
  function releaseEntry(entry) {
    if(entry.owners.size || entry.released || !entry.settled)return;
    entry.released=true;if(entries.get(entry.key)===entry)entries.delete(entry.key);
    if(entry.value!==undefined){entry.dispose(entry.value);destroyed++;}
  }
  return {
    acquire(key,owner,load,dispose) {
      let entry=entries.get(key);
      if(!entry) {
        entry={key,owners:new Set(),dispose,released:false,settled:false}; entries.set(key,entry);
        entry.promise=Promise.resolve().then(load).then(value=>{entry.value=value;return value;})
          .catch(error=>{if(entries.get(key)===entry)entries.delete(key);throw error;})
          .finally(()=>{entry.settled=true;releaseEntry(entry);});
      }
      entry.owners.add(owner);return entry.promise;
    },
    release(owner) {for(const entry of [...entries.values()]){entry.owners.delete(owner);releaseEntry(entry);}},
    values:()=>[...entries.values()].map(e=>e.value).filter(v=>v!==undefined),
    stats:()=>({entries:entries.size,pending:[...entries.values()].filter(e=>!e.settled).length,destroyed}),
  };
}
