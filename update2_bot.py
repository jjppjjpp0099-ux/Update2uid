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
# Yahan Render mein apne PURANE REPO ka naam dalna (e.g. 'username/old-repo')
REPO_NAME = os.getenv("REPO_NAME") 
TARGET_BOT_ID = 8292700848
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

# --- [ LOGIC FUNCTIONS ] ---
def get_last_update():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                return datetime.fromisoformat(data['time'])
        except: pass
    return datetime.min

def save_last_update():
    with open(DATA_FILE, 'w') as f:
        json.dump({'time': datetime.now().isoformat()}, f)

def update_github(file_path, content):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # Pehle SHA nikalna padta hai update ke liye
    r = requests.get(url, headers=headers)
    sha = r.json().get('sha') if r.status_code == 200 else None
    
    content_b64 = base64.b64encode(content.encode()).decode()
    data = {
        "message": f"Auto-Update {file_path} via Bot",
        "content": content_b64,
        "branch": "main"
    }
    if sha: data["sha"] = sha
    
    res = requests.put(url, headers=headers, json=data)
    return res.status_code

# --- [ BOT COMMANDS ] ---
client = TelegramClient('update2_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

@client.on(events.NewMessage(pattern='/update2'))
async def handle_update(event):
    global is_processing
    
    # 1. Anti-Spam Check
    if is_processing:
        return await event.reply("⚠️ Ek process abhi chal raha hai, thoda sabar karein!")

    # 2. Cooldown Check (4 Hours)
    last_time = get_last_update()
    diff = datetime.now() - last_time
    if diff < timedelta(hours=COOLDOWN_HOURS):
        remaining = timedelta(hours=COOLDOWN_HOURS) - diff
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return await event.reply(f"⏳ **Limit Active!** Agla update {hours}h {minutes}m baad kar payenge.")

    is_processing = True
    status_msg = await event.reply("⚙️ Kaam shuru... Target bot se contact kar raha hoon.")

    try:
        # 3. Chat with @Khushi_jwt_bot
        async with client.conversation(TARGET_BOT_USR) as conv:
            await status_msg.edit("📤 `id.json` bhej raha hoon...")
            await conv.send_file("id.json")
            
            await status_msg.edit("⏳ 3 files ka intezar hai (Filtering)...")
            
            found_file = None
            # Loop to check incoming messages for the specific file
            for _ in range(10): 
                resp = await conv.get_response(timeout=60)
                if resp.media and hasattr(resp.media, 'document'):
                    # Check file name in attributes
                    file_name = next((attr.file_name for attr in resp.media.document.attributes if hasattr(attr, 'file_name')), "")
                    if file_name == "jwt_token.json":
                        found_file = await client.download_media(resp.media)
                        break
            
            if not found_file:
                raise Exception("Teesre bot ne `jwt_token.json` nahi bheji (Timeout).")

            # 4. Read Downloaded File
            with open(found_file, 'r') as f:
                new_data = f.read()

            await status_msg.edit(f"🔗 Purane repo ({REPO_NAME}) mein upload ho raha hai...")
            
            # 5. Push to Old Repo
            success = True
            for f_name in FILES_TO_PUSH:
                code = update_github(f_name, new_data)
                if code not in [200, 201]:
                    success = False
                    break
            
            if success:
                save_last_update()
                await status_msg.edit(f"✅ **Success!** Purane repo ki dono files update ho gayi hain. Ab 4 ghante ka break!")
            else:
                await status_msg.edit("❌ GitHub Update Fail ho gaya! Token ya Repo Name check karein.")

            # Cleanup
            if os.path.exists(found_file): os.remove(found_file)

    except Exception as e:
        await status_msg.edit(f"❌ **Error:** {str(e)}")
    
    finally:
        is_processing = False

if __name__ == "__main__":
    Thread(target=run_web).start()
    print("🚀 Bot is LIVE for Group Users...")
    client.run_until_disconnected()
