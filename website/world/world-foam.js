import * as THREE from "three";
import { applyDepthEffect } from "./world-depth.js";

// Static source subset. No synthetic shoreline foam is added to unrelated water.
export async function applyFoamMaterial(material,descriptor,loadTexture,depth) {
  const foam=descriptor.settings.foam;
  for(const field of ["map","alphaMap","normalMap","roughnessMap","metalnessMap","aoMap","emissiveMap"]) material[field]=null;
  material.color.fromArray(foam.color);material.opacity=foam.opacity;
  material.emissive?.set(0);material.emissiveIntensity=0;material.vertexColors=false;
  material.roughness=1;material.metalness=0;material.alphaTest=0;
  material.transparent=true;material.depthWrite=false;
  const mask=await loadTexture(descriptor.textures.foam_mask);
  material.userData.foamMask=mask;material.userData.foamSettings=foam;
  material.onBeforeCompile=shader=>{
    shader.uniforms.foamMask={value:mask};
    shader.uniforms.foamUVScale={value:new THREE.Vector2(...foam.uv_scale)};
    shader.uniforms.foamMaskMult={value:new THREE.Vector4(...foam.mask_mult)};
    shader.uniforms.foamMaskSub={value:new THREE.Vector4(...foam.mask_sub)};
    shader.uniforms.foamMaskGainBias={value:new THREE.Vector2(foam.mask_gain,foam.mask_bias)};
    shader.vertexShader="varying vec2 foamUV;\n"+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace("#include <begin_vertex>","#include <begin_vertex>\nfoamUV=uv;");
    shader.fragmentShader=`varying vec2 foamUV;
      uniform sampler2D foamMask;
      uniform vec2 foamUVScale,foamMaskGainBias;
      uniform vec4 foamMaskMult,foamMaskSub;\n`+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace("#include <map_fragment>",`
      vec4 foamSample=texture2D(foamMask,foamUV*foamUVScale);
      float foamOpacity=${foam.rgb_mask?"dot(max(foamSample-foamMaskSub,vec4(0.0)),foamMaskMult)":"foamSample.a"};
      diffuseColor.a*=clamp((foamOpacity-foamMaskGainBias.y)*foamMaskGainBias.x,0.0,1.0);`);
  };
  material.customProgramCacheKey=()=>"world-foam-static-v1-"+foam.rgb_mask;
  material.userData.depthGeometryUnchanged=true;
  if(foam.depth_fade_m>0)applyDepthEffect(material,depth,
    `diffuseColor.a*=clamp(depthGap/${foam.depth_fade_m.toFixed(8)},0.0,1.0);`,"foam-"+foam.depth_fade_m,foam.depth_fade_m);
}
