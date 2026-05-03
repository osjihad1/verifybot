import os
import discord
from discord.ext import commands
from discord import app_commands
from quart import Quart, request, redirect
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import threading

# --- Configuration ---
# সরাসরি আইডি বা সিক্রেট না লিখে os.environ.get ব্যবহার করো
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# তোমার রেন্ডার অ্যাপের ইউআরএলটি এখানে দাও
REDIRECT_URI = "https://your-app-name.onrender.com/callback"

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
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = VerifyBot()

# --- OAuth2 Logic ---
@app.route('/callback')
async def callback():
    code = request.args.get('code')
    async with aiohttp.ClientSession() as session:
        # Exchange Code for Access Token
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

        # Get User Info
        headers = {'Authorization': f'Bearer {access_token}'}
        async with session.get('https://discord.com/api/users/@me', headers=headers) as resp:
            user_info = await resp.json()
            user_id = user_info.get('id')

        # Save to MongoDB
        await users_col.update_one(
            {"_id": user_id},
            {"$set": {"access_token": access_token}},
            upsert=True
        )

    return "✅ Verification Successful! You can close this window."

# --- Slash Command to Verify ---
@bot.tree.command(name="setup_verify", description="Send the verification button")
async def setup_verify(interaction: discord.Interaction):
    # The URL users click to authorize the bot
    auth_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds.join"
    
    embed = discord.Embed(
        title="🔒 Member Verification",
        description="Click the button below to verify your account and gain access to the server.",
        color=0x2b2d31
    )
    
    view = discord.ui.View()
    button = discord.ui.Button(label="Verify Now", url=auth_url)
    view.add_item(button)
    
    await interaction.response.send_message(embed=embed, view=view)

# --- Background Task to Run Web Server ---
def run_web():
    app.run(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.run(BOT_TOKEN)
