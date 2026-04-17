from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import sqlite3
from datetime import datetime, timedelta
import pytz
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

tz = pytz.timezone("Asia/Taipei")

conn = sqlite3.connect("boss.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL;")
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
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ 簽名錯誤")
        abort(400)
    except Exception as e:
        print("🔥 錯誤:", e)
        return 'OK'

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    parts = msg.split()
    now = datetime.now(tz)

    reply = None

    # 📖 指令
    if msg.lower() in ["查詢", "help"]:
        reply = """📖 指令

查詢
出
時間 王名 備註
6666 王名 備註
!open 開服時間
!add 王名 分鐘 別名
!edit 王名 分鐘
!del 王名
"""

    # 📋 查詢（🔥 時間排序）
    elif msg == "出":
        cursor.execute("SELECT * FROM bosses")
        rows = cursor.fetchall()

        boss_list = []

        for boss, respawn, last_kill, note in rows:
            next_time = None
            count = 0

            if last_kill:
                last_time = datetime.strptime(last_kill, "%Y-%m-%d %H:%M:%S")
                last_time = tz.localize(last_time)

                diff = (now - last_time).total_seconds()
                count = int(diff // respawn)

                if count < 0:
                    count = 0

                next_time = last_time + timedelta(seconds=(count + 1) * respawn)

            boss_list.append((boss, respawn, last_kill, note, next_time, count))

        # 🔥 只照時間排序
        boss_list.sort(key=lambda x: (x[4] is None, x[4]))

        reply = "📋 王表\n時間　　 王名稱\n----------------\n"

        for boss, respawn, last_kill, note, next_time, count in boss_list:
            note_text = f"｜{note}" if note else ""

            if next_time:
                time_str = next_time.strftime("%H:%M:%S")

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

            cursor.execute("UPDATE bosses SET last_kill=?, note=NULL", (full_time,))
            conn.commit()

            reply = f"🟢 開服時間 {time_str}"
        else:
            reply = "❌ 時間格式錯誤"

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
        reply = f"✅ 新增 {boss}（{minutes}分）"

    # ✏️ 修改
    elif msg.lower().startswith("!edit") and len(parts) == 3:
        boss = get_boss_id(parts[1])

        if boss:
            minutes = int(parts[2])
            respawn = minutes * 60

            cursor.execute(
                "UPDATE bosses SET respawn=? WHERE id=?",
                (respawn, boss)
            )
            conn.commit()

            reply = f"✏️ 修改 {boss} → {minutes}分"
        else:
            reply = "❌ 找不到王"

    # ❌ 刪除
    elif msg.lower().startswith("!del") and len(parts) == 2:
        boss = get_boss_id(parts[1])

        if boss:
            cursor.execute("DELETE FROM bosses WHERE id=?", (boss,))
            cursor.execute("DELETE FROM aliases WHERE boss_id=?", (boss,))
            conn.commit()

            reply = f"🗑 刪除 {boss}"
        else:
            reply = "❌ 找不到王"

    # 💀 即時死亡
    elif parts and parts[0] == "6666" and len(parts) >= 2:
        boss = get_boss_id(parts[1])

        if boss:
            note = " ".join(parts[2:]) if len(parts) > 2 else ""
            now_time = now.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE bosses SET last_kill=?, note=? WHERE id=?",
                (now_time, note, boss)
            )
            conn.commit()

            reply = f"💀 {boss} 已記錄｜{note}"
        else:
            reply = "❌ 找不到王"

    # ⏱ 手動時間
    elif any(parse_time(p) for p in parts):
        boss = None
        time_str = None
        note_parts = []

        for p in parts:
            if parse_time(p):
                time_str = parse_time(p)
            else:
                b = get_boss_id(p)
                if b:
                    boss = b
                else:
                    note_parts.append(p)

        if boss and time_str:
            note = " ".join(note_parts)

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
                "UPDATE bosses SET last_kill=?, note=? WHERE id=?",
                (full_time, note, boss)
            )
            conn.commit()

            reply = f"💀 {boss} 已記錄 {time_str}｜{note}"
        else:
            reply = "❌ 格式錯誤或找不到王"

    # 🔕 回覆
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
