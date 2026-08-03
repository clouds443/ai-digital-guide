# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import main  # noqa: E402


class AuthFallbackContractTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    class _Cursor:
        def __init__(self, existing_user=None):
            self.existing_user = existing_user
            self.queries = []
            self.inserted = None
            self.lastrowid = 42

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            self.queries.append((query, params))
            if "INSERT INTO users" in query:
                self.inserted = params

        def fetchone(self):
            if self.queries and "SELECT id FROM users WHERE username" in self.queries[-1][0]:
                return self.existing_user
            return None

    class _Connection:
        def __init__(self, cursor):
            self.cursor_obj = cursor
            self.closed = False

        def cursor(self):
            return self.cursor_obj

        def close(self):
            self.closed = True

    def test_demo_admin_can_login_and_access_admin_config_when_mysql_is_down(self):
        with mock.patch("auth_service.get_connection", side_effect=RuntimeError("mysql down")):
            with mock.patch.dict(os.environ, {"AUTH_DEMO_FALLBACK": "1"}, clear=False):
                login_response = self.client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "admin123456", "role": "admin"},
                )

        self.assertEqual(login_response.status_code, 200)
        data = login_response.get_json()
        self.assertEqual(data["auth_mode"], "demo_fallback")
        self.assertEqual(data["user"]["role"], "admin")

        config_response = self.client.get(
            "/api/admin/config",
            headers={"Authorization": "Bearer " + data["token"]},
        )

        self.assertEqual(config_response.status_code, 200)
        self.assertIn("name", config_response.get_json())

    def test_demo_fallback_rejects_wrong_password_when_mysql_is_down(self):
        with mock.patch("auth_service.get_connection", side_effect=RuntimeError("mysql down")):
            with mock.patch.dict(os.environ, {"AUTH_DEMO_FALLBACK": "1"}, clear=False):
                response = self.client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "wrong-password", "role": "admin"},
                )

        self.assertEqual(response.status_code, 401)
        self.assertIn("账号或密码错误", response.get_json()["error"])

    def test_demo_fallback_can_be_disabled_for_strict_mysql_auth(self):
        with mock.patch("auth_service.get_connection", side_effect=RuntimeError("mysql down")):
            with mock.patch.dict(os.environ, {"AUTH_DEMO_FALLBACK": "0"}, clear=False):
                response = self.client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "admin123456", "role": "admin"},
                )

        self.assertEqual(response.status_code, 401)
        self.assertIn("数据库连接失败", response.get_json()["error"])

    def test_health_exposes_demo_auth_fallback_state(self):
        with mock.patch("main.check_auth_db", return_value=False):
            with mock.patch.dict(os.environ, {"AUTH_DEMO_FALLBACK": "1"}, clear=False):
                response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["mysql_configured"])
        self.assertTrue(data["auth_demo_fallback_enabled"])

    def test_register_creates_normal_user_and_returns_session_when_mysql_is_available(self):
        cursor = self._Cursor()
        connection = self._Connection(cursor)
        with mock.patch("auth_service.get_connection", return_value=connection):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "username": "visitor001",
                    "password": "visitor123",
                    "display_name": "新游客",
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["auth_mode"], "mysql")
        self.assertEqual(data["user"]["username"], "visitor001")
        self.assertEqual(data["user"]["role"], "user")
        self.assertEqual(data["user"]["display_name"], "新游客")
        self.assertTrue(data["token"])
        self.assertEqual(cursor.inserted[0], "visitor001")
        self.assertEqual(cursor.inserted[3], "user")
        self.assertTrue(connection.closed)

    def test_register_rejects_duplicate_username(self):
        cursor = self._Cursor(existing_user={"id": 7})
        with mock.patch("auth_service.get_connection", return_value=self._Connection(cursor)):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "username": "visitor001",
                    "password": "visitor123",
                    "display_name": "重复游客",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("账号已存在", response.get_json()["error"])

    def test_register_rejects_admin_self_registration(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "username": "newadmin",
                "password": "admin123456",
                "display_name": "新管理员",
                "role": "admin",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持管理员自助注册", response.get_json()["error"])

    def test_register_returns_friendly_unavailable_when_mysql_is_down(self):
        with mock.patch("auth_service.get_connection", side_effect=RuntimeError("mysql down")):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "username": "visitor001",
                    "password": "visitor123",
                    "display_name": "新游客",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("注册暂不可用，请使用演示账号登录", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
