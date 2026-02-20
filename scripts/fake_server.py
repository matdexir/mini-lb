#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(f"{self.server.server_port}".encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1])
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Fake backend running on port {port}")
    server.serve_forever()
