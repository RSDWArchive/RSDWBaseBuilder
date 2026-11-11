import * as THREE from "three";
import { ueMatrix } from "./world-transforms.js";
import { applyWaterMaterial } from "./world-water.js";
import { applyWaterDepth } from "./world-depth.js";
import { applyFoamMaterial } from "./world-foam.js";
import { applySurfaceSettings } from "./world-surface.js";
import { createWorkBudget } from "./world-work-budget.js";

// Both hosts use the same source-backed material and instanced mesh adapters.
export function createWorldAssetRenderer({getData, modelRoot, regionRoot, loadModel, loadTexture,
  materialCache, mirrorCache, sceneDepth, layers, onAssetAdded=()=>{},checkpoint=createWorkBudget(),active=()=>{}}) {
async function mappedMaterial(original,asset,slot,geometry) {
  const data=getData();
  const ref=asset.materials[slot] || asset.default_materials[slot];
  const descriptor=data.materials[ref];
  const settings=descriptor?.settings || {};
  const sourceControlled=!!settings.surface_color || settings.emissive_enabled!==undefined || ["foliage","surface_maps","rock","water","foam"].includes(settings.family) || Object.keys(descriptor?.linear_color_sources || {}).length>0 || /Additive|Modulate|AlphaComposite/.test(descriptor?.properties?.BlendMode || "");
  if(!asset.native && !sourceControlled && !descriptor?.projection && (!asset.materials[slot] || asset.materials[slot]===asset.default_materials[slot])) return original;
  const vertexAO=settings.vertex_color_mode==="ao_red" && !!geometry.getAttribute("color");
  const key=(original?.uuid||"native")+ref+vertexAO;
  if(!materialCache.has(key)) materialCache.set(key,(async()=>{
    const m=original?.clone() || new THREE.MeshStandardMaterial({roughness:0.9});
    try {
    const p=data.materials[ref];
    if(!p) return m;
    m.name=p.name;
    if(asset.native || (asset.materials[slot] && asset.materials[slot]!==asset.default_materials[slot])) {
      for(const key of ["map","normalMap","roughnessMap","metalnessMap","aoMap","emissiveMap","alphaMap"]) m[key]=null;
      m.color.set(0xffffff);m.emissive.set(0x000000);m.metalness=0;m.roughness=0.9;m.alphaTest=0;
      m.transparent=false;m.opacity=1;
    }
    if(p.textures.base_color) {m.map=await loadTexture(p.textures.base_color,true);m.color.set(0xffffff);}
    if(p.textures.normal) {m.normalMap=await loadTexture(p.textures.normal);m.normalScale.set(1,-1);}
    if(p.properties.TwoSided!==undefined) m.side=p.properties.TwoSided?THREE.DoubleSide:THREE.FrontSide;
    if(p.properties.BlendMode!==undefined) {
      const blend=String(p.properties.BlendMode);
      m.alphaTest=blend.includes("Masked")?(p.properties.OpacityMaskClipValue??0.333):0;
      m.transparent=/Translucent|Additive|AlphaComposite|Modulate/.test(blend);
      m.depthWrite=!m.transparent;
      m.blending=blend.includes("Additive")?THREE.AdditiveBlending:blend.includes("Modulate")?THREE.MultiplyBlending:THREE.NormalBlending;
      if(!m.transparent)m.opacity=1;
    }
    if(settings.alpha_test_enabled===false) {m.alphaTest=0;m.alphaMap=null;}
    if(settings.emissive_enabled===false) {
      m.emissive.set(0x000000);m.emissiveMap=null;m.emissiveIntensity=0;
    } else if(settings.emissive_enabled===true && p.textures.emissive) {
      m.emissiveMap=await loadTexture(p.textures.emissive,true);
      const tint=p.vectors.EmissiveColor;
      m.emissive.setRGB(tint?.R??1,tint?.G??1,tint?.B??1);
      m.emissiveIntensity=Math.max(0,p.scalars["Emissive Scale"]??p.scalars["Emissive Add"]??1);
    }
    if(["geyser_stones","surface_maps"].includes(settings.family)) m.vertexColors=false;
    if(settings.family==="foliage") {
      // Unreal's vertex channels drive wind, AO and layer masks, not RGB tint/opacity.
      m.vertexColors=false;
      if(!m.roughnessMap) m.roughness=Math.min(1,Math.max(0,p.scalars.Roughness??0.8));
      if(vertexAO) {
        m.userData.depthGeometryUnchanged=true;
        m.userData.depthAlphaUnchanged=true;
        m.onBeforeCompile=shader=>{
          shader.vertexShader="attribute vec4 color;\nvarying float sourceVertexAO;\n"+shader.vertexShader;
          shader.vertexShader=shader.vertexShader.replace("#include <begin_vertex>","#include <begin_vertex>\nsourceVertexAO=clamp(color.r,0.0,1.0);");
          shader.fragmentShader="varying float sourceVertexAO;\n"+shader.fragmentShader;
          shader.fragmentShader=shader.fragmentShader.replace("#include <aomap_fragment>","#include <aomap_fragment>\nreflectedLight.indirectDiffuse*=sourceVertexAO;");
        };
        m.customProgramCacheKey=()=>"world-foliage-ao-v1";
      }
    }
    m.userData.sourceMaterial=ref;
    m.userData.sourceSettings=settings;
    const base=p.vectors[settings.base_color_parameter] || p.vectors.BaseColour || p.vectors.BaseColor;
    if(settings.family==="rock" && base)m.color.setRGB(base.R,base.G,base.B);
    if(base && settings.base_color_parameter && !p.textures.base_color) m.map=null;
    if(base && !p.textures.base_color) m.color.setRGB(base.R,base.G,base.B);
    applySurfaceSettings(m,settings);
    if(settings.family==="water") {
      await applyWaterMaterial(m,p,loadTexture,data.region.origin_cm);
      applyWaterDepth(m,settings.water,sceneDepth);
    }
    if(settings.family==="foam") await applyFoamMaterial(m,p,loadTexture,sceneDepth);
    if(p.projection==="landscape_color") {
      m.map=await loadTexture(p.textures.landscape_color,true);
      m.map.wrapS=m.map.wrapT=THREE.ClampToEdgeWrapping;
      m.color.set(0xffffff);
      m.userData.landscapeCoverage={value:false};
    }
    if(p.projection && m.map) {
      m.userData.depthGeometryUnchanged=true;
      m.normalMap=null;m.roughness=0.95;m.metalness=0;
      const tint=p.vectors["Rock BC Tint"] || p.vectors["Rock Base"];
      if(tint && p.projection==="triplanar") m.color.setRGB(tint.R,tint.G,tint.B);
      m.onBeforeCompile=shader=>{
        shader.uniforms.worldTileSize={value:p.tile_meters};
        shader.vertexShader="varying vec3 worldSurface;\n"+shader.vertexShader;
        shader.vertexShader=shader.vertexShader.replace("#include <worldpos_vertex>",`#include <worldpos_vertex>
          vec4 surfacePosition=vec4(transformed,1.0);
          #ifdef USE_INSTANCING
            surfacePosition=instanceMatrix*surfacePosition;
          #endif
          worldSurface=(modelMatrix*surfacePosition).xyz;`);
        if(p.projection==="landscape_color") {
          const [lo,hi]=p.landscape_bounds_cm,origin=data.region.origin_cm;
          shader.uniforms.landscapeBounds={value:new THREE.Vector4((lo[0]-origin[0])/100,(lo[1]-origin[1])/100,(hi[0]-lo[0])/100,(hi[1]-lo[1])/100)};
          const fallback=p.vectors.SandColourA || p.vectors.BaseColour || {R:.35,G:.35,B:.35};
          shader.uniforms.landscapeFallback={value:new THREE.Color().setRGB(fallback.R,fallback.G,fallback.B)};
          shader.uniforms.landscapeCoverageOnly=m.userData.landscapeCoverage;
          shader.fragmentShader="varying vec3 worldSurface;\nuniform vec4 landscapeBounds;\nuniform vec3 landscapeFallback;\nuniform bool landscapeCoverageOnly;\n"+shader.fragmentShader;
          shader.fragmentShader=shader.fragmentShader.replace("#include <map_fragment>",`
            vec2 terrainUV=(worldSurface.xz-landscapeBounds.xy)/landscapeBounds.zw;
            vec4 terrainColor=texture2D(map,terrainUV);
            float inTerrain=step(0.0,terrainUV.x)*step(0.0,terrainUV.y)*step(terrainUV.x,1.0)*step(terrainUV.y,1.0);
            float landscapeCoverage=terrainColor.a*inTerrain;
            diffuseColor.rgb*=mix(landscapeFallback,terrainColor.rgb,landscapeCoverage);`);
          shader.fragmentShader=shader.fragmentShader.replace("#include <dithering_fragment>",
            "#include <dithering_fragment>\nif(landscapeCoverageOnly) gl_FragColor=vec4(vec3(landscapeCoverage),diffuseColor.a);");
        } else {
          shader.uniforms.worldProjectionOrigin={value:new THREE.Vector3(data.region.origin_cm[0]/100,data.region.origin_cm[2]/100,data.region.origin_cm[1]/100)};
          shader.fragmentShader="varying vec3 worldSurface;\nuniform float worldTileSize;\nuniform vec3 worldProjectionOrigin;\n"+shader.fragmentShader;
          shader.fragmentShader=shader.fragmentShader.replace("#include <map_fragment>",`
          vec3 surfaceNormal=normalize(cross(dFdx(worldSurface),dFdy(worldSurface)));
          vec3 weights=pow(abs(surfaceNormal),vec3(4.0));weights/=max(dot(weights,vec3(1.0)),0.00001);
          vec3 uvWorld=(worldSurface+worldProjectionOrigin)/worldTileSize;
          vec4 triColor=texture2D(map,uvWorld.yz)*weights.x+texture2D(map,uvWorld.xz)*weights.y+texture2D(map,uvWorld.xy)*weights.z;
          diffuseColor*=triColor;`);
        }
      };
      m.customProgramCacheKey=()=>"world-projection-v2-"+p.projection;
    }
    m.needsUpdate=true;
    return m;
    } catch(error) { m.dispose(); throw error; }
  })());
  return materialCache.get(key);
}
function mirroredGeometry(source) {
  if(mirrorCache.has(source.uuid)) return mirrorCache.get(source.uuid);
  const g=source.clone();g.scale(-1,1,1);
  if(!g.index) g.setIndex(Array.from({length:g.attributes.position.count},(_,i)=>i));
  const idx=g.index.array;
  for(let i=0;i<idx.length;i+=3) [idx[i+1],idx[i+2]]=[idx[i+2],idx[i+1]];
  g.index.needsUpdate=true;
  mirrorCache.set(source.uuid,g);
  return g;
}
async function addAsset(asset,placements) {
  const data=getData();
  const root=asset.root==="models"?modelRoot:regionRoot;
  const gltf=await loadModel(new URL(asset.path,root));
  gltf.scene.updateMatrixWorld(true);
  const meshes=[];
  gltf.scene.traverse(o=>{if(o.isMesh) meshes.push(o);});
  let section=0;
  for(const mesh of meshes) {
    if(mesh.isSkinnedMesh) throw new Error("Unexpected animated world mesh: "+asset.source);
    const slot=asset.section_material_slots?.[section] ?? section;
    section++;
    const material=await mappedMaterial(mesh.material,asset,slot,mesh.geometry);
    const batches=new Map();
    for(const p of placements) {
      const pause=checkpoint();if(pause){await pause;active();}
      const m=ueMatrix(p.matrix,data.region.origin_cm).multiply(mesh.matrixWorld);
      const negative=m.determinant()<0;
      const key=[Math.floor(m.elements[12]/64),Math.floor(m.elements[14]/64),negative].join(":");
      if(negative) m.multiply(new THREE.Matrix4().makeScale(-1,1,1));
      if(!batches.has(key)) batches.set(key,{negative,matrices:[],ids:[]});
      batches.get(key).matrices.push(m);batches.get(key).ids.push(p.id);
    }
    for(const batch of batches.values()) {
      const geometry=batch.negative?mirroredGeometry(mesh.geometry):mesh.geometry;
      const instance=new THREE.InstancedMesh(geometry,material,batch.matrices.length);
      instance.userData.source=asset.source;
      instance.userData.asset=asset.id;
      instance.userData.materialSlot=slot;
      instance.userData.sourceMesh=mesh.uuid;
      instance.userData.placementIds=batch.ids;
      for(let i=0;i<batch.matrices.length;i++){
        instance.setMatrixAt(i,batch.matrices[i]);
        const pause=checkpoint();if(pause){await pause;active();}
      }
      instance.instanceMatrix.needsUpdate=true;
      instance.computeBoundingBox();instance.computeBoundingSphere();
      layers[asset.layer].add(instance);
      const pause=checkpoint();if(pause){await pause;active();}
    }
  }
  onAssetAdded();
  await new Promise(resolve=>requestAnimationFrame(resolve));
}

return {addAsset};
}
