import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const projectDir = path.dirname(fileURLToPath(import.meta.url));
const runtimeModules = process.env.RUNTIME_NODE_MODULES;
const runtimePython = process.env.RUNTIME_PYTHON;
const skillDir = process.env.SKILL_DIR;
const qaDir = process.env.QA_DIR;
if (![runtimeModules, runtimePython, skillDir, qaDir].every(value => value && path.isAbsolute(value))) {
  throw new Error("Set RUNTIME_NODE_MODULES, RUNTIME_PYTHON, SKILL_DIR and QA_DIR to absolute paths");
}

const { Presentation, PresentationFile } = await import(pathToFileURL(
  path.join(runtimeModules, "@oai/artifact-tool/dist/artifact_tool.mjs"),
).href);
const { finalizePresentation } = await import(pathToFileURL(
  path.join(skillDir, "container_tools/artifact_tool_utils.mjs"),
).href);

const yamlReader = [
  "import json,pathlib,sys,yaml",
  "root=pathlib.Path(sys.argv[1])",
  "manifest=yaml.safe_load((root/'deck.pptd').read_text(encoding='utf-8'))",
  "pages=[yaml.safe_load((root/name).read_text(encoding='utf-8')) for name in manifest['pages']]",
  "print(json.dumps({'manifest':manifest,'pages':pages},ensure_ascii=False))",
].join(";");
const parsed = spawnSync(runtimePython, ["-c", yamlReader, projectDir], {
  encoding: "utf8", maxBuffer: 2_000_000,
  env: { ...process.env, PYTHONPATH: path.join(process.cwd(), ".venv", "Lib", "site-packages"), PYTHONIOENCODING: "utf-8" },
});
if (parsed.status !== 0) throw new Error(parsed.stderr || "Cannot parse PPTD");
const { manifest, pages } = JSON.parse(parsed.stdout);
const palette = manifest.theme.colors;
const styles = manifest.theme.textStyles;
const resolveColor = value => value?.startsWith("$") ? palette[value.slice(1)] : value;
const presentation = Presentation.create({
  slideSize: { width: manifest.size[0], height: manifest.size[1] },
});
const builtSlides = [];

for (const page of pages) {
  const slide = presentation.slides.add();
  builtSlides.push(slide);
  slide.background.fill = resolveColor(page.background?.color ?? "#FFFFFF");
  for (const element of page.elements) {
    const [left, top, width, height] = element.bounds;
    if (element.elementType === "shape") {
      slide.shapes.add({
        geometry: element.shapeName,
        name: element.elementId,
        position: { left, top, width, height },
        fill: resolveColor(element.fill?.color ?? "none"),
        line: { style: "solid", fill: "none", width: 0 },
      });
    } else if (element.elementType === "text") {
      const source = element.content;
      const inherited = source.style ? styles[source.style.slice(1)] : {};
      const style = { ...inherited, ...source };
      const shape = slide.shapes.add({
        geometry: "textbox",
        name: element.elementId,
        position: { left, top, width, height },
        fill: "none",
        line: { style: "solid", fill: "none", width: 0 },
      });
      shape.text = style.text;
      shape.text.style = {
        typeface: style.fontFamily ?? "Arial",
        fontSize: style.fontSize ?? 18,
        bold: style.bold ?? false,
        color: resolveColor(style.color ?? "#202326"),
        alignment: style.align?.[0] ?? "left",
        verticalAlignment: style.align?.[1] ?? "top",
        autoFit: "none",
        wrap: style.wrap === false ? "none" : "square",
        insets: { left: 0, right: 0, top: 0, bottom: 0 },
      };
    } else {
      throw new Error(`Unsupported PPTD element: ${element.elementType}`);
    }
  }
}

await fs.mkdir(qaDir, { recursive: true });
for (let index = 0; index < pages.length; index += 1) {
  const preview = await presentation.export({ slide: builtSlides[index], format: "png", scale: 1 });
  await fs.writeFile(path.join(qaDir, `slide-${index + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const stagingDir = path.join(qaDir, "staging");
await fs.mkdir(stagingDir, { recursive: true });
const candidatePath = path.join(stagingDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const fade = spawnSync(runtimePython, [path.join(projectDir, "add_fade.py"), candidatePath], {
  encoding: "utf8",
});
if (fade.status !== 0) throw new Error(fade.stderr || "Cannot add slide transitions");
const finalPath = path.join(projectDir, "deck.pptx");
const result = await finalizePresentation({
  workspaceDir: process.cwd(),
  candidatePath,
  finalPath,
  pythonExecutable: runtimePython,
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "9144000,5143500", "--validate-heading-fit"],
  explicitTotalSlideCount: pages.length,
  requiredNativeTableOwnerSlides: [],
  requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: "design", families: ["Arial", "Consolas"] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "deck-v2.validation.json"),
});
console.log(JSON.stringify({ pages: pages.length, finalPath, qaDir, result }, null, 2));
