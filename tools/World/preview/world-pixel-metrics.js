export function measurePixels(pixels) {
  let visible=0,opaque=0,white=0,pale=0,sum=0,sq=0;
  for(let i=0;i<pixels.length;i+=4){
    if(pixels[i+3]>8)visible++;
    if(pixels[i+3]<240)continue;
    opaque++;const l=(pixels[i]+pixels[i+1]+pixels[i+2])/3;sum+=l;sq+=l*l;
    const low=Math.min(pixels[i],pixels[i+1],pixels[i+2]),high=Math.max(pixels[i],pixels[i+1],pixels[i+2]);
    if(low>235)white++;
    if(l>200 && high-low<25)pale++;
  }
  return {coverage:visible/(pixels.length/4),opaque_pixels:opaque,white_fraction:opaque?white/opaque:0,
    pale_fraction:opaque?pale/opaque:0,deviation:opaque?Math.sqrt(Math.max(0,sq/opaque-(sum/opaque)**2)):0};
}

// Diagnostic shader writes atlas coverage after tone mapping; alpha masks geometry.
export function measureProjectionCoverage(pixels) {
  let samples=0,covered=0;
  for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>=240){samples++;covered+=pixels[i]/255;}
  return {opaque_pixels:samples,atlas_fraction:samples?covered/samples:null,
    fallback_fraction:samples?1-covered/samples:null};
}
