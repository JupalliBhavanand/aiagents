import os
import asyncio
import urllib.parse
from serpapi import GoogleSearch
from playwright.async_api import async_playwright
from spoon_ai.tools.base import BaseTool

# === GLOBAL STATE FOR PLAYWRIGHT AGENT ===
SHARED_BROWSER_STATE = {
    "playwright": None,
    "browser": None,
    "page": None
}

# =========================================================
# TOOL 1: VISUAL SEARCH TOOL (Fast UI Generator)
# =========================================================
class VisualSearchTool(BaseTool):
    name: str = "search_products_visual"
    description: str = "Searches Google and returns HTML Product Cards."
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Product search query"}
        },
        "required": ["query"]
    }

    async def execute(self, query: str):
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key: return "<div>Error: SERPAPI_KEY missing.</div>"

        print(f"🤖 [VISUAL SEARCH] Searching for: {query}")
        
        # We request 10 just to be safe, but we limit to 6 in the loop below
        params = {
            "api_key": api_key, "engine": "google_shopping", "q": query,
            "google_domain": "google.com", "gl": "us", "hl": "en", "num": 10
        }

        try:
            search = await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
            results = search.get("shopping_results", [])
        except Exception as e:
            return f"Search Error: {e}"

        if not results: return "No products found."

        # --- GENERATE HTML CARDS ---
        html_output = "<div class='grid-container'>"
        
        # === NEW LOGIC: LIMIT TO 6 CARDS ===
        count = 0 
        
        for p in results:
            if count >= 6: break  # <--- STOPS LOOP AFTER 6 VALID ITEMS
            
            img = p.get("thumbnail", "")
            title = p.get("title", "Unknown")
            price = p.get("price", "Check Site")
            source = p.get("source", "Web")
            
            # Get the link
            raw_link = p.get("link") or p.get("product_link")
            if not raw_link: continue # Skip items without links
            
            # Count this as a valid item
            count += 1 
            
            # Encode link for safety
            encoded_link = urllib.parse.quote(raw_link)
            
            html_output += f"""
            <div class="card">
                <div class="image-container"><img src="{img}" alt="{title}"></div>
                <div class="meta">
                    <div class="title">{title}</div>
                    <div class="price">{price}</div>
                    <div class="store">{source}</div>
                    <button class="buy-btn" onclick="triggerAutoBuy('{encoded_link}')">
                        Auto-Buy 🤖
                    </button>
                </div>
            </div>
            """
        html_output += "</div>"
        return html_output

# =========================================================
# TOOL 2: RESOLVE & NAVIGATE TOOL (The Fix)
# =========================================================
class NavigateTool(BaseTool):
    name: str = "open_browser_to_url"
    description: str = "Resolves redirects silently, then opens visible browser to the clean URL."
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL (dirty or clean) to visit"}
        },
        "required": ["url"]
    }

    async def execute(self, url: str):
        decoded_url = urllib.parse.unquote(url)
        print(f"\n[🌐 NAVIGATOR] Received Request for: {decoded_url[:40]}...")
        
        # === STEP 1: HEADLESS RESOLVE (The Missing Logic) ===
        # If it's a google link, we clean it first so the visible browser doesn't get stuck
        clean_url = decoded_url
        if "google.com" in decoded_url:
            print("[🕵️ RESOLVER] Detected Google Link. Resolving in background...")
            clean_url = await self.resolve_url_headless(decoded_url)
            print(f"[✅ RESOLVER] Clean URL found: {clean_url}")
        
        # === STEP 2: LAUNCH VISIBLE BROWSER ===
        print(f"[🚀 LAUNCH] Opening Visible Browser to: {clean_url}")
        
        if SHARED_BROWSER_STATE["playwright"] is None:
            p = await async_playwright().start()
            SHARED_BROWSER_STATE["playwright"] = p
            # Visible Browser
            browser = await p.chromium.launch(headless=False, slow_mo=1000, args=["--disable-blink-features=AutomationControlled"])
            SHARED_BROWSER_STATE["browser"] = browser
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()
            SHARED_BROWSER_STATE["page"] = page
        
        page = SHARED_BROWSER_STATE["page"]
        
        try:
            await page.goto(clean_url, timeout=60000, wait_until="domcontentloaded")
            # Cookie Buster
            try: await page.get_by_text("Accept", exact=True).click(timeout=2000)
            except: pass
            
            return f"✅ Browser Opened. Navigated to: {clean_url}"
        except Exception as e:
            return f"Navigation Error: {e}"

    # --- The Helper Function from previous architecture ---
    async def resolve_url_headless(self, dirty_url):
        async with async_playwright() as p:
            # Headless = True (Invisible)
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            try:
                await page.goto(dirty_url, timeout=30000, wait_until="domcontentloaded")
                
                # If stuck on Google Redirect page
                if "google.com" in page.url:
                    # Try to extract from link href first (Fastest)
                    try:
                        link = page.locator("a[href*='url?q=']").first
                        if await link.count() > 0:
                            raw = await link.get_attribute("href")
                            # Parse /url?q=https://target.com...
                            parsed = urllib.parse.urlparse(raw)
                            clean = urllib.parse.parse_qs(parsed.query).get("q", [None])[0]
                            if clean: return clean
                    except: pass
                    
                    # Fallback: Click and wait for redirect
                    async with page.context.expect_page() as new_page_info:
                         await page.locator(".sh-osd__offer-row").first.click()
                    new_page = await new_page_info.value
                    await new_page.wait_for_load_state("domcontentloaded")
                    return new_page.url
                
                return page.url
            except:
                return dirty_url # If resolve fails, return original
            finally:
                await browser.close()

# =========================================================
# TOOL 3: CLICKER AGENT (Adds to Cart)
# =========================================================
class AddToCartTool(BaseTool):
    name: str = "click_add_to_cart"
    description: str = "Clicks 'Add to Cart' on the open page."
    
    # === THE FIX IS HERE: No trailing comma, valid schema ===
    parameters: dict = {
        "type": "object",
        "properties": {}
    }

    async def execute(self):
        page = SHARED_BROWSER_STATE["page"]
        if not page: return "Error: No browser open."
        
        print(f"\n[🛒 AGENT 3] Hunting for 'Add to Cart' button...")
        
        selectors = [
            "#add-to-cart-button", "#add-to-cart-button-ubb",
            "[data-automation-id='add-to-cart']", "button[name='add']",
            "button:has-text('Add to Cart')", "button:has-text('Add to Bag')",
            "form[action*='/cart/add'] button", ".add-to-cart"
        ]
        
        try:
            clicked = False
            for selector in selectors:
                if await page.locator(selector).first.is_visible():
                    print(f"[🛒 AGENT 3] Clicking: {selector}")
                    await page.locator(selector).first.click(force=True)
                    clicked = True
                    break
            
            if not clicked:
                return "❌ FAILED: Could not find 'Add to Cart' button."

            print("[✅ DONE] Item added. Waiting 60s for demo.")
            await asyncio.sleep(5)
            return "Success: Item added to cart."
            
        except Exception as e:
            return f"Click Error: {e}"
