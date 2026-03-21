import os
import json
import base64
import asyncio
import requests
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from threading import Thread
from flask import Flask

# --- [ CREDENTIALS ] ---
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Jis repo mein token update karna hai
REPO_NAME = "jjppjjpp0099-ux/Like-api-2" 

# Render Notification ke liye (Settings mein add karein)
RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID")

TARGET_BOT_USR = "@Khushi_jwt_bot"
FILES_TO_PUSH = ["token_ind.json", "token_ind_visit.json"]
COOLDOWN_HOURS = 4
DATA_FILE = "last_update.json"
is_processing = False

# --- [ KEEP ALIVE SERVER ] ---
app = Flask('')
@app.route('/')
def home(): return "Userbot is Active & Online"
def run_web(): app.run(host='0.0.0.0', port=os.getenv("PORT", 8080))

# --- [ HELPER FUNCTIONS ] ---
def get_last_update():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f: return datetime.fromisoformat(json.load(f)['time'])
        except: pass
    return datetime.min

def save_last_update():
    with open(DATA_FILE, 'w') as f: json.dump({'time': datetime.now().isoformat()}, f)

def update_github(file_path, content):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get('sha') if r.status_code == 200 else None
    content_b64 = base64.b64encode(content.encode()).decode()
    data = {"message": f"Auto-Update: {file_path}", "content": content_b64, "branch": "main"}
    if sha: data["sha"] = sha
    return requests.put(url, headers=headers, json=data).status_code

async def wait_for_render_live(event):
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return await event.respond("✅ GitHub files update ho gayi hain! (Render notification setup nahi hai)")

    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
    status_msg = await event.respond("🚀 GitHub Updated! Ab Render deploy check kar raha hoon... (Wait 1-2 mins)")

    # Render deployment status check karne ka loop
    for i in range(25): # 25 attempts * 15 seconds = ~6 minutes max
        await asyncio.sleep(15)
        try:
            r = requests.get(f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys", headers=headers)
            if r.status_code == 200:
                latest_deploy = r.json()[0]['deploy']
                status = latest_deploy.get('status')
                
                if status == "live":
                    return await status_msg.edit("✅ **Render Update Successfully!** 🔥\nNaya token ab Like Bot mein active ho gaya hai.")
                elif status in ["build_failed", "canceled"]:
                    return await status_msg.edit(f"❌ Render deploy fail ho gaya: `{status}`")
        except Exception as e:
            print(f"Render API Error: {e}")
            
    await status_msg.edit("⌛ Render deploy abhi bhi chal raha hai. Ek baar dashboard check kar lijiye!")

# --- [ MAIN BOT LOGIC ] ---
client = TelegramClient('update2_session', API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/update2', outgoing=True))
async def handle_update(event):
    global is_processing
    if is_processing: return await event.respond("⚠️ Ek process pehle se chal raha hai!")

    last_time = get_last_update()
    if datetime.now() - last_time < timedelta(hours=COOLDOWN_HOURS):
        return await event.respond("⏳ Cooldown active hai (4 Hours). Please wait.")

    is_processing = True
    status = await event.respond("⚙️ Khushi Bot se files nikal raha hoon...")

    try:
        async with client.conversation(TARGET_BOT_USR) as conv:
            await conv.send_file("id.json")
            found_file = None
            for _ in range(10): 
                resp = await conv.get_response()
                if resp.media:
                    found_file = await client.download_media(resp.media)
                    break
            
            if not found_file: raise Exception("Khushi Bot ne file reply nahi ki!")

            with open(found_file, 'r') as f: new_content = f.read()
            
            # GitHub par dono files update karein
            for f_name in FILES_TO_PUSH: 
                update_github(f_name, new_content)
            
            save_last_update()
            await status.delete()
            
            # Render deploy ka wait aur notification
            await wait_for_render_live(event)

    except Exception as e:
        await event.respond(f"❌ Error: {str(e)}")
    finally:
        is_processing = False
        if 'found_file' in locals() and found_file and os.path.exists(found_file): 
            os.remove(found_file)

async def main():
    await client.start()
    print("🚀 Protected Userbot is LIVE on Render...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    # Flask ko separate thread mein chalayein
    Thread(target=run_web).start()
    # Kal wala loop error fix karne ke liye modern asyncio method
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
