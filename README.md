arbitrage
=========

Minimal Python project scaffold for arbitrage experiments.

Quick start (PowerShell):

1. Create and activate a venv

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
```

2. Install dev deps

```powershell
pip install -r requirements.txt
```

3. Run the CLI

```powershell
python -m src.arbitrage.cli
```

4. Run tests

```powershell
python -m unittest discover -v
```

Notes:
- This is a minimal scaffold. Replace placeholder functions with real logic.

Web dashboard (demo)

1. Install web backend dependencies:

```powershell
pip install -r requirements.txt
```

2. Run the FastAPI server (from repo root):

```powershell
uvicorn arbitrage.web:app --reload --host 0.0.0.0 --port 8000
```

3. Open `web/index.html` in your browser. The demo frontend connects to `ws://localhost:8000/ws/opportunities` and shows live opportunities from mock exchanges.

Note: For a production setup, serve the React app from a proper static server and secure the websocket endpoint.
