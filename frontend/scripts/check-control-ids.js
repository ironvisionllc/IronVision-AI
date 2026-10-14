#!/usr/bin/env node
// Guard: control IDs must be displayed via fmtControl (eMASS/NIST form AC-2(3)), never raw "ac-2.3" / "AC-2.3".
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "src");
const BAD = [
  [/(control_id|controlId|parent_control_id)\??\.toUpperCase\(\)/, "use fmtControl() instead of toUpperCase() on control ids"],
  [/>[^<{]*\b[A-Z]{2}-\d+\.\d+\b[^<]*</, 'literal dotted control id like "AC-2.3" in JSX text'],
];
const files = [];
(function walk(d) {
  for (const f of fs.readdirSync(d)) {
    const p = path.join(d, f);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (/\.(tsx|ts)$/.test(f) && !p.includes(`${path.sep}components${path.sep}ui${path.sep}`)) files.push(p);
  }
})(SRC);
let bad = 0;
for (const f of files) {
  fs.readFileSync(f, "utf8").split("\n").forEach((line, i) => {
    for (const [rx, msg] of BAD) if (rx.test(line)) { console.error(`${path.relative(SRC, f)}:${i + 1}: ${msg}`); bad++; }
  });
}
// fmtControl contract
const fmt = (id) => { const [b, ...e] = id.split("."); return b.toUpperCase() + e.map((x) => `(${x})`).join(""); };
const cases = { "ac-2.3": "AC-2(3)", "ac-17.2": "AC-17(2)", "ra-5": "RA-5" };
for (const [k, v] of Object.entries(cases)) if (fmt(k) !== v) { console.error(`fmtControl(${k}) != ${v}`); bad++; }
const lib = fs.readFileSync(path.join(SRC, "lib", "format.ts"), "utf8");
if (!lib.includes("export function fmtControl")) { console.error("lib/format.ts must export fmtControl"); bad++; }
if (bad) { console.error(`control-id format guard: ${bad} problem(s)`); process.exit(1); }
console.log(`control-id format guard: OK (${files.length} files)`);
