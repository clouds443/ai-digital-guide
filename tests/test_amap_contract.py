# -*- coding: utf-8 -*-
import json
import math
import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import main  # noqa: E402


class AmapContractTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def assertPathContainsOrdered(self, path, waypoints, places=5):
        rounded_path = [[round(item[0], places), round(item[1], places)] for item in path]
        cursor = 0
        for waypoint in waypoints:
            expected = [round(waypoint[0], places), round(waypoint[1], places)]
            try:
                index = rounded_path.index(expected, cursor)
            except ValueError:
                self.fail("missing ordered waypoint {0} after index {1}".format(expected, cursor))
            cursor = index + 1

    def coord_distance_m(self, start, end):
        lng_m = (end[0] - start[0]) * 111000 * math.cos(math.radians((start[1] + end[1]) / 2.0))
        lat_m = (end[1] - start[1]) * 111000
        return (lng_m * lng_m + lat_m * lat_m) ** 0.5

    def test_map_config_returns_amap_js_credentials_and_camera_defaults(self):
        with mock.patch.dict(
            os.environ,
            {
                "AMAP_JS_KEY": "demo-key",
                "AMAP_JS_SECURITY_CODE": "demo-security",
            },
            clear=False,
        ):
            response = self.client.get("/api/map/config")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["amap_key"], "demo-key")
        self.assertEqual(data["security_js_code"], "demo-security")
        self.assertEqual(data["center"], [120.1007, 31.4255])
        self.assertGreaterEqual(data["pitch"], 45)
        self.assertGreaterEqual(data["zoom"], 15)

    def test_map_config_reports_missing_frontend_key_without_crashing(self):
        with mock.patch.dict(os.environ, {"AMAP_JS_KEY": "", "AMAP_JS_SECURITY_CODE": ""}, clear=False):
            response = self.client.get("/api/map/config")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("AMAP_JS_KEY", data["error"])

    def test_map_route_returns_points_polyline_bounds_and_skipped_stops(self):
        response = self.client.get("/api/map/route/route_family")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], "route_family")
        self.assertGreaterEqual(len(data["points"]), 5)
        self.assertEqual(len(data["polyline"]), len(data["points"]))
        self.assertIn("bounds", data)
        self.assertIn("southwest", data["bounds"])
        self.assertIn("northeast", data["bounds"])
        self.assertIsInstance(data["skipped_stops"], list)
        first = data["points"][0]
        self.assertIn("lng", first)
        self.assertIn("lat", first)
        self.assertIn("order", first)

    def test_nature_and_family_routes_both_have_map_points(self):
        for route_id in ("route_nature", "route_family"):
            with self.subTest(route_id=route_id):
                response = self.client.get("/api/map/route/{0}".format(route_id))

                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data["id"], route_id)
                self.assertGreaterEqual(len(data["points"]), 5)
                self.assertEqual(len(data["polyline"]), len(data["points"]))
                self.assertFalse(data["skipped_stops"])

    def test_route_maps_include_walkable_polyline_for_internal_park_roads(self):
        for route_id in ("route_history", "route_nature", "route_family", "route_fast_2h"):
            with self.subTest(route_id=route_id):
                response = self.client.get("/api/map/route/{0}".format(route_id))

                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertIn("walk_polyline", data)
                self.assertGreater(len(data["walk_polyline"]), len(data["points"]))
                self.assertNotEqual(data["walk_polyline"], data["polyline"])
                self.assertLessEqual(self.coord_distance_m(data["walk_polyline"][0], data["polyline"][0]), 80)
                self.assertLessEqual(self.coord_distance_m(data["walk_polyline"][-1], data["polyline"][-1]), 80)
                for lng, lat in data["walk_polyline"]:
                    self.assertGreaterEqual(lng, data["bounds"]["southwest"][0])
                    self.assertLessEqual(lng, data["bounds"]["northeast"][0])
                    self.assertGreaterEqual(lat, data["bounds"]["southwest"][1])
                    self.assertLessEqual(lat, data["bounds"]["northeast"][1])

    def test_walkable_polyline_uses_short_internal_road_segments(self):
        for route_id in ("route_history", "route_nature", "route_family", "route_fast_2h"):
            with self.subTest(route_id=route_id):
                response = self.client.get("/api/map/route/{0}".format(route_id))

                self.assertEqual(response.status_code, 200)
                path = response.get_json()["walk_polyline"]
                jumps = []
                for start, end in zip(path, path[1:]):
                    lng_m = (end[0] - start[0]) * 111000 * math.cos(math.radians((start[1] + end[1]) / 2.0))
                    lat_m = (end[1] - start[1]) * 111000
                    distance_m = (lng_m * lng_m + lat_m * lat_m) ** 0.5
                    if distance_m > 260:
                        jumps.append((start, end, round(distance_m, 1)))
                self.assertFalse(jumps, "walk_polyline contains long direct jumps: {0}".format(jumps[:3]))

    def test_all_preset_routes_use_current_controlled_white_road_waypoints(self):
        expected = {
            "route_history": [
                [120.102300, 31.421289],
                [120.101198, 31.423203],
                [120.100820, 31.423802],
                [120.099922, 31.424501],
                [120.099549, 31.424970],
                [120.099635, 31.426016],
                [120.098646, 31.426992],
                [120.098468, 31.427413],
                [120.096493, 31.430161],
                [120.098646, 31.426992],
                [120.100100, 31.426181],
                [120.102491, 31.427799],
                [120.102600, 31.426597],
                [120.101467, 31.425903],
                [120.102253, 31.424757],
                [120.103073, 31.424501],
            ],
            "route_nature": [
                [120.101194, 31.423203],
                [120.100820, 31.423802],
                [120.099922, 31.424501],
                [120.098711, 31.424844],
                [120.097795, 31.426814],
                [120.096493, 31.430161],
                [120.098077, 31.424293],
                [120.098824, 31.424674],
                [120.100751, 31.426306],
            ],
            "route_family": [
                [120.099922, 31.424501],
                [120.099527, 31.426181],
                [120.098646, 31.426992],
                [120.098468, 31.427413],
                [120.099501, 31.427014],
                [120.100100, 31.426181],
                [120.102491, 31.427799],
                [120.102600, 31.426597],
                [120.101467, 31.425903],
                [120.103073, 31.424501],
            ],
        }
        for route_id, waypoints in expected.items():
            with self.subTest(route_id=route_id):
                response = self.client.get("/api/map/route/{0}".format(route_id))

                self.assertEqual(response.status_code, 200)
                path = response.get_json()["walk_polyline"]
                self.assertPathContainsOrdered(path, waypoints)

    def test_history_route_visits_buddha_before_fangong_and_wuyin(self):
        response = self.client.get("/api/map/route/route_history")

        self.assertEqual(response.status_code, 200)
        route = response.get_json()
        self.assertEqual(route["stops"][-3:], ["灵山大佛", "灵山梵宫", "五印坛城"])

        ordered_names = [point["name"] for point in route["points"]]
        self.assertLess(ordered_names.index("灵山大佛"), ordered_names.index("灵山梵宫"))
        self.assertLess(ordered_names.index("灵山梵宫"), ordered_names.index("五印坛城"))

    def test_history_route_problem_segments_keep_dense_controlled_road_anchors(self):
        response = self.client.get("/api/map/route/route_history")

        self.assertEqual(response.status_code, 200)
        path = response.get_json()["walk_polyline"]
        rounded_path = [[round(item[0], 6), round(item[1], 6)] for item in path]

        checks = [
            (
                [120.101198, 31.423203],
                [120.099922, 31.424501],
                [
                    [120.100820, 31.423802],
                    [120.100508, 31.424288],
                    [120.100391, 31.424510],
                    [120.100260, 31.424488],
                    [120.100009, 31.424466],
                ],
            ),
            (
                [120.099922, 31.424501],
                [120.098650, 31.426992],
                [
                    [120.099549, 31.424970],
                    [120.099813, 31.425456],
                    [120.099635, 31.426016],
                    [120.099301, 31.426506],
                    [120.098932, 31.426597],
                ],
            ),
            (
                [120.098468, 31.427413],
                [120.096493, 31.430161],
                [
                    [120.098194, 31.427691],
                    [120.097817, 31.428303],
                    [120.097218, 31.428963],
                    [120.096680, 31.429826],
                ],
            ),
            (
                [120.096493, 31.430161],
                [120.102491, 31.427799],
                [
                    [120.097817, 31.428303],
                    [120.098194, 31.427691],
                    [120.098646, 31.426992],
                    [120.099501, 31.427014],
                    [120.100100, 31.426181],
                    [120.101862, 31.426484],
                    [120.102600, 31.426593],
                ],
            ),
            (
                [120.102491, 31.427799],
                [120.103073, 31.424501],
                [
                    [120.102457, 31.427361],
                    [120.102600, 31.426597],
                    [120.101467, 31.425903],
                    [120.101949, 31.425208],
                    [120.102253, 31.424757],
                    [120.102604, 31.424800],
                ],
            ),
        ]

        for start, end, required in checks:
            start = [round(start[0], 6), round(start[1], 6)]
            end = [round(end[0], 6), round(end[1], 6)]
            with self.subTest(start=start, end=end):
                self.assertIn(start, rounded_path)
                self.assertIn(end, rounded_path)
                segment = rounded_path[rounded_path.index(start):rounded_path.index(end) + 1]
                self.assertGreaterEqual(len(segment), len(required) + 2)
                for waypoint in required:
                    self.assertIn([round(waypoint[0], 6), round(waypoint[1], 6)], segment)

    def test_nature_route_garden_to_jingshe_uses_current_controlled_roads(self):
        response = self.client.get("/api/map/route/route_nature")

        self.assertEqual(response.status_code, 200)
        path = response.get_json()["walk_polyline"]
        rounded_path = [[round(item[0], 6), round(item[1], 6)] for item in path]
        garden_road = [round(120.098077, 6), round(31.424293, 6)]
        jingshe_road = [round(120.100751, 6), round(31.426306, 6)]
        self.assertIn(garden_road, rounded_path)
        self.assertIn(jingshe_road, rounded_path)
        segment = rounded_path[rounded_path.index(garden_road):rounded_path.index(jingshe_road) + 1]

        expected_waypoints = [
            [round(120.098342, 6), round(31.424410, 6)],
            [round(120.098824, 6), round(31.424674, 6)],
            [round(120.098776, 6), round(31.425365, 6)],
            [round(120.099631, 6), round(31.426016, 6)],
            [round(120.100556, 6), round(31.426228, 6)],
        ]
        forbidden_direct_edges = [
            ([round(120.097978, 6), round(31.424361, 6)], [round(120.100350, 6), round(31.425120, 6)]),
            ([round(120.099984, 6), round(31.424601, 6)], [round(120.100350, 6), round(31.425120, 6)]),
        ]
        for waypoint in expected_waypoints:
            with self.subTest(waypoint=waypoint):
                self.assertIn(waypoint, segment)
        actual_edges = list(zip(rounded_path, rounded_path[1:]))
        for edge in forbidden_direct_edges:
            with self.subTest(edge=edge):
                self.assertNotIn(edge, actual_edges)

    def test_core_scenic_coordinates_are_calibrated_to_amap_poi_positions(self):
        response = self.client.get("/api/map/scenics")

        self.assertEqual(response.status_code, 200)
        points = {point["name"]: point for point in response.get_json()["points"]}
        expected = {
            "灵山大照壁": (120.102499, 31.421388),
            "五明桥": (120.102050, 31.422040),
            "九龙灌浴": (120.099984, 31.424601),
            "天下第一掌": (120.098781, 31.427066),
            "灵山大佛": (120.096477, 31.430194),
            "灵山梵宫": (120.102420, 31.428218),
            "五印坛城": (120.103054, 31.424676),
        }
        old_points = {
            "灵山大照壁": (120.0908, 31.4243),
            "五明桥": (120.0916, 31.4239),
            "九龙灌浴": (120.0945, 31.4222),
            "灵山大佛": (120.0982, 31.4204),
            "五印坛城": (120.0931, 31.4188),
        }
        for name, (lng, lat) in expected.items():
            with self.subTest(name=name):
                self.assertIn(name, points)
                self.assertAlmostEqual(points[name]["lng"], lng, places=4)
                self.assertAlmostEqual(points[name]["lat"], lat, places=4)
                self.assertGreaterEqual(points[name]["lng"], 120.088)
                self.assertLessEqual(points[name]["lng"], 120.106)
                self.assertGreaterEqual(points[name]["lat"], 31.417)
                self.assertLessEqual(points[name]["lat"], 31.431)
        for name, old_coord in old_points.items():
            with self.subTest(old_name=name):
                coord = (points[name]["lng"], points[name]["lat"])
                self.assertNotEqual(coord, old_coord)

    def test_chat_route_suggestion_includes_map_payload(self):
        response = self.client.post(
            "/api/chat",
            json={"query": "我带孩子玩四小时，请推荐路线", "history": [], "interest": "亲子家庭"},
        )

        self.assertEqual(response.status_code, 200)
        route = response.get_json()["route_suggestion"]
        self.assertEqual(route["id"], "route_family")
        self.assertIn("map", route)
        self.assertEqual(route["map"]["id"], "route_family")
        self.assertGreaterEqual(len(route["map"]["points"]), 5)

    def test_ip_location_tool_is_removed_and_weather_reports_missing_key(self):
        with mock.patch.dict(os.environ, {"AMAP_WEB_SERVICE_KEY": "", "AMAP_JS_KEY": ""}, clear=False):
            ip_response = self.client.get("/api/map/tools/ip-location")
            weather_response = self.client.get("/api/map/tools/weather?city=无锡市")

        self.assertEqual(ip_response.status_code, 404)
        self.assertEqual(weather_response.status_code, 503)
        self.assertIn("未配置高德 Web 服务 Key", weather_response.get_json()["error"])

    def test_weather_tool_calls_amap_rest_api_directly_without_ip_location(self):
        def fake_urlopen(request, timeout=0):
            url = request.full_url
            if "/v3/weather/weatherInfo" in url:
                payload = {
                    "status": "1",
                    "info": "OK",
                    "lives": [
                        {
                            "province": "江苏省",
                            "city": "无锡市",
                            "adcode": "320200",
                            "weather": "晴",
                            "temperature": "28",
                            "winddirection": "东南",
                            "windpower": "≤3",
                            "humidity": "60",
                            "reporttime": "2026-06-22 12:00:00",
                        }
                    ],
                }
            else:
                raise AssertionError("unexpected url: {0}".format(url))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(payload, ensure_ascii=False).encode("utf-8")

            return Response()

        with mock.patch.dict(os.environ, {"AMAP_WEB_SERVICE_KEY": "demo-web-key"}, clear=False):
            with mock.patch("amap_service.urlopen", side_effect=fake_urlopen):
                ip_response = self.client.get("/api/map/tools/ip-location")
                weather_response = self.client.get("/api/map/tools/weather?city=无锡市")

        self.assertEqual(ip_response.status_code, 404)
        self.assertEqual(weather_response.status_code, 200)
        self.assertEqual(weather_response.get_json()["provider"], "amap_web_service")
        self.assertIn("晴", weather_response.get_json()["summary"])


if __name__ == "__main__":
    unittest.main()
