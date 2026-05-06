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

# =========================
# 原本資料表（不動）
# =========================
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

# =========================
# ⭐ 新增系統（四大功能）
# =========================

# 👑 玩家統計
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

# 🎖 成就
cursor.execute("""
CREATE TABLE IF NOT EXISTS achievements (
    user_id TEXT,
    achievement TEXT,
    PRIMARY KEY (user_id, achievement)
)
""")

# 🎭 人格
cursor.execute("""
CREATE TABLE IF NOT EXISTS personalities (
    user_id TEXT PRIMARY KEY,
    type TEXT
)
""")

conn.commit()

# =========================
# 🎭 人格庫
# =========================
personality_types = {
    "normal": ["太猛了🔥", "穩到不行😎"],
    "troll": ["這隻是撿的吧😂", "又混到一隻😏"],
    "toxic": ["隊友在哭了🤣", "王：又是你😡"],
    "god": ["神降臨👑", "全服最強🔥"]
}

# =========================
# 工具
# =========================
def get_boss_id(name):
    cursor.execute("SELECT boss_id FROM aliases WHERE alias=?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("SELECT id FROM bosses WHERE id=?", (name,))
    row = cursor.fetchone()
    return row[0] if row else None


def parse_time(text):
    if text.isdigit():
        if len(text) == 6:
            return f"{text[:2]}:{text[2:4]}:{text[4:]}"
        elif len(text) == 4:
            return f"{text[:2]}:{text[2:4]}:00"
    return None

# =========================
# Webhook
# =========================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# =========================
# 主邏輯
# =========================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):

    msg = event.message.text.strip()
    parts = msg.split()
    now = datetime.now(tz)

    reply = None

    # =========================
    # 💀 6666 打王（核心升級）
    # =========================
    if parts and parts[0] == "6666" and len(parts) >= 2:

        boss = get_boss_id(parts[1])

        if boss:
            note = " ".join(parts[2:]) if len(parts) > 2 else ""
            now_time = now.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "UPDATE bosses SET last_kill=?, note=? WHERE id=?",
                (now_time, note, boss)
            )
            conn.commit()

            user_id = event.source.user_id

            try:
                profile = line_bot_api.get_profile(user_id)
                name = profile.display_name
            except:
                name = "某位大佬"

            # =========================
            # 👑 玩家資料
            # =========================
            cursor.execute("""
                SELECT kills, streak, max_streak, last_kill_time
                FROM player_stats WHERE user_id=?
            """, (user_id,))

            row = cursor.fetchone()
            now_dt = datetime.now()

            if row:
                kills, streak, max_streak, last_time = row

                if last_time:
                    last_dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")

                    if (now_dt - last_dt).total_seconds() <= 1800:
                        streak += 1
                    else:
                        streak = 1
                else:
                    streak = 1

                kills += 1
                max_streak = max(max_streak, streak)

                cursor.execute("""
                    UPDATE player_stats 
                    SET kills=?, streak=?, max_streak=?, last_kill_time=?, name=?
                    WHERE user_id=?
                """, (kills, streak, max_streak, now_time, name, user_id))

            else:
                kills = 1
                streak = 1
                max_streak = 1

                cursor.execute("""
                    INSERT INTO player_stats VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, name, kills, streak, max_streak, now_time))

            conn.commit()

            # =========================
            # 🎭 人格
            # =========================
            cursor.execute("SELECT type FROM personalities WHERE user_id=?", (user_id,))
            p = cursor.fetchone()

            if p:
                p_type = p[0]
            else:
                p_type = random.choice(list(personality_types.keys()))
                cursor.execute("INSERT OR IGNORE INTO personalities VALUES (?, ?)", (user_id, p_type))
                conn.commit()

            talk = random.choice(personality_types[p_type])

            # =========================
            # 👑 MVP
            # =========================
            cursor.execute("SELECT name, kills FROM player_stats ORDER BY kills DESC LIMIT 1")
            top = cursor.fetchone()

            mvp_text = ""
            if top and top[0] == name:
                mvp_text = "\n👑 MVP"

            # =========================
            # 🔥 連殺
            # =========================
            streak_text = ""
            if streak >= 2:
                streak_text = f"\n🔥 連殺 {streak}"

            # =========================
            # 🎖 成就
            # =========================
            achievement_text = ""

            if kills == 100:
                cursor.execute("INSERT OR IGNORE INTO achievements VALUES (?, ?)", (user_id, "百人斬"))
                achievement_text = "\n🎖 百人斬"

            if kills == 500:
                cursor.execute("INSERT OR IGNORE INTO achievements VALUES (?, ?)", (user_id, "屠城者"))
                achievement_text = "\n🎖 屠城者"

            conn.commit()

            # 💥 隨機暴擊
            if random.random() < 0.05:
                talk = "🔥🔥 傳說級操作 🔥🔥"

            reply = f"""💀 {boss} 已記錄｜{note}
🔥 {name} {talk}
📊 總擊殺：{kills}{mvp_text}{streak_text}{achievement_text}"""

        else:
            reply = "❌ 找不到王"

    # =========================
    # 回覆
    # =========================
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
