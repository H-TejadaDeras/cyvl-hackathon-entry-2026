export const meta = {
  name: 'curbrisk-preflight',
  description: 'Parallel bug-review of the unrun CurbRisk modules before the autonomous build',
  phases: [
    { title: 'Review' },
    { title: 'Synthesize' },
  ],
}

const REPO = 'C:/Users/marut/OneDrive/Desktop/projects/cyvl_hack'

const FINDINGS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    module: { type: 'string' },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          severity: { type: 'string', enum: ['blocker', 'high', 'medium', 'low'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['severity', 'title', 'detail', 'fix'],
      },
    },
  },
  required: ['module', 'issues'],
}

const TARGETS = [
  { mod: 'curbrisk/ingest/opendata.py', note: 'KNOWN BUG: queries Somerville 311 dataset sxulr-rmsq filtering on case_title/latitude/longitude; the correct dataset is 4pyi-uqq6 which has block_code (15-digit Census block GEOID) and NO lat/lon. Real data is already downloaded at data/somerville_drainage/*.geojson (66 catch_basins, 577 storm_inlets, catch_basin_laterals, sw_gravity_mains with UPELEV/DOWNELEV/SLOPE) and data/somerville_311/drainage_pavement_311.csv (26,994 rows). This module should be rewired to read those instead of stale endpoints + 2-point sample fallbacks. Report exactly what risk.py expects it to output (flood_complaints.geojson, storm_drains.geojson) and any mismatch.' },
  { mod: 'curbrisk/scoring/risk.py', note: 'Composite CurbRisk = topo40 + pavement30 + basin20 + complaint10. Check exactly which input files/columns it reads, whether it crashes on empty complaints/drains, and that it writes data/processed/curbrisk_scores.geojson + scores.db.' },
  { mod: 'curbrisk/scoring/topo.py', note: 'Already ran OK (produced low_points.geojson, segments_elev.geojson). Flag only correctness issues that would corrupt downstream scores.' },
  { mod: 'curbrisk/output/crosssection.py', note: 'ezdxf DXF + SVG per low point. Report exactly which scoring outputs it needs and any path/schema mismatch.' },
  { mod: 'curbrisk/output/aps_upload.py', note: 'APS 2-legged OAuth + OSS bucket upload + Model Derivative translate to SVF2. Check env-var usage (APS_CLIENT_ID/SECRET/BUCKET) and that it does not silently fall back to SVG when creds ARE present.' },
  { mod: 'curbrisk/api/main.py', note: 'FastAPI GET /risk: Nominatim geocode -> nearest segment in scores.db. Check it hard-depends on scores.db existing and the <10s path; flag any startup crash if the DB is missing.' },
]

phase('Review')
const reviews = await parallel(TARGETS.map(t => () =>
  agent(
    `Review a Python module in the CurbRisk pipeline at ${REPO}. ` +
    `Read ${t.mod} plus anything it imports (especially curbrisk/config.py). ` +
    `Report only concrete bugs or integration mismatches that would break an autonomous end-to-end run via \`python -m curbrisk.run_pipeline\` using the REAL downloaded data. ` +
    `Prioritise: wrong file paths, column/schema mismatches against the real data, missing inputs, crash-on-empty. ` +
    `Context: ${t.note} ` +
    `Set "module" to "${t.mod}". Give each issue a specific one-line fix.`,
    { label: `review:${t.mod.split('/').pop()}`, phase: 'Review', schema: FINDINGS }
  )
))

phase('Synthesize')
const flat = reviews.filter(Boolean).flatMap(r => (r.issues || []).map(i => ({ module: r.module, ...i })))
const punchlist = await agent(
  `Review findings across the CurbRisk pipeline (JSON):\n${JSON.stringify(flat, null, 2)}\n\n` +
  `Produce a prioritised, de-duplicated punch list (blockers first) that an autonomous coding agent should fix IN ORDER to get \`python -m curbrisk.run_pipeline\` and the FastAPI /risk endpoint working end-to-end with the real downloaded Somerville data. Concise, concrete, numbered.`,
  { label: 'synthesize', phase: 'Synthesize' }
)
return { issueCount: flat.length, punchlist, raw: flat }
