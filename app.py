import asyncio
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import websockets

load_dotenv()

OBS_HOST = os.getenv("OBS_HOST", "127.0.0.1")
OBS_PORT = int(os.getenv("OBS_PORT", "4455"))
OBS_PASSWORD = os.getenv("OBS_PASSWORD", "")
BROWSER_SOURCE = os.getenv("BROWSER_SOURCE", "Webpage")
STREAM_PREVIEW_URL = os.getenv(
    "STREAM_PREVIEW_URL",
    "https://meshcast.io/view.html?geo=usw2&id=FlatDesk47971",
)

app = FastAPI(title="ealinks OBS Remote")

HTML = Path("static/index.html").read_text(encoding="utf-8")
HTML = HTML.replace("__STREAM_PREVIEW_URL__", STREAM_PREVIEW_URL)
HTML = HTML.replace("__BROWSER_SOURCE__", BROWSER_SOURCE)


def make_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode()).digest()
    ).decode()
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode()).digest()
    ).decode()


async def obs_request(request_type: str, request_data: dict | None = None):
    if request_data is None:
        request_data = {}

    uri = f"ws://{OBS_HOST}:{OBS_PORT}"
    request_id = str(uuid.uuid4())

    async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
        hello = json.loads(await ws.recv())
        hello_data = hello.get("d", {})

        if "authentication" in hello_data:
            auth = make_auth(
                OBS_PASSWORD,
                hello_data["authentication"]["salt"],
                hello_data["authentication"]["challenge"],
            )
            await ws.send(json.dumps({
                "op": 1,
                "d": {
                    "rpcVersion": 1,
                    "authentication": auth,
                },
            }))
            identified = json.loads(await ws.recv())
            if identified.get("op") != 2:
                raise RuntimeError("OBS WebSocket authentication failed")

        await ws.send(json.dumps({
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId": request_id,
                "requestData": request_data,
            },
        }))

        while True:
            message = json.loads(await ws.recv())
            if message.get("op") == 7 and message["d"].get("requestId") == request_id:
                result = message["d"]
                if not result.get("requestStatus", {}).get("result", False):
                    raise RuntimeError(result.get("requestStatus", {}).get("comment", "OBS request failed"))
                return result


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(HTML)


@app.get("/status")
async def status():
    try:
        result = await obs_request("GetStreamStatus")
        return {
            "obs_connected": True,
            "streaming": result["responseData"]["outputActive"],
        }
    except Exception:
        return {"obs_connected": False, "streaming": False}


@app.post("/stream")
async def stream(action: str = Form(...)):
    try:
        if action == "start":
            await obs_request("StartStream")
        elif action == "stop":
            await obs_request("StopStream")
        else:
            raise ValueError("Unknown action")
        return {"ok": True}
    except Exception as error:
        return {"ok": False, "error": str(error)}


@app.post("/url")
async def set_url(url: str = Form(...)):
    try:
        await obs_request("SetInputSettings", {
            "inputName": BROWSER_SOURCE,
            "inputSettings": {"url": url},
            "overlay": True,
        })
        return {"ok": True}
    except Exception as error:
        return {"ok": False, "error": str(error)}
