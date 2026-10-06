#!/usr/bin/env node
// Runs a script from backend/ with a Python that has the backend's dependencies.
//
//   node scripts/run-python.mjs save_auth.py
//
// `python` does not exist on a stock macOS (only `python3`), and the dependencies live in a virtualenv,
// so the npm scripts for the backend go through here instead of calling `python` directly. Looks for a
// virtualenv in backend/.venv or .venv first, then python3, then python.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = process.env.SARD_ROOT ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const backend = path.join(root, "backend");

const candidates = [
  path.join(backend, ".venv", "bin", "python"),
  path.join(backend, ".venv", "Scripts", "python.exe"),
  path.join(root, ".venv", "bin", "python"),
  path.join(root, ".venv", "Scripts", "python.exe"),
  "python3",
  "python",
];

function runs(python, args) {
  const result = spawnSync(python, args, { stdio: "pipe" });
  return !result.error && result.status === 0;
}

// An absolute path must exist; a bare name is looked up on PATH by spawn.
const available = candidates.filter((candidate) => !path.isAbsolute(candidate) || existsSync(candidate)).filter((candidate) => runs(candidate, ["--version"]));
const usable = available.find((candidate) => runs(candidate, ["-c", "import playwright, fastapi, pydantic_settings"]));

if (!usable) {
  const found = available.length ? `Found ${available[0]}, but it is missing the backend's packages.` : "No Python was found.";
  console.error(`${found}

Set up the backend once:

  cd backend
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
  .venv/bin/playwright install chromium
`);
  process.exit(1);
}

const [script, ...args] = process.argv.slice(2);
if (!script) {
  console.error("Usage: node scripts/run-python.mjs <script.py> [args]");
  process.exit(2);
}

const child = spawnSync(usable, [script, ...args], { cwd: backend, stdio: "inherit" });
process.exit(child.status ?? 1);
