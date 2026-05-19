"""ASGI HTTP server for fraud detection API with IVF + int8."""

import struct
from pathlib import Path

import numpy as np
import orjson


def load_index(data_path: Path):
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
    with open(path, "rb") as f:
        return orjson.loads(f.read())


def _build_weekday_lut():
    from datetime import datetime
    lut = {}
    for year in range(2024, 2029):
        for m in range(1, 13):
            for d in range(1, 32):
                try:
                    lut[year * 10000 + m * 100 + d] = datetime(year, m, d).weekday()
                except ValueError:
                    pass
    return lut

_WEEKDAY_LUT = _build_weekday_lut()


class FraudDetector:
    
    def __init__(self, resources_path: Path, data_path: Path):
        self.normalization = load_json(resources_path / "normalization.json")
        self.mcc_risk = load_json(resources_path / "mcc_risk.json")
        self.data = load_index(data_path)
        
        d = self.data
        n = self.normalization
        self._max_amount = float(n["max_amount"])
        self._max_installments = float(n["max_installments"])
        self._amount_vs_avg_ratio = float(n["amount_vs_avg_ratio"])
        self._max_minutes = float(n["max_minutes"])
        self._max_km = float(n["max_km"])
        self._max_tx_count_24h = float(n["max_tx_count_24h"])
        self._max_merchant_avg_amount = float(n["max_merchant_avg_amount"])
        
        self._dim_min = d["dim_min"]
        self._dim_scale = d["dim_scale"]
        self._centroids = d["centroids"]
        self._labels = d["labels"]
        self._vectors_q = d["vectors_q"]
        self._lists = d["lists"]
        
        self._query_buf = np.zeros(14, dtype=np.float32)
        self._query_q_buf = np.zeros(14, dtype=np.float32)
        self._centroid_dists_buf = np.zeros(d["n_centroids"], dtype=np.float32)
    
    def detect(self, payload: dict) -> dict:
        tx = payload["transaction"]
        customer = payload["customer"]
        merchant = payload["merchant"]
        terminal = payload["terminal"]
        last_tx = payload.get("last_transaction")
        
        vec = self._query_buf
        inv_max_amount = 1.0 / self._max_amount
        inv_max_installments = 1.0 / self._max_installments
        inv_ratio = 1.0 / self._amount_vs_avg_ratio
        inv_max_minutes = 1.0 / self._max_minutes
        inv_max_km = 1.0 / self._max_km
        inv_max_tx_count = 1.0 / self._max_tx_count_24h
        inv_max_merchant_avg = 1.0 / self._max_merchant_avg_amount
        
        a = tx["amount"]
        vec[0] = a * inv_max_amount if a < self._max_amount else 1.0
        
        inst = tx["installments"]
        vec[1] = inst * inv_max_installments if inst < self._max_installments else 1.0
        
        avg = customer["avg_amount"]
        ratio = a / avg * inv_ratio if avg > 0 else 0.0
        vec[2] = ratio if 0.0 <= ratio <= 1.0 else (1.0 if ratio > 1.0 else 0.0)
        
        ra = tx["requested_at"]
        hour = int(ra[11:13])
        vec[3] = hour * (1.0 / 23.0)
        ymd = int(ra[0:4]) * 10000 + int(ra[5:7]) * 100 + int(ra[8:10])
        vec[4] = _WEEKDAY_LUT.get(ymd, 0) * (1.0 / 6.0)
        
        if last_tx is None:
            vec[5] = -1.0
            vec[6] = -1.0
        else:
            lra = last_tx["timestamp"]
            cur_min = int(ra[11:13]) * 60 + int(ra[14:16])
            last_min = int(lra[11:13]) * 60 + int(lra[14:16])
            cur_day = int(ra[8:10])
            last_day = int(lra[8:10])
            minutes = cur_min - last_min + (cur_day - last_day) * 1440
            if minutes < 0:
                minutes = 0
            m = minutes * inv_max_minutes
            vec[5] = m if m < 1.0 else 1.0
            
            km = last_tx["km_from_current"]
            k = km * inv_max_km
            vec[6] = k if k < 1.0 else 1.0
        
        km_home = terminal["km_from_home"]
        k7 = km_home * inv_max_km
        vec[7] = k7 if k7 < 1.0 else 1.0
        
        tc = customer["tx_count_24h"]
        vec[8] = tc * inv_max_tx_count if tc < self._max_tx_count_24h else 1.0
        
        vec[9] = 1.0 if terminal["is_online"] else 0.0
        vec[10] = 1.0 if terminal["card_present"] else 0.0
        
        mid = merchant["id"]
        vec[11] = 0.0 if mid in customer["known_merchants"] else 1.0
        
        vec[12] = self.mcc_risk.get(merchant["mcc"], 0.5)
        
        ma = merchant["avg_amount"]
        vec[13] = ma * inv_max_merchant_avg if ma < self._max_merchant_avg_amount else 1.0
        
        query_q = self._query_q_buf
        dim_min = self._dim_min
        dim_scale = self._dim_scale
        for i in range(14):
            v = (vec[i] - dim_min[i]) * dim_scale[i] - 127.0
            if v < -128.0: v = -128.0
            elif v > 127.0: v = 127.0
            query_q[i] = v
        
        d = self.data
        centroids = self._centroids
        cdists = self._centroid_dists_buf
        nc = d["n_centroids"]
        
        min0 = 1e30
        min1 = 1e30
        cid0 = 0
        cid1 = 0
        for c in range(nc):
            dist = 0.0
            for j in range(14):
                diff = centroids[c, j] - query_q[j]
                dist += diff * diff
            if dist < min0:
                min1 = min0; cid1 = cid0
                min0 = dist; cid0 = c
            elif dist < min1:
                min1 = dist; cid1 = c
        
        lists = self._lists
        labels = self._labels
        vectors_q = self._vectors_q
        
        lst0 = lists[cid0]
        lst1 = lists[cid1]
        lim0 = min(len(lst0), 200)
        lim1 = min(len(lst1), 200)
        n_cand = lim0 + lim1
        
        best5_d = [1e30] * 5
        best5_i = [0] * 5
        
        for batch_lst, batch_lim in ((lst0, lim0), (lst1, lim1)):
            for i in range(batch_lim):
                idx = batch_lst[i]
                dist = 0.0
                vrow = vectors_q[idx]
                for j in range(14):
                    diff = float(vrow[j]) - query_q[j]
                    dist += diff * diff
                if dist < best5_d[4]:
                    pos = 4
                    while pos > 0 and dist < best5_d[pos - 1]:
                        pos -= 1
                    for s in range(4, pos, -1):
                        best5_d[s] = best5_d[s - 1]
                        best5_i[s] = best5_i[s - 1]
                    best5_d[pos] = dist
                    best5_i[pos] = idx
        
        fraud_count = 0
        for i in range(5):
            if labels[best5_i[i]] == 1:
                fraud_count += 1
        
        fraud_score = fraud_count * 0.2
        approved = fraud_score < 0.6
        return {"approved": approved, "fraud_score": fraud_score}


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
