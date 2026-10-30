import os
from aiohttp import web
import music as bot_module

async def health(request):
    return web.Response(text="ok", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server running on port {port}")

# Use the same loop the bot already connected on
loop = bot_module.bot.loop

# Start health server as a task on that loop
loop.create_task(start_health_server())

print("Bot starting...")
# This keeps the process alive using the original loop
bot_module.bot.run_until_disconnected()
