from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from datetime import datetime, timedelta
import pytz
import sqlite3

app = Flask(__name__)

import os

line_bot_api = LineBotApi(os.getenv('YOUR_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('YOUR_CHANNEL_SECRET'))

tz = pytz.timezone('Asia/Taipei')

# 📦 資料庫
conn = sqlite3.connect('boss.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS bosses (
    id TEXT PRIMARY KEY,
    respawn INTEGER,
    last_kill TEXT
)
''')
conn.commit()


def record_kill(boss_id, kill_time):
    cursor.execute(
        "UPDATE bosses SET last_kill=? WHERE id=?",
        (kill_time.isoformat(), boss_id)
    )
    conn.commit()


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    now = datetime.now(tz)

    # ⚙️ 設定王
    if msg.startswith("設定"):
        try:
            _, boss_id, minutes = msg.split()

            cursor.execute(
                "REPLACE INTO bosses (id, respawn, last_kill) VALUES (?, ?, COALESCE((SELECT last_kill FROM bosses WHERE id=?), NULL))",
                (boss_id, int(minutes), boss_id)
            )
            conn.commit()

            reply = f"{boss_id} 已設定 ⏱ {minutes} 分鐘"

        except:
            reply = "格式：設定 王ID 分鐘"

    # 📋 列表
    elif msg == "出":
        cursor.execute("SELECT id, respawn, last_kill FROM bosses")
        rows = cursor.fetchall()

        if not rows:
            reply = "沒有任何王"
        else:
            result = []

            for boss_id, respawn, last_kill in rows:
                if last_kill:
                    last = datetime.fromisoformat(last_kill)
                    respawn_time = last + timedelta(minutes=respawn)
                    remaining = respawn_time - now

                    if remaining.total_seconds() <= 0:
                        status = "已重生🔥"
                    else:
                        mins = int(remaining.total_seconds() // 60)
                        status = f"{mins}分"
                else:
                    status = "未記錄"

                result.append(f"{boss_id}｜{status}")

            reply = "📋 王表\n" + "\n".join(result)

    # 💀 現在死亡
    elif msg.startswith("6666"):
        try:
            _, boss_id = msg.split()

            cursor.execute("SELECT id FROM bosses WHERE id=?", (boss_id,))
            if not cursor.fetchone():
                reply = "此王尚未設定"
            else:
                record_kill(boss_id, now)
                reply = f"{boss_id} 已記錄 💀（現在）"
        except:
            reply = "格式：6666 王ID"

    # ⏱ 手動時間
    elif ":" in msg:
        try:
            time_part, boss_id = msg.split()

            cursor.execute("SELECT id FROM bosses WHERE id=?", (boss_id,))
            if not cursor.fetchone():
                reply = "此王尚未設定"
            else:
                kill_time = datetime.strptime(time_part, "%H:%M")
                kill_time = tz.localize(kill_time.replace(
                    year=now.year,
                    month=now.month,
                    day=now.day
                ))

                record_kill(boss_id, kill_time)
                reply = f"{boss_id} 已記錄 💀（{time_part}）"
        except:
            reply = "格式：HH:MM 王ID"

    else:
        return  # 不回應其他訊息

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run(port=5000)