#!/usr/bin/env node
/**
 * verify-build.mjs
 *
 * Acceptance criterion [T] for Task 1.1:
 *   "npm run build emits a static dist/; prove dist/index.html + hashed asset files exist."
 *
 * Runs: node scripts/verify-build.mjs  (after npm run build)
 * Exit 0 = all assertions pass. Exit 1 = at least one failure.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, "../dist");

let failures = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  PASS  ${message}`);
  } else {
    console.error(`  FAIL  ${message}`);
    failures++;
  }
}

console.log(`\nVerifying build output in: ${DIST}\n`);

// 1. dist/ directory exists
assert(fs.existsSync(DIST), "dist/ directory exists");

// 2. dist/index.html exists and is non-empty
const indexHtml = path.join(DIST, "index.html");
assert(fs.existsSync(indexHtml), "dist/index.html exists");
if (fs.existsSync(indexHtml)) {
  const size = fs.statSync(indexHtml).size;
  assert(size > 0, `dist/index.html is non-empty (${size} bytes)`);
}

// 3. dist/assets/ contains at least one hashed JS file
const assetsDir = path.join(DIST, "assets");
assert(fs.existsSync(assetsDir), "dist/assets/ directory exists");

if (fs.existsSync(assetsDir)) {
  const files = fs.readdirSync(assetsDir);

  // Hashed assets follow the pattern: <name>-<hash>.<ext>
  const hashedPattern = /^.+-[A-Za-z0-9]{8,}\.(js|css|svg|png|woff2?)$/;

  const hashedJs = files.filter((f) => /^.+-[A-Za-z0-9]{8,}\.js$/.test(f));
  const hashedCss = files.filter((f) => /^.+-[A-Za-z0-9]{8,}\.css$/.test(f));
  const anyHashed = files.filter((f) => hashedPattern.test(f));

  assert(
    hashedJs.length >= 1,
    `dist/assets/ contains ≥1 hashed JS file (found: ${hashedJs.join(", ") || "none"})`
  );
  assert(
    hashedCss.length >= 1,
    `dist/assets/ contains ≥1 hashed CSS file (found: ${hashedCss.join(", ") || "none"})`
  );
  assert(
    anyHashed.length >= 2,
    `dist/assets/ contains ≥2 hashed asset files (found ${anyHashed.length}: ${anyHashed.join(", ")})`
  );

  // 4. Spot-check: the JS entry is referenced in index.html
  const indexContent = fs.readFileSync(indexHtml, "utf8");
  const jsEntryInHtml = hashedJs.some((f) => indexContent.includes(f));
  assert(
    jsEntryInHtml,
    `index.html references the hashed JS entry (checked: ${hashedJs.join(", ")})`
  );
}

console.log(
  `\n${failures === 0 ? "All assertions passed." : `${failures} assertion(s) FAILED.`}\n`
);
process.exit(failures === 0 ? 0 : 1);
