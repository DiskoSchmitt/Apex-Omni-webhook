import asyncio
import websockets
import json
import time
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from typing import Optional
import logging

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class ApexWebSocket:
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.last_pong_time: float = time.time()
        self.is_connected: bool = False
        self.ws_url = "wss://api.apex.exchange/ws"  # Adjust URL as needed
        self.heartbeat_task = None
        self.connection_task = None

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.is_connected = True
            logger.info("WebSocket connected successfully")
            
            # Start heartbeat after successful connection
            if self.heartbeat_task is None:
                self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
                
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}")
            self.is_connected = False
            return False

    async def reconnect(self):
        """Reconnect WebSocket if disconnected"""
        logger.info("Attempting to reconnect...")
        self.is_connected = False
        if self.ws:
            await self.ws.close()
        return await self.connect()

    async def send_ping(self):
        """Send ping message"""
        if not self.is_connected:
            await self.reconnect()
            return

        try:
            timestamp = str(int(time.time() * 1000))
            ping_message = {
                "op": "ping",
                "args": [timestamp]
            }
            await self.ws.send(json.dumps(ping_message))
            logger.debug(f"Ping sent at {timestamp}")
            return timestamp
        except Exception as e:
            logger.error(f"Error sending ping: {str(e)}")
            self.is_connected = False
            await self.reconnect()

    async def handle_pong(self, message: str):
        """Handle pong response"""
        try:
            data = json.loads(message)
            if data.get("op") == "pong":
                self.last_pong_time = time.time()
                logger.debug(f"Pong received: {data}")
            elif data.get("op") == "ping":
                # If we receive a ping, we need to respond with pong
                pong_message = {
                    "op": "pong",
                    "args": data.get("args", [str(int(time.time() * 1000))])
                }
                await self.ws.send(json.dumps(pong_message))
                logger.debug("Responded to server ping with pong")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in pong message: {message}")
        except Exception as e:
            logger.error(f"Error handling pong: {str(e)}")

    async def heartbeat_loop(self):
        """Maintain heartbeat every 15 seconds"""
        while True:
            try:
                if not self.is_connected:
                    await self.reconnect()
                    continue

                # Send ping
                ping_time = await self.send_ping()
                
                # Wait for and process messages
                try:
                    message = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    await self.handle_pong(message)
                except asyncio.TimeoutError:
                    logger.warning("No pong received within timeout")
                    
                # Check connection health
                if time.time() - self.last_pong_time > 150:
                    logger.warning("No pong received for 150s, reconnecting...")
                    await self.reconnect()
                
                # Wait for next heartbeat
                await asyncio.sleep(15)
                
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {str(e)}")
                await asyncio.sleep(5)  # Wait before retry

    def get_connection_status(self):
        """Get current connection status"""
        current_time = time.time()
        status = {
            "connected": self.is_connected,
            "last_pong": datetime.fromtimestamp(self.last_pong_time).strftime('%Y-%m-%d %H:%M:%S'),
            "current_time": datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S'),
            "pong_age_seconds": int(current_time - self.last_pong_time)
        }
        return status

# Global WebSocket instance
apex_ws = ApexWebSocket()

@app.on_event("startup")
async def startup_event():
    """Start WebSocket connection on application startup"""
    global apex_ws
    apex_ws.connection_task = asyncio.create_task(apex_ws.connect())

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of WebSocket connection"""
    global apex_ws
    if apex_ws.ws:
        await apex_ws.ws.close()
    if apex_ws.heartbeat_task:
        apex_ws.heartbeat_task.cancel()
    if apex_ws.connection_task:
        apex_ws.connection_task.cancel()

@app.get("/health")
async def health_check():
    """Endpoint to check WebSocket connection health"""
    global apex_ws
    status = apex_ws.get_connection_status()
    
    # Consider connection unhealthy if no pong for 30 seconds
    if status["pong_age_seconds"] > 30:
        return {
            "status": "unhealthy",
            "details": status
        }
    
    return {
        "status": "healthy",
        "details": status
    }

@app.post("/webhook")
async def webhook(request: Request):
    """Webhook endpoint for trading signals"""
    global apex_ws
    
    # Check WebSocket connection health
    status = apex_ws.get_connection_status()
    if not status["connected"] or status["pong_age_seconds"] > 30:
        raise HTTPException(
            status_code=503,
            detail="WebSocket connection unhealthy, cannot process orders"
        )
    
    # ... Rest des Order-Codes bleibt gleich ...
