from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import sqlite3
from datetime import datetime, timedelta
import pytz
import os
import random

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

# ======================
# DB
# ======================
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS player_stats (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    kills INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    max_streak INTEGER DEFAULT 0,
    last_kill_time TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS achievements (
    user_id TEXT,
    achievement TEXT,
    PRIMARY KEY (user_id, achievement)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS personalities (
    user_id TEXT PRIMARY KEY,
    type TEXT
)
""")

conn.commit()

# ======================
# 預設王
# ======================
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

# ======================
# alias（已刪掉 鳥）
# ======================
default_aliases = [
    ("861", "86下飛龍"), ("862", "86上飛龍"), ("6", "巨大蜈蚣"),
    ("76", "76四色", "四色"), ("45", "伊佛利特", "EF"),
    ("54", "54綠王", "綠"), ("55", "55紅王", "紅"),
    ("863", "大黑老", "大黑"), ("83", "83飛龍"), ("85", "85飛龍"),
    ("51", "51鱷魚", "鱷魚"), ("32", "32強盜", "強盜"),
    ("231", "231樹精", "樹"), ("304", "賽尼斯"),
    ("69", "69大腳", "大腳"),
    ("57", "57奈克"), ("39", "39蜘蛛"), ("5", "05死騎"),
    ("23", "23烏勒"), ("81", "81貝里斯"),
    ("82", "巨大飛龍"), ("7", "象7"),
    ("29", "29螞蟻"), ("狼", "狼王"), ("卡", "卡王"),
    ("61", "變怪王", "變怪"),
    ("78", "78古巨", "古巨"), ("12", "12克特", "克特"),
]

# ======================
# 安全寫入 alias（修正重點）
# ======================
for row in default_aliases:
    boss = row[1]
    for alias in row:
        cursor.execute(
            "INSERT OR IGNORE INTO aliases VALUES (?, ?)",
            (alias, boss)
        )

for boss, respawn in default_bosses:
    cursor.execute(
        "INSERT OR IGNORE INTO bosses VALUES (?, ?, NULL, NULL)",
        (boss, respawn)
    )

conn.commit()

# ======================
# boss 查詢（穩定版）
# ======================
def get_boss_id(name):
    cursor.execute("SELECT boss_id FROM aliases WHERE alias=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT boss_id FROM aliases WHERE alias LIKE ?", (f"%{name}%",))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT id FROM bosses WHERE id=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    return None

def parse_time(text):
    if text.isdigit():
        if len(text) == 6:
            return f"{text[:2]}:{text[2:4]}:{text[4:]}"
        elif len(text) == 4:
            return f"{text[:2]}:{text[2:4]}:00"
    return None

# ======================
# webhook
# ======================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# ======================
# 主邏輯（保留你原本 + MVP）
# ======================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    msg = event.message.text.strip()
    parts = msg.split()
    now = datetime.now(tz)

    reply = None

    # ======================
    # 6666
    # ======================
    if parts and parts[0] == "6666" and len(parts) >= 2:

        boss = get_boss_id(parts[1])

        if not boss:
            reply = "❌ 找不到王"
        else:
            note = " ".join(parts[2:]) if len(parts) > 2 else ""
            now_time = now.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE bosses SET last_kill=?, note=? WHERE id=?",
                (now_time, note, boss)
            )
            conn.commit()

            reply = f"💀 {boss} 已記錄｜{note}"

    # ======================
    # reply
    # ======================
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
