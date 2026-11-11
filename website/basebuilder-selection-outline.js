import * as THREE from "three";

// Same twelve AABB edges/color/opacity as Box3Helper, submitted as one line draw.
export function createSelectionOutline(scene) {
  const material=new THREE.LineBasicMaterial({color:0xf3cf89,depthTest:false,transparent:true,opacity:.96});
  const object=new THREE.LineSegments(new THREE.BufferGeometry(),material);object.frustumCulled=false;
  object.name="Selection Boxes";object.renderOrder=999;object.visible=false;scene.add(object);
  let capacity=0;
  const edges=[[0,1],[0,2],[0,4],[1,3],[1,5],[2,3],[2,6],[3,7],[4,5],[4,6],[5,7],[6,7]];
  function update(placements,bounds,pickable) {
    object.position.set(0,0,0);
    if(capacity<placements.length){capacity=Math.max(placements.length,capacity*2);
      object.geometry.dispose();object.geometry=new THREE.BufferGeometry();
      object.geometry.setAttribute("position",new THREE.BufferAttribute(new Float32Array(capacity*72),3).setUsage(THREE.DynamicDrawUsage));}
    const attribute=object.geometry.getAttribute("position");let offset=0;
    for(const p of placements){if(!pickable(p))continue;const box=bounds(p);if(box.isEmpty())continue;
      for(const edge of edges)for(const vertex of edge){
        attribute.array[offset++]=vertex&1?box.max.x:box.min.x;
        attribute.array[offset++]=vertex&2?box.max.y:box.min.y;
        attribute.array[offset++]=vertex&4?box.max.z:box.min.z;
      }
    }
    if(attribute){attribute.clearUpdateRanges();if(offset)attribute.addUpdateRange(0,offset);attribute.needsUpdate=true;}
    object.geometry.setDrawRange(0,offset/3);object.visible=offset>0;
  }
  return {object,update,translate(delta){object.position.add(delta);},dispose(){object.removeFromParent();object.geometry.dispose();material.dispose();}};
}
