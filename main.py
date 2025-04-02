
from fastapi import FastAPI, Request
import httpx
import time
import os
import hashlib
import hmac
import json

app = FastAPI()

API_KEY = os.getenv("APEX_API_KEY")
API_SECRET = os.getenv("APEX_API_SECRET")
OMNI_KEY = os.getenv("APEX_OMNI_KEY")
BASE_URL = "https://api.apex.exchange"

# Firma para ApeX Omni API
def generate_signature(secret, timestamp, method, path, body=""):
    payload = f"{timestamp}{method.upper()}{path}{body}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

# Enviar orden firmada a ApeX Omni
async def send_order_apex(symbol, side, quantity, price, type="market", stop_price=None):
    timestamp = str(int(time.time() * 1000))
    path = "/v1/orders"
    method = "POST"

    order = {
        "symbol": symbol,
        "side": side,
        "type": type,
        "quantity": quantity,
        "price": price,
        "omniKey": OMNI_KEY
    }

    if stop_price:
        order["stopPrice"] = stop_price

    body = json.dumps(order)
    signature = generate_signature(API_SECRET, timestamp, method, path, body)

    headers = {
        "APEX-API-KEY": API_KEY,
        "APEX-API-TIMESTAMP": timestamp,
        "APEX-API-SIGNATURE": signature,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(BASE_URL + path, headers=headers, content=body)
        return response.json()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    symbol = data.get("symbol")
    side = data.get("side").upper()
    entry = float(data.get("entry"))
    quantity = float(data.get("quantity"))
    tps = [float(data.get(f"tp{i}")) for i in range(1, 8)]
    stop = float(data.get("stop"))

    # Orden de entrada
    order_market = await send_order_apex(symbol, side, quantity, entry, type="market")

    # TP en 7 niveles
    for tp in tps:
        await send_order_apex(
            symbol,
            "SELL" if side == "BUY" else "BUY",
            round(quantity / 7, 6),
            tp,
            type="limit"
        )

    # SL
    await send_order_apex(
        symbol,
        "SELL" if side == "BUY" else "BUY",
        quantity,
        stop,
        type="stop_market",
        stop_price=stop
    )

    return {"status": "órdenes enviadas con Omni Key"}
