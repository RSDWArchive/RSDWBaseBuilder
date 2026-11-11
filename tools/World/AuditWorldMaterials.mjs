import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile, copyFile, access } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";
import { isWhiteCandidate, whiteMaterialReview, summarizeWhiteMaterials } from "./world-white-triage.mjs";

const {values:args}=parseArgs({options:{
  url:{type:"string",default:"http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/index.html?world=1"},
  root:{type:"string",default:"_build/world-region/1.0.0.5/whole-world"},out:{type:"string"},
  chrome:{type:"string"},workers:{type:"string",default:"3"},limit:{type:"string"},assets:{type:"string"},resume:{type:"boolean",default:false},
}});
if(!args.out)throw new Error("Pass --out with an ignored local output folder");
const workers=Number(args.workers);
if(!Number.isInteger(workers)||workers<1||workers>6)throw new Error("Use 1-6 workers");
const require=createRequire(import.meta.url),{chromium}=require("playwright"),sharp=require("sharp");
const output=resolve(args.out),indexBytes=await readFile(resolve(args.root,"VisualAuditIndex.json"));
const index=JSON.parse(indexBytes);
const shared=JSON.parse(await readFile(resolve(args.root,"WorldShared.json"),"utf8"));
const sources=JSON.parse(await readFile(resolve(args.root,"MaterialSources.json"),"utf8"));
const sectionIndex=JSON.parse(await readFile(resolve(args.root,"WorldIndex.json"),"utf8"));
if(sectionIndex.scene_sha256!==index.scene_sha256)throw new Error("World and visual audit indexes differ; finish the rebuild first");
const hash=createHash("sha256").update(indexBytes).update(await readFile(new URL(import.meta.url)));
hash.update(await readFile(new URL("world-white-triage.mjs",import.meta.url)));
for(const file of ["world.js","world-visual-audit.js","world-pixel-metrics.js","world-transforms.js","world-water.js","world-depth.js","world-foam.js","world-surface.js","world.css","index.html",
  ...["world-assets.js","world-transforms.js","world-water.js","world-depth.js","world-foam.js","world-surface.js"].map(name=>"../../../website/world/"+name)])
  hash.update(await readFile(new URL("preview/"+file,import.meta.url)));
const fingerprint=hash.digest("hex");
let variants=index.variants;
if(args.assets)variants=variants.filter(v=>args.assets.split(",").includes(v.asset));
if(args.limit)variants=variants.slice(0,Number(args.limit));
if(!variants.length)throw new Error("No variants selected");
await mkdir(resolve(output,"previews"),{recursive:true});
await copyFile(new URL("audit-gallery.html",import.meta.url),resolve(output,"index.html"));
const report={schema:"RSDW.WorldVisualAudit.v1",fingerprint,scene_sha256:index.scene_sha256,
  started:new Date().toISOString(),status:"running",expected:index.variants.length,requested:variants.length,
  scope:"Isolated effective-material variants; actual shader-alpha masks. In-game visual parity remains manual_review_pending.",variants:[]};
if(args.resume)try {
  const previous=JSON.parse(await readFile(resolve(output,"VisualAudit.json"),"utf8"));
  if(previous.fingerprint===fingerprint)for(const row of previous.variants){
    if(!row.errors.length && variants.some(v=>v.asset===row.asset))try{await access(resolve(output,row.thumbnail));report.variants.push(row);}catch{}
  }
} catch(error){if(error.code!=="ENOENT")throw error;}
const complete=new Set(report.variants.map(v=>v.asset)),pending=variants.filter(v=>!complete.has(v.asset));
let cursor=0,saveQueue=Promise.resolve();
function save(){const content=JSON.stringify(report,null,2);saveQueue=saveQueue.then(()=>writeFile(resolve(output,"VisualAudit.json"),content));return saveQueue;}
const browser=await chromium.launch({headless:true,...(args.chrome?{executablePath:args.chrome}:{})});
const started=performance.now();
try {
  const url=new URL(args.url);url.searchParams.set("world","1");url.searchParams.set("materialAudit","1");
  // Workers are independent browser contexts; generated data and source files remain read-only.
  for(var workerPromises=[],i=0;i<Math.min(workers,pending.length);i++)workerPromises.push((async()=>{
    const context=await browser.newContext({viewport:{width:256,height:256}}),page=await context.newPage();
    let errors=[];
    page.on("pageerror",e=>errors.push(String(e)));
    page.on("console",e=>{if(e.type()==="error")errors.push(e.text());});
    page.on("requestfailed",r=>errors.push(r.url()+": "+r.failure()?.errorText));
    page.on("response",r=>{if(r.status()>=400)errors.push(r.status()+": "+r.url());});
    async function open(){
      await page.goto(url.href);await page.waitForFunction(()=>!!window.worldVisualAudit?.scene_sha256,null,{timeout:120000});
      if(await page.evaluate(()=>worldVisualAudit.scene_sha256)!==index.scene_sha256)throw new Error("Served world and --root audit index fingerprints differ");
    }
    await open();
    while(cursor<pending.length){
      const variant=pending[cursor++],row={...variant};delete row.sample;
      row.bookmark={version:index.version,region:"whole-world",target_cm:variant.sample.bounds[0].map((v,i)=>(v+variant.sample.bounds[1][i])/2)};
      const radius=Math.max(100,Math.hypot(...variant.sample.bounds[0].map((v,i)=>variant.sample.bounds[1][i]-v)));
      row.bookmark.position_cm=row.bookmark.target_cm.map((v,i)=>v+radius*[.8,.8,.9][i]);
      const center=row.bookmark.target_cm;
      row.section=sectionIndex.sections.find(s=>[0,1].every(i=>center[i]>=s.bounds_cm.min[i] && center[i]<s.bounds_cm.max[i]))?.id ||
        sectionIndex.sections.find(s=>[0,1].every(i=>variant.sample.bounds[0][i]<=s.bounds_cm.max[i] && variant.sample.bounds[1][i]>=s.bounds_cm.min[i]))?.id;
      const began=performance.now();
      try {
        const capture=await page.evaluate(v=>window.worldVisualAudit.capture(v),variant);
        const images=capture.views.map(v=>Buffer.from(v.png.split(",")[1],"base64"));
        row.thumbnail="previews/"+variant.asset+".webp";
        await sharp({create:{width:768,height:256,channels:4,background:{r:48,g:59,b:64,alpha:1}}})
          .composite(images.map((input,i)=>({input,left:i*256,top:0}))).webp({quality:85}).toFile(resolve(output,row.thumbnail));
        for(const view of capture.views)delete view.png;
        row.capture=capture;row.flags=[];
        if(capture.views.every(v=>v.coverage<.002))row.flags.push("nearly_invisible_in_all_views");
        if(capture.views.some(v=>v.opaque_pixels>100 && v.white_fraction>.4))row.flags.push("near_white_surface");
        if(capture.views.some(v=>v.opaque_pixels>100 && v.pale_fraction>.65))row.flags.push("pale_low_chroma_surface");
        if(capture.materials.some(m=>m.texture?.opaque_samples>100 && m.texture.deviation<2))row.flags.push("uniform_color_texture");
        if(capture.runtime.adapter_mismatches)errors.push("Supported material adapter mismatch");
        row.errors=[...new Set(errors)];
      } catch(error){row.errors=[...new Set([...errors,String(error)])];await open();}
      row.review_bucket=row.errors.length?"runtime_failure":
        row.source_issues.some(code=>["source_primary_color_mismatch","default_color_texture_review"].includes(code))?"surface_mapping":
        row.source_issues.includes("effect_shader_unreconstructed")?"unreconstructed_effect":
        row.flags?.length?"pixel_review":row.source_issues.length?"source_review":"manual_comparison";
      if(isWhiteCandidate(row))row.white_review=whiteMaterialReview(row,shared.materials,sources);
      row.elapsed_ms=Math.round(performance.now()-began);report.variants.push(row);errors=[];
      if(report.variants.length%50===0 || cursor>=pending.length){
        await save();console.log(`${report.variants.length}/${variants.length} variants, ${Math.round((performance.now()-started)/1000)}s`);
      }
    }
    await context.close();
  })());
  const results=await Promise.allSettled(workerPromises);
  const failures=results.filter(r=>r.status==="rejected");
  if(failures.length)throw new AggregateError(failures.map(r=>r.reason),"Visual audit workers failed");
  report.status=report.variants.some(r=>r.errors.length)?"failed":"completed_pending_manual_review";
  report.summary={variants:report.variants.length,models:new Set(report.variants.map(v=>v.source)).size,
    errors:report.variants.filter(v=>v.errors.length).length,pixel_flags:report.variants.filter(v=>v.flags?.length).length,
    source_flags:report.variants.filter(v=>v.source_issues.length).length,manual_review_pending:report.variants.length};
  if(report.status==="failed")process.exitCode=1;
} catch(error){report.status="failed";report.fatal_error=String(error);process.exitCode=1;}
finally {
  report.finished=new Date().toISOString();report.elapsed_seconds=(performance.now()-started)/1000;
  const priority={runtime_failure:0,surface_mapping:1,pixel_review:2,source_review:3,unreconstructed_effect:4,manual_comparison:5};
  report.variants.sort((a,b)=>priority[a.review_bucket]-priority[b.review_bucket]||b.placements-a.placements);
  await writeFile(resolve(output,"WhiteMaterialReview.json"),JSON.stringify(summarizeWhiteMaterials(report),null,2));
  await save();await browser.close();console.log(report.status,resolve(output,"VisualAudit.json"));
}
