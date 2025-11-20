import time
from playwright.sync_api import sync_playwright, expect

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to Admin Panel
        page.goto("http://localhost:8080/admin")

        # Wait for grid to load
        expect(page.locator("#pms-grid")).to_be_visible()

        # 1. Create a booking for October 21st
        page.evaluate("jumpToDate('2023-10-21')")
        time.sleep(1)

        # Trigger modal
        page.evaluate("openModal(null, '101', '2023-10-21')")

        # Fill Modal
        page.fill("#b-guest", "FrontendTestGuest")
        page.fill("#b-phone", "+79991112233")

        # Verify dates in modal
        checkin_val = page.input_value("#b-checkin")
        print(f"Checkin Value in Modal: {checkin_val}")

        # Save
        page.click("button:text('Сохранить')")

        # Wait for reload
        time.sleep(2)

        # Verify it appears
        # We expect at least one cell visible
        guest_cell = page.locator(".booking-cell", has_text="FrontendTestGuest").first
        expect(guest_cell).to_be_visible()

        # Take Screenshot
        page.screenshot(path="/home/jules/verification/verification.png")
        print("Screenshot saved.")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
