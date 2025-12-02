import os
import time
from datetime import datetime
from typing import Optional
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Response, Cookie, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from model.login import Login
from model.order import Order
from model.user import User

load_dotenv('.env', verbose=True)

logger.add(f'{datetime.now().strftime("%Y-%m-%d")}.log',
           backtrace=True,
           diagnose=True,
           colorize=True,
           level='DEBUG',
           compression='zip',
           rotation='1 day')

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "change_me_now")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
JWT_EXP_MIN = int(os.getenv("JWT_EXP_MIN", "60"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

logger.info(f'url:  {SUPABASE_URL}')
logger.info( f'key: {SUPABASE_ANON_KEY}')


if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    logger.error('Supabase URL or API key not set')
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in env file")

ROLE_PERMISSIONS = {
    "admin": {"canCreateOrder": True, "canEditOrder": True, "canViewOrders": True, "canPayOrder": True, "canViewReports": True, "canManageCash": True},
    "manager": {"canCreateOrder": True, "canEditOrder": True, "canViewOrders": True, "canPayOrder": True, "canViewReports": True, "canManageCash": True},
    "staff": {"canCreateOrder": True, "canEditOrder": False, "canViewOrders": False, "canPayOrder": False, "canViewReports": False, "canManageCash": False},
    "kitchen": {"canCreateOrder": False, "canEditOrder": False, "canViewOrders": True, "canPayOrder": False, "canViewReports": False, "canManageCash": False}
}
app = FastAPI(title="Pizza Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH"],
    allow_headers=["*"],
)


async_client = httpx.AsyncClient(
    headers={
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    },
    timeout=20.0
)

def create_jwt(payload: dict) -> str:
    payload = payload.copy()
    payload["exp"] = int(time.time()) + JWT_EXP_MIN * 60
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(token: Optional[str] = Cookie(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_jwt(token)


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static/html")


# ---------- Auth ----------
@app.post("/api/login", response_model=User)
async def login(payload: Login, response: Response):
    """
    Verify credentials using Supabase RPC 'verify_staff_login' (server-side).
    Sets HttpOnly cookie with JWT.
    """
    rpc = f"{SUPABASE_URL}/rest/v1/rpc/verify_staff_login"
    res = await async_client.post(rpc, json={"p_username": payload.username, "p_password": payload.password})
    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    data = res.json()
    if not data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = data[0]
    roles = ROLE_PERMISSIONS.get(user.get("role", "staff"), ROLE_PERMISSIONS["staff"])
    token = create_jwt({
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "store_code": user.get("store_code"),
        "role": user.get("role"),
        "perms": roles
    })
    # Set secure cookie (adjust secure & samesite for production)
    response.set_cookie("token", token, httponly=True, secure=True, samesite="lax", max_age=JWT_EXP_MIN*60)
    return {
        "id": user.get("user_id"),
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "store_code": user.get("store_code"),
        "role": user.get("role"),
        "permissions": roles
    }

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}


# ---------- Orders endpoints ----------
@app.get("/api/orders")
async def get_orders(user = Depends(get_current_user)):
    store = user.get("store_code")
    # fetch pending orders + optionally today's paid ones (mimic your original logic)
    today = time.strftime("%Y-%m-%d")
    url = f"{SUPABASE_URL}/orders?store_code=eq.{store}&or=(status.eq.pending,status.eq.paid)&order=created_at.desc"
    r = await async_client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to fetch orders")
    return r.json()

@app.post("/api/orders")
async def create_order(payload: Order, user = Depends(get_current_user)):
    # validate minimum structure on server
    if not payload.items or payload.total <= 0:
        raise HTTPException(status_code=400, detail="Invalid order")
    order = payload.dict()
    order["user_id"] = user["user_id"]
    order["store_code"] = user["store_code"]
    order["status"] = "pending"
    order["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    url = f"{SUPABASE_URL}/orders"
    r = await async_client.post(url, json=order)
    if r.status_code not in (200,201):
        raise HTTPException(status_code=500, detail="Failed to create order")
    return r.json()

@app.patch("/api/orders/{order_id}")
async def update_order(order_id: int, payload: dict, user = Depends(get_current_user)):
    # simple permission check: allow editors or owner
    # (improve: fetch order owner & check)
    if not user.get("perms", {}).get("canEditOrder"):
        # Let owners update their own orders (simple example)
        # You might want to check actual owner in DB
        # For now only editors allowed
        raise HTTPException(status_code=403, detail="Forbidden")
    url = f"{SUPABASE_URL}/orders?id=eq.{order_id}"
    r = await async_client.patch(url, json=payload)
    if r.status_code not in (200,204):
        raise HTTPException(status_code=500, detail="Failed to update order")
    return {"ok": True}

@app.post("/api/orders/{order_id}/pay")
async def pay_order(order_id: int, method: str, user = Depends(get_current_user)):
    if not user.get("perms", {}).get("canPayOrder"):
        raise HTTPException(status_code=403, detail="No permission")
    # update order status to paid
    body = {"status": "paid", "payment_method": method}
    url = f"{SUPABASE_URL}/orders?id=eq.{order_id}"
    r = await async_client.patch(url, json=body)
    if r.status_code not in (200,204):
        raise HTTPException(status_code=500, detail="Failed to update payment")
    # (optionally update daily_reports here)
    return {"ok": True}

@app.get("/staffapp")
async def staffapp(request: Request):
    logger.info(f"Request: {request}")
    return templates.TemplateResponse("staffapp.html",
                                      {"request":request, "title":"Quản lý Đơn hàng Pizza"})


@app.get("/menu")
async def menu(request: Request):
    return templates.TemplateResponse("menu.html",
                                      {"request":request, "title":"Đặt Món - Pizza"})
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html",
                                      {"request": request, "title": "Đang kết nối..."})