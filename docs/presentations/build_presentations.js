#!/usr/bin/env node
/*
 * Regenerates the two DAGonStar slide decks in this directory:
 *
 *   dagonstar_scientific_talk.pptx   20-minute workshop/conference talk
 *   dagonstar_tutorial.pptx          20-minute build/install/configure/test/evaluate tutorial
 *
 * Usage (from the repository root):
 *
 *   npm install --no-save pptxgenjs@3.12.0
 *   node docs/presentations/build_presentations.js
 *
 * The figures quoted on the slides are collected in EVIDENCE below. Each one
 * was observed by running the command named next to it on a checkout of this
 * repository; update them (and the "observed on" note) when you re-measure.
 */
"use strict";
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");
const JSZip = require("jszip"); // installed with pptxgenjs


const OUT_DIR = __dirname;

// ---------------------------------------------------------------------------
// Observed evidence (re-measure before presenting a new release).
// ---------------------------------------------------------------------------
const EVIDENCE = {
  version: "2.9.4",                       // setup.cfg [metadata] version
  observedOn: "macOS, Python 3.12.10, November 2026",
  unitTests: 383,            // python -m unittest discover -s tests
  unitTestSeconds: "328.682",
  unitTestSkipped: "0",
  unitTestMinutes: "5.5",    // wall-clock of the full suite
  localExamples: 46,    // python tools/run_local_examples.py
  localExamplesMinutes: "4",
  taskTypes: 14,                          // dagon.task.TaskType
  lessons: 36,                            // docs/tutorial lessons 00-35
  testModules: 45,                        // files in tests/ (modules + helpers)
  firstWorkflowSeconds: "4.9",            // getting-started workflow, two tasks
};

// ---------------------------------------------------------------------------
// Palette and typography: deep-sea ink with a single amber "star" accent.
// ---------------------------------------------------------------------------
const P = {
  deep: "0B2E33", ink: "14262B", teal: "1F6F78", sea: "4F9DA6", seaLight: "CFE6E8",
  foam: "E8F2F3", mist: "F4F8F8", amber: "F2A541", coral: "C8553D", muted: "5B6B73",
  white: "FFFFFF", code: "10201F", codeText: "DDEFF0", okFill: "E7F4EC", ok: "2E7D4F",
  line: "C9DCDF",
};
const HEAD = "Cambria";
const BODY = "Calibri";
const MONO = "Courier New";

function newDeck(title, footer) {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
  pres.author = "DAGonStar project";
  pres.company = "DAGonStar";
  pres.title = title;
  pres.theme = { headFontFace: HEAD, bodyFontFace: BODY };

  pres.defineSlideMaster({
    title: "Title (dark)",
    background: { color: P.deep },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.25, w: 6.0, h: 1.9,
        fontFace: HEAD, fontSize: 32, bold: true, color: P.white, valign: "bottom", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.3, w: 6.0, h: 0.9,
        fontFace: BODY, fontSize: 16, color: P.seaLight, valign: "top", margin: 0 }, text: "" } },
    ],
  });
  pres.defineSlideMaster({
    title: "Content",
    background: { color: P.white },
    margin: [0.3, 0.5, 0.5, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.28, w: 9.0, h: 0.75,
        fontFace: HEAD, fontSize: 28, bold: true, color: P.deep, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: footer, options: { x: 0.5, y: 5.2, w: 7.0, h: 0.3, fontFace: BODY, fontSize: 10,
        color: P.muted, margin: 0 } } },
    ],
    slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.3, fontFace: BODY, fontSize: 10, color: P.muted, align: "right" },
  });
  pres.defineSlideMaster({
    title: "Closing (dark)",
    background: { color: P.deep },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 8.8, h: 0.8,
        fontFace: HEAD, fontSize: 30, bold: true, color: P.white, valign: "middle", margin: 0 }, text: "" } },
    ],
    slideNumber: { x: 9.0, y: 5.2, w: 0.5, h: 0.3, fontFace: BODY, fontSize: 10, color: P.seaLight, align: "right" },
  });
  return pres;
}

// ---------------------------------------------------------------------------
// Drawing helpers. The recurring motif is the DAG node: a filled circle.
// ---------------------------------------------------------------------------
function kit(pres) {
  const S = pres.shapes;
  const k = {};
  k.slide = (layout, section, title, notes) => {
    const s = pres.addSlide({ masterName: layout, sectionTitle: section });
    if (title) s.addText(title, { placeholder: "title" });
    if (notes) s.addNotes(notes);
    return s;
  };
  k.text = (s, text, o) => s.addText(text, Object.assign({ isTextBox: true, fontFace: BODY, fontSize: 14,
    color: P.ink, margin: 0, valign: "top" }, o));
  k.box = (s, x, y, w, h, fill, name) => s.addShape(S.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name });
  k.node = (s, x, y, d, label, fill, color, size) => s.addText(label, { shape: S.OVAL, x, y, w: d, h: d,
    fill: { color: fill }, line: { color: fill, width: 0 }, color: color || P.white, fontFace: BODY,
    fontSize: size || 14, bold: true, align: "center", valign: "middle", margin: 0, isTextBox: true });
  k.arrow = (s, x1, y1, x2, y2, color, width) => {
    const o = { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.001),
      h: Math.max(Math.abs(y2 - y1), 0.001), line: { color: color || P.sea, width: width || 1.5, endArrowType: "triangle" } };
    if (x2 < x1) o.flipH = true;
    if (y2 < y1) o.flipV = true;
    s.addShape(S.LINE, o);
  };
  k.line = (s, x1, y1, x2, y2, color, width) => s.addShape(S.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2),
    w: Math.max(Math.abs(x2 - x1), 0.001), h: Math.max(Math.abs(y2 - y1), 0.001),
    line: { color: color || P.line, width: width || 1 } });
  // A card: tinted rounded box, optional numbered node, bold heading, body.
  k.card = (s, x, y, w, h, heading, body, o) => {
    o = o || {};
    k.box(s, x, y, w, h, o.fill || P.foam, o.name);
    let tx = x + 0.2;
    if (o.num !== undefined) {
      k.node(s, x + 0.2, y + 0.2, 0.42, String(o.num), o.nodeFill || P.teal, P.white, 13);
      tx = x + 0.75;
    }
    k.text(s, heading, { x: tx, y: y + 0.18, w: x + w - tx - 0.15, h: 0.46, fontSize: o.headSize || 15, bold: true,
      color: o.headColor || P.deep, valign: "middle" });
    if (body) k.text(s, body, { x: x + 0.2, y: y + 0.72, w: w - 0.4, h: h - 0.85, fontSize: o.bodySize || 14,
      color: o.bodyColor || P.ink, paraSpaceAfter: 4 });
  };
  k.code = (s, x, y, w, h, code, size) => {
    k.box(s, x, y, w, h, P.code);
    k.text(s, code, { x: x + 0.15, y: y + 0.12, w: w - 0.3, h: h - 0.24, fontFace: MONO, fontSize: size || 11,
      color: P.codeText });
  };
  // "Expected result" panel used throughout the tutorial.
  k.expect = (s, x, y, w, h, body, size) => {
    k.box(s, x, y, w, h, P.okFill);
    k.node(s, x + 0.18, y + 0.16, 0.34, "✓", P.ok, P.white, 13);
    k.text(s, "Expected result", { x: x + 0.62, y: y + 0.16, w: w - 0.8, h: 0.34, fontSize: 13, bold: true,
      color: P.ok, valign: "middle" });
    k.text(s, body, { x: x + 0.2, y: y + 0.62, w: w - 0.4, h: h - 0.72, fontSize: size || 13, color: P.ink,
      paraSpaceAfter: 3 });
  };
  k.bullets = (items, o) => items.map((t, i) => ({ text: t,
    options: Object.assign({ bullet: { indent: 14 }, breakLine: i < items.length - 1, paraSpaceAfter: 6 }, o || {}) }));
  k.stat = (s, x, y, w, value, label, color) => {
    k.text(s, String(value), { x, y, w, h: 0.75, fontFace: HEAD, fontSize: 40, bold: true, color: color || P.teal });
    k.text(s, label, { x, y: y + 0.78, w, h: 0.55, fontSize: 12, color: P.muted });
  };
  // Small DAG mark used on dark title and closing slides.
  k.dagMark = (s, ox, oy, scale) => {
    const d = 0.62 * scale;
    const pts = { A: [ox + 1.0 * scale, oy], B: [ox, oy + 1.25 * scale], C: [ox + 2.0 * scale, oy + 1.25 * scale],
      D: [ox + 1.0 * scale, oy + 2.5 * scale] };
    const c = (n) => [pts[n][0] + d / 2, pts[n][1] + d / 2];
    [["A", "B"], ["A", "C"], ["B", "D"], ["C", "D"]].forEach(([a, b]) => {
      const [x1, y1] = c(a); const [x2, y2] = c(b);
      k.arrow(s, x1, y1 + d / 2, x2, y2 - d / 2, P.sea, 1.75);
    });
    k.node(s, pts.A[0], pts.A[1], d, "A", P.teal);
    k.node(s, pts.B[0], pts.B[1], d, "B", P.teal);
    k.node(s, pts.C[0], pts.C[1], d, "C", P.teal);
    k.node(s, pts.D[0], pts.D[1], d, "★", P.amber, P.deep, 18);
  };
  return k;
}

// Write the deck without ZIP directory entries, which some cloud editors reject.
async function save(pres, file) {
  const src = await JSZip.loadAsync(await pres.write({ outputType: "nodebuffer" }));
  const out = new JSZip();
  for (const name of Object.keys(src.files)) {
    const entry = src.files[name];
    if (!entry.dir) out.file(name, await entry.async("nodebuffer"), { createFolders: false });
  }
  fs.writeFileSync(file, await out.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  return file;
}

// ===========================================================================
// Deck 1: scientific talk (workshop / conference, 20 minutes)
// ===========================================================================
async function buildScientific() {
  const pres = newDeck("DAGonStar: FAIR-by-design workflows across the computing continuum",
    "DAGonStar · FAIR-by-design workflows across the computing continuum");
  const k = kit(pres);
  const E = EVIDENCE;
  const CONTENT = "Content";

  // 1 Title ------------------------------------------------------------------
  pres.addSection({ title: "Opening" });
  let s = k.slide("Title (dark)", "Opening", null,
    "0:00–0:45. Introduce DAGonStar (DAGon*): a Python workflow engine developed at the University of Naples " +
    "\"Parthenope\" for environmental and marine forecasting workflows, now generalised to the computing continuum. " +
    "State the thesis: one small programming model, many execution targets, and evidence recorded by design.");
  s.addText("DAGonStar: FAIR-by-Design Workflows Across the Computing Continuum", { placeholder: "title" });
  s.addText("Python-native DAG orchestration from laptops to HPC, cloud, serverless, IoT, and bounded agents",
    { placeholder: "body" });
  k.text(s, "Raffaele Montella and the DAGonStar team · University of Naples “Parthenope”",
    { x: 0.6, y: 4.45, w: 6.2, h: 0.32, fontSize: 13, color: P.amber });
  k.text(s, "DAGonStar " + E.version + " · Apache License 2.0 · github.com/DagOnStar/dagonstar",
    { x: 0.6, y: 4.8, w: 6.2, h: 0.3, fontSize: 11, color: P.seaLight });
  k.dagMark(s, 7.05, 1.2, 1.0);

  // 2 Motivation -------------------------------------------------------------
  pres.addSection({ title: "Problem" });
  s = k.slide(CONTENT, "Problem", "Every science is now computational",
    "0:45–2:00. Motivation from the README: clouds democratised computing, so any field is computational if it " +
    "has an easy-to-manage workflow engine. Our own driver is operational forecasting (weather, sea, pollutants, " +
    "mussel-farm contamination), which spans laptops, HPC clusters, and cloud services every day. The four " +
    "pressures on the right are the requirements the rest of the talk answers.");
  k.text(s, k.bullets([
    "Scientific results now depend on chains of models, converters, and services rather than single programs",
    "The same chain must run on a laptop, an HPC cluster, a cloud VM, or a remote service, often in one run",
    "Reviewers and operators ask what ran, on which inputs, and whether it can be repeated elsewhere",
  ]), { x: 0.5, y: 1.35, w: 4.4, h: 3.6, fontSize: 15 });
  const pressures = [
    ["Heterogeneity", "Local, Slurm, containers, cloud, FaaS, IoT, and LLM endpoints"],
    ["Data movement", "Inputs must reach each task; HPC cores idle while they copy"],
    ["Reproducibility", "Provenance, fixity, and safe checkpoint reuse"],
    ["Portability", "Workflows should leave the engine in a standard form"],
  ];
  pressures.forEach(([h, b], i) => {
    const y = 1.3 + i * 0.93;
    k.node(s, 5.3, y + 0.08, 0.55, String(i + 1), i === 1 ? P.amber : P.teal, i === 1 ? P.deep : P.white, 15);
    k.text(s, h, { x: 6.05, y, w: 3.45, h: 0.32, fontSize: 15, bold: true, color: P.deep });
    k.text(s, b, { x: 6.05, y: y + 0.33, w: 3.45, h: 0.5, fontSize: 13, color: P.muted });
  });

  // 3 Contributions ----------------------------------------------------------
  s = k.slide(CONTENT, "Problem", "Contributions",
    "2:00–3:00. Six contributions, each backed later by a slide and by tests in the repository. Stress that " +
    "every optional capability is opt-in: workflows that do not enable FAIR recording, pre-staging, or agentic " +
    "tasks keep their previous behaviour.");
  const contrib = [
    ["Data-driven DAGs", "workflow:// references in plain Python infer dependencies and staging"],
    ["One task contract", E.taskTypes + " task types share dependencies, staging, and checkpoints"],
    ["Pre-staging", "Slurm inputs staged and verified before sbatch, never after"],
    ["Bounded agents", "Agent results accepted only by independent evaluators"],
    ["FAIR by design", "Opt-in RO-Crate, PROV, DataCite, CodeMeta, and fixity"],
    ["CWL v1.2 export", "Deterministic, credential-safe command-graph interchange"],
  ];
  contrib.forEach(([h, b], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    k.card(s, 0.5 + col * 3.07, 1.3 + row * 1.9, 2.86, 1.72, h, b, { num: i + 1,
      nodeFill: i === 2 ? P.amber : P.teal });
  });

  // 4 Programming model ------------------------------------------------------
  pres.addSection({ title: "Model and architecture" });
  s = k.slide(CONTENT, "Model and architecture", "Dependencies follow the data",
    "3:00–4:30. Walk the quick-start example. Nobody writes an edge: task D reads workflow:///B/f2.txt and " +
    "workflow:///C/f2.txt, so make_dependencies() adds B→D and C→D, and at run time the stager places " +
    "the producer's file in D's scratch directory and rewrites the reference to that path. Explicit add_dependency_to " +
    "edges remain available and are kept when the graph is rebuilt or loaded from JSON.");
  k.code(s, 0.5, 1.3, 5.2, 3.65,
    "from dagon import Workflow\n" +
    "from dagon.task import DagonTask, TaskType\n\n" +
    "wf = Workflow(\"DataFlow-Demo\")\n" +
    "a = DagonTask(TaskType.BATCH, \"A\",\n" +
    "    \"mkdir -p output; hostname > output/f1.txt\")\n" +
    "b = DagonTask(TaskType.BATCH, \"B\",\n" +
    "    \"cat workflow:///A/output/f1.txt > f2.txt\")\n" +
    "c = DagonTask(TaskType.BATCH, \"C\",\n" +
    "    \"cat workflow:///A/output/f1.txt > f2.txt\")\n" +
    "d = DagonTask(TaskType.BATCH, \"D\",\n" +
    "    \"cat workflow:///B/f2.txt \"\n" +
    "    \"workflow:///C/f2.txt > f3.txt\")\n" +
    "for t in (a, b, c, d): wf.add_task(t)\n" +
    "wf.make_dependencies()  # inferred edges\n" +
    "wf.run()", 10.5);
  {
    const d = 0.62, cx = 7.55;
    const P4 = { A: [cx, 1.35], B: [cx - 1.05, 2.65], C: [cx + 1.05, 2.65], D: [cx, 3.95] };
    const mid = (n) => [P4[n][0] + d / 2, P4[n][1] + d / 2];
    [["A", "B", "f1.txt"], ["A", "C", "f1.txt"], ["B", "D", "f2.txt"], ["C", "D", "f2.txt"]].forEach(([a, b, lab], i) => {
      const [x1, y1] = mid(a); const [x2, y2] = mid(b);
      k.arrow(s, x1, y1 + d / 2, x2, y2 - d / 2, P.sea, 1.75);
      const left = (x1 + x2) / 2 < cx + d / 2;
      const lx = (x1 + x2) / 2 + (left ? -1.0 : 0.15);
      k.text(s, lab, { x: lx, y: (y1 + y2) / 2 - 0.13, w: 0.85, h: 0.26, fontSize: 11, color: P.muted,
        fontFace: MONO, align: left ? "right" : "left" });
      return i;
    });
    ["A", "B", "C"].forEach((n) => k.node(s, P4[n][0], P4[n][1], d, n, P.teal));
    k.node(s, P4.D[0], P4.D[1], d, "D", P.amber, P.deep, 16);
    k.text(s, "Inferred graph: no edge was declared by hand", { x: 6.0, y: 4.72, w: 3.5, h: 0.3, fontSize: 12,
      color: P.muted, align: "center" });
  }

  // 5 Architecture -----------------------------------------------------------
  s = k.slide(CONTENT, "Model and architecture", "Architecture",
    "4:30–5:45. Top to bottom: the Workflow owns the graph, validation, checkpoint state and lifecycle hooks; " +
    "DagonTask is a factory from TaskType to a concrete class; every Task is a thread that creates its scratch " +
    "directory, writes a bash launcher, rewrites workflow:// references and stages inputs. The FAIR recorder and the " +
    "CWL exporter sit beside the core and observe it; they do not change execution.");
  const layers = [
    ["Workflow", "graph · make_dependencies · cycle validation · checkpoints · run / launch · hooks"],
    ["DagonTask factory", "TaskType → concrete task class (Batch, Slurm, Docker, Native, FaaS, Agentic …)"],
    ["Task (thread)", "scratch directory · launcher · workflow:// rewriting · staging · status"],
  ];
  layers.forEach(([h, b], i) => {
    const y = 1.3 + i * 0.92;
    k.box(s, 0.5, y, 6.1, 0.72, i === 0 ? P.teal : P.foam);
    k.text(s, h, { x: 0.7, y: y + 0.1, w: 1.9, h: 0.52, fontSize: 15, bold: true, valign: "middle",
      color: i === 0 ? P.white : P.deep });
    k.text(s, b, { x: 2.6, y: y + 0.1, w: 3.9, h: 0.52, fontSize: 12, valign: "middle",
      color: i === 0 ? P.white : P.ink });
    if (i < 2) k.arrow(s, 3.55, y + 0.72, 3.55, y + 0.92, P.sea, 1.5);
  });
  k.arrow(s, 3.55, 1.3 + 2 * 0.92 + 0.72, 3.55, 4.18, P.sea, 1.5);
  ["Local bash", "Slurm + BeeOND", "SSH", "Containers", "Cloud", "Services"].forEach((b, i) => {
    const w = 0.95, x = 0.5 + i * 1.03;
    k.box(s, x, 4.2, w, 0.72, P.mist);
    k.text(s, b, { x: x + 0.05, y: 4.2, w: w - 0.1, h: 0.72, fontSize: 11, align: "center", valign: "middle",
      color: P.deep, bold: true });
  });
  k.card(s, 6.95, 1.3, 2.55, 1.72, "FAIR recorder", "Listens to lifecycle hooks; exports local metadata",
    { fill: P.mist, bodySize: 13 });
  k.card(s, 6.95, 3.2, 2.55, 1.72, "CWL exporter", "Workflow.saveAsCWL() writes CWL v1.2 JSON",
    { fill: P.mist, bodySize: 13 });
  k.arrow(s, 6.6, 1.66, 6.95, 1.66, P.amber, 1.5);
  k.arrow(s, 6.6, 2.58, 6.95, 3.56, P.amber, 1.5);

  // 6 Task types -------------------------------------------------------------
  s = k.slide(CONTENT, "Model and architecture", E.taskTypes + " task types behind one contract",
    "5:45–6:45. The TaskType enumeration currently registers fourteen types. The point is not the list but the " +
    "contract: all of them take part in workflow:// dependencies, checkpoints, JSON serialisation, FAIR declarations " +
    "and CWL export. A single all-factory test builds a mixed workflow containing every type and checks these " +
    "properties without live external services.");
  const groups = [
    ["Execution backends", ["batch", "slurm", "docker", "apptainer", "kubernetes", "nomad", "cloud"], P.teal],
    ["Structured services", ["native", "web", "llm", "faas", "iot", "agentic"], P.sea],
    ["Control", ["checkpoint"], P.amber],
  ];
  groups.forEach(([h, items, color], gi) => {
    const x = 0.5 + gi * 3.07;
    k.box(s, x, 1.3, 2.86, 2.75, P.mist);
    k.text(s, h, { x: x + 0.2, y: 1.42, w: 2.5, h: 0.36, fontSize: 15, bold: true, color: P.deep });
    items.forEach((it, i) => {
      const cx = x + 0.2 + (i % 2) * 1.27, cy = 1.92 + Math.floor(i / 2) * 0.5;
      k.box(s, cx, cy, 1.17, 0.38, color);
      k.text(s, it, { x: cx, y: cy, w: 1.17, h: 0.38, fontFace: MONO, fontSize: 11, align: "center",
        valign: "middle", color: color === P.amber ? P.deep : P.white, bold: true });
    });
  });
  k.box(s, 0.5, 4.25, 9.0, 0.72, P.foam);
  k.text(s, "One all-factory contract test builds a mixed workflow with every TaskType and checks workflow:// " +
    "references, FAIR declarations, checkpoint reuse, and runnable CWL export.",
    { x: 0.7, y: 4.25, w: 8.6, h: 0.72, fontSize: 13, valign: "middle" });

  // 7 Staging ----------------------------------------------------------------
  pres.addSection({ title: "Data movement" });
  s = k.slide(CONTENT, "Data movement", "One reference, many data movers",
    "6:45–7:45. A workflow:// URI names a producer task and a path inside its scratch directory. The stager " +
    "chooses a mover: a symbolic link or copy on the same host, SCP between hosts, Globus or SKYCDS for managed " +
    "transfers. The consumer sees a local path below .dagon/inputs; the path shown is the one observed in our " +
    "getting-started run. Slurm tasks can also run on BeeOND volumes created per task or per workflow.");
  k.box(s, 0.5, 1.35, 3.3, 0.9, P.code);
  k.text(s, "workflow:///prepare/\ndata/profile.csv", { x: 0.65, y: 1.35, w: 3.0, h: 0.9, fontFace: MONO,
    fontSize: 13, color: P.codeText, valign: "middle" });
  k.arrow(s, 3.8, 1.8, 4.4, 1.8, P.sea, 2);
  k.node(s, 4.45, 1.38, 0.85, "Stager", P.teal, P.white, 12);
  ["LINK", "COPY", "SCP", "Globus", "SKYCDS"].forEach((m, i) => {
    const y = 1.3 + i * 0.5;
    k.arrow(s, 5.3, 1.8, 5.85, y + 0.19, P.line, 1.25);
    k.box(s, 5.9, y, 1.3, 0.38, i < 2 ? P.sea : P.foam);
    k.text(s, m, { x: 5.9, y, w: 1.3, h: 0.38, fontSize: 12, bold: true, align: "center", valign: "middle",
      color: i < 2 ? P.white : P.deep });
  });
  k.text(s, "same host", { x: 7.35, y: 1.42, w: 2.1, h: 0.6, fontSize: 12, color: P.muted, valign: "middle" });
  k.text(s, "across hosts and managed transfer services", { x: 7.35, y: 2.32, w: 2.1, h: 0.9, fontSize: 12,
    color: P.muted, valign: "middle" });
  k.text(s, "Observed consumer path after staging", { x: 0.5, y: 3.88, w: 6, h: 0.3, fontSize: 13, bold: true,
    color: P.deep });
  k.code(s, 0.5, 4.2, 9.0, 0.6, "<scratch>/1794842172279-analyze/.dagon/inputs/FirstWorkflow/prepare//data/profile.csv", 11);
  k.text(s, "Links and copies run locally; SCP, Globus, and SKYCDS need hosts, endpoints, or tokens from the environment.",
    { x: 0.5, y: 2.55, w: 3.75, h: 1.1, fontSize: 13, color: P.ink });

  // 8 Pre-staging concept ----------------------------------------------------
  s = k.slide(CONTENT, "Data movement", "Scheduler-aware pre-staging",
    "7:45–9:30. In the legacy lifecycle the job copies its inputs after the allocation starts, so every core " +
    "is idle during the copy. With pre_stage=True the task stages and verifies inputs on the submission host first; " +
    "sbatch never runs if stage-in failed or cannot be confirmed. The compute launcher re-checks the staged content " +
    "before the payload runs. The 100 core-hour figure is the worked example from docs/scheduler_prestaging.md. " +
    "DAGonStar reports cores × (staging − re-check) / 3600 as an estimate of allocation not held, not a " +
    "measured saving in queue or wall time.");
  const X0 = 2.0, U = 0.62; // inches per time unit
  const rowBar = (y, segs) => {
    let x = X0;
    segs.forEach(([len, label, fill, color]) => {
      k.box(s, x, y, len * U - 0.04, 0.52, fill);
      k.text(s, label, { x: x + 0.05, y, w: len * U - 0.14, h: 0.52, fontSize: 11, align: "center",
        valign: "middle", color: color || P.white, bold: true });
      x += len * U;
    });
  };
  k.text(s, "Legacy", { x: 0.5, y: 1.62, w: 1.4, h: 0.52, fontSize: 15, bold: true, valign: "middle", color: P.deep });
  rowBar(1.62, [[3, "Queue wait", P.line, P.deep], [3, "Stage-in: cores idle", P.coral], [5, "Compute", P.teal]]);
  k.line(s, X0 + 3 * U, 1.47, X0 + 11 * U - 0.04, 1.47, P.coral, 1.5);
  k.text(s, "allocation held", { x: X0 + 3 * U, y: 1.2, w: 2.4, h: 0.25, fontSize: 11, color: P.coral });
  k.text(s, "Pre-staged", { x: 0.5, y: 2.62, w: 1.4, h: 0.52, fontSize: 15, bold: true, valign: "middle", color: P.deep });
  rowBar(2.62, [[3, "Stage-in on login host", P.amber, P.deep], [3, "Queue wait", P.line, P.deep],
    [0.8, "", P.sea], [5, "Compute", P.teal]]);
  k.line(s, X0 + 6 * U, 3.29, X0 + 11.8 * U - 0.04, 3.29, P.teal, 1.5);
  k.text(s, "allocation held (incl. content re-check)", { x: X0 + 6 * U, y: 3.33, w: 3.6, h: 0.25, fontSize: 11,
    color: P.teal });
  k.stat(s, 0.5, 3.75, 2.7, "100", "core-hours not held: 200 cores × 30 min stage-in (worked example)", P.amber);
  k.text(s, k.bullets([
    "Opt-in per workflow or per task; the legacy launcher is guarded byte for byte",
    "No sbatch before a confirmed stage-in; staging, submission, execution failures stay distinct",
  ]), { x: 3.4, y: 3.8, w: 6.1, h: 1.25, fontSize: 13 });

  // 9 Bounded agentic tasks -------------------------------------------------
  pres.addSection({ title: "Structured tasks" });
  s = k.slide(CONTENT, "Structured tasks", "Bounded agents, independent acceptance",
    "9:30–11:00. TaskType.AGENTIC treats an agent as an untrusted producer. The dagon.ini profile is the maximum " +
    "authority: a task may narrow tools and budgets or add guardrails, never widen them. Guardrails and evaluators " +
    "run outside the agent, in supervised processes; the agent's self-report is never evidence. Only an accepted " +
    "result is published, atomically, with commit.json written last. A rejected run never releases dependants. " +
    "Tests use a deterministic mock adapter and a loopback server; live models are not evaluated.");
  const steps = [["Profile", "dagon.ini, max authority"], ["Bounded loop", "steps, time, tools"],
    ["Guardrails", "outside the agent"], ["Evaluators", "weights + mandatory gates"]];
  steps.forEach(([h, b], i) => {
    const x = 0.5 + i * 2.3;
    k.node(s, x + 0.55, 1.35, 0.8, String(i + 1), P.teal, P.white, 18);
    if (i < 3) k.arrow(s, x + 1.38, 1.75, x + 2.82, 1.75, P.sea, 1.75);
    k.text(s, h, { x, y: 2.25, w: 1.9, h: 0.34, fontSize: 15, bold: true, color: P.deep, align: "center" });
    k.text(s, b, { x, y: 2.6, w: 1.9, h: 0.5, fontSize: 12, color: P.muted, align: "center" });
  });
  k.card(s, 0.5, 3.3, 4.4, 1.65, "Accepted",
    "Published atomically (commit.json last); dependants released; checkpoint keyed by contract, profile, versions, and input hashes",
    { fill: P.okFill, headColor: P.ok, bodySize: 13 });
  k.card(s, 5.1, 3.3, 4.4, 1.65, "Rejected or failed",
    "Nothing published; dependants never released; the evaluation report explains which gate failed",
    { fill: "F8E9E5", headColor: P.coral, bodySize: 13 });

  // 10 FAIR -------------------------------------------------------------------
  pres.addSection({ title: "FAIR and interoperability" });
  s = k.slide(CONTENT, "FAIR and interoperability", "FAIR by design, and opt-in",
    "11:00–12:15. Workflow.enable_fair(profile) registers a standard-library recorder on lifecycle hooks; " +
    "without it nothing changes. The recorder exports what the implementation can substantiate locally: lifecycle, " +
    "tasks, workflow:// producer/consumer edges, declared outputs with SHA-256 fixity, and checkpoint reuse. " +
    "The file list is exactly what examples/fair/fair_local.py verified in our run. These are local metadata " +
    "artifacts, not repository publication; credentials are never captured.");
  k.text(s, k.bullets([
    "Lifecycle, task, and dependency records from workflow hooks",
    "workflow:// producer and consumer edges become PROV relations",
    "Declared outputs carry licence, media type, and SHA-256 fixity",
    "No dependencies added; credential capture disabled by default",
  ]), { x: 0.5, y: 1.35, w: 4.3, h: 3.0, fontSize: 15 });
  ["run.json", "ro-crate-metadata.json", "prov.json", "datacite.json", "codemeta.json", "checksums.sha256",
    "fairness-report.json", "report.md / report.html"].forEach((f, i) => {
    const x = 5.15 + (i % 2) * 2.2, y = 1.35 + Math.floor(i / 2) * 0.62;
    k.box(s, x, y, 2.1, 0.48, i === 1 ? P.teal : P.foam);
    k.text(s, f, { x: x + 0.08, y, w: 1.94, h: 0.48, fontFace: MONO, fontSize: 10, align: "center",
      valign: "middle", color: i === 1 ? P.white : P.deep, bold: true });
  });
  k.text(s, "Written below <scratch>/.dagon/fair/<workflow>/<run>/", { x: 5.15, y: 3.85, w: 4.35, h: 0.3,
    fontSize: 12, color: P.muted });
  k.box(s, 0.5, 4.35, 9.0, 0.62, P.mist);
  k.text(s, "Boundary: exports are local metadata. They do not copy large outputs, fetch remote checksums, or publish to a repository.",
    { x: 0.7, y: 4.35, w: 8.6, h: 0.62, fontSize: 13, valign: "middle" });

  // 11 CWL -------------------------------------------------------------------
  s = k.slide(CONTENT, "FAIR and interoperability", "CWL v1.2: an explicit portability boundary",
    "12:15–13:15. Workflow.saveAsCWL(filename) writes a self-contained CWL v1.2 JSON document. The export is " +
    "deterministic and contains no scratch paths or credentials; Lesson 32 validates it with cwltool --validate, " +
    "which reported ok in our run. What is portable is the command graph; DAGonStar's staging, schedulers, and " +
    "remote runtimes stay on the DAGonStar side. Structured task types are represented through runner tools such as " +
    "dagon-agent-runner.");
  k.card(s, 0.5, 1.3, 4.4, 2.55, "Portable in CWL",
    "", { fill: P.foam });
  k.text(s, k.bullets(["Command-line steps and their dependency graph", "Deterministic, credential-free output",
    "Runner-based tools for FaaS, IoT, and agentic tasks"]), { x: 0.7, y: 2.0, w: 4.0, h: 1.75, fontSize: 14 });
  k.card(s, 5.1, 1.3, 4.4, 2.55, "Stays in DAGonStar", "", { fill: P.mist });
  k.text(s, k.bullets(["Stagers and data movers", "Slurm, BeeOND, SSH, and cloud runtime behaviour",
    "Checkpoint and FAIR recording"]), { x: 5.3, y: 2.0, w: 4.0, h: 1.75, fontSize: 14 });
  k.code(s, 0.5, 4.05, 5.6, 0.9, "wf.saveAsCWL(\"workflow.cwl\")\n$ python examples/tutorial/lesson_32_cwl_export.py\ncwltool --validate: ok", 11);
  k.text(s, "\"cwlVersion\": \"v1.2\", \"class\": \"Workflow\"", { x: 6.3, y: 4.05, w: 3.2, h: 0.9, fontFace: MONO,
    fontSize: 11, color: P.muted, valign: "middle" });

  // 12 Evaluation -------------------------------------------------------------
  pres.addSection({ title: "Evaluation" });
  s = k.slide(CONTENT, "Evaluation", "Evaluation: evidence levels, not claims",
    "13:15–14:45. Numbers observed on " + E.observedOn + ". The unit suite and local examples need no external " +
    "service. CI repeats them on Ubuntu (Python 3.8–3.13), macOS, Windows with Git Bash, Rocky Linux 9 and Debian " +
    "bookworm arm64, and runs BeeOND and pre-staging on a single-node Slurm cluster. The table is the honest map: " +
    "what is only tested locally, what CI exercises, what one manual production run showed, and what is not exercised.");
  k.stat(s, 0.5, 1.2, 2.1, E.unitTests, "unit tests pass locally, no live services");
  k.stat(s, 2.75, 1.2, 2.1, "5", "CI platforms incl. Windows and arm64");
  k.stat(s, 5.0, 1.2, 2.1, E.lessons, "self-checking tutorial lessons");
  k.stat(s, 7.25, 1.2, 2.25, E.localExamples, "local examples run end to end");
  const ev = [
    ["Evidence level", "What it covers"],
    ["Local tests", "Dependency discovery, staging commands, checkpoints, JSON/CWL, FAIR, agentic contract"],
    ["CI, single-node Slurm", "BeeOND (emulated site) and pre-staging with real sbatch"],
    ["Manual, one production site", "Pre-staging on Slurm 23.11 with NFS scratch; BeeOND on four nodes"],
    ["Not exercised", "Live cloud, FaaS, IoT, LLM, and agent providers"],
  ];
  s.addTable(ev.map((r, i) => r.map((c) => ({ text: c, options: { bold: i === 0 || false, color: i === 0 ? P.white : P.ink,
    fill: { color: i === 0 ? P.teal : (i % 2 ? P.mist : P.white) } } }))), {
    x: 0.5, y: 2.85, w: 9.0, colW: [2.6, 6.4], fontFace: BODY, fontSize: 12, rowH: 0.4, valign: "middle",
    border: { type: "solid", pt: 0.5, color: P.line }, margin: [0, 0.1, 0, 0.1] });

  // 13 Pre-staging on a production site ----------------------------------------
  s = k.slide(CONTENT, "Evaluation", "Pre-staging on a production cluster",
    "14:45–16:15. Report the manual site run recorded in the README. Setup: Slurm 23.11, NFS-shared scratch, " +
    "compute nodes, real SSH for RemoteSlurm; tools/hpc_prestage_deep.py adds a 1 GiB input, 5,000 small files, a " +
    "two-node allocation, induced queue waits, a change and a cancellation while pending, two contending processes " +
    "and node-local scratch. Key finding: for a 1 GiB input the job's re-check of staged data took most of the " +
    "pre-staged allocation; after checksum batching the pre-staged job was shorter than the legacy one under load, " +
    "but not on a quiet file system. One site, so evidence, not a guarantee.");
  k.card(s, 0.5, 1.3, 2.86, 2.6, "Setup",
    "Slurm 23.11, NFS scratch, real SSH. 1 GiB input and 5,000 small files; two nodes; induced queue waits, change and cancel while pending",
    { num: 1, bodySize: 13 });
  k.card(s, 3.57, 1.3, 2.86, 2.6, "Observation",
    "The job's re-check of staged content took most of the pre-staged allocation for 1 GiB. After checksum batching, pre-staged ran shorter than legacy under load",
    { num: 2, nodeFill: P.amber, bodySize: 13 });
  k.card(s, 6.64, 1.3, 2.86, 2.6, "Interpretation",
    "Benefit depends on file-system load: none on a quiet file system. Re-check time is reported and subtracted; core-hours stay an estimate",
    { num: 3, bodySize: 13 });
  k.box(s, 0.5, 4.1, 9.0, 0.85, P.mist);
  k.text(s, "One site and one Slurm release: evidence, not a general guarantee. Production-scale transfers and real queue waits are not yet measured.",
    { x: 0.7, y: 4.1, w: 8.6, h: 0.85, fontSize: 13, valign: "middle" });

  // 14 Applications -----------------------------------------------------------
  s = k.slide(CONTENT, "Evaluation", "Applications in environmental science",
    "16:15–17:15. DAGonStar runs production workflows in three funded initiatives listed in the README: MytilX " +
    "(Istituto Zooprofilattico Sperimentale dell'Umbria e delle Marche) and MytilEx (Campania Region) for weather, " +
    "marine, pollutant and farmed-mussel contamination forecasts, and the EuroHPC ADMIRE environmental application. " +
    "Related application papers cover Lagrangian pollutant transport and the Shoreline Alert Model.");
  [["MytilX", "Mytilus farming at scale: weather, marine, pollutant, and contamination forecasts per study zone"],
    ["MytilEx", "Daily operational forecasts for mussel farming with HPC and AI, Campania Region"],
    ["ADMIRE (EuroHPC)", "WP7 environmental application: on-demand weather, marine, and pollutant simulations"]]
    .forEach(([h, b], i) => k.card(s, 0.5 + i * 3.07, 1.3, 2.86, 2.55, h, b, { num: ["X", "E", "A"][i],
      nodeFill: i === 0 ? P.amber : P.teal, bodySize: 13 }));
  k.box(s, 0.5, 4.05, 9.0, 0.9, P.mist);
  k.text(s, "Also used for Lagrangian transport and diffusion of marine pollutants and the parallel Shoreline Alert Model (PDP 2023).",
    { x: 0.7, y: 4.05, w: 8.6, h: 0.9, fontSize: 13, valign: "middle" });

  // 15 Limitations ------------------------------------------------------------
  pres.addSection({ title: "Closing" });
  s = k.slide(CONTENT, "Closing", "Limitations and threats to validity",
    "17:15–18:30. Be explicit. Pre-staging evidence comes from one production site. SCP, GridFTP and SKYCDS " +
    "transfers are checked for existence, not content. Several legacy paths still build shell strings, and rewritten " +
    "workflow:// arguments stay unquoted, so paths with spaces are not supported in user commands. The unit suite " +
    "validates command generation and boundaries, not live Docker, Kubernetes, cloud, FaaS, IoT or LLM providers.");
  [["External validity", "Pre-staging measured on one production site and one CI cluster"],
    ["Verification depth", "SCP, GridFTP, and SKYCDS inputs checked for existence, not content"],
    ["Shell construction", "Legacy paths build shell strings; rewritten workflow:// arguments stay unquoted"],
    ["Test scope", "Suite checks command generation and boundaries, not live providers"]]
    .forEach(([h, b], i) => k.card(s, 0.5 + (i % 2) * 4.6, 1.3 + Math.floor(i / 2) * 1.85, 4.4, 1.68, h, b,
      { num: i + 1, nodeFill: P.coral, bodySize: 14 }));

  // 16 Conclusions ------------------------------------------------------------
  s = k.slide("Closing (dark)", "Closing", "Conclusions and future work",
    "18:30–20:00. Three take-aways, then future work stated as future work: live IoT network providers, automatic " +
    "object-store upload for FaaS artifacts, wider quoting helpers, and pre-staging measurements on more sites and " +
    "under real queue waits. Invite questions and point to the repository and the 33-lesson tutorial.");
  [["Small model, wide reach", "Plain Python plus workflow:// spans " + E.taskTypes + " task types"],
    ["Evidence by design", "FAIR, checkpoints, and acceptance are recorded, not asserted"],
    ["Portable by contract", "CWL v1.2 export with an explicit boundary"]].forEach(([h, b], i) => {
    const y = 1.45 + i * 0.95;
    k.node(s, 0.6, y, 0.6, String(i + 1), i === 0 ? P.amber : P.teal, i === 0 ? P.deep : P.white, 16);
    k.text(s, h, { x: 1.4, y: y - 0.02, w: 4.4, h: 0.34, fontSize: 16, bold: true, color: P.white });
    k.text(s, b, { x: 1.4, y: y + 0.33, w: 4.6, h: 0.5, fontSize: 13, color: P.seaLight });
  });
  k.box(s, 6.15, 1.4, 3.35, 2.85, "123F45");
  k.text(s, "Future work", { x: 6.35, y: 1.55, w: 3.0, h: 0.35, fontSize: 16, bold: true, color: P.amber });
  k.text(s, k.bullets(["Live IoT network providers", "Object-store upload for FaaS artifacts",
    "Safer quoting on legacy paths", "Pre-staging on more sites"]), { x: 6.35, y: 2.0, w: 3.0, h: 2.15,
    fontSize: 13, color: P.white });
  k.text(s, "github.com/DagOnStar/dagonstar · tutorial: docs/tutorial/  ·  Questions?",
    { x: 0.6, y: 4.6, w: 8.9, h: 0.35, fontSize: 13, color: P.amber });

  // 17 References -------------------------------------------------------------
  s = k.slide(CONTENT, "Closing", "Selected references",
    "Backup slide. Cite the FGCS 2021 paper for the engine and the WORKS 2018 paper for the original DAGon design.");
  k.text(s, [
    "Montella, R., Di Luccio, D., Kosta, S. DAGon: Executing direct acyclic graphs as parallel jobs on anything. IEEE/ACM WORKS 2018, 64–73.",
    "Sánchez-Gallegos, D. D., Di Luccio, D., Kosta, S., Gonzalez-Compean, J. L., Montella, R. An efficient pattern-based approach for workflow supporting large-scale science: The DagOnStar experience. Future Generation Computer Systems 122 (2021) 187–203.",
    "Sánchez-Gallegos, D. D., Di Luccio, D., Gonzalez-Compean, J. L., Montella, R. Internet of things orchestration using DagOn* workflow engine. IEEE WF-IoT 2019, 95–100.",
    "Sánchez-Gallegos, D. D., et al. A microservice-based building block approach for scientific workflow engines. IEEE SITIS 2019, 368–375.",
    "Barron-Lugo, J. A., et al. A novel transversal processing model to build environmental big data services in the cloud. Environmental Modelling & Software 144 (2021) 105173.",
    "Montella, R., et al. A highly scalable high-performance Lagrangian transport and diffusion model for marine pollutants assessment. PDP 2023, 17–26.",
  ].map((t, i, a) => ({ text: t, options: { bullet: { type: "number" }, breakLine: i < a.length - 1, paraSpaceAfter: 6 } })),
  { x: 0.5, y: 1.3, w: 9.0, h: 3.7, fontSize: 12 });

  const file = path.join(OUT_DIR, "dagonstar_scientific_talk.pptx");
  return save(pres, file);
}

// ===========================================================================
// Deck 2: tutorial (build, install, configure, test, evaluate; 20 minutes)
// ===========================================================================
async function buildTutorial() {
  const pres = newDeck("DAGonStar hands-on tutorial", "DAGonStar hands-on · build, install, configure, test, evaluate");
  const k = kit(pres);
  const E = EVIDENCE;
  const CONTENT = "Content";

  // 1 Title -------------------------------------------------------------------
  pres.addSection({ title: "Opening" });
  let s = k.slide("Title (dark)", "Opening", null,
    "0:00–0:30. Goal: in twenty minutes every participant builds DAGonStar from source, installs it, writes a " +
    "configuration, runs the tests, and checks the results against the expected values on the slides. Everything " +
    "runs locally: no cluster, cloud account, or model key is needed.");
  s.addText("DAGonStar Hands-On: Build, Install, Configure, Test, Evaluate", { placeholder: "title" });
  s.addText("A 20-minute local path from a fresh clone to verified results", { placeholder: "body" });
  k.text(s, "DAGonStar " + E.version + " · Python 3.8+ · Linux, macOS, Windows (Git Bash)",
    { x: 0.6, y: 4.45, w: 6.2, h: 0.32, fontSize: 13, color: P.amber });
  k.text(s, "Expected values observed on " + E.observedOn, { x: 0.6, y: 4.8, w: 6.2, h: 0.3, fontSize: 11,
    color: P.seaLight });
  k.dagMark(s, 7.05, 1.2, 1.0);

  // 2 Roadmap -----------------------------------------------------------------
  s = k.slide(CONTENT, "Opening", "Roadmap for the next 20 minutes",
    "0:30–1:15. Seven steps, each with a command and an expected result. The long-running checks (the full " +
    "unit suite and all local examples) take minutes; start them in a second terminal and continue with the slides.");
  const road = [["Prepare", "2 min"], ["Build", "3 min"], ["Install", "2 min"], ["Configure", "2 min"],
    ["Verify", "3 min"], ["Test", "3 min"], ["Evaluate", "5 min"]];
  road.forEach(([h, t], i) => {
    const x = 0.5 + i * 1.3;
    if (i < road.length - 1) k.line(s, x + 0.75, 2.0, x + 1.3 + 0.3, 2.0, P.line, 2);
    k.node(s, x + 0.3, 1.6, 0.8, String(i + 1), i === 6 ? P.amber : P.teal, i === 6 ? P.deep : P.white, 18);
    k.text(s, h, { x, y: 2.55, w: 1.4, h: 0.32, fontSize: 15, bold: true, color: P.deep, align: "center" });
    k.text(s, t, { x, y: 2.88, w: 1.4, h: 0.3, fontSize: 12, color: P.muted, align: "center" });
  });
  k.box(s, 0.5, 3.6, 9.0, 1.35, P.mist);
  k.text(s, "Every step ends with an expected result in a green panel. If what you see differs, check the " +
    "troubleshooting slide before moving on: later steps depend on earlier ones.",
    { x: 0.75, y: 3.6, w: 8.5, h: 1.35, fontSize: 15, valign: "middle" });

  // 3 Prerequisites -----------------------------------------------------------
  pres.addSection({ title: "Build and install" });
  s = k.slide(CONTENT, "Build and install", "Step 1 — Prerequisites",
    "1:15–3:00. Python 3.8 or newer (CI covers 3.8 to 3.13). Local tasks run as bash launchers found by " +
    "dagon.platform_support.bash_executable(); on Windows install Git for Windows, MSYS2 or Cygwin, or point " +
    "DAGON_BASH at a bash. Docker, Slurm, SSH, cloud and transfer services are optional and not used today.");
  [["Python ≥ 3.8", "CI tests 3.8 to 3.13. A virtual environment keeps the install isolated"],
    ["POSIX bash", "Linux and macOS ship it. Windows: Git Bash, MSYS2, or Cygwin, or set DAGON_BASH"],
    ["Git", "To clone the repository; Node is not needed"]].forEach(([h, b], i) =>
    k.card(s, 0.5 + i * 3.07, 1.3, 2.86, 2.2, h, b, { num: i + 1 }));
  k.code(s, 0.5, 3.7, 5.3, 1.25, "python3 --version      # 3.8 or newer\nbash --version | head -1\ngit --version", 12);
  k.text(s, "Optional, not needed today: Docker, Apptainer, Kubernetes, Nomad, SSH hosts, Slurm, cloud, Globus, SKYCDS",
    { x: 6.0, y: 3.7, w: 3.5, h: 1.25, fontSize: 13, color: P.muted, valign: "middle" });

  // 4 Build ----------------------------------------------------------------
  s = k.slide(CONTENT, "Build and install", "Step 2 — Get the source and compile",
    "3:00–5:00. DAGonStar is pure Python, so compiling means byte-compiling the sources and, optionally, " +
    "building the sdist and wheel exactly as the CI build job does with python -m build and twine check --strict. " +
    "py_compile prints nothing on success. The distribution names come from setup.cfg version " + E.version + ".");
  k.code(s, 0.5, 1.3, 5.4, 3.65,
    "git clone https://github.com/DagOnStar/dagonstar.git\n" +
    "cd dagonstar\n" +
    "python3 -m venv .venv\n" +
    ". .venv/bin/activate\n" +
    "# Windows: .venv\\Scripts\\activate\n" +
    "python -m pip install --upgrade pip\n\n" +
    "# byte-compile every module (silent)\n" +
    "python -m py_compile dagon/*.py dagon/api/*.py \\\n" +
    "  dagon/communication/*.py dagon/ftp_publisher/*.py \\\n" +
    "  dagon/peer2peer/*.py\n\n" +
    "# optional: build distributions like CI\n" +
    "python -m pip install build twine\n" +
    "python -m build\n" +
    "python -m twine check --strict dist/*", 10);
  k.expect(s, 6.1, 1.3, 3.4, 3.65,
    "py_compile exits 0 and prints nothing\n\ndist/ contains:\ndagonstar-" + E.version + ".tar.gz\ndagonstar-" +
    E.version + "-py3-none-any.whl\n\ntwine reports PASSED for both", 13);

  // 5 Install ---------------------------------------------------------------
  s = k.slide(CONTENT, "Build and install", "Step 3 — Install, with extras only when needed",
    "5:00–7:00. The editable install is what developers use. The base package installs requests, fabric3, " +
    "paramiko, graphviz and pycryptodome; Docker, cloud SDKs, Globus and Flask are extras. requirements.txt is the " +
    "full demo environment with all integrations. If you call an integration without its extra, DAGonStar reports " +
    "the install command at that boundary.");
  k.code(s, 0.5, 1.3, 4.6, 1.6, "python -m pip install -e .\n\n# or the full demo environment\npython -m pip install -r requirements.txt", 11.5);
  const extras = [["Extra", "Enables"], ["docker", "Docker tasks, local or over SSH"], ["kubernetes", "Kubernetes tasks"],
    ["cloud", "Apache Libcloud cloud tasks"], ["globus", "Globus staging"], ["api", "Flask workflow service"],
    ["faas-aws / -azure / -gcp", "Cloud FaaS adapters"], ["all", "Every optional integration"]];
  s.addTable(extras.map((r, i) => r.map((c, j) => ({ text: c, options: { bold: i === 0, fontFace: j === 0 && i > 0 ? MONO : BODY,
    color: i === 0 ? P.white : P.ink, fill: { color: i === 0 ? P.teal : (i % 2 ? P.mist : P.white) } } }))), {
    x: 5.35, y: 1.3, w: 4.15, colW: [1.85, 2.3], fontSize: 11, rowH: 0.42, valign: "middle",
    border: { type: "solid", pt: 0.5, color: P.line }, margin: [0, 0.08, 0, 0.08] });
  k.text(s, "pip install -e \".[docker]\"", { x: 5.35, y: 4.75, w: 4.15, h: 0.25, fontFace: MONO, fontSize: 11,
    color: P.muted });
  k.expect(s, 0.5, 3.1, 4.6, 1.85, "python -c \"import dagon\" exits 0\npip show dagonstar → Version: " + E.version +
    "\nNo Docker or cloud SDK installed by the base package", 13);

  // 6 Configure -------------------------------------------------------------
  pres.addSection({ title: "Configure and verify" });
  s = k.slide(CONTENT, "Configure and verify", "Step 4 — Configure dagon.ini",
    "7:00–9:00. Always start from the sample: it also carries the logging sections ([loggers], [handlers], " +
    "[formatters]). A hand-written file with only [batch] fails at start-up with KeyError: 'formatters' — we hit " +
    "this while preparing the tutorial. Point scratch_dir_base at a directory you own. Secrets never go in the file: " +
    "SKYCDS tokens, cloud keys and model keys come from environment variables named by the configuration.");
  k.code(s, 0.5, 1.3, 4.6, 2.65,
    "cp dagon.ini.sample dagon.ini\n\n" +
    "[dagon_service]\n" +
    "use = False\n\n" +
    "[batch]\n" +
    "scratch_dir_base = /path/to/scratch/\n\n" +
    "# keep [loggers] [handlers] [formatters]", 11.5);
  [["[batch]", "local scratch and staging threads"], ["[slurm] [beeond]", "partition and BeeOND defaults"],
    ["[llm.*] [agent.*]", "named LLM and agent profiles"], ["[ec2] [gce] …", "optional cloud providers"]]
    .forEach(([h, b], i) => {
      const y = 1.3 + i * 0.66;
      k.box(s, 5.35, y, 1.75, 0.52, P.foam);
      k.text(s, h, { x: 5.35, y, w: 1.75, h: 0.52, fontFace: MONO, fontSize: 10.5, bold: true, color: P.deep,
        align: "center", valign: "middle" });
      k.text(s, b, { x: 7.25, y, w: 2.25, h: 0.52, fontSize: 13, valign: "middle" });
    });
  k.box(s, 0.5, 4.15, 9.0, 0.8, "F8E9E5");
  k.text(s, "Never commit credentials. Tokens and keys come from environment variables, e.g. DAGON_SKYCDS_API_TOKEN, or an agent profile's api_key_env.",
    { x: 0.7, y: 4.15, w: 8.6, h: 0.8, fontSize: 13, valign: "middle" });

  // 7 Verify environment ----------------------------------------------------
  s = k.slide(CONTENT, "Configure and verify", "Step 5 — Verify the environment (Lesson 00)",
    "9:00–10:00. Lesson 00 imports dagon, finds bash, reads dagon.ini.sample, checks that no API key is " +
    "committed, and lists the registered task types and optional packages. The output on the right is verbatim from " +
    "our run; your Python version, platform and optional packages may differ, but the fourteen task types must match.");
  k.code(s, 0.5, 1.3, 9.0, 0.55, "python examples/tutorial/lesson_00_environment_check.py", 12);
  k.code(s, 0.5, 2.05, 9.0, 1.35,
    "Python 3.12.10 on Darwin | dagonstar " + E.version + "\n" +
    "bash: /bin/bash\n" +
    "registered task types: agentic, apptainer, batch, checkpoint, cloud, docker, faas,\n" +
    "  iot, kubernetes, llm, native, nomad, slurm, web\n" +
    "optional packages present: cwltool, docker, globus_sdk, kubernetes, libcloud", 11);
  k.expect(s, 0.5, 3.6, 9.0, 1.35, "Exit status 0 and all " + E.taskTypes + " task types listed. \"optional packages present\" " +
    "depends on the extras you installed (\"none\" after a base install is correct).", 13);

  // 8 First workflow --------------------------------------------------------
  s = k.slide(CONTENT, "Configure and verify", "Step 6 — Run a first workflow",
    "10:00–11:30. The getting-started workflow: prepare writes a CSV, analyze counts its lines through a " +
    "workflow:// reference. make_dependencies() infers prepare→analyze. Each task gets a timestamped scratch " +
    "directory with a .dagon folder holding the launcher, context script, captured stdout and staged inputs. " +
    "Our run completed in " + E.firstWorkflowSeconds + " s; most of that is the engine's polling interval, not the commands.");
  k.code(s, 0.5, 1.3, 5.3, 2.3,
    "wf = Workflow(\"FirstWorkflow\")\n" +
    "prepare = DagonTask(TaskType.BATCH, \"prepare\",\n" +
    "  \"mkdir -p data; \"\n" +
    "  \"echo 'temperature,depth' > data/profile.csv; \"\n" +
    "  \"echo '18.5,12' >> data/profile.csv\")\n" +
    "analyze = DagonTask(TaskType.BATCH, \"analyze\",\n" +
    "  \"wc -l workflow:///prepare/data/profile.csv\"\n" +
    "  \" > summary.txt\")\n" +
    "wf.add_task(prepare); wf.add_task(analyze)\n" +
    "wf.make_dependencies(); wf.run()", 10.5);
  k.code(s, 0.5, 3.8, 5.3, 1.15,
    "<scratch>/1794842169829-prepare/\n<scratch>/1794842172279-analyze/\n  summary.txt\n  .dagon/  launcher.sh context.sh stdout.txt inputs/", 10);
  k.expect(s, 6.0, 1.3, 3.5, 3.65,
    "Log ends with:\nWorkflow 'FirstWorkflow' completed in ~5 s\n\nTwo scratch directories, prepare and analyze\n\n" +
    "summary.txt starts with 2 (two CSV lines), followed by the staged path", 13);

  // 9 Tests -----------------------------------------------------------------
  pres.addSection({ title: "Test and evaluate" });
  s = k.slide(CONTENT, "Test and evaluate", "Step 7 — Run the test suite",
    "11:30–13:30. The suite is local: it tests command generation, failure propagation, dependency discovery, " +
    "checkpoints, JSON and CWL, FAIR, pre-staging with a mock sbatch, and the agentic contract with a mock adapter. " +
    "Tracebacks printed during the run are expected: many tests exercise failure paths on purpose. Judge the final " +
    "summary line only. Start it in a second terminal; it took about " + E.unitTestMinutes + " minutes on our laptop.");
  k.code(s, 0.5, 1.3, 5.4, 2.0,
    "python -m unittest discover -s tests -v\n\n" +
    "# focused style and type checks, as in CI\n" +
    "python -m pip install ruff mypy\n" +
    "python -m ruff check dagon/shell.py dagon/agentic tests\n" +
    "python -m mypy --follow-imports=skip dagon/shell.py", 10.5);
  k.expect(s, 6.1, 1.3, 3.4, 2.0, "Final lines:\nRan " + E.unitTests + " tests in " + E.unitTestSeconds + "s\nOK" +
    (E.unitTestSkipped && E.unitTestSkipped !== "0" ? " (skipped=" + E.unitTestSkipped + ")" : ""), 13);
  k.stat(s, 0.5, 3.55, 2.8, E.unitTests, "tests, no network or live services");
  k.stat(s, 3.5, 3.55, 2.8, "~" + E.unitTestMinutes + " min", "wall clock, macOS laptop");
  k.stat(s, 6.5, 3.55, 3.0, E.taskTypes, "task types in the all-factory contract test");

  // 10 Examples and validators -----------------------------------------------
  s = k.slide(CONTENT, "Test and evaluate", "Run the examples and tutorial validators",
    "13:30–14:30. run_local_examples.py runs every self-contained local example with temporary scratch. The two " +
    "validators check the tutorial's structure, links and metadata, and that every TaskType and inventoried feature " +
    "maps to a lesson, an example and a test in docs/tutorial/coverage.json.");
  k.code(s, 0.5, 1.3, 5.4, 1.6,
    "python tools/run_local_examples.py\n" +
    "python tools/validate_tutorial.py\n" +
    "python tools/validate_tutorial_coverage.py", 12);
  k.expect(s, 6.1, 1.3, 3.4, 3.65, E.localExamples + " local examples pass (about " + E.localExamplesMinutes +
    " min)\n\nTutorial validator: exit 0\n\nCoverage validator: every task type mapped, exit 0", 13);
  k.card(s, 0.5, 3.1, 5.4, 1.85, "Why it matters",
    "Examples are the user-facing contract: if one fails, a lesson or README is out of date with the code",
    { fill: P.mist, bodySize: 14 });

  // 11 Evaluate: checkpoints and CWL ------------------------------------------
  s = k.slide(CONTENT, "Test and evaluate", "Evaluate: checkpoint reuse and CWL export",
    "14:30–16:00. Two behaviours to evaluate yourself. Lesson 07 runs a workflow, then resumes it from the " +
    "checkpoint file and confirms the scratch directory was reused rather than recomputed. Lesson 32 exports a " +
    "workflow to CWL v1.2 and, when cwltool is installed, validates it. The export is deterministic: re-running it " +
    "yields the same document with no scratch paths.");
  k.card(s, 0.5, 1.3, 4.4, 3.65, "Checkpoint and resume", "", { num: 1 });
  k.code(s, 0.7, 2.05, 4.0, 0.55, "python examples/tutorial/lesson_07_*.py", 10);
  k.expect(s, 0.7, 2.9, 4.0, 1.85, "checkpoint: <tmp>/checkpoint.json\nscratch reused: True", 12);
  k.card(s, 5.1, 1.3, 4.4, 3.65, "CWL v1.2 export", "", { num: 2 });
  k.code(s, 5.3, 2.05, 4.0, 0.55, "python examples/tutorial/lesson_29_*.py", 10);
  k.expect(s, 5.3, 2.9, 4.0, 1.85, "cwltool --validate: ok\nsteps: announce, measure, summarise\ndeterministic export, no scratch paths", 12);

  // 12 Evaluate: FAIR and pre-staging ----------------------------------------
  s = k.slide(CONTENT, "Test and evaluate", "Evaluate: FAIR metadata and pre-staging",
    "16:00–17:30. fair_local.py enables FAIR recording, runs a small workflow in temporary scratch, and checks " +
    "the exported files. pre_stage_mock.py runs a Slurm task twice, legacy and pre-staged, against a mock sbatch " +
    "and compares results. The core-hour figure is tiny because the mock stage-in takes a fraction of a second; " +
    "it is an estimate of allocation not held, not a measured saving. Results must be identical in both modes.");
  k.card(s, 0.5, 1.3, 4.4, 3.65, "FAIR recording", "", { num: 3 });
  k.code(s, 0.7, 2.05, 4.0, 0.7, "python examples/fair/fair_local.py", 10);
  k.expect(s, 0.7, 2.9, 4.0, 1.85, "FAIR metadata verified: checksums.sha256, codemeta.json, datacite.json, fairness-report.json, prov.json, report.html, report.md, ro-crate-metadata.json, run.json", 11);
  k.card(s, 5.1, 1.3, 4.4, 3.65, "Pre-staging, mock Slurm", "", { num: 4, nodeFill: P.amber });
  k.code(s, 5.3, 2.05, 4.0, 0.7, "python examples/dataflow/slurm/\\\n  pre_stage_mock.py", 10);
  k.expect(s, 5.3, 2.9, 4.0, 1.85, "Highest sea levels identical in both modes\nEstimated core-hours not held (200 cores): ~0.02\nVerification: ok", 12);

  // 13 Expected results at a glance -------------------------------------------
  s = k.slide(CONTENT, "Test and evaluate", "Expected results at a glance",
    "17:30–18:30. A checklist participants can keep. Every row was observed on " + E.observedOn + ".");
  const rows = [
    ["Step", "Command", "Expected"],
    ["Compile", "python -m py_compile dagon/*.py …", "silent, exit 0"],
    ["Build", "python -m build; twine check --strict", "sdist + wheel " + E.version + ", PASSED"],
    ["Verify", "lesson_00_environment_check.py", E.taskTypes + " task types listed"],
    ["First run", "python first_workflow.py", "completed in ~5 s; summary.txt = 2"],
    ["Unit tests", "unittest discover -s tests", "Ran " + E.unitTests + " tests … OK"],
    ["Examples", "tools/run_local_examples.py", E.localExamples + " examples pass"],
    ["Checkpoint", "lesson_07_checkpoint_and_resume.py", "scratch reused: True"],
    ["CWL", "lesson_32_cwl_export.py", "cwltool --validate: ok"],
    ["FAIR / pre-stage", "fair_local.py; pre_stage_mock.py", "metadata verified; Verification: ok"],
  ];
  s.addTable(rows.map((r, i) => r.map((c, j) => ({ text: c, options: { bold: i === 0 || j === 0,
    fontFace: j === 1 && i > 0 ? MONO : BODY, fontSize: j === 1 && i > 0 ? 10 : 12,
    color: i === 0 ? P.white : P.ink, fill: { color: i === 0 ? P.teal : (i % 2 ? P.mist : P.white) } } }))), {
    x: 0.5, y: 1.2, w: 9.0, colW: [1.6, 4.0, 3.4], rowH: 0.37, valign: "middle",
    border: { type: "solid", pt: 0.5, color: P.line }, margin: [0, 0.08, 0, 0.08] });

  // 14 Troubleshooting ---------------------------------------------------------
  s = k.slide(CONTENT, "Test and evaluate", "Troubleshooting",
    "18:30–19:15. The four problems most likely in a room of laptops. The pre-staging row is for participants " +
    "who later run on a real cluster: failure_phase tells you whether anything was submitted.");
  [["KeyError: 'formatters'", "dagon.ini lacks the logging sections: start again from cp dagon.ini.sample dagon.ini"],
    ["bash not found (Windows)", "Install Git for Windows, MSYS2, or Cygwin, or set DAGON_BASH to a bash executable"],
    ["Integration import error", "Install the matching extra, e.g. pip install -e \".[docker]\"; the error names it"],
    ["failure_phase == \"staging\"", "Stage-in failed and no job was submitted; read .dagon/stage_in.sh in the working dir"]]
    .forEach(([h, b], i) => k.card(s, 0.5 + (i % 2) * 4.6, 1.3 + Math.floor(i / 2) * 1.85, 4.4, 1.68, h, b,
      { num: i + 1, nodeFill: P.coral, headSize: 14, bodySize: 13 }));

  // 15 Next steps --------------------------------------------------------------
  pres.addSection({ title: "Closing" });
  s = k.slide("Closing (dark)", "Closing", "Where to go next",
    "19:15–20:00. Point to the 33-lesson tutorial and its six modules, the examples catalog and the platform " +
    "support page. Infrastructure lessons (Docker to data movers) run against mocks locally and need a real site " +
    "only for live runs.");
  [["Tutorial", E.lessons + " lessons, 00–35, each with a self-checking script in examples/tutorial/"],
    ["Documentation", "docs/getting_started.md, configuration.md, user_guide.md, architecture.md"],
    ["Real infrastructure", "Lessons 17–28: Docker, Apptainer, Kubernetes, Nomad, SSH, cloud, Slurm, BeeOND"]]
    .forEach(([h, b], i) => {
      const y = 1.45 + i * 0.95;
      k.node(s, 0.6, y, 0.6, String(i + 1), i === 0 ? P.amber : P.teal, i === 0 ? P.deep : P.white, 16);
      k.text(s, h, { x: 1.4, y: y - 0.02, w: 5.0, h: 0.34, fontSize: 16, bold: true, color: P.white });
      k.text(s, b, { x: 1.4, y: y + 0.33, w: 5.0, h: 0.45, fontSize: 13, color: P.seaLight });
    });
  k.dagMark(s, 7.05, 1.35, 0.9);
  k.text(s, "github.com/DagOnStar/dagonstar  ·  Questions?", { x: 0.6, y: 4.6, w: 8.9, h: 0.35, fontSize: 13,
    color: P.amber });

  const file = path.join(OUT_DIR, "dagonstar_tutorial.pptx");
  return save(pres, file);
}

(async () => {
  for (const f of [await buildScientific(), await buildTutorial()]) console.log("wrote", f);
})().catch((err) => { console.error(err); process.exit(1); });
