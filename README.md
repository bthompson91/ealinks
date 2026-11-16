# ealinks

Private OBS remote-control web app.

- Start and stop the OBS stream
- Change the URL of a named OBS Browser Source
- Start playback inside a Browser Source through OBS Chromium remote debugging
- Embedded stream preview
- Designed to run on a home server and be accessed through Tailscale

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```env
OBS_PASSWORD=your-obs-websocket-password
BROWSER_SOURCE=Webpage
STREAM_PREVIEW_URL=https://meshcast.io/view.html?geo=usw2&id=FlatDesk47971
BROWSER_SOURCE_URL_MATCH=partner.bestofthebest.sx
```

Run:

```bash
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8080
```

## Browser-source playback

Start OBS with Chromium remote debugging enabled:

```bash
obs --remote-debugging-port=9222 --autoplay-policy=no-user-gesture-required
```

The **Start playback** button connects locally to `127.0.0.1:9222`, finds the Browser Source whose URL contains `BROWSER_SOURCE_URL_MATCH`, and runs JavaScript to start its video or click its Play control.

Keep port 9222 bound to localhost only. Do not expose it through Tailscale, port forwarding, or a reverse proxy.

## Tailscale access

```bash
tailscale serve --bg http://127.0.0.1:8080
```

Open the HTTPS Tailscale URL on an authorised phone or computer, then use **Add to Home Screen** in Safari or Chrome.

## Security

Do not expose OBS WebSocket port 4455, the web app port 8080, or OBS CDP port 9222 directly to the internet. Use Tailscale Serve for private remote access.
