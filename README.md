# ealinks

Private OBS remote-control web app.

- Start and stop the OBS stream
- Change the URL of a named OBS Browser Source
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
```

Run:

```bash
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8080
```

## Tailscale access

```bash
tailscale serve --bg http://127.0.0.1:8080
```

Open the HTTPS Tailscale URL on an authorised phone or computer, then use **Add to Home Screen** in Safari or Chrome.

## Security

Do not expose port 4455 (OBS WebSocket) or port 8080 directly to the internet. Use Tailscale Serve for private remote access.
