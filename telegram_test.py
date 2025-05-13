import os

import requests
from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BOT_URL = f'https://api.telegram.org/bot{TOKEN}'

app = Flask(__name__)

@app.route('/')
def index():
    return 'Bot is running.'

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    if 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        print(f"[RECEIVED] {chat_id}: {text}")

        send_message(chat_id, f"You said: {text}")
    return 'ok'

def send_message(chat_id, text):
    url = f'{BOT_URL}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text}
    requests.post(url, json=payload)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)