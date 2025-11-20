import aiosqlite
import json
from datetime import datetime

DB_NAME = "hotel.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                current_room INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                items TEXT,
                total_price REAL,
                status TEXT DEFAULT 'new',
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_number INTEGER,
                guest_name TEXT,
                check_in TEXT,
                check_out TEXT,
                status TEXT DEFAULT 'booked',
                cost_per_night REAL DEFAULT 0,
                extras_total REAL DEFAULT 0,
                paid_amount REAL DEFAULT 0
            )
        """)

        # Migrations for existing tables
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN cost_per_night REAL DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN extras_total REAL DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN paid_amount REAL DEFAULT 0")
        except Exception:
            pass

        # New Tables
        await db.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price REAL,
                description TEXT,
                category TEXT,
                is_available BOOLEAN DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER UNIQUE,
                type TEXT,
                price REAL,
                description TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                rating INTEGER,
                text TEXT,
                created_at TEXT
            )
        """)
        await db.commit()

# --- User ---
async def add_user(user_id, username, current_room):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, username, current_room)
            VALUES (?, ?, ?)
        """, (user_id, username, current_room))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"user_id": row[0], "username": row[1], "current_room": row[2]}
            return None

# --- Orders ---
async def save_order(user_id, items, total_price):
    created_at = datetime.now().isoformat()
    items_json = json.dumps(items)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO orders (user_id, items, total_price, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, items_json, total_price, created_at))
        await db.commit()
        return cursor.lastrowid

# --- Bookings ---
async def add_booking(room_number, guest_name, check_in, check_out, cost_per_night, paid_amount=0):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO bookings (room_number, guest_name, check_in, check_out, cost_per_night, paid_amount)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (room_number, guest_name, check_in, check_out, cost_per_night, paid_amount))
        await db.commit()
        return cursor.lastrowid

async def update_booking(booking_id, room_number, guest_name, check_in, check_out, cost_per_night, paid_amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE bookings
            SET room_number = ?, guest_name = ?, check_in = ?, check_out = ?, cost_per_night = ?, paid_amount = ?
            WHERE id = ?
        """, (room_number, guest_name, check_in, check_out, cost_per_night, paid_amount, booking_id))
        await db.commit()

async def update_booking_extras(room_number, amount):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        # Find active booking for this room
        # Simple logic: check_in <= today < check_out
        # Note: SQLite dates as strings work with lexicographical comparison (YYYY-MM-DD)
        async with db.execute("""
            SELECT id, extras_total FROM bookings
            WHERE room_number = ? AND check_in <= ? AND check_out > ?
            ORDER BY check_in DESC LIMIT 1
        """, (room_number, today, today)) as cursor:
            row = await cursor.fetchone()
            if row:
                booking_id = row[0]
                current_extras = row[1] or 0
                new_extras = current_extras + amount
                await db.execute("UPDATE bookings SET extras_total = ? WHERE id = ?", (new_extras, booking_id))
                await db.commit()
                return booking_id
    return None

async def get_bookings():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_booking(booking_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        await db.commit()

# --- Menu ---
async def add_menu_item(name, price, description, category):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO menu_items (name, price, description, category)
            VALUES (?, ?, ?, ?)
        """, (name, price, description, category))
        await db.commit()
        return cursor.lastrowid

async def get_menu_items():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM menu_items WHERE is_available = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_menu_item(item_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM menu_items WHERE id = ?", (item_id,))
        await db.commit()

# --- Rooms ---
async def add_room(number, type, price, description):
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            cursor = await db.execute("""
                INSERT INTO rooms (number, type, price, description)
                VALUES (?, ?, ?, ?)
            """, (number, type, price, description))
            await db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            return None # Room already exists

async def get_rooms():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rooms ORDER BY number") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_room(room_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        await db.commit()

# --- Reviews ---
async def add_review(user_id, rating, text):
    created_at = datetime.now().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO reviews (user_id, rating, text, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, rating, text, created_at))
        await db.commit()

if __name__ == "__main__":
    asyncio.run(init_db())
