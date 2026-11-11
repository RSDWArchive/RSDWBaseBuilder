export function isWhiteCandidate(row) {
  return row.flags?.some(flag => ["near_white_surface", "pale_low_chroma_surface", "uniform_color_texture"].includes(flag)) ?? false;
}

export function whiteMaterialReview(row, materials, sources) {
  const evidence=(row.materials ?? []).map(ref=>{
    const descriptor=materials[ref] ?? {},source=sources[ref] ?? {};
    const master=(source.master ?? descriptor.master ?? "").split("/").at(-1).split(".")[0];
    let category="shader_reference_required",reason="Source shader connections remain unreconstructed; inspect the named parameters before assigning textures or colors.";
    if(!ref){category="unassigned_source_slot";reason="Source mesh and component both have no material assigned. A replacement cannot be inferred from white pixels.";}
    else if(descriptor.projection==="landscape_color"){
      category="terrain_projection_and_deformation";
      reason="Atlas is bound. Inspect measured atlas/fallback coverage and the source dune skirt/deformation before changing its pale fallback.";
    } else if(["M_SW_Crystals","M_SW_CrystalsFade"].includes(master)){
      category="crystal_base_proxy";
      reason="Source Base color/normal/PBR only. Packed color masks, gradient, bright tips, subsurface and fading still require in-game comparison.";
    } else if(master==="M_ShellFur" && source.switches?.["UseTexture?"]===false){
      category="disabled_texture_branch";
      reason="The source explicitly disables its base texture. The MixColor-only proxy omits shell masks and overlay math; do not attach the inactive Ram texture.";
    } else if(master==="M_Standard_MR_Notex"){
      category="constant_color_source";
      reason="Source uses a constant BaseColor and PBR scalars, not a diffuse image. Pale/metallic appearance is not automatically a defect or approval.";
    } else if(row.layer==="helpers"){
      category="helper_geometry";
      reason="This is classified helper/blockout geometry. Debug shader colors can be unreconstructed; hidden by default is not the same as verified against the game.";
    } else if(descriptor.settings?.base_color_parameter && !descriptor.textures?.base_color){
      category="source_color_proxy";
      reason="Named source "+descriptor.settings.base_color_parameter+" is used as a limited color proxy. "+(descriptor.settings.approximation??"Compare the missing shader layers and lighting in-game.");
    } else if(descriptor.settings?.family==="surface_maps" && descriptor.textures?.base_color){
      category="textured_surface_comparison";
      reason="The supported surface adapter binds a recovered base-color image. Compare its color, packed channels and lighting in-game; a pale pixel is not proof of a missing image.";
    } else if(/VFX|Anima|Ghost|Glass|Flowmap|Disabled/.test(master)){
      category="effect_or_transmission";
      reason="Effect/transmission shading can render white in a static proxy. Compare opacity, emission, reflection, animation and source context; do not substitute an arbitrary diffuse map.";
    } else if(descriptor.textures?.base_color){
      category="textured_surface_comparison";
      reason="A recovered base-color image is bound. Verify pale source pixels, brightness, tint, packed channels and lighting rather than assuming the texture is absent.";
    }
    return {material:ref,master,category,reason,source_texture_parameters:Object.keys(source.textures ?? {}),
      recovered_roles:Object.keys(descriptor.textures ?? {}),source_base:source.vectors?.Base ?? source.vectors?.BaseColor ?? null,
      review_status:"manual_review_pending"};
  });
  const coverage=(row.capture?.views ?? []).map(v=>v.landscape_projection).filter(Boolean);
  return {categories:[...new Set(evidence.map(e=>e.category))],materials:evidence,
    ...(coverage.length?{landscape_projection_views:coverage}:{}),review_status:"manual_review_pending"};
}

export function summarizeWhiteMaterials(report) {
  const variants=report.variants.filter(isWhiteCandidate).map(row=>({asset:row.asset,source:row.source,
    section:row.section,placements:row.placements,flags:row.flags,errors:row.errors,thumbnail:row.thumbnail,
    bookmark:row.bookmark,review:row.white_review}));
  const categories={};
  for(const row of variants)for(const category of row.review.categories)categories[category]=(categories[category]??0)+1;
  return {schema:"RSDW.WorldWhiteMaterialReview.v1",fingerprint:report.fingerprint,scene_sha256:report.scene_sha256,
    status:report.status,scope:"Every white/pale/uniform-texture candidate in this audit. Categories can overlap; no automatic approval or recoloring.",
    summary:{variants:variants.length,models:new Set(variants.map(v=>v.source)).size,categories},variants};
}
