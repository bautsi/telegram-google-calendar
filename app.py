import json
import logging
import os
import time
import traceback
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Thread
from typing import Any, List, Optional

# import ngrok
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel

load_dotenv()

local_time = datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0)
formated_time = local_time.strftime("%Y-%m-%d_%H-%M-%S")

os.makedirs("/tmp", exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s : %(message)s",
    handlers=[
        logging.FileHandler(f"/tmp/{formated_time}.log"),
        logging.StreamHandler(),
    ],
    level=logging.DEBUG,
)

# Global Variables
# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]
OAUTH_FLAG_PATH = "/tmp/oauth_waiting"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MY_GMAIL = os.getenv("MY_GMAIL")

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL")

# Use Mandarin cause I usaully text by, could change to English if needed
DEFAULT_PROMPT = f"""
    現在時間為: {local_time.isoformat()}
    請根據下方訊息內容，自動填入我定義的 GeminiSchema (Pydantic 格式)，只回傳符合 schema 的 JSON: 

    - `summary`: 事件標題
    - `location`: 事件地點 (可選, 即使不是正式地址，也請將認為是地點的詞填入 location 欄位)
    - `description`: 說明內容 (可選)
    - `start_time`: 事件開始時間 (RFC3339 格式，如 "2025-05-11T15:00:00+08:00")
    - `end_time`: 事件結束時間 (可選, 若有 start_time 且無提供 end_time 請幫我設定為一小時之後結束)
    - `reminder_minutes`: 提醒時間, 無論如何幫我加入一天前和兩天前, 如你認為必要請幫我填充至上限五個即可 (單位為分鐘) (可選但至少一天前和兩天前)

    注意事項: 
    - 請只回傳 JSON, 勿回傳說明文字。
    - 欄位若無法明確解析，請略過不填。
"""

# Flask
app = Flask(__name__)


@app.route("/")
def index():
    """Not really used but keep"""
    return "<h1>Telegram Google Calendar bot is running.</h1>"


def run_flask():
    """Extract for multi-thread"""
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


# Gemini
# Default event structure waiting for replacement after Gemini response
# Change time zone if you r in different ones
# Location may be hard for some specific places so is normal if that place not famous, cause it depends of Gemini model intelligence
DEFAULT_EVENT_STRUCTURE = {
    "summary": "Unknown",
    "location": "",
    "description": "",
    "start": {
        "dateTime": local_time.isoformat(),
        "timeZone": "Asia/Shanghai",
    },
    "end": {
        "dateTime": (local_time + timedelta(hours=1)).isoformat(),
        "timeZone": "Asia/Shanghai",
    },
    "attendees": [
        {"email": MY_GMAIL},
    ],
    "reminders": {
        "useDefault": False,
        "overrides": [
            # {"method": "popup", "minutes": 1 * 60},
            # {"method": "popup", "minutes": 2 * 60},
            # {"method": "popup", "minutes": 1 * 24 * 60},
            # {"method": "popup", "minutes": 2 * 24 * 60},
            # {"method": "popup", "minutes": 7 * 24 * 60},
        ],
    },
}


def event_replace(gemini_json_response: dict[str, Any], copied_event: dict[str, Any]) -> dict[str, Any]:
    """Replace default event after getting Gemini response

    Args:
        gemini_json_response (dict[str, Any]): Converted json now dict
        copied_event (dict[str, Any]): Deep copied default event

    Returns:
        dict[str, Any]: Dict for Google Calendar
    """
    # Replace summary
    if gemini_json_response.get("summary"):
        copied_event["summary"] = gemini_json_response["summary"]
        logging.debug("[Event replace]: summary replaced")

    # Replace location
    if gemini_json_response.get("location"):
        copied_event["location"] = gemini_json_response["location"]
        logging.debug("[Event replace]: location replaced")

    # Replace description
    if gemini_json_response.get("description"):
        copied_event["description"] = gemini_json_response["description"]
        logging.debug("[Event replace]: description replaced")

    # Replace start time
    if gemini_json_response.get("start_time"):
        copied_event["start"]["dateTime"] = gemini_json_response["start_time"]
        logging.debug("[Event replace]: start time replaced")

    # Replace end time
    if gemini_json_response.get("end_time"):
        copied_event["end"]["dateTime"] = gemini_json_response["end_time"]
        logging.debug("[Event replace]: end time replaced")

    # Turn minutes into int and push to reminder override minutes
    if gemini_json_response.get("reminder_minutes"):
        for minute in gemini_json_response["reminder_minutes"]:
            # Prevent over limit popups (5)
            if len(copied_event["reminders"]["overrides"]) < 5:
                copied_event["reminders"]["overrides"].append({"method": "popup", "minutes": int(minute)})
            else:
                break
        logging.debug("[Event replace]: reminder added")

    return copied_event


# Json restrict to let Gemini follow for responses
class GeminiSchema(BaseModel):
    summary: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    reminder_minutes: Optional[List[int]] = None


def ask_gemini(input_text: str) -> str:
    """Gemini chatting

    Args:
        input_text (str): Text from telegram user message

    Returns:
        str: After replacement dict for Google Calender event insert
    """
    try:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=DEFAULT_PROMPT + input_text,
            config={
                "response_mime_type": "application/json",
                "response_schema": GeminiSchema,
            },
        )

        response_json = json.loads(response.text)
        logging.debug(f"[Gemini response]: {response_json}")
        event = deepcopy(DEFAULT_EVENT_STRUCTURE)
        logging.debug(f"[Default event]: {event}")

        return event_replace(response_json, event)
    except Exception as e:
        logging.error(f"[Gemini error]: {e}")


# Telegram Bot
def set_webhook(public_url: str):
    """Set Cloud Run (ngrok) url as webhook url

    Args:
        public_url (str): Cloud Run (ngrok) url
    """
    webhook_url = f"{public_url}/{BOT_TOKEN}"
    logging.debug(f"[Webhook]: Set to - {webhook_url}")
    response = requests.post(f"{BOT_URL}/setWebhook", data={"url": webhook_url})
    logging.debug(f"[Webhook set response]: {response.text}")


def send_message(text: str):
    """Telegram send message from server to chat room

    Args:
        chat_id (str): Chat room id
        text (str): Message that want to let user read
    """
    url = f"{BOT_URL}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()

    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        user_text: str = update["message"].get("text", "")

        from_user = update["message"].get("from", {})
        if from_user.get("is_bot", False):
            # logging.info(f"[Telegram bot]: {user_text}")
            return

        logging.info(f"[Telegram user]: {user_text}")

        gemini_response = ask_gemini(user_text)

        send_message(add_event(gemini_response))

    return {"ok": True}

    # send_message(chat_id, gemini_reply)  # Test receive and response


# Google Calendar
def set_oauth_flag():
    with open(OAUTH_FLAG_PATH, "w") as f:
        f.write("waiting")


def clear_oauth_flag():
    if os.path.exists(OAUTH_FLAG_PATH):
        os.remove(OAUTH_FLAG_PATH)


def is_oauth_waiting():
    return os.path.exists(OAUTH_FLAG_PATH)


def generate_auth_url():
    flow = Flow.from_client_secrets_file("credentials.json", scopes=SCOPES, redirect_uri=f"{CLOUD_RUN_URL}/auth/callback")
    auth_uri, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return auth_uri


@app.route("/auth/start")
def auth_start():
    url = generate_auth_url()
    return jsonify({"auth_url": url})


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    flow = Flow.from_client_secrets_file("credentials.json", scopes=SCOPES, redirect_uri=f"{CLOUD_RUN_URL}/auth/callback")
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open("/tmp/token.json", "w") as token:
        token.write(creds.to_json())
    clear_oauth_flag()
    return "Authorization completed. You can return to the app."


def add_event(replaced_response: dict[str, Any]) -> str:
    logging.debug(f"[Final event]: {replaced_response}")

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("/tmp/token.json"):
        try:
            creds = Credentials.from_authorized_user_file("/tmp/token.json", SCOPES)
            if not creds.refresh_token:
                logging.warning("[Google Calendar]: Token exists but no refresh_token, deleting")
                os.remove("/tmp/token.json")
                creds = None
        except Exception as e:
            logging.error(f"[Google Calendar]: Failed to parse token file - {e}")
            os.remove("/tmp/token.json")
            creds = None
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        # logging.error("[Google Calendar]: Token not found")
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"[Google Calendar]: Token refresh failed - {e}")

                set_oauth_flag()

                auth_url = generate_auth_url()
                send_message(f"Google Token Error, creating new token: \n{auth_url}")

                while is_oauth_waiting():
                    time.sleep(5)

                creds = Credentials.from_authorized_user_file("/tmp/token.json", SCOPES)
        else:
            set_oauth_flag()

            auth_url = generate_auth_url()
            send_message(f"Create new token: \n{auth_url}")

            while is_oauth_waiting():
                time.sleep(5)

            creds = Credentials.from_authorized_user_file("/tmp/token.json", SCOPES)
            # flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            # creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        # with open("/tmp/token.json", "w") as token:
        #     token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        event = service.events().insert(calendarId="primary", body=replaced_response).execute()

        logging.info(f"[Google Calendar]: Event created - {event.get('htmlLink')}")
        return f"Event created: {event.get('htmlLink')}"

    except HttpError as error:
        logging.error(f"[Google Calendar]: An error occurred: {error}")
        return f"[Google Calendar]: An error occurred: {error}"


# Main run
if __name__ == "__main__":
    # Run flask at background in one thread
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Establish ngrok tunnel and set webhook
    # listener = ngrok.forward(8000, authtoken=os.getenv("NGROK_AUTHTOKEN"))
    # public_url = listener.url()
    # logging.debug(f"[ngrok] Ingress established at: {public_url}")

    logging.debug(f"[Cloud run]: Url set - {CLOUD_RUN_URL}")
    set_webhook(CLOUD_RUN_URL)

    try:
        while True:
            time.sleep(1)
    except:
        error_message = traceback.format_exc()
        logging.error(error_message)
    finally:
        os._exit(0)
