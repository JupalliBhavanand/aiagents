import os
import sys
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# --- SpoonOS Imports ---
root_dir = os.path.dirname(_file_)
spoon_dir = os.path.join(root_dir, "spoon-core")
if spoon_dir not in sys.path: sys.path.append(spoon_dir)

from spoon_ai.chat import ChatBot
from spoon_ai.agents.toolcall import ToolCallAgent
from spoon_ai.tools import ToolManager
from shopping_tools import VisualSearchTool, NavigateTool, AddToCartTool

load_dotenv()
app = FastAPI()

# =========================================================
# AGENT 1: THE SEARCHER (Generates UI)
# =========================================================
class SearchAgent(ToolCallAgent):
    name: str = "searcher"
    system_prompt: str = """
    You are a Visual Shopping Assistant.
    If user asks to find products, call 'search_products_visual'.
    Output the HTML EXACTLY as returned by the tool. Do not wrap in markdown.
    """
    available_tools: ToolManager = ToolManager([VisualSearchTool()])

search_agent = SearchAgent(llm=ChatBot(llm_provider="gemini", model_name="gemini-2.0-flash"))

# =========================================================
# AGENT 2: THE EXECUTOR (Runs Playwright)
# =========================================================
class ActionAgent(ToolCallAgent):
    name: str = "executor"
    system_prompt: str = """
    You are an Automation Engineer.
    1. Call 'open_browser_to_url' with the provided URL.
    2. Call 'click_add_to_cart'.
    Report success only after the click is done.
    """
    available_tools: ToolManager = ToolManager([NavigateTool(), AddToCartTool()])

action_agent = ActionAgent(llm=ChatBot(llm_provider="gemini", model_name="gemini-2.0-flash"))

# =========================================================
# API ROUTES
# =========================================================
@app.get("/", response_class=HTMLResponse)
async def index():
    if not os.path.exists("frontend/index.html"): return "<h1>Error: Create frontend/index.html</h1>"
    return HTMLResponse(open("frontend/index.html", encoding="utf-8").read())

# Endpoint 1: Handles Text Chat (Search)
@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    msg = body.get("message", "")
    try:
        resp = await search_agent.run(msg)
        return JSONResponse({"response": str(resp)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Endpoint 2: Handles Auto-Buy Triggers (Action)
@app.post("/execute_buy")
async def execute_buy(request: Request):
    body = await request.json()
    url = body.get("url", "")
    print(f"\n[🚀 TRIGGER] Starting Auto-Buy Sequence for: {url}")
    
    # We feed a synthetic prompt to the Action Agent
    prompt = f"Open browser to {url} and add the item to the cart."
    
    try:
        # This runs the Playwright sequence
        resp = await action_agent.run(prompt)
        return JSONResponse({"response": str(resp)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if _name_ == "_main_":
    uvicorn.run(app, host="127.0.0.1", port=8000)
