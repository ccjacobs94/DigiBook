import sys
import time
import subprocess
from playwright.sync_api import sync_playwright

def main():
    # Start the flask server in the background
    flask_process = subprocess.Popen(["python", "app.py"])
    time.sleep(2) # Give it time to start

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to index
            page.goto("http://localhost:5000/")

            # Create a new book session to get to the rip page
            page.goto("http://localhost:5000/new")
            page.fill("input[name='book_name']", "Test_Book")
            page.click("button[type='submit']")

            # Wait for the rip page to load
            page.wait_for_selector("#auto_mode_toggle")

            # Check initial state (manual mode)
            print("Initial state:")
            print("Manual controls visible:", page.is_visible("#manual_controls"))
            print("Auto controls visible:", page.is_visible("#auto_controls"))

            # Toggle auto mode
            page.check("#auto_mode_toggle")

            # Check new state
            print("After toggling:")
            print("Manual controls visible:", page.is_visible("#manual_controls"))
            print("Auto controls visible:", page.is_visible("#auto_controls"))

            # Capture screenshot
            page.screenshot(path="auto_mode_screenshot.png")
            print("Screenshot saved to auto_mode_screenshot.png")

            browser.close()
    finally:
        flask_process.terminate()
        flask_process.wait()

if __name__ == "__main__":
    main()
