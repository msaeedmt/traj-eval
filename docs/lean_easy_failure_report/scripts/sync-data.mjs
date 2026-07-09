import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const reportRoot = resolve(here, "..");
const repoRoot = resolve(reportRoot, "..", "..");
const source = resolve(repoRoot, "data", "analysis", "lean_easy_failure_patterns.csv");
const target = resolve(reportRoot, "public", "data", "lean_easy_failure_patterns.csv");

if (!existsSync(source)) {
  throw new Error(
    `Missing ${source}. Run "python scripts/analyze_lean_easy_failures.py" from the repo root first.`,
  );
}

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`synced ${source} -> ${target}`);
