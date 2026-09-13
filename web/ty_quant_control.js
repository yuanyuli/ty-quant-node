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

function addSection(node, title, beforeName) {
  if (!node.addCustomWidget || node.widgets?.some((w) => w.name === `__ty_section_${title}`)) return;
  const widget = {
    name: `__ty_section_${title}`,
    type: "TY_SECTION",
    serialize: false,
    options: { serialize: false },
    computeSize: () => [node.size?.[0] || 300, 24],
    draw(ctx, _node, width, y, height) {
      ctx.save();
      ctx.fillStyle = "#3b82f6";
      ctx.fillRect(8, y + 5, 3, height - 10);
      ctx.fillStyle = "#dbeafe";
      ctx.font = "bold 13px sans-serif";
      ctx.fillText(title, 18, y + height - 8);
      ctx.strokeStyle = "#475569";
      ctx.beginPath(); ctx.moveTo(18, y + height - 3); ctx.lineTo(width - 8, y + height - 3); ctx.stroke();
      ctx.restore();
    },
  };
  node.addCustomWidget(widget);
  const inserted = node.widgets.pop();
  const index = node.widgets.findIndex((w) => w.name === beforeName);
  node.widgets.splice(index < 0 ? node.widgets.length : index, 0, inserted);
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

app.registerExtension({
  name: "ty-quant-node.control-ux",
  nodeCreated(node) {
    if (node.comfyClass !== "QlibControl" || node.__tyQuantEnhanced) return;
    node.__tyQuantEnhanced = true;
    setTimeout(() => {
      for (const [title, fields] of SECTIONS) addSection(node, title, fields[0]);
      addPicker(node, "csv_path", true);
      addPicker(node, "artifact_root", false);
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
