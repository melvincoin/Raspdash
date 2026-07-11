let config = JSON.parse(document.body.dataset.config || "{}");
let widgets = config.dashboard?.widgets || {};
let widgetOrder = config.dashboard?.widget_order || Object.keys(widgets);
let latestVehicleData = {};
let statusText = "INITIALIZING";
let lastConfigSignature = JSON.stringify(config);
let backgroundImage = null;
let backgroundImageKey = "";
let backgroundCache = null;
let backgroundCacheKey = "";
let drawQueued = false;
let firstFrameShown = false;
let previousRpm = 0;
let oilToastUntil = 0;
let oilToastStartedAt = 0;
let oilToastSeenForStart = false;
let oilToastPendingForStart = false;
let dtcToastUntil = 0;
let dtcToastStartedAt = 0;
let dtcToastSignature = "";
let oilIconImage = null;
let oilIconTintCache = null;
let oilIconTintCacheKey = "";
let actIconImage = null;
let actEcoIconImage = null;
let lastVehicleRenderSignature = "";

const canvas = document.getElementById("dashboard-canvas");
const ctx = canvas.getContext("2d", { alpha: false });
const PARAMETER_META = {
  battery_voltage_v: { label: "BATTERY", unit: "V", min: 10, max: 16 },
  coolant_temp_c: { label: "COOLANT", unit: "deg C", min: 40, max: 130 },
  intake_temp_c: { label: "INTAKE AIR", unit: "deg C", min: -20, max: 80 },
  rpm: { label: "RPM", unit: "rpm", min: 0, max: 8000 },
  speed_kmh: { label: "SPEED", unit: "km/h", min: 0, max: 240 },
  throttle_pct: { label: "THROTTLE", unit: "%", min: 0, max: 100 },
  engine_load_pct: { label: "LOAD", unit: "%", min: 0, max: 100 },
  fuel_consumption_l_per_100km: { label: "CONSUMPTION", unit: "L/100km", min: 0, max: 30 },
  map_kpa: { label: "MAP", unit: "kPa", min: 20, max: 250 },
  barometric_pressure_kpa: { label: "BARO", unit: "kPa", min: 90, max: 110 },
  boost_bar: { label: "BOOST", unit: "bar", min: 0, max: 2.5 },
  boost_estimated_bar: { label: "BOOST EST", unit: "bar", min: -1, max: 2.5 },
  oil_pan_temp_c: { label: "OIL PAN", unit: "deg C", min: 40, max: 130 },
  transmission_fluid_temp_c: { label: "DSG OIL", unit: "deg C", min: 20, max: 130 },
  tcu_module_temp_c: { label: "TCU", unit: "deg C", min: 0, max: 110 },
  absolute_intake_pressure_bar: { label: "INTAKE ABS", unit: "bar", min: 0, max: 2.5 },
  ambient_air_pressure_bar: { label: "AMBIENT", unit: "bar", min: 0.7, max: 1.1 },
  engine_oil_pressure_actual_bar: { label: "OIL PRESSURE", unit: "bar", min: 0, max: 8 },
  engine_oil_pressure_setpoint_bar: { label: "OIL PRESS SET", unit: "bar", min: 0, max: 8 },
  transmission_oil_pressure_actual_bar: { label: "DSG PRESSURE", unit: "bar", min: 0, max: 30 },
  transmission_input_speed_rpm: { label: "DSG INPUT", unit: "rpm", min: 0, max: 8000 },
  oil_level_available: { label: "OIL LEVEL", unit: "status", min: 0, max: 1 },
  oil_level_method_1_pct: { label: "OIL LVL 1", unit: "%", min: 0, max: 100 },
  oil_level_method_2_pct: { label: "OIL LEVEL", unit: "%", min: 0, max: 100 },
  oil_level_method_3_pct: { label: "OIL LVL 3", unit: "%", min: 0, max: 100 },
  oil_level_max_relative_pct: { label: "OIL MAX", unit: "%", min: 0, max: 100 },
  oil_level_min_relative_pct: { label: "OIL MIN", unit: "%", min: 0, max: 100 },
  oil_level_current_pct: { label: "OIL CURRENT", unit: "%", min: 0, max: 100 },
  oil_temp_c: { label: "ENGINE OIL", unit: "deg C", min: 40, max: 130 },
  dsg_temp_c: { label: "DSG TEMP", unit: "deg C", min: 40, max: 130 },
};

function resizeCanvas() {
  const width = Math.max(1, window.innerWidth);
  const height = Math.max(1, window.innerHeight);
  const renderScale = Math.max(0.35, Math.min(1, Number(config.display?.render_scale ?? 0.6)));
  canvas.width = Math.floor(width * renderScale);
  canvas.height = Math.floor(height * renderScale);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(renderScale, 0, 0, renderScale, 0, 0);
  backgroundCache = null;
  oilIconTintCache = null;
  oilIconTintCacheKey = "";
  queueDraw();
}

function configuredBackgroundUrl(background) {
  if (["carbon-pattern", "dark-gray", "vw-blue"].includes(background)) return "";
  return `/uploads/backgrounds/${encodeURIComponent(background)}`;
}

function loadBackgroundIfNeeded() {
  const key = config.display?.background || "carbon-pattern";
  if (key === backgroundImageKey) return;
  backgroundImageKey = key;
  backgroundImage = null;
  backgroundCache = null;
  const url = configuredBackgroundUrl(key);
  if (!url) {
    queueDraw();
    return;
  }
  const image = new Image();
  image.onload = () => {
    backgroundImage = image;
    queueDraw();
  };
  image.onerror = () => {
    backgroundImage = null;
    queueDraw();
  };
  image.src = `${url}?v=${Date.now()}`;
}

function loadOilIcon() {
  oilIconImage = new Image();
  oilIconImage.onload = () => {
    oilIconTintCache = null;
    oilIconTintCacheKey = "";
    queueDraw();
  };
  oilIconImage.src = `/static/img/oil-level.svg?v=${Date.now()}`;
}

function loadActIcon() {
  actIconImage = new Image();
  actIconImage.onload = () => queueDraw();
  actIconImage.src = `/static/img/act-active-icon.svg?v=${Date.now()}`;
}

function loadActEcoIcon() {
  actEcoIconImage = new Image();
  actEcoIconImage.onload = () => queueDraw();
  actEcoIconImage.src = `/static/img/act-eco-icon.svg?v=${Date.now()}`;
}

function applyConfig(nextConfig) {
  const previousScale = config.display?.render_scale;
  config = nextConfig;
  widgets = config.dashboard?.widgets || {};
  widgetOrder = config.dashboard?.widget_order || Object.keys(widgets);
  loadBackgroundIfNeeded();
  if (previousScale !== config.display?.render_scale) {
    resizeCanvas();
    return;
  }
  backgroundCache = null;
  queueDraw();
}

function drawBackground(width, height) {
  const cacheKey = `${width}x${height}:${config.display?.background}:${config.display?.background_dim}:${backgroundImageKey}:${backgroundImage ? "img" : "preset"}`;
  if (backgroundCache && backgroundCacheKey === cacheKey) {
    ctx.drawImage(backgroundCache, 0, 0, width, height);
    return;
  }

  const cache = document.createElement("canvas");
  cache.width = canvas.width;
  cache.height = canvas.height;
  const targetCtx = ctx;
  const oldCanvasCtx = ctx;
  const cacheCtx = cache.getContext("2d", { alpha: false });
  cacheCtx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
  const previousCtxState = currentCtx;
  currentCtx = cacheCtx;
  drawBackgroundUncached(width, height);
  currentCtx = previousCtxState;
  backgroundCache = cache;
  backgroundCacheKey = cacheKey;
  targetCtx.drawImage(cache, 0, 0, width, height);
}

let currentCtx = ctx;

function drawBackgroundUncached(width, height) {
  const c = currentCtx;
  const background = config.display?.background || "carbon-pattern";
  c.fillStyle = "#030507";
  c.fillRect(0, 0, width, height);

  if (backgroundImage) {
    const scale = Math.max(width / backgroundImage.width, height / backgroundImage.height);
    const drawWidth = backgroundImage.width * scale;
    const drawHeight = backgroundImage.height * scale;
    c.drawImage(backgroundImage, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
  } else if (background === "vw-blue") {
    const gradient = c.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#03070d");
    gradient.addColorStop(0.55, "#071c36");
    gradient.addColorStop(1, "#030507");
    c.fillStyle = gradient;
    c.fillRect(0, 0, width, height);
  } else if (background === "dark-gray") {
    const gradient = c.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#030405");
    gradient.addColorStop(0.48, "#10151c");
    gradient.addColorStop(1, "#05070a");
    c.fillStyle = gradient;
    c.fillRect(0, 0, width, height);
  } else {
    drawCarbon(width, height, c);
  }

  const dim = Number(config.display?.background_dim ?? 0.72);
  c.fillStyle = `rgba(0, 0, 0, ${Math.max(0, Math.min(0.95, dim))})`;
  c.fillRect(0, 0, width, height);

  const glow = c.createRadialGradient(width * 0.5, height * 0.45, 0, width * 0.5, height * 0.45, width * 0.48);
  glow.addColorStop(0, "rgba(45, 125, 255, 0.10)");
  glow.addColorStop(1, "rgba(45, 125, 255, 0)");
  c.fillStyle = glow;
  c.fillRect(0, 0, width, height);
}

function drawCarbon(width, height, c = ctx) {
  c.fillStyle = "#05070a";
  c.fillRect(0, 0, width, height);
  c.strokeStyle = "rgba(255,255,255,0.035)";
  c.lineWidth = 1;
  for (let y = -height; y < height * 2; y += 14) {
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(width, y + width);
    c.stroke();
  }
  c.strokeStyle = "rgba(0,0,0,0.5)";
  for (let y = 0; y < height * 2; y += 14) {
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(width, y - width);
    c.stroke();
  }
}

function formatValue(value, source) {
  if (value === null || value === undefined) return "---";
  if (source === "oil_level_available") return value ? "ok" : "check";
  if (source.endsWith("_temp_c")) return `${String(Math.round(value)).padStart(3, "0")}${String.fromCharCode(176)}C`;
  if (source === "battery_voltage_v") return `${Number(value).toFixed(1).replace(".", ",")}V`;
  if (source.endsWith("_bar")) return `${Number(value).toFixed(2).replace(".", ",")}bar`;
  if (source.endsWith("_kpa")) return `${Math.round(value)}kPa`;
  if (source === "rpm" || source.endsWith("_rpm")) return `${Math.round(value)}rpm`;
  if (source.endsWith("_raw")) return String(value);
  if (source === "speed_kmh") return `${Math.round(value)}km/h`;
  if (source === "fuel_consumption_l_per_100km") return `${Number(value).toFixed(1).replace(".", ",")}L/100km`;
  if (source.endsWith("_pct")) return `${Math.round(value)}%`;
  return String(value);
}

function formatValueParts(value, source) {
  if (value === null || value === undefined) return { number: "---", unit: "" };
  if (source === "oil_level_available") return { number: value ? "ok" : "check", unit: "" };
  if (source.endsWith("_temp_c")) return { number: String(Math.round(value)), unit: `${String.fromCharCode(176)}C` };
  if (source === "battery_voltage_v") return { number: Number(value).toFixed(1).replace(".", ","), unit: "V" };
  if (source.endsWith("_bar")) return { number: Number(value).toFixed(2).replace(".", ","), unit: "bar" };
  if (source.endsWith("_kpa")) return { number: String(Math.round(value)), unit: "kPa" };
  if (source === "rpm" || source.endsWith("_rpm")) return { number: String(Math.round(value)), unit: "rpm" };
  if (source.endsWith("_raw")) return { number: String(value), unit: "" };
  if (source === "speed_kmh") return { number: String(Math.round(value)), unit: "km/h" };
  if (source === "fuel_consumption_l_per_100km") return { number: Number(value).toFixed(1).replace(".", ","), unit: "L/100km" };
  if (source.endsWith("_pct")) return { number: String(Math.round(value)), unit: "%" };
  return { number: String(value), unit: "" };
}

function valueRatio(value, source) {
  if (value === null || value === undefined) return 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  const meta = PARAMETER_META[source] || { min: 0, max: 100 };
  const min = Number(meta.min);
  const max = Number(meta.max);
  const clamped = Math.max(min, Math.min(max, Number(value)));
  return (clamped - min) / (max - min);
}

function warningColor(value, source, normalColor) {
  if (value === null || value === undefined) return normalColor;
  if (source === "oil_level_available") return value ? "#37d67a" : "#ff2f2f";
  if (source.startsWith("oil_level_") && source.endsWith("_pct")) {
    if (Number(value) < 20) return "#ff2f2f";
    if (Number(value) <= 30) return "#ffb02e";
    return "#37d67a";
  }
  const thresholds = config.dashboard?.warning_thresholds || {};
  const threshold = thresholds[source];
  if (!threshold) return normalColor;
  const numeric = Number(value);
  if (numeric >= Number(threshold.critical)) return "#ff2f2f";
  if (numeric >= Number(threshold.warn)) return "#ffb02e";
  return normalColor;
}

function updateOilStartupToast(vehicleData) {
  if (config.dashboard?.oil_startup_toast?.enabled === false) return;
  const rpm = Number(vehicleData?.rpm || 0);
  const engineRunning = rpm > 250;
  const wasRunning = previousRpm > 250;
  previousRpm = rpm;

  if (!engineRunning) {
    oilToastSeenForStart = false;
    oilToastPendingForStart = false;
    return;
  }
  if (!wasRunning && !oilToastSeenForStart) {
    oilToastPendingForStart = true;
  }

  const source = config.dashboard?.oil_startup_toast?.source || "oil_level_method_2_pct";
  const oilLevel = Number(vehicleData?.[source]);
  const oilLevelReady =
    vehicleData?.oil_level_available === true &&
    Number.isFinite(oilLevel) &&
    oilLevel > 0 &&
    oilLevel <= 100;
  if (oilToastPendingForStart && oilLevelReady) {
    oilToastPendingForStart = false;
    oilToastSeenForStart = true;
    const duration = Number(config.dashboard?.oil_startup_toast?.duration_seconds ?? 60);
    oilToastStartedAt = performance.now();
    oilToastUntil = oilToastStartedAt + Math.max(1, duration) * 1000;
  }
}

function updateDtcStartupToast(vehicleData) {
  if (config.dashboard?.dtc_startup_toast?.enabled === false) return;
  const alerts = Array.isArray(vehicleData?.dtc_alerts) ? vehicleData.dtc_alerts : [];
  if (!alerts.length) return;
  const signature = JSON.stringify(alerts);
  if (signature === dtcToastSignature) return;
  dtcToastSignature = signature;
  const duration = Number(config.dashboard?.dtc_startup_toast?.duration_seconds ?? 90);
  dtcToastStartedAt = performance.now();
  dtcToastUntil = dtcToastStartedAt + Math.max(1, duration) * 1000;
}

function toastFade(startedAt, until) {
  const now = performance.now();
  if (!startedAt || now >= until) return 0;
  const fadeIn = Math.min(1, (now - startedAt) / 450);
  const fadeOut = Math.min(1, (until - now) / 2500);
  return Math.max(0, Math.min(fadeIn, fadeOut));
}

function drawToastBackdrop(width, height) {
  const oilFade = config.dashboard?.oil_startup_toast?.enabled === false ? 0 : toastFade(oilToastStartedAt, oilToastUntil);
  const dtcFade = config.dashboard?.dtc_startup_toast?.enabled === false ? 0 : toastFade(dtcToastStartedAt, dtcToastUntil);
  const fade = Math.max(oilFade, dtcFade);
  if (fade <= 0) return;
  ctx.save();
  ctx.fillStyle = `rgba(0, 0, 0, ${0.52 * fade})`;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
  if (fade < 0.999) queueDraw();
}

function oilLevelToastState() {
  const toastConfig = config.dashboard?.oil_startup_toast || {};
  const source = toastConfig.source || "oil_level_method_2_pct";
  const warnPct = Number(toastConfig.warn_pct ?? 30);
  const criticalPct = Number(toastConfig.critical_pct ?? 20);
  const raw = latestVehicleData[source];
  const pct = Number(raw);
  if (!Number.isFinite(pct)) {
    return latestVehicleData.oil_level_available === false
      ? { label: "check", detail: "Oliepeil", color: "#ff2f2f" }
      : { label: "onbekend", detail: "Oliepeil", color: "#9fb1c4" };
  }
  if (pct < criticalPct) return { label: `${Math.round(pct)}%`, detail: "Oliepeil", color: "#ff2f2f" };
  if (pct <= warnPct) return { label: `${Math.round(pct)}%`, detail: "Oliepeil", color: "#ffb02e" };
  return { label: `${Math.round(pct)}%`, detail: "Oliepeil", color: "#37d67a" };
}

function drawOilIcon(c, x, y, scale, color) {
  const width = 900 * scale;
  const height = 900 * scale;
  c.save();
  if (oilIconImage?.complete) {
    const cacheWidth = Math.max(1, Math.ceil(width));
    const cacheHeight = Math.max(1, Math.ceil(height));
    const cacheKey = `${cacheWidth}x${cacheHeight}:${color}`;
    if (!oilIconTintCache || oilIconTintCacheKey !== cacheKey) {
      const mask = document.createElement("canvas");
      mask.width = cacheWidth;
      mask.height = cacheHeight;
      const maskCtx = mask.getContext("2d");
      maskCtx.drawImage(oilIconImage, 0, 0, cacheWidth, cacheHeight);
      maskCtx.globalCompositeOperation = "source-in";
      maskCtx.fillStyle = color;
      maskCtx.fillRect(0, 0, cacheWidth, cacheHeight);
      oilIconTintCache = mask;
      oilIconTintCacheKey = cacheKey;
    }
    c.drawImage(oilIconTintCache, x, y, width, height);
  } else {
    c.fillStyle = color;
    c.font = `900 ${Math.max(32, height * 0.55)}px Segoe UI Symbol, Arial, sans-serif`;
    c.fillText("oil", x, y + height * 0.62);
  }
  c.restore();
}

function roundedRectPath(c, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  c.moveTo(x + r, y);
  c.lineTo(x + width - r, y);
  c.quadraticCurveTo(x + width, y, x + width, y + r);
  c.lineTo(x + width, y + height - r);
  c.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  c.lineTo(x + r, y + height);
  c.quadraticCurveTo(x, y + height, x, y + height - r);
  c.lineTo(x, y + r);
  c.quadraticCurveTo(x, y, x + r, y);
}

function toastBounds(width, height, toastWidth, toastHeight, toastConfig, fallbackPosition) {
  const position = toastConfig.position || fallbackPosition;
  const margin = Math.max(16, width * 0.018);
  const verticalOffset = Math.max(12, height * (Number(toastConfig.y_pct ?? 5.5) / 100));
  const defaultCenterX = position.endsWith("-left")
    ? margin + toastWidth / 2
    : position.endsWith("-right")
      ? width - margin - toastWidth / 2
      : width / 2;
  const centerX = toastConfig.x_pct == null ? defaultCenterX : width * Number(toastConfig.x_pct) / 100;
  const x = Math.max(margin, Math.min(width - toastWidth - margin, centerX - toastWidth / 2));
  const y = position.startsWith("bottom-") ? height - toastHeight - verticalOffset : verticalOffset;
  return { x, y };
}

function drawOilStartupToast(width, height) {
  if (config.dashboard?.oil_startup_toast?.enabled === false) return;
  if (performance.now() > oilToastUntil) return;
  const toastConfig = config.dashboard?.oil_startup_toast || {};
  const state = oilLevelToastState();
  const toastWidth = width * (Number(toastConfig.width_pct ?? 46) / 100);
  const toastHeight = Math.max(92, Math.min(130, height * 0.14));
  const { x, y } = toastBounds(width, height, toastWidth, toastHeight, toastConfig, "top-center");
  const radius = Math.min(14, toastHeight * 0.16);

  ctx.save();
  ctx.globalAlpha = toastFade(oilToastStartedAt, oilToastUntil);
  ctx.fillStyle = "rgba(3, 7, 10, 0.92)";
  ctx.strokeStyle = state.color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  roundedRectPath(ctx, x, y, toastWidth, toastHeight, radius);
  ctx.fill();
  ctx.stroke();

  const contentY = y + toastHeight / 2;
  const iconSize = toastHeight * 0.575;
  const valueSize = Math.max(50, toastHeight * 0.525);
  const gap = toastHeight * 0.14;
  ctx.font = `800 ${valueSize}px "VW Head", Arial, sans-serif`;
  const totalWidth = iconSize + gap + ctx.measureText(state.label).width;
  const contentX = x + (toastWidth - totalWidth) / 2;
  const iconScale = iconSize / 900;
  const iconX = contentX;
  const iconY = contentY - iconSize / 2;
  drawOilIcon(ctx, iconX, iconY, iconScale, state.color);

  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = state.color;
  ctx.font = `800 ${valueSize}px "VW Head", Arial, sans-serif`;
  ctx.fillText(state.label, iconX + iconSize + gap, contentY);
  ctx.restore();
}

function drawDtcStartupToast(width, height) {
  if (config.dashboard?.dtc_startup_toast?.enabled === false) return;
  if (performance.now() > dtcToastUntil) return;
  const alerts = Array.isArray(latestVehicleData.dtc_alerts) ? latestVehicleData.dtc_alerts : [];
  if (!alerts.length) return;

  const toastConfig = config.dashboard?.dtc_startup_toast || {};
  const visibleAlerts = alerts.slice(0, 4);
  const toastWidth = width * (Number(toastConfig.width_pct ?? 60) / 100);
  const toastHeight = Math.max(118, 58 + visibleAlerts.length * 30);
  const { x, y } = toastBounds(width, height, toastWidth, toastHeight, toastConfig, "bottom-center");
  const radius = Math.min(14, toastHeight * 0.14);

  ctx.save();
  ctx.globalAlpha = toastFade(dtcToastStartedAt, dtcToastUntil);
  ctx.fillStyle = "rgba(8, 5, 5, 0.94)";
  ctx.strokeStyle = "rgba(255, 80, 80, 0.58)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  roundedRectPath(ctx, x, y, toastWidth, toastHeight, radius);
  ctx.fill();
  ctx.stroke();

  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#ff3a3a";
  ctx.font = `850 ${Math.max(26, toastHeight * 0.20)}px \"VW Head\", Arial, sans-serif`;
  ctx.fillText("OBD foutcodes", x + 24, y + 28);

  ctx.font = `750 ${Math.max(20, toastHeight * 0.15)}px \"VW Text\", Arial, sans-serif`;
  let lineY = y + 62;
  for (const alert of visibleAlerts) {
    const code = String(alert.code || "---");
    const status = String(alert.status || "unknown");
    const moduleName = String(alert.module || "Module");
    ctx.fillStyle = status === "pending" ? "#ffb02e" : "#ff3a3a";
    ctx.fillText(`${code}  ${status}  ${moduleName}`, x + 24, lineY);
    lineY += 30;
  }
  if (alerts.length > visibleAlerts.length) {
    ctx.fillStyle = "#d9e6f5";
    ctx.fillText(`+${alerts.length - visibleAlerts.length} meer`, x + 24, lineY);
  }
  ctx.restore();
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} value        - huidige waarde (raw)
 * @param {number} min          - minimumwaarde van parameter
 * @param {number} max          - maximumwaarde van parameter
 * @param {string} label        - parameternaam (bijv. "RPM")
 * @param {string} unit         - eenheid (bijv. "rpm", "km/h")
 * @param {string} accentColor  - dashboard accentkleur (hex)
 * @param {number} fontSize     - basisgrootte in pixels
 */
function drawGauge(widget, x, y, size, value, source) {
  const radius = size / 2;
  const cx = x + radius;
  const cy = y + radius;
  const start = Math.PI * 0.75;
  const end = Math.PI * 2.25;
  const ratio = valueRatio(value, source);
  const accent = warningColor(value, source, config.dashboard?.accent_color || "#2d7dff");

  ctx.save();
  ctx.translate(cx, cy);

  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.96, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(3, 7, 13, 0.94)";
  ctx.fill();
  ctx.lineWidth = Math.max(2, size * 0.012);
  ctx.strokeStyle = "rgba(220,235,255,0.14)";
  ctx.stroke();

  ctx.lineCap = "round";
  ctx.lineWidth = Math.max(8, size * 0.055);
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.78, start, end);
  ctx.strokeStyle = "rgba(72, 84, 101, 0.62)";
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.78, start, start + (end - start) * ratio);
  ctx.strokeStyle = accent;
  ctx.stroke();

  ctx.lineWidth = Math.max(1, size * 0.006);
  ctx.strokeStyle = "rgba(230,241,255,0.46)";
  for (let i = 0; i <= 24; i += 1) {
    const angle = start + ((end - start) * i) / 24;
    const inner = radius * (i % 4 === 0 ? 0.66 : 0.7);
    const outer = radius * 0.74;
    ctx.beginPath();
    ctx.moveTo(Math.cos(angle) * inner, Math.sin(angle) * inner);
    ctx.lineTo(Math.cos(angle) * outer, Math.sin(angle) * outer);
    ctx.stroke();
  }

  drawWidgetText(widget, 0, 0, size, value, source, true);
  ctx.restore();
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} value        - huidige waarde (raw)
 * @param {number} min          - minimumwaarde van parameter
 * @param {number} max          - maximumwaarde van parameter
 * @param {string} label        - parameternaam (bijv. "RPM")
 * @param {string} unit         - eenheid (bijv. "rpm", "km/h")
 * @param {string} accentColor  - dashboard accentkleur (hex)
 * @param {number} fontSize     - basisgrootte in pixels
 */
function drawDigital(widget, x, y, width, height, value, source) {
  ctx.save();
  const panelGradient = ctx.createLinearGradient(x, y, x, y + height);
  panelGradient.addColorStop(0, "rgba(15, 25, 34, 0.70)");
  panelGradient.addColorStop(0.52, "rgba(4, 10, 17, 0.86)");
  panelGradient.addColorStop(1, "rgba(12, 20, 29, 0.76)");

  ctx.fillStyle = panelGradient;
  const oilLevelSource = source === "oil_level_available" || (source.startsWith("oil_level_") && source.endsWith("_pct"));
  ctx.strokeStyle = oilLevelSource ? warningColor(value, source, "#9fb1c4") : "rgba(145, 172, 202, 0.34)";
  ctx.lineWidth = Math.max(1, width * 0.002);
  ctx.beginPath();
  ctx.rect(x, y, width, height);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "rgba(255, 255, 255, 0.035)";
  ctx.fillRect(x + 1, y + 1, width - 2, Math.max(1, height * 0.18));
  drawWidgetText(widget, x + width / 2, y + height / 2, Math.min(width, height * 2), value, source, false);
  ctx.restore();
}

function widgetRenderer(widget) {
  const style = widget.displayType || widget.style || "digitaal";
  const mapping = {
    "Golf 7 klok": "golf7",
    "Golf 8 klok": "golf8",
    "VW Retro": "retro",
    "Digitaal": "digitaal",
    gauge: "golf7",
    digital: "digitaal",
  };
  return mapping[style] || style;
}

function drawWidgetText(widget, cx, cy, size, value, source, localCoordinates) {
  const label = widget.label || "";
  const text = formatValue(value, source);
  const parts = formatValueParts(value, source);
  const valueColor = warningColor(value, source, widget.color || "#f6fbff");
  const labelSize = Math.max(18, Math.min(32, size * 0.105));
  const requestedValueSize = Math.max(22, Number(widget.font_size || 56));
  const maxValueWidth = size * (localCoordinates ? 0.68 : 0.94);
  const baseY = localCoordinates ? 0 : cy;
  const labelY = baseY - size * 0.14;
  const valueY = baseY + size * 0.09;
  const minGap = labelSize * 0.85;

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `800 ${labelSize}px "VW Head", Arial, sans-serif`;
  ctx.fillStyle = config.dashboard?.dimmed_color || "#9fb1c4";
  ctx.fillText(label, cx, labelY);

  if (!localCoordinates) {
    drawValueParts(parts, cx, valueY, requestedValueSize, maxValueWidth, valueColor, source);
    return;
  }

  const valueSize = fitFontSize(text, requestedValueSize, 34, maxValueWidth, '"VW Head", Arial, sans-serif');
  const adjustedValueY = Math.max(valueY, labelY + minGap + valueSize * 0.42);
  ctx.font = `800 ${valueSize}px "VW Head", Arial, sans-serif`;
  ctx.fillStyle = valueColor;
  ctx.fillText(text, cx, adjustedValueY);
}

function drawValueParts(parts, cx, cy, preferredSize, maxWidth, color, source) {
  let numberSize = preferredSize;
  let unitSize = Math.max(18, preferredSize * 0.38);
  const gap = Math.max(4, preferredSize * 0.08);
  while (numberSize > 36) {
    unitSize = Math.max(18, numberSize * 0.38);
    ctx.font = `800 ${numberSize}px "VW Head", Arial, sans-serif`;
    const numberWidth = ctx.measureText(parts.number).width;
    ctx.font = `800 ${unitSize}px "VW Text", Arial, sans-serif`;
    const unitWidth = parts.unit ? ctx.measureText(parts.unit).width : 0;
    if (numberWidth + (parts.unit ? gap + unitWidth : 0) <= maxWidth) break;
    numberSize -= 2;
  }

  unitSize = Math.max(18, numberSize * 0.38);
  ctx.font = `800 ${numberSize}px \"VW Head\", Arial, sans-serif`;
  const numberWidth = ctx.measureText(parts.number).width;
  ctx.font = `800 ${unitSize}px \"VW Text\", Arial, sans-serif`;
  const unitWidth = parts.unit ? ctx.measureText(parts.unit).width : 0;
  const showEco = source === "fuel_consumption_l_per_100km" && latestVehicleData.act_active === true && actEcoIconImage?.complete;
  const ecoSize = unitSize * 2.47;
  const unitX = cx + preferredSize * 0.58;

  ctx.fillStyle = color;
  drawLocalizedNumber(parts.number, parts.unit ? unitX - gap : cx, cy, numberSize, parts.unit ? "right" : "center");
  if (parts.unit) {
    ctx.textAlign = "left";
    ctx.font = `800 ${unitSize}px "VW Text", Arial, sans-serif`;
    ctx.fillText(parts.unit, unitX, cy + numberSize * 0.14);
  }
  if (showEco) {
    ctx.drawImage(actEcoIconImage, unitX + unitWidth + gap, cy - ecoSize * 0.55, ecoSize, ecoSize);
  }
  ctx.textAlign = "center";
}

function drawLocalizedNumber(text, anchorX, cy, size, align) {
  const value = String(text);
  if (!value.includes(",")) {
    ctx.font = `800 ${size}px "VW Head", Arial, sans-serif`;
    ctx.textAlign = align;
    ctx.fillText(value, anchorX, cy);
    return;
  }
  const [integer, decimal] = value.split(",", 2);
  const commaSize = size * 0.55;
  ctx.font = `800 ${size}px "VW Head", Arial, sans-serif`;
  const integerWidth = ctx.measureText(integer).width;
  const decimalWidth = ctx.measureText(decimal).width;
  ctx.font = `800 ${commaSize}px "VW Text", Arial, sans-serif`;
  const commaWidth = ctx.measureText(",").width;
  const totalWidth = integerWidth + commaWidth + decimalWidth;
  const startX = align === "right" ? anchorX - totalWidth : anchorX - totalWidth / 2;
  ctx.textAlign = "left";
  ctx.font = `800 ${size}px "VW Head", Arial, sans-serif`;
  ctx.fillText(integer, startX, cy);
  ctx.font = `800 ${commaSize}px "VW Text", Arial, sans-serif`;
  ctx.fillText(",", startX + integerWidth, cy + size * 0.17);
  ctx.font = `800 ${size}px "VW Head", Arial, sans-serif`;
  ctx.fillText(decimal, startX + integerWidth + commaWidth, cy);
}

function fitFontSize(text, preferred, minimum, maxWidth, family) {
  let size = preferred;
  while (size > minimum) {
    ctx.font = `800 ${size}px ${family}`;
    if (ctx.measureText(text).width <= maxWidth) return size;
    size -= 2;
  }
  return minimum;
}

function drawStatus(width, height) {
  if (config.dashboard?.status_enabled === false) return;
  const normalized = String(statusText || "").toLowerCase();
  const hasError =
    latestVehicleData.connected === false ||
    normalized.includes("error") ||
    normalized.includes("no data") ||
    normalized.includes("offline") ||
    normalized.includes("disconnected") ||
    normalized.includes("unable") ||
    normalized.includes("reconnecting");
  if (!hasError) return;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `650 ${Math.max(12, width * 0.014)}px \"VW Text\", Arial, sans-serif`;
  ctx.fillStyle = config.dashboard?.dimmed_color || "#7e8fa8";
  ctx.fillText(statusText, width / 2, height * 0.955);
}

function drawActIndicator(x, y, width, height) {
  if (!actIconImage?.complete) return;
  const size = Math.min(width, height);
  ctx.drawImage(actIconImage, x + (width - size) / 2, y + (height - size) / 2, size, size);
}

function draw() {
  drawQueued = false;
  const width = window.innerWidth;
  const height = window.innerHeight;
  drawBackground(width, height);

  for (const widgetId of widgetOrder) {
    const widget = widgets[widgetId];
    if (!widget || widget.enabled === false) continue;
    const source = widget.source || "battery_voltage_v";
    const value = latestVehicleData[source];
    const x = (Number(widget.x ?? 10) / 100) * width;
    const y = (Number(widget.y ?? 30) / 100) * height;
    const w = (Number(widget.width ?? 28) / 100) * width;
    const renderer = widgetRenderer(widget);
    const meta = PARAMETER_META[source] || { label: widget.label || source, unit: "", min: 0, max: 100 };
    if (source === "act_active") {
      if (value === true) drawActIndicator(x, y, w, w);
      continue;
    }
    if (renderer === "retro" && typeof window.renderRetro === "function") {
      window.renderRetro(ctx, value, Number(meta.min), Number(meta.max), widget.label || meta.label, meta.unit, config.dashboard?.accent_color || "#2d7dff", Number(widget.font_size || 56), {
        x,
        y,
        size: Math.min(w, height * 0.55),
        text: formatValue(value, source),
      });
    } else if (renderer === "golf7" || renderer === "golf8") {
      drawGauge(widget, x, y, Math.min(w, height * 0.55), value, source);
    } else {
      drawDigital(widget, x, y, w, Math.max(92, height * Number(widget.height ?? 0.15)), value, source);
    }
  }
  drawStatus(width, height);
  drawToastBackdrop(width, height);
  drawOilStartupToast(width, height);
  drawDtcStartupToast(width, height);
  if (!firstFrameShown) {
    firstFrameShown = true;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        document.body.classList.add("dashboard-ready");
        fetch("/api/display/ready", { method: "POST", keepalive: true }).catch(() => {});
      });
    });
  }
}

function queueDraw() {
  if (drawQueued) return;
  drawQueued = true;
  window.requestAnimationFrame(draw);
}

async function loadSnapshot() {
  const response = await fetch("/api/vehicle");
  applyVehicleData(await response.json());
}

function vehicleRenderSignature(vehicleData) {
  const visibleValues = widgetOrder.map((widgetId) => {
    const source = widgets[widgetId]?.source;
    return source ? vehicleData?.[source] : null;
  });
  const oilSource = config.dashboard?.oil_startup_toast?.source || "oil_level_method_2_pct";
  return JSON.stringify([
    visibleValues,
    vehicleData?.connected,
    vehicleData?.status,
    vehicleData?.rpm,
    vehicleData?.act_active,
    vehicleData?.[oilSource],
    vehicleData?.oil_level_available,
    vehicleData?.dtc_alerts,
  ]);
}

function applyVehicleData(vehicleData) {
  latestVehicleData = vehicleData;
  updateOilStartupToast(vehicleData);
  updateDtcStartupToast(vehicleData);
  statusText = vehicleData.status || "NO DATA";

  const signature = vehicleRenderSignature(vehicleData);
  const toastActive = performance.now() < oilToastUntil || performance.now() < dtcToastUntil;
  if (signature !== lastVehicleRenderSignature || toastActive) {
    lastVehicleRenderSignature = signature;
    queueDraw();
  }
}

function connectVehicleSocket() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/vehicle`);
  socket.addEventListener("message", (event) => {
    applyVehicleData(JSON.parse(event.data));
  });
  socket.addEventListener("close", () => {
    statusText = "RECONNECTING";
    queueDraw();
    window.setTimeout(connectVehicleSocket, 1500);
  });
}

async function refreshConfig() {
  const response = await fetch(`/api/config?v=${Date.now()}`);
  const nextConfig = await response.json();
  const signature = JSON.stringify(nextConfig);
  if (signature !== lastConfigSignature) {
    lastConfigSignature = signature;
    applyConfig(nextConfig);
  }
}

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
applyConfig(config);
loadOilIcon();
loadActIcon();
loadActEcoIcon();
loadSnapshot().catch(() => {
  statusText = "BACKEND OFFLINE";
  queueDraw();
});
connectVehicleSocket();
window.setInterval(() => refreshConfig().catch(() => {}), 10000);
window.setTimeout(() => document.body.classList.add("dashboard-ready"), 1500);
