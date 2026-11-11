import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({ options: {
  url: { type: "string", default: "http://127.0.0.1:8765/RSDWBaseBuilder/tools/World/preview/index.html?world=1" },
  out: { type: "string" }, chrome: { type: "string" },
  sections: { type: "string" }, resume: { type: "boolean", default: false },
} });
if (!args.out) throw new Error("Pass --out with an ignored local audit directory");
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const output = resolve(args.out);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(args.chrome ? { executablePath: args.chrome } : {}) });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
let errors = [];
page.on("pageerror", e => errors.push(String(e)));
page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
page.on("requestfailed", request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
page.on("response", response => { if (response.status() >= 400) errors.push(`${response.status()}: ${response.url()}`); });
const report = { schema: "RSDW.WorldBrowserAudit.v1", started: new Date().toISOString(), status: "running",
  scope: "Area-group and section render/load checks, not approval of in-game visual parity", groups: [], sections: [] };
const reportPath = resolve(output, "BrowserAudit.json");
async function save() { await writeFile(reportPath, JSON.stringify(report, null, 2)); }
async function open() {
  await page.goto(args.url);
  await page.waitForFunction(() => window.worldRegionDebug?.metrics().ready, null, { timeout: 120000 });
}
try {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await open();
  report.scene_sha256 = await page.evaluate(() => worldRegionDebug.worldBrowser.index.scene_sha256);
  const expectedModels = await page.evaluate(() => [...new Set(worldRegionDebug.data.assets.map(a => a.source))]);
  const hash = createHash("sha256");
  for (const file of ["world.js", "world-browser.js", "world-section-markers.js", "world-visual-audit.js", "world-pixel-metrics.js", "world-transforms.js", "world-water.js", "world-depth.js", "world-foam.js", "world-surface.js", "world.css", "index.html",
    ...["world-assets.js", "world-transforms.js", "world-water.js", "world-depth.js", "world-foam.js", "world-surface.js"].map(name => "../../../website/world/" + name)]) {
    const response = await fetch(new URL(file, args.url));
    if (!response.ok) throw new Error(`Cannot fingerprint ${file}: ${response.status}`);
    hash.update(await response.text());
  }
  report.viewer_sha256 = hash.digest("hex");
  report.audit_sha256 = createHash("sha256").update(await readFile(new URL(import.meta.url))).digest("hex");
  report.startup_errors = errors;
  if (args.resume) {
    try {
      const previous = JSON.parse(await readFile(reportPath, "utf8"));
      if (previous.scene_sha256 === report.scene_sha256 && previous.viewer_sha256 === report.viewer_sha256 &&
          previous.audit_sha256 === report.audit_sha256) {
        report.sections = previous.sections.filter(row => row.status === "passed" && Array.isArray(row.loaded_models));
      }
    } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  let sections = await page.evaluate(() => worldRegionDebug.worldBrowser.index.sections);
  if (args.sections) sections = sections.filter(row => args.sections.split(",").includes(row.id));
  if (!sections.length) throw new Error("No requested sections exist in this world index");
  report.sections = report.sections.filter(row => sections.some(section => section.id === row.id));
  report.requested_sections = sections.length;
  if (!args.sections) {
    const biomes=await page.locator('#world-biome option').evaluateAll(options=>options.map(o=>o.value));
    for(const biome of biomes) {
      errors=[];
      await page.locator('#world-biome').selectOption(biome);
      await page.locator('#world-load').click();
      await page.waitForFunction(()=>!document.querySelector('#world-load').disabled,null,{timeout:120000});
      const row=await page.evaluate(biome=>{
        const d=worldRegionDebug,rows=d.worldBrowser.index.sections.filter(r=>biome==='all'||r.biome===biome);
        return {biome,metrics:d.worldBrowser.metrics(),placements:d.data.placements.length,
          no_landscape:rows.every(r=>!r.terrain),visible_expected:rows.some(r=>(r.visible_placements??r.placements)>0)};
      },biome);
      row.errors=[...errors];
      if(row.no_landscape && row.visible_expected && !row.placements)row.errors.push('Non-terrain group opened without visible content');
      if(!row.placements && !row.metrics.markers)row.errors.push('Overview has no detail or section navigation');
      row.screenshot='group-'+biome.replaceAll(' ','-')+'.png';
      await page.screenshot({path:resolve(output,row.screenshot)});
      await page.locator('#world-overview').click();
      await page.waitForFunction(()=>!worldRegionDebug.worldBrowser.metrics().busy);
      row.overview=await page.evaluate(()=>worldRegionDebug.worldBrowser.metrics());
      if(row.overview.sections>1 && !row.overview.markers)row.errors.push('Area overview has no section markers');
      row.status=row.errors.length?'failed':'passed';report.groups.push(row);await save();
      console.log(`Group ${biome}: ${row.status}`);
    }
  }
  for (const section of sections) {
    if (report.sections.some(row => row.id === section.id)) continue;
    errors = [];
    const started = performance.now();
    const row = { id: section.id, name: section.name, source_placements: section.placements, status: "failed" };
    try {
      await page.evaluate(id => worldRegionDebug.worldBrowser.load(id), section.id);
      row.load_ms = Math.round(performance.now() - started);
      Object.assign(row, await page.evaluate(() => {
        const d = worldRegionDebug, audit = d.auditMaterials();
        d.render();
        // Read immediately after rendering; preserved drawing buffers are not needed.
        const gl = d.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
        const pixels = new Uint8Array(w * h * 4);
        gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        const colors = new Set(); let white = 0, samples = 0;
        for (let i = 0; i < pixels.length; i += 4 * 97) {
          colors.add(`${pixels[i] >> 3},${pixels[i + 1] >> 3},${pixels[i + 2] >> 3}`);
          white += pixels[i] > 235 && pixels[i + 1] > 235 && pixels[i + 2] > 235; samples++;
        }
        const activeAssets = new Set(d.data.placements.map(p => p.asset));
        return { loaded_placements: d.data.placements.length, metrics: d.metrics(),
          hud_overflow: [...document.querySelectorAll(".toolbar button,.toolbar select,.toolbar label")].some(e => {
            const r = e.getBoundingClientRect(); return e.getClientRects().length && (r.left < -1 || r.right > innerWidth + 1);
          }),
          loaded_models: [...new Set(d.data.assets.filter(a => activeAssets.has(a.id)).map(a => a.source))],
          checked_mesh_sections: audit.checked_sections,
          adapter_mismatches: audit.materials.filter(m => m.status === "mapping_mismatch"),
          runtime_review: audit.materials.filter(m => m.status === "needs_review"),
          canvas: { quantized_colors: colors.size, near_white_fraction: white / samples } };
      }));
      row.screenshot = section.id + ".png";
      await page.screenshot({ path: resolve(output, row.screenshot) });
      row.errors = [...new Set([...errors, ...row.metrics.errors])];
      if (row.loaded_placements < row.source_placements) row.errors.push("The selected section did not load all of its placements");
      if (row.hud_overflow) row.errors.push("Viewport toolbar controls extend outside the viewport");
      row.warnings = [];
      if (row.canvas.quantized_colors < 3) row.warnings.push("Uniform canvas: inspect framing or intentionally empty/helper-only section");
      if (row.canvas.near_white_fraction > 0.8) row.warnings.push("Mostly near-white: inspect source materials; not automatic evidence of missing textures");
      if (!row.errors.length && !row.adapter_mismatches.length) row.status = "passed";
    } catch (error) {
      row.errors = [...new Set([...errors, String(error)])];
      await open();
    }
    report.sections.push(row);
    await save();
    console.log(`${report.sections.length}/${sections.length} ${row.id}: ${row.status} ${row.load_ms ?? 0}ms, ${row.loaded_placements ?? 0} placements`);
  }
  report.finished = new Date().toISOString();
  const loadedModels = new Set(report.sections.flatMap(row => row.loaded_models ?? []));
  report.models = { expected: expectedModels.length, loaded: loadedModels.size,
    missing: expectedModels.filter(model => !loadedModels.has(model)) };
  report.status = report.startup_errors.length || report.groups.some(row=>row.status!=="passed") || report.sections.some(row => row.status !== "passed") ||
    (!args.sections && report.models.missing.length) ? "failed" : "passed";
  await save();
  console.log(`${report.status}: ${reportPath}`);
  if (report.status !== "passed") process.exitCode = 1;
} catch (error) {
  report.status = "failed";
  report.finished = new Date().toISOString();
  report.fatal_error = String(error);
  await save();
  throw error;
} finally {
  await browser.close();
}
