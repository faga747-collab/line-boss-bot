from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from datetime import datetime, timedelta
import pytz
import sqlite3

app = Flask(__name__)

import os

line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

print("TOKEN:", os.getenv("CHANNEL_ACCESS_TOKEN"))
print("SECRET:", os.getenv("CHANNEL_SECRET"))

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

    elif msg == "出":
    cursor.execute("SELECT id, respawn, last_kill FROM bosses")
    rows = cursor.fetchall()

    if not rows:
        reply = "沒有任何王"
    else:
        now_list = []      # 已重生30分鐘內
        future_list = []   # 未來

        for boss_id, respawn, last_kill in rows:
            if not last_kill:
                continue

            last = datetime.fromisoformat(last_kill)
            respawn_time = last + timedelta(minutes=respawn)

            diff = (now - respawn_time).total_seconds()

            # ✅ 已重生（30分鐘內）→ 顯示
            if 0 <= diff <= 1800:
                time_str = respawn_time.strftime("%H:%M")
                now_list.append((respawn_time, f"{time_str}  {boss_id}"))

            # ✅ 未來 → 顯示
            elif respawn_time > now:
                time_str = respawn_time.strftime("%H:%M")
                future_list.append((respawn_time, f"{time_str}  {boss_id}"))

            # ❌ 超過30分鐘 → 不顯示

        # 排序
        now_list.sort(key=lambda x: x[0])
        future_list.sort(key=lambda x: x[0])

        # 組輸出
        text = ["📋 王表", "時間    王名稱", "----------------"]

        # ⭐ 上面：剛重生
        for _, line in now_list:
            text.append(line)

        # ⭐ 下面：未來
        for _, line in future_list:
            text.append(line)

        reply = "\n".join(text)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
