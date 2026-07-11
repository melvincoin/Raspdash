const config = JSON.parse(document.body.dataset.config || "{}");
let editorConfig = JSON.parse(JSON.stringify(config));
let currentCapabilities = [];
let currentThemes = [];
let selectedWidgetId = editorConfig.dashboard.widget_order?.[0] || Object.keys(editorConfig.dashboard.widgets)[0];
let dragState = null;

const field = (id) => document.getElementById(id);
const preview = field("layout-preview");

field("toggle-advanced").addEventListener("click", () => {
  const visible = document.body.classList.toggle("show-advanced");
  field("toggle-advanced").setAttribute("aria-expanded", String(visible));
  field("toggle-advanced").textContent = visible ? "Geavanceerd verbergen" : "Geavanceerd tonen";
});

function syncRangeValue(input) {
  const output = field(`${input.id}-value`);
  if (!output) return;
  const value = Number(input.value);
  const format = input.dataset.valueFormat;
  output.textContent = format === "percent01"
    ? `${Math.round(value * 100)}%`
    : format === "percent"
      ? `${Number(value.toFixed(1))}%`
      : format === "x"
        ? `${Number(value.toFixed(2))}x`
        : input.value;
}

function bindRangeValues() {
  document.querySelectorAll('input[type="range"][data-value-format]').forEach((input) => {
    syncRangeValue(input);
    input.addEventListener("input", () => syncRangeValue(input));
  });
}

field("resolution").value = editorConfig.display.resolution;
field("fullscreen").checked = editorConfig.display.fullscreen;
field("brightness").value = editorConfig.display.brightness;
field("background-dim").value = editorConfig.display.background_dim ?? 0.72;
field("render-scale").value = editorConfig.display.render_scale ?? 0.6;
field("splash").value = editorConfig.display.splash;
field("background").value = editorConfig.display.background;
field("provider").value = editorConfig.obd.provider;
field("elm-port").value = editorConfig.obd.elm327.port;
field("elm-mac").value = editorConfig.obd.elm327.bluetooth_mac;
field("elm-allow-requests").checked = editorConfig.obd.elm327.allow_requests === true;
field("accent-color").value = editorConfig.dashboard.accent_color;
field("status-enabled").checked = editorConfig.dashboard.status_enabled !== false;
editorConfig.dashboard.oil_startup_toast = editorConfig.dashboard.oil_startup_toast || {};
field("oil-toast-enabled").checked = editorConfig.dashboard.oil_startup_toast.enabled !== false;
field("oil-toast-position").value = editorConfig.dashboard.oil_startup_toast.position || "top-center";
field("oil-toast-duration").value = editorConfig.dashboard.oil_startup_toast.duration_seconds ?? 60;
field("oil-toast-x").value = editorConfig.dashboard.oil_startup_toast.x_pct ?? 50;
field("oil-toast-y").value = editorConfig.dashboard.oil_startup_toast.y_pct ?? 5.5;
field("oil-toast-width").value = editorConfig.dashboard.oil_startup_toast.width_pct ?? 46;
editorConfig.dashboard.dtc_startup_toast = editorConfig.dashboard.dtc_startup_toast || {};
field("dtc-toast-enabled").checked = editorConfig.dashboard.dtc_startup_toast.enabled !== false;
field("dtc-toast-position").value = editorConfig.dashboard.dtc_startup_toast.position || "bottom-center";
field("dtc-toast-duration").value = editorConfig.dashboard.dtc_startup_toast.duration_seconds ?? 90;
field("dtc-toast-x").value = editorConfig.dashboard.dtc_startup_toast.x_pct ?? 50;
field("dtc-toast-y").value = editorConfig.dashboard.dtc_startup_toast.y_pct ?? 6;
field("dtc-toast-width").value = editorConfig.dashboard.dtc_startup_toast.width_pct ?? 60;
field("editor-snap").checked = editorConfig.dashboard.editor_snap !== false;
field("editor-grid-size").value = editorConfig.dashboard.editor_grid_size || 2.5;
bindRangeValues();

function formatUptime(seconds) {
  if (!Number.isFinite(seconds)) return "-";
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}u`;
  if (hours > 0) return `${hours}u ${minutes % 60}m`;
  return `${minutes}m`;
}

function setStatusValue(id, value, ok = true) {
  const element = field(id);
  element.textContent = value;
  element.dataset.state = ok ? "ok" : "bad";
}

async function loadPiStatus() {
  try {
    const response = await fetch(`/api/system/status?v=${Date.now()}`);
    const data = await response.json();
    const flags = data.throttled || {};
    const undervoltage = flags.undervoltage_now || flags.undervoltage_seen;
    const throttled = flags.throttled_now || flags.throttled_seen || flags.frequency_capped_now || flags.frequency_capped_seen;
    const thermal = flags.soft_temp_limit_now || flags.soft_temp_limit_seen;
    setStatusValue("pi-temp", data.temperature_c == null ? "-" : `${data.temperature_c.toFixed(1)}°C`, !thermal && (data.temperature_c ?? 0) < 75);
    setStatusValue("pi-power", undervoltage ? "te laag" : "ok", !undervoltage);
    setStatusValue("pi-throttle", throttled || thermal ? flags.hex : "ok", !(throttled || thermal));
    setStatusValue("pi-display", String(data.display_power || "-").replace("display_power=", ""), String(data.display_power || "").endsWith("1"));
    setStatusValue("pi-load", data.load_average?.["1m"] == null ? "-" : data.load_average["1m"].toFixed(2), true);
    setStatusValue("pi-uptime", formatUptime(data.uptime_seconds), true);
    field("pi-status-output").textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    field("pi-status-output").textContent = String(error.message || error);
  }
}

function widgetOrder() {
  if (!editorConfig.dashboard.widget_order) {
    editorConfig.dashboard.widget_order = Object.keys(editorConfig.dashboard.widgets);
  }
  return editorConfig.dashboard.widget_order;
}

async function loadCapabilities(provider = field("provider").value) {
  const response = await fetch(`/api/capabilities?provider=${encodeURIComponent(provider)}`);
  const data = await response.json();
  currentCapabilities = data.parameters;
  const hint = {
    simulated: "Simulator toont alle waarden met fake data.",
    hexv2: "HEX-V2 is bedoeld voor VAG-specifieke waarden zoals olie, DSG, koeling en boost. Echte polling wordt pas aangezet na hardwaretest.",
    elm327: "ELM327/vLinker USB leest bewezen standaard OBD-II waarden. Onbewezen VAG-temperaturen blijven uit tot er mapping is.",
  };
  field("provider-hint").textContent = hint[provider] || "";
  populateAddCategorySelect();
  renderEditor();
}

async function loadThemes() {
  const response = await fetch("/api/themes");
  const data = await response.json();
  currentThemes = data.themes || [];
  const select = field("edit-style");
  select.textContent = "";
  for (const theme of currentThemes) {
    const option = document.createElement("option");
    option.value = theme.id;
    option.textContent = theme.label;
    option.dataset.renderer = theme.renderer;
    select.append(option);
  }
}

function renderEditor() {
  renderWidgetSelect();
  renderPreview();
  syncSelectedControls();
}

function renderWidgetSelect() {
  const select = field("edit-widget");
  select.textContent = "";
  for (const widgetId of widgetOrder()) {
    const widget = editorConfig.dashboard.widgets[widgetId];
    if (!widget) continue;
    const option = document.createElement("option");
    option.value = widgetId;
    option.textContent = widget.label || widgetId;
    select.append(option);
  }
  if (!editorConfig.dashboard.widgets[selectedWidgetId]) {
    selectedWidgetId = widgetOrder()[0];
  }
  select.value = selectedWidgetId;
}

function renderPreview() {
  preview.textContent = "";
  preview.style.setProperty("--grid-size", Number(editorConfig.dashboard.editor_grid_size || 2.5));
  for (const widgetId of widgetOrder()) {
    const widget = editorConfig.dashboard.widgets[widgetId];
    if (!widget) continue;
    const element = document.createElement("div");
    element.className = "editor-widget";
    element.dataset.editWidget = widgetId;
    element.dataset.style = themeRenderer(widgetThemeId(widget));
    element.dataset.source = widget.source || "";
    if (widget.source === "act_active") {
      const icon = document.createElement("img");
      icon.src = "/static/img/act-active-icon.svg";
      icon.alt = "ACT actief";
      element.append(icon);
    } else {
      element.textContent = widget.label || widgetId;
    }
    element.style.left = `${widget.x ?? 10}%`;
    element.style.top = `${widget.y ?? 30}%`;
    element.style.setProperty("--w", Number(widget.width ?? 28));
    element.style.color = widget.color || "#e8f1ff";
    if (widgetId === selectedWidgetId) element.classList.add("is-selected");
    element.addEventListener("pointerdown", startDrag);
    element.addEventListener("click", () => {
      selectedWidgetId = widgetId;
      renderEditor();
    });
    preview.append(element);
  }
}

function populateSourceSelect(selected) {
  const select = field("edit-source");
  select.textContent = "";
  for (const [category, parameters] of groupedCapabilities()) {
    const group = document.createElement("optgroup");
    group.label = category;
    for (const parameter of parameters) {
      const option = document.createElement("option");
      option.value = parameter.key;
      option.textContent = `${parameter.label} (${parameter.unit})`;
      group.append(option);
    }
    select.append(group);
  }
  if (currentCapabilities.some((parameter) => parameter.key === selected)) {
    select.value = selected;
  }
}

function groupedCapabilities() {
  const groups = new Map();
  for (const parameter of currentCapabilities) {
    const category = parameter.category || "Overig";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(parameter);
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right, "nl"));
}

function populateAddCategorySelect() {
  const select = field("add-category");
  if (!select) return;
  const previous = select.value;
  select.textContent = "";
  for (const [category] of groupedCapabilities()) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    select.append(option);
  }
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
  populateAddSourceSelect();
}

function populateAddSourceSelect() {
  const select = field("add-source");
  if (!select) return;
  const category = field("add-category").value;
  const parameters = currentCapabilities.filter((parameter) => (parameter.category || "Overig") === category);
  select.textContent = "";
  for (const parameter of parameters) {
    const option = document.createElement("option");
    option.value = parameter.key;
    option.textContent = `${parameter.label} (${parameter.unit})`;
    select.append(option);
  }
}

function syncSelectedControls() {
  const widget = editorConfig.dashboard.widgets[selectedWidgetId];
  if (!widget) return;
  populateSourceSelect(widget.source || "battery_voltage_v");
  field("edit-style").value = widgetThemeId(widget);
  field("edit-font-size").value = widget.font_size || 64;
  const widthControl = field("edit-width");
  widthControl.min = widget.source.startsWith("act_active") ? 3 : 14;
  widthControl.step = widget.source.startsWith("act_active") ? 0.5 : 1;
  widthControl.value = widget.width ?? 28;
  syncRangeValue(widthControl);
  field("edit-color").value = widget.color || "#e8f1ff";
  field("edit-x").value = formatCoordinate(widget.x ?? 10);
  field("edit-y").value = formatCoordinate(widget.y ?? 30);
}

function parameterLabel(key) {
  return currentCapabilities.find((parameter) => parameter.key === key)?.label || key.toUpperCase();
}

function updateSelectedWidgetFromControls() {
  const widget = editorConfig.dashboard.widgets[selectedWidgetId];
  if (!widget) return;
  widget.source = field("edit-source").value;
  widget.label = parameterLabel(widget.source);
  widget.displayType = field("edit-style").value;
  widget.style = themeRenderer(widget.displayType);
  widget.font_size = Number(field("edit-font-size").value);
  widget.width = Number(field("edit-width").value);
  widget.color = field("edit-color").value;
  widget.x = snapWidgetX(Number(field("edit-x").value), widget.width || 28);
  widget.y = snapWidgetY(Number(field("edit-y").value), widget.width || 28);
  renderEditor();
}

function snapPercent(value) {
  if (editorConfig.dashboard.editor_snap === false) return value;
  const grid = Number(editorConfig.dashboard.editor_grid_size || 2.5);
  return Math.round(value / grid) * grid;
}

function formatCoordinate(value) {
  return Number(Number(value).toFixed(1));
}

function snapWidgetX(x, width) {
  if (editorConfig.dashboard.editor_snap === false) return x;
  const center = snapPercent(x + width / 2);
  return center - width / 2;
}

function snapWidgetY(y, width) {
  if (editorConfig.dashboard.editor_snap === false) return y;
  const previewRect = preview.getBoundingClientRect();
  const heightPct = (width * previewRect.width) / previewRect.height;
  const center = snapPercent(y + heightPct / 2);
  return center - heightPct / 2;
}

function startDrag(event) {
  const widgetId = event.currentTarget.dataset.editWidget;
  selectedWidgetId = widgetId;
  const rect = preview.getBoundingClientRect();
  const widget = editorConfig.dashboard.widgets[widgetId];
  dragState = { widgetId, rect, offsetX: event.clientX - rect.left - (widget.x || 0) * rect.width / 100, offsetY: event.clientY - rect.top - (widget.y || 0) * rect.height / 100 };
  event.currentTarget.setPointerCapture(event.pointerId);
  window.addEventListener("pointermove", dragMove);
  window.addEventListener("pointerup", stopDrag, { once: true });
  renderEditor();
}

function dragMove(event) {
  if (!dragState) return;
  const widget = editorConfig.dashboard.widgets[dragState.widgetId];
  const width = widget.width ?? 28;
  const x = ((event.clientX - dragState.rect.left - dragState.offsetX) / dragState.rect.width) * 100;
  const y = ((event.clientY - dragState.rect.top - dragState.offsetY) / dragState.rect.height) * 100;
  widget.x = Math.max(0, Math.min(100 - width, snapWidgetX(x, width)));
  widget.y = Math.max(0, Math.min(86, snapWidgetY(y, width)));
  renderPreview();
  syncSelectedControls();
}

function stopDrag() {
  dragState = null;
  window.removeEventListener("pointermove", dragMove);
}

function nudgeSelectedWidget(event) {
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
  const widget = editorConfig.dashboard.widgets[selectedWidgetId];
  if (!widget) return;
  const active = document.activeElement;
  if (active && ["TEXTAREA", "SELECT"].includes(active.tagName)) return;

  event.preventDefault();
  const grid = Number(editorConfig.dashboard.editor_grid_size || 2.5);
  const step = event.altKey ? 0.5 : event.shiftKey ? grid * 2 : grid;
  const width = Number(widget.width ?? 28);
  const previewRect = preview.getBoundingClientRect();
  const heightPct = (width * previewRect.width) / previewRect.height;
  const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
  const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
  widget.x = formatCoordinate(Math.max(0, Math.min(100 - width, Number(widget.x ?? 0) + dx)));
  widget.y = formatCoordinate(Math.max(0, Math.min(100 - heightPct, Number(widget.y ?? 0) + dy)));
  renderPreview();
  syncSelectedControls();
}

function addWidget() {
  const count = widgetOrder().length + 1;
  const source = field("add-source").value || currentCapabilities[0]?.key || "battery_voltage_v";
  const widgetId = `widget_${Date.now()}`;
  const defaultWidth = 34;
  editorConfig.dashboard.widgets[widgetId] = {
    enabled: true,
    source,
    label: parameterLabel(source),
    font_size: 82,
    color: "#ffffff",
    position: "custom",
    x: Math.min(100 - defaultWidth, 14 + (count % 2) * 38),
    y: Math.min(78, 4 + Math.floor(count / 2) * 18.5),
    width: defaultWidth,
    height: 0.155,
    displayType: "Digitaal",
    style: "digitaal",
  };
  widgetOrder().push(widgetId);
  selectedWidgetId = widgetId;
  renderEditor();
}

function removeWidget() {
  if (widgetOrder().length <= 1) return;
  delete editorConfig.dashboard.widgets[selectedWidgetId];
  editorConfig.dashboard.widget_order = widgetOrder().filter((id) => id !== selectedWidgetId);
  selectedWidgetId = widgetOrder()[0];
  renderEditor();
}

function collectConfig() {
  editorConfig.display.resolution = field("resolution").value;
  editorConfig.display.fullscreen = field("fullscreen").checked;
  editorConfig.display.brightness = Number(field("brightness").value);
  editorConfig.display.background_dim = Number(field("background-dim").value);
  editorConfig.display.render_scale = Number(field("render-scale").value);
  editorConfig.display.splash = field("splash").value;
  editorConfig.display.background = field("background").value;
  editorConfig.obd.provider = field("provider").value;
  editorConfig.obd.elm327.port = field("elm-port").value.trim();
  editorConfig.obd.elm327.bluetooth_mac = field("elm-mac").value.trim();
  editorConfig.obd.elm327.allow_requests = field("elm-allow-requests").checked;
  editorConfig.dashboard.accent_color = field("accent-color").value;
  editorConfig.dashboard.status_enabled = field("status-enabled").checked;
  editorConfig.dashboard.oil_startup_toast = {
    ...(editorConfig.dashboard.oil_startup_toast || {}),
    enabled: field("oil-toast-enabled").checked,
    position: field("oil-toast-position").value,
    duration_seconds: Number(field("oil-toast-duration").value),
    x_pct: Number(field("oil-toast-x").value),
    y_pct: Number(field("oil-toast-y").value),
    width_pct: Number(field("oil-toast-width").value),
    source: "oil_level_method_2_pct",
    warn_pct: 30,
    critical_pct: 20,
  };
  editorConfig.dashboard.dtc_startup_toast = {
    ...(editorConfig.dashboard.dtc_startup_toast || {}),
    enabled: field("dtc-toast-enabled").checked,
    position: field("dtc-toast-position").value,
    duration_seconds: Number(field("dtc-toast-duration").value),
    x_pct: Number(field("dtc-toast-x").value),
    y_pct: Number(field("dtc-toast-y").value),
    width_pct: Number(field("dtc-toast-width").value),
  };
  editorConfig.dashboard.editor_snap = field("editor-snap").checked;
  editorConfig.dashboard.editor_grid_size = Number(field("editor-grid-size").value);
  normalizeWidgetThemes();
  return editorConfig;
}

async function saveEditorConfig({ reload = true } = {}) {
  updateSelectedWidgetFromControls();
  const response = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectConfig()),
  });
  if (!response.ok) {
    alert("Opslaan mislukt");
    return false;
  }
  if (reload) window.location.reload();
  return true;
}

async function refreshEditorConfig() {
  const response = await fetch(`/api/config?v=${Date.now()}`);
  editorConfig = await response.json();
  if (!editorConfig.dashboard.widget_order) {
    editorConfig.dashboard.widget_order = Object.keys(editorConfig.dashboard.widgets || {});
  }
  selectedWidgetId = editorConfig.dashboard.widgets[selectedWidgetId] ? selectedWidgetId : widgetOrder()[0];
  renderEditor();
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  field("layout-output").textContent = JSON.stringify(data, null, 2);
  if (!response.ok) throw new Error(data.error || "API fout");
  return data;
}

async function runPersistedAction(action) {
  const saved = await saveEditorConfig({ reload: false });
  if (!saved) return;
  try {
    await action();
    await refreshEditorConfig();
  } catch (error) {
    field("layout-output").textContent = String(error.message || error);
  }
}

field("save-config").addEventListener("click", () => saveEditorConfig());
field("refresh-pi-status").addEventListener("click", loadPiStatus);

field("detect-hex").addEventListener("click", async () => {
  const response = await fetch("/api/obd/hexv2");
  field("hex-output").textContent = JSON.stringify(await response.json(), null, 2);
});

field("detect-elm").addEventListener("click", async () => {
  const response = await fetch("/api/obd/elm327");
  const data = await response.json();
  const selected = data.ports?.find((port) => port.recommended) || data.ports?.find((port) => port.adapter_present) || data.ports?.[0];
  if (selected?.device) {
    field("provider").value = "elm327";
    field("elm-port").value = selected.device;
    editorConfig.obd.provider = "elm327";
    editorConfig.obd.elm327.port = selected.device;
    editorConfig.obd.elm327.allow_requests = true;
    field("elm-allow-requests").checked = true;
    if (selected.baudrate) editorConfig.obd.elm327.baudrate = selected.baudrate;
    await loadCapabilities("elm327");
  }
  field("hex-output").textContent = JSON.stringify(data, null, 2);
});

field("provider").addEventListener("change", () => loadCapabilities(field("provider").value));
field("add-category").addEventListener("change", populateAddSourceSelect);
field("edit-widget").addEventListener("change", () => {
  selectedWidgetId = field("edit-widget").value;
  renderEditor();
});
for (const id of ["edit-source", "edit-style", "edit-font-size", "edit-width", "edit-color", "edit-x", "edit-y"]) {
  field(id).addEventListener("input", updateSelectedWidgetFromControls);
  field(id).addEventListener("change", updateSelectedWidgetFromControls);
}
field("add-widget").addEventListener("click", addWidget);
field("remove-widget").addEventListener("click", removeWidget);
field("duplicate-widget").addEventListener("click", () => runPersistedAction(() => postJson(`/api/widgets/${selectedWidgetId}/duplicate`)));
field("snap-widget").addEventListener("click", () => runPersistedAction(() => postJson(`/api/widgets/${selectedWidgetId}/snap`)));
field("auto-grid").addEventListener("click", () => runPersistedAction(() => postJson("/api/widgets/auto-layout", { strategy: "grid", padding: 2, startX: 0, startY: 0 })));
field("auto-row").addEventListener("click", () => runPersistedAction(() => postJson("/api/widgets/auto-layout", { strategy: "row", padding: 2, startX: 0, startY: 0 })));
field("auto-column").addEventListener("click", () => runPersistedAction(() => postJson("/api/widgets/auto-layout", { strategy: "column", padding: 2, startX: 0, startY: 0 })));
field("check-overlaps").addEventListener("click", async () => {
  const response = await fetch("/api/widgets/overlaps");
  field("layout-output").textContent = JSON.stringify(await response.json(), null, 2);
});
field("check-free-space").addEventListener("click", async () => {
  const response = await fetch("/api/widgets/free-space");
  field("layout-output").textContent = JSON.stringify(await response.json(), null, 2);
});
field("save-layout").addEventListener("click", () => runPersistedAction(() => postJson("/api/layouts", { name: field("layout-name").value.trim() || "Preset" })));
field("apply-layout").addEventListener("click", () => runPersistedAction(async () => {
  const name = encodeURIComponent(field("layout-name").value.trim());
  if (!name) throw new Error("Presetnaam ontbreekt");
  const response = await fetch(`/api/layouts/${name}/apply`, { method: "PUT" });
  const data = await response.json();
  field("layout-output").textContent = JSON.stringify(data, null, 2);
  if (!response.ok) throw new Error(data.error || "API fout");
}));
field("delete-layout").addEventListener("click", () => runPersistedAction(async () => {
  const name = encodeURIComponent(field("layout-name").value.trim());
  if (!name) throw new Error("Presetnaam ontbreekt");
  const response = await fetch(`/api/layouts/${name}`, { method: "DELETE" });
  const data = await response.json();
  field("layout-output").textContent = JSON.stringify(data, null, 2);
  if (!response.ok) throw new Error(data.error || "API fout");
}));
document.addEventListener("keydown", nudgeSelectedWidget);
field("editor-snap").addEventListener("change", () => {
  editorConfig.dashboard.editor_snap = field("editor-snap").checked;
  renderEditor();
});
field("editor-grid-size").addEventListener("input", () => {
  editorConfig.dashboard.editor_grid_size = Number(field("editor-grid-size").value);
  renderEditor();
});

function widgetThemeId(widget) {
  if (widget.displayType) return widget.displayType;
  const style = widget.style || "digitaal";
  const legacy = { gauge: "golf7", digital: "digitaal" };
  const renderer = legacy[style] || style;
  return currentThemes.find((theme) => theme.renderer === renderer)?.id || "Digitaal";
}

function themeRenderer(themeId) {
  return currentThemes.find((theme) => theme.id === themeId)?.renderer || "digitaal";
}

function normalizeWidgetThemes() {
  for (const widget of Object.values(editorConfig.dashboard.widgets || {})) {
    const themeId = widgetThemeId(widget);
    widget.displayType = themeId;
    widget.style = themeRenderer(themeId);
  }
}

async function bootAdmin() {
  await loadThemes();
  await loadCapabilities();
  await loadPiStatus();
  window.setInterval(loadPiStatus, 10000);
}

bootAdmin();
