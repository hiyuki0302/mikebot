import requests
from datetime import datetime

webhook_url = "https://discord.com/api/webhooks/1369503632650928148/lNMN5RzSRDTIYo2X4nTbMBlv4Rzg_HYR4PQY7shMnTnAhZv-xkbdVAdbI59JAslVa8cl"
webhook_url2 = "https://discord.com/api/webhooks/1392043445182398564/eeAtT9WHF3EYSurQn5k0DrGnHDt0TZxse3xZOjbT7quzN6du0aK2229JCipPTTKjK3ei"
webhook_url3 = "https://discord.com/api/webhooks/1394107484255555758/ZsB2rnwxXLOrv9kwZOc6yB8jl11lbZNNGs90apR3w6_EnwmqTyYuFst4Bgw4SnTrrVDS"

def entry_discord(result=None, symbol=None, qty=None, entry_price=None, take_profit=None, direction=None):
    now = datetime.now()
    color = 0x55efc4 if direction == "LONG" else 0xff7675  # 緑 or 赤

    title_emoji = "🟩" if direction == "LONG" else "🟥"
    result_msg = "✅OK" if result == "OK" else f"⚠️{result}"
    title = f"{title_emoji} {'ロング' if direction == 'LONG' else 'ショート'}エントリー通知"

    description = f"**{'新規ポジションが成立しました！' if direction == 'LONG' else 'ショートポジションが成立しました！'}**"

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [
            {"name": "注文結果",      "value": f"`{result_msg}`", "inline": True},
            {"name": "シンボル",      "value": f"`{symbol}`", "inline": True},
            {"name": "ロット数",      "value": f"`{qty}`", "inline": True},
            {"name": "エントリー価格", "value": f"`{entry_price}`", "inline": True},
            {"name": "利確",         "value": f"`{take_profit}`", "inline": True},
            {"name": "エントリー時刻", "value": f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", "inline": False},
        ],
        "footer": {"text": "powered by YOURBOT"},
    }

    payload = {"embeds": [embed]}
    response = requests.post(webhook_url2, json=payload)
    if response.status_code == 204:
        print("✅ Discord通知成功！")
    else:
        print(f"⚠️ Discord通知失敗: {response.status_code} - {response.text}")

def notify_discord(symbol=None, qty=None, entry_price=None, exit_price=None):
    now = datetime.now()
    now = now.strftime('%Y-%m-%d %H:%M:%S')
    embed = {
        "title": "⚠️ クローズ通知",
        "description": "⏰ ポジションが決済されました",
        "color": 0xfdcb6e,
        "fields": [
        {"name": "シンボル",      "value": f"`{symbol}`", "inline": True},
        {"name": "ロット数",      "value": f"`{qty}`", "inline": True},
        {"name": "建値",          "value": f"`{entry_price}`", "inline": True},
        {"name": "決済価格",      "value": f"`{exit_price}`", "inline": True},
        {"name": "クローズ時刻",  "value": f"`{now}`", "inline": False}
        ],
        "footer": {"text": "powered by YOURBOT"},
    }

    payload = {"embeds": [embed]}
    response = requests.post(webhook_url2, json=payload)
    if response.status_code == 204:
        print("✅ Discord通知成功！")
    else:
        print(f"⚠️ Discord通知失敗: {response.status_code} - {response.text}")

def notify_error_discord(subtitle=None, error_message=None):
    now = datetime.now()
    embed = {
        "title": "🚨 エラー通知",
        "description": f"```{subtitle}{error_message}```",
        "color": 0xe17055,
        "fields": [
            {"name": "発生時刻", "value": f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", "inline": False}
        ],
        "footer": {"text": "powered by YOURBOT"},
    }
    payload = {"embeds": [embed]}
    res = requests.post(webhook_url3, json=payload)
    if res.status_code == 204:
        print("✅ エラーDiscord通知成功")
    else:
        print(f"⚠️ エラーDiscord通知失敗: {res.status_code} - {res.text}")

def notify_dual_discord(msg):
    now = datetime.now()
    embed = {
        "title": msg,
        "color": 0xe17055,
        "fields": [
            {"name": "通知時刻", "value": f"`{now.strftime('%Y-%m-%d %H:%M:%S')}`", "inline": False}
        ],
        "footer": {"text": "powered by YOURBOT"},
    }
    payload = {"embeds": [embed]}
    res = requests.post(webhook_url, json=payload)
    if res.status_code == 204:
        print("処理通知完了")
    else:
        print(f"⚠️ エラーDiscord通知失敗: {res.status_code} - {res.text}")

if __name__ == '__main__':
    notify_dual_discord(msg="test")