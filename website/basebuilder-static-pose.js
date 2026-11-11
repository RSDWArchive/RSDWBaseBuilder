import * as THREE from "three";

// The editor does not animate model skeletons. Cache their current, full-detail
// pose for instancing; selected objects still use the original editable model.
const poses=new WeakMap();
export function staticPoseGeometry(mesh){return poses.get(mesh);}
export function disposeClonedSkeletons(root) {
  const skeletons=new Set();root?.traverse(o=>{if(o.isSkinnedMesh)skeletons.add(o.skeleton);});
  for(const skeleton of skeletons)skeleton.dispose();
}
export function prepareEditablePoseRaycasts(source,clone) {
  const geometry=poses.get(source);
  if(geometry&&clone.isSkinnedMesh){
    const proxy=new THREE.Mesh(geometry,clone.material);
    clone.raycast=function(raycaster,hits){
      proxy.material=this.material;proxy.matrixWorld.copy(this.matrixWorld);
      const start=hits.length;proxy.raycast(raycaster,hits);
      for(let i=start;i<hits.length;i++)hits[i].object=this;
    };
  }
  for(let i=0;i<source.children.length;i++)prepareEditablePoseRaycasts(source.children[i],clone.children[i]);
}
export async function prepareStaticPoses(root) {
  root.updateMatrixWorld(true);const meshes=[];
  root.traverse(o=>{if(o.isSkinnedMesh&&!o.morphTargetInfluences?.some(Boolean))meshes.push(o);});
  for(const mesh of meshes) {
    if(poses.has(mesh))continue;
    const source=mesh.geometry,indices=source.attributes.skinIndex,weights=source.attributes.skinWeight;
    if(!indices||!weights)continue;
    mesh.skeleton.update();
    const geometry=source.clone(),position=geometry.attributes.position,normal=geometry.attributes.normal,tangent=geometry.attributes.tangent;
    const point=new THREE.Vector3(),direction=new THREE.Vector4(),skin=new THREE.Matrix4(),bone=new THREE.Matrix4();
    let start=performance.now();
    for(let i=0;i<position.count;i++) {
      // Three.js owns position skinning. Normals/tangents follow its
      // skinnormal_vertex chunk: bindInverse * weightedBones * bind, w = 0.
      mesh.getVertexPosition(i,point);position.setXYZ(i,point.x,point.y,point.z);
      skin.elements.fill(0);
      for(let j=0;j<4;j++) {
        const weight=weights.getComponent(i,j);if(!weight)continue;
        bone.fromArray(mesh.skeleton.boneMatrices,indices.getComponent(i,j)*16);
        for(let k=0;k<16;k++)skin.elements[k]+=bone.elements[k]*weight;
      }
      skin.premultiply(mesh.bindMatrixInverse).multiply(mesh.bindMatrix);
      for(const attribute of [normal,tangent].filter(Boolean)) {
        direction.set(attribute.getX(i),attribute.getY(i),attribute.getZ(i),0).applyMatrix4(skin);
        attribute.setXYZ(i,direction.x,direction.y,direction.z);
      }
      if(i%512===0&&performance.now()-start>=5){await new Promise(r=>requestAnimationFrame(r));start=performance.now();}
    }
    geometry.deleteAttribute("skinIndex");geometry.deleteAttribute("skinWeight");geometry.morphAttributes={};
    geometry.computeBoundingBox();geometry.computeBoundingSphere();poses.set(mesh,geometry);
    // SkinnedMesh.copy carries these into editable clones. Avoid rescanning all
    // skinned vertices on their first selection/render for this unchanged pose.
    mesh.boundingBox=geometry.boundingBox.clone();mesh.boundingSphere=geometry.boundingSphere.clone();
  }
}
