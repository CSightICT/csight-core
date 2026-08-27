import { readFile, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const temporaryOutput = join(tmpdir(), `csight-openapi-${process.pid}.ts`);

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", shell: process.platform === "win32" });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}`)));
  });
}

try {
  await run(process.platform === "win32" ? "npx.cmd" : "npx", [
    "--no-install", "openapi-typescript", "./src/api/openapi.snapshot.json", "-o", temporaryOutput,
  ]);
  const rawActual = await readFile(temporaryOutput, "utf8");
  await import("node:fs/promises").then(({ writeFile }) => writeFile(
    temporaryOutput,
    `// @ts-nocheck -- FastAPI emits recursive JsonValue schemas; keep generated declarations verbatim.\n${rawActual}`,
    "utf8",
  ));
  const [expected, actual] = await Promise.all([
    readFile("./src/api/openapi.generated.ts", "utf8"),
    readFile(temporaryOutput, "utf8"),
  ]);
  if (expected !== actual) {
    throw new Error("OpenAPI generated types are stale. Run npm run generate:api and commit the result.");
  }
  process.stdout.write("OpenAPI snapshot and generated types are in sync.\n");
} finally {
  await rm(temporaryOutput, { force: true });
}
