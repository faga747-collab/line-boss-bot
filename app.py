import os
from flask import Flask, request, abort
import psycopg2
from psycopg2.extras import RealDictCursor

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ===== LINE 設定 =====
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ===== 資料庫連線（關鍵穩定版）=====
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",   # ✅ Supabase 必要
        connect_timeout=10   # ✅ 避免卡死
    )

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id TEXT UNIQUE
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("DB OK")
    except Exception as e:
        print("DB ERROR:", e)

init_db()

# ===== Webhook =====
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# ===== 訊息處理 =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text

    try:
        conn = get_db()
        cur = conn.cursor()

        # 存 user
        cur.execute(
            "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING;",
            (user_id,)
        )
        conn.commit()

        reply = f"你說：{text}"

        cur.close()
        conn.close()

    except Exception as e:
        reply = "資料庫錯誤"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

# ===== Render 必備 =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
