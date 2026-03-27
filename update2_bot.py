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

# --- [ FIX 1: INITIALIZE WITH NOW ] ---
# Isse deploy hote hi turant update nahi hoga. 2 ghante baad hi pehla check hoga.
LAST_UPDATE_TIME = datetime.now() 
IS_PROCESSING = False

app = Flask(__name__)

# --- [ FLASK ROUTES ] ---

@app.route('/')
def home():
    return "Manager Bot is Awake ⚡", 200

@app.route('/keep_alive')
def keep_alive():
    # Last update kab hua tha, ye browser pe dikhega debug ke liye
    last_t = LAST_UPDATE_TIME.strftime("%H:%M:%S")
    return f"Status: Monitoring... Last Update: {last_t} (2h Strict Guard Active)", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- [ GITHUB & TOKEN FUNCTIONS ] ---

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
    data = {"message": "Auto-Update", "content": base64.b64encode(content.encode()).decode(), "sha": sha}
    return requests.put(url, headers=headers, json=data).status_code

async def wait_for_render_deploy():
    url = f"https://api.render.com/v1/services/{SERVICE_ID}/deploys"
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
    while True:
        try:
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                status = r.json()[0]['deploy']['status']
                if status == "live": return True
                elif status in ["build_failed", "canceled"]: return False
        except: pass
        await asyncio.sleep(30)

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
                    # Expired tokens ko track karne ke liye 
                    exp_times.append(0) 
        return active_count, len(tokens), (min([x for x in exp_times if x > 0]) if any(x > 0 for x in exp_times) else 0)
    except: return 0, 0, 0

# --- [ TELEGRAM CLIENT ] ---

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

@client.on(events.NewMessage(pattern='/expire', chats=GROUP_ID))
async def expire_report(event):
    content, _ = get_github_content("token_ind.json")
    if not content: return await event.reply("❌ Error: Repo not found!")
    active, total, next_exp = analyze_tokens(content)
    msg = f"📊 **Token Status**\n━━━━━━━━━━\n✅ Active: `{active}/{total}`"
    if next_exp > 0:
        wait_m = int((next_exp-time.time())//60)
        msg += f"\n⏳ Next Expiry in: `{wait_m}m`"
    await event.reply(msg)

async def auto_updater():
    global IS_PROCESSING, LAST_UPDATE_TIME
    while True:
        try:
            # --- [ FIX 2: STRICT LOGIC CHECK ] ---
            current_time = datetime.now()
            time_passed = current_time - LAST_UPDATE_TIME
            
            # Sirf tab aage badho jab 2 ghante (7200 sec) ho chuke hon
            if time_passed >= timedelta(hours=2):
                
                content, sha = get_github_content("token_ind.json")
                if content:
                    active, total, next_exp = analyze_tokens(content)
                    now_ts = time.time()
                    
                    # Condition: Ya to koi token mar chuka ho (active < total)
                    # Ya koi agle 10 min (600s) me marne wala ho
                    is_expiring_soon = (next_exp > 0 and (next_exp - now_ts) < 600)
                    
                    if (active < total) or is_expiring_soon:
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
                                
                                if found_file:
                                    with open(found_file, 'r') as f: new_data = f.read()
                                    # Update both files
                                    for f_n in ["token_ind.json", "token_ind_visit.json"]:
                                        _, c_sha = get_github_content(f_n)
                                        update_github(f_n, new_data, c_sha)
                                    
                                    LAST_UPDATE_TIME = datetime.now()
                                    await client.send_message(GROUP_ID, "✅ **Auto-Update Done!**\nLogic: Expiry reached & 2h gap maintained.")
                                    
                                    if await wait_for_render_deploy():
                                        await client.send_message(GROUP_ID, "🚀 **BOT REDEPLOYED & LIVE**")
                                    
                                    if os.path.exists(found_file):
                                        os.remove(found_file)
                            IS_PROCESSING = False
                    else:
                        print(f"Update Skipped: Tokens are healthy. Next check in 10 mins.")
            else:
                remaining = timedelta(hours=2) - time_passed
                print(f"Guard Active: Waiting {str(remaining).split('.')[0]} more.")

        except Exception as e:
            print(f"Error: {e}")
            IS_PROCESSING = False
        
        # Har 10 minute me check karega ki kya 2 ghante poore hue?
        await asyncio.sleep(600)

async def start_bot_and_loop():
    await client.start()
    asyncio.create_task(auto_updater())
    await client.run_until_disconnected()

# --- [ GUNICORN & RUN LOGIC ] ---

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot_and_loop())
else:
    Thread(target=lambda: asyncio.run(start_bot_and_loop()), daemon=True).start()
