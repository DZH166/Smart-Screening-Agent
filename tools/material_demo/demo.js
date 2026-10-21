/* Isolated UI prototype. No provider requests, credentials, server uploads or
   production APIs. The only generated files are PNGs of the built-in artwork. */
"use strict";
const $ = (id) => document.getElementById(id);
const originals = [
  {
    id: "orange-bear",
    label: "橘子小熊",
    bounds: { x: 24, y: 78, width: 272, height: 272 },
  },
  {
    id: "mint-cat",
    label: "薄荷小猫",
    bounds: { x: 344, y: 78, width: 272, height: 272 },
  },
  {
    id: "sunshine",
    label: "SUNSHINE 文字设计",
    bounds: { x: 664, y: 78, width: 272, height: 272 },
  },
  {
    id: "flower",
    label: "春日小花",
    bounds: { x: 24, y: 400, width: 272, height: 272 },
  },
  {
    id: "rocket",
    label: "漫游小火箭",
    bounds: { x: 344, y: 400, width: 272, height: 272 },
  },
  {
    id: "cherry",
    label: "双生樱桃",
    bounds: { x: 664, y: 400, width: 272, height: 272 },
  },
];
const items = new Map(
  originals.map((item) => [item.id, { ...item, bounds: { ...item.bounds } }]),
);
const state = {
  page: "material",
  phase: "upload",
  step: 0,
  available: new Set(items.keys()),
  selected: new Set(items.keys()),
  focused: "orange-bear",
  removed: [],
  edits: new Map(),
  localUrl: null,
  previewRevision: 0,
  downloadBusy: false,
  editor: null,
  tool: "bounds",
};
let toastTimer;
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4200);
}
function escapeHtml(text) {
  return String(text).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
function assetUrl(id) {
  return `assets/${id}.svg`;
}
function safeName(text) {
  return (
    String(text)
      .replace(/[\x00-\x1f<>:"/\\|?*]/g, "_")
      .replace(/[ .]+$/g, "")
      .slice(0, 70) || "示例素材"
  );
}
function setBox(id, bounds) {
  for (const [name, value] of Object.entries(bounds))
    $(id).setAttribute(name, String(value));
}
function render() {
  for (const page of ["material", "numbering", "admin"])
    $(page + "-page").hidden = state.page !== page;
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === state.page);
    if (button.dataset.page === state.page)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  for (const phase of ["upload", "process", "results"])
    $(phase + "-view").hidden = state.phase !== phase;
  const phaseIndex = { upload: 0, process: 1, results: 2 }[state.phase];
  $("step-indicator")
    .querySelectorAll("span")
    .forEach((el, index) =>
      el.classList.toggle("current", index === phaseIndex),
    );
  if (state.phase === "process") renderProcess();
  if (state.phase === "results") renderResults();
  document.title =
    { material: "素材提取", numbering: "图片编号", admin: "统一管理" }[
      state.page
    ] + " · 智筛 Agent 交互演示";
}
function renderProcess() {
  const titles = ["识别完整设计", "分离背景与处理水印", "生成独立素材"];
  const descriptions = [
    "人物、文字和配件属于同一设计时，保持为一个整体。",
    "演示仅说明修复位置，不执行真实抠图或去水印。",
    "接下来查看内置示例，体验选择、局部修正和下载。",
  ];
  $("process-title").textContent = titles[state.step];
  $("process-description").textContent = descriptions[state.step];
  $("next-step").textContent = [
    "下一步：处理水印 →",
    "下一步：生成素材 →",
    "查看示例结果 →",
  ][state.step];
  $("process-steps")
    .querySelectorAll("li")
    .forEach((el, index) => {
      el.classList.toggle("current", index === state.step);
      el.classList.toggle("done", index < state.step);
    });
}
function renderResults() {
  const focusedElement = document.activeElement,
    focusedCard = focusedElement?.closest?.("[data-asset-id]");
  const focusTarget = focusedCard
    ? {
        id: focusedCard.dataset.assetId,
        select: focusedElement.dataset.select,
        action: focusedElement.dataset.action,
      }
    : null;
  const visible = [...state.available].map((id) => items.get(id));
  $("asset-grid").innerHTML = visible
    .map(
      (item) =>
        `<article class="asset-card${item.id === state.focused ? " focused" : ""}" data-asset-id="${item.id}"><label class="asset-select"><input type="checkbox" data-select="${item.id}" aria-label="选择${escapeHtml(item.label)}" ${state.selected.has(item.id) ? "checked" : ""}></label><button class="asset-image checker" type="button" data-action="view" aria-label="放大对照${escapeHtml(item.label)}"><img src="${assetUrl(item.id)}" alt="${escapeHtml(item.label)}，内置合成示例"></button><div class="asset-body"><span class="asset-name">${escapeHtml(item.label)}</span><div class="asset-meta"><span>320 × 320 · 透明 PNG</span>${state.edits.has(item.id) ? "<em>有修正方案</em>" : "<span>示例</span>"}</div><div class="asset-actions"><button class="text-button" type="button" data-action="edit">局部修正</button><button class="text-button" type="button" data-action="download">下载</button><button class="text-button remove" type="button" data-action="remove" aria-label="移除${escapeHtml(item.label)}">移除</button></div></div></article>`,
    )
    .join("");
  $("result-count").textContent = String(visible.length);
  renderSelection();
  $("undo-remove").hidden = !state.removed.length;
  $("empty-results").hidden = !!visible.length;
  $("edit-reminder").hidden = !state.edits.size;
  renderFocus();
  if (focusTarget && state.available.has(focusTarget.id)) {
    const selector = focusTarget.select
      ? `[data-select="${focusTarget.id}"]`
      : `[data-asset-id="${focusTarget.id}"] [data-action="${focusTarget.action}"]`;
    document.querySelector(selector)?.focus({ preventScroll: true });
  } else if (focusTarget && state.removed.length)
    $("undo-remove").focus({ preventScroll: true });
}
function renderSelection() {
  $("selected-count").textContent = `已选择 ${state.selected.size} 个示例素材`;
  $("select-all").textContent =
    state.selected.size === state.available.size && state.available.size
      ? "取消全选"
      : "全选";
  $("download-all").disabled = !state.selected.size || state.downloadBusy;
  $("download-all").querySelector("span").textContent = state.downloadBusy
    ? "正在准备示例…"
    : "下载示例 ZIP";
}
function renderFocus() {
  const item = items.get(state.focused);
  if (!item || !state.available.has(item.id)) {
    setBox("source-box", { x: 0, y: 0, width: 0, height: 0 });
    $("source-location").textContent = "点击右侧素材，查看它在原图中的位置。";
    return;
  }
  setBox("source-box", state.edits.get(item.id)?.bounds || item.bounds);
  $("source-location").textContent =
    `当前查看：${item.label}${state.edits.has(item.id) ? "（框选方案已调整）" : ""}`;
}
function focusAsset(id) {
  state.focused = id;
  renderFocus();
  document
    .querySelectorAll(".asset-card")
    .forEach((card) =>
      card.classList.toggle("focused", card.dataset.assetId === id),
    );
}
function beginDemo() {
  state.phase = "process";
  state.step = 0;
  state.available = new Set(items.keys());
  state.selected = new Set(items.keys());
  state.edits.clear();
  state.removed = [];
  for (const original of originals)
    items.get(original.id).label = original.label;
  state.focused = originals[0].id;
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
  $("next-step").focus({ preventScroll: true });
}
function reset() {
  state.phase = "upload";
  state.step = 0;
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
  $("start-demo").focus({ preventScroll: true });
}
async function previewFile(file) {
  if (!file) return;
  const revision = ++state.previewRevision;
  $("file-error").hidden = true;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    $("file-error").textContent = "请选择 PNG、JPG 或 WebP 图片。";
    $("file-error").hidden = false;
    return;
  }
  const url = URL.createObjectURL(file);
  try {
    const image = await loadImage(url);
    if (revision !== state.previewRevision) {
      URL.revokeObjectURL(url);
      return;
    }
    if (state.localUrl) URL.revokeObjectURL(state.localUrl);
    state.localUrl = url;
    $("local-preview").src = url;
    $("local-preview").hidden = false;
    $("upload-placeholder").hidden = true;
    $("file-caption").textContent =
      `${file.name} · ${image.naturalWidth} × ${image.naturalHeight} · 仅本机预览`;
    $("start-demo").textContent = "切换到示例并体验 →";
    $("upload-explainer").textContent =
      "你的图片仅作上传预览。开始演示后将切换为内置拼图，避免把示例结果当成这张图的处理结果。";
  } catch {
    URL.revokeObjectURL(url);
    if (revision !== state.previewRevision) return;
    $("file-error").textContent = "这张图片无法预览，请检查文件是否完整。";
    $("file-error").hidden = false;
  }
}
function showZoom(item = null) {
  $("zoom-dialog")
    .querySelector(".zoom-comparison")
    .classList.toggle("source-only", !item);
  if (item) {
    focusAsset(item.id);
    $("zoom-title").textContent = item.label;
    $("zoom-asset").src = assetUrl(item.id);
    setBox("zoom-source-box", state.edits.get(item.id)?.bounds || item.bounds);
    $("zoom-dialog").querySelector(".zoom-comparison").lastElementChild.hidden =
      false;
  } else {
    $("zoom-title").textContent = "合成示例原图";
    setBox("zoom-source-box", { x: 0, y: 0, width: 0, height: 0 });
    $("zoom-dialog").querySelector(".zoom-comparison").lastElementChild.hidden =
      true;
  }
  $("zoom-dialog").showModal();
}
function showEditor(item) {
  focusAsset(item.id);
  const previous = state.edits.get(item.id);
  state.editor = {
    id: item.id,
    bounds: { ...(previous?.bounds || item.bounds) },
    strokes: (previous?.strokes || []).map((s) => ({
      points: s.points.map((p) => ({ ...p })),
    })),
  };
  state.tool = "bounds";
  $("asset-label").value = item.label;
  $("editor-asset").src = assetUrl(item.id);
  $("editor-title").textContent = `局部修正 · ${item.label}`;
  renderEditor();
  $("editor-dialog").showModal();
}
function renderEditor() {
  if (!state.editor) return;
  setBox("editor-box", state.editor.bounds);
  const b = state.editor.bounds;
  setBox("editor-handle", {
    x: b.x + b.width - 10,
    y: b.y + b.height - 10,
    width: 20,
    height: 20,
  });
  $("editor-strokes").replaceChildren(
    ...state.editor.strokes.map((stroke) => {
      const path = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "path",
      );
      path.setAttribute(
        "d",
        stroke.points.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" "),
      );
      path.setAttribute("stroke-width", "18");
      return path;
    }),
  );
  document
    .querySelectorAll("[data-tool]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.tool === state.tool),
    );
  $("tool-hint").textContent = {
    bounds: "拖动方框调整位置，拖动右下角调整范围。",
    add: "拖动标记要修复的水印区域。仅保存演示方案。",
    erase: "拖动擦除整条标记。仅影响本次演示。",
  }[state.tool];
  $("editor-surface").style.cursor =
    state.tool === "bounds" ? "move" : "crosshair";
}
function imagePoint(event) {
  const rect = $("editor-surface").getBoundingClientRect();
  return {
    x: Math.max(
      0,
      Math.min(960, ((event.clientX - rect.left) / rect.width) * 960),
    ),
    y: Math.max(
      0,
      Math.min(720, ((event.clientY - rect.top) / rect.height) * 720),
    ),
  };
}
let pointer = null;
function eraseAt(point) {
  state.editor.strokes = state.editor.strokes.filter(
    (stroke) =>
      !stroke.points.some((p) => Math.hypot(p.x - point.x, p.y - point.y) < 30),
  );
}
$("editor-surface").addEventListener("pointerdown", (event) => {
  if (!state.editor || event.button !== 0) return;
  const point = imagePoint(event);
  pointer = {
    id: event.pointerId,
    start: point,
    bounds: { ...state.editor.bounds },
    resize: event.target.id === "editor-handle",
  };
  if (state.tool === "add")
    state.editor.strokes.push({
      points: [point, { x: point.x + 0.1, y: point.y + 0.1 }],
    });
  if (state.tool === "erase") eraseAt(point);
  $("editor-surface").setPointerCapture(event.pointerId);
  event.preventDefault();
  renderEditor();
});
$("editor-surface").addEventListener("pointermove", (event) => {
  if (!pointer || !state.editor || event.pointerId !== pointer.id) return;
  const p = imagePoint(event),
    b = pointer.bounds;
  if (state.tool === "bounds") {
    if (pointer.resize)
      state.editor.bounds = {
        x: b.x,
        y: b.y,
        width: Math.round(
          Math.max(30, Math.min(960 - b.x, b.width + p.x - pointer.start.x)),
        ),
        height: Math.round(
          Math.max(30, Math.min(720 - b.y, b.height + p.y - pointer.start.y)),
        ),
      };
    else
      state.editor.bounds = {
        ...b,
        x: Math.round(
          Math.max(0, Math.min(960 - b.width, b.x + p.x - pointer.start.x)),
        ),
        y: Math.round(
          Math.max(0, Math.min(720 - b.height, b.y + p.y - pointer.start.y)),
        ),
      };
  } else if (state.tool === "add") state.editor.strokes.at(-1).points.push(p);
  else eraseAt(p);
  renderEditor();
});
for (const type of ["pointerup", "pointercancel", "lostpointercapture"])
  $("editor-surface").addEventListener(type, () => (pointer = null));
$("save-correction").addEventListener("click", () => {
  if (!state.editor) return;
  const id = state.editor.id;
  items.get(id).label = $("asset-label").value.trim() || items.get(id).label;
  state.edits.set(id, {
    bounds: { ...state.editor.bounds },
    strokes: state.editor.strokes,
  });
  $("editor-dialog").close();
  state.editor = null;
  renderResults();
  toast("已保存演示修正方案，未执行真实重新处理。");
});
document.querySelectorAll("[data-tool]").forEach((button) =>
  button.addEventListener("click", () => {
    state.tool = button.dataset.tool;
    pointer = null;
    renderEditor();
  }),
);
$("clear-marks").addEventListener("click", () => {
  state.editor.strokes = [];
  renderEditor();
});
for (const dialog of document.querySelectorAll("dialog"))
  dialog.addEventListener("close", () => {
    pointer = null;
    if (dialog.id === "editor-dialog") state.editor = null;
  });
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => $(button.dataset.close).close()),
  );
document.querySelectorAll("[data-page]").forEach((button) =>
  button.addEventListener("click", () => {
    state.page = button.dataset.page;
    render();
    window.scrollTo({ top: 0, behavior: "instant" });
  }),
);
document.querySelector(".brand").addEventListener("click", (event) => {
  event.preventDefault();
  state.page = "material";
  render();
});
$("choose-file").addEventListener("click", () => $("image-file").click());
$("drop-zone").addEventListener("click", () => $("image-file").click());
$("image-file").addEventListener("change", (event) => {
  void previewFile(event.target.files[0]);
  event.target.value = "";
});
for (const eventName of ["dragenter", "dragover"])
  $("drop-zone").addEventListener(eventName, (event) => {
    event.preventDefault();
    $("drop-zone").classList.add("dragging");
  });
for (const eventName of ["dragleave", "drop"])
  $("drop-zone").addEventListener(eventName, (event) => {
    event.preventDefault();
    $("drop-zone").classList.remove("dragging");
  });
$("drop-zone").addEventListener("drop", (event) => {
  if (event.dataTransfer.files.length !== 1) {
    toast("每次选择一张图片即可。");
    return;
  }
  void previewFile(event.dataTransfer.files[0]);
});
$("start-demo").addEventListener("click", beginDemo);
$("stop-demo").addEventListener("click", reset);
$("restart-demo").addEventListener("click", reset);
$("next-step").addEventListener("click", () => {
  if (state.step < 2) state.step++;
  else state.phase = "results";
  render();
  if (state.phase === "results") {
    window.scrollTo({ top: 0, behavior: "instant" });
    $("download-all").focus({ preventScroll: true });
  }
});
$("zoom-source").addEventListener("click", () => showZoom());
$("select-all").addEventListener("click", () => {
  state.selected =
    state.selected.size === state.available.size
      ? new Set()
      : new Set(state.available);
  $("asset-grid")
    .querySelectorAll("[data-select]")
    .forEach(
      (input) => (input.checked = state.selected.has(input.dataset.select)),
    );
  renderSelection();
});
$("undo-remove").addEventListener("click", () => {
  const removed = state.removed.pop();
  if (!removed) return;
  state.available = new Set(
    originals
      .filter((i) => state.available.has(i.id) || i.id === removed.id)
      .map((i) => i.id),
  );
  if (removed.selected) state.selected.add(removed.id);
  state.focused = removed.id;
  renderResults();
  toast("已恢复示例素材。");
});
$("asset-grid").addEventListener("change", (event) => {
  const id = event.target.dataset.select;
  if (!id) return;
  if (event.target.checked) state.selected.add(id);
  else state.selected.delete(id);
  renderSelection();
});
$("asset-grid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-asset-id]"),
    button = event.target.closest("[data-action]");
  if (!card || !button) return;
  const item = items.get(card.dataset.assetId);
  focusAsset(item.id);
  if (button.dataset.action === "view") showZoom(item);
  if (button.dataset.action === "edit") showEditor(item);
  if (button.dataset.action === "download")
    void downloadSamples([item.id], false);
  if (button.dataset.action === "remove") {
    state.removed.push({ id: item.id, selected: state.selected.has(item.id) });
    state.available.delete(item.id);
    state.selected.delete(item.id);
    if (state.focused === item.id) state.focused = [...state.available][0];
    renderResults();
    toast("已移除，可点击“撤销移除”恢复。");
  }
});
function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("示例图片加载失败，请刷新后重试。"));
    image.src = url;
  });
}
async function samplePng(id) {
  const image = await loadImage(assetUrl(id));
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 320;
  canvas.getContext("2d").drawImage(image, 0, 0, 320, 320);
  return await new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) =>
        blob ? resolve(blob) : reject(new Error("示例 PNG 生成失败。")),
      "image/png",
    ),
  );
}
const crcTable = Array.from({ length: 256 }, (_, value) => {
  for (let i = 0; i < 8; i++)
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  return value >>> 0;
});
function crc32(bytes) {
  let c = 0xffffffff;
  for (const byte of bytes) c = crcTable[(c ^ byte) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function zipStored(entries) {
  const local = [],
    central = [];
  let offset = 0,
    centralLength = 0;
  for (const entry of entries) {
    const name = new TextEncoder().encode(entry.name),
      bytes = entry.bytes,
      crc = crc32(bytes),
      header = new Uint8Array(30 + name.length),
      v = new DataView(header.buffer);
    v.setUint32(0, 0x04034b50, true);
    v.setUint16(4, 20, true);
    v.setUint16(6, 0x0800, true);
    v.setUint16(12, 33, true);
    v.setUint32(14, crc, true);
    v.setUint32(18, bytes.length, true);
    v.setUint32(22, bytes.length, true);
    v.setUint16(26, name.length, true);
    header.set(name, 30);
    local.push(header, bytes);
    const record = new Uint8Array(46 + name.length),
      r = new DataView(record.buffer);
    r.setUint32(0, 0x02014b50, true);
    r.setUint16(4, 20, true);
    r.setUint16(6, 20, true);
    r.setUint16(8, 0x0800, true);
    r.setUint16(14, 33, true);
    r.setUint32(16, crc, true);
    r.setUint32(20, bytes.length, true);
    r.setUint32(24, bytes.length, true);
    r.setUint16(28, name.length, true);
    r.setUint32(42, offset, true);
    record.set(name, 46);
    central.push(record);
    centralLength += record.length;
    offset += header.length + bytes.length;
  }
  const end = new Uint8Array(22),
    v = new DataView(end.buffer);
  v.setUint32(0, 0x06054b50, true);
  v.setUint16(8, entries.length, true);
  v.setUint16(10, entries.length, true);
  v.setUint32(12, centralLength, true);
  v.setUint32(16, offset, true);
  return new Blob([...local, ...central, end], { type: "application/zip" });
}
function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
async function downloadSamples(ids, asZip = true) {
  if (state.downloadBusy || !ids.length) return;
  state.downloadBusy = true;
  renderResults();
  try {
    const entries = [];
    for (const [index, id] of ids.entries()) {
      const blob = await samplePng(id);
      entries.push({
        name: `DEMO_${String(index + 1).padStart(2, "0")}_${safeName(items.get(id).label)}.png`,
        blob,
        bytes: new Uint8Array(await blob.arrayBuffer()),
      });
    }
    if (asZip) saveBlob(zipStored(entries), "智筛Agent_DEMO_合成示例素材.zip");
    else saveBlob(entries[0].blob, entries[0].name);
    toast(
      "已发起示例下载，请查看浏览器下载列表。这不是上传图片的 AI 处理结果。",
    );
  } catch (error) {
    toast(error.message || "示例下载失败，请重试。");
  } finally {
    state.downloadBusy = false;
    renderResults();
  }
}
$("download-all").addEventListener(
  "click",
  () => void downloadSamples([...state.selected]),
);
window.addEventListener("pagehide", () => {
  if (state.localUrl) URL.revokeObjectURL(state.localUrl);
});
render();
