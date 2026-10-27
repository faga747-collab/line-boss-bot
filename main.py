from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import psycopg2
import logging
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

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("缺少 DATABASE_URL，請檢查 Railway Variables")

def db_connect():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)

# 僅在初始化時使用此連線；處理訊息時會建立各自的連線。
conn = db_connect()
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

# 預設王
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
    ("61", "變怪王", "變怪"), ("鳥", "不死鳥"),
    ("78", "78古巨", "古巨"), ("12", "12克特", "克特"),
]

for boss, respawn in default_bosses:
    cursor.execute(
        "INSERT INTO bosses (id, respawn, last_kill, note) VALUES (%s, %s, NULL, NULL) ON CONFLICT (id) DO NOTHING",
        (boss, respawn)
    )
