from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import sqlite3
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = "gdsj6TwRFERmBblRf/HvzltxF96+hBJtHei+v5HgW91EQTcoh/sDtv7JZHd7Kk9XZB84ziADfThuaMJzB/I4/xUYS6b79qB9OjskQknw5Ncf1dQxRzJXnHInwY9aCZIIuu1IjfXEOdFWXP6fARJUngdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "fec2f3302c8532f6966618ffe12464c7"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

tz = pytz.timezone("Asia/Taipei")

conn = sqlite3.connect("boss.db", check_same_thread=False)
cursor = conn.cursor()

# 建表
cursor.execute("""
CREATE TABLE IF NOT EXISTS bosses (
    id TEXT PRIMARY KEY,
    respawn INTEGER,
    last_kill TEXT,
    note TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS aliases (
    alias TEXT PRIMARY KEY,
    boss_id TEXT
)
""")

conn.commit()

# 找王
def get_boss_id(name):
    cursor.execute("SELECT boss_id FROM aliases WHERE alias=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT id FROM bosses WHERE id=?", (name,))
    row = cursor.fetchone()
    return row[0] if row else None

# 解析時間
def parse_time(text):
    if text.isdigit():
        if len(text) == 6:
            return f"{text[:2]}:{text[2:4]}:{text[4:]}"
        elif len(text) == 4:
            return f"{text[:2]}:{text[2:4]}:00"
    return None

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
    parts = msg.split()
    now = datetime.now(tz)

    reply = None  # 🔥 預設不回

    # 📖 指令說明
    if msg.lower() in ["查詢", "help"]:
        reply = """📖 指令

查詢
出
0900 王名
6666 王名
!open 0900
!add 王名 分鐘 別名
!edit 王名 分鐘
!del 王名
!clear 王名 / all
"""

    # 📋 查詢
    elif msg == "出":
        cursor.execute("SELECT * FROM bosses")
        rows = cursor.fetchall()

        reply = "📋 王表\n時間　　 王名稱\n----------------\n"

        for boss, respawn, last_kill, note in rows:
            if last_kill:
                last_time = datetime.strptime(last_kill, "%Y-%m-%d %H:%M:%S")
                last_time = tz.localize(last_time)

                count = 0
                next_time = last_time + timedelta(seconds=respawn)

                while now > next_time:
                    count += 1
                    next_time += timedelta(seconds=respawn)

                time_str = next_time.strftime("%H:%M:%S")
                note_text = f"｜{note}" if note else ""

                if count == 0:
                    reply += f"{time_str}　{boss}{note_text}\n"
                else:
                    reply += f"{time_str}　{boss}（過{count}）{note_text}\n"
            else:
                reply += f"--:--:--　{boss}\n"

    # 🟢 開服
    elif msg.lower().startswith("!open") and len(parts) == 2:
        time_str = parse_time(parts[1])
        if time_str:
            input_time = datetime.strptime(time_str, "%H:%M:%S")
            input_time = now.replace(
                hour=input_time.hour,
                minute=input_time.minute,
                second=input_time.second
            )

            full_time = input_time.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE bosses SET last_kill=?, note=NULL",
                (full_time,)
            )
            conn.commit()

            reply = f"🟢 開服時間 {time_str}"

    # ➕ 新增
    elif msg.lower().startswith("!add") and len(parts) >= 3:
        boss = parts[1]
        minutes = int(parts[2])
        respawn = minutes * 60
        aliases = parts[3:]

        cursor.execute(
            "INSERT OR REPLACE INTO bosses VALUES (?, ?, NULL, NULL)",
            (boss, respawn)
        )

        for a in aliases:
            cursor.execute(
                "INSERT OR REPLACE INTO aliases VALUES (?, ?)",
                (a, boss)
            )

        conn.commit()
        reply = f"✅ 新增 {boss}"

    # ❌ 刪除
    elif msg.lower().startswith("!del") and len(parts) == 2:
        boss = get_boss_id(parts[1])
        if boss:
            cursor.execute("DELETE FROM bosses WHERE id=?", (boss,))
            cursor.execute("DELETE FROM aliases WHERE boss_id=?", (boss,))
            conn.commit()
            reply = f"🗑 刪除 {boss}"

    # 💀 即時死亡
    elif parts and parts[0] == "6666" and len(parts) >= 2:
        boss = get_boss_id(parts[1])
        if boss:
            now_time = now.strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE bosses SET last_kill=? WHERE id=?",
                (now_time, boss)
            )
            conn.commit()
            reply = f"💀 {boss} 已記錄"

    # ⏱ 手動時間（🔥 修正關鍵）
    elif any(parse_time(p) for p in parts):
        boss = None
        time_str = None

        for p in parts:
            if parse_time(p):
                time_str = parse_time(p)
            else:
                b = get_boss_id(p)
                if b:
                    boss = b

        if boss and time_str:
            input_time = datetime.strptime(time_str, "%H:%M:%S")
            input_time = now.replace(
                hour=input_time.hour,
                minute=input_time.minute,
                second=input_time.second
            )

            if input_time > now:
                input_time -= timedelta(days=1)

            full_time = input_time.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE bosses SET last_kill=? WHERE id=?",
                (full_time, boss)
            )
            conn.commit()

            reply = f"💀 {boss} 已記錄 {time_str}"

    # 🔥 沒命中 → 不回
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    app.run(port=5000)
