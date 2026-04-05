from playwright.sync_api import sync_playwright
import time
import os

def test_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Generate a dummy MP3 if library is empty to ensure we have a book to view
        os.system('mkdir -p library')
        if not os.path.exists('library/verify_test.mp3'):
            os.system('ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t 120 -q:a 9 -acodec libmp3lame library/verify_test.mp3 2>/dev/null')

        # Visit library
        print("Visiting library...")
        page.goto('http://127.0.0.1:5000/')
        page.wait_for_selector('h1')

        # Visit Listen page
        print("Visiting listen page...")
        page.goto('http://127.0.0.1:5000/listen/verify_test.mp3')
        page.wait_for_selector('#playbackSpeed')

        # Drop a bookmark
        print("Dropping bookmark...")
        page.click('#addBookmarkBtn')

        # Set sleep timer
        print("Setting sleep timer...")
        page.select_option('#sleepTimer', '15')

        # Screenshot listen page
        print("Taking listen page screenshot...")
        page.screenshot(path='listen_ui_verify.png', full_page=True)

        # Trigger loadedmetadata by playing briefly
        print("Playing audio briefly to trigger metadata and position save...")
        page.evaluate("document.getElementById('audioPlayer').play()")
        time.sleep(2)
        page.evaluate("document.getElementById('audioPlayer').pause()")
        time.sleep(1)

        # Visit library again
        print("Visiting library again...")
        page.goto('http://127.0.0.1:5000/')
        page.wait_for_selector('.book')

        # Wait a bit for JS to execute
        time.sleep(1)

        # Screenshot library page
        print("Taking library page screenshot...")
        page.screenshot(path='library_ui_verify.png', full_page=True)

        browser.close()

if __name__ == '__main__':
    test_ui()
