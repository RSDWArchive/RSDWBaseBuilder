import * as THREE from "three";
import {uePoint} from "./world-transforms.js";

// Read-only overview visuals shared by the standalone viewer and builder host.
export function createOverviewTile(model,tile,sourceOrigin,renderOrigin) {
  const object=model.scene.clone(true);
  object.position.add(uePoint(sourceOrigin,renderOrigin));
  object.userData.overview=true;object.userData.tile=tile;object.userData.worldTile=tile;
  return object;
}
export function createMapPoints({size=9,color="#e0c896"}={}) {
  const icon=document.createElement("canvas");icon.width=32;icon.height=32;
  const ctx=icon.getContext("2d");ctx.fillStyle=color;ctx.strokeStyle="#303b40";ctx.lineWidth=3;
  ctx.beginPath();ctx.arc(16,16,11,0,Math.PI*2);ctx.fill();ctx.stroke();
  const material=new THREE.PointsMaterial({map:new THREE.CanvasTexture(icon),size,sizeAttenuation:false,
    transparent:true,alphaTest:.05,depthTest:false,depthWrite:false});
  const points=new THREE.Points(new THREE.BufferGeometry(),material);points.renderOrder=100;points.frustumCulled=false;
  return points;
}
export function projectedMarkerDistance(point,event,rect,camera) {
  const p=point.clone().project(camera);if(p.z<-1||p.z>1)return Infinity;
  return Math.hypot(rect.left+(p.x+1)*rect.width/2-event.clientX,rect.top+(1-p.y)*rect.height/2-event.clientY);
}
