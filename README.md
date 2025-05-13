# Telegram Google Calendar

Create Google Calendar events by messaging a Telegram bot.

This is a simple project demonstrating how to build and deploy a conversational AI service using Gemini, Google APIs, and Cloud Run.

---

## Tech Stack

| Area               | Technology               |
| ------------------ | ------------------------ |
| Bot Platform       | Telegram Bot API         |
| Backend            | Flask                    |
| AI Model           | Gemini 2.0 Flash         |
| Calendar Service   | Google Calendar API      |
| Cloud Deployment   | Google Cloud Run         |
| Container Registry | Artifact Registry        |
| Auth Handling      | OAuth 2.0 (`token.json`) |
| Language           | Python 3.13.2            |

---

## Deployment Guide

### 1. Clone the Repository

```bash
git clone https://github.com/bautsi/telegram-google-calendar
cd telegram-google-calendar
```

### 2. Configure Environment Variables

#### Option A: Deploying to Cloud Run

- When deploying or revising a service on Cloud Run, go to:
  Edit and deploy new revision → Variables and secrets

- Add the following environment variables:

```makefile
TELEGRAM_BOT_TOKEN=...
MY_GMAIL=...          # The Gmail address that will receive the event
GEMINI_API_KEY=...
CLOUD_RUN_URL=...     # e.g. https://CLOUD_RUN_NAME-GARBLED-uc.a.run.app
```

#### Option B: Running Locally

- Create a .env file in the project root:

```makefile
TELEGRAM_BOT_TOKEN="..."
MY_GMAIL="..."
GEMINI_API_KEY="..."
CLOUD_RUN_URL="..."
```

Bring back ngrok things in main app.py file (also the token create method if expired or not created)

### 3. Set Up Google Calendar Credentials

- In the GCP Console, enable Google Calendar API

- Download the OAuth 2.0 Client ID and save it as credentials.json in the root directory

- Run calendar_test.py locally to generate token.json (you'll be prompted to authenticate)

### 4. Build and Deploy to Cloud Run

#### a. Initialize Artifact Registry (first time only):

```bash
gcloud auth configure-docker REGION-docker.pkg.dev
```

#### b. Build and Push Docker Image:

```bash
docker build -t REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPO_NAME/telegram-google-calendar .

docker push REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPO_NAME/telegram-google-calendar
```

#### c. Deploy to Cloud Run:

You can use the GCP Console or CLI. Remember to:

- Choose the pushed image

- Set environment variables

## Security & Deployment Notes

- Never commit the following files:

  - .env
  - credentials.json
  - token.json

- Add them to .gitignore

- token.json must be placed in /tmp/token.json in Cloud Run for write access

- For production use, consider using Secret Manager

## Project Structure

```
.
├── app.py             # Main Flask server
├── Dockerfile         # Container definition
├── .env
├── token.json         # OAuth token (generated locally, do not commit)
├── credentials.json   # Google OAuth credentials
├── requirements.txt
└── README.md
```

Some test files are also included for local validation.

# License

MIT License © 2025 Brad Liu
