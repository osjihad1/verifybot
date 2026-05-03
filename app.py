import os
import discord
from discord.ext import commands
from discord import app_commands
from quart import Quart, request
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import threading
from datetime import datetime

# --- Configuration ---
# Render Environment Variables থেকে এগুলো অটোমেটিক আসবে
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# আপনার দেওয়া রেন্ডার ইউআরএল
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
        intents.members = True  # মেম্বারদের রোল দেওয়ার জন্য এটি জরুরি
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # স্ল্যাশ কমান্ড সিঙ্ক করা
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
        # এক্সচেঞ্জ কোড ফর টোকেন (Access & Refresh Token)
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
            # ইউজারের আইডি এবং তথ্য বের করা
            headers = {'Authorization': f'Bearer {access_token}'}
            async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
                user_info = await resp.json()
                user_id = user_info.get('id')
                username = user_info.get('username')

                # MongoDB-তে পার্মানেন্টলি সেভ করা (ভবিষ্যতে ব্যাকআপের জন্য)
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
                return f"✅ Verification Successful, {username}! You can close this window now."
        
    return "❌ Verification Failed. Please try again.", 400

# --- Slash Command: /verify ---
@bot.tree.command(name="verify", description="Get verified and access all channels")
async def verify(interaction: discord.Interaction):
    # অথোরাইজেশন ইউআরএল (Scopes: identify এবং guilds.join)
    auth_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')}"
        f"&response_type=code&scope=identify%20guilds.join"
    )
    
    embed = discord.Embed(
        title="🛡️ Member Verification",
        description=(
            "To gain full access to the server, please click the button below to verify your account.\n\n"
            "**Why verify?**\n"
            "✅ Protection against raids\n"
            "✅ Member backup status\n"
            "✅ Access to hidden channels"
        ),
        color=0x2b2d31
    )
    # আপনার আগের দেওয়া সেই গিফ ইমেজটি এখানে ব্যবহার করা হয়েছে
    embed.set_image(url="https://i.imgur.com/fpdYZ4d.gif")
    embed.set_footer(text="Shadow Verify System • Secure & Fast")

    view = discord.ui.View()
    button = discord.ui.Button(
        label="Verify Now", 
        url=auth_url, 
        style=discord.ButtonStyle.link,
        emoji="✅"
    )
    view.add_item(button)
    
    await interaction.response.send_message(embed=embed, view=view)

# --- Background Web Server with Port Binding Fix ---
def run_web():
    # Render-এর দেওয়া ডাইনামিক পোর্ট ধরা (PORT না থাকলে ডিফল্ট ১০০০০)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # ওয়েব সার্ভার আলাদা থ্রেডে চালানো
    threading.Thread(target=run_web, daemon=True).start()
    # ডিসকর্ড বট চালানো
    bot.run(BOT_TOKEN)
