import os
import discord
from discord.ext import commands
from quart import Quart, request
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import asyncio
from datetime import datetime, timezone
from hypercorn.config import Config
from hypercorn.asyncio import serve

# --- Configuration ---
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
GUILD_ID = int(os.environ.get("GUILD_ID", "0"))
ROLE_ID = int(os.environ.get("ROLE_ID", "0"))
print("🔧 APP STARTING...")
REDIRECT_URI = "https://verifybot-shjs.onrender.com/callback"

print(f"🔧 Config loaded: GUILD_ID={GUILD_ID}, ROLE_ID={ROLE_ID}")

# --- Database Setup ---
cluster = AsyncIOMotorClient(MONGO_URI)
db = cluster["VerifyBot"]
users_col = db["verified_users"]

# --- Web Server Setup ---
app = Quart(__name__)

# --- Discord Bot Setup ---
class VerifyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        try:
            await self.tree.sync()
            print(f"✅ Commands synced for {self.user}")
        except Exception as e:
            print(f"❌ Command sync failed: {e}")

    async def on_ready(self):
        print(f"🤖 Bot is ready! Logged in as {self.user}")
        print(f"🏠 Guild ID: {GUILD_ID}, Role ID: {ROLE_ID}")

bot = VerifyBot()

# --- OAuth2 Callback Route ---
@app.route('/callback')
async def callback():
    code = request.args.get('code')
    if not code:
        return "❌ Error: No code provided.", 400

    async with aiohttp.ClientSession() as session:
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        async with session.post('https://discord.com/api/oauth2/token', data=data, headers=headers) as resp:
            token_data = await resp.json()
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')

        if not access_token:
            return "❌ Verification Failed: Could not get access token.", 400

        auth_headers = {'Authorization': f'Bearer {access_token}'}
        async with session.get('https://discord.com/api/users/@me', headers=auth_headers) as resp:
            user_info = await resp.json()
            user_id = user_info.get('id')
            username = user_info.get('username')

        if not user_id:
            return "❌ Verification Failed: Could not get user info.", 400

        await users_col.update_one(
            {"_id": user_id},
            {"$set": {
                "username": username,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "verified_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        print(f"📝 User saved: {username} ({user_id})")

        try:
            guild = bot.get_guild(GUILD_ID)
            if guild is None:
                print(f"⚠️ Guild not in cache, fetching...")
                guild = await bot.fetch_guild(GUILD_ID)

            print(f"✅ Guild found: {guild.name}")

            member = guild.get_member(int(user_id))
            if member is None:
                print(f"⚠️ Member not in cache, fetching...")
                member = await guild.fetch_member(int(user_id))

            print(f"✅ Member found: {member.name}")

            role = guild.get_role(ROLE_ID)
            print(f"🔍 Role found: {role}")

            if role and member:
                await member.add_roles(role, reason="Verified via OAuth2")
                print(f"✅ Role given to {username} ({user_id})")
            else:
                print(f"⚠️ Role or member not found: role={role}, member={member}")

        except Exception as e:
            print(f"❌ Failed to assign role to {username}: {e}")

    success_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verified!</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d1117;font-family:'Segoe UI',Arial,sans-serif}}
.page{{min-height:100vh;background:radial-gradient(ellipse at top left,#1a1b2e 0%,#0d1117 60%);display:flex;align-items:center;justify-content:center;padding:2rem;position:relative;overflow:hidden}}
.glow{{position:absolute;border-radius:50%;filter:blur(80px);opacity:.15;pointer-events:none}}
.g1{{width:400px;height:400px;background:#5865F2;top:-100px;left:-100px}}
.g2{{width:400px;height:400px;background:#57F287;bottom:-100px;right:-100px}}
.card{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:3rem 2.5rem;text-align:center;max-width:420px;width:100%;position:relative;backdrop-filter:blur(20px)}}
.card::before{{content:'';position:absolute;inset:0;border-radius:20px;padding:1px;background:linear-gradient(135deg,rgba(88,101,242,.4),rgba(87,242,135,.2),transparent);-webkit-mask:linear-gradient(#fff 0 0) content-box,linear-gradient(#fff 0 0);-webkit-mask-composite:destination-out;mask-composite:exclude;pointer-events:none}}
.icon-wrap{{width:80px;height:80px;border-radius:50%;background:rgba(87,242,135,.12);border:2px solid rgba(87,242,135,.3);display:flex;align-items:center;justify-content:center;margin:0 auto 1.5rem;animation:pop .5s ease}}
@keyframes pop{{0%{{transform:scale(.5);opacity:0}}70%{{transform:scale(1.1)}}100%{{transform:scale(1);opacity:1}}}}
.checkmark{{width:36px;height:36px;stroke:#57F287;stroke-width:3;fill:none;stroke-dasharray:60;stroke-dashoffset:60;animation:draw .6s .3s ease forwards}}
@keyframes draw{{to{{stroke-dashoffset:0}}}}
.badge{{display:inline-flex;align-items:center;gap:6px;background:rgba(88,101,242,.15);border:1px solid rgba(88,101,242,.3);border-radius:20px;padding:4px 12px;font-size:12px;color:#8b96f8;letter-spacing:.5px;text-transform:uppercase;margin-bottom:1.2rem}}
.dot{{width:6px;height:6px;border-radius:50%;background:#5865F2;animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.5;transform:scale(.8)}}}}
h1{{font-size:26px;font-weight:700;color:#fff;margin-bottom:.5rem}}
.uname{{color:#57F287}}
.sub{{font-size:14px;color:rgba(255,255,255,.4);line-height:1.6;margin-bottom:1.5rem}}
.divider{{height:1px;background:rgba(255,255,255,.06);margin:1.2rem 0}}
.row{{display:flex;align-items:center;justify-content:space-between;font-size:13px;margin-bottom:10px}}
.lbl{{color:rgba(255,255,255,.35)}}
.val{{color:rgba(255,255,255,.7);font-weight:500}}
.pill{{background:rgba(87,242,135,.12);color:#57F287;border-radius:20px;padding:2px 10px;font-size:12px}}
.bar{{height:3px;background:rgba(255,255,255,.06);border-radius:2px;margin-top:1.5rem;overflow:hidden}}
.fill{{height:100%;width:100%;background:linear-gradient(90deg,#5865F2,#57F287);animation:shrink 3s linear forwards}}
@keyframes shrink{{to{{width:0%}}}}
.hint{{font-size:12px;color:rgba(255,255,255,.2);margin-top:.6rem}}
</style>
</head>
<body>
<div class="page">
<div class="glow g1"></div>
<div class="glow g2"></div>
<div class="card">
  <div class="badge"><div class="dot"></div>Server Access Granted</div>
  <div class="icon-wrap">
    <svg class="checkmark" viewBox="0 0 24 24"><polyline points="4,12 9,17 20,7"/></svg>
  </div>
  <h1>Welcome, <span class="uname">{username}!</span></h1>
  <p class="sub">Your identity has been verified.<br>You now have full access to the server.</p>
  <div class="divider"></div>
  <div class="row"><span class="lbl">Status</span><span class="pill">Verified Member</span></div>
  <div class="row"><span class="lbl">Access level</span><span class="val">Member</span></div>
  <div class="row"><span class="lbl">Username</span><span class="val">{username}</span></div>
  <div class="bar"><div class="fill"></div></div>
  <p class="hint">This tab will close automatically...</p>
</div>
</div>
<script>setTimeout(()=>window.close(),3000)</script>
</body>
</html>"""
    return success_html

@app.route('/')
async def index():
    return "✅ VerifyBot is running!", 200

@bot.tree.command(name="verify", description="Get verified and gain access")
async def verify(interaction: discord.Interaction):
    auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')}"
        f"&response_type=code&scope=identify%20guilds.join"
    )

    embed = discord.Embed(
        title="🛡️ Member Verification",
        description="To access the server, click the button below and verify your account.",
        color=0x2b2d31
    )
    embed.set_image(url="https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExdGc0NGpvMndvNTVmNDZwa243b2ZlczdyZTZxcTdzZmZ6cXkwZjJjeSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/uXiMMGuqzVfWziFdSP/giphy.gif")

    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Now", url=auth_url, emoji="✅")
    view.add_item(button)

    await interaction.response.send_message("✅", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)

# --- Self-Ping to prevent Render sleep ---
async def self_ping():
    await bot.wait_until_ready()
    url = "https://verifybot-shjs.onrender.com/"
    while not bot.is_closed():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    print(f"🏓 Self-ping: {resp.status}")
        except Exception as e:
            print(f"⚠️ Self-ping failed: {e}")
        await asyncio.sleep(300)  # ping every 5 minutes

async def main():
    config = Config()
    port = int(os.environ.get("PORT", 10000))
    config.bind = [f"0.0.0.0:{port}"]
    print(f"🌐 Starting web server on port {port}...")

    await asyncio.gather(
        serve(app, config),
        bot.start(BOT_TOKEN),
        self_ping()
    )

if __name__ == "__main__":
    asyncio.run(main())
