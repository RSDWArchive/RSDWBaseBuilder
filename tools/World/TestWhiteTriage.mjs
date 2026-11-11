import assert from "node:assert/strict";
import { isWhiteCandidate, whiteMaterialReview, summarizeWhiteMaterials } from "./world-white-triage.mjs";
assert.equal(isWhiteCandidate({flags:["nearly_invisible_in_all_views"]}),false);
assert.equal(isWhiteCandidate({flags:["near_white_surface"]}),true);
const row={asset:"a",source:"Mesh",materials:["M"],flags:["pale_low_chroma_surface"],capture:{views:[{
  landscape_projection:{opaque_pixels:10,atlas_fraction:.2,fallback_fraction:.8}}]}};
const review=whiteMaterialReview(row,{M:{projection:"landscape_color"}},{});
assert.deepEqual(review.categories,["terrain_projection_and_deformation"]);
assert.equal(review.landscape_projection_views[0].fallback_fraction,.8);
assert.equal(review.review_status,"manual_review_pending");
assert.deepEqual(whiteMaterialReview(row,{}, {M:{master:"M_ShellFur.0",switches:{"UseTexture?":false}}}).categories,["disabled_texture_branch"]);
assert.deepEqual(whiteMaterialReview(row,{M:{textures:{base_color:"p.webp"}}},{}).categories,["textured_surface_comparison"]);
assert.deepEqual(whiteMaterialReview({...row,materials:[""]},{},{}).categories,["unassigned_source_slot"]);
const summary=summarizeWhiteMaterials({status:"completed_pending_manual_review",variants:[{...row,white_review:review}]});
assert.equal(summary.summary.variants,1);assert.equal(summary.summary.models,1);
console.log("White triage: all candidate categories remain manual; invisible-only rows are separate");
