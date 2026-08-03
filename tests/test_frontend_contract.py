# -*- coding: utf-8 -*-
import json
from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT_DIR / "frontend" / "index.html"
MAP_HTML = ROOT_DIR / "frontend" / "map.html"
PANORAMA_HTML = ROOT_DIR / "frontend" / "panorama.html"
LIVE2D_BUNDLE = next((ROOT_DIR / "frontend" / "cubism" / "assets").glob("index-*.js"))
LOGIN_PARTICLE_MODULE = ROOT_DIR / "frontend" / "login-particle-landscape.js"
THREE_BUNDLE = ROOT_DIR / "frontend" / "vendor" / "three.min.js"
PARTICLES_BUNDLE = ROOT_DIR / "frontend" / "vendor" / "particles.min.js"
SCENIC_ASSET_DIR = ROOT_DIR / "frontend" / "assets" / "scenics"
SCENIC_SOURCE_MAP = SCENIC_ASSET_DIR / "sources.json"


def extract_js_function(source, name):
    marker = f"function {name}("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    for pos in range(brace_start, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f"Function {name} was not closed")


class FrontendContractTests(unittest.TestCase):
    def test_tourist_frontend_tracks_emotion_and_sends_it_to_live2d(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("currentEmotion", html)
        self.assertIn("emotionLabel", html)
        self.assertIn("postLive2D({ emotion:", html)
        self.assertIn("data.emotion", html)
        self.assertIn("data.latency_ms", html)
        self.assertIn("emotionEnabled", html)
        self.assertIn("emotion: state.currentEmotion", html)

    def test_live2d_bundle_accepts_emotion_messages(self):
        bundle = LIVE2D_BUNDLE.read_text(encoding="utf-8")

        self.assertIn("setEmotion", bundle)
        self.assertIn("t.emotion", bundle)
        self.assertIn("document.body.dataset.emotion", bundle)

    def test_live2d_bundle_maps_emotions_to_haru_expressions(self):
        bundle = LIVE2D_BUNDLE.read_text(encoding="utf-8")

        self.assertIn("emotionExpressionMap", bundle)
        self.assertIn("happy:`F05`", bundle)
        self.assertIn("thanks:`F07`", bundle)
        self.assertIn("surprised:`F06`", bundle)
        self.assertIn("confused:`F03`", bundle)
        self.assertIn("sad:`F04`", bundle)
        self.assertNotIn("confused:`F04`,sad:`F04`", bundle)
        self.assertNotIn("confused:`F03`,sad:`F03`", bundle)
        self.assertIn("setExpression", bundle)
        self.assertIn("lastExpression", bundle)

    def test_tourist_frontend_labels_sad_reflective_emotion(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        emotion_label = extract_js_function(html, "emotionLabel")

        self.assertIn('sad: "伤心反思"', emotion_label)

    def test_admin_frontend_exposes_operation_and_avatar_controls(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("游客消费分析", html)
        self.assertIn("路线偏好", html)
        self.assertIn("avatar-preset-card", html)
        self.assertIn("配置一", html)
        self.assertIn("配置二", html)

    def test_admin_frontend_saves_avatar_appearance_and_emotion_fields(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("avatar_preset_id", html)
        self.assertIn("function selectedAvatarPresetConfig(", html)
        self.assertIn("function editableAvatarConfig(", html)
        self.assertIn("function readAvatarFormConfig(", html)
        self.assertIn("function updateAvatarDraftFromForm(", html)
        self.assertIn("function persistCurrentAvatarDraftToCatalog(", html)
        self.assertIn("function avatarPresetsForSave(", html)
        self.assertIn("function commitAvatarDraftForSave(", html)
        self.assertIn("function addAvatarPreset(", html)
        self.assertIn("function deleteAvatarPreset(", html)
        self.assertIn("dhAvatarName", html)
        self.assertIn("dhAvatarModel", html)
        self.assertIn("dhAvatarPresetLabel", html)
        self.assertIn("dhAvatarPresetSummary", html)
        self.assertIn("dhAvatarAppearance", html)
        self.assertIn("dhAvatarCostume", html)
        self.assertIn("dhAvatarEmotionEnabled", html)
        self.assertIn("dhAvatarStyle", html)
        self.assertIn("dhAvatarOpening", html)
        self.assertIn("const data = commitAvatarDraftForSave()", html)
        self.assertIn("avatar_presets: presets", html)
        self.assertNotIn("appearance: selectedAvatar.appearance", html)
        self.assertNotIn("emotion_enabled: selectedAvatar.emotion_enabled", html)

    def test_admin_digital_human_voice_config_uses_single_voice_choice(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderDigitalHumanConfig")
        detail = extract_js_function(html, "renderAvatarPresetDetail")
        save_config = extract_js_function(html, "saveConfig")
        commit_save = extract_js_function(html, "commitAvatarDraftForSave")
        preview_voice = extract_js_function(html, "previewVoice")

        self.assertIn("dhVoiceProvider", page)
        self.assertIn("dhVoiceChoice", page)
        self.assertIn("数字人使用音色", page)
        self.assertIn("试听音色", page)
        self.assertIn("previewVoice()", page)
        self.assertIn("configSaving", html)
        self.assertIn("保存中...", html)
        self.assertIn("buildVoiceChoiceOptions", html)
        self.assertIn("selectedVoiceChoiceValue", html)
        self.assertIn("voiceConfigFromChoice", html)
        self.assertIn("commitAvatarDraftForSave()", save_config)
        self.assertIn("voiceConfigFromChoice", commit_save)
        self.assertIn("voiceConfigFromChoice", preview_voice)
        self.assertIn("保存配置", extract_js_function(html, "adminActionBar"))
        self.assertNotIn("保存语音配置", page)
        self.assertNotIn("开源语音音色", page)
        self.assertNotIn("克隆音色</label>", page)
        self.assertNotIn("Edge-TTS 音色</label>", page)

    def test_admin_digital_human_page_uses_expandable_avatar_presets(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderDigitalHumanConfig")
        detail = extract_js_function(html, "renderAvatarPresetDetail")

        self.assertIn("renderAvatarPresetCards", page)
        self.assertIn("renderAvatarPresetDetail", page)
        self.assertIn("添加配置", page)
        self.assertIn("配置一：温婉新中式导游", html)
        self.assertIn("配置二：亲和活力讲解员", html)
        self.assertIn("function selectAvatarPreset(", html)
        self.assertIn("persistCurrentAvatarDraftToCatalog()", extract_js_function(html, "selectAvatarPreset"))
        self.assertIn("删除配置", detail)
        delete_preset = extract_js_function(html, "deleteAvatarPreset")
        self.assertIn("confirm(", delete_preset)
        self.assertIn("avatar_presets", delete_preset)
        self.assertIn('apiPost("/api/admin/config"', delete_preset)
        self.assertIn("syncAvatarPresetState", delete_preset)
        self.assertIn("立即保存", delete_preset)
        self.assertNotIn("需要点击顶部", delete_preset)
        self.assertIn("window.deleteAvatarPreset = deleteAvatarPreset", html)
        self.assertIn("expandedAvatarPresetId", html)
        self.assertIn("当前选择", html)

    def test_admin_config_refresh_does_not_restore_deleted_avatar_during_save_race(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        load_admin_data = extract_js_function(html, "loadAdminData")
        delete_preset = extract_js_function(html, "deleteAvatarPreset")
        save_config = extract_js_function(html, "saveConfig")

        self.assertIn("configMutationSeqAtStart", load_admin_data)
        self.assertIn("canApplyConfig", load_admin_data)
        self.assertIn("!state.configSaving", load_admin_data)
        self.assertIn("configMutationSeqAtStart === (state.configMutationSeq || 0)", load_admin_data)
        self.assertIn("if (canApplyConfig)", load_admin_data)
        self.assertIn("state.configMutationSeq = (state.configMutationSeq || 0) + 1", delete_preset)
        self.assertIn("state.configMutationSeq = (state.configMutationSeq || 0) + 1", save_config)

    def test_frontend_visual_system_uses_apple_design_tokens(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("DESIGN-apple.md", html)
        self.assertIn("--apple-blue: #0066cc", html)
        self.assertIn("--apple-ink: #1d1d1f", html)
        self.assertIn("--apple-parchment: #f5f5f7", html)
        self.assertIn("--apple-dark-tile: #272729", html)
        self.assertIn("--apple-hairline: #e0e0e0", html)
        self.assertIn("letter-spacing: 0", html)
        self.assertIn("backdrop-filter: saturate(180%) blur(20px)", html)
        self.assertNotIn("refero.design", html)
        self.assertNotIn("--surface-glass", html)
        self.assertNotIn("--accent-jade", html)

    def test_tourist_frontend_uses_unframed_digital_human_stage(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")

        self.assertIn('class="digital-human-stage', tourist)
        self.assertIn("stage-context", tourist)
        self.assertIn("stage-live2d", tourist)
        self.assertIn("stage-subject", tourist)
        self.assertIn("stage-live2d-centered", tourist)
        self.assertIn("stage-mode-status", tourist)
        self.assertIn("conversation-dock", tourist)
        self.assertIn("conversation-drawer", tourist)
        self.assertIn("conversation-history-panel", tourist)
        self.assertIn("stage-map-module", tourist)
        self.assertIn("scenic-gallery", tourist)
        self.assertNotIn('id="tourMapCanvas"', tourist)
        self.assertNotIn('class="apple-message-panel"', tourist)
        self.assertNotIn('class="apple-product-stage"', tourist)

    def test_tourist_stage_exposes_five_stable_modes(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function currentStageMode()", html)
        self.assertIn('return "listening"', html)
        self.assertIn('return "thinking"', html)
        self.assertIn('return "speaking"', html)
        self.assertIn('return "route-active"', html)
        self.assertIn('return "idle"', html)
        self.assertIn('stage.dataset.mode = currentStageMode()', html)

    def test_tourist_conversation_history_is_collapsible(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")
        history_pos = tourist.index('id="conversationDrawer"')
        live2d_pos = tourist.index("stage-live2d stage-subject stage-live2d-centered")
        iframe_pos = tourist.index('<iframe id="live2dFrame"')
        dock_pos = tourist.index('<div class="conversation-dock">')
        left_rail_close_pos = tourist.index('</aside>')

        self.assertIn("conversationDrawerOpen", html)
        self.assertIn("toggleConversationDrawer", html)
        self.assertIn("conversation-history-panel", html)
        self.assertIn("conversation-drawer.open.conversation-history-panel", html)
        self.assertIn("conversation-stage-panel", html)
        self.assertIn("stage-left-rail", html)
        self.assertIn('aria-expanded="${state.conversationDrawerOpen ? "true" : "false"}"', html)
        self.assertIn("查看对话记录", html)
        self.assertIn("收起对话记录", html)
        self.assertGreater(history_pos, live2d_pos)
        self.assertGreater(history_pos, iframe_pos)
        self.assertGreater(history_pos, left_rail_close_pos)
        self.assertLess(live2d_pos, dock_pos)
        self.assertLess(history_pos, dock_pos)
        self.assertRegex(html, r"\.conversation-stage-panel\s*\{[^}]*right:\s*clamp")
        self.assertIn(".digital-human-stage.history-open", html)
        self.assertIn("420px minmax(560px, 620px)", html)
        self.assertIn("minmax(992px, 1fr)", html)
        self.assertIn("column-gap: 12px", html)
        self.assertIn("width: min(560px, calc(100% - 32px))", html)
        self.assertIn("width: min(100%, 620px)", html)
        self.assertIn("max-height: 680px", html)
        self.assertIn("width: min(100%, 420px)", html)
        self.assertIn("width: min(100%, 520px)", html)
        self.assertNotIn("width: min(100%, 390px)", html)
        self.assertRegex(html, r"\.conversation-history-panel\s+\.msg\s*\{[^}]*max-width:\s*100%;")
        self.assertRegex(html, r"\.conversation-history-panel\s+\.bubble\s*\{[^}]*max-width:\s*100%;")
        self.assertNotIn('conversation-drawer.open + .conversation-dock-bar', html)

    def test_tourist_map_lives_in_stage_context_and_expands_on_demand(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")
        quick_panel_pos = tourist.index('id="coreScenicQuickPanel"')
        live2d_pos = tourist.index("stage-live2d stage-subject stage-live2d-centered")
        stage_context_pos = tourist.index('<div class="stage-context stage-right-rail">')
        map_panel_pos = tourist.index('id="lingshanMapPanel"')

        self.assertIn("mapCanvasExpanded", html)
        self.assertIn("toggleTourMapCanvas", html)
        self.assertIn("stage-map-module", html)
        self.assertIn("stage-map-expanded", html)
        self.assertIn('lingshanMapPanel.classList.toggle("stage-map-expanded"', html)
        self.assertIn("展开路线地图", html)
        self.assertIn("收起路线地图", html)
        self.assertIn("lingshanMap.instance.resize()", html)
        self.assertLess(quick_panel_pos, stage_context_pos)
        self.assertLess(quick_panel_pos, live2d_pos)
        self.assertLess(live2d_pos, stage_context_pos)
        self.assertGreater(map_panel_pos, stage_context_pos)
        self.assertNotIn('class="tour-map-canvas"', tourist)

    def test_tourist_stage_reduces_empty_space_with_dense_route_context(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")

        self.assertIn("stage-guide-shell", html)
        self.assertIn("stage-map-layout", html)
        self.assertIn("stage-guide-panel", html)
        self.assertIn("stage-dashboard-card", html)
        self.assertIn("stage-action-row", html)
        self.assertIn("stageRoutePace", tourist)
        self.assertIn("stageRouteAction", tourist)
        self.assertIn("讲当前路线", tourist)
        self.assertIn("查演出时间", tourist)
        self.assertIn("grid-template-columns: minmax(250px, 286px) minmax(560px, 1fr) minmax(320px, 380px)", html)
        self.assertNotIn("grid-template-columns: minmax(286px, 330px) minmax(420px, 1fr) minmax(360px, 430px)", html)
        self.assertIn(".stage-left-rail", html)
        self.assertIn(".stage-subject", html)
        self.assertIn(".stage-live2d-centered", html)
        self.assertIn(".stage-right-rail", html)
        self.assertIn("grid-column: 2", html)
        self.assertIn("grid-column: 3", html)
        self.assertIn("height: 380px", html)
        stage_block = html.split(".digital-human-stage {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 820px", stage_block)
        self.assertIn("height: clamp(820px, calc(100vh - 96px), 900px)", stage_block)
        self.assertIn("max-height: none", stage_block)
        self.assertNotIn("height: auto", stage_block)
        self.assertNotIn("height: calc(100vh - 96px)", stage_block)
        self.assertIn("@media (min-width: 1440px)", html)
        self.assertIn(".stage-map-module.map-panel { height: 420px; }", html)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", html)
        self.assertRegex(html, r"\.stage-map-layout\s*\{[^}]*grid-template-columns:\s*1fr;")
        self.assertRegex(html, r"\.stage-route-summary\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\);")
        self.assertRegex(html, r"\.stage-map-layout\s*\{[^}]*margin-bottom:\s*18px;")
        self.assertRegex(html, r"\.stage-map-layout\s*\{[^}]*min-height:\s*398px;")
        self.assertRegex(html, r"\.stage-map-layout\s*\{[^}]*position:\s*relative;")
        self.assertRegex(html, r"\.stage-guide-panel,\s*\.stage-dashboard-card\s*\{[^}]*position:\s*relative;[^}]*z-index:\s*0;")
        self.assertRegex(html, r"\.stage-map-module\.map-panel\s*\{[^}]*position:\s*relative;[^}]*z-index:\s*1;[^}]*isolation:\s*isolate;")
        self.assertRegex(html, r"\.stage-route-summary\s*\{[^}]*margin:\s*0;")
        self.assertRegex(html, r"\.stage-route-summary\s*>\s*div\s*\{[^}]*min-height:\s*58px;")
        summary_text_block = html.split(".stage-route-summary strong {", 1)[1].split("}", 1)[0]
        self.assertIn("line-height: 1.35", summary_text_block)
        self.assertIn("white-space: normal", summary_text_block)
        self.assertIn("overflow-wrap: anywhere", summary_text_block)
        self.assertNotIn("white-space: nowrap", summary_text_block)
        self.assertNotIn("text-overflow: ellipsis", summary_text_block)
        self.assertNotIn("overflow: hidden", summary_text_block)
        self.assertRegex(html, r"\.stage-context\s*\{[^}]*overflow-y:\s*auto;")
        self.assertRegex(html, r"@media \(max-width: 980px\)\s*\{[\s\S]*?\.stage-context\s*\{[^}]*overflow-x:\s*hidden;[^}]*overflow-y:\s*auto;")
        self.assertNotIn("text-align: center; overflow: visible; border-left", html)
        self.assertRegex(html, r"\.stage-guide-shell\s*\{[^}]*height:\s*auto;[^}]*grid-template-rows:\s*auto auto auto;")
        self.assertRegex(html, r"\.stage-dashboard-card\s*\{[^}]*grid-template-rows:\s*auto auto auto;")
        self.assertNotIn("grid-template-rows: auto auto minmax(0, 1fr)", html)
        self.assertIn("width: min(100%, 520px)", html)
        self.assertIn("place-items: center", html)
        self.assertIn("stage-route-steps", html)
        self.assertIn("stageRouteSteps", tourist)
        self.assertNotIn("stage-live2d-float", html)
        self.assertNotIn("padding-right: clamp(250px, 24vw, 350px)", html)
        self.assertNotIn("width: clamp(240px, 22vw, 330px)", html)
        self.assertNotIn("padding-right: clamp(160px, 18vw, 280px)", html)
        self.assertIn("coreScenicQuickPanel", tourist)
        self.assertIn("core-scenic-quick-panel", tourist)
        self.assertNotIn("grid-template-columns: minmax(235px, 285px) minmax(420px, 1fr) minmax(220px, 280px)", html)
        self.assertNotIn("grid-template-columns: minmax(500px, 560px) minmax(0, 1fr)", html)

    def test_tourist_scenic_gallery_exposes_expected_actions(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("renderScenicGallery", html)
        self.assertIn("开始讲解", html)
        self.assertIn("地图定位", html)
        self.assertIn("查看实景", html)

    def test_tourist_uses_left_core_scenic_quick_panel_and_gallery_below_stage(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")

        self.assertIn("renderCoreScenicQuickPanel", html)
        self.assertIn(".core-scenic-quick-panel", html)
        self.assertIn(".core-scenic-list", html)
        self.assertIn(".core-scenic-list {", html)
        self.assertIn("slice(0, 16)", html)
        self.assertIn("开始讲解", html)
        self.assertIn("askSpot", html)
        self.assertIn("scenicImageUrl", html)
        self.assertIn("scenic-gallery-media", html)
        self.assertIn("/assets/scenics/", html)
        self.assertIn('id="coreScenicQuickPanel"', tourist)
        self.assertIn('class="core-scenic-quick-panel"', tourist)
        self.assertIn("renderCoreScenicQuickPanel()", tourist)
        self.assertIn('const coreScenicQuickPanel = $("coreScenicQuickPanel")', html)
        self.assertIn("coreScenicQuickPanel.innerHTML = renderCoreScenicQuickPanel()", html)
        self.assertNotIn("stage-scenic-strip", tourist)

    def test_topbar_hides_identity_chip_and_tts_install_status(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertNotIn("currentUserText", html)
        self.assertNotIn('class="user-chip"', html)
        self.assertNotIn("TTS 待安装", html)
        self.assertNotIn("开源语音已启用", html)
        self.assertIn("DeepSeek 已配置", html)
        self.assertIn("本地知识库模式", html)
        self.assertIn('id="healthText"', html)

    def test_core_scenic_quick_panel_has_real_vertical_scroll_viewport(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        panel_block = html.split(".core-scenic-quick-panel {", 1)[1].split("}", 1)[0]
        list_block = html.split(".core-scenic-list {", 1)[1].split("}", 1)[0]

        self.assertIn("overflow: hidden", panel_block)
        self.assertIn("flex: 1", list_block)
        self.assertIn("overflow-y: auto", list_block)
        self.assertIn("overscroll-behavior: contain", list_block)

    def test_core_scenic_quick_cards_do_not_render_duplicate_bottom_cta(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        quick_panel = extract_js_function(html, "renderCoreScenicQuickPanel")

        self.assertIn("core-scenic-meta", quick_panel)
        self.assertIn("<small>开始讲解</small>", quick_panel)
        self.assertNotIn("quick-action", quick_panel)

    def test_scenic_image_assets_have_source_map_for_all_core_spots(self):
        self.assertTrue(SCENIC_SOURCE_MAP.exists())
        sources = json.loads(SCENIC_SOURCE_MAP.read_text(encoding="utf-8"))
        items = sources.get("items", [])
        ids = {item.get("id") for item in items}

        self.assertEqual(len(items), 16)
        for index in range(1, 17):
          scenic_id = f"LS-{index:03d}"
          self.assertIn(scenic_id, ids)
          asset = SCENIC_ASSET_DIR / f"{scenic_id}.jpg"
          self.assertTrue(asset.exists(), scenic_id)
          self.assertGreater(asset.stat().st_size, 3 * 1024, scenic_id)
          item = next(item for item in items if item.get("id") == scenic_id)
          self.assertTrue(item.get("source_url"), scenic_id)
          self.assertTrue(item.get("image_src"), scenic_id)
        self.assertFalse(any(item.get("source_type") == "overview_crop" for item in items))

    def test_admin_frontend_uses_task_oriented_workbench_layout(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('class="admin-workbench"', html)
        self.assertIn("admin-icon-rail", html)
        self.assertIn("admin-command-bar", html)
        self.assertIn("admin-data-canvas", html)
        self.assertIn("admin-kpi-band", html)
        self.assertIn("admin-data-table", html)
        self.assertNotIn("workbench-shell", html)
        self.assertNotIn("admin-page-kicker", html)

    def test_login_uses_sliding_auth_switch_layout(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("auth-switch-shell", html)
        self.assertIn("auth-card", html)
        self.assertIn("auth-form-panel sign-in-panel", html)
        self.assertIn("auth-form-panel sign-up-panel", html)
        self.assertIn("auth-overlay-panel", html)
        self.assertIn("auth-register-toggle", html)
        self.assertIn("auth-login-toggle", html)
        self.assertIn("login-wordmark", html)
        self.assertIn("login-segmented-control", html)
        self.assertIn("login-primary-action", html)
        self.assertIn("registerUsername", html)
        self.assertIn("registerDisplayName", html)
        self.assertIn("registerPassword", html)
        self.assertIn("registerPasswordConfirm", html)
        self.assertIn("setAuthPanel", html)
        self.assertIn("doRegister", html)
        self.assertNotIn('class="login-brand"', html)

    def test_login_does_not_report_post_auth_boot_errors_as_login_failure(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        do_login = extract_js_function(html, "doLogin")

        self.assertIn("loginBusy", html)
        self.assertIn("safeSnippet(", html)
        self.assertIn("finishLoginAfterAuth", html)
        self.assertNotIn("await bootAppData()", do_login)
        self.assertIn("登录失败", do_login)
        self.assertIn("登录中", html)

    def test_frontend_loads_local_lucide_icons_for_navigation(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        lucide = ROOT_DIR / "frontend" / "vendor" / "lucide.min.js"

        self.assertTrue(lucide.exists())
        self.assertIn('src="/vendor/lucide.min.js"', html)
        self.assertIn("data-lucide", html)
        self.assertIn("refreshLucideIcons", html)
        self.assertNotIn('src="https://cdn.jsdelivr.net/npm/lucide', html)

    def test_admin_mode_overrides_legacy_horizontal_sidebar_layout(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        v2 = html.split("Apple product-stage v2", 1)[1]
        app_block = v2.split(".app {", 1)[1].split("}", 1)[0]
        sidebar_block = v2.split("\n    .sidebar {", 1)[1].split("}", 1)[0]
        panel_block = v2.split(".sidebar .panel-scroll {", 1)[1].split("}", 1)[0]

        self.assertIn("display: grid", app_block)
        self.assertIn("flex-direction: column", sidebar_block)
        self.assertIn("height: 100%", sidebar_block)
        self.assertIn("flex-direction: column", panel_block)
        self.assertIn("overflow-y: auto", panel_block)

    def test_login_v2_overrides_legacy_split_screen_grid(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        v2 = html.split("Apple product-stage v2", 1)[1]
        login_block = v2.split(".login-view {", 1)[1].split("}", 1)[0]

        self.assertIn("grid-template-columns: 1fr", login_block)
        self.assertIn("place-items: center", login_block)

    def test_auth_card_floats_over_static_landscape_photo(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        v2 = html.split("Apple product-stage v2", 1)[1]
        login_block = v2.split(".login-view {", 1)[1].split("}", 1)[0]
        overlay_block = v2.split(".login-view::before {", 1)[1].split("}", 1)[0]
        shell_block = v2.split(".auth-switch-shell {", 1)[1].split("}", 1)[0]
        card_block = v2.split(".auth-card {", 1)[1].split("}", 1)[0]
        panel_block = v2.split(".auth-form-panel {", 1)[1].split("}", 1)[0]

        self.assertIn('url("/assets/login-lingshan-sunset.jpg")', login_block)
        self.assertIn("background-size: cover", login_block)
        self.assertIn("background-position: center", login_block)
        self.assertIn("linear-gradient", overlay_block)
        self.assertIn("pointer-events: none", overlay_block)
        self.assertIn("width: min(100%, 920px)", shell_block)
        self.assertIn("background: rgba(255,255,255,.94)", card_block)
        self.assertIn("backdrop-filter: saturate(150%) blur(18px)", card_block)
        self.assertIn("border: 1px solid rgba(255,255,255,.32)", card_block)
        self.assertIn("display: grid", card_block)
        self.assertIn("grid-template-columns: 1fr 1fr", card_block)
        self.assertIn("padding: 28px", panel_block)
        self.assertNotIn("login-photo-backdrop", html)

    def test_login_tts_status_is_short_single_line_chip(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        v2 = html.split("Apple product-stage v2", 1)[1]
        self.assertIn(".login-status-chip {", v2)
        chip_block = v2.split(".login-status-chip {", 1)[1].split("}", 1)[0]
        refresh = extract_js_function(html, "refreshTtsHint")

        self.assertIn('class="login-status-chip"', html)
        self.assertIn("display: inline-flex", chip_block)
        self.assertIn("white-space: nowrap", chip_block)
        self.assertIn("text-overflow: ellipsis", chip_block)
        self.assertIn("max-width: 100%", chip_block)
        self.assertIn("语音：", refresh)
        self.assertIn("可用", refresh)
        self.assertIn("克隆音色待启动", refresh)
        self.assertIn("未就绪", refresh)
        self.assertNotIn("-webkit-line-clamp", chip_block)
        self.assertNotIn("语音服务已启用：", refresh)
        self.assertNotIn("默认低内存模式不会自动启动", refresh)

    def test_login_background_uses_local_landscape_photo_without_particle_layers(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertTrue((ROOT_DIR / "frontend" / "assets" / "login-lingshan-sunset.jpg").exists())
        self.assertIn('url("/assets/login-lingshan-sunset.jpg")', html)
        self.assertNotIn('id="loginParticleCanvas"', html)
        self.assertNotIn('id="loginParticlesJsLayer"', html)
        self.assertNotIn("login-particle-layer", html)
        self.assertNotIn('src="/vendor/three.min.js"', html)
        self.assertNotIn('src="/login-particle-landscape.js"', html)
        self.assertNotIn('src="/vendor/particles.min.js"', html)
        self.assertNotIn("ensureLoginParticleLandscape", html)
        self.assertNotIn("ensureLoginParticlesJs", html)
        self.assertNotIn("particlesJS", html)

    def test_login_landscape_photo_fits_short_desktop_viewports(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("@media (max-height: 820px)", html)
        self.assertIn(".auth-form-panel { padding: 24px; }", html)
        self.assertIn(".auth-switch-shell { width: min(100%, 880px);", html)

    def test_login_panel_keeps_the_lower_valley_visible(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        v2 = html.split("Apple product-stage v2", 1)[1]
        wordmark_block = v2.split(".login-wordmark {", 1)[1].split("}", 1)[0]

        self.assertIn("margin-bottom: 16px", wordmark_block)
        self.assertIn(".login-status-chip {", v2)
        self.assertNotIn("-webkit-line-clamp: 2", v2)

    def test_admin_layout_splits_dashboard_evaluation_and_operation_pages(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('["qaEvaluation", "问答验收"', html)
        self.assertIn('["operationInsights", "运营建议"', html)
        self.assertIn("问答质量验收", html)
        self.assertIn("DeepSeek 评测", html)
        self.assertIn("本地基线", html)
        self.assertIn("/api/admin/evaluation", html)
        self.assertIn("/api/admin/evaluation/run", html)
        self.assertIn("runEvaluation", html)
        self.assertIn("游客运营建议", html)
        self.assertIn("服务风险提醒", html)
        self.assertIn("operation_insights", html)
        self.assertIn("recommended_actions", html)
        self.assertIn("renderQaEvaluationPage", html)
        self.assertIn("renderOperationInsightsPage", html)
        self.assertIn('state.adminPage === "qaEvaluation"', html)
        self.assertIn('state.adminPage === "operationInsights"', html)

    def test_admin_dashboard_keeps_evaluation_and_operation_cards_out_of_overview(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        dashboard = extract_js_function(html, "renderAdminDashboard")

        self.assertNotIn('renderEvaluationCard("deepseek")', dashboard)
        self.assertNotIn('renderEvaluationCard("local")', dashboard)
        self.assertNotIn('renderInsightList("游客运营建议"', dashboard)
        self.assertNotIn('renderInsightList("服务风险提醒"', dashboard)
        self.assertIn("问答质量状态", dashboard)
        self.assertIn("查看问答验收", dashboard)
        self.assertIn("查看运营建议", dashboard)

    def test_admin_evaluation_page_uses_compact_comparison_layout(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderQaEvaluationPage")

        self.assertIn("evaluation-summary-strip", page)
        self.assertIn("evaluation-compare-grid", page)
        self.assertIn("低分题清单", page)
        self.assertIn("测试用例明细", page)
        self.assertIn("预期结果", page)
        self.assertIn("实际结果", page)
        self.assertIn("evaluation-detail-controls", page)
        self.assertIn("renderEvaluationVisualSummary", page)
        self.assertIn("evaluation-visual-grid", html)
        self.assertIn("case_items", html)
        self.assertIn("category_stats", page)
        self.assertIn("exportEvaluationWord", page)
        self.assertIn("旧缓存包含规则直答", html)
        self.assertIn("evaluation-progress-panel", html)
        self.assertIn('role="progressbar"', html)
        self.assertIn("pollEvaluationProgress", html)
        self.assertIn("/api/admin/evaluation/progress?job_id=", html)
        self.assertIn('renderEvaluationCard("deepseek")', page)
        self.assertIn('renderEvaluationCard("local")', page)

    def test_admin_evaluation_progress_does_not_wait_forever_at_zero(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        run_evaluation = extract_js_function(html, "runEvaluation")
        poll_evaluation = extract_js_function(html, "pollEvaluationProgress")

        self.assertIn("evaluationFetchWithTimeout", html)
        self.assertIn("createEvaluationJobId", html)
        self.assertIn("client_job_id", run_evaluation)
        self.assertIn("const clientJobId = createEvaluationJobId(selectedMode)", run_evaluation)
        self.assertIn("evaluationRunRequestTimeoutMs", html)
        self.assertIn("AbortController", html)
        self.assertIn("评测启动请求超时", html)
        self.assertIn("启动响应较慢，正在继续追踪后台任务", html)
        self.assertIn("评测进度请求超时", html)
        self.assertIn("evaluationFetchWithTimeout(\"/api/admin/evaluation/run\"", run_evaluation)
        self.assertIn("evaluationFetchWithTimeout(\"/api/admin/evaluation/progress?job_id=\"", poll_evaluation)
        self.assertIn("\"&mode=\" + encodeURIComponent(selectedMode)", poll_evaluation)

    def test_admin_evaluation_can_be_cancelled_from_frontend(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        card = extract_js_function(html, "renderEvaluationCard")
        cancel_button = extract_js_function(html, "renderEvaluationCancelButton")
        cancel_evaluation = extract_js_function(html, "cancelEvaluation")

        self.assertIn("结束评测", cancel_button)
        self.assertIn("cancelEvaluation('${mode}')", cancel_button)
        self.assertIn("renderEvaluationCancelButton(mode)", card)
        self.assertIn("state.evaluationJobIds", html)
        self.assertIn("/api/admin/evaluation/cancel", cancel_evaluation)
        self.assertIn("正在结束评测，当前题完成后停止", html)
        self.assertIn('progress.status === "cancelled"', html)
        self.assertIn("window.cancelEvaluation = cancelEvaluation", html)

    def test_admin_evaluation_runs_semantic_review_automatically_without_extra_button(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        card = extract_js_function(html, "renderEvaluationCard")
        hit_detail = extract_js_function(html, "renderEvaluationHitDetail")

        self.assertNotIn("renderEvaluationReviewButton(mode)", card)
        self.assertNotIn("function renderEvaluationReviewButton", html)
        self.assertNotIn("function reviewLowScoreEvaluation", html)
        self.assertNotIn("reviewLowScoreEvaluation('deepseek')", html)
        self.assertNotIn("evaluationReview-", html)
        self.assertNotIn("window.reviewLowScoreEvaluation", html)
        self.assertIn("reviewing", html)
        self.assertIn("正在语义复核低分题", html)
        self.assertIn("语义复核命中", hit_detail)
        self.assertIn("语义复核失败", hit_detail)
        self.assertIn("semantic_review.covered_include", hit_detail)
        self.assertIn("semantic_review.error", hit_detail)

    def test_admin_evaluation_progress_updates_without_forcing_scroll_to_top(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        poll_evaluation = extract_js_function(html, "pollEvaluationProgress")
        run_evaluation = extract_js_function(html, "runEvaluation")
        get_scroll_element = extract_js_function(html, "getAdminScrollElement")
        refresh_progress = extract_js_function(html, "refreshEvaluationProgressView")
        render_function = extract_js_function(html, "render")

        self.assertIn("refreshEvaluationProgressView", html)
        self.assertIn("withPreservedAdminScroll", html)
        self.assertIn("renderPreservingAdminScroll", html)
        self.assertIn("getAdminScrollElement", html)
        self.assertIn('id="evaluationProgress-${escapeHtml(mode)}"', html)
        self.assertIn('id="evaluationRun-${escapeHtml(mode)}"', html)
        self.assertIn('document.querySelector(".admin-data-canvas")', get_scroll_element)
        self.assertLess(
            get_scroll_element.index('document.querySelector(".admin-data-canvas")'),
            get_scroll_element.index('document.querySelector(".workspace")')
        )

        not_found_branch = poll_evaluation.split('if (progress.status === "not_found" && state.evaluationBusy === selectedMode)', 1)[1].split("return;", 1)[0]
        running_branch = poll_evaluation.split('if (progress.status === "queued" || progress.status === "running" || progress.status === "reviewing" || progress.status === "cancelling")', 1)[1].split("return;", 1)[0]
        self.assertIn("refreshEvaluationProgressView(selectedMode)", not_found_branch)
        self.assertIn("refreshEvaluationProgressView(selectedMode)", running_branch)
        self.assertNotIn("render();", not_found_branch)
        self.assertNotIn("render();", running_branch)
        self.assertNotIn("render();", run_evaluation)
        self.assertIn("refreshEvaluationProgressView(selectedMode)", run_evaluation)
        self.assertIn("withPreservedAdminScroll(() =>", refresh_progress)
        self.assertIn("requestAnimationFrame(restoreScroll)", html)
        self.assertIn("state.evaluationBusy", render_function)
        self.assertIn("restoreEvaluationScroll", render_function)
        self.assertIn("renderPreservingAdminScroll()", poll_evaluation)

    def test_admin_async_data_refresh_preserves_scroll_during_evaluation(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        load_admin_data = extract_js_function(html, "loadAdminData")
        refresh_services = extract_js_function(html, "refreshServices")

        self.assertIn("renderPreservingAdminScroll()", load_admin_data)
        self.assertNotIn("state.voiceClones = clones.voices || [];\n        render();", load_admin_data)
        self.assertIn("renderPreservingAdminScroll()", refresh_services)
        self.assertNotIn("finally {\n        render();", refresh_services)

    def test_admin_evaluation_page_has_filtering_and_word_export_helpers(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function filteredEvaluationCases(", html)
        self.assertIn("function renderEvaluationCaseRows(", html)
        self.assertIn("function renderEvaluationVisualSummary(", html)
        self.assertIn("function setEvaluationDetailMode(", html)
        self.assertIn("function exportEvaluationWord(", html)
        self.assertIn("/api/admin/evaluation/export?mode=", html)
        self.assertIn("导出 DeepSeek Word", html)
        self.assertIn("导出本地基线 Word", html)
        self.assertIn("导出对比报告 Word", html)

    def test_admin_operation_page_groups_insights_risks_and_actions(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderOperationInsightsPage")

        self.assertIn("游客最关心什么", page)
        self.assertIn("当前服务风险", page)
        self.assertIn("建议景区怎么优化", page)
        self.assertIn("低评分反馈摘要", page)

    def test_admin_operation_page_has_deepseek_ai_analysis_action(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderOperationInsightsPage")

        self.assertIn("AI分析建议", page)
        self.assertIn("operationAiAnalysis", html)
        self.assertIn("operationAiBusy", html)
        self.assertIn("function runOperationAiAnalysis(", html)
        self.assertIn('/api/admin/analytics/ai-analysis', html)
        self.assertIn("DeepSeek 辅助分析", html)
        self.assertIn("aiAnalysisError", html)

    def test_service_page_shows_error_feedback_and_retry_action(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("serviceStatusError", html)
        self.assertIn("服务状态读取失败", html)
        self.assertIn("retryLoadServices", html)

    def test_service_page_shows_service_setup_hint_and_disabled_start(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("service.hint", html)
        self.assertIn("!service.can_start", html)
        self.assertIn("service.runtime", html)
        self.assertIn("运行设备", html)
        self.assertIn("effective_device", html)

    def test_spot_click_uses_segmented_narration_endpoint(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('apiGet("/api/scenic/" + id + "/narration")', html)
        self.assertIn("display_segments", html)
        self.assertIn("data.segments", html)
        self.assertIn("speakNarration", html)
        self.assertIn('purpose: "narration_first"', html)
        self.assertIn("narrationSpeechStatus", html)
        self.assertIn("第 1 段语音生成中", html)
        self.assertIn("景点讲解克隆音色合成失败", html)

    def test_live2d_speaking_subtitles_are_wired_to_all_audio_paths(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("live2dSubtitle", html)
        self.assertIn("live2d-subtitle", html)
        self.assertIn("setLive2DSubtitle", html)
        self.assertIn("clearLive2DSubtitle", html)
        self.assertIn("startSubtitleSync", html)
        self.assertIn("normalizeSubtitles", html)
        self.assertIn("data.tts && data.tts.subtitles", html)
        self.assertIn("speech.subtitles", html)
        self.assertIn("playRealtimeAudio(data.audio_url, data.text || \"\", data.tts && data.tts.subtitles)", html)
        self.assertIn("playAudioSpeechQueued(speech.audio_url, session.sentences[index], session, speech.subtitles)", html)

    def test_frontend_sanitizes_speech_text_before_tts_and_subtitles(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("prepareSpeechText", html)
        self.assertIn("normalizeTimeForSpeech", html)
        self.assertIn("decimalNumberToSpeech", html)
        self.assertIn("stripStageDirectionsForSpeech", html)
        self.assertIn("normalizePolyphonicChineseForSpeech", html)
        self.assertIn("raw = prepareSpeechText(text)", html)
        self.assertIn('minutes === 30', html)
        self.assertIn('"半"', html)
        self.assertIn("微微|语气|笑|欠身", html)
        self.assertIn('if (number < 1000)', html)
        self.assertIn('"百"', html)
        self.assertIn('"零"', html)
        self.assertIn("汉藏", html)
        self.assertIn("臧传", html)
        self.assertIn("同行", html)
        self.assertIn("同游", html)
        self.assertIn("桥长", html)
        self.assertIn("桥的长度", html)
        self.assertIn("桥身长", html)
        self.assertIn("桥身长度", html)
        self.assertIn("全长", html)
        self.assertIn("总长度", html)
        self.assertIn('.replace(/长/g, "常")', html)

    def test_page_switching_does_not_pause_ai_speech(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertNotIn("pauseHeavyFrontendActivity()", html)
        self.assertIn("function stopAiSpeech() {\n      stopSpeech();", html)
        self.assertIn('onclick="stopAiSpeech()"', html)
        self.assertIn("globalStopSpeechBtn", html)
        self.assertIn("const canStopSpeech = hasActiveSpeechPlayback();", html)
        self.assertIn('globalStopSpeechBtn.classList.toggle("hidden", !canStopSpeech)', html)

    def test_frontend_labels_gpt_sovits_compatibility_as_gsv_tts_lite(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("GSV-TTS-Lite 克隆音色", html)
        self.assertIn("GSV-TTS-Lite 克隆音色服务", html)
        self.assertIn("旧配置值 gpt_sovits 仅用于兼容", html)
        self.assertNotIn("GPT-SoVITS 克隆音色", html)

    def test_realtime_voice_shows_final_recognition_status(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("首次识别会稍慢", html)
        self.assertIn("正在识别最终文本", html)
        self.assertIn("speech_rms_threshold", html)
        self.assertIn("请用正常音量说话", html)

    def test_realtime_done_updates_message_meta_and_live2d_emotion(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('if (data.type === "done")', html)
        self.assertIn("state.messages[this.answerIndex].meta = responseMeta(data)", html)
        self.assertIn("applyAssistantMeta(data)", html)
        self.assertIn("postLive2D({ emotion:", html)

    def test_browser_speech_recognition_is_corrected_before_chat_send(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        toggle_voice = extract_js_function(html, "toggleVoice")

        self.assertIn("function correctVoiceTranscript(", html)
        self.assertIn('apiPost("/api/voice/correct-text"', html)
        self.assertIn("correctVoiceTranscript(transcript)", toggle_voice)
        self.assertIn("sendMessage(corrected.text", toggle_voice)
        self.assertNotIn("sendMessage(transcript);", toggle_voice)
        self.assertIn("语音纠错失败", html)
        self.assertIn("已纠正识别", html)

    def test_frontend_response_meta_prefers_server_emotion_label_and_client_criticism_fallback(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        response_meta = extract_js_function(html, "responseMeta")
        apply_meta = extract_js_function(html, "applyAssistantMeta")
        send_message = extract_js_function(html, "sendMessage")

        self.assertIn("data.emotion_label", response_meta)
        self.assertIn("isCriticismText", html)
        self.assertIn("function assistantEmotion(", html)
        self.assertIn("assistantEmotion(data)", apply_meta)
        self.assertIn("data.query = data.query || query", send_message)
        self.assertIn("伤心反思", response_meta)
        self.assertLess(response_meta.index("data.emotion_label"), response_meta.index("emotionLabel(data.emotion)"))

    def test_realtime_voice_button_is_continuous_mode_toggle(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("realtimeSessionActive", html)
        self.assertIn("startRealtimeConversation", html)
        self.assertIn("stopRealtimeConversation", html)
        self.assertIn('type: "start", mode: "continuous", allow_barge_in: true', html)
        self.assertIn('type: "end_session"', html)
        self.assertIn("\u7ee7\u7eed\u8bf4\u8bdd\uff0c\u6211\u5728\u542c", html)

    def test_realtime_voice_requires_server_side_asr_correction_capability(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        realtime_ready = extract_js_function(html, "realtimeVoiceReady")

        self.assertIn("protocol", realtime_ready)
        self.assertIn("asr_correction_required", realtime_ready)
        self.assertIn("asr_correction_uses_deepseek", realtime_ready)

    def test_realtime_done_uses_last_voice_query_for_criticism_fallback(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("lastVoiceQuery", html)
        self.assertIn("this.lastVoiceQuery = query", html)
        self.assertIn("data.query = data.query || this.lastVoiceQuery || state.realtimeTranscript", html)
        self.assertIn("AI \u56de\u590d\u4e2d\uff0c\u53ef\u76f4\u63a5\u6253\u65ad", html)
        self.assertIn('if (this.sessionActive && data.continue_listening !== false)', html)
        self.assertIn('state.realtimeTurnState = "listening"', html)
        self.assertNotIn('state.isListening = false;\n            postLive2D({ listen: false });\n            this.cleanup(true);', html)

    def test_realtime_frontend_keeps_capture_after_turn_and_supports_barge_in(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("maybeTriggerRealtimeBargeIn", html)
        self.assertIn("bufferToBase64", html)
        self.assertIn('type: "barge_in", audio: this.bufferToBase64(buffer)', html)
        self.assertIn("stopCurrentAiPlaybackForBargeIn", html)
        self.assertIn('this.turnState = "answering"', html)
        self.assertIn('this.turnState = "answering";\n            this.bargeInArmed = true;', html)
        self.assertIn('this.turnState = "listening"', html)
        self.assertIn("if (!this.sessionActive) return", html)
        self.assertNotIn('this.cleanup(true);\n            render();\n            return;\n          }\n          if (data.type === "interrupted")', html)

    def test_realtime_done_waits_for_audio_queue_before_resuming_listening(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("resumeRealtimeListeningAfterAudio", html)
        self.assertIn("this.audioQueue = this.audioQueue.then(resumeAfterAudio, resumeAfterAudio)", html)
        self.assertIn('state.realtimeTurnState = "speaking"', html)
        self.assertIn("AI 正在播报，可直接打断", html)

    def test_realtime_listening_event_is_deferred_while_audio_queue_is_draining(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("pendingServerListening", html)
        self.assertIn('if (this.turnState === "speaking")', html)
        self.assertIn('this.pendingServerListening = true', html)
        self.assertIn("return;", html[html.index('if (data.type === \"listening\")'):html.index('if (data.type === \"asr_partial\")')])

    def test_realtime_barge_in_resolves_current_audio_queue(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("finishRealtimePlayback", html)
        self.assertIn("_finishRealtimePlayback", html)
        self.assertIn("const generation = this.playbackGeneration", html)
        self.assertIn("generation !== this.playbackGeneration", html)

    def test_stopping_realtime_mode_keeps_ai_playback_stop_control_available(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        stop_block = html[html.index("async stop() {"):html.index("interrupt() {")]

        self.assertIn("function hasActiveSpeechPlayback()", html)
        self.assertIn("const canStopSpeech = hasActiveSpeechPlayback();", html)
        self.assertIn("stopSpeechBtn.disabled = !canStopSpeech", html)
        self.assertIn('globalStopSpeechBtn.classList.toggle("hidden", !canStopSpeech)', html)
        self.assertIn("state.isSpeaking = hasActiveSpeechPlayback();", stop_block)
        self.assertNotIn("state.isSpeaking = false;", stop_block)

    def test_tourist_feedback_entry_lives_next_to_stop_speech(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        tourist = extract_js_function(html, "renderTourist")
        submit_feedback = extract_js_function(html, "submitFeedback")

        self.assertIn("feedbackPanelOpen", html)
        self.assertIn("feedbackSubmitting", html)
        self.assertIn("function toggleTouristFeedbackPanel(", html)
        self.assertIn("touristFeedbackBtn", tourist)
        self.assertIn("touristFeedbackPanel", tourist)
        self.assertIn("touristFeedbackRating", tourist)
        self.assertIn("touristFeedbackMessage", tourist)
        self.assertLess(tourist.index("stopSpeechBtn"), tourist.index("touristFeedbackBtn"))
        self.assertIn('onclick="toggleTouristFeedbackPanel()"', tourist)
        self.assertIn('onclick="submitFeedback()"', tourist)
        self.assertIn('apiPost("/api/feedback", { message, rating })', submit_feedback)
        self.assertIn('$("touristFeedbackMessage")', submit_feedback)
        self.assertIn('$("touristFeedbackRating")', submit_feedback)
        self.assertNotIn('$("fbMessage")', submit_feedback)
        self.assertNotIn('$("fbRating")', submit_feedback)
        self.assertIn("state.feedbackPanelOpen = false", submit_feedback)

    def test_admin_feedback_page_is_read_only(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        side = extract_js_function(html, "renderSide")
        action_bar = extract_js_function(html, "adminActionBar")
        feedback_page = extract_js_function(html, "renderFeedbackPage")

        self.assertIn("反馈管理", side)
        self.assertIn("查看游客反馈并跟踪满意度", side)
        self.assertNotIn("提交测试反馈", feedback_page)
        self.assertNotIn("fbRating", feedback_page)
        self.assertNotIn("fbMessage", feedback_page)
        self.assertNotIn("onclick=\"submitFeedback()\"", feedback_page)
        self.assertIn("游客满意度反馈", feedback_page)
        self.assertIn("暂无反馈记录", feedback_page)
        self.assertNotIn('state.adminPage === "feedback"', action_bar)

    def test_pdf_upload_hint_explains_all_pdfs_use_paddleocr(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("所有 PDF 都将使用 PaddleOCR 解析", html)
        self.assertIn("正在使用 PaddleOCR 解析 PDF", html)
        self.assertIn("PDF 解析完成并已加入知识库", html)
        self.assertIn("OCR 页数", html)
        self.assertIn("OCR 模型", html)
        self.assertNotIn("文本型 PDF 优先本地解析", html)
        self.assertNotIn("PDF 将使用 PaddleOCR", html)

    def test_admin_knowledge_page_shows_current_library_details(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("当前知识库内容", html)
        self.assertIn("knowledgeSummary", html)
        self.assertIn("knowledge_documents", html)
        self.assertIn("上传时间", html)
        self.assertIn("来源", html)
        self.assertIn("正文预览", html)
        self.assertIn("toggleKnowledgePreview", html)
        self.assertIn("can_delete", html)
        page = extract_js_function(html, "renderAdminKnowledge")
        self.assertNotIn("知识库质量概览", page)
        self.assertNotIn("const quality = doc.quality_report", page)
        self.assertNotIn("质检标签", html)
        self.assertNotIn("复核建议", html)

    def test_admin_knowledge_full_content_shows_plain_text_without_quality_highlights(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        page = extract_js_function(html, "renderAdminKnowledge")

        self.assertIn("knowledge-content-expanded", html)
        self.assertIn("expanded ? escapeHtml(fullContent) : escapeHtml(preview)", page)
        self.assertNotIn("renderKnowledgeContentWithQuality", html)
        self.assertNotIn("knowledge-duplicate-sentence", html)
        self.assertNotIn("knowledge-extraction-issue", html)
        self.assertNotIn("extractionKnowledgeIssueKeys", html)
        self.assertNotIn('title="重复句"', html)
        self.assertNotIn('title="抽取疑点"', html)
        self.assertNotIn("抽取疑点", html)
        self.assertNotIn("重复句", html)
        self.assertNotIn("OCR 疑点", html)

    def test_frontend_displays_route_recommendation_reasons(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("recommendation_reason", html)
        self.assertIn("recommendation_context", html)
        self.assertIn("推荐理由", html)
        self.assertIn("routeRecommendationReason", html)

    def test_tourist_frontend_embeds_3d_amap_route_panel(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("lingshanMapPanel", html)
        self.assertIn("/api/map/config", html)
        self.assertIn('viewMode: "3D"', html)
        self.assertIn("window._AMapSecurityConfig", html)
        self.assertIn("AMap.Marker", html)
        self.assertIn("AMap.Polyline", html)
        self.assertIn("/api/map/tools/weather", html)
        self.assertIn("highlightRouteOnMap", html)
        self.assertIn("focusScenicOnMap", html)
        self.assertIn("showMapFallback", html)
        self.assertIn("data.route_suggestion.map", html)
        self.assertIn("loadMapWeather", html)

    def test_tourist_map_routes_prefer_amap_walking_before_controlled_fallback(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("AMap.Walking", html)
        self.assertIn("buildWalkableRoutePath", html)
        self.assertIn("drawRoutePolyline", html)
        self.assertIn("walking.search", html)
        self.assertIn("routePathSource", html)
        self.assertIn("walkable", html)
        self.assertIn("fallbackRoutePath", html)
        self.assertIn("isUsableWalkingSegment", html)
        self.assertIn("mapData.walk_polyline", html)
        self.assertIn("const controlledPath = controlledRoutePath(mapData)", html)
        self.assertIn("const walkablePath = await buildWalkableRoutePath(points, mapData)", html)
        self.assertIn("segmentFallbackPath(mapData", html)
        self.assertIn("const segmentFallback = fallbackSegments[i]", html)
        self.assertIn("fallbackLength >= 5 && segment.length < fallbackLength", html)
        self.assertIn("if (controlledPath.length >= 2) return controlledPath", html)
        self.assertLess(html.index("if (controlledPath.length >= 2) return controlledPath"), html.index("new AMap.Walking"))
        self.assertLess(html.index("const controlledPath = controlledRoutePath(mapData)"), html.index("const walkablePath = await buildWalkableRoutePath(points, mapData)"))
        self.assertIn("const source = controlledRoutePath(mapData).length >= 2 ? \"controlled\" : \"walkable\"", html)
        self.assertIn("drawRoutePolyline(walkablePath, source)", html)
        self.assertIn('drawRoutePolyline(controlledPath, "controlled")', html)

    def test_tourist_map_uses_compact_number_markers_to_avoid_clipped_names(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("map-route-marker", html)
        self.assertIn("mapRouteMarkerContent", html)
        self.assertIn("content: mapRouteMarkerContent(point)", html)
        self.assertIn("display: inline-grid", html)
        self.assertIn("grid-template-columns: 24px", html)
        self.assertIn("routeStopSummary(route)", html)
        self.assertIn("markerTitle", html)
        self.assertNotIn("map-route-name", html)
        self.assertNotIn('label: { content: `${point.order}. ${point.name}`, direction: "top" }', html)

    def test_tourist_route_marker_text_moves_to_info_bar(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("function routeStopSummary(route)", html)
        self.assertIn("point.order || index + 1", html)
        self.assertIn("point.name", html)
        self.assertIn("info.title = infoText", html)

    def test_tourist_map_weather_renders_on_separate_info_line(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        update_block = extract_js_function(html, "updateMapPanelText")

        self.assertIn("map-info-route", html)
        self.assertIn("map-info-stops", html)
        self.assertIn("map-info-weather", html)
        self.assertIn("info.innerHTML", update_block)
        self.assertIn("state.mapWeather", update_block)
        self.assertNotIn("[routeText, stopText, state.mapWeather].filter(Boolean).join", update_block)

    def test_tourist_map_weather_animation_overlay_is_local_and_temporary(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("weather-animation-overlay", html)
        self.assertIn("function showWeatherAnimation", html)
        self.assertIn("function hideWeatherAnimation", html)
        self.assertIn("function weatherAnimationTypeFromText", html)

        load_map_weather = extract_js_function(html, "loadMapWeather")
        load_backend_weather = extract_js_function(html, "loadBackendMapWeather")
        show_animation = extract_js_function(html, "showWeatherAnimation")
        hide_animation = extract_js_function(html, "hideWeatherAnimation")
        animation_type = extract_js_function(html, "weatherAnimationTypeFromText")

        self.assertIn("weatherAnimationType", html)
        self.assertIn("weatherAnimationVisible", html)
        self.assertIn("weatherAnimationTimer", html)
        self.assertIn("showWeatherAnimation(state.mapWeather)", load_map_weather)
        self.assertIn("showWeatherAnimation(state.mapWeather)", load_backend_weather)
        self.assertIn("6000", show_animation)
        self.assertIn("clearTimeout(state.weatherAnimationTimer)", show_animation)
        self.assertIn("state.weatherAnimationTimer = null", hide_animation)
        self.assertIn("prefers-reduced-motion: reduce", html)
        for keyword in ["晴", "阴", "多云", "雨", "雪", "雾", "霾"]:
            self.assertIn(keyword, animation_type)
        for animation_class in ["weather-sunny", "weather-cloudy", "weather-rain", "weather-snow", "weather-fog"]:
            self.assertIn(animation_class, html)

    def test_map_tools_keep_weather_but_remove_unreliable_ip_location(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("loadAmapPlugins", html)
        self.assertIn("AMap.Weather", html)
        self.assertIn("getLive", html)
        self.assertIn("loadBackendMapWeather", html)
        self.assertIn("正在通过高德 JSAPI 查询", html)
        self.assertNotIn("AMap.CitySearch", html)
        self.assertNotIn("getLocalCity", html)
        self.assertNotIn("loadMapIpLocation", html)
        self.assertNotIn("loadBackendMapIpLocation", html)
        self.assertNotIn("IP定位", html)

    def test_map_fallback_updates_after_async_load_failure_and_late_dom_render(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("syncMapFallbackState", html)
        self.assertIn("地图加载失败，已切换本地路线示意。", html)
        self.assertIn('state.mapStatus !== "3D 地图已就绪"', html)
        self.assertIn("updateMapPanelText", html)
        self.assertIn("showMapFallback(state.mapStatus", html)

    def test_map_panel_selects_default_route_for_initial_visible_fallback(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("ensureDefaultRouteMap", html)
        self.assertIn("默认路线：", html)
        self.assertIn("ensureDefaultRouteMap(options);\n        renderSide();", html)
        self.assertIn("ensureDefaultRouteMap();\n        loadMapConfig();", html)

    def test_map_panel_prefers_first_route_when_interest_changes(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("loadRoutes(tag, { preferFirst: true })", html)
        self.assertIn("function ensureDefaultRouteMap(options)", html)
        self.assertIn("options.preferFirst", html)
        self.assertIn("state.selectedRouteMap = route.map", html)
        self.assertIn("route_nature", html)
        self.assertIn("route_family", html)

    def test_map_panel_opens_standalone_map_page(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("mapOpenBtn", html)
        self.assertIn("openStandaloneMap", html)
        self.assertIn("/map.html?route=", html)
        self.assertIn("打开地图", html)
        self.assertIn("buildStandaloneMapUrl", html)
        self.assertNotIn("toggleMapExpanded", html)

    def test_tourist_map_exposes_scenic_panorama_entry_without_iframing_456ss(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("实景", html)
        self.assertIn("/api/panorama/scenic/", html)
        self.assertIn("openPanoramaViewer", html)
        self.assertIn("/panorama.html?scenic=", html)
        self.assertNotIn('src="https://street.456ss.com', html)

    def test_tourist_map_exposes_overview_panorama_map_entry(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("全景地图", html)
        self.assertIn("openOverviewPanorama", html)
        self.assertIn("/panorama.html?overview=1", html)
        self.assertIn("/api/panorama/overview", html)

    def test_standalone_map_page_loads_3d_amap_and_route_payload(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("standaloneMapPanel", html)
        self.assertIn("standaloneAmap", html)
        self.assertIn("/api/map/config", html)
        self.assertIn("/api/map/scenics", html)
        self.assertIn("/api/map/route/", html)
        self.assertIn("/api/routes", html)
        self.assertIn('viewMode: "3D"', html)
        self.assertIn("window._AMapSecurityConfig", html)
        self.assertIn("AMap.Marker", html)
        self.assertIn("AMap.Polyline", html)
        self.assertIn("URLSearchParams", html)
        self.assertIn("route_history", html)
        self.assertIn("地图加载失败", html)
        self.assertIn("本地路线示意", html)

    def test_standalone_map_exposes_scenic_panorama_entry(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("实景", html)
        self.assertIn("/api/panorama/scenic/", html)
        self.assertIn("openPanoramaViewer", html)
        self.assertIn("/panorama.html?scenic=", html)
        self.assertNotIn('src="https://street.456ss.com', html)

    def test_standalone_map_exposes_overview_panorama_map_entry(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("全景地图", html)
        self.assertIn("openOverviewPanorama", html)
        self.assertIn("/panorama.html?overview=1", html)
        self.assertIn("/api/panorama/overview", html)

    def test_standalone_map_return_guide_navigates_to_tourist_stage(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("function returnToGuide()", html)
        self.assertIn('onclick="returnToGuide()"', html)
        self.assertIn('"/?view=tourist"', html)
        self.assertNotIn('onclick="window.close()"', html)

    def test_index_honors_tourist_view_url_parameter_on_boot_and_login(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        boot = extract_js_function(html, "boot")
        do_login = extract_js_function(html, "doLogin")

        self.assertIn("function preferredAppModeFromUrl()", html)
        self.assertIn('params.get("view") === "tourist"', html)
        self.assertIn("preferredAppModeFromUrl() ||", boot)
        self.assertIn("preferredAppModeFromUrl() ||", do_login)

    def test_panorama_page_uses_panolens_and_has_missing_asset_fallback(self):
        html = PANORAMA_HTML.read_text(encoding="utf-8")

        self.assertIn("PANOLENS", html)
        self.assertIn("THREE", html)
        self.assertIn("/api/panorama/scenic/", html)
        self.assertIn("PanoramaViewer", html)
        self.assertIn("ImagePanorama", html)
        self.assertIn("暂无全景素材", html)
        self.assertIn('target="_blank"', html)
        self.assertIn("street.456ss.com", html)
        self.assertNotIn("<iframe", html)

    def test_panorama_page_supports_overview_gallery_switching(self):
        html = PANORAMA_HTML.read_text(encoding="utf-8")

        self.assertIn("/api/panorama/overview", html)
        self.assertIn("overview=1", html)
        self.assertIn("overviewGallery", html)
        self.assertIn("switchOverviewPanorama", html)
        self.assertIn("灵山胜境全景地图", html)

    def test_panorama_page_has_static_image_fallback_to_avoid_black_screen(self):
        html = PANORAMA_HTML.read_text(encoding="utf-8")

        self.assertIn("viewerFallbackImage", html)
        self.assertIn("showViewerFallbackImage", html)
        self.assertIn("hideViewerFallbackImage", html)
        self.assertIn("panorama.addEventListener", html)

    def test_standalone_map_routes_prefer_amap_walking_before_controlled_fallback(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("AMap.Walking", html)
        self.assertIn("buildWalkableRoutePath", html)
        self.assertIn("drawRoutePolyline", html)
        self.assertIn("walking.search", html)
        self.assertIn("routePathSource", html)
        self.assertIn("walkable", html)
        self.assertIn("fallbackRoutePath", html)
        self.assertIn("isUsableWalkingSegment", html)
        self.assertIn("routeMap.walk_polyline", html)
        self.assertIn("const controlledPath = controlledRoutePath(routeMap)", html)
        self.assertIn("const walkablePath = await buildWalkableRoutePath(points, state.routeMap)", html)
        self.assertIn("segmentFallbackPath(routeMap", html)
        self.assertIn("const segmentFallback = fallbackSegments[i]", html)
        self.assertIn("fallbackLength >= 5 && segment.length < fallbackLength", html)
        self.assertIn("if (controlledPath.length >= 2) return controlledPath", html)
        self.assertLess(html.index("if (controlledPath.length >= 2) return controlledPath"), html.index("new AMap.Walking"))
        self.assertLess(html.index("const controlledPath = controlledRoutePath(routeMap)"), html.index("const walkablePath = await buildWalkableRoutePath(points, state.routeMap)"))
        self.assertIn("const source = controlledRoutePath(state.routeMap).length >= 2 ? \"controlled\" : \"walkable\"", html)
        self.assertIn("drawRoutePolyline(walkablePath, source)", html)
        self.assertIn('drawRoutePolyline(controlledPath, "controlled")', html)
        self.assertNotIn("path: state.routeMap.polyline,", html)

    def test_standalone_map_page_has_controlbar_and_performance_settings(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("AMap.ControlBar", html)
        self.assertIn("addControl", html)
        self.assertIn("showControlButton", html)
        self.assertIn("animateEnable: false", html)
        self.assertIn("jogEnable: false", html)
        self.assertIn("route-marker", html)
        self.assertIn("markerContent", html)
        self.assertNotIn("label: { content:", html)
        self.assertNotIn("if (state.map && state.AMap) {\n        if (state.map && state.AMap)", html)

    def test_standalone_route_marker_names_are_not_ellipsized(self):
        html = MAP_HTML.read_text(encoding="utf-8")
        marker_block = html.split(".route-marker {", 1)[1].split("}", 1)[0]
        marker_name_block = html.split(".route-marker-name {", 1)[1].split("}", 1)[0]

        self.assertIn("display: inline-grid", marker_block)
        self.assertIn("grid-template-columns: 28px max-content", marker_block)
        self.assertIn("width: max-content", marker_block)
        self.assertIn("max-width: none", marker_block)
        self.assertIn("overflow: visible", marker_block)
        self.assertIn("min-width: max-content", marker_name_block)
        self.assertIn("width: max-content", marker_name_block)
        self.assertIn("max-width: none", marker_name_block)
        self.assertIn("overflow: visible", marker_name_block)
        self.assertIn("white-space: nowrap", marker_name_block)
        self.assertNotIn("text-overflow", marker_name_block)
        self.assertNotIn("overflow: hidden", marker_name_block)
        self.assertNotIn("max-width: 96px", marker_name_block)
        self.assertIn("markerSideForPoint(point)", html)
        self.assertIn("route-marker-left", html)

    def test_standalone_route_marker_side_uses_viewport_position(self):
        html = MAP_HTML.read_text(encoding="utf-8")

        self.assertIn("function markerSideForPoint(point)", html)
        self.assertIn("state.map.lngLatToContainer", html)
        self.assertIn('return "route-marker-right"', html)
        self.assertIn('return "route-marker-left"', html)
        self.assertIn("markerContent(point)", html)
        self.assertNotIn('Number(point.order || 0) % 2 === 0 ? "route-marker-left" : "route-marker-right"', html)

    def test_ip_location_ui_and_frontend_code_are_removed(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertNotIn("sanitizeMapToolError", html)
        self.assertNotIn("IP定位暂不可用", html)
        self.assertNotIn("USERKEY_PLAT_NOMATCH", html)
        self.assertNotIn("/api/map/tools/ip-location", html)

    def test_map_panel_keeps_route_fallback_available_when_amap_is_unavailable(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn("map-fallback-overlay", html)
        self.assertIn("map-fallback-stops", html)
        self.assertIn('showMapFallback(state.mapStatus || "本地路线示意", route)', html)
        self.assertIn("地图加载失败，已切换本地路线示意。", html)

    def test_map_panel_hides_fallback_when_3d_map_is_ready(self):
        html = INDEX_HTML.read_text(encoding="utf-8")

        self.assertIn('hideMapFallback();', html)
        self.assertIn("function hideMapFallback()", html)
        self.assertIn("fallback.style.display = \"none\"", html)
        self.assertIn("if (lingshanMap.instance) {\n        hideMapFallback();\n        return;\n      }", html)
        self.assertNotIn('lingshanMap.instance && state.mapStatus === "3D 地图已就绪"', html)
        self.assertNotIn('showMapFallback("路线顺序", route)', html)
        self.assertNotIn('showMapFallback("路线顺序", mapData)', html)


if __name__ == "__main__":
    unittest.main()
