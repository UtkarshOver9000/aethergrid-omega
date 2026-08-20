"""Vercel serverless entrypoint for AETHERGRID Omega.

Streamlit apps cannot run inside Vercel's serverless functions (they require a
persistent WebSocket server). This handler serves an HTML landing page that
points visitors to the live Streamlit deployment on Streamlit Community Cloud.

To host the full interactive app, run:
    streamlit run aethergrid/ui/app.py
or deploy to: https://share.streamlit.io
"""
from __future__ import annotations

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AETHERGRID Omega</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f4f6fb;
      color: #101828;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .card {
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 4px 32px rgba(37,99,235,.10);
      max-width: 560px;
      width: 90%;
      padding: 48px 40px 40px;
      text-align: center;
    }
    .badge {
      display: inline-block;
      background: #eff6ff;
      color: #2563eb;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: .08em;
      text-transform: uppercase;
      border-radius: 999px;
      padding: 4px 14px;
      margin-bottom: 20px;
    }
    h1 {
      font-size: 2rem;
      font-weight: 700;
      color: #101828;
      margin-bottom: 8px;
    }
    .omega { color: #2563eb; }
    p {
      color: #475467;
      line-height: 1.65;
      margin-bottom: 28px;
    }
    .btn {
      display: inline-block;
      background: #2563eb;
      color: #fff;
      text-decoration: none;
      font-weight: 600;
      font-size: 1rem;
      border-radius: 10px;
      padding: 14px 32px;
      transition: background .2s;
    }
    .btn:hover { background: #1d4ed8; }
    .note {
      margin-top: 24px;
      font-size: .85rem;
      color: #98a2b3;
    }
    .note a { color: #2563eb; text-decoration: none; }
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">Live Digital Twin</span>
    <h1>AETHERGRID <span class="omega">&Omega;</span></h1>
    <p>
      Hierarchical, uncertainty-aware, safety-constrained electricity demand
      optimisation for smart building ecosystems. Powered by a full agent-based
      World simulation, MPC/RL controllers, and a 3-D visualisation engine.
    </p>
    <a class="btn" href="https://github.com/UtkarshOver9000/aethergrid-omega" target="_blank">
      View on GitHub
    </a>
    <p class="note">
      The interactive Streamlit dashboard requires a persistent server.<br/>
      Run locally: <code>streamlit run aethergrid/ui/app.py</code>
    </p>
  </div>
</body>
</html>"""


def handler(request, response):
    """WSGI-style handler used by Vercel Python runtime."""
    response.status_code = 200
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return HTML.encode()
