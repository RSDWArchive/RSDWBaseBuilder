import * as THREE from "three";
import { uePoint } from "./world-transforms.js";
import {createMapPoints,projectedMarkerDistance} from "../../../website/world/world-navigation-visuals.js";

// Screen-sized navigation markers, not substitute geometry or loaded placements.
export function createSectionMarkers({scene,camera,canvas,origin,open,invalidate}) {
  const points=createMapPoints({size:7});points.material.opacity=.8;points.visible=false;scene.add(points);
  let rows=[],positions=[],down=null;
  function hit(event) {
    if(!points.visible)return null;
    const rect=canvas.getBoundingClientRect();let best=null,distance=12;
    positions.forEach((p,i)=>{
      const d=projectedMarkerDistance(p,event,rect,camera);
      if(d<distance){best=rows[i];distance=d;}
    });
    return best;
  }
  canvas.addEventListener("pointerdown",e=>{if(e.button===0)down=[e.clientX,e.clientY];});
  canvas.addEventListener("pointerup",e=>{
    const click=down && e.button===0 && Math.hypot(e.clientX-down[0],e.clientY-down[1])<5;down=null;
    const row=click?hit(e):null;if(row)open(row.id);
  });
  canvas.addEventListener("pointercancel",()=>{down=null;});
  canvas.addEventListener("pointermove",e=>{if(!e.buttons)canvas.title=hit(e)?.name || "";});
  return {
    setSections(sections) {
      rows=sections.filter(s=>(s.visible_placements??s.placements)>0 || s.terrain>0);
      positions=rows.map(s=>{
        const b=s.content_bounds_cm || s.bounds_cm;
        const center=b.min.map((v,i)=>(v+b.max[i])/2);
        for(let i=0;i<2;i++)center[i]=Math.max(s.bounds_cm.min[i],Math.min(s.bounds_cm.max[i],center[i]));
        return uePoint(center,origin);
      });
      points.geometry.dispose();points.geometry=new THREE.BufferGeometry();
      points.geometry.setAttribute("position",new THREE.Float32BufferAttribute(positions.flatMap(p=>p.toArray()),3));
      invalidate();
    },
    setVisible(visible){if(points.visible!==visible){points.visible=visible;invalidate();}},
    count:()=>points.visible?rows.length:0,
  };
}
