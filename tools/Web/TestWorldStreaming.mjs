import assert from "node:assert/strict";
import {readFile,access} from "node:fs/promises";
import {resolve} from "node:path";
import {createHash} from "node:crypto";
import {planSections,sectionFocus,createLeaseCache,createJobPool,detailViewSpan} from "../../website/world/world-streaming.js";
import {projectNavigation,validateProject} from "../../website/basebuilder-project.js";

const root=resolve("_build/world-region/1.0.0.5/whole-world"),read=async path=>JSON.parse(await readFile(resolve(root,path),"utf8"));
const index=await read("WorldIndex.json"),shared=await read("WorldShared.json"),spanning=await read(index.spanning);
const assetIds=new Set(shared.assets.map(a=>a.id)),ids=new Map(),terrainIds=new Set(),spanIds=new Set(spanning.map(p=>p.id));
let placements=0,overlapReferences=0;
for(const section of index.sections) {
  const focus=sectionFocus(section,shared.overview),plan=planSections({sections:index.sections,focus,destination:section.id});
  assert.equal(plan.desired[0],section.id);assert.ok(plan.desired.length<=4);assert.ok(focus.every(Number.isFinite));
  assert.ok(focus[0]>=section.bounds_cm.min[0]&&focus[0]<=section.bounds_cm.max[0]);
  assert.ok(focus[1]>=section.bounds_cm.min[1]&&focus[1]<=section.bounds_cm.max[1]);
  const part=await read(section.path);
  for(const p of part.placements){assert.ok(assetIds.has(p.asset));assert.ok(!spanIds.has(p.id));
    const hash=createHash("sha256").update(JSON.stringify(p)).digest("hex");if(ids.has(p.id)){assert.equal(hash,ids.get(p.id),"Inconsistent shared placement "+p.id);overlapReferences++;}
    else {ids.set(p.id,hash);placements++;}}
  for(const tile of part.terrain){terrainIds.add(tile.source);await access(resolve(root,tile.path));}
}
for(const tile of shared.overview){assert.ok(terrainIds.has(tile.source));await access(resolve(root,tile.overview_path));}
assert.equal(placements+spanning.length,index.unique_placements);
const sample=index.sections.find(s=>s.id==="x3_y1"),focus=sectionFocus(sample,shared.overview);
assert.deepEqual(planSections({sections:index.sections,focus,area:"unavailable"}).desired,[]);
assert.equal(detailViewSpan({isOrthographicCamera:true,top:10,bottom:-10,zoom:2},999),10);
assert.ok(detailViewSpan({isOrthographicCamera:false,fov:60,zoom:1},100)>100);
const cache=createLeaseCache();let loads=0,disposed=0;
const create=async()=>{loads++;return {};},dispose=()=>disposed++;
const [a,b]=await Promise.all([cache.acquire("model","a",create,dispose),cache.acquire("model","b",create,dispose)]);
assert.equal(a,b);assert.equal(loads,1);cache.release("a");assert.equal(disposed,0);cache.release("b");assert.equal(disposed,1);
let finish;const pending=cache.acquire("late","owner",()=>new Promise(r=>finish=r),dispose);
await Promise.resolve();cache.release("owner");finish({});await pending;assert.equal(disposed,2);
await assert.rejects(cache.acquire("fail","owner",()=>Promise.reject(Error("test")),dispose));
await cache.acquire("fail","owner",create,dispose);cache.release("owner");assert.equal(disposed,3);
const pool=createJobPool(3);let running=0,peak=0;
await Promise.all(Array.from({length:20},()=>pool.run(async()=>{running++;peak=Math.max(peak,running);await new Promise(r=>setTimeout(r,1));running--;})));
assert.equal(peak,3);
const project=JSON.parse(await readFile("_build/world-builder-m1/acceptance-final/manual-review.rsdwproject.json","utf8"));
const catalog=JSON.parse(await readFile("website/basebuilder-index.json","utf8"));
assert.equal(projectNavigation(project.workspace).mode,"build");validateProject(project,catalog);
project.workspace.navigation=projectNavigation(project.workspace);validateProject(project,catalog);
for(const mutate of [n=>n.mode="bad",n=>n.focus_cm=[0,NaN,0],n=>n.streaming_enabled=1,n=>n.last_build_camera={},n=>n.area_filter=null]) {
  const bad=structuredClone(project);mutate(bad.workspace.navigation);assert.throws(()=>validateProject(bad,catalog));
}
console.log(JSON.stringify({sections:index.sections.length,placements:placements+spanning.length,terrain:terrainIds.size,
  overview:shared.overview.length,overlapReferences,planner:true,cache_leases:true,late_decode_disposal:true,retry:true,concurrency:true,old_project:true,new_project_validation:true},null,2));
