from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from datetime import datetime, timedelta
import pytz
import psycopg2
import os

app = Flask(__name__)

# LINE
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

tz = pytz.timezone('Asia/Taipei')

# 🟢 Supabase PostgreSQL
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()


# 📌 記錄死亡
def record_kill(boss_id, kill_time):
    cursor.execute(
        "UPDATE bosses SET last_kill=%s WHERE id=%s",
        (kill_time, boss_id)
    )
    conn.commit()


# 📌 取得 alias 對應 boss
def get_boss_id(name):
    cursor.execute("SELECT boss_id FROM aliases WHERE alias=%s", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return name  # 如果沒設定 alias 就當本名


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

            cursor.execute("""
                INSERT INTO bosses (id, respawn)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET respawn = EXCLUDED.respawn
            """, (boss_id, int(minutes)))

            conn.commit()
            reply = f"{boss_id} 已設定 ⏱ {minutes} 分鐘"

        except:
            reply = "格式：設定 王ID 分鐘"

    # 🔗 設定別名
    elif msg.startswith("別名"):
        try:
            _, alias, boss_id = msg.split()

            cursor.execute("""
                INSERT INTO aliases (alias, boss_id)
                VALUES (%s, %s)
                ON CONFLICT (alias) DO UPDATE SET boss_id = EXCLUDED.boss_id
            """, (alias, boss_id))

            conn.commit()
            reply = f"{alias} → {boss_id} 已設定"

        except:
            reply = "格式：別名 別名 王ID"

    # 📋 出王表（含秒）
    elif msg == "出":
        cursor.execute("SELECT id, respawn, last_kill FROM bosses")
        rows = cursor.fetchall()

        if not rows:
            reply = "沒有任何王"
        else:
            now_list = []
            future_list = []

            for boss_id, respawn, last_kill in rows:
                if not last_kill:
                    continue

                respawn_time = last_kill + timedelta(minutes=respawn)
                diff = (now - respawn_time).total_seconds()

                time_str = respawn_time.strftime("%H:%M:%S")

                if 0 <= diff <= 1800:
                    now_list.append((respawn_time, f"{time_str}  {boss_id}"))
                elif respawn_time > now:
                    future_list.append((respawn_time, f"{time_str}  {boss_id}"))

            now_list.sort()
            future_list.sort()

            text = ["📋 王表", "時間        王名稱", "----------------"]

            for _, line in now_list:
                text.append(line)
            for _, line in future_list:
                text.append(line)

            reply = "\n".join(text)

    # 💀 現在死亡
    elif msg.startswith("6666"):
        try:
            _, name = msg.split()
            boss_id = get_boss_id(name)

            cursor.execute("SELECT id FROM bosses WHERE id=%s", (boss_id,))
            if not cursor.fetchone():
                reply = "此王尚未設定"
            else:
                record_kill(boss_id, now)
                reply = f"{boss_id} 已記錄 💀（現在）"
        except:
            reply = "格式：6666 王ID"

    # ⏱ 手動時間（支援秒）
    elif len(msg.split()) == 2:
        try:
            time_part, name = msg.split()
            boss_id = get_boss_id(name)

            if not time_part.isdigit() or len(time_part) not in [4, 6]:
                return

            hour = int(time_part[:2])
            minute = int(time_part[2:4])
            second = int(time_part[4:6]) if len(time_part) == 6 else 0

            if hour > 23 or minute > 59 or second > 59:
                reply = "時間格式錯誤"
            else:
                cursor.execute("SELECT id FROM bosses WHERE id=%s", (boss_id,))
                if not cursor.fetchone():
                    reply = "此王尚未設定"
                else:
                    kill_time = datetime(
                        year=now.year,
                        month=now.month,
                        day=now.day,
                        hour=hour,
                        minute=minute,
                        second=second,
                        tzinfo=tz
                    )

                    record_kill(boss_id, kill_time)
                    reply = f"{boss_id} 已記錄 💀（{hour:02}:{minute:02}:{second:02}）"

        except:
            reply = "格式：2136 或 213645 王ID"

    else:
        return

    # ✅ 回覆
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
