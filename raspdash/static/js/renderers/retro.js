/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} value        - huidige waarde (raw)
 * @param {number} min          - minimumwaarde van parameter
 * @param {number} max          - maximumwaarde van parameter
 * @param {string} label        - parameternaam (bijv. "RPM")
 * @param {string} unit         - eenheid (bijv. "rpm", "km/h")
 * @param {string} accentColor  - dashboard accentkleur (hex)
 * @param {number} fontSize     - basisgrootte in pixels
 * @param {{x:number,y:number,size:number,text:string}} bounds
 */
function renderRetro(ctx, value, min, max, label, unit, accentColor, fontSize, bounds) {
  const { x, y, size, text } = bounds;
  const radius = size / 2;
  const cx = x + radius;
  const cy = y + radius;
  const start = Math.PI * 1.25;
  const end = -Math.PI * 0.25;
  const numeric = Number(value);
  const ratio = Number.isFinite(numeric) ? Math.max(0, Math.min(1, (numeric - min) / (max - min))) : 0;
  const needleAngle = start + (end - start) * ratio;

  ctx.save();
  ctx.translate(cx, cy);

  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.98, 0, Math.PI * 2);
  ctx.fillStyle = "#c8c8c8";
  ctx.fill();

  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.90, 0, Math.PI * 2);
  ctx.fillStyle = "#2e2e2e";
  ctx.fill();

  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.82, 0, Math.PI * 2);
  ctx.fillStyle = "#1a1a1a";
  ctx.fill();

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `${Math.max(9, size * 0.038)}px "Share Tech Mono", "VT323", Consolas, monospace`;
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#ffffff";

  for (let i = 0; i <= 20; i += 1) {
    const tickRatio = i / 20;
    const angle = start + (end - start) * tickRatio;
    const major = i % 2 === 0;
    const inner = radius * (major ? 0.64 : 0.70);
    const outer = radius * 0.78;
    ctx.lineWidth = major ? 3 : 1.5;
    ctx.beginPath();
    ctx.moveTo(Math.cos(angle) * inner, Math.sin(angle) * inner);
    ctx.lineTo(Math.cos(angle) * outer, Math.sin(angle) * outer);
    ctx.stroke();
    if (major) {
      const tickValue = Math.round(min + (max - min) * tickRatio);
      ctx.fillText(String(tickValue), Math.cos(angle) * radius * 0.52, Math.sin(angle) * radius * 0.52);
    }
  }

  ctx.rotate(needleAngle);
  ctx.beginPath();
  ctx.moveTo(-radius * 0.08, -radius * 0.018);
  ctx.lineTo(radius * 0.68, 0);
  ctx.lineTo(-radius * 0.08, radius * 0.018);
  ctx.closePath();
  ctx.fillStyle = "#e87722";
  ctx.fill();
  ctx.restore();

  ctx.save();
  ctx.translate(cx, cy);
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.055, 0, Math.PI * 2);
  ctx.fillStyle = "#101010";
  ctx.fill();
  ctx.strokeStyle = "#c8c8c8";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `700 ${Math.max(10, size * 0.052)}px "Share Tech Mono", Consolas, monospace`;
  ctx.fillStyle = "#ffffff";
  ctx.fillText(label, 0, radius * 0.42);

  const lcdWidth = radius * 0.82;
  const lcdHeight = radius * 0.22;
  ctx.fillStyle = "#050705";
  ctx.strokeStyle = "#5c665f";
  ctx.lineWidth = 1.5;
  ctx.fillRect(-lcdWidth / 2, radius * 0.54, lcdWidth, lcdHeight);
  ctx.strokeRect(-lcdWidth / 2, radius * 0.54, lcdWidth, lcdHeight);
  ctx.font = `700 ${Math.max(12, Math.min(fontSize, size * 0.085))}px "Share Tech Mono", Consolas, monospace`;
  ctx.fillStyle = unit === "bar" ? "#e87722" : "#00ff88";
  ctx.fillText(text, 0, radius * 0.65);
  ctx.restore();
}

window.renderRetro = renderRetro;
