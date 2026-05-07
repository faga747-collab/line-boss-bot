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

# ===== 建表 =====
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

# ===== 預設王 =====
default_bosses = [
    ("86下飛龍", 120*60), ("86上飛龍", 120*60), ("巨大蜈蚣", 120*60),
    ("76四色", 120*60), ("伊佛利特", 120*60), ("54綠王", 120*60),
    ("55紅王", 120*60),

    ("大黑老", 180*60), ("83飛龍", 180*60), ("85飛龍", 180*60),
    ("51鱷魚", 180*60), ("32強盜", 180*60), ("231樹精", 180*60),
    ("賽尼斯", 180*60), ("69大腳", 180*60),

    ("57奈克", 240*60), ("39蜘蛛", 240*60), ("05死騎", 240*60),

    ("23烏勒", 360*60), ("81貝里斯", 360*60),
    ("巨大飛龍", 360*60), ("象7", 360*60),

    ("29螞蟻", 210*60), ("狼王", 480*60), ("卡王", 450*60),
    ("變怪王", 420*60), ("不死鳥", 480*60),
    ("78古巨", 510*60), ("12克特", 600*60),
]

# ===== 修正後 aliases =====
default_aliases = [
    ("861", "86下飛龍"), ("862", "86上飛龍"), ("6", "巨大蜈蚣"),

    ("76", "76四色"), ("四色", "76四色"),
    ("45", "伊佛利特"), ("EF", "伊佛利特"),
    ("54", "54綠王"), ("綠", "54綠王"),
    ("55", "55紅王"), ("紅", "55紅王"),

    ("863", "大黑老"), ("大黑", "大黑老"),
    ("83", "83飛龍"), ("85", "85飛龍"),

    ("51", "51鱷魚"), ("鱷魚", "51鱷魚"),
    ("32", "32強盜"), ("強盜", "32強盜"),

    ("231", "231樹精"), ("樹", "231樹精"),
    ("304", "賽尼斯"),

    ("69", "69大腳"), ("大腳", "69大腳"),

    ("57", "57奈克"),
    ("39", "39蜘蛛"),
    ("5", "05死騎"),

    ("23", "23烏勒"),
    ("81", "81貝里斯"),

    ("82", "巨大飛龍"),
    ("7", "象7"),

    ("29", "29螞蟻"),
    ("狼", "狼王"),
    ("卡", "卡王"),

    ("61", "變怪王"), ("變怪", "變怪王"),

    # ✅ 保留不死鳥
    ("鳥", "不死鳥"),

    ("78", "78古巨"), ("古巨", "78古巨"),
    ("12", "12克特"), ("克特", "12克特"),
]

# ===== 初始化資料 =====
for boss, respawn in default_bosses:
    cursor.execute(
        "INSERT OR IGNORE INTO bosses VALUES (?, ?, NULL, NULL)",
        (boss, respawn)
    )

for alias, boss in default_aliases:
    cursor.execute(
        "INSERT OR IGNORE INTO aliases VALUES (?, ?)",
        (alias, boss)
    )

conn.commit()

# ===== 強化查詢 =====
def get_boss_id(name):
    cursor.execute("SELECT boss_id FROM aliases WHERE alias=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT id FROM bosses WHERE id=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # 模糊搜尋
    cursor.execute("SELECT id FROM bosses WHERE id LIKE ?", (f"%{name}%",))
    row = cursor.fetchone()
    return row[0] if row else None

def parse_time(text):
    if text.isdigit():
        if len(text) == 6:
            return f"{text[:2]}:{text[2:4]}:{text[4:]}"
        elif len(text) == 4:
            return f"{text[:2]}:{text[2:4]}:00"
    return None

def parse_datetime(parts, now):
    try:
        if len(parts) == 2:
            time_str = parse_time(parts[1])
            if not time_str:
                return None

            t = datetime.strptime(time_str, "%H:%M:%S")
            return now.replace(hour=t.hour, minute=t.minute, second=t.second)

        elif len(parts) >= 3:
            date_part = parts[1]
            time_part = parse_time(parts[2])

            if not time_part:
                return None

            if "-" in date_part:
                d = datetime.strptime(date_part, "%Y-%m-%d")
            else:
                d = datetime.strptime(date_part, "%Y%m%d")

            t = datetime.strptime(time_part, "%H:%M:%S")

            return datetime(
                year=d.year,
                month=d.month,
                day=d.day,
                hour=t.hour,
                minute=t.minute,
                second=t.second
            )
    except:
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
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
!clear all 清除全部時間
"""

    elif msg.lower() == "!clear all":
        cursor.execute("UPDATE bosses SET last_kill=NULL, note=NULL")
        conn.commit()
        reply = "🧹 已清除所有王的時間"

    elif msg.lower() in ["出", "o"]:
        priority_bosses = ["不死鳥", "05死騎", "78古巨"]

        cursor.execute("SELECT * FROM bosses")
        rows = cursor.fetchall()

        boss_list = []
        overdue_30 = []

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

            if next_time:
                diff_sec = (now - next_time).total_seconds()

                if 0 < diff_sec <= 1800:
                    overdue_30.append((boss, respawn, last_kill, note, next_time, count))
                else:
                    boss_list.append((boss, respawn, last_kill, note, next_time, count))

        boss_list.sort(key=lambda x: (x[4] is None, x[4]))

        reply = "📋 王表\n時間　　 王名稱\n----------------\n"

        if overdue_30:
            overdue_30.sort(key=lambda x: x[4])

            for boss, respawn, last_kill, note, next_time, count in overdue_30:
                note_text = f"｜{note}" if note else ""
                time_str = next_time.strftime("%H:%M:%S")
                reply += f"🔴{time_str}　{boss}（過{count}）{note_text}\n"

            reply += "－－逾時30分鐘內未打－－\n"

        for boss, respawn, last_kill, note, next_time, count in boss_list:
            if not next_time:
                continue

            note_text = f"｜{note}" if note else ""
            time_str = next_time.strftime("%H:%M:%S")
            icon = "🔥" if boss in priority_bosses else "　"

            if count == 0:
                reply += f"{icon}{time_str}　{boss}{note_text}\n"
            else:
                reply += f"{icon}{time_str}　{boss}（過{count}）{note_text}\n"

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

    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
