"""
run_app.py
Unified single-command launcher for CreatorPulse (Exploding Topics Web Application).
Starts the FastAPI backend and serves the sleek React frontend at http://localhost:8000
"""
import sys
import subprocess
import webbrowser

def main():
    print("=" * 60)
    print("🔥 CREATOR PULSE - Exploding Topics Influencer App")
    print("   Serving at: http://localhost:8000")
    print("   Backend: FastAPI + Apache Spark HDFS Gold Tier")
    print("=" * 60)
    
    # Open browser automatically
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    # Launch uvicorn server
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
    ]
    subprocess.run(cmd)

if __name__ == "__main__":
    main()
