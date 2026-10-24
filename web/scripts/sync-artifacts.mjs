// Copy pipeline + eval outputs into public/demo so the dashboard works as a static site
// (offline replay). Run `acc run world/` and `python -m eval.crosstenant` first.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = join(root, "web", "public", "demo");
mkdirSync(out, { recursive: true });

const files = {
  "artifacts/catalog.json": "catalog.json",
  "artifacts/invariants.json": "invariants.json",
  "artifacts/verify.json": "verify.json",
  "artifacts/verify_details.json": "verify_details.json",
  "artifacts/reachability.json": "reachability.json",
  "artifacts/run.json": "run.json",
  "artifacts/export/progent.json": "progent.json",
  "artifacts/export/assay.yaml": "assay.yaml",
  "eval/results/crosstenant.json": "crosstenant.json",
  "eval/results/agentdojo.json": "agentdojo.json",
};
for (const [src, dst] of Object.entries(files)) {
  const from = join(root, src);
  if (!existsSync(from)) throw new Error(`missing ${src}: run the pipeline first`);
  copyFileSync(from, join(out, dst));
}
// policy.yaml -> JSON via the Python package so the browser needs no YAML parser
import { execFileSync } from "node:child_process";
const python = join(root, ".venv", "bin", "python");
const policy = execFileSync(python, ["-c",
  "import json,sys,yaml;print(json.dumps(yaml.safe_load(open(sys.argv[1]))))",
  join(root, "artifacts", "policy.yaml")]).toString();
writeFileSync(join(out, "policy.json"), policy);
const hook = readFileSync(join(root, "artifacts", "export", "acc_hook.py"), "utf8");
writeFileSync(join(out, "acc_hook.py.txt"), hook);
const live = join(root, "eval", "results", "live", "summary.json");
if (existsSync(live)) copyFileSync(live, join(out, "live_summary.json"));
execFileSync(python, ["-m", "api.record_demo", join(out, "live.json")], { cwd: root, stdio: "ignore" });
console.log(`synced ${Object.keys(files).length + 2} files to web/public/demo`);
