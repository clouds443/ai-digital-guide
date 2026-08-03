# -*- coding: utf-8 -*-
import hashlib
import hmac
import os
import secrets
import time
from functools import wraps

import pymysql
from flask import jsonify, request


SESSIONS = {}
SESSION_TTL_SECONDS = 8 * 60 * 60
DEMO_USERS = {
    "user": {
        "id": "demo-user",
        "username": "user",
        "password": "user123456",
        "role": "user",
        "display_name": "普通游客",
    },
    "admin": {
        "id": "demo-admin",
        "username": "admin",
        "password": "admin123456",
        "role": "admin",
        "display_name": "管理员",
    },
}


def get_mysql_config():
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "123456"),
        "database": os.getenv("MYSQL_DATABASE", "aidigitalhuman"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def _server_config():
    config = get_mysql_config()
    config.pop("database", None)
    return config


def get_connection(with_db=True):
    config = get_mysql_config() if with_db else _server_config()
    return pymysql.connect(**config)


def is_demo_auth_fallback_enabled():
    value = (os.getenv("AUTH_DEMO_FALLBACK", "1") or "").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        (password or "").encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return salt, digest


def verify_password(password, salt, password_hash):
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash or "")


def init_auth_db():
    config = get_mysql_config()
    database = config["database"]
    try:
        conn = get_connection(with_db=False)
        with conn.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS `{0}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci".format(database)
            )
        conn.close()

        conn = get_connection(with_db=True)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(64) NOT NULL UNIQUE,
                    password_hash VARCHAR(128) NOT NULL,
                    salt VARCHAR(64) NOT NULL,
                    role ENUM('user','admin') NOT NULL DEFAULT 'user',
                    display_name VARCHAR(64) NOT NULL,
                    status TINYINT NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    last_login_at DATETIME NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            _ensure_default_user(cursor, "user", "user123456", "user", "普通游客")
            _ensure_default_user(cursor, "admin", "admin123456", "admin", "管理员")
        conn.close()
        print("Auth MySQL ready: {0}@{1}:{2}/{3}".format(
            config["user"], config["host"], config["port"], database
        ))
        return True
    except Exception as exc:
        print("Auth MySQL init failed: {0}".format(exc))
        return False


def check_auth_db():
    try:
        conn = get_connection(with_db=True)
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        conn.close()
        return True
    except Exception:
        return False


def _ensure_default_user(cursor, username, password, role, display_name):
    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    if cursor.fetchone():
        return
    salt, password_hash = hash_password(password)
    cursor.execute(
        """
        INSERT INTO users (username, password_hash, salt, role, display_name, status)
        VALUES (%s, %s, %s, %s, %s, 1)
        """,
        (username, password_hash, salt, role, display_name),
    )


def login_user(username, password, role):
    username = (username or "").strip()
    role = (role or "").strip()
    if role not in ("user", "admin"):
        return None, "登录身份不正确"
    if not username or not password:
        return None, "请输入账号和密码"

    try:
        conn = get_connection(with_db=True)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, password_hash, salt, role, display_name, status
                FROM users
                WHERE username=%s
                """,
                (username,),
            )
            user = cursor.fetchone()
            if not user or int(user.get("status", 0)) != 1:
                return None, "账号不存在或已停用"
            if user["role"] != role:
                return None, "账号身份与所选登录身份不匹配"
            if not verify_password(password, user["salt"], user["password_hash"]):
                return None, "账号或密码错误"

            cursor.execute(
                "UPDATE users SET last_login_at=NOW() WHERE id=%s",
                (user["id"],),
            )
        conn.close()
    except Exception as exc:
        print("Login failed: {0}".format(exc))
        if is_demo_auth_fallback_enabled():
            return _login_demo_user(username, password, role)
        return None, "数据库连接失败，请检查 MySQL 配置"

    safe_user = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
    }
    result = _create_session(safe_user)
    result["auth_mode"] = "mysql"
    return result, ""


def register_user(username, password, display_name=None, role=None):
    username = (username or "").strip()
    password = password or ""
    display_name = (display_name or "").strip() or username
    role = (role or "user").strip()
    if role != "user":
        return None, "不支持管理员自助注册", 400
    if not username:
        return None, "请输入账号", 400
    if len(username) > 64:
        return None, "账号长度不能超过 64 个字符", 400
    if len(password) < 6:
        return None, "密码长度至少 6 位", 400
    if len(display_name) > 64:
        display_name = display_name[:64]

    conn = None
    try:
        conn = get_connection(with_db=True)
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                return None, "账号已存在，请直接登录", 409
            salt, password_hash = hash_password(password)
            cursor.execute(
                """
                INSERT INTO users (username, password_hash, salt, role, display_name, status)
                VALUES (%s, %s, %s, %s, %s, 1)
                """,
                (username, password_hash, salt, "user", display_name),
            )
            user_id = getattr(cursor, "lastrowid", None) or username
    except Exception as exc:
        print("Register failed: {0}".format(exc))
        return None, "注册暂不可用，请使用演示账号登录", 503
    finally:
        if conn:
            conn.close()

    safe_user = {
        "id": user_id,
        "username": username,
        "role": "user",
        "display_name": display_name,
    }
    result = _create_session(safe_user)
    result["auth_mode"] = "mysql"
    return result, "", 200


def _login_demo_user(username, password, role):
    demo = DEMO_USERS.get(role)
    if not demo or username != demo["username"]:
        return None, "账号不存在或已停用"
    if password != demo["password"]:
        return None, "账号或密码错误"
    safe_user = {
        "id": demo["id"],
        "username": demo["username"],
        "role": demo["role"],
        "display_name": demo["display_name"],
    }
    result = _create_session(safe_user)
    result["auth_mode"] = "demo_fallback"
    return result, ""


def _create_session(safe_user):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"user": safe_user, "expires_at": time.time() + SESSION_TTL_SECONDS}
    return {"token": token, "user": safe_user}


def get_current_user():
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token:
        return None
    session = SESSIONS.get(token)
    if not session:
        return None
    if session["expires_at"] < time.time():
        SESSIONS.pop(token, None)
        return None
    session["expires_at"] = time.time() + SESSION_TTL_SECONDS
    return session["user"]


def require_role(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "请先登录"}), 401
            if roles and user.get("role") not in roles:
                return jsonify({"error": "当前账号无权限访问"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
