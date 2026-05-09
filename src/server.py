"""HTTP server for fraud detection API."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class FraudHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Disable logging for performance

    def do_GET(self):
        if self.path == "/ready":
            self.send_response(200)
            self.end_headers()
        else:
            self._safe_response()

    def do_POST(self):
        if self.path == "/fraud-score":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body)
                # TODO: Implement fraud detection
                response = {"approved": True, "fraud_score": 0.0}
                self._send_json(response)
            except Exception:
                self._safe_response()
        else:
            self._safe_response()

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _safe_response(self):
        self._send_json({"approved": True, "fraud_score": 0.0})


def main():
    server = HTTPServer(("0.0.0.0", 8000), FraudHandler)
    print("Server running on port 8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
