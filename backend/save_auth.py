import os
from playwright.sync_api import sync_playwright

def main():
    storage_path = os.path.join(os.path.dirname(__file__), "storage_state.json")
    print("================================================================")
    print("Google NotebookLM Session Authenticator for Sard-AI")
    print("================================================================")
    print("Launching Chrome/Edge browser window...")
    print("Please log into your Google Account in the opened browser window.")
    print("Once logged in and on the NotebookLM homepage, press ENTER here.")
    print("================================================================")

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    with sync_playwright() as p:
        browser = None
        for channel in ["chrome", "msedge", None]:
            try:
                kwargs = {
                    "headless": False,
                    "ignore_default_args": ["--enable-automation"],
                    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                }
                if channel:
                    kwargs["channel"] = channel
                browser = p.chromium.launch(**kwargs)
                print(f"[INFO] Successfully launched browser channel: {channel or 'default chromium'}")
                break
            except Exception as e:
                print(f"[WARN] Channel '{channel}' launch failed: {e}")

        if not browser:
            print("[ERROR] Could not launch Chromium browser.")
            return

        context = browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        page.goto("https://notebooklm.google.com")

        input("\n>>> Press ENTER after logging into Google in the browser window to save session...\n")

        context.storage_state(path=storage_path)
        print(f"[SUCCESS] Google authentication session saved to: {os.path.abspath(storage_path)}")
        browser.close()

if __name__ == "__main__":
    main()
