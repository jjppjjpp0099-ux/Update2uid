import os
import json
import base64
import asyncio
import requests
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

# --- [ RENDER ENVIRONMENT VARIABLES ] ---
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME") 
TARGET_BOT_USR = "@Khushi_jwt_bot"

FILES_TO_PUSH = ["token_ind.json", "token_ind_visit.json"]
COOLDOWN_HOURS = 4
DATA_FILE = "last_update.json"
is_processing = False 

# --- [ KEEP ALIVE FOR RENDER ] ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"
def run_web(): app.run(host='0.0.0.0', port=os.getenv("PORT", 8080))

# --- [ FUNCTIONS ] ---
def get_last_update():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return datetime.fromisoformat(json.load(f)['time'])
        except: pass
    return datetime.min

def save_last_update():
    with open(DATA_FILE, 'w') as f:
        json.dump({'time': datetime.now().isoformat()}, f)

def update_github(file_path, content):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get('sha') if r.status_code == 200 else None
    content_b64 = base64.b64encode(content.encode()).decode()
    data = {"message": f"Auto-Update: {file_path}", "content": content_b64, "branch": "main"}
    if sha: data["sha"] = sha
    res = requests.put(url, headers=headers, json=data)
    return res.status_code

# --- [ BOT COMMANDS ] ---
client = TelegramClient('update2_session', API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/update2'))
async def handle_update(event):
    global is_processing
    if is_processing: return await event.reply("⚠️ Wait, ek process chal raha hai!")

    last_time = get_last_update()
    if datetime.now() - last_time < timedelta(hours=COOLDOWN_HOURS):
        return await event.reply("⏳ 4 ghante ka cooldown active hai!")

    is_processing = True
    status = await event.reply("⚙️ Shuru kar raha hoon...")

    try:
        async with client.conversation(TARGET_BOT_USR) as conv:
            await conv.send_file("id.json")
            found_file = None
            for _ in range(10):
                resp = await conv.get_response(timeout=60)
                if resp.media:
                    file_name = next((attr.file_name for attr in resp.media.document.attributes if hasattr(attr, 'file_name')), "")
                    if file_name == "jwt_token.json":
                        found_file = await client.download_media(resp.media)
                        break
            
            if not found_file: raise Exception("jwt_token.json nahi mila!")

            with open(found_file, 'r') as f: new_content = f.read()
            for f_name in FILES_TO_PUSH: update_github(f_name, new_content)

            save_last_update()
            await status.edit(f"✅ Success! Purane repo ({REPO_NAME}) ki files update ho gayi.")
            if os.path.exists(found_file): os.remove(found_file)
    except Exception as e:
        await status.edit(f"❌ Error: {str(e)}")
    finally:
        is_processing = False

# --- [ MAIN RUNNER ] ---
async def start_bot():
    await client.start(bot_token=BOT_TOKEN)
    print("🚀 Bot is LIVE...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    Thread(target=run_web).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
