import { readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", shell: process.platform === "win32" });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}`)));
  });
}

const output = "./src/api/openapi.generated.ts";
await run(process.platform === "win32" ? "npx.cmd" : "npx", [
  "--no-install", "openapi-typescript", "./src/api/openapi.snapshot.json", "-o", output,
]);
const generated = await readFile(output, "utf8");
await writeFile(output, `// @ts-nocheck -- FastAPI emits recursive JsonValue schemas; keep generated declarations verbatim.\n${generated}`, "utf8");
