import { writeFile } from "node:fs/promises";

const source = process.env.CSIGHT_OPENAPI_URL ?? "http://127.0.0.1:8000/openapi.json";
const response = await fetch(source, { headers: { Accept: "application/json" } });
if (!response.ok) throw new Error(`Could not fetch ${source}: HTTP ${response.status}`);
const document = await response.json();
if (document?.openapi === undefined || document?.paths === undefined) {
  throw new Error(`${source} did not return an OpenAPI document.`);
}
await writeFile("./src/api/openapi.snapshot.json", `${JSON.stringify(document, null, 2)}\n`, "utf8");
process.stdout.write(`Refreshed src/api/openapi.snapshot.json from ${source}.\nRun npm run generate:api next.\n`);
