"""Production entry point — runs the Flask app with Waitress on Windows."""
import os, sys
from dotenv import load_dotenv

load_dotenv()

from waitress import serve
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"Production server starting on http://{host}:{port}")
    print(f"Frontend: http://localhost:{port}")
    serve(app, host=host, port=port, threads=8, url_scheme="http")