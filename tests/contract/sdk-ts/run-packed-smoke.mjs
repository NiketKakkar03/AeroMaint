import { execFileSync } from "node:child_process";
import {
  cpSync,
  copyFileSync,
  mkdirSync,
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
const npmCache = mkdtempSync(join(tmpdir(), "aeromaint-sdk-npm-cache-"));
const environment = {
  ...process.env,
  CI: "true",
  npm_config_offline: "true",
  npm_config_cache: npmCache,
  npm_config_audit: "false",
  npm_config_fund: "false",
  NODE_PATH: ""
};

function run(command, args, cwd) {
  execFileSync(command, args, { cwd, env: environment, stdio: "inherit" });
}

function packPackage(source, files, dependencies = {}) {
  const manifest = JSON.parse(
    readFileSync(join(source, "package.json"), "utf8")
  );
  const stage = join(consumer, `.pack-${manifest.name.replaceAll("/", "-")}`);
  mkdirSync(stage);
  for (const file of files)
    cpSync(join(source, file), join(stage, file), { recursive: true });
  writeFileSync(
    join(stage, "package.json"),
    `${JSON.stringify({ ...manifest, dependencies }, null, 2)}\n`
  );
  run("npm", ["pack", "--pack-destination", consumer], stage);
}

run("tsc", ["-p", join(root, "packages/contracts/tsconfig.json")], root);
run("tsc", ["-p", join(root, "packages/capture-sdk-ts/tsconfig.json")], root);
run(
  "tsc",
  ["-p", join(root, "examples/typescript-export-cli/tsconfig.json")],
  root
);
packPackage(join(root, "packages/contracts"), ["dist"]);
packPackage(join(root, "packages/capture-sdk-ts"), ["dist", "README.md"], {
  "@aeromaint/contracts": "^1.0.0"
});
packPackage(join(root, "examples/typescript-export-cli"), ["dist"], {
  "@aeromaint/capture-sdk": "^1.0.0"
});

const archives = readdirSync(consumer).filter((name) => name.endsWith(".tgz"));
if (archives.length !== 3)
  throw new Error("Expected contracts, SDK, and CLI package archives");
const contractsArchive = archives.find((name) => name.includes("contracts"));
const sdkArchive = archives.find((name) => name.includes("capture-sdk"));
const cliArchive = archives.find((name) => name.includes("export-cli"));
if (!contractsArchive || !sdkArchive || !cliArchive)
  throw new Error("Could not identify all packed package archives");

function assertPackageContents(archive, required) {
  const entries = execFileSync("tar", ["-tzf", join(consumer, archive)], {
    encoding: "utf8"
  })
    .trim()
    .split("\n");
  for (const path of required) {
    if (!entries.includes(`package/${path}`))
      throw new Error(`${archive} does not contain ${path}`);
  }
  if (entries.some((entry) => entry.startsWith("package/src/")))
    throw new Error(`${archive} unexpectedly contains TypeScript sources`);
}

assertPackageContents(contractsArchive, [
  "package.json",
  "dist/index.js",
  "dist/index.d.ts"
]);
assertPackageContents(sdkArchive, [
  "package.json",
  "README.md",
  "dist/index.js",
  "dist/index.d.ts"
]);
assertPackageContents(cliArchive, ["package.json", "dist/cli.js"]);
writeFileSync(
  join(consumer, "package.json"),
  JSON.stringify(
    {
      private: true,
      type: "module",
      dependencies: {
        "@aeromaint/contracts": `file:./${contractsArchive}`,
        "@aeromaint/capture-sdk": `file:./${sdkArchive}`,
        "@aeromaint/typescript-export-cli": `file:./${cliArchive}`
      }
    },
    null,
    2
  )
);
run(
  "npm",
  [
    "install",
    "--offline",
    "--ignore-scripts",
    "--no-audit",
    "--no-fund",
    "--package-lock=false"
  ],
  consumer
);
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
