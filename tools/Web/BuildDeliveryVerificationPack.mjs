import {readFile, writeFile, mkdir} from "node:fs/promises";
import {resolve} from "node:path";
import {createHash} from "node:crypto";
import {parseArgs} from "node:util";
import {createRequire} from "node:module";
import {validateProject} from "../../website/basebuilder-project.js";
import {compareDelivery} from "./VerifyGameDelivery.mjs";

const require=createRequire(import.meta.url);
const {chromium}=require("playwright");

const {values:args}=parseArgs({options:{project:{type:"string",default:"_build/world-builder-m4/acceptance/world-mixed.rsdwproject.json"},out:{type:"string",default:"_build/world-builder-m4/game-verification"}}});
const out=resolve(args.out);await mkdir(out,{recursive:true});
const catalog=JSON.parse(await readFile("website/basebuilder-index.json","utf8")),project=validateProject(JSON.parse(await readFile(args.project,"utf8")),catalog);
const targets=new Map(catalog.targets.map(t=>[t.target_id,t])),sha=data=>createHash("sha256").update(data).digest("hex");
const original=project.build.placements.find(p=>!p.hidden),base=original.state;
const chosen=["085_DA_T1_Foundation_Medium","072_DA_T3_Wall_Large_Special_Windowed_1","324_DA_T3_Type2_Floor_Medium","007_DA_T2_Roof_Medium_Diagonal"].map(id=>targets.get(id));
chosen.push(catalog.targets.find(t=>t.asset_kind==="building_piece"&&t.catalog_path.includes("Crafting Stations")),
  catalog.targets.find(t=>t.asset_kind==="item"&&t.asset_stem.includes("Stone")),
  catalog.targets.find(t=>t.asset_kind==="bp"&&/OreNode.*Stone/i.test(t.asset_stem))||catalog.targets.find(t=>t.asset_stem==="BP_NPC_HighLightingTheProblem_Statue_C"));
if(chosen.some(t=>!t))throw Error("Verification fixture target unavailable");
project.project_id="milestone-4-delivery-fixture";project.revision=0;project.delivery.preferred_mode="saved_world_location";
project.build.build_name="Milestone 4 delivery verification";
project.build.placements=chosen.map((target,i)=>({id:`obj_${i+1}`,target_id:target.target_id,
  state:{x:base.x+(i%3)*600,y:base.y+Math.floor(i/3)*600,z:base.z,
    pitch:i>=5?12:0,yaw:i*15,roll:i>=5?-9:0,scale_x:1,scale_y:i>=4?.9:1,scale_z:i>=4?1.1:1},
  metadata:target.asset_kind==="building_piece"?{piece_id:i+1}:{item_count:2},hidden:false,ui_collection_id:"collection_1"}));
project.build.ui_collections=[{id:"collection_1",name:"Delivery verification",order:0,collapsed:false}];project.build.selected_ids=[];
project.build.anchor_piece_id=1;project.build.next_piece_id=8;project.build.next_object_id=8;project.build.next_ui_collection_id=2;
async function generate(p){
  const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});
  try{
    const page=await browser.newPage();
    await page.route("**/delivery-verification.html",r=>r.fulfill({contentType:"text/html",body:'<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.184.0/build/three.module.js"}}</script>'}));
    await page.goto("http://127.0.0.1:8765/RSDWBaseBuilder/website/delivery-verification.html");
    return await page.evaluate(async({project,targets})=>{
      const {serializeBuildingJson}=await import("./basebuilder-serialization.js"),lookup=new Map(targets.map(t=>[t.target_id,t]));
      return serializeBuildingJson({placements:new Map(project.build.placements.map(row=>[row.id,{...row,target:lookup.get(row.target_id)}])),
        buildSchema:project.build.build_schema,buildName:project.build.build_name,anchorPieceId:project.build.anchor_piece_id,allocatePieceId:()=>{throw Error("Unexpected ID allocation");}},0);
    },{project:p,targets:chosen});
  }finally{await browser.close();}
}
const checks=[];
for(const [name,p]of [["world-location",project],["below-zero",structuredClone(project)]]){
  if(name==="below-zero"){for(const row of p.build.placements){row.state.x+=3000;row.state.y+=3000;row.state.z=-1000;}p.build.build_name+=" below-zero mathematical check";}
  validateProject(p,catalog);const json=await generate(p),data=JSON.stringify(json,null,2)+"\n";
  await writeFile(resolve(out,name+".json"),data);await writeFile(resolve(out,name+".rsdwproject.json"),JSON.stringify(p,null,2));
  checks.push({name,sha256:sha(data),count:json.pieces.length+json.items.length+json.actors.length,
    browser_location_verified:name==="world-location",in_game_status:"pending_in_game",self_comparison:compareDelivery(json,json).status});
}
const sourceRoot="E:/Github/RSDToolsWorkspace/RSDWTools/Mods/RSDWTools/scripts/",installedRoot="F:/SteamLibrary/steamapps/common/RSDragonwilds/RSDragonwilds/Binaries/Win64/ue4ss/Mods/RSDWTools/scripts/";
const consumer=[];for(const file of ["feature_buildings.lua","feature_build_preview.lua"]){let source=null,installed=null;try{source=sha(await readFile(sourceRoot+file));}catch{}try{installed=sha(await readFile(installedRoot+file));}catch{}consumer.push({file,source_path:sourceRoot+file,installed_path:installedRoot+file,source_sha256:source,installed_sha256:installed,matching:!!source&&source===installed});}
const report={schema:"RSDW.DeliveryVerificationPack.v1",status:"pending_in_game",prepared_at:new Date().toISOString(),
  dataset:project.dataset,actual_game_version:null,tool_app_version:null,level_identity:null,consumer,fixtures:checks,
  required_runs:["known-game-capture unchanged round trip","saved location delivery and actor-root capture","game save/reload recapture","anchor delivery at different position/yaw","large samples one at a time after paced queue completion"],
  limitations:["Game was unavailable during preparation; browser correctness is not in-game acceptance.","Below-zero fixture is a mathematical transform fixture; select a safe below-zero in-game location before delivery.","Item physics, unsupported piece tilt/scale, native level context and tool versions require manual verification.","Use isolated backed-up save and fixture-only captures; do not deliver both test fixtures at once."]};
await writeFile(resolve(out,"Verification.json"),JSON.stringify(report,null,2));
await writeFile(resolve(out,"README.md"),`# Milestone 4 In-Game Verification\n\nStatus: pending_in_game. No game delivery has been performed.\n\n1. Back up a disposable test save. Verify game/catalog ${catalog.version}, companion tool version and level identity. Script hashes are in Verification.json; resolve mismatches before testing.\n2. Open world-location.rsdwproject.json in the local builder. Review its terrain/location and export Saved World Location. In RSDWTools use **Deliver Build**, not Deliver via Preview. Wait for the entire queue to finish.\n3. Capture only these spawned pieces/items/actors using the tools. Save the complete actor-root capture as actual-delivery.json. Run the comparison below. Runtime IDs may differ.\n4. Save/reload the game, recapture as actual-reloaded.json and compare again. Check initial capture against recapture too.\n5. Deliver at a second safe location/elevation. below-zero.json tests numeric transforms only: choose a real safe below-zero landmark first.\n6. Test Place Using Anchor via **Deliver via Preview** at another position/yaw. Its source is unchanged JSON. Obtain the tool's actual anchor location and yaw delta, then compare against the rigidly transformed expectations. Do not compare relocated actors to the original coordinates.\n7. Repeat with Grand_Exchange.json and Looter_Paradise_3.json, one at a time; wait for all actors, not merely request acceptance. Their capture game versions are unknown.\n\nComparison:\n\n\x60\x60\x60powershell\nnode tools/Web/VerifyGameDelivery.mjs --expected _build/world-builder-m4/game-verification/world-location.json --actual _build/world-builder-m4/game-verification/actual-delivery.json --out _build/world-builder-m4/game-verification/initial-comparison.json\n\x60\x60\x60\n\nRepeat using actual-reloaded.json. Passing requires every class/data asset to match one-to-one, position <=1 cm, equivalent orientation <=0.1 degree, scale <=0.001. Missing/extra actors or incomplete transform captures fail. Capture before item physics/NPC motion alters placement, and separately annotate native limitations. Screenshots alone are insufficient.\n\nRecord spawned actors and remove only this test content between runs. Never clean up the user's normal builds. Fill in actual game/tool versions, level, captures, queue results and reports in Verification.json before declaring accepted.\n`);
await writeFile(resolve(out,"AnchorGuide.md"),`# Native Anchor Comparison\n\nUse Deliver via Preview with the unchanged world-location.json. Capture the actual placed native anchor actor root. Obtain the yaw delta as actual anchor yaw minus source anchor yaw (the source selected by anchor_piece_id, then anchor_piece_data_index, then the first piece). Do not use rounded console log values for large builds.\n\nSave anchor.json with numeric x, y, z and yaw_delta. These must be the real native anchor/delta, not browser preview values. Then run:\n\n\x60\x60\x60powershell\nnode tools/Web/VerifyGameDelivery.mjs --expected _build/world-builder-m4/game-verification/world-location.json --anchor _build/world-builder-m4/game-verification/anchor.json --actual _build/world-builder-m4/game-verification/actual-anchor-delivery.json --out _build/world-builder-m4/game-verification/anchor-comparison.json\n\x60\x60\x60\n\nThe expectation mirrors the consumer's rigid XY rotation and XYZ relocation, adds the yaw delta, and preserves pitch/roll/scale. The native first anchor itself is placed by the engine; use the upright unscaled foundation fixture. Any unsupported native anchor transform must be annotated rather than hidden by changing the browser exporter.\n`);
console.log(`Prepared ${out}; ${consumer.filter(c=>!c.matching).length} consumer script mismatches; live acceptance pending`);
