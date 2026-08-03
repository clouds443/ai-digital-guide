import { spawn } from "node:child_process";
import { mkdirSync, openSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const root = resolve(import.meta.dirname, "..");
const outDir = resolve(root, "frontend", "assets", "scenics");
const cacheDir = resolve(root, ".cache", "scenic-search");
mkdirSync(outDir, { recursive: true });
mkdirSync(cacheDir, { recursive: true });

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const port = 9348;
const profileDir = resolve(cacheDir, "edge-profile");
const logFd = openSync(resolve(cacheDir, "edge.log"), "w");

const scenicQueries = [
  ["LS-001", "灵山大照壁", "灵山胜境 灵山大照壁 华夏第一壁 实景"],
  ["LS-002", "五明桥", "灵山胜境 五明桥 香水海 石桥 实景"],
  ["LS-003", "佛足坛", "灵山胜境 佛足坛 佛足印 实景"],
  ["LS-004", "五智门", "灵山胜境 五智门 景点 实景"],
  ["LS-005", "菩提大道", "灵山胜境 菩提大道 蓝天绿树 实景"],
  ["LS-006", "九龙灌浴", "无锡灵山胜境 九龙灌浴 喷泉 实景"],
  ["LS-007", "降魔浮雕", "灵山胜境 降魔浮雕 佛陀 魔王波旬 实景"],
  ["LS-008", "阿育王柱", "灵山胜境 阿育王柱 四狮柱 实景"],
  ["LS-009", "天下第一掌", "灵山胜境 天下第一掌 佛手 实景"],
  ["LS-010", "百子戏弥勒", "灵山胜境 百子戏弥勒 弥勒 实景"],
  ["LS-011", "灵山大佛", "无锡灵山大佛 景区 实景"],
  ["LS-012", "灵山梵宫", "无锡灵山梵宫 内景 实景"],
  ["LS-013", "五印坛城", "灵山胜境 五印坛城 藏传佛教 实景"],
  ["LS-014", "曼飞龙塔", "灵山胜境 曼飞龙塔 实景"],
  ["LS-015", "无尽意斋", "灵山胜境 无尽意斋 赵朴初 实景"],
  ["LS-016", "祥符禅寺", "灵山胜境 祥符禅寺 寺院 实景"],
];

async function waitForHttp(url, timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
    } catch {}
    await delay(350);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function connectCdp() {
  const edge = spawn(edgePath, [
    "--headless",
    "--disable-gpu",
    "--no-sandbox",
    "--no-first-run",
    "--remote-allow-origins=*",
    "--remote-debugging-port=" + port,
    "--user-data-dir=" + profileDir,
    "--window-size=1280,900",
    "about:blank",
  ], { stdio: ["ignore", logFd, logFd], windowsHide: true });

  await waitForHttp(`http://127.0.0.1:${port}/json/version`);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl);
  if (!target) throw new Error("No Edge page target was available.");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolveSocket, rejectSocket) => {
    ws.addEventListener("open", resolveSocket, { once: true });
    ws.addEventListener("error", rejectSocket, { once: true });
  });

  let seq = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (!msg.id || !pending.has(msg.id)) return;
    const { resolve: ok, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message || "CDP error"));
    else ok(msg.result || {});
  });
  const cdp = (method, params = {}) => new Promise((resolveCall, rejectCall) => {
    const id = ++seq;
    pending.set(id, { resolve: resolveCall, reject: rejectCall });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { edge, ws, cdp };
}

function imageProbeScript() {
  return `(() => {
    const candidates = Array.from(document.querySelectorAll("img")).map((img) => {
      const rect = img.getBoundingClientRect();
      const area = rect.width * rect.height;
      const src = img.currentSrc || img.src || "";
      const alt = img.alt || "";
      return { src, alt, x: rect.x, y: rect.y, width: rect.width, height: rect.height, area, naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight };
    }).filter((item) => {
      return item.width >= 120 && item.height >= 90 && item.area >= 14000 && item.y >= 0 && item.y < window.innerHeight - 20 && !/^data:image\\/gif/i.test(item.src);
    }).sort((a, b) => {
      const ay = Math.max(0, a.y);
      const by = Math.max(0, b.y);
      if (Math.abs(ay - by) > 20) return ay - by;
      return b.area - a.area;
    });
    return candidates.slice(0, 8);
  })()`;
}

async function captureScenic(cdp, scenic) {
  const [id, name, query] = scenic;
  const url = `https://www.bing.com/images/search?q=${encodeURIComponent(query)}&qft=+filterui:imagesize-large&form=IRFLTR`;
  await cdp("Page.navigate", { url });
  await cdp("Page.loadEventFired").catch(() => {});
  await delay(2600);
  const result = await cdp("Runtime.evaluate", {
    expression: imageProbeScript(),
    awaitPromise: true,
    returnByValue: true,
  });
  const candidates = result.result?.value || [];
  const picked = candidates[0];
  if (!picked) throw new Error(`No visible image candidate for ${id}`);
  const clip = {
    x: Math.max(0, picked.x),
    y: Math.max(0, picked.y),
    width: Math.max(120, picked.width),
    height: Math.max(90, picked.height),
    scale: 1,
  };
  const shot = await cdp("Page.captureScreenshot", { format: "jpeg", quality: 88, clip });
  writeFileSync(resolve(outDir, `${id}.jpg`), Buffer.from(shot.data, "base64"));
  return {
    id,
    name,
    query,
    source_type: "browser_image_search_screenshot",
    source_url: url,
    image_src: picked.src,
    image_alt: picked.alt,
    needs_review: false,
    captured_at: new Date().toISOString(),
  };
}

async function main() {
  let edge;
  let ws;
  try {
    const browser = await connectCdp();
    edge = browser.edge;
    ws = browser.ws;
    const cdp = browser.cdp;
    await cdp("Page.enable");
    await cdp("Runtime.enable");
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });

    const items = [];
    for (const scenic of scenicQueries) {
      try {
        items.push(await captureScenic(cdp, scenic));
        console.log(`captured ${scenic[0]} ${scenic[1]}`);
      } catch (error) {
        const [id, name, query] = scenic;
        items.push({
          id,
          name,
          query,
          source_type: "browser_image_search_failed",
          source_url: `https://www.bing.com/images/search?q=${encodeURIComponent(query)}`,
          image_src: "",
          image_alt: "",
          needs_review: true,
          error: error.message,
          captured_at: new Date().toISOString(),
        });
        console.warn(`failed ${id} ${name}: ${error.message}`);
      }
    }
    writeFileSync(resolve(outDir, "sources.json"), JSON.stringify({
      generated_at: new Date().toISOString(),
      method: "Edge headless browser screenshots from Bing Images search results",
      items,
    }, null, 2), "utf-8");
  } finally {
    if (ws) ws.close();
    if (edge && !edge.killed) edge.kill();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
