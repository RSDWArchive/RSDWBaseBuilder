// Values are source linear RGB. Always assign, never multiply cached GLTF tint again.
export function applySurfaceSettings(material, settings) {
  if(settings.base_color_enabled===false) material.map=null;
  if(settings.normal_enabled===false) material.normalMap=null;
  if(settings.surface_opacity!==undefined && material.transparent) material.opacity=settings.surface_opacity;
  const color=settings.surface_color;
  if(color) material.color.setRGB(...color.multiplier);
  if(settings.surface_pbr) {
    material.roughnessMap=null;material.metalnessMap=null;
    material.roughness=settings.surface_pbr.roughness;
    material.metalness=settings.surface_pbr.metalness;
  }
}

export function surfaceSettingsIssues(material, settings) {
  const issues=[],color=settings.surface_color;
  if(settings.base_color_enabled===false && material.map) issues.push("Source-disabled base-color map is still bound");
  if(settings.normal_enabled===false && material.normalMap) issues.push("Source-disabled normal map is still bound");
  if(settings.surface_opacity!==undefined && material.transparent && Math.abs(material.opacity-settings.surface_opacity)>1e-6)
    issues.push("Source scalar opacity proxy disagrees with descriptor");
  if(color && color.multiplier.some((value,i)=>Math.abs(material.color.toArray()[i]-value)>1e-6))
    issues.push("Source surface RGB tint proxy is not applied exactly once");
  if(settings.surface_pbr) {
    for(const field of ["roughness","metalness"])
      if(material[field+"Map"] || Math.abs(material[field]-settings.surface_pbr[field])>1e-6)
        issues.push("Source surface "+field+" proxy disagrees with descriptor");
  }
  return issues;
}
