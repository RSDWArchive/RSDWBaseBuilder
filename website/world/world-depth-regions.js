import * as THREE from "three";

// Bounds prove absence only. Unknown deformation or a near-plane crossing keeps
// the original draw, including alpha cutouts and anti-aliased boundary pixels.
export function createDepthRegions(camera,width,height) {
  const view=new THREE.Matrix4(),point=new THREE.Vector3(),projected=new THREE.Vector3();
  const cache=new WeakMap();
  const safe=m=>!m.isShaderMaterial&&!m.isRawShaderMaterial&&!m.displacementMap&&
    (m.onBeforeCompile===THREE.Material.prototype.onBeforeCompile||m.userData.depthGeometryUnchanged===true);
  function bounds(object) {
    if(!object.isMesh||object.isSkinnedMesh||object.onBeforeRender!==THREE.Object3D.prototype.onBeforeRender||object.morphTargetInfluences?.some(Boolean)||![object.material].flat().every(safe))return null;
    if(object.isInstancedMesh){if(!object.boundingBox)object.computeBoundingBox();}
    else if(!object.geometry.boundingBox)object.geometry.computeBoundingBox();
    const box=object.isInstancedMesh?object.boundingBox:object.geometry.boundingBox;
    if(!box||box.isEmpty())return null;
    const cached=cache.get(box);if(cached?.matrix.equals(object.matrixWorld))return cached.bounds;
    view.multiplyMatrices(camera.matrixWorldInverse,object.matrixWorld);
    const result={left:Infinity,right:-Infinity,bottom:Infinity,top:-Infinity,near:Infinity,far:-Infinity};
    for(let i=0;i<8;i++){
      point.set(i&1?box.max.x:box.min.x,i&2?box.max.y:box.min.y,i&4?box.max.z:box.min.z).applyMatrix4(view);
      const depth=-point.z;if(!Number.isFinite(depth)||depth<=camera.near)return null;
      result.near=Math.min(result.near,depth);result.far=Math.max(result.far,depth);
      projected.copy(point).applyMatrix4(camera.projectionMatrix);
      result.left=Math.min(result.left,projected.x);result.right=Math.max(result.right,projected.x);
      result.bottom=Math.min(result.bottom,projected.y);result.top=Math.max(result.top,projected.y);
    }
    // Four drawing-buffer pixels on each side cover sample/filter edge differences.
    result.left-=8/width;result.right+=8/width;result.bottom-=8/height;result.top+=8/height;
    cache.set(box,{matrix:object.matrixWorld.clone(),bounds:result});
    return result;
  }
  const receivers=[];
  return {
    add(object){
      const box=bounds(object);
      const gaps=[object.material].flat().filter(m=>m.userData.sceneDepthEffect).map(m=>m.userData.depthMaxGap??Infinity);
      receivers.push(box?{...box,far:box.far+Math.max(...gaps)}:null);
    },
    affects(object){
      if(receivers.some(r=>!r))return true;
      const box=bounds(object);if(!box)return true;
      return receivers.some(r=>box.left<=r.right&&box.right>=r.left&&box.bottom<=r.top&&box.top>=r.bottom&&box.near<=r.far+0.01);
    },
  };
}
