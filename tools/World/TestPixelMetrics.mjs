import assert from "node:assert/strict";
import { measurePixels, measureProjectionCoverage } from "./preview/world-pixel-metrics.js";

const result=measurePixels(new Uint8Array([255,255,255,0, 245,245,245,255, 210,210,210,255, 255,0,0,255, 255,255,255,64]));
assert.equal(result.coverage,.8);
assert.equal(result.opaque_pixels,3);
assert.equal(result.white_fraction,1/3);
assert.equal(result.pale_fraction,2/3);
assert.equal(measurePixels(new Uint8Array([0,0,0,0])).white_fraction,0);
assert.equal(measurePixels(new Uint8Array([186,186,186,255,186,186,186,255])).deviation,0);
assert.deepEqual(measureProjectionCoverage(new Uint8Array([255,255,255,0])),
  {opaque_pixels:0,atlas_fraction:null,fallback_fraction:null});
assert.deepEqual(measureProjectionCoverage(new Uint8Array([255,255,255,255,0,0,0,255,255,255,255,0])),
  {opaque_pixels:2,atlas_fraction:.5,fallback_fraction:.5});
console.log("Pixel metrics: transparent background/effects excluded; opaque white, pale and color samples pass");
