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
                status TEXT DEFAULT 'booked'
            )
        """)
        await db.commit()

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

async def add_booking(room_number, guest_name, check_in, check_out):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO bookings (room_number, guest_name, check_in, check_out)
            VALUES (?, ?, ?, ?)
        """, (room_number, guest_name, check_in, check_out))
        await db.commit()
        return cursor.lastrowid

async def get_bookings():
    # For MVP, we return all bookings. In production, filter by date range.
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_booking(booking_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        await db.commit()

# Test script
if __name__ == "__main__":
    import asyncio
    async def test():
        await init_db()
        await add_user(123, "test_user", 101)
        print("User added")
        await add_booking(101, "John Doe", "2023-10-26", "2023-10-28")
        print("Booking added")
        bookings = await get_bookings()
        print("Bookings:", bookings)

    asyncio.run(test())
