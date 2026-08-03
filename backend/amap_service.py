# -*- coding: utf-8 -*-
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


def _amap_web_key():
    return (os.getenv("AMAP_WEB_SERVICE_KEY") or os.getenv("AMAP_JS_KEY") or "").strip()


def _missing_key(tool_name):
    return {
        "ok": False,
        "ready": False,
        "status": 503,
        "provider": "amap_web_service",
        "tool": tool_name,
        "error": "未配置高德 Web 服务 Key，请在 backend/.env 中设置 AMAP_WEB_SERVICE_KEY。",
    }


def _get_json(url, params, timeout=8):
    query = urlencode(params)
    request = Request("{0}?{1}".format(url, query), headers={"User-Agent": "AIhumannew/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _amap_error(data, tool_name):
    info = data.get("info") or data.get("infocode") or "高德 API 未返回成功状态。"
    return {
        "ok": False,
        "ready": True,
        "status": 502,
        "provider": "amap_web_service",
        "tool": tool_name,
        "error": "高德 API 调用失败：{0}".format(info),
        "raw": data,
    }


def weather(city):
    tool_name = "amap_weather"
    key = _amap_web_key()
    if not key:
        return _missing_key(tool_name)
    city = (city or "无锡市").strip() or "无锡市"
    params = {
        "key": key,
        "city": city,
        "extensions": "base",
        "output": "JSON",
    }
    try:
        data = _get_json(AMAP_WEATHER_URL, params)
    except Exception as exc:
        return {
            "ok": False,
            "ready": True,
            "status": 502,
            "provider": "amap_web_service",
            "tool": tool_name,
            "error": "高德天气调用失败：{0}".format(exc),
        }
    if str(data.get("status")) != "1":
        return _amap_error(data, tool_name)
    lives = data.get("lives") or []
    live = lives[0] if lives else {}
    summary = "天气：{city}{weather}，{temp}℃，{wind}风{power}级，湿度{humidity}%".format(
        city=live.get("city") or city,
        weather=live.get("weather") or "",
        temp=live.get("temperature") or "-",
        wind=live.get("winddirection") or "",
        power=live.get("windpower") or "-",
        humidity=live.get("humidity") or "-",
    )
    return {
        "ok": True,
        "ready": True,
        "status": 200,
        "provider": "amap_web_service",
        "tool": tool_name,
        "summary": summary,
        "data": data,
    }
