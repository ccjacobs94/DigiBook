import sys
from playwright.sync_api import sync_playwright

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://127.0.0.1:5000/new")

        # Take screenshot of the new page
        page.screenshot(path="new_page_screenshot.png")
        print("Screenshot saved to new_page_screenshot.png")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
