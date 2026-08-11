import { execFileSync } from "node:child_process";
import {
  cpSync,
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
const clean = mkdtempSync(join(tmpdir(), "aeromaint-react-consumer-"));
const env = {
  ...process.env,
  npm_config_offline: "true",
  npm_config_cache: join(clean, ".npm-cache"),
  npm_config_audit: "false",
  npm_config_fund: "false",
  NODE_PATH: ""
};
const run = (command, args, cwd) =>
  execFileSync(command, args, { cwd, env, stdio: "inherit" });

const tsc = join(root, "node_modules/typescript/bin/tsc");
run(
  process.execPath,
  [tsc, "-p", join(root, "packages/contracts/tsconfig.json")],
  root
);
run(
  process.execPath,
  [tsc, "-p", join(root, "packages/capture-sdk-ts/tsconfig.json")],
  root
);
const exampleBuildConfig = join(clean, "example-tsconfig.json");
writeFileSync(
  exampleBuildConfig,
  JSON.stringify({
    extends: join(root, "tsconfig.base.json"),
    compilerOptions: {
      outDir: join(root, "examples/react-minimal-viewer/dist"),
      rootDir: join(root, "examples/react-minimal-viewer/src"),
      declaration: true,
      jsx: "react-jsx",
      baseUrl: root,
      paths: {
        "@aeromaint/capture-sdk": ["packages/capture-sdk-ts/dist/index.d.ts"],
        react: ["apps/viewer/node_modules/@types/react/index.d.ts"],
        "react/jsx-runtime": [
          "apps/viewer/node_modules/@types/react/jsx-runtime.d.ts"
        ]
      }
    },
    include: [join(root, "examples/react-minimal-viewer/src")]
  })
);
run(process.execPath, [tsc, "-p", exampleBuildConfig], root);

function pack(source, files, dependencies = {}, peerDependencies = undefined) {
  const manifest = JSON.parse(
    readFileSync(join(source, "package.json"), "utf8")
  );
  const stage = join(clean, `.pack-${manifest.name.replaceAll("/", "-")}`);
  mkdirSync(stage);
  for (const file of files)
    cpSync(join(source, file), join(stage, file), { recursive: true });
  writeFileSync(
    join(stage, "package.json"),
    JSON.stringify(
      {
        ...manifest,
        dependencies,
        ...(peerDependencies ? { peerDependencies } : {})
      },
      null,
      2
    )
  );
  run("npm", ["pack", "--pack-destination", clean], stage);
}
pack(join(root, "packages/contracts"), ["dist"]);
pack(join(root, "packages/capture-sdk-ts"), ["dist", "README.md"], {
  "@aeromaint/contracts": "^1.0.0"
});
pack(join(root, "examples/react-minimal-viewer"), ["dist", "README.md"], {
  "@aeromaint/capture-sdk": "^1.0.0",
  react: ">=19"
});
run(
  "npm",
  [
    "pack",
    join(root, "apps/viewer/node_modules/react"),
    "--pack-destination",
    clean
  ],
  clean
);

const archives = readdirSync(clean).filter((name) => name.endsWith(".tgz"));
const locate = (part) => archives.find((name) => name.includes(part));
const contracts = locate("contracts");
const sdk = locate("capture-sdk");
const viewer = locate("react-minimal-viewer");
const react = locate("react-19");
if (!contracts || !sdk || !viewer || !react)
  throw new Error(`Missing archive: ${archives.join(", ")}`);
for (const archive of [contracts, sdk, viewer]) {
  const entries = execFileSync("tar", ["-tzf", join(clean, archive)], {
    encoding: "utf8"
  });
  if (!entries.includes("package/dist/") || entries.includes("package/src/"))
    throw new Error(`Bad package contents: ${archive}`);
}
writeFileSync(
  join(clean, "package.json"),
  JSON.stringify(
    {
      private: true,
      type: "module",
      dependencies: {
        "@aeromaint/contracts": `file:./${contracts}`,
        "@aeromaint/capture-sdk": `file:./${sdk}`,
        "@aeromaint/react-minimal-viewer": `file:./${viewer}`,
        react: `file:./${react}`
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
    "--legacy-peer-deps",
    "--ignore-scripts",
    "--no-audit",
    "--no-fund",
    "--package-lock=false"
  ],
  clean
);
cpSync(join(here, "packed-smoke.mjs"), join(clean, "packed-smoke.mjs"));
run(process.execPath, ["packed-smoke.mjs"], clean);
process.stdout.write(`clean packed React consumer passed: ${clean}\n`);
