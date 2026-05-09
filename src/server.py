"""HTTP server for fraud detection API."""

import json
import struct
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import numpy as np


def clamp(x: float) -> float:
    """Clamp value to [0.0, 1.0]."""
    return max(0.0, min(1.0, x))


def load_index(path: Path):
    """Load binary index file with vectors in RAM for speed."""
    with open(path, "rb") as f:
        magic = struct.unpack("<I", f.read(4))[0]
        if magic != 0x52494E48:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        
        version = struct.unpack("<I", f.read(4))[0]
        total_vectors = struct.unpack("<I", f.read(4))[0]
        
        # Version 3+ has exact counts
        if version >= 3:
            n_legit = struct.unpack("<I", f.read(4))[0]
            n_fraud = struct.unpack("<I", f.read(4))[0]
        else:
            # Fallback for version 2 (estimate)
            n_legit = total_vectors - int(total_vectors * 0.06)
            n_fraud = total_vectors - n_legit
        
        n_centroids_legit = struct.unpack("<I", f.read(4))[0]
        n_centroids_fraud = struct.unpack("<I", f.read(4))[0]
        dimensions = struct.unpack("<I", f.read(4))[0]
        
        # Calculate offsets
        header_size = 32 if version >= 3 else 24
        legit_offset = header_size
        fraud_offset = legit_offset + n_legit * dimensions * 4
        legit_cent_offset = fraud_offset + n_fraud * dimensions * 4
        fraud_cent_offset = legit_cent_offset + n_centroids_legit * dimensions * 4
        lists_offset = fraud_cent_offset + n_centroids_fraud * dimensions * 4
    
    # Load vectors directly into RAM (much faster than memmap)
    print(f"Loading {n_legit} legit vectors into RAM...")
    with open(path, "rb") as f:
        f.seek(legit_offset)
        legit_vectors = np.frombuffer(f.read(n_legit * dimensions * 4), 
                                      dtype=np.float32).reshape(n_legit, dimensions).copy()
    
    print(f"Loading {n_fraud} fraud vectors into RAM...")
    with open(path, "rb") as f:
        f.seek(fraud_offset)
        fraud_vectors = np.frombuffer(f.read(n_fraud * dimensions * 4),
                                      dtype=np.float32).reshape(n_fraud, dimensions).copy()
    
    # Load centroids
    with open(path, "rb") as f:
        f.seek(legit_cent_offset)
        legit_centroids = np.frombuffer(f.read(n_centroids_legit * dimensions * 4), 
                                        dtype=np.float32).reshape(n_centroids_legit, dimensions)
        fraud_centroids = np.frombuffer(f.read(n_centroids_fraud * dimensions * 4),
                                        dtype=np.float32).reshape(n_centroids_fraud, dimensions)
        
        # Load inverted lists
        legit_lists = []
        for _ in range(n_centroids_legit):
            count = struct.unpack("<I", f.read(4))[0]
            indices = struct.unpack(f"<{count}I", f.read(count * 4))
            legit_lists.append(list(indices))
        
        fraud_lists = []
        for _ in range(n_centroids_fraud):
            count = struct.unpack("<I", f.read(4))[0]
            indices = struct.unpack(f"<{count}I", f.read(count * 4))
            fraud_lists.append(list(indices))
    
    return {
        "legit_vectors": legit_vectors,
        "fraud_vectors": fraud_vectors,
        "legit_centroids": legit_centroids,
        "fraud_centroids": fraud_centroids,
        "legit_lists": legit_lists,
        "fraud_lists": fraud_lists,
    }


def load_json(path: Path):
    """Load JSON file."""
    with open(path, "r") as f:
        return json.load(f)


class FraudDetector:
    """Fraud detection engine."""
    
    def __init__(self, resources_path: Path, data_path: Path):
        self.normalization = load_json(resources_path / "normalization.json")
        self.mcc_risk = load_json(resources_path / "mcc_risk.json")
        self.index = load_index(data_path / "rinha.idx")
    
    def vectorize(self, payload: dict) -> np.ndarray:
        """Convert payload to 14-dimensional vector."""
        tx = payload["transaction"]
        customer = payload["customer"]
        merchant = payload["merchant"]
        terminal = payload["terminal"]
        last_tx = payload.get("last_transaction")
        
        norm = self.normalization
        
        vec = np.zeros(14, dtype=np.float32)
        
        vec[0] = clamp(tx["amount"] / norm["max_amount"])
        vec[1] = clamp(tx["installments"] / norm["max_installments"])
        vec[2] = clamp((tx["amount"] / customer["avg_amount"]) / norm["amount_vs_avg_ratio"])
        
        dt = datetime.fromisoformat(tx["requested_at"].replace("Z", "+00:00"))
        vec[3] = dt.hour / 23.0
        vec[4] = dt.weekday() / 6.0
        
        if last_tx is None:
            vec[5] = -1.0
            vec[6] = -1.0
        else:
            last_dt = datetime.fromisoformat(last_tx["timestamp"].replace("Z", "+00:00"))
            minutes = (dt - last_dt).total_seconds() / 60.0
            vec[5] = clamp(minutes / norm["max_minutes"])
            vec[6] = clamp(last_tx["km_from_current"] / norm["max_km"])
        
        vec[7] = clamp(terminal["km_from_home"] / norm["max_km"])
        vec[8] = clamp(customer["tx_count_24h"] / norm["max_tx_count_24h"])
        vec[9] = 1.0 if terminal["is_online"] else 0.0
        vec[10] = 1.0 if terminal["card_present"] else 0.0
        vec[11] = 1.0 if merchant["id"] not in customer["known_merchants"] else 0.0
        vec[12] = self.mcc_risk.get(merchant["mcc"], 0.5)
        vec[13] = clamp(merchant["avg_amount"] / norm["max_merchant_avg_amount"])
        
        return vec
    
    def search(self, query: np.ndarray, k: int = 5) -> int:
        """Search for k nearest neighbors, return fraud count."""
        idx = self.index
        
        # Find nearest centroid for each class
        diff_legit = idx["legit_centroids"] - query
        diff_fraud = idx["fraud_centroids"] - query
        dists_legit = np.sum(diff_legit ** 2, axis=1)
        dists_fraud = np.sum(diff_fraud ** 2, axis=1)
        
        # Use only nearest centroid
        top_legit_idx = np.argmin(dists_legit)
        top_fraud_idx = np.argmin(dists_fraud)
        
        candidates = []
        max_candidates_per_class = 100  # Drastically reduced for throughput
        
        # Get candidates from nearest legit centroid
        legit_indices = idx["legit_lists"][top_legit_idx]
        if len(legit_indices) > max_candidates_per_class:
            # Sample evenly if too many
            step = len(legit_indices) // max_candidates_per_class
            legit_indices = legit_indices[::step][:max_candidates_per_class]
        
        for i in legit_indices:
            vec = idx["legit_vectors"][i]
            dist = np.sum((vec - query) ** 2)
            candidates.append((dist, 0))
        
        # Get candidates from nearest fraud centroid
        fraud_indices = idx["fraud_lists"][top_fraud_idx]
        if len(fraud_indices) > max_candidates_per_class:
            step = len(fraud_indices) // max_candidates_per_class
            fraud_indices = fraud_indices[::step][:max_candidates_per_class]
        
        for i in fraud_indices:
            vec = idx["fraud_vectors"][i]
            dist = np.sum((vec - query) ** 2)
            candidates.append((dist, 1))
        
        if len(candidates) < k:
            return 0
        
        # Sort by distance and count frauds in top-k
        candidates.sort(key=lambda x: x[0])
        fraud_count = sum(label for _, label in candidates[:k])
        return fraud_count
    
    def detect(self, payload: dict) -> dict:
        """Detect fraud for a transaction."""
        vec = self.vectorize(payload)
        fraud_count = self.search(vec, k=5)
        fraud_score = fraud_count / 5.0
        approved = fraud_score < 0.6
        return {"approved": approved, "fraud_score": fraud_score}


detector: FraudDetector = None


class FraudHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path == "/ready":
            self._send_json({"status": "ready"}, status=200)
        else:
            self._safe_response()
    
    def do_POST(self):
        if self.path == "/fraud-score":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body)
                response = detector.detect(data)
                self._send_json(response)
            except Exception:
                self._safe_response()
        else:
            self._safe_response()
    
    def _send_json(self, data, status=200):
        response_body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response_body))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(response_body)
    
    def _safe_response(self):
        self._send_json({"approved": True, "fraud_score": 0.0})


def main():
    global detector
    
    resources_path = Path(__file__).parent.parent / "resources"
    data_path = Path(__file__).parent.parent / "data"
    
    print("Loading index...")
    detector = FraudDetector(resources_path, data_path)
    print("Index loaded")
    
    server = ThreadingHTTPServer(("0.0.0.0", 8000), FraudHandler)
    print("Server running on port 8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
