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
        tokens = data if isinstance(data, list) else [data]
        now = int(time.time())
        active_count = 0
        exp_times = []
        for item in tokens:
            t = item.get("token")
            if t:
                expiry = decode_jwt_exp(t)
                if expiry > now:
                    active_count += 1
                    exp_times.append(expiry)
        next_expiry = min(exp_times) if exp_times else 0
        return active_count, len(tokens), next_expiry
    except: return 0, 0, 0

# --- [ CLIENT SETUP ] ---
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/expire', chats=GROUP_ID))
async def expire_report(event):
    content, _ = get_github_content("token_ind.json")
    if not content: return await event.reply("❌ Error: External Repo file not found!")
    
    active, total, next_exp = analyze_tokens(content)
    msg = f"**📊 Token Status (External Repo)**\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"✅ **Active:** `{active}/{total}`\n"
    if next_exp > 0:
        time_left = next_exp - int(time.time())
        hrs, mins = divmod(time_left // 60, 60)
        msg += f"⏳ **Next Expiry In:** `{int(hrs)}h {int(mins)}m`\n"
    await event.reply(msg)

async def auto_updater():
    global LAST_UPDATE_TIME, IS_PROCESSING
    while True:
        try:
            content, sha = get_github_content("token_ind.json")
            if content:
                active, total, next_exp = analyze_tokens(content)
                now = int(time.time())
                
                should_update = False
                # T-10 Trigger
                if next_exp > 0 and (next_exp - now) < 600:
                    should_update = True
                # Emergency Trigger (2-hour safety gap)
                elif active < total:
                    if datetime.now() - LAST_UPDATE_TIME > timedelta(hours=2):
                        should_update = True
                
                if should_update and not IS_PROCESSING:
                    IS_PROCESSING = True
                    async with client.conversation(TARGET_BOT) as conv:
                        await conv.send_file("id.json")
                        found_file = None
                        for _ in range(5):
                            resp = await conv.get_response()
                            if resp.media:
                                found_file = await client.download_media(resp.media)
                                break
                        
                        if found_file:
                            with open(found_file, 'r') as f: new_data = f.read()
                            # Push updates to external repo files
                            for f_name in ["token_ind.json", "token_ind_visit.json"]:
                                _, c_sha = get_github_content(f_name)
                                update_github(f_name, new_data, c_sha)
                            
                            LAST_UPDATE_TIME = datetime.now()
                            await client.send_message(GROUP_ID, "✅ **Automatic update successfully!**\nWaiting for deployment...")
                            
                            # Track External Render Deploy
                            success = await wait_for_render_deploy()
                            if success:
                                await client.send_message(GROUP_ID, "BOT IS LIVE ✅")
                            os.remove(found_file)
                    IS_PROCESSING = False
        except Exception as e:
            print(f"Error in updater: {e}")
            IS_PROCESSING = False
        await asyncio.sleep(600) # 10 minute check

async def main():
    await client.start()
    # Silent Startup: No message sent here.
    asyncio.create_task(auto_updater())
    await client.run_until_disconnected()

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
