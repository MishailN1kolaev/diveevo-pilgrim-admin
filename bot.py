import asyncio
import logging
import sys
import json
from os import getenv
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.markdown import hbold
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
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
    try:
        data = await request.json()
        cost_per_night = data.get('cost_per_night', 0)
        paid_amount = data.get('paid_amount', 0)
        # Pass phone if present
        phone = data.get('phone')
        await db.add_booking(
            data['room_number'],
            data['guest_name'],
            data['check_in'],
            data['check_out'],
            cost_per_night,
            phone=phone,
            paid_amount=paid_amount
        )

        # Check if we should create/update a user for this phone
        if phone:
            existing_user = await db.get_user_by_phone(phone)
            if existing_user:
                # Issue 1: Sync user's room
                await db.add_user(existing_user['user_id'], existing_user['username'], int(data['room_number']))
                # Also ensure their ID is on the booking (add_booking already tries to do this)
            else:
                # User doesn't exist yet, will be linked when they join via bot
                pass

        return web.json_response({"status": "ok"})
    except Exception as e:
        with open('error.log', 'a') as f:
            import traceback
            f.write(f"Error: {e}\n")
            traceback.print_exc(file=f)
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_update_booking(request):
    data = await request.json()
    booking_id = data.get('id')
    if not booking_id:
        return web.json_response({"status": "error", "message": "ID missing"}, status=400)

    # Fetch old booking to check for room changes
    old_booking = await db.get_booking(booking_id)
    if not old_booking:
        return web.json_response({"status": "error", "message": "Booking not found"}, status=404)

    new_room_number = data['room_number']
    phone = data.get('phone')
    paid_amount = data.get('paid_amount', 0)

    # Update DB
    await db.update_booking(
        booking_id,
        new_room_number,
        data['guest_name'],
        data['check_in'],
        data['check_out'],
        data.get('cost_per_night', 0),
        phone,
        paid_amount
    )

    # Task 1 & 4: Notify user if room changed
    if str(old_booking['room_number']) != str(new_room_number):
        # Find user associated with this booking (via phone)
        # Prioritize the phone in the payload, or fallback to old booking phone
        target_phone = phone or old_booking['phone']
        if target_phone:
            user = await db.get_user_by_phone(target_phone)
            if user:
                user_id = user['user_id']

                # Update User's current room context
                await db.add_user(user_id, user['username'], int(new_room_number))

                # Send Notification
                bot = request.app['bot']
                try:
                    msg_text = (
                        f"ℹ️ Ваш номер был изменен на {new_room_number}.\n"
                        f"Весь расчет теперь ведется по этому номеру."
                    )
                    await bot.send_message(user_id, msg_text)
                except Exception as e:
                    logging.error(f"Failed to notify user {user_id} of room change: {e}")

    return web.json_response({"status": "ok"})

async def handle_delete_booking(request):
    data = await request.json()
    await db.delete_booking(data['id'])
    return web.json_response({"status": "ok"})

async def handle_toggle_cleaning(request):
    data = await request.json()
    booking_id = data.get('id')
    if booking_id:
        new_status = await db.toggle_booking_cleaning_status(booking_id)
        return web.json_response({"status": "ok", "is_cleaned": new_status})
    return web.json_response({"status": "error"}, status=400)

async def handle_add_service_to_booking(request):
    data = await request.json()
    booking_id = data.get('booking_id')
    items = data.get('items') # Expected dict or list
    total_price = data.get('total_price')

    if not booking_id or not items:
        return web.json_response({"status": "error", "message": "Missing data"}, status=400)

    # Get booking to find user_id (if any)
    booking = await db.get_booking(booking_id)
    if not booking:
         return web.json_response({"status": "error", "message": "Booking not found"}, status=404)

    user_id = booking['user_id'] # May be None

    # Save Order linked to Booking
    await db.save_order(user_id, items, total_price, booking_id)

    # Update Booking Extras
    await db.update_booking_extras(booking['room_number'], total_price, booking_id)

    return web.json_response({"status": "ok"})

async def handle_get_booking_orders(request):
    booking_id = request.match_info.get('id')
    if not booking_id:
        return web.json_response({"status": "error"}, status=400)

    orders = await db.get_orders_by_booking(booking_id)
    return web.json_response([dict(o) for o in orders])

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

class UserState(StatesGroup):
    waiting_for_phone = State()

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext) -> None:
    # Check if user is admin
    if message.from_user.id == ADMIN_ID:
        await show_main_menu(message, "101")
        return

    # Check if user exists and has phone
    user = await db.get_user(message.from_user.id)

    # Parse room from deep link if present
    args = message.text.split(' ')
    room = "101"
    has_deep_link = False
    if len(args) > 1:
        payload = args[1]
        if payload.startswith("room_"):
            room = payload.replace("room_", "")
            has_deep_link = True

    # Save payload room to state for later usage
    await state.update_data(room=room)

    if user and user.get('phone'):
        # User is fully registered

        # Issue 1: If no deep link, try to sync room with active booking
        if not has_deep_link:
            active_booking = await db.get_active_booking_by_user(user['user_id'])
            if active_booking:
                room = str(active_booking['room_number'])
                # Update user context
                await db.add_user(user['user_id'], user['username'], int(room))

        await show_main_menu(message, room)
    else:
        # User needs to register phone
        await message.answer(
            "Добро пожаловать! Для продолжения, пожалуйста, введите ваш номер телефона (начиная с +7).",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(UserState.waiting_for_phone)

@dp.message(UserState.waiting_for_phone)
async def handle_phone_input(message: Message, state: FSMContext):
    phone = message.text.strip()

    # Basic validation
    if not re.match(r'^\+7\d{10}$', phone):
        await message.answer("Неверный формат. Пожалуйста, введите номер в формате +7XXXXXXXXXX")
        return

    # Check if this phone is already associated with another user (or created by admin without Telegram ID?)
    # Actually, admin creates bookings with phone, but doesn't create users with Telegram ID.
    # But we might have a user entry with this phone but DIFFERENT Telegram ID? (Unlikely unless user changed accounts)
    # Or we might have a user entry with this phone and NULL Telegram ID? (We didn't implement that yet, we just query by phone)

    existing_user_by_phone = await db.get_user_by_phone(phone)

    data = await state.get_data()
    room = data.get('room', "101")

    if existing_user_by_phone:
        # If the existing user has a different Telegram ID, we have a conflict or a merge.
        # If existing_user has the same ID, we are good.
        if existing_user_by_phone['user_id'] != message.from_user.id:
            await message.answer("Этот номер уже зарегистрирован на другого пользователя. Обратитесь к администратору.")
            return

    # Register/Update User
    # First, ensure user record exists
    await db.add_user(message.from_user.id, message.from_user.full_name, int(room))
    # Then update phone
    success = await db.update_user_phone(message.from_user.id, phone)

    if success:
        # Link any existing bookings that have this phone but no user_id
        await db.link_bookings_to_user(phone, message.from_user.id)

        # Check for active booking to set correct room immediately
        active_booking = await db.get_active_booking_by_user(message.from_user.id)
        if active_booking:
             room = str(active_booking['room_number'])
             await db.add_user(message.from_user.id, message.from_user.full_name, int(room))

        await message.answer("Регистрация успешна!")
        await state.clear()
        await show_main_menu(message, room)
    else:
        await message.answer("Ошибка при сохранении номера.")

async def show_main_menu(message: Message, room: str):
    web_app_url = f"{BASE_URL}/guest?room={room}"
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛎 Открыть меню", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    await message.answer(f"Вы в комнате {room}.", reply_markup=kb)


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
        # Issue 3: Check Time for Breakfast
        has_breakfast = False
        for k, v in data['items'].items():
            if "завтрак" in v['name'].lower():
                has_breakfast = True
                break

        if has_breakfast:
            now = datetime.now()
            # 12:00 to 19:00
            if not (12 <= now.hour < 19):
                await message.answer("⛔ Заказ завтрака доступен только с 12:00 до 19:00.")
                return

        # Save to DB
        # We need booking_id for Issue 2 (link orders to booking)
        # Try to find active booking
        room_num = None
        booking_id = None
        if 'room' in data:
            try:
                room_num = int(data['room'])
                active_booking = await db.get_active_booking_by_room(room_num)
                if active_booking:
                    booking_id = active_booking['id']
            except ValueError:
                pass

        # Fetch phone for order binding
        user_phone = None
        user = await db.get_user(message.from_user.id)
        if user:
            user_phone = user.get('phone')

        order_id = await db.save_order(message.from_user.id, data['items'], data['total_price'], booking_id, phone=user_phone)

        # Update active booking extras
        if room_num:
            await db.update_booking_extras(room_num, data['total_price'], booking_id)

        # Reply to User
        await message.answer(f"✅ Заказ #{order_id} принят! Оплата на кассе.\nСумма: {data['total_price']} ₽")

        # Notify Admin
        room = data.get('room', '???')
        items_str = ""
        for k, v in data['items'].items():
            items_str += f"- {v['name']} x{v['qty']} ({v['price']*v['qty']}₽)\n"

        # Fetch user phone for admin info
        user = await db.get_user(message.from_user.id)
        phone_info = f" ({user['phone']})" if user and user.get('phone') else ""

        admin_text = (
            f"🔔 <b>Новый заказ!</b>\n"
            f"Комната: {room}\n"
            f"Гость: @{message.from_user.username or message.from_user.id}{phone_info}\n\n"
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
    app.router.add_put('/api/bookings', handle_update_booking)
    app.router.add_delete('/api/bookings', handle_delete_booking)
    app.router.add_post('/api/bookings/toggle_cleaning', handle_toggle_cleaning)
    app.router.add_post('/api/bookings/services', handle_add_service_to_booking)
    app.router.add_get('/api/bookings/{id}/orders', handle_get_booking_orders)

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
