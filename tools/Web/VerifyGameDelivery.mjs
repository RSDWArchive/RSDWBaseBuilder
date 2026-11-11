import {readFile, writeFile, mkdir} from "node:fs/promises";
import {resolve, dirname} from "node:path";
import {parseArgs} from "node:util";
import {pathToFileURL} from "node:url";

const axes=["x","y","z","pitch","yaw","roll","scale_x","scale_y","scale_z"];
const radians=Math.PI/180;
const shortName=value=>String(value||"").replace(/["']/g,"").split("/").at(-1).split(".").at(-1);
function rows(document){
  if(document.schema!=="rsdwtools.buildings.v1")throw Error("Expected rsdwtools.buildings.v1 capture");
  return ["pieces","items","actors"].flatMap(kind=>(document[kind]||[]).map((row,index)=>{
    if(!axes.every(k=>Number.isFinite(row[k])))throw Error(`Incomplete actor-root transform: ${kind}[${index}]`);
    const actor=shortName(row.class_name||row.actor_class||row.class_path);
    const data=kind==="pieces"?shortName(row.piece_data_name):kind==="items"?shortName(row.item_asset_name||row.item_asset_path):"";
    if(!actor || (kind!=="actors"&&!data))throw Error(`Missing class/data identity: ${kind}[${index}]`);
    return {kind,index,row,identity:[kind,actor,data].join("|")};
  }));
}
// Unreal FRotator's quaternion signs/order, independent of browser mesh offsets.
function quaternion({pitch,yaw,roll}){
  const [sp,sy,sr]=[pitch,yaw,roll].map(v=>Math.sin(v*radians/2));
  const [cp,cy,cr]=[pitch,yaw,roll].map(v=>Math.cos(v*radians/2));
  return [cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy];
}
function errors(expected,actual){
  const a=quaternion(expected),b=quaternion(actual);
  return {position_cm:Math.hypot(...["x","y","z"].map(k=>actual[k]-expected[k])),
    orientation_degrees:2*Math.acos(Math.min(1,Math.abs(a.reduce((n,v,i)=>n+v*b[i],0))))/radians,
    scale_max:Math.max(...["scale_x","scale_y","scale_z"].map(k=>Math.abs(actual[k]-expected[k])))};
}
const cell=row=>[row.x,row.y,row.z].map(v=>Math.floor(v/5));
const cellKey=(identity,xyz)=>identity+"|"+xyz.join(",");
export function compareDelivery(expected,actual){
  const source=rows(expected),received=rows(actual),buckets=new Map(),used=new Set(),assigned=new Map(),edges=new Map();
  for(const row of received){const key=cellKey(row.identity,cell(row.row));if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(row);}
  const missing=[],matches=[],max={position_cm:0,orientation_degrees:0,scale_max:0},outliers=new Map();
  for(const row of source){
    const xyz=cell(row.row),candidates=[];
    for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++)
      for(const candidate of buckets.get(cellKey(row.identity,[xyz[0]+x,xyz[1]+y,xyz[2]+z]))||[])if(!used.has(candidate))candidates.push(candidate);
    const ranked=candidates.map(candidate=>({candidate,error:errors(row.row,candidate.row)}))
      .filter(({error:e})=>e.position_cm<=1&&e.orientation_degrees<=.1&&e.scale_max<=.001)
      .sort((a,b)=>a.error.position_cm-b.error.position_cm||a.error.orientation_degrees-b.error.orientation_degrees);
    edges.set(row,ranked);outliers.set(row,candidates);
  }
  // Augmenting paths avoid greedy false failures when neighboring duplicates have
  // overlapping tolerances. Matching is one-to-one, never based on runtime IDs.
  const owner=new Map();
  for(const start of source){
    const queue=[start],visited=new Set([start]),parent=new Map();let free=null;
    for(let i=0;i<queue.length&&!free;i++)for(const edge of edges.get(queue[i])){
      const previous=owner.get(edge.candidate);
      if(!previous){free={row:queue[i],edge};break;}
      if(!visited.has(previous)){visited.add(previous);parent.set(previous,{row:queue[i],edge});queue.push(previous);}
    }
    while(free){owner.set(free.edge.candidate,free.row);assigned.set(free.row,free.edge);free=parent.get(free.row)||null;}
  }
  for(const row of source){
    const match=assigned.get(row);
    if(!match){missing.push({kind:row.kind,index:row.index,identity:row.identity,nearby_outliers:outliers.get(row).slice(0,4).map(c=>({index:c.index,...errors(row.row,c.row)}))});continue;}
    used.add(match.candidate);for(const k of Object.keys(max))max[k]=Math.max(max[k],match.error[k]);
    matches.push({kind:row.kind,expected_index:row.index,actual_index:match.candidate.index,...match.error});
  }
  const extra=received.filter(r=>!used.has(r)).map(r=>({kind:r.kind,index:r.index,identity:r.identity}));
  return {schema:"RSDW.GameDeliveryComparison.v1",status:missing.length||extra.length?"failed":"passed",
    tolerances:{position_cm:1,orientation_degrees:.1,scale_per_component:.001},expected_count:source.length,actual_count:received.length,
    matched_count:matches.length,maximum_matched_errors:max,missing,extra,matches};
}
export function anchorExpectation(document,anchor){
  if(!["x","y","z","yaw_delta"].every(k=>Number.isFinite(anchor[k])))throw Error("Anchor requires finite x/y/z/yaw_delta from the delivery tool");
  const pieces=document.pieces||[],first=pieces.find(p=>p.piece_id===document.anchor_piece_id)||pieces.find(p=>p.piece_data_index===document.anchor_piece_data_index)||pieces[0];
  if(!first)throw Error("Native preview requires a building-piece anchor");
  const expected=structuredClone(document),cos=Math.cos(anchor.yaw_delta*radians),sin=Math.sin(anchor.yaw_delta*radians);
  for(const kind of ["pieces","items","actors"])for(const p of expected[kind]||[]){
    const dx=p.x-first.x,dy=p.y-first.y,dz=p.z-first.z;
    p.x=anchor.x+dx*cos-dy*sin;p.y=anchor.y+dx*sin+dy*cos;p.z=anchor.z+dz;p.yaw+=anchor.yaw_delta;
  }
  return expected;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const {values:args}=parseArgs({options:{expected:{type:"string"},actual:{type:"string"},out:{type:"string"},anchor:{type:"string"}}});
  if(!args.expected||!args.actual||!args.out)throw Error("Pass --expected, --actual and --out");
  let expected=JSON.parse(await readFile(args.expected,"utf8"));
  if(args.anchor)expected=anchorExpectation(expected,JSON.parse(await readFile(args.anchor,"utf8")));
  const result=compareDelivery(expected,JSON.parse(await readFile(args.actual,"utf8")));
  await mkdir(dirname(resolve(args.out)),{recursive:true});await writeFile(args.out,JSON.stringify(result,null,2));
  console.log(`${result.status}: ${result.matched_count}/${result.expected_count} matched; ${result.extra.length} unexpected`);
  if(result.status!=="passed")process.exitCode=1;
}
