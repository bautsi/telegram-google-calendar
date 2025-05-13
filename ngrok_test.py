# import ngrok python sdk
import os
import time

import ngrok
from dotenv import load_dotenv

load_dotenv()

# Establish connectivity
listener = ngrok.forward(8000, authtoken=os.getenv("NGROK_AUTHTOKEN"))

# Output ngrok url to console
print(f"Ingress established at {listener.url()}")

# Keep the listener alive
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Closing listener")