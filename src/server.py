"""ASGI HTTP server for fraud detection API with C extension."""

import struct
from pathlib import Path

import numpy as np
import orjson

try:
    from src import _fraud
    HAS_CEXT = True
except ImportError:
    HAS_CEXT = False


def load_index(data_path: Path):
    """Load IVF index with int8 quantization."""
    index_file = data_path / "rinha.idx"
    
    print(f"Loading index from {index_file}...")
    with open(index_file, "rb") as f:
        magic = struct.unpack("<I", f.read(4))[0]
        if magic != 0x52494E48:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        
        version = struct.unpack("<I", f.read(4))[0]
        if version != 5:
            raise ValueError(f"Unsupported version: {version}")
        
        n_vectors = struct.unpack("<I", f.read(4))[0]
        n_centroids = struct.unpack("<I", f.read(4))[0]
        n_dims = struct.unpack("<I", f.read(4))[0]
        
        dim_min = np.frombuffer(f.read(n_dims * 4), dtype=np.float32).copy()
        dim_scale = np.frombuffer(f.read(n_dims * 4), dtype=np.float32).copy()
        
        centroids = np.frombuffer(f.read(n_centroids * n_dims * 4), dtype=np.float32).copy()
        centroids = centroids.reshape(n_centroids, n_dims)
        
        labels = np.frombuffer(f.read(n_vectors * 4), dtype=np.int32).copy()
        
        vectors_q = np.frombuffer(f.read(n_vectors * n_dims), dtype=np.int8).copy()
        vectors_q = vectors_q.reshape(n_vectors, n_dims)
        
        lists = []
        for _ in range(n_centroids):
            count = struct.unpack("<I", f.read(4))[0]
            indices = struct.unpack(f"<{count}I", f.read(count * 4))
            lists.append(np.array(indices, dtype=np.int32))
    
    vectors_q = np.ascontiguousarray(vectors_q)
    vectors_q.flags.writeable = False
    labels.flags.writeable = False
    centroids.flags.writeable = False

    print(f"Index loaded: {n_vectors} vectors, {n_centroids} centroids")
    return {
        "n_vectors": n_vectors,
        "n_centroids": n_centroids,
        "dim_min": dim_min,
        "dim_scale": dim_scale,
        "centroids": centroids,
        "labels": labels,
        "vectors_q": vectors_q,
        "lists": lists,
    }


def load_json(path: Path):
    """Load JSON file."""
    with open(path, "rb") as f:
        return orjson.loads(f.read())


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


class FraudDetector:
    def __init__(self, resources_path: Path, data_path: Path):
        self.normalization = load_json(resources_path / "normalization.json")
        self.mcc_risk = load_json(resources_path / "mcc_risk.json")
        self.data = load_index(data_path)
        self.use_cext = HAS_CEXT

        if self.use_cext:
            _fraud.init_index(self.data)
            _fraud.init_norm(self.normalization)
            _fraud.init_mcc(self.mcc_risk)
            print("C extension loaded")
        else:
            print("C extension not available, using Python fallback")
    
    def detect(self, payload: dict) -> dict:
        if self.use_cext:
            return _fraud.detect(payload)
        return self._detect_python(payload)
    
    def _detect_python(self, payload: dict) -> dict:
        """Python fallback for detect."""
        vec = self._vectorize(payload)
        fraud_count = self._search(vec, k=5)
        fraud_score = fraud_count / 5.0
        approved = fraud_score < 0.6
        return {"approved": approved, "fraud_score": fraud_score}
    
    def _vectorize(self, payload: dict) -> np.ndarray:
        from datetime import datetime
        
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

        known_merchants = set(customer["known_merchants"])
        vec[11] = 1.0 if merchant["id"] not in known_merchants else 0.0
        vec[12] = self.mcc_risk.get(merchant["mcc"], 0.5)
        vec[13] = clamp(merchant["avg_amount"] / norm["max_merchant_avg_amount"])

        return vec
    
    def _search(self, query: np.ndarray, k: int = 5) -> int:
        d = self.data
        max_candidates = 200

        query_q = ((query - d["dim_min"]) * d["dim_scale"] - 127).clip(-128, 127).astype(np.float32)

        diff = d["centroids"] - query_q
        dists = np.sum(diff ** 2, axis=1)
        top_centroids = np.argpartition(dists, 2)[:2]

        all_candidates = []
        for cid in top_centroids:
            lst = d["lists"][cid]
            if len(lst) > max_candidates:
                lst = lst[:max_candidates]
            all_candidates.append(lst)
        candidates = np.concatenate(all_candidates)

        candidate_vecs = d["vectors_q"][candidates].astype(np.float32)
        dists = np.sum((candidate_vecs - query_q) ** 2, axis=1)

        if len(dists) < k:
            return 0

        top_k_local = np.argpartition(dists, k)[:k]
        top_k_indices = candidates[top_k_local]

        return int(np.sum(d["labels"][top_k_indices]))


detector: FraudDetector = None

RESPONSE_READY = orjson.dumps({"status": "ready"})
RESPONSE_SAFE = orjson.dumps({"approved": True, "fraud_score": 0.0})

resources_path = Path(__file__).parent.parent / "resources"
data_path = Path(__file__).parent.parent / "data"
print("Loading index...")
detector = FraudDetector(resources_path, data_path)
print("Index loaded")


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]
        method = scope["method"]
        
        if method == "GET" and path == "/ready":
            await send_json(send, RESPONSE_READY)
        elif method == "POST" and path == "/fraud-score":
            await handle_fraud_score(scope, receive, send)
        else:
            await send_json(send, RESPONSE_SAFE)


async def handle_fraud_score(scope, receive, send):
    try:
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        
        data = orjson.loads(body)
        result = detector.detect(data)
        await send_json(send, orjson.dumps(result))
    except Exception:
        await send_json(send, RESPONSE_SAFE)


async def send_json(send, body: bytes, status: int = 200):
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body)).encode()],
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")


if __name__ == "__main__":
    main()
