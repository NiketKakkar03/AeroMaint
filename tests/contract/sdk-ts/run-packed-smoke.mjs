import { execFileSync } from "node:child_process";
import {
  copyFileSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  writeFileSync
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../..");
const consumer = mkdtempSync(join(tmpdir(), "aeromaint-sdk-consumer-"));
const environment = {
  ...process.env,
  CI: "true",
  npm_config_offline: "true",
  npm_config_cache: join(consumer, ".npm-cache")
};

function run(command, args, cwd) {
  execFileSync(command, args, { cwd, env: environment, stdio: "inherit" });
}

run("pnpm", ["--filter", "@aeromaint/contracts", "build"], root);
run("pnpm", ["--filter", "@aeromaint/capture-sdk", "build"], root);
run(
  "pnpm",
  ["pack", "--pack-destination", consumer],
  join(root, "packages/contracts")
);
run(
  "pnpm",
  ["pack", "--pack-destination", consumer],
  join(root, "packages/capture-sdk-ts")
);

const archives = readdirSync(consumer).filter((name) => name.endsWith(".tgz"));
if (archives.length !== 2)
  throw new Error("Expected contracts and SDK package archives");
const contractsArchive = archives.find((name) => name.includes("contracts"));
const sdkArchive = archives.find((name) => name.includes("capture-sdk"));
if (!contractsArchive || !sdkArchive)
  throw new Error("Could not identify the packed contracts and SDK archives");
writeFileSync(
  join(consumer, "package.json"),
  JSON.stringify(
    {
      private: true,
      type: "module",
      dependencies: {
        "@aeromaint/contracts": `file:./${contractsArchive}`,
        "@aeromaint/capture-sdk": `file:./${sdkArchive}`
      }
    },
    null,
    2
  )
);
run("npm", ["install", "--offline", "--ignore-scripts"], consumer);
copyFileSync(
  join(here, "packed-smoke.mjs"),
  join(consumer, "packed-smoke.mjs")
);
run(process.execPath, ["packed-smoke.mjs"], consumer);

const installed = JSON.parse(
  readFileSync(join(consumer, "package.json"), "utf8")
);
if (!installed.dependencies?.["@aeromaint/capture-sdk"])
  throw new Error("Clean consumer did not install the capture SDK");
process.stdout.write(`clean packed consumer passed: ${consumer}\n`);
