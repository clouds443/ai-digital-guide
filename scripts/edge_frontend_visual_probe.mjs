import { spawn } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = resolve(root, ".cache", "visual");
mkdirSync(outDir, { recursive: true });

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const pythonPath = process.env.FLASK_PYTHON || "D:\\Anaconda\\python.exe";
const backendLog = openSync(resolve(outDir, "backend-visual-probe.log"), "w");
const backend = spawn(pythonPath, [resolve(root, "backend", "main.py")], {
  cwd: resolve(root, "backend"),
  env: {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    LOCAL_RAG_ONLY: "1",
  },
  stdio: ["ignore", backendLog, backendLog],
  windowsHide: true,
});

async function waitForHttp(url, timeoutMs = 90000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {}
    await delay(400);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

let edge;
try {
  await waitForHttp("http://127.0.0.1:8000/");
  const profileDir = resolve(outDir, "edge-profile");
  rmSync(profileDir, { recursive: true, force: true });
  const port = 9339;
  const edgeLog = openSync(resolve(outDir, "edge-visual-probe.log"), "w");
  edge = spawn(edgePath, [
    "--headless",
    "--disable-gpu",
    "--no-sandbox",
    "--no-first-run",
    "--remote-allow-origins=*",
    "--hide-scrollbars",
    "--remote-debugging-port=" + port,
    "--user-data-dir=" + profileDir,
    "--window-size=1440,960",
    "about:blank",
  ], { stdio: ["ignore", edgeLog, edgeLog], windowsHide: true });
  await waitForHttp(`http://127.0.0.1:${port}/json/version`);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find((item) => item.type === "page" && item.webSocketDebuggerUrl);
  if (!target) throw new Error("No Edge page target was available for CDP visual probe.");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolveSocket, rejectSocket) => {
    ws.addEventListener("open", resolveSocket, { once: true });
    ws.addEventListener("error", rejectSocket, { once: true });
  });
  let seq = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message || "CDP error"));
      else ok(msg.result || {});
    }
  });
  const cdp = (method, params = {}) => new Promise((resolveCall, rejectCall) => {
    const id = ++seq;
    pending.set(id, { resolve: resolveCall, reject: rejectCall });
    ws.send(JSON.stringify({ id, method, params }));
  });
  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await cdp("Page.navigate", { url: "http://127.0.0.1:8000/" });
  await delay(1600);
  const setupScript = `
    (() => {
      showApp();
      state.auth.user = { username: "visual", display_name: "视觉验收", role: "admin" };
      state.auth.token = "visual";
      state.mode = "tourist";
      state.config = { name: "灵小境", model: "Haru", opening: "您好，我是灵山胜境 AI 数字人导游灵小境。想了解景点、路线、演出、门票或交通，都可以直接问我。" };
      state.scenics = [
        { id: "LS-001", name: "灵山大照壁", summary: "华夏第一壁，进入灵山的第一视觉焦点。" },
        { id: "LS-002", name: "五明桥", summary: "连接入口与核心礼佛区的智慧之桥。" },
        { id: "LS-003", name: "佛足坛", summary: "以佛足印理解佛光普照的寓意。" },
        { id: "LS-004", name: "五智门", summary: "象征五方五佛与六度波罗蜜。" },
        { id: "LS-005", name: "菩提大道", summary: "中轴礼佛步道，串联核心景观。" },
        { id: "LS-006", name: "九龙灌浴", summary: "释迦牟尼诞生故事的动态景观。" },
        { id: "LS-007", name: "降魔浮雕", summary: "表现佛陀战胜魔王波旬的成道故事。" },
        { id: "LS-008", name: "阿育王柱", summary: "象征佛法传播与和平包容。" },
        { id: "LS-009", name: "天下第一掌", summary: "灵山大佛右手复制，可摸佛手祈福。" },
        { id: "LS-010", name: "百子戏弥勒", summary: "亲子互动与欢喜包容的代表景点。" },
        { id: "LS-011", name: "灵山大佛", summary: "88 米佛像，是灵山胜境核心地标。" },
        { id: "LS-012", name: "灵山梵宫", summary: "佛教艺术殿堂，也是吉祥颂演出场地。" },
        { id: "LS-013", name: "祥符禅寺", summary: "承载小灵山历史脉络的寺院空间。" },
        { id: "LS-014", name: "五印坛城", summary: "藏传佛教艺术、色彩与坛城象征集中呈现。" },
        { id: "LS-015", name: "曼飞龙塔", summary: "体现南传佛教与傣族建筑风格。" },
        { id: "LS-016", name: "无尽意斋", summary: "纪念赵朴初，适合禅茶与静心休憩。" }
      ];
      state.routes = [
        { id: "route_history", name: "历史文化深度游", duration: "6小时", summary: "大照壁、祥符禅寺、大佛、梵宫、五印坛城", map: { id: "route_history", name: "历史文化深度游", points: [{ name: "灵山大照壁" }, { name: "五明桥" }] } },
        { id: "route_family", name: "亲子家庭互动游", duration: "4小时", summary: "九龙灌浴、天下第一掌、百子戏弥勒", map: { id: "route_family", name: "亲子家庭互动游", points: [{ name: "九龙灌浴" }, { name: "天下第一掌" }] } }
      ];
      state.analytics = {
        served_today: 126,
        served_week: 842,
        satisfaction: 96,
        hot_questions: [{ name: "演出时间", count: 42 }, { name: "路线推荐", count: 31 }],
        route_preference: [{ id: "route_history", count: 56 }, { id: "route_family", count: 38 }],
        consumption: [{ name: "门票", count: 21 }, { name: "素斋", count: 13 }],
        suggestions: ["增加吉祥颂场次提醒"],
        recent_chats: [{ query: "吉祥颂几点演出？", answer: "每天常见场次为 10:35、11:30、14:00、16:00。" }]
      };
      state.evaluations = {
        deepseek: { ready: true, score_percent: 93, fact_accuracy: .94, failed_count: 3, model: "deepseek-chat", avg_latency_ms: 2800, low_score_items: [] },
        local: { ready: true, score_percent: 96, fact_accuracy: .97, failed_count: 1, model: "local-rag", avg_latency_ms: 22, low_score_items: [] }
      };
      state.feedback = [{ rating: 2, sentiment: "需跟进", message: "希望路线提示更清楚。" }];
      initMessages();
      render();
      return document.body.innerText.slice(0, 120);
    })();
  `;
  await cdp("Runtime.evaluate", { expression: setupScript, awaitPromise: true });
  await delay(1200);
  const stageMapMetrics = await cdp("Runtime.evaluate", {
    expression: `
      new Promise((resolve) => {
        const panel = document.querySelector("#lingshanMapPanel");
        const stageContext = document.querySelector(".stage-context");
        const leftRail = document.querySelector(".stage-left-rail");
        const subject = document.querySelector(".stage-subject");
        const drawer = document.querySelector("#conversationDrawer");
        const dock = document.querySelector(".conversation-dock");
        const oldCanvas = document.querySelector("#tourMapCanvas");
        if (!panel || !stageContext || !leftRail || !subject || !drawer) {
          resolve({ ok: false, reason: "missing centered tourist stage elements" });
          return;
        }
        const beforeRect = panel.getBoundingClientRect();
        const beforeHeight = Math.round(beforeRect.height);
        const beforeWidth = Math.round(beforeRect.width);
        const subjectRect = subject.getBoundingClientRect();
        const subjectCenter = subjectRect.left + subjectRect.width / 2;
        const viewportCenter = window.innerWidth / 2;
        const subjectCenterDelta = Math.round(Math.abs(subjectCenter - viewportCenter));
        const dockRect = dock ? dock.getBoundingClientRect() : null;
        const defaultDockOverlap = Boolean(dockRect && beforeRect.left < dockRect.right && beforeRect.right > dockRect.left && beforeRect.top < dockRect.bottom && beforeRect.bottom > dockRect.top);
        if (!state.conversationDrawerOpen) toggleConversationDrawer();
        toggleTourMapCanvas();
        setTimeout(() => {
          const expandedHeight = Math.round(panel.getBoundingClientRect().height);
          const drawerRect = drawer.getBoundingClientRect();
          const currentSubjectRect = subject.getBoundingClientRect();
          const drawerSubjectOverlap = Boolean(drawerRect.left < currentSubjectRect.right && drawerRect.right > currentSubjectRect.left && drawerRect.top < currentSubjectRect.bottom && drawerRect.bottom > currentSubjectRect.top);
          resolve({
            ok: stageContext.contains(panel) && leftRail.contains(drawer) && subject.contains(document.querySelector("#live2dFrame")) && !oldCanvas && !defaultDockOverlap && !drawerSubjectOverlap && beforeHeight >= 250 && expandedHeight > beforeHeight && subjectCenterDelta <= 80,
            inRightRail: stageContext.contains(panel),
            historyInLeftRail: leftRail.contains(drawer),
            live2dInSubject: subject.contains(document.querySelector("#live2dFrame")),
            oldCanvasPresent: Boolean(oldCanvas),
            defaultDockOverlap,
            drawerSubjectOverlap,
            subjectCenterDelta,
            defaultWidth: beforeWidth,
            defaultHeight: beforeHeight,
            expandedHeight,
            className: panel.className
          });
        }, 280);
      });
    `,
    returnByValue: true,
    awaitPromise: true
  });
  await delay(350);
  const stageMapShot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(outDir, "frontend-tourist-stage-map-1366.png"), Buffer.from(stageMapShot.data, "base64"));
  writeFileSync(resolve(outDir, "frontend-tourist-stage-map-metrics.json"), JSON.stringify(stageMapMetrics.result.value, null, 2), "utf-8");
  await cdp("Runtime.evaluate", { expression: `(() => { if (state.mapCanvasExpanded) toggleTourMapCanvas(); if (state.conversationDrawerOpen) toggleConversationDrawer(); window.scrollTo(0, 0); })();` });
  await delay(300);
  async function capture(name, width, height, mobile = false) {
    await cdp("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
    await delay(450);
    const shot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const buffer = Buffer.from(shot.data, "base64");
    writeFileSync(resolve(outDir, name), buffer);
    return buffer;
  }
  await capture("frontend-tourist-1366.png", 1366, 768);
  const weatherInfoMetrics = await cdp("Runtime.evaluate", {
    expression: `
      (() => {
        state.mapWeather = "天气：无锡市，阴，31°C，东南风";
        updateMapPanelText();
        const route = document.querySelector(".map-info-route");
        const weather = document.querySelector(".map-info-weather");
        if (!route || !weather) return { ok: false, reason: "missing map info rows" };
        const routeRect = route.getBoundingClientRect();
        const weatherRect = weather.getBoundingClientRect();
        return {
          ok: weatherRect.top >= routeRect.bottom,
          routeText: route.innerText.replace(/\\s+/g, " ").trim(),
          weatherText: weather.innerText.replace(/\\s+/g, " ").trim(),
          routeBottom: routeRect.bottom,
          weatherTop: weatherRect.top
        };
      })();
    `,
    returnByValue: true
  });
  await cdp("Runtime.evaluate", { expression: `(() => { const info = document.querySelector("#mapInfoText"); if (info) info.scrollIntoView({ block: "center" }); })();` });
  await delay(300);
  const weatherInfoShot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(outDir, "frontend-tourist-weather-info-1366.png"), Buffer.from(weatherInfoShot.data, "base64"));
  writeFileSync(resolve(outDir, "frontend-tourist-weather-info-metrics.json"), JSON.stringify(weatherInfoMetrics.result.value, null, 2), "utf-8");
  const weatherAnimationMetrics = await cdp("Runtime.evaluate", {
    expression: `
      (() => {
        state.mapWeather = "天气：无锡市，雷阵雨，28°C，东南风";
        updateMapPanelText();
        showWeatherAnimation(state.mapWeather);
        const overlay = document.querySelector("#weatherAnimationOverlay");
        if (!overlay) return { ok: false, reason: "missing weather animation overlay" };
        const rect = overlay.getBoundingClientRect();
        return {
          ok: overlay.classList.contains("visible") && overlay.classList.contains("weather-rain"),
          className: overlay.className,
          particleCount: overlay.querySelectorAll(".weather-drop").length,
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        };
      })();
    `,
    returnByValue: true
  });
  await delay(300);
  const weatherAnimationShot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(outDir, "frontend-tourist-weather-animation-1366.png"), Buffer.from(weatherAnimationShot.data, "base64"));
  writeFileSync(resolve(outDir, "frontend-tourist-weather-animation-metrics.json"), JSON.stringify(weatherAnimationMetrics.result.value, null, 2), "utf-8");
  await cdp("Runtime.evaluate", { expression: `(() => { hideWeatherAnimation(); })();` });
  await cdp("Runtime.evaluate", { expression: `(() => { state.mapWeather = ""; updateMapPanelText(); window.scrollTo(0, 0); })();` });
  const scenicScrollMetrics = await cdp("Runtime.evaluate", {
    expression: `
      (() => {
        const list = document.querySelector(".core-scenic-list");
        if (!list) return { ok: false, reason: "missing core scenic list" };
        const before = list.scrollTop;
        list.scrollTop = list.scrollHeight;
        const cards = Array.from(list.querySelectorAll(".core-scenic-card"));
        const visibleCards = cards.filter((card) => {
          const rect = card.getBoundingClientRect();
          const listRect = list.getBoundingClientRect();
          return rect.bottom > listRect.top && rect.top < listRect.bottom;
        }).map((card) => card.innerText.replace(/\\s+/g, " ").trim());
        return {
          ok: list.scrollTop > before,
          before,
          after: list.scrollTop,
          scrollHeight: list.scrollHeight,
          clientHeight: list.clientHeight,
          visibleCards,
          lastVisible: visibleCards[visibleCards.length - 1] || ""
        };
      })();
    `,
    returnByValue: true
  });
  await delay(300);
  const scrolledShot = await cdp("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(outDir, "frontend-tourist-core-scenic-scrolled-1366.png"), Buffer.from(scrolledShot.data, "base64"));
  writeFileSync(resolve(outDir, "frontend-tourist-core-scenic-scroll-metrics.json"), JSON.stringify(scenicScrollMetrics.result.value, null, 2), "utf-8");
  await cdp("Runtime.evaluate", { expression: `(() => { const list = document.querySelector(".core-scenic-list"); if (list) list.scrollTop = 0; })();` });
  await capture("frontend-tourist-1920.png", 1920, 1080);
  await capture("frontend-tourist-768.png", 768, 1024);
  await capture("frontend-tourist-390.png", 390, 844, true);
  await cdp("Runtime.evaluate", {
    expression: `
      (() => {
        showApp();
        state.auth.user = { username: "visual", display_name: "视觉验收", role: "admin" };
        state.auth.token = "visual";
        state.mode = "admin";
        state.adminPage = "dashboard";
        render();
      })();
    `,
    awaitPromise: true,
  });
  await delay(800);
  await capture("frontend-admin-1366.png", 1366, 768);
  await cdp("Runtime.evaluate", { expression: "showLogin();", awaitPromise: true });
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
  await delay(1200);
  const loginMetricsResult = await cdp("Runtime.evaluate", {
    expression: `(() => {
      const canvas = document.getElementById("loginParticleCanvas");
      const panel = document.querySelector(".login-panel");
      const canvasRect = canvas.getBoundingClientRect();
      const panelRect = panel.getBoundingClientRect();
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      return {
        canvas: { left: canvasRect.left, top: canvasRect.top, width: canvasRect.width, height: canvasRect.height },
        panel: { left: panelRect.left, top: panelRect.top, width: panelRect.width, height: panelRect.height },
        backingWidth: canvas.width,
        backingHeight: canvas.height,
        webgl: Boolean(gl),
        fallbackVisible: document.getElementById("loginView").classList.contains("login-particle-fallback-visible"),
        horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth
      };
    })()`,
    returnByValue: true,
  });
  const loginMetrics = loginMetricsResult.result.value;
  writeFileSync(resolve(outDir, "frontend-login-particle-metrics.json"), JSON.stringify(loginMetrics, null, 2));
  await capture("frontend-login-1366.png", 1366, 768);
  await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x: 110, y: 430, button: "left", clickCount: 1 });
  await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: 300, y: 345, button: "left", buttons: 1 });
  await delay(260);
  await capture("frontend-login-dragged-1366.png", 1366, 768);
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: 300, y: 345, button: "left", clickCount: 1 });
  await delay(1500);
  await capture("frontend-login-returned-1366.png", 1366, 768);
  await capture("frontend-login-1920.png", 1920, 1080);
  await capture("frontend-login-768.png", 768, 1024);
  await capture("frontend-login-390.png", 390, 844, true);
  await cdp("Runtime.evaluate", {
    expression: `(() => {
      if (loginParticleLandscape) loginParticleLandscape.destroy();
      loginParticleLandscape = null;
      window.THREE = null;
      document.getElementById("loginView").classList.remove("login-particle-fallback-visible");
      ensureLoginParticleLandscape();
      return {
        fallbackVisible: document.getElementById("loginView").classList.contains("login-particle-fallback-visible"),
        loginPanelVisible: Boolean(document.querySelector(".login-panel"))
      };
    })()`,
    returnByValue: true,
  }).then((result) => {
    writeFileSync(resolve(outDir, "frontend-login-fallback-metrics.json"), JSON.stringify(result.result.value, null, 2));
  });
  await capture("frontend-login-fallback-1366.png", 1366, 768);
  ws.close();
  console.log(resolve(outDir, "frontend-tourist-1366.png"));
  console.log(resolve(outDir, "frontend-tourist-1920.png"));
  console.log(resolve(outDir, "frontend-tourist-768.png"));
  console.log(resolve(outDir, "frontend-tourist-390.png"));
  console.log(resolve(outDir, "frontend-admin-1366.png"));
  console.log(resolve(outDir, "frontend-login-1366.png"));
  console.log(resolve(outDir, "frontend-login-dragged-1366.png"));
  console.log(resolve(outDir, "frontend-login-returned-1366.png"));
  console.log(resolve(outDir, "frontend-login-particle-metrics.json"));
  console.log(resolve(outDir, "frontend-login-fallback-1366.png"));
  console.log(resolve(outDir, "frontend-login-fallback-metrics.json"));
} finally {
  if (edge && !edge.killed) edge.kill();
  if (backend && !backend.killed) backend.kill();
}
