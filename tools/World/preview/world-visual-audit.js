import * as THREE from "three";
import { measurePixels, measureProjectionCoverage } from "./world-pixel-metrics.js";

export function createVisualAudit({renderer,scene,camera,controls,layers,replaceDetail,render,auditMaterials}) {
  controls.enabled=false;
  const directions=[[1,.65,1],[-1,.65,-1],[.1,1,.1]];
  const scratch=document.createElement("canvas");scratch.width=scratch.height=32;
  const context=scratch.getContext("2d",{willReadFrequently:true});
  function textureStats(texture) {
    if(!texture?.image)return null;
    try {
      context.clearRect(0,0,32,32);context.drawImage(texture.image,0,0,32,32);
      const pixels=context.getImageData(0,0,32,32).data;
      let n=0,sum=0,sq=0,white=0;
      for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>200){
        const l=(pixels[i]+pixels[i+1]+pixels[i+2])/3;n++;sum+=l;sq+=l*l;
        if(Math.min(pixels[i],pixels[i+1],pixels[i+2])>235)white++;
      }
      return {width:texture.image.width,height:texture.image.height,opaque_samples:n,
        mean:n?sum/n:0,deviation:n?Math.sqrt(Math.max(0,sq/n-(sum/n)**2)):0,white_fraction:n?white/n:0};
    } catch(error) {return {error:String(error)};}
  }
  return {async capture(variant) {
    await replaceDetail({placements:[variant.sample],terrain:[],label:variant.source});
    for(const [name,layer] of Object.entries(layers))layer.visible=name!=="bounds";
    scene.updateMatrixWorld(true);
    const box=new THREE.Box3();
    for(const layer of Object.values(layers))box.expandByObject(layer);
    if(box.isEmpty())throw new Error("No geometry for "+variant.asset);
    const center=box.getCenter(new THREE.Vector3()),radius=Math.max(.01,box.getSize(new THREE.Vector3()).length()/2);
    camera.near=Math.max(.001,radius/10000);camera.far=Math.max(100,radius*30);camera.updateProjectionMatrix();
    controls.target.copy(center);
    const materials=[],projectionUniforms=new Set(),nonProjected=[];
    scene.traverse(o=>{if(o.isMesh && o.userData.asset){const m=o.material;materials.push({slot:o.userData.materialSlot,
      map:!!m.map,texture:textureStats(m.map),color:m.color?.toArray(),roughness:m.roughness,metalness:m.metalness,
      emissive:m.emissive?.toArray(),emissive_intensity:m.emissiveIntensity,
      transparent:m.transparent,alpha_test:m.alphaTest});
      if(m.userData.landscapeCoverage)projectionUniforms.add(m.userData.landscapeCoverage);
      else nonProjected.push([o,o.visible]);}});
    const views=[],oldBackground=scene.background,clear=renderer.getClearColor(new THREE.Color()),alpha=renderer.getClearAlpha();
    try {
      // Real shader alpha provides the object mask, including cutouts and foam.
      scene.background=null;renderer.setClearColor(0x000000,0);
      for(const direction of directions) {
        camera.position.copy(center).add(new THREE.Vector3(...direction).normalize().multiplyScalar(radius/Math.sin(THREE.MathUtils.degToRad(camera.fov/2))*1.12));
        camera.lookAt(center);camera.updateMatrixWorld();render();
        const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
        const pixels=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        const view={...measurePixels(pixels),png:renderer.domElement.toDataURL("image/png")};
        if(projectionUniforms.size){
          for(const [object] of nonProjected)object.visible=false;
          for(const u of projectionUniforms)u.value=true;
          render();gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
          view.landscape_projection=measureProjectionCoverage(pixels);
          for(const u of projectionUniforms)u.value=false;
          for(const [object,visible] of nonProjected)object.visible=visible;
        }
        views.push(view);
      }
    } finally {
      for(const u of projectionUniforms)u.value=false;
      for(const [object,visible] of nonProjected)object.visible=visible;
      scene.background=oldBackground;renderer.setClearColor(clear,alpha);
    }
    if(projectionUniforms.size)render();
    return {views,materials,runtime:auditMaterials(),triangles:renderer.info.render.triangles,
      geometry_count:renderer.info.memory.geometries,texture_count:renderer.info.memory.textures};
  }};
}
