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

# --- [ INITIALIZATION ] ---
# Pichle update ka time 2 ghante purana rakha hai taaki deploy hote hi check ho sake
LAST_UPDATE_TIME = datetime.now() - timedelta(hours=2) 
IS_PROCESSING = False

app = Flask(__name__)

# --- [ FLASK ROUTES ] ---

@app.route('/')
def home():
    return "Manager Bot is Awake ⚡", 200

@app.route('/keep_alive')
def keep_alive():
    return f"Status: Monitoring... Last Update: {LAST_UPDATE_TIME.strftime('%H:%M:%S')}", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- [ GITHUB & TOKEN FUNCTIONS ] ---

def get_github_content(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = base64.b64decode(r.json()['content']).decode()
            return content, r.json().get('sha')
    except Exception as e:
        print(f"GitHub Error: {e}")
    return None, None

def update_github(file_path, content, sha=None):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "message": "Auto-Update Tokens",
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha
    }
    try:
        r = requests.put(url, headers=headers, json=data)
        return r.status_code
    except:
        return 500

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
                else:
                    exp_times.append(0)
        
        valid_exps = [x for x in exp_times if x > 0]
        next_exp = min(valid_exps) if valid_exps else 0
        return active_count, len(tokens), next_exp
    except: return 0, 0, 0

# --- [ TELEGRAM CLIENT & COMMANDS ] ---

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Command Handler - Isme pattern ko thoda relax kiya hai
@client.on(events.NewMessage(pattern=r'(?i)^/expire'))
async def expire_report(event):
    # Sirf specific group ID me reply kare
    if event.chat_id != GROUP_ID:
        return
        
    print(f"Received /expire from {event.chat_id}") # Log for Render
    
    content, _ = get_github_content("token_ind.json")
    if not content: 
        return await event.reply("❌ Error: GitHub file nahi mili!")
        
    active, total, next_exp = analyze_tokens(content)
    msg = f"📊 **Token Status**\n━━━━━━━━━━\n✅ Active: `{active}/{total}`"
    
    if active > 0 and next_exp > 0:
        remaining_sec = int(next_exp - time.time())
        hours, remainder = divmod(remaining_sec, 3600)
        minutes, _ = divmod(remainder, 60)
        
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        msg += f"\n⏳ Next Expiry in: `{time_str}`"
    elif active == 0:
        msg += f"\n⚠️ **All Tokens Expired!**"
        
    await event.reply(msg)

# --- [ AUTO UPDATER LOGIC ] ---

async def auto_updater():
    global IS_PROCESSING, LAST_UPDATE_TIME
    while True:
        try:
            content, sha = get_github_content("token_ind.json")
            if content:
                active, total, _ = analyze_tokens(content)
                
                # Condition: Sirf 0 hone par
                if active == 0:
                    current_time = datetime.now()
                    if (current_time - LAST_UPDATE_TIME) >= timedelta(hours=2):
                        if not IS_PROCESSING:
                            IS_PROCESSING = True
                            print("🚨 Tokens 0! Requesting new ones...")
                            
                            async with client.conversation(TARGET_BOT) as conv:
                                await conv.send_file("id.json")
                                found_file = None
                                for _ in range(5):
                                    resp = await conv.get_response()
                                    if resp.media:
                                        found_file = await client.download_media(resp.media)
                                        break
                                    await asyncio.sleep(2)
                                
                                if found_file:
                                    with open(found_file, 'r') as f: new_data = f.read()
                                    for f_n in ["token_ind.json", "token_ind_visit.json"]:
                                        _, c_sha = get_github_content(f_n)
                                        update_github(f_n, new_data, c_sha)
                                    
                                    LAST_UPDATE_TIME = datetime.now()
                                    await client.send_message(GROUP_ID, "✅ **Auto-Update Success!**\nTokens refreshed because they hit 0.")
                                    if os.path.exists(found_file): os.remove(found_file)
                                else:
                                    LAST_UPDATE_TIME = datetime.now()
                                    print("No response from target bot.")
                            IS_PROCESSING = False
                    else:
                        print("Tokens 0, but safety 2h gap active.")
                else:
                    print(f"Status: {active}/{total} tokens active.")

        except Exception as e:
            print(f"Loop Error: {e}")
            IS_PROCESSING = False
        
        await asyncio.sleep(300)

# --- [ MAIN LOOP ] ---

async def main():
    print("Starting Client...")
    await client.start()
    print("Bot is LIVE! Listening for commands...")
    
    # Task list create karein
    updater_task = asyncio.create_task(auto_updater())
    
    # Bot ko chalu rakhein
    await client.run_until_disconnected()

if __name__ == "__main__":
    # Web server thread
    Thread(target=run_web, daemon=True).start()
    # Async loop
    asyncio.run(main())
