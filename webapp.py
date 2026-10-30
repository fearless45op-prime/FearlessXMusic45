"""Render Web Service wrapper for VibeFearless.

The HTTP health server runs in a daemon thread. The Telegram bot runs on the
main thread because python-telegram-bot's run_polling() installs signal
handlers, which are only supported from the main interpreter thread.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b'{"status":"ok","service":"VibeFearless"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b'{"error":"not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_health_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


def main():
    threading.Thread(
        target=start_health_server,
        name="health-server",
        daemon=True,
    ).start()

    # IMPORTANT: run the Telegram bot on the main thread.
    import music
    music.main()


if __name__ == "__main__":
    main()
