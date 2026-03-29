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
REPO_NAME = os.getenv("REPO_NAME")
GROUP_ID = int(os.getenv("GROUP_ID", 0))
RENDER_API_KEY = os.getenv("RENDER_API_KEY")
SERVICE_ID = os.getenv("SERVICE_ID")
TARGET_BOT = "@Khushi_jwt_bot"

LAST_UPDATE_TIME = datetime.now() - timedelta(hours=2) 
IS_PROCESSING = False
app = Flask(__name__)

@app.route('/')
def home(): return "Userbot is Active ⚡", 200

@app.route('/keep_alive')
def keep_alive(): return "Alive", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- [ GITHUB & ANALYZER ] ---
def get_github_content(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = base64.b64decode(r.json()['content']).decode()
            return content, r.json().get('sha')
    except: pass
    return None, None

def update_github(file_path, content, sha=None):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {"message": "Auto-Update", "content": base64.b64encode(content.encode()).decode(), "sha": sha}
    try: return requests.put(url, headers=headers, json=data).status_code
    except: return 500

def decode_jwt_exp(token):
    try:
        payload = json.loads(base64.b64decode(token.split('.')[1] + '==').decode())
        return payload.get('exp', 0)
    except: return 0

def analyze_tokens(content):
    try:
        data = json.loads(content)
        tokens = data if isinstance(data, list) else [data]
        now = int(time.time())
        active_count, exp_times = 0, []
        for item in tokens:
            t = item.get("token")
            if t:
                expiry = decode_jwt_exp(t)
                if expiry > now:
                    active_count += 1
                    exp_times.append(expiry)
        next_exp = min([x for x in exp_times if x > 0]) if any(x > 0 for x in exp_times) else 0
        return active_count, len(tokens), next_exp
    except: return 0, 0, 0

# --- [ USERBOT CLIENT ] ---
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@client.on(events.NewMessage(pattern=r'(?i)^/expire'))
async def expire_report(event):
    # Userbot hamesha response dega agar group match hua
    if event.chat_id != GROUP_ID: return
    
    content, _ = get_github_content("token_ind.json")
    if not content:
        return await event.respond("❌ Error: GitHub file nahi mili!")
    
    active, total, next_exp = analyze_tokens(content)
    msg = f"📊 **Userbot Status**\n━━━━━━━━━━━━━━\n✅ Active: `{active}/{total}`"
    
    if active > 0 and next_exp > 0:
        rem_sec = int(next_exp - time.time())
        h, r = divmod(rem_sec, 3600)
        m, _ = divmod(r, 60)
        t_str = f"{h}h {m}m" if h > 0 else f"{m}m"
        msg += f"\n⏳ Next Expiry: `{t_str}`"
    else:
        msg += f"\n⚠️ **All Tokens Expired!**"
    
    await event.respond(msg)

# --- [ AUTO UPDATER ] ---
async def auto_updater():
    global IS_PROCESSING, LAST_UPDATE_TIME
    while True:
        try:
            content, sha = get_github_content("token_ind.json")
            if content:
                active, _, _ = analyze_tokens(content)
                if active == 0:
                    if (datetime.now() - LAST_UPDATE_TIME) >= timedelta(hours=2):
                        if not IS_PROCESSING:
                            IS_PROCESSING = True
                            async with client.conversation(TARGET_BOT) as conv:
                                await conv.send_file("id.json")
                                f_file = None
                                for _ in range(5):
                                    resp = await conv.get_response()
                                    if resp.media:
                                        f_file = await client.download_media(resp.media)
                                        break
                                    await asyncio.sleep(2)
                                if f_file:
                                    with open(f_file, 'r') as f: new_data = f.read()
                                    for f_n in ["token_ind.json", "token_ind_visit.json"]:
                                        _, c_sha = get_github_content(f_n)
                                        update_github(f_n, new_data, c_sha)
                                    LAST_UPDATE_TIME = datetime.now()
                                    await client.send_message(GROUP_ID, "✅ **Tokens Refreshed!**")
                                    if os.path.exists(f_file): os.remove(f_file)
                            IS_PROCESSING = False
        except: pass
        await asyncio.sleep(300)

async def main():
    await client.start()
    print("Userbot Started Successfully!")
    await asyncio.gather(client.run_until_disconnected(), auto_updater())

if __name__ == "__main__":
    # Flask thread start karo
    Thread(target=run_web, daemon=True).start()
    # Main Bot start karo
    asyncio.run(main())
