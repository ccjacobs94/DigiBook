from playwright.sync_api import sync_playwright
import time
import os

def test_vbr_warning():
    os.makedirs('library', exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Start server in background
        import subprocess
        server = subprocess.Popen(['python', 'app.py'])
        time.sleep(2) # wait for server to start

        try:
            # We need to set a local storage value that implies a long saved position
            # for a book that has a short duration.
            # But first we need to open the page to set local storage
            page.goto("http://127.0.0.1:5000/")
            # Set up the condition: we need a book_name. Let's use 'testbook'
            # To do that, let's create a dummy mp3 in library/
            subprocess.run(['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '1', '-q:a', '9', '-acodec', 'libmp3lame', 'library/testbook.mp3'], stderr=subprocess.DEVNULL)

            page.goto("http://127.0.0.1:5000/")

            # Now set the local storage before going to listen page
            page.evaluate("""() => {
                localStorage.setItem('audiobook_position_testbook.mp3', '3600'); // 1 hour
            }""")

            # Go to listen page
            page.goto("http://127.0.0.1:5000/listen/testbook.mp3")

            # Wait for the loadedmetadata event which triggers the check
            # We can wait for the warning to become visible
            page.wait_for_selector('#vbrWarning', state='visible', timeout=5000)

            # Take screenshot
            page.screenshot(path="listen_ui_verify.png")
            print("Screenshot saved to listen_ui_verify.png")
        finally:
            server.terminate()
            browser.close()

if __name__ == "__main__":
    test_vbr_warning()
