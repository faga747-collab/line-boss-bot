from flask import Flask, request, abort
import os
import psycopg2

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage
from linebot.v3.webhook import WebhookHandler as WebhookHandlerV3
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage

app = Flask(__name__)

# ===== LINE 設定 =====
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ===== 資料庫（Supabase）=====
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

# ===== 建立資料表 =====
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boss (
            id SERIAL PRIMARY KEY,
            name TEXT,
            code TEXT,
            last_time TEXT
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

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
@handler.add_message()
def handle_message(event):
    user_msg = event.message.text

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # ===== 查詢 =====
        if user_msg == "查王":
            conn = get_db()
            cursor = conn.cursor()

            cursor.execute("SELECT name, code, last_time FROM boss")
            rows = cursor.fetchall()

            msg = ""
            for r in rows:
                msg += f"{r[0]} ({r[1]})：{r[2]}\n"

            if msg == "":
                msg = "目前沒有資料"

            cursor.close()
            conn.close()

        # ===== 新增 =====
        elif user_msg.startswith("新增"):
            try:
                _, name, code, time = user_msg.split()

                conn = get_db()
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO boss (name, code, last_time) VALUES (%s, %s, %s)",
                    (name, code, time)
                )

                conn.commit()
                cursor.close()
                conn.close()

                msg = "新增成功"

            except:
                msg = "格式錯誤（新增 名稱 代號 時間）"

        # ===== 更新時間 =====
        elif user_msg.startswith("打王"):
            try:
                _, code, time = user_msg.split()

                conn = get_db()
                cursor = conn.cursor()

                cursor.execute(
                    "UPDATE boss SET last_time=%s WHERE code=%s",
                    (time, code)
                )

                conn.commit()
                cursor.close()
                conn.close()

                msg = "時間已更新"

            except:
                msg = "格式錯誤（打王 代號 時間）"

        else:
            msg = "指令：新增 / 查王 / 打王"

        # 回覆
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=msg)]
            )
        )


# ===== Render 啟動 =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
