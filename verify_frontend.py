import asyncio
from playwright.async_api import async_playwright, expect

BASE_URL = "http://localhost:8080"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Handle dialogs
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

        # Go to admin panel
        await page.goto(f"{BASE_URL}/admin")

        # Wait for grid to load
        await page.wait_for_selector("#pms-grid")

        # Screenshot 1: Empty Grid
        await page.screenshot(path="/home/jules/verification/1_grid_empty.png")

        # Create a room if needed (assuming 101 exists from startup script)

        # Click on a cell to create booking (Room 101, Today)
        # Find cell for Room 101, first day (column 2, row 2)
        # We can use data attributes if available or just position
        # Grid: .cell[data-room='101'][data-date='YYYY-MM-DD']

        # Get today's date string
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        # Select cell
        cell = page.locator(f".cell[data-room='101'][data-date='{today}']")
        if await cell.count() == 0:
            print("Cell not found, maybe date mismatch?")
            # Try to find any cell with data-room='101'
            cell = page.locator(".cell[data-room='101']").first

        await cell.click()

        # Wait for modal
        await expect(page.locator("#booking-modal")).to_be_visible()

        # Fill booking details
        await page.fill("#b-guest", "Test Guest")

        # Set 3 days duration
        # Checkin is today, set Checkout to today + 3 days
        # This might be tricky with date picker input format, usually YYYY-MM-DD
        # We can use JS to set value or type
        from datetime import timedelta
        checkin_date = datetime.strptime(today, "%Y-%m-%d")
        checkout_date = checkin_date + timedelta(days=3)
        checkout_str = checkout_date.strftime("%Y-%m-%d")

        await page.fill("#b-checkout", checkout_str)

        # Verify "Paid" field exists
        await expect(page.locator("#b-paid-amount")).to_be_visible()

        # Enter payment
        await page.fill("#b-paid-amount", "1000")

        # Verify calculations
        # Cost per night is default (3000). 3 nights = 9000. Paid 1000. Remaining 8000.
        # Note: JS uses Math.round for diffDays.
        # Checkin: 00:00, Checkout: 00:00 + 3 days. diff = 3 days.

        # Wait for calc to update (onchange event)
        # We might need to trigger change event manually if fill doesn't
        await page.locator("#b-paid-amount").evaluate("el => el.dispatchEvent(new Event('change'))")
        await page.locator("#b-checkout").evaluate("el => el.dispatchEvent(new Event('change'))")

        await expect(page.locator("#calc-total")).to_have_text("9000") # 3 * 3000
        await expect(page.locator("#calc-remaining")).to_have_text("8000")

        # Screenshot 2: Modal with payment
        await page.screenshot(path="/home/jules/verification/2_modal_payment.png")

        # Save
        await page.click("text=Сохранить")

        # Wait for modal to close
        await expect(page.locator("#booking-modal")).to_be_hidden()

        # Wait for grid reload
        await page.wait_for_timeout(1000)

        # Screenshot 3: Grid with 3-day booking
        await page.screenshot(path="/home/jules/verification/3_grid_with_booking.png")

        # Click the booking bar to edit
        await page.locator(".booking-bar", has_text="Test Guest").click()

        # Wait for modal
        await expect(page.locator("#booking-modal")).to_be_visible()

        # Verify paid amount persisted
        paid_val = await page.locator("#b-paid-amount").input_value()
        assert paid_val == "1000"

        # Update payment
        await page.fill("#b-paid-amount", "9000")
        await page.locator("#b-paid-amount").evaluate("el => el.dispatchEvent(new Event('change'))")

        await expect(page.locator("#calc-remaining")).to_have_text("0")

        # Save
        await page.click("text=Сохранить")
        await expect(page.locator("#booking-modal")).to_be_hidden()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
