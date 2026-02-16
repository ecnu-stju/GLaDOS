import requests
import datetime
import random
import os
import time
from dotenv import load_dotenv

def translate_message(raw_message):
    if raw_message == "Please Try Tomorrow":
        return "签到失败，请明天再试 🤖"
    elif "Checkin! Got" in raw_message:
        points = raw_message.split("Got ")[1].split(" Points")[0]
        return f"签到成功，获得{points}积分 🎉"
    elif raw_message == "Checkin Repeats! Please Try Tomorrow":
        return "重复签到，请明天再试 🔁"
    else:
        return f"未知的签到结果: {raw_message} ❓"

def generate_headers(cookie):
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Linux; Android 10; zh-CN; SM-G9750) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.1 Safari/605.1.15",
    ]
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Authorization": "9876543210987654321098765432109-1234-567",
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie,
        "Origin": "https://glados.rocks",
        "Sec-Ch-Ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": random.choice(user_agents)
    }

def format_days(days_str):
    days = float(days_str)
    if days.is_integer():
        return str(int(days))
    return f"{days:.8f}".rstrip('0').rstrip('.')

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
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"发送 Telegram 消息失败: {e}")

def check_account_status(email, cookie, proxy):
    url = "https://glados.rocks/api/user/status"
    headers = generate_headers(cookie)
    try:
        response = requests.get(url, headers=headers, proxies=proxy, timeout=10)
        response.raise_for_status()
        data = response.json()
        left_days = format_days(data['data']['leftDays'])
        return f"<b>{email}</b>: 剩余 {left_days} 天 🗓️"
    except requests.RequestException as e:
        return f"<b>{email}</b>: 获取状态失败 - {str(e)} ❌"
    except (KeyError, ValueError) as e:
        return f"<b>{email}</b>: 解析响应失败 - {str(e)} ❌"

def sign(email, cookie, proxy):
    url = "https://glados.cloud/api/user/checkin"
    headers = generate_headers(cookie)
    data = {"token": "glados.one"}
    try:
        response = requests.post(url, headers=headers, json=data, proxies=proxy, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        raw_message = response_data.get("message", "")
        translated_message = translate_message(raw_message)
    except requests.RequestException as e:
        translated_message = f"请求失败: {e}"
    except ValueError:
        translated_message = f"解析响应失败: {response.text}"
    
    beijing_time = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    log_message = f"{beijing_time.strftime('%Y-%m-%d %H:%M')} {email}: {translated_message}"
    print(log_message)
    return f"<b>{email}</b>: {translated_message}"

def multi_account_sign():
    load_dotenv()
    bot_token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    proxy = {
        "http": os.getenv("HTTP_PROXY"),
        "https": os.getenv("HTTPS_PROXY")
    }

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
        print("未找到账号信息，请检查 .env 文件")
        return

    sign_messages = []
    status_messages = []
    for email, cookie in accounts:
        sign_result = sign(email, cookie, proxy)
        sign_messages.append(sign_result)
        status_result = check_account_status(email, cookie, proxy)
        status_messages.append(status_result)
        time.sleep(random.randint(5, 15))

    send_notification(sign_messages, status_messages, bot_token, chat_id)

if __name__ == "__main__":
    multi_account_sign()
