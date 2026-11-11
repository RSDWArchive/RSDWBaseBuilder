import * as THREE from "three";

// Static inspection adapter, not Unreal's depth-dependent SingleLayerWater pass.
export async function applyWaterMaterial(material, descriptor, loadTexture, origin) {
  const water=descriptor.settings.water;
  material.map=null;material.alphaMap=null;material.roughnessMap=null;
  material.metalnessMap=null;material.aoMap=null;material.emissiveMap=null;
  material.vertexColors=false;material.alphaTest=0;material.metalness=0;
  material.roughness=water.roughness;material.opacity=water.opacity;
  material.color.fromArray(water.color);
  material.emissive.fromArray(water.color);material.emissiveIntensity=water.emission;
  material.userData.waterSettings=water;
  if(!material.normalMap) return;
  const second=descriptor.textures.water_normal_2
    ? await loadTexture(descriptor.textures.water_normal_2) : material.normalMap;
  material.userData.waterNormal2=second;
  material.userData.depthGeometryUnchanged=true;
  material.onBeforeCompile=shader=>{
    shader.uniforms.waterNormal2={value:second};
    shader.uniforms.waterStrength={value:new THREE.Vector2(...water.normal_strengths)};
    shader.uniforms.waterScale={value:new THREE.Vector2(...water.normal_scales_m)};
    shader.uniforms.waterUVScale={value:new THREE.Vector4(...water.normal_uv_scales.flat())};
    shader.uniforms.waterOrigin={value:new THREE.Vector2(origin[0]/100,origin[1]/100)};
    shader.vertexShader="varying vec3 waterPosition;\n"+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace("#include <worldpos_vertex>",`#include <worldpos_vertex>
      vec4 waterVertex=vec4(transformed,1.0);
      #ifdef USE_INSTANCING
        waterVertex=instanceMatrix*waterVertex;
      #endif
      waterPosition=(modelMatrix*waterVertex).xyz;`);
    shader.fragmentShader=`varying vec3 waterPosition;
      uniform sampler2D waterNormal2;
      uniform vec2 waterStrength,waterScale,waterOrigin;
      uniform vec4 waterUVScale;
      // Derivative tangent frame follows the projected UVs, including mirrored instances.
      mat3 waterFrame(vec3 position,vec3 n,vec2 uv) {
        vec3 dx=dFdx(position),dy=dFdy(position);
        vec2 du=dFdx(uv),dv=dFdy(uv);
        vec3 t=cross(dy,n)*du.x+cross(n,dx)*dv.x;
        vec3 b=cross(dy,n)*du.y+cross(n,dx)*dv.y;
        float invLength=inversesqrt(max(max(dot(t,t),dot(b,b)),1e-12));
        return mat3(t*invLength,b*invLength,n);
      }
      `+shader.fragmentShader;
    const coordinates=water.uv_mode==="mesh"
      ? "vec2 uvA=vNormalMapUv*waterUVScale.xy;vec2 uvB=vNormalMapUv*waterUVScale.zw;"
      : "vec2 uvA=(waterPosition.xz+waterOrigin)/waterScale.x;vec2 uvB=(waterPosition.xz+waterOrigin)/waterScale.y;";
    shader.fragmentShader=shader.fragmentShader.replace("#include <normal_fragment_maps>",`
      ${coordinates}
      vec2 slopeA=(texture2D(normalMap,uvA).xy*2.0-1.0)*waterStrength.x;
      vec2 slopeB=(texture2D(waterNormal2,uvB).xy*2.0-1.0)*waterStrength.y;
      vec3 ripple=normalize(vec3((slopeA+slopeB)*vec2(1.0,-1.0),1.0));
      normal=normalize(waterFrame(-vViewPosition,normal,uvA)*ripple);`);
  };
  material.customProgramCacheKey=()=>"world-water-static-v1-"+water.uv_mode;
}
