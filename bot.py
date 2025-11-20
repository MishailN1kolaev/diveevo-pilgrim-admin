import asyncio
import logging
import sys
import json
from os import getenv

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.markdown import hbold
from aiohttp import web
from pathlib import Path

import database as db

# Configuration
TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11" # Placeholder
ADMIN_ID = int(getenv("ADMIN_ID", 123456789))
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080
BASE_URL = "http://localhost:8080"

dp = Dispatcher()

# --- Web Server Handlers ---

BASE_DIR = Path(__file__).resolve().parent

async def handle_guest_page(request):
    return web.FileResponse(BASE_DIR / 'static/guest_index.html')

async def handle_admin_page(request):
    return web.FileResponse(BASE_DIR / 'static/admin_pms.html')

async def handle_get_bookings(request):
    bookings = await db.get_bookings()
    # Convert rows to dicts if not already
    return web.json_response([dict(b) for b in bookings])

# --- Bot Handlers ---

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    if message.from_user.id == ADMIN_ID:
        await command_admin_handler(message)
        return

    args = message.text.split(' ')
    room = "101"
    if len(args) > 1:
        payload = args[1]
        if payload.startswith("room_"):
            room = payload.replace("room_", "")

    await db.add_user(message.from_user.id, message.from_user.full_name, int(room))

    web_app_url = f"{BASE_URL}/guest?room={room}"

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛎 Открыть меню", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )

    await message.answer(f"Добро пожаловать в отель! Вы в комнате {room}.", reply_markup=kb)

@dp.message(Command("admin"))
async def command_admin_handler(message: Message) -> None:
    web_app_url = f"{BASE_URL}/admin"
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Шахматка бронирований", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    await message.answer("Панель администратора", reply_markup=kb)

@dp.message(F.web_app_data)
async def handle_web_app_data(message: Message, bot: Bot):
    data = json.loads(message.web_app_data.data)

    if data['type'] == 'order':
        order_id = await db.save_order(message.from_user.id, data['items'], data['total_price'])
        await message.answer(f"Заказ #{order_id} принят! Сумма: {data['total_price']} ₽")

    elif data['type'] == 'feedback':
        rating = data['rating']
        if rating >= 4:
            await message.answer("Спасибо! Оставьте отзыв на картах.")
        else:
            await message.answer("Простите! Передали директору.")

    elif data['type'] == 'booking_create':
        await db.add_booking(
            data['room_number'],
            data['guest_name'],
            data['check_in'],
            data['check_out']
        )
        await message.answer(f"✅ Бронь создана: Комната {data['room_number']}, {data['guest_name']}")

    elif data['type'] == 'booking_cancel':
        await db.delete_booking(data['booking_id'])
        await message.answer(f"❌ Бронь #{data['booking_id']} удалена")

# --- Main Execution ---

async def start_bot_safely(bot):
    try:
        # Verify token logic usually happens here.
        # We skip actual polling if token is invalid to keep server alive for demo
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Bot polling failed (expected in demo without valid token): {e}")

async def on_startup(app):
    await db.init_db()
    # Start polling in background
    asyncio.create_task(start_bot_safely(app['bot']))

async def main():
    logging.basicConfig(level=logging.INFO)

    # Setup Bot
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Setup Web Server
    app = web.Application()
    app['bot'] = bot

    app.router.add_get('/guest', handle_guest_page)
    app.router.add_get('/admin', handle_admin_page)
    app.router.add_get('/api/bookings', handle_get_bookings)

    app.on_startup.append(on_startup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()

    print(f"Server started at {BASE_URL}")

    # Keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
