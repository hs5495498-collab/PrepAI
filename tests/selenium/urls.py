"""Fixed URLs the Selenium suite talks to.

These match the ones hardcoded in prepai/js/api.js (backend) and required by
backend/main.py's CORS allow_origins (frontend) - see prepai/CLAUDE.md and
docs/LOCAL_SETUP_AND_DEMO.md. Both must stay in sync with those files.
"""

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5500
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"
