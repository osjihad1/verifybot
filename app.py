import os
import discord
from discord.ext import commands
from quart import Quart, request
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import threading
from datetime import datetime

# --- Configuration ---
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
REDIRECT_URI = "https://verifybot-shjs.onrender.com/callback"

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
        await self.tree.sync()
        print(f"✅ Commands synced for {self.user}")

bot = VerifyBot()

# --- OAuth2 Logic ---
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

        if access_token:
            headers = {'Authorization': f'Bearer {access_token}'}
            async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
                user_info = await resp.json()
                user_id = user_info.get('id')
                username = user_info.get('username')

                await users_col.update_one(
                    {"_id": user_id},
                    {"$set": {
                        "username": username,
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "verified_at": datetime.utcnow()
                    }},
                    upsert=True
                )
                return f"✅ Verification Successful, {username}!"
        
    return "❌ Verification Failed.", 400

# --- Slash Command ---
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
    embed.set_image(url="https://i.imgur.com/fpdYZ4d.gif")

    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Now", url=auth_url, emoji="✅")
    view.add_item(button)
    
    await interaction.response.send_message(embed=embed, view=view)

# --- Background Web Server ---
def run_web():
    # Render-এর জন্য ডাইনামিক পোর্ট সেট করা
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # ওয়েব সার্ভার আলাদা থ্রেডে চালু করা
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    
    # এরর এড়াতে সাধারণ bot.run ব্যবহার করা হয়েছে
    bot.run(BOT_TOKEN)
