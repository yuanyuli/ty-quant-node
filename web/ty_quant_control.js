import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const SECTIONS = [
  ["数据源", ["data_source", "csv_path", "ts_codes", "query_start", "query_end"]],
  ["复权与数据维护", ["adjustment_mode", "include_events", "incremental"]],
  ["训练与测试", ["train_start", "train_end", "test_start", "test_end"]],
  ["因子", ["factor_set", "selected_json", "custom_json"]],
  ["模型与回测", ["model_type", "params_json", "segment", "topk", "n_drop", "transaction_cost_bps"]],
  ["产物目录", ["artifact_root"]],
];

function addSection(node, title, fields, expanded = false, refresh = () => {}) {
  if (!node.addWidget || node.widgets?.some((w) => w.name === `__ty_section_${title}`)) return;
  const state = { expanded: Boolean(expanded) };
  const button = node.addWidget("button", `__ty_section_${title}`, `${state.expanded ? "▾" : "▸"} ${title}`, () => {
    state.expanded = !state.expanded;
    button.label = `${state.expanded ? "▾" : "▸"} ${title}`;
    refresh();
  });
  button.serialize = false;
  button.options = { ...(button.options || {}), serialize: false, tooltip: `${title} 参数；点击标题展开或收起。` };
  button.__tySection = { fields, state };
  const inserted = node.widgets.pop();
  const index = node.widgets.findIndex((w) => w.name === fields[0]);
  node.widgets.splice(index < 0 ? node.widgets.length : index, 0, inserted);
}

function replaceDateWidget(node, inputName) {
  if (!node.addDOMWidget || node.__tyDateWidgets?.has(inputName)) return;
  const index = node.widgets?.findIndex((w) => w.name === inputName);
  if (index == null || index < 0) return;
  const old = node.widgets[index];
  const element = document.createElement("input");
  element.type = "date";
  element.value = String(old.value ?? "");
  element.title = old.options?.tooltip || "日期";
  Object.assign(element.style, { width: "100%", boxSizing: "border-box", colorScheme: "dark" });
  node.widgets.splice(index, 1);
  const widget = node.addDOMWidget(inputName, "TY_DATE", element, {
    serialize: true,
    getValue: () => element.value,
    setValue: (value) => { element.value = String(value ?? ""); },
  });
  widget.options = { ...(widget.options || {}), tooltip: old.options?.tooltip || "日期" };
  widget.value = element.value;
  element.addEventListener("change", () => { widget.value = element.value; node.graph?.setDirtyCanvas(true, true); });
  const current = node.widgets.indexOf(widget);
  if (current >= 0) node.widgets.splice(current, 1);
  node.widgets.splice(Math.min(index, node.widgets.length), 0, widget);
  old.element && (old.element.style.display = "none");
  node.__tyDateWidgets ??= new Set();
  node.__tyDateWidgets.add(inputName);
}

async function browsePath(current, chooseFile, onPick) {
  const rootsResponse = await api.fetchApi("/ty-quant-node/fs/roots");
  if (!rootsResponse.ok) throw new Error("无法读取允许的目录");
  const roots = (await rootsResponse.json()).roots || [];
  let listingPath = current || roots[0] || "";
  if (chooseFile && /[\\/][^\\/]+\.[^\\/]+$/.test(listingPath)) listingPath = listingPath.replace(/[\\/][^\\/]+$/, "");
  const overlay = document.createElement("div");
  Object.assign(overlay.style, { position: "fixed", inset: "0", zIndex: "10000", background: "rgba(0,0,0,.65)", display: "flex", alignItems: "center", justifyContent: "center" });
  const panel = document.createElement("div");
  Object.assign(panel.style, { width: "min(680px, 90vw)", maxHeight: "80vh", overflow: "auto", background: "#20242b", color: "#eee", padding: "16px", borderRadius: "8px", boxShadow: "0 8px 30px #000" });
  overlay.appendChild(panel); document.body.appendChild(overlay);
  const close = () => overlay.remove();
  const render = async (path) => {
    const response = await api.fetchApi(`/ty-quant-node/fs/list?path=${encodeURIComponent(path)}`);
    if (!response.ok) throw new Error("目录不可访问");
    const listing = await response.json(); listingPath = listing.path;
    panel.replaceChildren();
    const title = document.createElement("div"); title.textContent = "选择路径"; title.style.fontWeight = "bold"; title.style.marginBottom = "8px"; panel.appendChild(title);
    const current = document.createElement("div"); current.textContent = listing.path; current.style.cssText = "font-size:12px;color:#9ca3af;margin-bottom:10px;word-break:break-all"; panel.appendChild(current);
    const actions = document.createElement("div"); actions.style.marginBottom = "10px";
    const use = document.createElement("button"); use.textContent = chooseFile ? "请选择文件列表中的文件" : "使用此目录"; use.disabled = chooseFile; use.onclick = () => { onPick(listing.path); close(); }; actions.appendChild(use);
    const cancel = document.createElement("button"); cancel.textContent = "取消"; cancel.style.marginLeft = "8px"; cancel.onclick = close; actions.appendChild(cancel); panel.appendChild(actions);
    if (listing.parent && listing.parent !== listing.path) { const up = document.createElement("button"); up.textContent = "⬆ 上级"; up.onclick = () => render(listing.parent); panel.appendChild(up); }
    for (const entry of listing.entries || []) {
      const button = document.createElement("button"); button.textContent = `${entry.is_dir ? "📁" : "📄"} ${entry.name}`; button.style.cssText = "display:block;width:100%;text-align:left;margin-top:4px;padding:6px";
      button.onclick = () => entry.is_dir ? render(entry.path) : (onPick(entry.path), close());
      panel.appendChild(button);
    }
  };
  try { await render(listingPath); } catch (error) { close(); throw error; }
}

function addPicker(node, inputName, chooseFile = false) {
  if (!node.addWidget || node.widgets?.some((w) => w.name === `__ty_picker_${inputName}`)) return;
  const input = node.widgets?.find((w) => w.name === inputName);
  if (!input) return;
  const picker = node.addWidget("button", `__ty_picker_${inputName}`, "选择路径", () => {
    browsePath(String(input.value || ""), chooseFile, (value) => { input.value = value; node.graph?.setDirtyCanvas(true); })
      .catch((error) => window.alert(`路径选择失败：${error.message}`));
  });
  picker.serialize = false;
  picker.options = { ...(picker.options || {}), serialize: false };
}

function applyControlVisibility(node) {
  if ((node.comfyClass || node.type) === "QlibControl") return;
  const controlInput = (node.inputs || []).find((input) => input.name === "control");
  const controlled = Boolean(controlInput?.link);
  for (const widget of node.widgets || []) {
    if (widget.name === "control" || widget.name?.startsWith("__ty_")) continue;
    widget.hidden = controlled;
    if (controlled) widget.computeSize = () => [0, -4];
  }
  node.computeSize?.();
  node.setDirtyCanvas?.(true, true);
}

function applySourceVisibility(node) {
  if ((node.comfyClass || node.type) !== "QlibControl") return;
  const source = node.widgets?.find((widget) => widget.name === "data_source")?.value;
  const hidden = source === "local_csv" ? new Set(["ts_codes", "query_start", "query_end", "include_events"]) : new Set(["csv_path"]);
  for (const widget of node.widgets || []) {
    if (widget.name === "__ty_picker_csv_path") { widget.hidden = source === "local_csv"; widget.computeSize = () => [0, -4]; continue; }
    if (widget.name?.startsWith("__ty_")) continue;
    if (hidden.has(widget.name)) { widget.hidden = true; widget.computeSize = () => [0, -4]; }
  }
  node.computeSize?.();
}

app.registerExtension({
  name: "ty-quant-node.control-ux",
  nodeCreated(node) {
    if (node.__tyQuantEnhanced) return;
    node.__tyQuantEnhanced = true;
    setTimeout(() => {
      const nodeClass = node.comfyClass || node.type;
      applyControlVisibility(node);
      if (nodeClass !== "QlibControl") {
        if ((node.inputs || []).some((input) => input.name === "control" && input.link)) return;
        for (const widget of node.widgets || []) {
          if (["query_start", "query_end", "train_start", "train_end", "test_start", "test_end"].includes(widget.name)) replaceDateWidget(node, widget.name);
          if (/(_path|_dir|_root|^output_dir$|^provider_uri$|^experiment_uri$)/.test(widget.name || "")) addPicker(node, widget.name, widget.name === "csv_path");
        }
        return;
      }
      applySourceVisibility(node);
      const sourceWidget = node.widgets?.find((widget) => widget.name === "data_source");
      if (sourceWidget) {
        const previous = sourceWidget.callback;
        sourceWidget.callback = (value) => { previous?.call(sourceWidget, value); applySourceVisibility(node); };
      }
      for (const [title, fields] of SECTIONS) addSection(node, title, fields[0]);
      for (const name of ["query_start", "query_end", "train_start", "train_end", "test_start", "test_end"]) replaceDateWidget(node, name);
      addPicker(node, "csv_path", true);
      addPicker(node, "artifact_root", false);
      applySourceVisibility(node);
      for (const widget of node.widgets || []) {
        const tooltip = widget.options?.tooltip;
        if (tooltip) {
          if (widget.element) widget.element.title = tooltip;
          widget.tooltip = tooltip;
        }
      }
      node.computeSize?.();
      node.setDirtyCanvas?.(true, true);
    }, 50);
  },
});
