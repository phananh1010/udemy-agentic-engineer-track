from playwright.async_api import async_playwright

from langchain.tools import tool
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper

from langchain_experimental.tools import PythonREPLTool

import os
import requests
from dotenv import load_dotenv
load_dotenv()

pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_user = os.getenv("PUSHOVER_USER")
pushover_url = "https://api.pushover.net/1/messages.json"
serper = GoogleSerperAPIWrapper()

async def playwright_tools():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
    return toolkit.get_tools(), browser, playwright

@tool("search")
def tool_search(query: str) -> str:
    """Use to perform external web search to retrieve information online"""
    print (f"Performing web search...")
    return serper.run(query)

@tool("push")
def tool_push(msg: str):
    "Use this tool when asked to send notification or email or message to user's devices"
    requests.post(pushover_url, data={"token": pushover_token, "user": pushover_user, "message": msg})
    print (f"Message {msg[:5]} is pushed")
    return 

def get_file_tools():
    toolkit = FileManagementToolkit(root_dir="sandbox")
    return toolkit.get_tools()

async def other_tools():
    """create and return list of other tools"""
    file_tools = get_file_tools()
    wikipedia = WikipediaAPIWrapper()
    tool_wiki = WikipediaQueryRun(api_wrapper=wikipedia)
    python_repl = PythonREPLTool()
    return file_tools + [tool_push, tool_search, python_repl, tool_wiki]


    