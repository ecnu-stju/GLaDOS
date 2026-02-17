import datetime
import json
import os
import random
import time

import requests

try:
    # Optional: for local .env usage (kept for backward compatibility)
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


# =========================
# LOCAL DEBUG (REMOVE BEFORE PUSHING TO GITHUB)
# Fill in secrets below, then set ENABLE_LOCAL_ENV_INJECTION = True
# =========================
ENABLE_LOCAL_ENV_INJECTION = False


# [GladosC CHANGE] Centralize and make endpoint configurable.
BASE_URL = os.getenv("GLADOS_BASE_URL", "https://glados.cloud").rstrip("/")
CHECKIN_URL = f"{BASE_URL}/api/user/checkin"
STATUS_URL = f"{BASE_URL}/api/user/status"

# [GladosC CHANGE] Align token with the glados.cloud workflow (override via env if needed).
TOKEN = os.getenv("GLADOS_TOKEN", "glados.cloud")

TIMEOUT = int(os.getenv("GLADOS_TIMEOUT", "10"))
DEBUG = os.getenv("GLADOS_DEBUG", "0") == "1"

# [GladosC CHANGE] Use a stable UA and consistent browser-like headers.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def debug_log(msg: str) -> None:
    if DEBUG:
        print(msg)


def safe_json(resp: requests.Response, ctx: str = ""):
    """Parse JSON with useful debug info when response isn't JSON."""
    try:
        return resp.json()
    except Exception as e:
        ct = resp.headers.get("Content-Type", "")
        head = (resp.text or "")[:200]
        debug_log(
            f"[DEBUG] {ctx} JSON decode failed: {e}; "
            f"status={resp.status_code}; url={resp.url}; ct={ct}; head={head!r}"
        )
        return None


def translate_message(raw_message: str, points=None) -> str:
    # Keep old messages compatible; make it slightly more tolerant.
    if raw_message == "Please Try Tomorrow":
        return "签到失败，请明天再试 🤖"

    msg_lower = (raw_message or "").lower()
    if "got" in msg_lower:
        if points is None:
            try:
                points = raw_message.split("Got ")[1].split(" Points")[0]
            except Exception:
                points = None
        if points is not None:
            return f"签到成功，获得{points}积分 🎉"
        return f"签到成功 🎉 ({raw_message})"

    if "repeat" in msg_lower or "already" in msg_lower:
        return "重复签到，请明天再试 🔁"

    if raw_message:
        return f"未知的签到结果: {raw_message} ❓"
    return "未知的签到结果: (empty message) ❓"


def generate_headers(cookie: str) -> dict:
    """Build headers aligned with the working checkin.py style."""
    # [GladosC CHANGE] Remove inconsistent/over-specified headers; add Referer/Origin.
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie,
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/console/checkin",
        "User-Agent": USER_AGENT,
    }


def format_days(days_str):
    days = float(days_str)
    if days.is_integer():
        return str(int(days))
    return f"{days:.8f}".rstrip("0").rstrip(".")


def send_notification(sign_messages, status_messages, bot_token, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    sign_text = "🔔 GLaDOS 签到结果:\n" + "\n".join(sign_messages)
    status_text = "\n⏳ GLaDOS 账号状态:\n" + "\n".join(status_messages)
    beijing_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    current_time = beijing_time.strftime("%Y-%m-%d %H:%M")
    text = f"🕒 当前时间: {current_time}\n\n{sign_text}\n{status_text}\n\n✅ 签到任务完成"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(url, data=data, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"发送 Telegram 消息失败: {e}")


def build_proxies():
    # [GladosC CHANGE] Avoid passing empty proxy strings.
    http = os.getenv("HTTP_PROXY") or ""
    https = os.getenv("HTTPS_PROXY") or ""
    proxies = {}
    if http:
        proxies["http"] = http
    if https:
        proxies["https"] = https
    return proxies or None


def check_account_status(email, cookie, proxy):
    headers = generate_headers(cookie)
    debug_log(f"[DEBUG] email/status -> {STATUS_URL}")
    try:
        response = requests.get(STATUS_URL, headers=headers, proxies=proxy, timeout=TIMEOUT)
    except requests.RequestException as e:
        return f"<b>{email}</b>: 获取状态失败 - {str(e)} ❌"

    data = safe_json(response, ctx=f"{email}/status")
    if not data:
        return f"<b>{email}</b>: 解析响应失败 - HTTP {response.status_code} ❌"

    try:
        left_days = format_days(data["data"]["leftDays"])
        return f"<b>{email}</b>: 剩余 {left_days} 天 🗓️"
    except Exception as e:
        return f"<b>{email}</b>: 解析响应失败 - {str(e)} ❌"


def sign(email, cookie, proxy):
    headers = generate_headers(cookie)
    payload = {"token": TOKEN}

    # [GladosC CHANGE] Add lightweight debug logs (no cookie content leakage).
    debug_log(
        f"[DEBUG] email/checkin -> {CHECKIN_URL} "
        f"origin={headers.get('Origin')} referer={headers.get('Referer')} "
        f"ua={headers.get('User-Agent')} cookie_len={len(cookie)}"
    )

    try:
        response = requests.post(
            CHECKIN_URL,
            headers=headers,
            data=json.dumps(payload),
            proxies=proxy,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        translated_message = f"请求失败: {e}"
        beijing_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
        log_message = f"{beijing_time.strftime('%Y-%m-%d %H:%M')} {email}: {translated_message}"
        print(log_message)
        return f"<b>{email}</b>: {translated_message}"

    debug_log(
        f"[DEBUG] email/checkin response status={response.status_code} "
        f"url={response.url} ct={response.headers.get('Content-Type', '')}"
    )

    response_data = safe_json(response, ctx=f"{email}/checkin")
    if not response_data:
        translated_message = f"解析响应失败: HTTP {response.status_code}"
    else:
        raw_message = response_data.get("message", "")
        translated_message = translate_message(raw_message, points=response_data.get("points"))

    beijing_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    log_message = f"{beijing_time.strftime('%Y-%m-%d %H:%M')} em: {translated_message}"
    print(log_message)
    return f"<b>{email}</b>: {translated_message}"


def multi_account_sign():
    if load_dotenv:
        load_dotenv()

    bot_token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    proxy = build_proxies()

    accounts = []
    i = 1
    while True:
        email = os.getenv(f"GLADOS_EMAIL_{i}")
        cookie = os.getenv(f"GLADOS_COOKIE_{i}")
        if not email or not cookie:
            break
        accounts.append((email, cookie))
        i += 1

    if not accounts:
        print("未找到账号信息，请检查环境变量或 .env 文件")
        return

    if not bot_token or not chat_id:
        print("未设置 TG_BOT_TOKEN / TG_CHAT_ID，将只在控制台输出，不发送 Telegram 通知")

    sign_messages = []
    status_messages = []
    for email, cookie in accounts:
        sign_result = sign(email, cookie, proxy)
        sign_messages.append(sign_result)
        status_result = check_account_status(email, cookie, proxy)
        status_messages.append(status_result)
        time.sleep(random.randint(5, 15))

    if bot_token and chat_id:
        send_notification(sign_messages, status_messages, bot_token, chat_id)


if __name__ == "__main__":
    multi_account_sign()

