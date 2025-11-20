import pytest
import asyncio
import database as db
from datetime import datetime, timedelta
import os

@pytest.mark.asyncio
async def test_db_schema():
    # Ensure DB is init
    await db.init_db()

    async with db.aiosqlite.connect(db.DB_NAME) as conn:
        cursor = await conn.execute("PRAGMA table_info(bookings)")
        columns = await cursor.fetchall()
        col_names = [c[1] for c in columns]

        assert 'cost_per_night' in col_names
        assert 'extras_total' in col_names

@pytest.mark.asyncio
async def test_booking_extras():
    await db.init_db()

    # Create room
    await db.add_room(999, "Test", 1000, "")

    # Create booking
    check_in = datetime.now().strftime("%Y-%m-%d")
    check_out = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

    booking_id = await db.add_booking(999, "Tester", check_in, check_out, 1000)
    assert booking_id is not None

    # Update extras
    updated_id = await db.update_booking_extras(999, 500)
    assert updated_id == booking_id

    bookings = await db.get_bookings()
    b = next(b for b in bookings if b['id'] == booking_id)
    assert b['extras_total'] == 500

    # Update extras again
    updated_id = await db.update_booking_extras(999, 250)
    bookings = await db.get_bookings()
    b = next(b for b in bookings if b['id'] == booking_id)
    assert b['extras_total'] == 750

    # Clean up
    await db.delete_booking(booking_id)
    room = (await db.get_rooms())[-1]
    await db.delete_room(room['id'])
