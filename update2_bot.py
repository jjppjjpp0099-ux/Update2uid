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
LAST_UPDATE_TIME = datetime.now() - timedelta(hours=2) 
IS_PROCESSING = False

app = Flask(__name__)

# --- [ FLASK ROUTES ] ---
@app.route('/')
def home():
    return "Manager Bot is Awake ⚡", 200

@app.route('/keep_alive')
def keep_alive():
    last_t = LAST_UPDATE_TIME.strftime("%H:%M:%S")
    return f"Status: Monitoring... Last Update: {last_t}", 200

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
    except: pass
    return None, None

def update_github(file_path, content, sha=None):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {"message": "Auto-Update", "content": base64.b64encode(content.encode()).decode(), "sha": sha}
    try:
        return requests.put(url, headers=headers, json=data).status_code
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
                else:
                    exp_times.append(0)
        return active_count, len(tokens), (min([x for x in exp_times if x > 0]) if any(x > 0 for x in exp_times) else 0)
    except: return 0, 0, 0

# --- [ TELEGRAM CLIENT SETUP ] ---
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# UPDATED HANDLER: Isme 'incoming=True' aur 'func' add kiya hai taaki koi miss na ho
@client.on(events.NewMessage(pattern='/expire', incoming=True))
async def expire_report(event):
    # Check if message is from your group
    if event.chat_id != GROUP_ID:
        return
    
    print(f"DEBUG: /expire command detected in chat {event.chat_id}")
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
                if active == 0:
                    current_time = datetime.now()
                    if (current_time - LAST_UPDATE_TIME) >= timedelta(hours=2):
                        if not IS_PROCESSING:
                            IS_PROCESSING = True
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
                                    await client.send_message(GROUP_ID, "✅ **Auto-Update Success!**")
                                    if os.path.exists(found_file): os.remove(found_file)
                                else:
                                    LAST_UPDATE_TIME = datetime.now()
                            IS_PROCESSING = False
                else:
                    print(f"Monitoring: {active}/{total} active.")
            
        except Exception as e:
            print(f"Loop Error: {e}")
            IS_PROCESSING = False
        await asyncio.sleep(300)

async def main():
    await client.start()
    print("Bot is LIVE and Listening...")
    # Dono loops ko start karna zaroori hai
    await asyncio.gather(
        client.run_until_disconnected(),
        auto_updater()
    )

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
