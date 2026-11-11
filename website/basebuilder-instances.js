import * as THREE from "three";

// Slots are disposable render addresses. Placement IDs and transforms stay in the editor.
export function createInstanceStore({root,templateForTarget,matrixForPlacement,isVisible,prepareMesh=()=>{},cellCm=6400,legacy=false}) {
  const batches=new Map(),entries=new Map(),dirty=new Set(),reserved=new Map(),renders=new Map();
  const frustum=new THREE.Frustum(),projection=new THREE.Matrix4();
  const hidden=new THREE.Matrix4().makeScale(0,0,0),matrix=new THREE.Matrix4(),rootMatrix=new THREE.Matrix4();
  let meshCount=0,uploads=0,revision=0;
  function keyFor(p) {
    const t=templateForTarget(p.target);
    if(!t?.eligible)return null;
    const spatial=!legacy&&!t.descriptors.some(d=>[d.material].flat().some(m=>m.transparent));
    const cx=Math.floor(p.state.x/cellCm),cy=Math.floor(p.state.y/cellCm);
    return {template:t,spatial,cx,cy,key:spatial?`${t.key}@${cx},${cy}`:t.key};
  }
  function reserve(placements) {
    for(const p of placements){const info=keyFor(p);if(info)reserved.set(info.key,(reserved.get(info.key)||0)+1);}
  }
  function grow(batch,min) {
    const capacity=Math.max(legacy?64:8,batch.capacity*2,min),previous=batch.meshes;
    batch.meshes=batch.template.descriptors.map((d,i)=>{
      const mesh=new THREE.InstancedMesh(d.geometry,d.material,capacity);
      mesh.name=`${batch.target.asset_stem||batch.target.target_id} Instances ${i+1}`;
      mesh.count=batch.rows.length;mesh.frustumCulled=batch.spatial;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);mesh.userData.instanceBatchKey=batch.key;
      if(previous[i])mesh.instanceMatrix.array.set(previous[i].instanceMatrix.array.subarray(0,batch.rows.length*16));
      if(legacy)root.add(mesh);prepareMesh(mesh);return mesh;
    });
    for(const mesh of previous){mesh.removeFromParent();mesh.dispose();}
    meshCount+=batch.meshes.length-previous.length;batch.capacity=capacity;
    batch.first=0;batch.last=batch.rows.length-1;dirty.add(batch);
  }
  function ensure(p,info) {
    let batch=batches.get(info.key);
    if(!batch){batch={...info,target:p.target,rows:[],meshes:[],capacity:0,first:Infinity,last:-1,version:0};batches.set(info.key,batch);grow(batch,reserved.get(info.key)||0);}
    if(batch.rows.length===batch.capacity)grow(batch,batch.rows.length+1);
    return batch;
  }
  function touch(batch,slot){batch.first=Math.min(batch.first,slot);batch.last=Math.max(batch.last,slot);dirty.add(batch);}
  function write(entry) {
    const {placement:p,batch,slot}=entry,visible=isVisible(p);
    const rootTransform=matrixForPlacement(p,rootMatrix),transform=visible?rootTransform:hidden;
    (p.visual.rootMatrix ||= new THREE.Matrix4()).copy(rootTransform);
    batch.template.descriptors.forEach((d,i)=>batch.meshes[i].setMatrixAt(slot,matrix.copy(transform).multiply(d.localMatrix)));
    (p.visual.worldBounds ||= new THREE.Box3()).copy(batch.template.bounds).applyMatrix4(rootTransform);
    p.visual.worldBoundsDirty=false;p.visual.screenBoundsRevision=-1;
    if(visible)entry.bounds.copy(p.visual.worldBounds);else entry.bounds.makeEmpty();
    touch(batch,slot);
  }
  function add(p) {
    const info=keyFor(p);if(!info)return false;
    const batch=ensure(p,info),slot=batch.rows.length;
    const entry={placement:p,batch,slot,bounds:new THREE.Box3()};batch.rows.push(entry);entries.set(p.id,entry);
    Object.assign(p.visual,{backend:"instanced",root:null,batchKey:batch.key,instanceSlot:slot,localBounds:batch.template.bounds});
    p.group=null;for(const mesh of batch.meshes)mesh.count=batch.rows.length;
    write(entry);return true;
  }
  function remove(p) {
    const entry=entries.get(p.id);if(!entry)return false;
    const {batch,slot}=entry,last=batch.rows.pop();entries.delete(p.id);
    if(last!==entry){batch.rows[slot]=last;last.slot=slot;last.placement.visual.instanceSlot=slot;write(last);}
    for(const mesh of batch.meshes)mesh.count=batch.rows.length;
    if(!batch.rows.length){for(const mesh of batch.meshes){mesh.removeFromParent();mesh.dispose();}meshCount-=batch.meshes.length;batches.delete(batch.key);dirty.delete(batch);}
    else touch(batch,slot);
    Object.assign(p.visual,{backend:"",batchKey:"",instanceSlot:-1});return true;
  }
  function update(p) {
    let entry=entries.get(p.id);if(!entry)return;
    const b=entry.batch;
    if(b.spatial&&(Math.floor(p.state.x/cellCm)!==b.cx||Math.floor(p.state.y/cellCm)!==b.cy)){remove(p);add(p);return;}
    write(entry);
  }
  function translate(p,delta) {
    const entry=entries.get(p.id);if(!entry)return false;
    const {batch,slot}=entry;
    if(batch.spatial&&(Math.floor(p.state.x/cellCm)!==batch.cx||Math.floor(p.state.y/cellCm)!==batch.cy)){update(p);return true;}
    const visual=p.visual,e=visual.rootMatrix.elements;
    e[12]+=delta.x;e[13]+=delta.y;e[14]+=delta.z;
    visual.worldBounds.translate(delta);visual.screenBoundsRevision=-1;
    if(isVisible(p)){
      entry.bounds.translate(delta);
      for(let j=0;j<batch.meshes.length;j++){
        const a=batch.meshes[j].instanceMatrix.array,i=slot*16,t=batch.template.descriptors[j].localMatrix.elements;
        // Component origins are not necessarily the actor origin.
        a[i+12]=e[0]*t[12]+e[4]*t[13]+e[8]*t[14]+e[12];
        a[i+13]=e[1]*t[12]+e[5]*t[13]+e[9]*t[14]+e[13];
        a[i+14]=e[2]*t[12]+e[6]*t[13]+e[10]*t[14]+e[14];
      }
    }
    touch(batch,slot);return true;
  }
  function flushBatch(batch) {
    if(!dirty.delete(batch))return;
    const box=new THREE.Box3();for(const row of batch.rows)box.union(row.bounds);
    for(const mesh of batch.meshes){
      mesh.boundingBox=box;mesh.boundingSphere=box.getBoundingSphere(new THREE.Sphere());
      mesh.instanceMatrix.clearUpdateRanges();
      const last=Math.min(batch.rows.length-1,batch.last);
      if(last>=batch.first)mesh.instanceMatrix.addUpdateRange(batch.first*16,(last-batch.first+1)*16);
      mesh.instanceMatrix.needsUpdate=true;uploads++;
    }
    batch.first=Infinity;batch.last=-1;
    batch.version=++revision;
  }
  function flush(camera){
    for(const batch of dirty)flushBatch(batch);
    if(legacy||!camera)return;
    camera.updateMatrixWorld();frustum.setFromProjectionMatrix(projection.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse));
    const groups=new Map();
    for(const batch of batches.values()) {
      if(batch.spatial&&!frustum.intersectsSphere(batch.meshes[0].boundingSphere))continue;
      if(!groups.has(batch.template.key))groups.set(batch.template.key,[]);groups.get(batch.template.key).push(batch);
    }
    // Cull in small cells, submit compatible visible cells together. This keeps the
    // full-build view from paying thousands of draw calls for the culling granularity.
    for(const [key,visible]of groups) {
      const signature=visible.map(b=>`${b.key}:${b.version}`).join("|"),count=visible.reduce((n,b)=>n+b.rows.length,0);
      let render=renders.get(key);
      if(!render||render.capacity<count){
        if(render)disposeRender(render);
        const capacity=Math.max(count,render?.capacity*2||0,8);
        const meshes=visible[0].template.descriptors.map(d=>{
          const m=new THREE.InstancedMesh(d.geometry,d.material,capacity);m.frustumCulled=false;
          m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);m.name="Visible authored instances";
          prepareMesh(m);root.add(m);return m;
        });render={meshes,capacity,signature:null,depth:[]};renders.set(key,render);
        meshes.forEach((m,i)=>{m.userData.depthCandidate=test=>depthCandidate(render,i,test);});
      }
      render.cells=visible;
      for(const m of render.meshes)m.visible=true;
      if(render.signature===signature)continue;
      render.signature=signature;
      const bounds=new THREE.Box3();for(const b of visible)bounds.union(b.meshes[0].boundingBox);
      render.meshes.forEach((m,i)=>{let slot=0;
        for(const b of visible){m.instanceMatrix.array.set(b.meshes[i].instanceMatrix.array.subarray(0,b.rows.length*16),slot*16);slot+=b.rows.length;}
        m.count=count;m.instanceMatrix.clearUpdateRanges();m.instanceMatrix.addUpdateRange(0,count*16);m.instanceMatrix.needsUpdate=true;uploads++;
        m.boundingBox=bounds.clone();m.boundingSphere=bounds.getBoundingSphere(new THREE.Sphere());
      });
    }
    for(const [key,r]of renders)if(!groups.has(key)){
      if(![...batches.values()].some(b=>b.template.key===key)){disposeRender(r);renders.delete(key);}
      else for(const m of r.meshes)m.visible=false;
    }
  }
  function disposeRender(render){for(const m of [...render.meshes,...render.depth.map(d=>d?.mesh).filter(Boolean)]){m.removeFromParent();m.dispose();}}
  function depthCandidate(render,index,test){
    const source=render.meshes[index],cells=render.cells.filter(b=>{
      const mesh=b.meshes[index];mesh.matrixWorld.copy(source.matrixWorld);return test(mesh);
    });
    if(cells.length===render.cells.length)return source;
    if(!cells.length)return null;
    const count=cells.reduce((n,b)=>n+b.rows.length,0),signature=cells.map(b=>`${b.key}:${b.version}`).join("|");
    let depth=render.depth[index];
    if(!depth||depth.capacity<count){
      depth?.mesh.dispose();const capacity=Math.max(count,depth?.capacity*2||0,8);
      const mesh=new THREE.InstancedMesh(source.geometry,source.material,capacity);mesh.frustumCulled=false;
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);mesh.name="Authored water depth instances";
      depth={mesh,capacity,signature:null};render.depth[index]=depth;
    }
    const mesh=depth.mesh;mesh.material=source.material;mesh.matrixWorld.copy(source.matrixWorld);
    if(depth.signature!==signature){
      let slot=0;const bounds=new THREE.Box3();
      for(const b of cells){mesh.instanceMatrix.array.set(b.meshes[index].instanceMatrix.array.subarray(0,b.rows.length*16),slot*16);slot+=b.rows.length;bounds.union(b.meshes[index].boundingBox);}
      mesh.count=count;mesh.instanceMatrix.clearUpdateRanges();mesh.instanceMatrix.addUpdateRange(0,count*16);mesh.instanceMatrix.needsUpdate=true;
      mesh.boundingBox=bounds;mesh.boundingSphere=bounds.getBoundingSphere(new THREE.Sphere());depth.signature=signature;uploads++;
    }
    return mesh;
  }
  function candidates(placements){
    const selected=new Set();for(const p of placements){const e=entries.get(p.id);if(e)selected.add(e.batch);}
    for(const batch of selected)flushBatch(batch);
    return [...selected].flatMap(b=>b.meshes);
  }
  function hitId(hit){return batches.get(hit?.object?.userData?.instanceBatchKey)?.rows[hit.instanceId]?.placement.id||"";}
  function stats(camera) {
    const result={batches:batches.size,meshes:legacy?meshCount:[...renders.values()].reduce((n,r)=>n+r.meshes.length,0),instances:entries.size,uploads,cell_cm:cellCm,legacy};
    if(camera){flush();camera.updateMatrixWorld();const f=new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse));
      result.visible_batches=0;result.submitted_instances=0;
      for(const b of batches.values()){const m=b.meshes[0];m.updateWorldMatrix(true,false);if(!m.frustumCulled||f.intersectsObject(m)){result.visible_batches++;result.submitted_instances+=b.rows.length;}}
    }return result;
  }
  function dispose(){for(const b of batches.values())for(const m of b.meshes){m.removeFromParent();m.dispose();}for(const r of renders.values())disposeRender(r);batches.clear();renders.clear();entries.clear();dirty.clear();meshCount=0;}
  return {batches,add,remove,update,translate,flush,candidates,hitId,stats,reserve,dispose};
}
