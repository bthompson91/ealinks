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
import httpx
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
OBS_CDP_HOST = os.getenv("OBS_CDP_HOST", "127.0.0.1")
OBS_CDP_PORT = int(os.getenv("OBS_CDP_PORT", "9222"))
BROWSER_SOURCE_URL_MATCH = os.getenv(
    "BROWSER_SOURCE_URL_MATCH",
    "partner.bestofthebest.sx",
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


PLAY_SCRIPT = """
(() => {
  const video = document.querySelector('video');

  if (video) {
    video.muted = false;
    const playPromise = video.play();

    if (playPromise) {
      return playPromise
        .then(() => 'Video playback started.')
        .catch((error) => {
          const playButton =
            document.querySelector('button[aria-label*="play" i]') ||
            document.querySelector('button[title*="play" i]') ||
            document.querySelector('[class*="play" i]');

          if (playButton) {
            playButton.click();
            return 'Clicked play button after direct playback was blocked.';
          }

          return 'Playback blocked: ' + error.message;
        });
    }

    return 'Video element found; playback requested.';
  }

  const playButton =
    document.querySelector('button[aria-label*="play" i]') ||
    document.querySelector('button[title*="play" i]') ||
    document.querySelector('[class*="play" i]');

  if (playButton) {
    playButton.click();
    return 'Clicked play button.';
  }

  return 'No video element or play button was found.';
})()
"""


async def find_browser_source_target():
    url = f"http://{OBS_CDP_HOST}:{OBS_CDP_PORT}/json/list"

    async with httpx.AsyncClient(timeout=3) as client:
        response = await client.get(url)
        response.raise_for_status()
        targets = response.json()

    matches = [
        target for target in targets
        if target.get("type") == "page"
        and BROWSER_SOURCE_URL_MATCH.lower() in target.get("url", "").lower()
    ]

    if not matches:
        raise RuntimeError(
            f"No OBS Browser Source matching '{BROWSER_SOURCE_URL_MATCH}' was found."
        )

    return matches[0]


async def run_in_browser_source(expression: str):
    target = await find_browser_source_target()
    websocket_url = target.get("webSocketDebuggerUrl")

    if not websocket_url:
        raise RuntimeError("The matching Browser Source has no debugger WebSocket URL.")

    async with websockets.connect(websocket_url, max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        }))

        while True:
            message = json.loads(await ws.recv())
            if message.get("id") == 1:
                result = message.get("result", {})
                if "error" in result:
                    raise RuntimeError(result["error"].get("message", "CDP request failed"))

                value = result.get("result", {}).get("value")
                exception = result.get("exceptionDetails")

                if exception:
                    raise RuntimeError(exception.get("text", "JavaScript error in Browser Source"))

                return value


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


@app.post("/play")
async def play():
    try:
        result = await run_in_browser_source(PLAY_SCRIPT)
        return {"ok": True, "result": result}
    except Exception as error:
        return {"ok": False, "error": str(error)}
