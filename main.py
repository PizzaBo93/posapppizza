from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from loguru import logger
from datetime import datetime
import os

logger.add(f'/tmp/logs/{datetime.now().strftime("%Y-%m-%d")}.log',
           backtrace=True,
           diagnose=True,
           colorize=True,
           level='DEBUG',
           rotation='00:00')

load_dotenv('.env', verbose=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
logger.debug(SUPABASE_URL)
logger.debug(SUPABASE_ANON_KEY)


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static/html")

@app.get("/staffapp")
async def staffapp(request: Request):
    logger.info(f"Request: {request}")
    return templates.TemplateResponse("staffapp.html",{"request":request})


@app.get("/menu")
async def menu(request: Request):
    return templates.TemplateResponse("menu.html",{"request":request})
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html",{"request":request})