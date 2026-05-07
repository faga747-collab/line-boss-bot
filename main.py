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

# ====== DB ======
conn = sqlite3.connect("boss.db", check_same_thread=False)
cursor = conn.cursor()

# 原本王表
cursor.execute("""
CREATE TABLE IF NOT EXISTS bosses (
    id TEXT PRIMARY KEY,
    last_kill TEXT,
    note TEXT
)
""")

# MVP表（新增）
cursor.execute("""
CREATE TABLE IF NOT EXISTS mvp (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    kills INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_kill TEXT
)
""")

conn.commit()

# ====== 王 & 別名 ======
boss_alias = {
    "鳥": "鳥",
    "78": "78古巨",
    "古巨": "78古巨",
    "死騎": "死騎",
    "05": "死騎",
    "5": "死騎"
}

def get_boss_id(text):
    return boss_alias.get(text, None)

# ====== 時間解析 ======
def parse_time(text):
    text = text.replace(":", "")
    if text.isdigit():
        if len(text) == 4:
            return f"{text[:2]}:{text[2:]}:00"
        elif len(text) == 6:
            return f"{text[:2]}:{text[2:4]}:{text[4:]}"
    return None

# ====== MVP稱號 ======
def get_title(kills):
    if kills >= 200:
        return "👑 神級玩家"
    elif kills >= 100:
        return "🥇 屠龍王"
    elif kills >= 50:
        return "🥈 王之獵手"
    elif kills >= 10:
        return "🥉 新手獵人"
    else:
        return "🐣 路過鄉民"

# ====== LINE ======
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

    tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz)

    reply = None

    # ====== 6666 記錄 ======
    if msg.startswith("6666"):
        if len(parts) < 2:
            reply = "❌ 請輸入王名"
        else:
            boss = get_boss_id(parts[1])
            note = " ".join(parts[2:]) if len(parts) > 2 else ""

            if boss:
                now_str = now.strftime("%Y-%m-%d %H:%M:%S")

                # 原本功能（不動）
                cursor.execute("""
                INSERT OR REPLACE INTO bosses (id, last_kill, note)
                VALUES (?, ?, ?)
                """, (boss, now_str, note))
                conn.commit()

                # ====== ⭐ MVP系統 ======
                user_id = event.source.user_id
                name = "玩家"

                try:
                    profile = line_bot_api.get_profile(user_id)
                    name = profile.display_name
                except:
                    pass

                cursor.execute("SELECT kills, streak, last_kill FROM mvp WHERE user_id=?", (user_id,))
                row = cursor.fetchone()

                if row:
                    kills, streak, last_time = row

                    if last_time:
                        last_time_dt = datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                        if (now - last_time_dt).total_seconds() <= 3600:
                            streak += 1
                        else:
                            streak = 1
                    else:
                        streak = 1

                    kills += 1

                    cursor.execute("""
                    UPDATE mvp SET kills=?, streak=?, last_kill=?, name=?
                    WHERE user_id=?
                    """, (kills, streak, now_str, name, user_id))

                else:
                    cursor.execute("""
                    INSERT INTO mvp (user_id, name, kills, streak, last_kill)
                    VALUES (?, ?, 1, 1, ?)
                    """, (user_id, name, now_str))

                conn.commit()

                reply = f"🔥 {boss} 已記錄\n時間：{now_str}\n備註：{note}"
            else:
                reply = "❌ 找不到王"

    # ====== 時間輸入 ======
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
            input_time = datetime.strptime(time_str, "%H:%M:%S")
            input_time = now.replace(
                hour=input_time.hour,
                minute=input_time.minute,
                second=input_time.second
            )

            if input_time > now:
                input_time -= timedelta(days=1)

            full_time = input_time.strftime("%Y-%m-%d %H:%M:%S")
            note = " ".join(note_parts)

            cursor.execute(
                "UPDATE bosses SET last_kill=?, note=? WHERE id=?",
                (full_time, note, boss)
            )
            conn.commit()

            reply = f"💀 {boss} 已記錄 {time_str}｜{note}"
        else:
            reply = "❌ 格式錯誤或找不到王"

    # ====== 排行榜 ======
    elif msg == "排行榜":
        cursor.execute("""
        SELECT name, kills FROM mvp
        ORDER BY kills DESC LIMIT 5
        """)
        rows = cursor.fetchall()

        if rows:
            text = "🏆 MVP排行榜\n"
            for i, r in enumerate(rows, start=1):
                text += f"{i}️⃣ {r[0]}｜{r[1]}隻｜{get_title(r[1])}\n"
            reply = text
        else:
            reply = "⚠️ 尚無資料"

    # ====== 查自己 ======
    elif msg == "我":
        user_id = event.source.user_id
        cursor.execute("SELECT name, kills, streak FROM mvp WHERE user_id=?", (user_id,))
        row = cursor.fetchone()

        if row:
            reply = f"""👤 {row[0]}
擊殺數：{row[1]}
連殺：🔥 {row[2]}
稱號：{get_title(row[1])}"""
        else:
            reply = "⚠️ 你還沒打過王"

    # ====== 查詢王 ======
    else:
        boss = get_boss_id(msg)
        if boss:
            cursor.execute("SELECT last_kill, note FROM bosses WHERE id=?", (boss,))
            row = cursor.fetchone()

            if row and row[0]:
                last_kill = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                diff = now - last_kill

                h, rem = divmod(diff.total_seconds(), 3600)
                m, s = divmod(rem, 60)

                reply = f"⏱ {boss}\n已過：{int(h)}時{int(m)}分{int(s)}秒\n備註：{row[1]}"
            else:
                reply = f"⚠️ {boss} 尚未記錄"

    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )

if __name__ == "__main__":
    app.run()
