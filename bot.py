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
TOKEN = "8353595718:AAEN6_8rF3feUhWOzgulM2Ns_HLYI2c45bw" # Placeholder
ADMIN_ID = int(getenv("ADMIN_ID", 627977881))
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8080
BASE_URL = "https://divinely-golden-potoroo.cloudpub.ru"

dp = Dispatcher()

# --- Web Server Handlers ---

BASE_DIR = Path(__file__).parent

async def handle_guest_page(request):
    return web.FileResponse(BASE_DIR / 'static' / 'guest_index.html')

async def handle_admin_page(request):
    return web.FileResponse(BASE_DIR / 'static' / 'admin_pms.html')

# --- API Endpoints ---

# Bookings
async def handle_get_bookings(request):
    bookings = await db.get_bookings()
    return web.json_response([dict(b) for b in bookings])

async def handle_add_booking(request):
    data = await request.json()
    await db.add_booking(data['room_number'], data['guest_name'], data['check_in'], data['check_out'])
    return web.json_response({"status": "ok"})

async def handle_delete_booking(request):
    data = await request.json()
    await db.delete_booking(data['id'])
    return web.json_response({"status": "ok"})

# Rooms
async def handle_get_rooms(request):
    rooms = await db.get_rooms()
    return web.json_response([dict(r) for r in rooms])

async def handle_add_room(request):
    data = await request.json()
    await db.add_room(data['number'], data['type'], data['price'], "")
    return web.json_response({"status": "ok"})

async def handle_delete_room(request):
    data = await request.json()
    await db.delete_room(data['id'])
    return web.json_response({"status": "ok"})

# Menu
async def handle_get_menu(request):
    menu = await db.get_menu_items()
    return web.json_response([dict(m) for m in menu])

async def handle_add_menu(request):
    data = await request.json()
    await db.add_menu_item(data['name'], data['price'], "", data['category'])
    return web.json_response({"status": "ok"})

async def handle_delete_menu(request):
    data = await request.json()
    await db.delete_menu_item(data['id'])
    return web.json_response({"status": "ok"})

# --- Bot Handlers ---

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
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
    if message.from_user.id != ADMIN_ID:
        await message.answer("Доступ запрещен.")
        return

    web_app_url = f"{BASE_URL}/admin"
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 PMS Панель", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    await message.answer("Панель администратора", reply_markup=kb)

@dp.message(F.web_app_data)
async def handle_web_app_data(message: Message, bot: Bot):
    data = json.loads(message.web_app_data.data)

    if data['type'] == 'order':
        # Save to DB
        order_id = await db.save_order(message.from_user.id, data['items'], data['total_price'])

        # Reply to User
        await message.answer(f"✅ Заказ #{order_id} принят! Оплата на кассе.\nСумма: {data['total_price']} ₽")

        # Notify Admin
        room = data.get('room', '???')
        items_str = ""
        for k, v in data['items'].items():
            items_str += f"- {v['name']} x{v['qty']} ({v['price']*v['qty']}₽)\n"

        admin_text = (
            f"🔔 <b>Новый заказ!</b>\n"
            f"Комната: {room}\n"
            f"Гость: @{message.from_user.username or message.from_user.id}\n\n"
            f"{items_str}\n"
            f"<b>Итого: {data['total_price']} ₽</b>"
        )
        try:
            await bot.send_message(ADMIN_ID, admin_text)
        except Exception as e:
            logging.error(f"Failed to notify admin: {e}")

    elif data['type'] == 'feedback':
        # Save Review
        await db.add_review(message.from_user.id, data['rating'], data['text'])

        # Reply to User
        if data['rating'] >= 4:
            await message.answer("Спасибо за высокую оценку! Будем рады видеть вас снова.")
        else:
            await message.answer("Спасибо за отзыв. Мы обязательно примем меры.")

        # Notify Admin
        admin_text = (
            f"💬 <b>Новый отзыв!</b>\n"
            f"От: @{message.from_user.username}\n"
            f"Оценка: {'⭐' * data['rating']}\n"
            f"Текст: {data['text']}"
        )
        try:
            await bot.send_message(ADMIN_ID, admin_text)
        except Exception as e:
            logging.error(f"Failed to notify admin: {e}")

# --- Main Execution ---

async def start_bot_safely(bot):
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Bot polling failed: {e}")

async def on_startup(app):
    await db.init_db()
    # Seed basic data if empty
    rooms = await db.get_rooms()
    if not rooms:
        await db.add_room(101, "Standard", 3000, "")
        await db.add_room(102, "Standard", 3000, "")
        await db.add_room(201, "Luxe", 5000, "")

    menu = await db.get_menu_items()
    if not menu:
        await db.add_menu_item("Завтрак Континентальный", 500, "", "food")
        await db.add_menu_item("Кофе", 150, "", "drinks")

    asyncio.create_task(start_bot_safely(app['bot']))

async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    app = web.Application()
    app['bot'] = bot

    # Routes
    app.router.add_get('/guest', handle_guest_page)
    app.router.add_get('/admin', handle_admin_page)

    # API
    app.router.add_get('/api/bookings', handle_get_bookings)
    app.router.add_post('/api/bookings', handle_add_booking)
    app.router.add_delete('/api/bookings', handle_delete_booking)

    app.router.add_get('/api/rooms', handle_get_rooms)
    app.router.add_post('/api/rooms', handle_add_room)
    app.router.add_delete('/api/rooms', handle_delete_room)

    app.router.add_get('/api/menu', handle_get_menu)
    app.router.add_post('/api/menu', handle_add_menu)
    app.router.add_delete('/api/menu', handle_delete_menu)

    app.on_startup.append(on_startup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()

    print(f"Server started at {BASE_URL}")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
