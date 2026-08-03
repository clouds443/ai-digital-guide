(function (global) {
  "use strict";

  // 固定峡谷构图：山体围合中间河谷，避免元素各自漂浮而失去主体。
  const IRREGULAR_RIDGE_PROFILE = {
    left: [0, 0.1, 0.28, 0.48, 0.7, 0.88, 1, 0.86, 0.76, 0.82, 0.58, 0.32, 0.12, 0],
    right: [0, 0.14, 0.34, 0.55, 0.76, 0.96, 0.9, 1, 0.8, 0.66, 0.73, 0.45, 0.18, 0],
    low: [0, 0.16, 0.31, 0.5, 0.72, 0.6, 0.78, 0.48, 0.3, 0.12, 0]
  };

  const MOUNTAIN_LAYOUT = [
    { id: "left-hero", x: -5.95, base: -4.42, height: 5.66, width: 2.76, z: 0.34, fill: 0x082e3c, edge: 0x49dceb, profile: "left" },
    { id: "right-hero", x: 5.85, base: -4.42, height: 6.04, width: 2.86, z: 0.3, fill: 0x082e3c, edge: 0x4be0f2, profile: "right" },
    { id: "left-foreground", x: -8.15, base: -4.44, height: 3.42, width: 2.86, z: 1.08, fill: 0x0a3543, edge: 0x2ec6d1, profile: "low" },
    { id: "right-foreground", x: 8.22, base: -4.44, height: 3.92, width: 2.62, z: 1.05, fill: 0x083743, edge: 0x2ac4d0, profile: "right" }
  ];

  const CONTINUOUS_RIDGE_ANCHORS = [
    { id: "left-connector-ridge", x: -3.65, base: -4.38, height: 2.82, width: 1.98, z: 0.06, fill: 0x0b3c49, edge: 0x249aaa, profile: "low" },
    { id: "center-left-ridge", x: -1.72, base: -4.36, height: 1.88, width: 1.62, z: -0.04, fill: 0x0c414b, edge: 0x238b9a, profile: "low" },
    { id: "center-valley-ridge", x: 0.02, base: -4.38, height: 1.36, width: 1.44, z: -0.08, fill: 0x0d4650, edge: 0x1e8190, profile: "low" },
    { id: "center-right-ridge", x: 1.82, base: -4.36, height: 1.94, width: 1.7, z: -0.02, fill: 0x0b3d49, edge: 0x2492a1, profile: "low" },
    { id: "right-connector-ridge", x: 3.64, base: -4.38, height: 2.76, width: 1.98, z: 0.06, fill: 0x0a3a47, edge: 0x25a5b5, profile: "low" }
  ];

  const ALL_MOUNTAIN_LAYOUT = MOUNTAIN_LAYOUT.concat(CONTINUOUS_RIDGE_ANCHORS);

  // 河流保持在登录框下方的峡谷中，以扁平水面而非悬空管道呈现。
  const VALLEY_RIVER_LAYOUT = {
    center: [[-3.2, -2.18, -0.42], [-2.64, -2.52, -0.2], [-1.78, -2.9, 0.04], [-0.82, -3.25, 0.32], [0.1, -3.52, 0.62], [1.15, -3.72, 0.88], [2.24, -3.92, 1.04], [3.15, -4.1, 1.16]],
    widths: [0.1, 0.15, 0.2, 0.28, 0.42, 0.58, 0.82, 1.08]
  };

  const WATERFALL_LAYOUT = [
    { x: 5.42, top: 1.72, bottom: -1.18, width: 0.5, bend: -0.22, z: 0.64 },
    { x: 7.88, top: 0.72, bottom: -2.28, width: 0.32, bend: 0.18, z: 0.86 }
  ];

  const MIST_LAYOUT = [
    { x: -5.7, y: 0.86, span: 2.7, depth: 0.28, phase: 0.2 },
    { x: 0.1, y: -0.35, span: 3.8, depth: 0.22, phase: 1.25 },
    { x: 5.25, y: 1.28, span: 2.9, depth: 0.32, phase: 2.6 }
  ];
  const USE_PHOTO_BACKDROP = false;

  function createLoginParticleLandscape(canvas, options) {
    options = options || {};
    const root = options.root || (canvas && canvas.parentElement);
    const fallbackClass = "login-particle-fallback-visible";
    const THREE = global.THREE;

    if (!canvas || !THREE) {
      if (root) root.classList.add(fallbackClass);
      return createUnavailableController();
    }

    const MAX_YAW = THREE.MathUtils.degToRad(8);
    const MAX_PITCH = THREE.MathUtils.degToRad(4);
    const focusArea = { x: 0, y: -0.15, width: 3.4, height: 4.9 };
    const reducedMotionQuery = global.matchMedia("(prefers-reduced-motion: reduce)");
    const pointer = { dragging: false, id: null, startX: 0, startY: 0, hoverX: 0, hoverY: 0 };
    let running = false;
    let destroyed = false;
    let animationFrame = 0;
    let lastTime = 0;
    let currentYaw = 0;
    let currentPitch = 0;
    let targetYaw = 0;
    let targetPitch = 0;
    let resizeObserver = null;
    let renderer;
    let scene;
    let camera;
    let landscape;
    let backLayer;
    let mountainLayer;
    let waterLayer;
    let atmosphereLayer;

    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: false, powerPreference: "high-performance" });
      renderer.setClearColor(0x174f5d, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.shadowMap.enabled = false;
      if ("outputColorSpace" in renderer && THREE.SRGBColorSpace) renderer.outputColorSpace = THREE.SRGBColorSpace;

      scene = new THREE.Scene();
      camera = new THREE.OrthographicCamera(-10, 10, 5.7, -5.7, 0.1, 100);
      camera.position.set(0, 0, 18);
      camera.lookAt(0, 0, 0);

      landscape = new THREE.Group();
      backLayer = new THREE.Group();
      mountainLayer = new THREE.Group();
      waterLayer = new THREE.Group();
      atmosphereLayer = new THREE.Group();
      landscape.add(backLayer, mountainLayer, waterLayer, atmosphereLayer);
      scene.add(landscape);

      const particleCount = selectParticleCount(global.innerWidth || 1366);
      backLayer.add(createBackdrop(THREE));
      mountainLayer.add(createMountainSilhouettes(THREE));
      mountainLayer.add(createMountainFacets(THREE));
      mountainLayer.add(createStructuredMountainLayer(THREE, particleCount, focusArea));
      mountainLayer.add(createMountainStreams(THREE, particleCount));
      mountainLayer.add(createPeakRidges(THREE));
      waterLayer.add(createRiverChannels(THREE, particleCount));
      waterLayer.add(createWaterfallFalls(THREE, particleCount));
      waterLayer.add(createWaterRipples(THREE));
      atmosphereLayer.add(createMistBands(THREE));
      atmosphereLayer.add(createSparseAtmosphere(THREE));

      resize();
      bindEvents();
      if (root) root.classList.remove(fallbackClass);
      renderFrame(0);
    } catch (error) {
      if (root) root.classList.add(fallbackClass);
      disposeScene();
      return createUnavailableController();
    }

    function selectParticleCount(width) {
      if (width <= 640) return 4500;
      if (width <= 1024) return 9000;
      return 16000;
    }

    function bindEvents() {
      canvas.addEventListener("pointerdown", onPointerDown);
      canvas.addEventListener("pointermove", onPointerMove);
      canvas.addEventListener("pointerup", onPointerUp);
      canvas.addEventListener("pointercancel", onPointerUp);
      document.addEventListener("visibilitychange", onVisibilityChange);
      reducedMotionQuery.addEventListener("change", onMotionPreferenceChange);
      resizeObserver = new ResizeObserver(resize);
      resizeObserver.observe(canvas.parentElement || canvas);
    }

    function onPointerDown(event) {
      if (destroyed || event.button !== 0) return;
      pointer.dragging = true;
      pointer.id = event.pointerId;
      pointer.startX = event.clientX;
      pointer.startY = event.clientY;
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add("is-dragging");
    }

    function onPointerMove(event) {
      const rect = canvas.getBoundingClientRect();
      pointer.hoverX = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 2 - 1;
      pointer.hoverY = -(((event.clientY - rect.top) / Math.max(rect.height, 1)) * 2 - 1);
      if (!pointer.dragging || event.pointerId !== pointer.id) return;
      const dx = (event.clientX - pointer.startX) / Math.max(rect.width, 1);
      const dy = (event.clientY - pointer.startY) / Math.max(rect.height, 1);
      targetYaw = THREE.MathUtils.clamp(dx * MAX_YAW * 3.2, -MAX_YAW, MAX_YAW);
      targetPitch = THREE.MathUtils.clamp(dy * MAX_PITCH * 3.2, -MAX_PITCH, MAX_PITCH);
      if (reducedMotionQuery.matches) {
        currentYaw = targetYaw;
        currentPitch = targetPitch;
        renderFrame(performance.now());
      }
    }

    function onPointerUp(event) {
      if (!pointer.dragging || event.pointerId !== pointer.id) return;
      pointer.dragging = false;
      pointer.id = null;
      targetYaw = 0;
      targetPitch = 0;
      canvas.classList.remove("is-dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    }

    function onVisibilityChange() {
      if (document.hidden) pause();
      else if (!root || !root.classList.contains("hidden")) start();
    }

    function onMotionPreferenceChange() {
      if (reducedMotionQuery.matches) {
        pause();
        renderFrame(performance.now());
      } else if (!document.hidden) {
        start();
      }
    }

    function animate(time) {
      if (!running || destroyed) return;
      renderFrame(time);
      animationFrame = global.requestAnimationFrame(animate);
    }

    function renderFrame(time) {
      if (!renderer || !scene || !camera) return;
      const delta = Math.min(32, Math.max(0, time - lastTime));
      lastTime = time;
      const damping = pointer.dragging ? 0.18 : Math.min(0.12, 0.035 + delta / 900);
      currentYaw += (targetYaw - currentYaw) * damping;
      currentPitch += (targetPitch - currentPitch) * damping;

      // 拖拽只制造层级视差，不扭曲山、水、瀑布的固定构图。
      backLayer.position.x = currentYaw * 2.2;
      mountainLayer.position.x = currentYaw * 5.2;
      waterLayer.position.x = currentYaw * 7.2;
      atmosphereLayer.position.x = currentYaw * 3.6;
      landscape.position.y = currentPitch * 1.4;

      if (!reducedMotionQuery.matches) {
        const seconds = time * 0.001;
        atmosphereLayer.position.y = Math.sin(seconds * 0.22) * 0.035;
        waterLayer.position.y = Math.sin(seconds * 0.4) * 0.018;
      }
      renderer.render(scene, camera);
    }

    function start() {
      if (destroyed || running) return;
      running = true;
      if (reducedMotionQuery.matches) {
        running = false;
        renderFrame(performance.now());
        return;
      }
      animationFrame = global.requestAnimationFrame(animate);
    }

    function pause() {
      running = false;
      if (animationFrame) global.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
    }

    function resize() {
      if (!renderer || !camera || !canvas) return;
      const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : canvas.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width));
      const height = Math.max(1, Math.round(rect.height));
      const halfWidth = 10;
      const halfHeight = Math.max(5.7, halfWidth / (width / height));
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      renderer.setSize(width, height, false);
      camera.left = -halfWidth;
      camera.right = halfWidth;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      pause();
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      reducedMotionQuery.removeEventListener("change", onMotionPreferenceChange);
      if (resizeObserver) resizeObserver.disconnect();
      disposeScene();
    }

    function disposeScene() {
      if (landscape) disposeObject(landscape);
      if (renderer) renderer.dispose();
    }

    return { available: true, start: start, pause: pause, resize: resize, destroy: destroy };
  }

  function createBackdrop(THREE) {
    const geometry = new THREE.PlaneGeometry(24, 18);
    const material = new THREE.MeshBasicMaterial({ color: 0x174f5d, depthWrite: false });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.z = -4;
    return mesh;
  }

  function createMountainSilhouettes(THREE) {
    const group = new THREE.Group();
    ALL_MOUNTAIN_LAYOUT.forEach(function (mountain) {
      const shape = mountainShape(THREE, mountain);
      const geometry = new THREE.ShapeGeometry(shape);
      const material = new THREE.MeshBasicMaterial({
        color: mountain.fill,
        transparent: true,
        opacity: mountain.id.indexOf("hero") > -1 ? 0.86 : 0.72,
        depthWrite: false,
        side: THREE.DoubleSide
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.z = mountain.z - 0.8;
      group.add(mesh);
    });
    return group;
  }

  function createMountainFacets(THREE) {
    const group = new THREE.Group();
    MOUNTAIN_LAYOUT.filter(function (mountain) { return mountain.id.indexOf("hero") > -1; }).forEach(function (mountain) {
      const contour = mountainContour(mountain);
      const peakIndex = contour.reduce(function (best, point, index) { return point.y > contour[best].y ? index : best; }, 0);
      const peak = contour[peakIndex];
      const leftFoot = { x: mountain.x - mountain.width * 0.18, y: mountain.base + mountain.height * 0.04 };
      const rightFoot = { x: mountain.x + mountain.width * 0.46, y: mountain.base + mountain.height * 0.03 };
      group.add(createMountainFacet(THREE, [contour[0], contour[Math.max(1, peakIndex - 3)], peak, leftFoot], 0x126070, 0.22, mountain.z - 0.3));
      group.add(createMountainFacet(THREE, [peak, contour[Math.min(contour.length - 2, peakIndex + 3)], contour[contour.length - 1], rightFoot], 0x021e2a, 0.32, mountain.z - 0.26));
    });
    return group;
  }

  function createMountainFacet(THREE, points, color, opacity, z) {
    const shape = new THREE.Shape();
    shape.moveTo(points[0].x, points[0].y);
    points.slice(1).forEach(function (point) { shape.lineTo(point.x, point.y); });
    shape.closePath();
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: opacity,
      depthWrite: false,
      side: THREE.DoubleSide
    }));
    mesh.position.z = z;
    return mesh;
  }

  function createStructuredMountainLayer(THREE, particleCount, focusArea) {
    const group = new THREE.Group();
    const totalWeight = ALL_MOUNTAIN_LAYOUT.reduce(function (sum, mountain) { return sum + mountain.height * mountain.width; }, 0);
    ALL_MOUNTAIN_LAYOUT.forEach(function (mountain, mountainIndex) {
      const count = Math.max(260, Math.round(particleCount * 0.66 * (mountain.height * mountain.width / totalWeight)));
      group.add(createMountainPoints(THREE, mountain, count, mountainIndex, focusArea));
    });
    return group;
  }

  function createMountainStreams(THREE, particleCount) {
    const group = new THREE.Group();
    MOUNTAIN_LAYOUT.filter(function (mountain) { return mountain.id.indexOf("hero") > -1; }).forEach(function (mountain, index) {
      for (let stream = 0; stream < 6; stream += 1) {
        group.add(createSlopeStream(THREE, mountain, stream, Math.max(110, Math.round(particleCount * 0.007)), 83011 + index * 101 + stream));
      }
    });
    return group;
  }

  function createSlopeStream(THREE, mountain, streamIndex, count, seed) {
    const random = seededRandom(seed);
    const profile = IRREGULAR_RIDGE_PROFILE[mountain.profile] || IRREGULAR_RIDGE_PROFILE.low;
    const peakIndex = profile.reduce(function (best, height, index) { return height > profile[best] ? index : best; }, 0);
    const peakT = peakIndex / Math.max(1, profile.length - 1);
    const direction = streamIndex % 2 ? 1 : -1;
    const widthFactor = 0.18 + Math.floor(streamIndex / 2) * 0.16;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const cyan = new THREE.Color(streamIndex === 0 ? 0xbafcff : 0x48cfda);
    const deep = new THREE.Color(0x0c5968);
    const color = new THREE.Color();
    for (let index = 0; index < count; index += 1) {
      const t = Math.pow(random(), 0.82);
      const x = mountain.x + (peakT - 0.5) * mountain.width * 2 + direction * mountain.width * widthFactor * t + Math.sin(t * 8 + streamIndex) * 0.12;
      const y = mountain.base + mountain.height * (0.96 - t * 0.9) - Math.abs(Math.sin(t * 3.1 + streamIndex)) * t * mountain.height * 0.13;
      const offset = index * 3;
      color.copy(deep).lerp(cyan, 0.3 + (1 - t) * 0.36);
      positions[offset] = x + (random() - 0.5) * 0.055;
      positions[offset + 1] = y + (random() - 0.5) * 0.05;
      positions[offset + 2] = mountain.z + 0.52 + (random() - 0.5) * 0.08;
      colors[offset] = color.r;
      colors[offset + 1] = color.g;
      colors[offset + 2] = color.b;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      size: 0.044,
      vertexColors: true,
      transparent: true,
      opacity: 0.58,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createMountainPoints(THREE, mountain, count, seedOffset, focusArea) {
    const random = seededRandom(71821 + seedOffset * 971);
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const dark = new THREE.Color(mountain.fill);
    const bright = new THREE.Color(mountain.edge);
    const gold = new THREE.Color(0xe7c167);
    const color = new THREE.Color();
    for (let index = 0; index < count; index += 1) {
      const horizontal = random();
      const ridge = ridgeHeightAt(mountain, horizontal);
      const vertical = Math.pow(random(), 0.68);
      const lateral = (horizontal - 0.5) * mountain.width * 2;
      const edgeRatio = Math.abs(horizontal - 0.5) * 2;
      let x = mountain.x + lateral;
      let y = mountain.base + ridge * vertical;
      if (isInsideFocusArea(x, y, focusArea)) {
        x += mountain.x < 0 ? -1.1 : 1.1;
        y -= 0.28;
      }
      color.copy(dark).lerp(bright, 0.08 + edgeRatio * 0.2 + vertical * 0.13);
      if (edgeRatio > 0.78 && random() > 0.93) color.lerp(gold, 0.74);
      const offset = index * 3;
      positions[offset] = x + (random() - 0.5) * 0.045;
      positions[offset + 1] = y + (random() - 0.5) * 0.04;
      positions[offset + 2] = mountain.z + (random() - 0.5) * 0.24;
      colors[offset] = color.r;
      colors[offset + 1] = color.g;
      colors[offset + 2] = color.b;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      size: mountain.id.indexOf("hero") > -1 ? 0.062 : 0.052,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createPeakRidges(THREE) {
    const group = new THREE.Group();
    ALL_MOUNTAIN_LAYOUT.forEach(function (mountain, index) {
      const positions = new Float32Array(42 * 3);
      for (let step = 0; step < 42; step += 1) {
        const t = step / 41;
        const x = mountain.x - mountain.width + t * mountain.width * 2;
        const y = mountain.base + ridgeHeightAt(mountain, t) + Math.sin(t * 20 + index * 1.7) * 0.035;
        const offset = step * 3;
        positions[offset] = x;
        positions[offset + 1] = y;
        positions[offset + 2] = mountain.z + 0.35;
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      group.add(new THREE.Points(geometry, new THREE.PointsMaterial({
        color: index === 1 || index === 4 ? 0x4be0f2 : 0x2ab5c5,
        transparent: true,
        opacity: index === 1 || index === 4 ? 0.58 : 0.28,
        size: index === 1 || index === 4 ? 0.055 : 0.04,
        depthWrite: false
      })));
    });
    return group;
  }

  function createRiverChannels(THREE, particleCount) {
    const group = new THREE.Group();
    const path = VALLEY_RIVER_LAYOUT.center;
    group.add(createValleyRiverSurface(THREE, VALLEY_RIVER_LAYOUT));
    group.add(createPathParticles(THREE, path, Math.max(420, Math.round(particleCount * 0.055)), 16001, 0xa5f8f6, 0.034));
    group.add(createRiverCurrentLines(THREE, path));
    return group;
  }

  function createValleyRiverSurface(THREE, layout) {
    const leftBank = [];
    const rightBank = [];
    const path = layout.center;
    path.forEach(function (point, index) {
      const previous = path[Math.max(0, index - 1)];
      const next = path[Math.min(path.length - 1, index + 1)];
      const dx = next[0] - previous[0];
      const dy = next[1] - previous[1];
      const length = Math.max(0.001, Math.sqrt(dx * dx + dy * dy));
      const nx = -dy / length;
      const ny = dx / length;
      const width = layout.widths[index];
      leftBank.push([point[0] + nx * width, point[1] + ny * width]);
      rightBank.push([point[0] - nx * width, point[1] - ny * width]);
    });
    const shape = new THREE.Shape();
    shape.moveTo(leftBank[0][0], leftBank[0][1]);
    leftBank.slice(1).forEach(function (point) { shape.lineTo(point[0], point[1]); });
    rightBank.slice().reverse().forEach(function (point) { shape.lineTo(point[0], point[1]); });
    shape.closePath();
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({
      color: 0x3ec2cb,
      transparent: true,
      opacity: 0.32,
      depthWrite: false,
      side: THREE.DoubleSide
    }));
    mesh.position.z = 0.45;
    return mesh;
  }

  function createRiverCurrentLines(THREE, path) {
    const group = new THREE.Group();
    [-0.13, 0.11].forEach(function (offset, index) {
      const points = path.map(function (point, pointIndex) {
        const scale = 1 - pointIndex / Math.max(1, path.length - 1) * 0.45;
        return new THREE.Vector3(point[0] + offset * scale, point[1], point[2] + 0.28);
      });
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({
        color: index ? 0x68e4e4 : 0xe1ffff,
        transparent: true,
        opacity: 0.38,
        depthWrite: false
      })));
    });
    return group;
  }

  function createWaterfallFalls(THREE, particleCount) {
    const group = new THREE.Group();
    WATERFALL_LAYOUT.forEach(function (fall, index) {
      group.add(createWaterfallSurface(THREE, fall));
      const path = [[fall.x, fall.top, fall.z], [fall.x + fall.bend, (fall.top + fall.bottom) / 2, fall.z + 0.1], [fall.x + fall.bend * 0.35, fall.bottom, fall.z + 0.16]];
      group.add(createPathParticles(THREE, path, Math.max(180, Math.round(particleCount * 0.012)), 24101 + index, 0xb4fbff, 0.046));
    });
    return group;
  }

  function createWaterfallSurface(THREE, fall) {
    const group = new THREE.Group();
    group.add(createWaterfallParticles(THREE, fall, 520, Math.round((fall.x + 12) * 1000)));
    group.add(createWaterfallStrands(THREE, fall));
    group.add(createWaterfallMist(THREE, fall, 120, Math.round((fall.x + 21) * 1000)));
    return group;
  }

  function createWaterfallStrands(THREE, fall) {
    const group = new THREE.Group();
    for (let strand = 0; strand < 2; strand += 1) {
      const drift = (strand - 0.5) * fall.width * 0.48;
      const points = [];
      for (let step = 0; step <= 36; step += 1) {
        const t = step / 36;
        points.push(new THREE.Vector3(
          fall.x + drift + fall.bend * Math.sin(t * Math.PI) + Math.sin(t * 10 + strand * 1.7) * 0.045,
          fall.top + (fall.bottom - fall.top) * t,
          fall.z + 0.48
        ));
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: strand === 1 ? 0xe8ffff : 0x83e7ec,
        transparent: true,
        opacity: 0.2,
        depthWrite: false
      })));
    }
    return group;
  }

  function createWaterfallParticles(THREE, fall, count, seed) {
    const random = seededRandom(seed);
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const t = Math.pow(random(), 0.84);
      const offset = index * 3;
      const width = fall.width * (0.35 + t * 0.8);
      positions[offset] = fall.x + (random() - 0.5) * width + fall.bend * Math.sin(t * Math.PI) + Math.sin(t * 15 + index) * 0.035;
      positions[offset + 1] = fall.top + (fall.bottom - fall.top) * t + (random() - 0.5) * 0.07;
      positions[offset + 2] = fall.z + 0.5 + (random() - 0.5) * 0.16;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xbefcff,
      size: 0.053,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createWaterfallMist(THREE, fall, count, seed) {
    const random = seededRandom(seed);
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const offset = index * 3;
      positions[offset] = fall.x + fall.bend * 0.35 + (random() - 0.5) * fall.width * 1.8;
      positions[offset + 1] = fall.bottom + random() * 0.34;
      positions[offset + 2] = fall.z + 0.68 + (random() - 0.5) * 0.14;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xe3ffff,
      size: 0.075,
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createWaterRipples(THREE) {
    const group = new THREE.Group();
    for (let ripple = 0; ripple < 6; ripple += 1) {
      const points = [];
      const y = -3.78 - ripple * 0.14;
      for (let step = 0; step <= 80; step += 1) {
        const t = step / 80;
        points.push(new THREE.Vector3(-4.7 + t * 7.5, y + Math.sin(t * Math.PI * 2 + ripple) * 0.045, 1.22));
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      group.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({
        color: ripple === 1 ? 0xe7c167 : 0x68dbe1,
        transparent: true,
        opacity: ripple === 1 ? 0.45 : 0.42,
        depthWrite: false
      })));
    }
    return group;
  }

  function createMistBands(THREE) {
    const group = new THREE.Group();
    MIST_LAYOUT.forEach(function (mist, index) {
      group.add(createMistCloud(THREE, mist, 240, 36011 + index));
    });
    return group;
  }

  function createMistCloud(THREE, mist, count, seed) {
    const random = seededRandom(seed);
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const progress = random();
      const spread = (random() - 0.5) * mist.depth;
      const offset = index * 3;
      positions[offset] = mist.x + (progress - 0.5) * mist.span;
      positions[offset + 1] = mist.y + Math.sin(progress * Math.PI * 2 + mist.phase) * 0.18 + spread;
      positions[offset + 2] = 1.35 + (random() - 0.5) * 0.12;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xd5f8f7,
      size: 0.085,
      transparent: true,
      opacity: 0.22,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createSparseAtmosphere(THREE) {
    const random = seededRandom(3091);
    const count = 30;
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const offset = index * 3;
      positions[offset] = -8.7 + random() * 17.4;
      positions[offset + 1] = 1.9 + random() * 2.8;
      positions[offset + 2] = -1.9;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0xe8ffff,
      size: 0.045,
      transparent: true,
      opacity: 0.46,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function createPathParticles(THREE, path, count, seed, color, size) {
    const random = seededRandom(seed);
    const curve = new THREE.CatmullRomCurve3(path.map(function (value) { return vectorFromArray(THREE, value); }));
    const positions = new Float32Array(count * 3);
    for (let index = 0; index < count; index += 1) {
      const point = curve.getPoint(random());
      const offset = index * 3;
      positions[offset] = point.x + (random() - 0.5) * 0.14;
      positions[offset + 1] = point.y + (random() - 0.5) * 0.08;
      positions[offset + 2] = point.z + (random() - 0.5) * 0.1;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return new THREE.Points(geometry, new THREE.PointsMaterial({
      color: color,
      size: size,
      transparent: true,
      opacity: 0.78,
      depthWrite: false,
      sizeAttenuation: true
    }));
  }

  function mountainShape(THREE, mountain) {
    const shape = new THREE.Shape();
    const contour = mountainContour(mountain);
    shape.moveTo(contour[0].x, contour[0].y);
    contour.slice(1).forEach(function (point) { shape.lineTo(point.x, point.y); });
    shape.lineTo(mountain.x + mountain.width, mountain.base);
    shape.lineTo(mountain.x - mountain.width, mountain.base);
    shape.lineTo(mountain.x - mountain.width, mountain.base);
    return shape;
  }

  function mountainContour(mountain) {
    const profile = IRREGULAR_RIDGE_PROFILE[mountain.profile] || IRREGULAR_RIDGE_PROFILE.low;
    return profile.map(function (height, index) {
      const t = index / Math.max(1, profile.length - 1);
      return { x: mountain.x - mountain.width + t * mountain.width * 2, y: mountain.base + height * mountain.height };
    });
  }

  function ridgeHeightAt(mountain, t) {
    const profile = IRREGULAR_RIDGE_PROFILE[mountain.profile] || IRREGULAR_RIDGE_PROFILE.low;
    const scaled = Math.max(0, Math.min(profile.length - 1, t * (profile.length - 1)));
    const left = Math.floor(scaled);
    const right = Math.min(profile.length - 1, left + 1);
    const blend = scaled - left;
    return mountain.height * (profile[left] + (profile[right] - profile[left]) * blend);
  }

  function vectorFromArray(THREE, value) {
    return new THREE.Vector3(value[0], value[1], value[2]);
  }

  function isInsideFocusArea(x, y, focusArea) {
    return Math.abs(x - focusArea.x) < focusArea.width * 0.64 && Math.abs(y - focusArea.y) < focusArea.height * 0.52;
  }

  function disposeObject(object) {
    object.traverse(function (child) {
      if (child.geometry) child.geometry.dispose();
      if (!child.material) return;
      if (Array.isArray(child.material)) child.material.forEach(function (material) { material.dispose(); });
      else child.material.dispose();
    });
  }

  function seededRandom(seed) {
    let value = seed >>> 0;
    return function () {
      value += 0x6D2B79F5;
      let result = value;
      result = Math.imul(result ^ result >>> 15, result | 1);
      result ^= result + Math.imul(result ^ result >>> 7, result | 61);
      return ((result ^ result >>> 14) >>> 0) / 4294967296;
    };
  }

  function createUnavailableController() {
    return { available: false, start() {}, pause() {}, resize() {}, destroy() {} };
  }

  global.createLoginParticleLandscape = createLoginParticleLandscape;
})(window);
