import * as THREE from "three";
import {createRenderMetrics} from "./world-render-metrics.js";
import {createDepthRegions} from "./world-depth-regions.js";

// Capture real opaque geometry with its original alpha tests and instance transforms.
// This pass runs only on a dirty frame with a visible depth-aware surface.
export function createSceneDepth(renderer,options={}) {
  const local=["localhost","127.0.0.1","::1"].includes(globalThis.location?.hostname);
  const query=new URLSearchParams(globalThis.location?.search||"");
  const legacy=options.legacy??(local&&query.get("performance")==="legacy");
  const metrics=createRenderMetrics(renderer,local&&query.has("debug"));
  const target=new THREE.WebGLRenderTarget(1,1,{
    depthTexture:new THREE.DepthTexture(1,1,THREE.UnsignedIntType),
    minFilter:THREE.NearestFilter,magFilter:THREE.NearestFilter,
  });
  const size=new THREE.Vector2(), frustum=new THREE.Frustum(), matrix=new THREE.Matrix4();
  const uniforms={sceneDepth:{value:target.depthTexture},depthViewport:{value:size},
    depthNearFar:{value:new THREE.Vector2()},depthPerspective:{value:true}};
  const variants=new Map(),previousRows=new Map();
  let captures=0,drawCalls=0,triangles=0,reused=0,depthCpu=0,colorCpu=0,scanCpu=0,cacheKey="",serial=0,regionCulled=0;
  const depthProperties=["side","alphaTest","alphaHash","alphaToCoverage","opacity","map","alphaMap","displacementMap",
    "displacementScale","displacementBias","depthTest","depthWrite","depthFunc","polygonOffset","polygonOffsetFactor",
    "polygonOffsetUnits","clippingPlanes","clipIntersection","clipShadows","wireframe","visible"];
  function supported(m,o){return !m.isShaderMaterial&&!m.isRawShaderMaterial&&!m.stencilWrite&&
    (!m.vertexColors||o.geometry?.attributes.color?.itemSize!==4)&&
    (m.onBeforeCompile===THREE.Material.prototype.onBeforeCompile||
      (m.userData.depthGeometryUnchanged===true&&(!(m.alphaTest||m.alphaHash||m.alphaToCoverage)||m.userData.depthAlphaUnchanged===true)));}
  function depthMaterial(m,o) {
    if(legacy||!supported(m,o))return m;
    let row=variants.get(m);
    if(!row){const material=new THREE.MeshDepthMaterial();material.colorWrite=false;
      const dispose=()=>{material.dispose();m.removeEventListener("dispose",dispose);variants.delete(m);};
      row={material,dispose,version:-1};variants.set(m,row);m.addEventListener("dispose",dispose);}
    let changed=row.version!==m.version;
    for(const key of depthProperties){
      const value=(key==="map"||key==="alphaMap")&&!(m.alphaTest||m.alphaHash||m.alphaToCoverage)?null:m[key];
      if(row.material[key]!==value){row.material[key]=value;changed=true;}
    }
    if(changed){row.material.needsUpdate=true;row.version=m.version;}
    return row.material;
  }
  function rowSignature(o) {
    const materials=[o.material].flat(),g=o.geometry;
    const values=[o.id,o.count,g?.id,g?.drawRange.start,g?.drawRange.count,o.instanceMatrix?.version,
      o.instanceColor?.version,o.renderOrder,o.layers.mask,...o.matrixWorld.elements];
    for(const a of Object.values(g?.attributes||{}))values.push(a.version??a.data?.version);
    values.push(g?.index?.version);
    for(const group of g?.groups||[])values.push(group.start,group.count,group.materialIndex);
    for(const m of materials){values.push(m.id,m.version,...depthProperties.map(k=>typeof m[k]==="object"?m[k]?.id??JSON.stringify(m[k]):m[k]));
      for(const t of [m.map,m.alphaMap,m.displacementMap].filter(Boolean)){if(t.matrixAutoUpdate)t.updateMatrix();values.push(t.id,t.version,t.channel,...t.matrix.elements);}
    }return values.join(",");
  }
  async function prepareEditable(root,camera,scene) {
    if(legacy)return;
    const prepared=new THREE.Group();
    root.traverse(o=>{
      if(!o.isMesh)return;
      const materials=[o.material].flat();
      if(materials.some(m=>m.transparent||!m.depthWrite||m.userData.sceneDepthEffect))return;
      const copy=o.clone(false);
      copy.material=Array.isArray(o.material)?materials.map(m=>depthMaterial(m,o)):depthMaterial(o.material,o);
      prepared.add(copy);
    });
    // Compilation depends on the depth target's linear output color space. Restore
    // the target before awaiting so normal frames can continue during preparation.
    const previous=renderer.getRenderTarget();let ready;
    try {renderer.setRenderTarget(target);ready=renderer.compileAsync(prepared,camera,scene);}
    finally {renderer.setRenderTarget(previous);}
    await ready;
  }
  function render(scene,camera) {
    metrics.poll();drawCalls=0;triangles=0;depthCpu=0;regionCulled=0;
    const scanStart=performance.now();
    camera.updateMatrixWorld();
    scene.updateMatrixWorld();
    frustum.setFromProjectionMatrix(matrix.multiplyMatrices(camera.projectionMatrix,camera.matrixWorldInverse),camera.coordinateSystem,camera.reversedDepth);
    renderer.getDrawingBufferSize(size);
    let regions;
    let needed=false,uncacheable=false;
    let renderCallbacks=scene.onBeforeRender!==THREE.Object3D.prototype.onBeforeRender || scene.onAfterRender!==THREE.Object3D.prototype.onAfterRender;
    const opaque=[],hidden=[],visible=[],receivers=[],replacements=[],colorHidden=[],cullingDisabled=[];
    const inFrustum=new Map();
    scene.traverseVisible(o=>{
      if(!o.material)return;
      if(o.onBeforeRender!==THREE.Object3D.prototype.onBeforeRender || o.onAfterRender!==THREE.Object3D.prototype.onAfterRender)renderCallbacks=true;
      visible.push(o);
      const materials=Array.isArray(o.material)?o.material:[o.material];
      if(materials.some(m=>m.onBeforeRender && m.onBeforeRender!==THREE.Material.prototype.onBeforeRender))renderCallbacks=true;
      if(o.isMesh&&o.frustumCulled)inFrustum.set(o,frustum.intersectsObject(o));
      if(o.isMesh&&materials.some(m=>m.userData.sceneDepthEffect)&&inFrustum.get(o)!==false){needed=true;receivers.push(o);}
    });
    const autoUpdate=scene.matrixWorldAutoUpdate;
    // Both passes use the same camera and transforms. Unknown render callbacks
    // retain automatic updates in case they change transforms between passes.
    if(!renderCallbacks){
      scene.matrixWorldAutoUpdate=false;
      for(const [object,inside]of inFrustum){
        if(inside){object.frustumCulled=false;cullingDisabled.push(object);}
        // Renderer culling never suppresses a mesh's children. Hide only leaves.
        else if(!object.children.length){object.visible=false;colorHidden.push(object);}
      }
    }
    try {
    if(needed) {
      if(!legacy){regions=createDepthRegions(camera,size.x,size.y);for(const o of receivers)regions.add(o);}
      for(let o of visible){
        const materials=Array.isArray(o.material)?o.material:[o.material];
        // Helpers with depth testing disabled cannot write depth (glDepthMask).
        if(!legacy&&o.onBeforeRender===THREE.Object3D.prototype.onBeforeRender&&materials.every(m=>!m.stencilWrite&&(!m.depthTest||!m.depthWrite))){hidden.push(o);continue;}
        if(o.isMesh&&materials.some(m=>m.transparent||!m.depthWrite||m.userData.sceneDepthEffect)){hidden.push(o);continue;}
        if(inFrustum.get(o)===false)continue;
        if(!legacy){
          const candidate=o.userData.depthCandidate?.(regions.affects);
          if(candidate===null){hidden.push(o);regionCulled++;continue;}
          if(candidate&&candidate!==o){hidden.push(o);replacements.push([candidate,o.parent]);o=candidate;}
          else if(!regions.affects(o)){hidden.push(o);regionCulled++;continue;}
        }
        opaque.push(o);
        if(o.isSkinnedMesh||o.morphTargetInfluences||materials.some(m=>!supported(m,o))||
          o.onBeforeRender!==THREE.Object3D.prototype.onBeforeRender)uncacheable=true;
      }
      renderer.getDrawingBufferSize(size);
      if(target.width!==size.x || target.height!==size.y) target.setSize(size.x,size.y);
      uniforms.depthNearFar.value.set(camera.near,camera.far);
      uniforms.depthPerspective.value=!!camera.isPerspectiveCamera;
      const key=[serial,size.x,size.y,camera.layers.mask,...camera.matrixWorld.elements,...camera.projectionMatrix.elements].join(",");
      let dirty=legacy||uncacheable||cacheKey!==key||previousRows.size!==opaque.length;
      const rows=new Map();
      // A moving camera already requires a capture. Avoid allocating thousands of
      // signatures for a cache that cannot be reused on that frame.
      if(!legacy&&!uncacheable&&cacheKey===key)
        for(const o of opaque){const stamp=rowSignature(o);rows.set(o.id,stamp);if(previousRows.get(o.id)!==stamp)dirty=true;}
      scanCpu=performance.now()-scanStart;
      if(dirty){
      const previous=renderer.getRenderTarget();
      const viewport=renderer.getViewport(new THREE.Vector4());
      const scissor=renderer.getScissor(new THREE.Vector4());
      const scissorTest=renderer.getScissorTest();
      const originals=[];const start=performance.now();
      try {
        for(const o of hidden)o.visible=false;
        for(const [o,parent]of replacements)parent.add(o);
        for(const o of opaque)if(o.isMesh){originals.push([o,o.material]);o.material=Array.isArray(o.material)?o.material.map(m=>depthMaterial(m,o)):depthMaterial(o.material,o);}
        metrics.begin("depth");renderer.setRenderTarget(target);renderer.setScissorTest(false);renderer.clear();renderer.render(scene,camera);metrics.end();captures++;
        drawCalls=renderer.info.render.calls;triangles=renderer.info.render.triangles;
        previousRows.clear();for(const [id,stamp]of rows)previousRows.set(id,stamp);cacheKey=key;
      } finally {
        metrics.end();
        renderer.setRenderTarget(previous);
        renderer.setViewport(viewport);renderer.setScissor(scissor);renderer.setScissorTest(scissorTest);
        for(const o of hidden)o.visible=true;
        for(const [o,m]of originals)o.material=m;
        for(const [o]of replacements)o.removeFromParent();
      }
      depthCpu=performance.now()-start;
      }else reused++;
    } else {
      scanCpu=performance.now()-scanStart;
    }
    const start=performance.now();metrics.begin("color");renderer.render(scene,camera);metrics.end();colorCpu=performance.now()-start;
    } finally {
      metrics.end(); scene.matrixWorldAutoUpdate=autoUpdate;
      for(const object of cullingDisabled)object.frustumCulled=true;
      for(const object of colorHidden)object.visible=true;
    }
  }
  return {uniforms,render,prepareEditable,invalidate:()=>{serial++;},
    dispose:()=>{target.dispose();for(const row of [...variants.values()])row.dispose();previousRows.clear();metrics.dispose();},
    stats:()=>({captures,reused,width:target.width,height:target.height,draw_calls:drawCalls,triangles,
      depth_cpu_ms:depthCpu,color_cpu_ms:colorCpu,scan_cpu_ms:scanCpu,region_culled:regionCulled,variants:variants.size,...metrics.stats()})};
}

export function applyDepthEffect(material,depth,code,key,maxGap=Infinity) {
  material.transparent=true;material.depthWrite=false;
  material.userData.sceneDepthEffect=key;
  const previous=material.onBeforeCompile,previousKey=material.customProgramCacheKey();
  material.userData.depthGeometryUnchanged=previous===THREE.Material.prototype.onBeforeCompile||material.userData.depthGeometryUnchanged===true;
  material.userData.depthMaxGap=maxGap;
  material.onBeforeCompile=shader=>{
    previous.call(material,shader);
    Object.assign(shader.uniforms,depth.uniforms);
    shader.vertexShader="varying float surfaceViewDepth;\n"+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace("#include <project_vertex>",
      "#include <project_vertex>\nsurfaceViewDepth=-mvPosition.z;");
    shader.fragmentShader=`varying float surfaceViewDepth;
      uniform sampler2D sceneDepth;
      uniform vec2 depthViewport,depthNearFar;
      uniform bool depthPerspective;
      float surfaceDepthGap() {
        float z=texture2D(sceneDepth,gl_FragCoord.xy/depthViewport).r;
        if(z>=1.0) return 1e6;
        float nearZ=depthNearFar.x,farZ=depthNearFar.y;
        float viewDepth;
        #ifdef USE_LOGARITHMIC_DEPTH_BUFFER
          viewDepth=depthPerspective?exp2(z*log2(farZ+1.0))-1.0:mix(nearZ,farZ,z);
        #else
          viewDepth=depthPerspective?nearZ*farZ/(farZ-z*(farZ-nearZ)):mix(nearZ,farZ,z);
        #endif
        return max(0.0,viewDepth-surfaceViewDepth);
      }
      `+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace("#include <color_fragment>",
      "#include <color_fragment>\nfloat depthGap=surfaceDepthGap();\n"+code);
  };
  material.customProgramCacheKey=()=>previousKey+"-depth-v1-"+key;
}

export function applyWaterDepth(material,water,depth) {
  const settings=water.depth;
  if(!settings)return;
  const fade=Math.max(.0001,settings.fade_m).toFixed(8);
  let code=`diffuseColor.a*=clamp(depthGap/${fade},0.0,1.0);`;
  if(settings.mode==="river") {
    const shallow=settings.shallow_color.map(n=>n.toFixed(8)).join(",");
    code=`diffuseColor.rgb=mix(vec3(${shallow}),diffuseColor.rgb,clamp(depthGap/${Math.max(.0001,settings.color_m).toFixed(8)},0.0,1.0));
      diffuseColor.a=mix(${settings.shallow_opacity.toFixed(8)},diffuseColor.a,clamp(depthGap/${fade},0.0,1.0));`;
  }
  applyDepthEffect(material,depth,code,JSON.stringify(settings),Math.max(.0001,settings.fade_m,settings.color_m||0));
}
