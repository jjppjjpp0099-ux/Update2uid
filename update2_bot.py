import os, json, base64, asyncio, requests, time
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from threading import Thread
from flask import Flask

# --- [ CONFIGURATION ] ---
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME") # External Repo: username/Like-api-2
GROUP_ID = int(os.getenv("GROUP_ID", 0))
RENDER_API_KEY = os.getenv("RENDER_API_KEY") # External Account API Key
SERVICE_ID = os.getenv("SERVICE_ID") # External Service ID
TARGET_BOT = "@Khushi_jwt_bot"

LAST_UPDATE_TIME = datetime.min
IS_PROCESSING = False

# --- [ KEEP ALIVE SYSTEM (Anti-Sleep) ] ---
app = Flask('')
@app.route('/')
def home(): return "Manager Bot is Awake ⚡"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- [ GITHUB HELPERS ] ---
def get_github_content(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        content = base64.b64decode(r.json()['content']).decode()
        return content, r.json().get('sha')
    return None, None

def update_github(file_path, content, sha=None):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Auto-Update: Tokens for External Repo", 
        "content": base64.b64encode(content.encode()).decode(), 
        "sha": sha
    }
    return requests.put(url, headers=headers, json=data).status_code

# --- [ RENDER TRACKER (Target Bot) ] ---
async def wait_for_render_deploy():
    url = f"https://api.render.com/v1/services/{SERVICE_ID}/deploys"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
    
    # Wait for status to become 'live'
    while True:
        try:
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                latest_deploy = r.json()[0]
                status = latest_deploy['deploy']['status']
                if status == "live":
                    return True
                elif status in ["build_failed", "canceled"]:
                    return False
        except: pass
        await asyncio.sleep(30) # Har 30 sec mein check karega

# --- [ JWT LOGIC ] ---
def decode_jwt_exp(token):
    try:
        payload = json.loads(base64.b64decode(token.split('.')[1] + '==').decode())
        return payload.get('exp', 0)
    except: return 0

def analyze_tokens(content):
    try:
        data = json.loads(content)
        tokens = data if isinstance(data
