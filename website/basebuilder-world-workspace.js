import * as THREE from "three";
import { LOCAL_WORLD } from "./world/local-config.js";
import { createWorldLayer, readWorldDataset } from "./world/world-layer.js";
import { uePoint, worldPoint } from "./world/world-transforms.js";
import { projectNavigation } from "./basebuilder-project.js";
import { createWorldOverview } from "./world/world-overview.js";
import { planSections, sectionFocus, detailViewSpan, distanceToSection, STREAM_POLICY } from "./world/world-streaming.js";

export async function createWorldWorkspace(host) {
  const listeners = new AbortController(), listenerOptions = { signal: listeners.signal };
  const panel = document.querySelector("#world-workspace"); panel.hidden = false;
  const section = panel.querySelector("#world-section-select");
  const status = panel.querySelector("#world-load-status");
  const areaInput=panel.querySelector("#world-area"),search=panel.querySelector("#world-search"),streamInput=panel.querySelector("#world-streaming");
  let dataset = null, datasetError = null;
  try { dataset = await readWorldDataset(LOCAL_WORLD, host.catalog.version); }
  catch (error) { datasetError = error.message; status.textContent = datasetError; }
  const first = dataset?.index.sections.find(s => s.id === LOCAL_WORLD.sectionId);
  const origin = [...host.getOrigin()];
  const root = new THREE.Group(); root.name = "Read-only World"; host.scene.add(root);
  const layer = createWorldLayer({renderer:host.renderer,root,getCamera:host.getCamera,originCm:origin,isBusy:host.busy,onStatus:()=>updateWorldStatus()});
  let overview=null,overviewState={},streamTimer=0,streamKey="",navigationSerial=0,detailActive=true,mapPointer=null;
  let navigation={mode:"overview",streaming_enabled:true,area_filter:"all",focus_cm:[...origin],last_build_camera:null,overview_camera:null};
  let plannerDeferred=[];
  let locationChoices=null;
  areaInput.replaceChildren(new Option("All Areas", "all")); section.replaceChildren();
  for(const area of [...new Set((dataset?.index.sections||[]).map(r=>r.biome))].sort())areaInput.add(new Option(area,area));
  function populateLocations() {
    const current=section.value || requestedSection;
    section.replaceChildren();
    for(const row of locationChoices?.rows || dataset?.index.sections || [])if((navigation.area_filter==="all"||row.biome===navigation.area_filter)&&row.name.toLowerCase().includes(search.value.toLowerCase()))section.add(new Option(row.name,row.id));
    if([...section.options].some(o=>o.value===current))section.value=current;
    panel.querySelector("#world-load-section").disabled=!section.options.length;
  }
  for (const row of dataset?.index.sections || []) section.add(new Option(row.name,row.id));
  section.value = first?.id || "";
  let requestedSection = section.value, worldEnabled = true, worldMismatch = false;
  let suspended = true, pendingWorld = null;
  const markChanged = options => host.markChanged(options);
  const cameraState=()=>({position_cm:worldPoint(host.getCamera().position,origin),target_cm:worldPoint(host.controls.target,origin),
    projection:host.getCamera().isOrthographicCamera?"orthographic":"perspective",size:host.getOrthoSize()});
  function restoreCamera(camera) {host.restoreView({camera,orientation:host.getOrientation()});}
  function updateWorldStatus() {
    const state=layer.getStatus(),issues=state.failed?.length || 0;
    const overviewIssues=overviewState.failed?.length || 0;
    status.dataset.error=String(issues>0||overviewIssues>0||!!state.error||!!datasetError||worldMismatch);
    if(!dataset||worldMismatch){status.textContent=worldMismatch?"Project world identity differs; context remains disabled":datasetError;return;}
    if(!worldEnabled){status.textContent="World unloaded";return;}
    const label=navigation.mode==="overview"?"World Map":dataset.index.sections.find(s=>s.id===state.sectionId)?.name || "Nearby world";
    const summary=navigation.mode==="overview"?`${overviewState.loaded || 0}/${dataset.shared.overview.length} map tiles`:
      `${state.placements.toLocaleString()} world objects | ${state.loadedSectionIds.length} sections`;
    const pending=state.pending?.length || 0,deferred=(state.deferred?.length||0)+plannerDeferred.length;
    status.textContent=`${label} | ${summary}${pending?` | ${pending} loading`:""}${deferred?` | ${deferred} deferred`:""}${issues+overviewIssues?` | ${issues+overviewIssues} failed (Load / Retry)`:""}${!navigation.streaming_enabled?" | Streaming paused":""}`;
    overview?.setCoverage(layer.getTerrainIds());
  }
  async function prepareOverview() {
    if(overview)return overview;
    if(!dataset||worldMismatch)return null;
    overview=createWorldOverview({root:host.scene,dataset,resources:layer.resources,originCm:origin,getCamera:host.getCamera,isBusy:host.busy,
      onStatus:state=>{overviewState=state;updateWorldStatus();}});
    overview.setArea(navigation.area_filter);overview.setTerrainVisible(layer.getVisibility().terrain);overview.setVisible(worldEnabled);
    overview.load().catch(error=>host.notice(error.message));return overview;
  }
  function syncNavigation() {
    areaInput.value=navigation.area_filter;streamInput.checked=navigation.streaming_enabled;
    panel.querySelector("#world-map").setAttribute("aria-pressed",String(navigation.mode==="overview"));
    host.setMapMode?.(!suspended && worldEnabled && navigation.mode==="overview");
    overview?.setArea(navigation.area_filter);overview?.setVisible(worldEnabled);
    overview?.setMarkersVisible(navigation.mode==="overview"||!detailActive);
    populateLocations();updateWorldStatus();
  }
  async function stream(force=false) {
    if(!dataset||worldMismatch||!worldEnabled||suspended||host.busy())return;
    if(navigation.mode==="overview")return;
    const camera=host.getCamera(),span=detailViewSpan(camera,camera.position.distanceTo(host.controls.target));
    detailActive=span<(detailActive?1600:1200);overview?.setMarkersVisible(!detailActive);
    const focus=worldPoint(host.controls.target,origin);
    const dest=dataset.index.sections.find(s=>s.id===requestedSection);
    const destination=dest&&distanceToSection(focus,dest)===0?requestedSection:
      dataset.index.sections.find(s=>(navigation.area_filter==="all"||s.biome===navigation.area_filter)&&distanceToSection(focus,s)===0)?.id;
    const neighborhood=focus.map((v,i)=>i<2?Math.round(v/STREAM_POLICY.quantumCm)*STREAM_POLICY.quantumCm:v);
    const plan=planSections({sections:dataset.index.sections,focus:neighborhood,area:navigation.area_filter,destination,resident:layer.getStatus().loadedSectionIds});
    const desired=detailActive?(navigation.streaming_enabled?plan.desired:(destination?[destination]:[])):[];
    if(!navigation.streaming_enabled&&!force)return;
    const key=[...desired,detailActive,navigation.area_filter].join(":");if(!force&&key===streamKey)return;
    streamKey=key;plannerDeferred=plan.deferred;
    await layer.setSections({dataset,sectionIds:desired,sectionId:destination||desired[0],retry:force});updateWorldStatus();
  }
  function scheduleStream() {clearTimeout(streamTimer);streamTimer=setTimeout(()=>stream().catch(e=>host.notice(e.message)),STREAM_POLICY.debounceMs);}
  async function enterLocation(id,point=null) {
    if(host.busy()){pendingWorld=()=>enterLocation(id,point);host.notice("World change queued until editing finishes");return;}
    if(!dataset||worldMismatch)return;
    const row=dataset.index.sections.find(s=>s.id===id);if(!row)throw Error("Unknown world location");
    locationChoices=null;
    if(navigation.mode==="overview")navigation.overview_camera=cameraState();
    const token=++navigationSerial;requestedSection=id;section.value=id;worldEnabled=true;
    navigation.mode="build";navigation.focus_cm=point?[...point]:(overview?.navigationPoint(row)||sectionFocus(row,dataset.shared.overview));
    if(navigation.area_filter!=="all"&&navigation.area_filter!==row.biome)navigation.area_filter="all";
    detailActive=true;streamKey="";await prepareOverview();if(token!==navigationSerial)return;syncNavigation();
    const focus=uePoint(navigation.focus_cm,origin);
    host.frameDestination(new THREE.Box3().setFromCenterAndSize(focus,new THREE.Vector3(100,40,100)),focus);
    const destinationCamera=cameraState();navigation.last_build_camera=destinationCamera;markChanged();
    panel.querySelector(".world-location-menu").open=false;
    await stream(true);
    if(token===navigationSerial && JSON.stringify(cameraState())===JSON.stringify(destinationCamera) && layer.getStatus().loadedSectionIds.includes(id)) {
      const ray=new THREE.Ray(new THREE.Vector3(focus.x,100000,focus.z),new THREE.Vector3(0,-1,0));const hit=layer.raycastSurface(ray);
      if(hit&&Math.abs(hit.point.y-focus.y)<200){const delta=(hit.point.y-focus.y)*100;destinationCamera.target_cm[2]+=delta;destinationCamera.position_cm[2]+=delta;restoreCamera(destinationCamera);navigation.last_build_camera=destinationCamera;markChanged();}
    }
  }
  async function showMap({restore=true}={}) {
    if(host.busy()){pendingWorld=()=>showMap({restore});host.notice("World change queued until editing finishes");return;}
    const token=++navigationSerial;if(navigation.mode==="build")navigation.last_build_camera=cameraState();
    navigation.mode="overview";worldEnabled=true;clearTimeout(streamTimer);streamKey="";
    await prepareOverview();if(token!==navigationSerial)return;syncNavigation();
    if(restore&&navigation.overview_camera)restoreCamera(navigation.overview_camera);
    else {const box=overview?.getBounds();if(box)host.frameMap(box);}
    navigation.overview_camera=cameraState();markChanged();
    if(dataset)await layer.setSections({dataset,sectionIds:[]});
  }
  async function returnToBuild() {
    if(host.busy()){pendingWorld=returnToBuild;return;}
    if(navigation.mode==="overview")navigation.overview_camera=cameraState();
    navigation.mode="build";worldEnabled=true;const token=++navigationSerial;detailActive=true;streamKey="";await prepareOverview();if(token!==navigationSerial)return;syncNavigation();
    if(navigation.last_build_camera)restoreCamera(navigation.last_build_camera);
    else if(host.count())host.frameBuild();
    else return enterLocation(requestedSection||first?.id);
    markChanged();await stream(true);
  }
  async function runWorld(action) {
    if (host.busy()) { pendingWorld = action; status.textContent = "World change queued until editing finishes"; return; }
    pendingWorld = null;
    if (action === "unload") { navigationSerial++;clearTimeout(streamTimer);streamKey="";worldEnabled=false;layer.unload();overview?.setVisible(false);markChanged();return; }
    const token=++navigationSerial;worldEnabled=true; markChanged();
    if (!dataset || worldMismatch) { status.textContent=worldMismatch?"Project world identity differs; context remains disabled":datasetError; return; }
    try {await prepareOverview();if(token!==navigationSerial||!worldEnabled)return;syncNavigation();overview?.load({retry:true});
      if(action==="load") {requestedSection=section.value||requestedSection;navigation.mode="build";syncNavigation();
        // Explicit Load keeps the saved camera; Build Here is the navigation action.
        await layer.loadSection({dataset,sectionId:requestedSection});}
      else if(navigation.mode==="overview")await showMap();else await stream(true);
    }
    catch(error) { status.textContent=error.message; }
  }
  function frame() {
    if(navigation.mode==="overview"){const b=overview?.getBounds();if(b)host.frameMap(b);markChanged();return;}
    const box=layer.getBounds(),focus=layer.getFocus();
    if (!box || !focus) return;
    host.frameWorld(box,focus); markChanged();
  }
  function action(id,callback) {panel.querySelector(id).addEventListener("click",()=>Promise.resolve().then(callback).catch(error=>host.notice(error.message)), listenerOptions);}
  const menus=[...panel.querySelectorAll("details")];
  function positionMenus() {for(const menu of menus)if(menu.open){const actions=menu.querySelector(".project-menu-actions");if(!actions)continue;
    const r=menu.getBoundingClientRect(),width=actions.getBoundingClientRect().width;
    actions.style.left=`${Math.max(8,Math.min(r.left,innerWidth-width-8))-r.left}px`;actions.style.right="auto";
  }}
  for(const menu of menus)menu.addEventListener("toggle",positionMenus);window.addEventListener("resize",positionMenus);
  action("#world-load-section",()=>enterLocation(section.value,locationChoices?.point)); action("#world-unload-section",()=>runWorld("unload"));
  action("#world-resume",()=>runWorld("resume"));action("#world-map",()=>showMap());action("#world-return-build",returnToBuild);
  search.addEventListener("input",()=>{locationChoices=null;populateLocations();}, listenerOptions);
  areaInput.addEventListener("change",()=>{
    const value=areaInput.value;
    const apply=async()=>{locationChoices=null;navigation.area_filter=value;navigation.overview_camera=null;populateLocations();await showMap({restore:false});};
    if(host.busy())pendingWorld=apply;else apply().catch(e=>host.notice(e.message));
  }, listenerOptions);
  streamInput.addEventListener("change",()=>{
    const enabled=streamInput.checked;
    const apply=async()=>{navigation.streaming_enabled=enabled;streamKey="";markChanged();updateWorldStatus();
      if(enabled)await stream(true);
      else if(dataset){const state=layer.getStatus();await layer.setSections({dataset,sectionIds:state.loadedSectionIds,sectionId:state.loadedSectionId});}
    };
    if(host.busy())pendingWorld=apply;else apply().catch(e=>host.notice(e.message));
  }, listenerOptions);
  action("#world-frame-section",frame);
  const layerInputs=[...panel.querySelectorAll("[data-world-layer]")];
  function syncLayerControls(){for(const input of layerInputs)input.checked=layer.getVisibility()[input.dataset.worldLayer];}
  for(const input of layerInputs)input.addEventListener("change",()=>{layer.setLayerVisible(input.dataset.worldLayer,input.checked);
    if(input.dataset.worldLayer==="terrain")overview?.setTerrainVisible(input.checked);markChanged();}, listenerOptions);
  syncLayerControls();
  function cameraChanged(){if(!suspended)scheduleStream();}
  host.controls.addEventListener("change",cameraChanged);
  const canvas=host.renderer.domElement;
  function mapDown(event){if(suspended||!worldEnabled||navigation.mode!=="overview"||event.button!==0||host.busy())return;
    mapPointer={id:event.pointerId,x:event.clientX,y:event.clientY};event.stopImmediatePropagation();canvas.setPointerCapture(event.pointerId);}
  function mapUp(event){if(!mapPointer||mapPointer.id!==event.pointerId)return;
    const clicked=Math.hypot(event.clientX-mapPointer.x,event.clientY-mapPointer.y)<5;mapPointer=null;event.stopImmediatePropagation();canvas.releasePointerCapture(event.pointerId);
    if(!clicked)return;const hit=overview?.hit(event,canvas);
    if(hit?.build)returnToBuild().catch(e=>host.notice(e.message));
    else if(hit?.section)enterLocation(hit.section.id,hit.point).catch(e=>host.notice(e.message));
    else if(hit?.choices){locationChoices={rows:hit.choices,point:hit.point};search.value="";populateLocations();panel.querySelector(".world-location-menu").open=true;host.notice("Choose a location from Locations");}
  }
  function mapCancel(){mapPointer=null;}
  function mapHover(event){if(!suspended&&worldEnabled&&navigation.mode==="overview"&&!event.buttons)canvas.title=overview?.hit(event,canvas,{terrain:false})?.name || "World Map";else canvas.title="";}
  canvas.addEventListener("pointerdown",mapDown,true);canvas.addEventListener("pointerup",mapUp,true);
  canvas.addEventListener("pointercancel",mapCancel);canvas.addEventListener("pointermove",mapHover);
  const gestureTimer=setInterval(()=>{if(suspended)return;if(pendingWorld&&!host.busy()){const action=pendingWorld;pendingWorld=null;
    Promise.resolve(typeof action==="function"?action():runWorld(action)).catch(e=>host.notice(e.message));}else if(!host.busy()&&worldEnabled)scheduleStream();},500);
  function captureContext() {
    return {requested_section_id:requestedSection,world_enabled:worldEnabled,visible_world_layers:layer.getVisibility(),
      navigation:{...structuredClone(navigation),focus_cm:worldPoint(host.controls.target,origin)},camera:cameraState()};
  }
  async function deactivate() {
    suspended=true;navigationSerial++;pendingWorld=null;clearTimeout(streamTimer);streamKey="";
    layer.unload();root.visible=false;host.setMapMode(false);
    if(overview){const old=overview;overview=null;await old.dispose();}overviewState={};
  }
  async function start(context=null) {
    root.visible=true;suspended=false;
    worldMismatch=!!dataset&&!!host.getWorldIdentity()&&host.getWorldIdentity()!==dataset.index.scene_sha256;
    if(context){
      requestedSection=context.requested_section_id;section.value=requestedSection;worldEnabled=context.world_enabled;
      navigation=projectNavigation(context);restoreCamera(context.camera);
      for(const [name,visible]of Object.entries(context.visible_world_layers))layer.setLayerVisible(name,visible);
      syncLayerControls();
      if(navigation.area_filter!=="all"&&!dataset?.index.sections.some(s=>s.biome===navigation.area_filter))navigation.area_filter="all";
      if(dataset&&!dataset.index.sections.some(s=>s.id===requestedSection))requestedSection=planSections({sections:dataset.index.sections,focus:navigation.focus_cm}).desired[0]||"";
      syncNavigation();
      if(worldEnabled&&!worldMismatch){await prepareOverview();syncNavigation();if(navigation.mode==="build")await stream(true);}
    }else await showMap({restore:false});
    updateBuildMarker();updateWorldStatus();
  }
  function updateBuildMarker(){const bounds=host.getBuildBounds?.();overview?.setBuildPoint(bounds?worldPoint(bounds.getCenter(new THREE.Vector3()),origin):null);}
  return {start,deactivate,captureContext,updateBuildMarker,layer,runWorld,frame,enterLocation,showMap,returnToBuild,stream,
    identity:()=>dataset?.index.scene_sha256 || null,
    error:()=>datasetError || (worldMismatch?"Project world identity differs; context remains disabled":null),
    isMap:()=>!suspended&&worldEnabled&&navigation.mode==="overview",getNavigation:()=>structuredClone(navigation),getOverviewMetrics:()=>overview?.getMetrics(),
    beforeFrameBuild(){if(!suspended&&navigation.mode==="overview"){navigation.overview_camera=cameraState();navigation.mode="build";syncNavigation();streamKey="";}},
    render:scene=>layer.render(scene),surface:ray=>!suspended&&worldEnabled?layer.raycastSurface(ray):null,
    clipDistance:()=>Math.max(layer.getBounds()?.getSize(new THREE.Vector3()).length()||0,overview?.getBounds()?.getSize(new THREE.Vector3()).length()||0),
    async dispose(){listeners.abort();await deactivate();clearInterval(gestureTimer);host.controls.removeEventListener("change",cameraChanged);
      canvas.removeEventListener("pointerdown",mapDown,true);canvas.removeEventListener("pointerup",mapUp,true);canvas.removeEventListener("pointercancel",mapCancel);canvas.removeEventListener("pointermove",mapHover);
      for(const menu of menus)menu.removeEventListener("toggle",positionMenus);window.removeEventListener("resize",positionMenus);
      layer.unload();if(overview)await overview.dispose();await layer.dispose();root.removeFromParent();},
  };
}
