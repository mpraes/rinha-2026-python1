"""Generate IVF index with int8 quantization from references.json.gz - streaming."""

import gzip
import struct
import random
from pathlib import Path

import ijson
import numpy as np



N_DIMS = 14
SENTINEL_DIMS = {5, 6}
N_CENTROIDS = 96


def scan_quantization_params(refs_file: Path):
    """Scan dataset once to count vectors and compute per-dimension min/max."""
    print("First pass: computing quantization parameters...")
    n_vectors = 0
    dim_min = np.full(N_DIMS, np.inf, dtype=np.float32)
    dim_max = np.full(N_DIMS, -np.inf, dtype=np.float32)

    with gzip.open(refs_file, "rb") as f:
        for ref in ijson.items(f, "item"):
            vec = ref["vector"]
            n_vectors += 1

            # Ignore sentinel -1 only for dimensions where it represents missing data.
            for i in range(N_DIMS):
                v = vec[i]
                if v >= 0 or i not in SENTINEL_DIMS:
                    dim_min[i] = min(dim_min[i], v)
                    dim_max[i] = max(dim_max[i], v)

            if n_vectors % 500000 == 0:
                print(f"  Scanned {n_vectors}")

    print(f"Total vectors: {n_vectors}")
    return n_vectors, dim_min, dim_max


def compute_dim_scale(dim_min: np.ndarray, dim_max: np.ndarray):
    """Compute per-dimension int8 scaling parameters."""
    dim_range = dim_max - dim_min
    dim_range = np.where(dim_range < 1e-6, 1.0, dim_range)
    return 254.0 / dim_range


def quantize_vector(vec: np.ndarray, dim_min: np.ndarray, dim_scale: np.ndarray):
    """Quantize a float32 vector into int8 space used by the index."""
    return np.clip((vec - dim_min) * dim_scale - 127, -128, 127).astype(np.int8)


def sample_vectors_for_clustering(
    refs_file: Path,
    n_vectors: int,
    dim_min: np.ndarray,
    dim_scale: np.ndarray,
):
    """Sample and quantize vectors to train IVF centroids."""
    print("Sampling vectors for clustering...")
    sample_size = min(100000, n_vectors)
    sample_indices = set(random.sample(range(n_vectors), sample_size))

    sample_vectors = []
    idx = 0
    with gzip.open(refs_file, "rb") as f:
        for ref in ijson.items(f, "item"):
            if idx in sample_indices:
                vec = np.array(ref["vector"], dtype=np.float32)
                vec_q = quantize_vector(vec, dim_min, dim_scale).astype(np.float32)
                sample_vectors.append(vec_q)
            idx += 1

    sample_vectors = np.array(sample_vectors, dtype=np.float32)
    return sample_vectors, sample_size


def train_centroids(sample_vectors: np.ndarray, sample_size: int, n_centroids: int = 64):
    """Train k-means centroids in quantized space for IVF indexing."""
    n_centroids = max(1, min(n_centroids, sample_size))
    print(f"Clustering {sample_size} samples into {n_centroids} centroids...")
    random.seed(42)
    np.random.seed(42)

    indices = random.sample(range(sample_size), n_centroids)
    centroids = sample_vectors[indices].copy()

    for _ in range(20):
        diff = sample_vectors[:, np.newaxis, :] - centroids[np.newaxis, :, :]
        distances = np.sum(diff**2, axis=2)
        assignments = np.argmin(distances, axis=1)

        new_centroids = np.zeros_like(centroids)
        for j in range(n_centroids):
            mask = assignments == j
            if np.any(mask):
                new_centroids[j] = sample_vectors[mask].mean(axis=0)
            else:
                new_centroids[j] = centroids[j]
        centroids = new_centroids

    return centroids


def assign_vectors_and_build_lists(
    refs_file: Path,
    n_vectors: int,
    centroids: np.ndarray,
    dim_min: np.ndarray,
    dim_scale: np.ndarray,
):
    """Quantize all vectors, assign nearest centroid, and build IVF lists."""
    print("Second pass: assigning vectors to centroids...")
    n_centroids = centroids.shape[0]
    lists = [[] for _ in range(n_centroids)]
    labels = np.zeros(n_vectors, dtype=np.int32)
    vectors_q = np.zeros((n_vectors, N_DIMS), dtype=np.int8)

    idx = 0
    with gzip.open(refs_file, "rb") as f:
        for ref in ijson.items(f, "item"):
            vec = np.array(ref["vector"], dtype=np.float32)
            labels[idx] = 1 if ref["label"] == "fraud" else 0

            vec_q = quantize_vector(vec, dim_min, dim_scale)
            vectors_q[idx] = vec_q

            diff = centroids - vec_q.astype(np.float32)
            dist = np.sum(diff**2, axis=1)
            cluster = np.argmin(dist)
            lists[cluster].append(idx)

            idx += 1
            if idx % 500000 == 0:
                print(f"  Processed {idx}/{n_vectors}")

    return labels, vectors_q, lists


def optimize_runtime_layout(
    labels: np.ndarray,
    vectors_q: np.ndarray,
    lists,
    centroids: np.ndarray,
):
    """Reorder vectors by cluster and centroid distance to improve runtime locality."""
    print("Optimizing index layout for runtime...")

    ordered_lists = []
    for cluster_idx, lst in enumerate(lists):
        if not lst:
            ordered_lists.append(np.empty(0, dtype=np.int32))
            continue

        idx_arr = np.asarray(lst, dtype=np.int32)
        cluster_vecs = vectors_q[idx_arr].astype(np.float32)
        dists = np.sum((cluster_vecs - centroids[cluster_idx]) ** 2, axis=1)
        sort_order = np.argsort(dists, kind="stable")
        ordered_lists.append(idx_arr[sort_order])

    new_order = np.concatenate(ordered_lists).astype(np.int32)
    vectors_q = vectors_q[new_order]
    labels = labels[new_order]

    compact_lists = []
    offset = 0
    for idx_arr in ordered_lists:
        count = len(idx_arr)
        compact_lists.append(np.arange(offset, offset + count, dtype=np.int32))
        offset += count

    return labels, vectors_q, compact_lists


def write_index_file(
    output_file: Path,
    n_vectors: int,
    dim_min: np.ndarray,
    dim_scale: np.ndarray,
    centroids: np.ndarray,
    labels: np.ndarray,
    vectors_q: np.ndarray,
    lists,
):
    """Write the IVF + int8 index in the expected binary format."""
    print(f"Writing {output_file}...")

    with open(output_file, "wb") as f:
        # Header
        f.write(struct.pack("<I", 0x52494E48))  # "RINH"
        f.write(struct.pack("<I", 5))  # version 5 = IVF + int8
        f.write(struct.pack("<I", n_vectors))
        f.write(struct.pack("<I", centroids.shape[0]))
        f.write(struct.pack("<I", N_DIMS))  # dimensions

        # Quantization params
        f.write(dim_min.astype(np.float32).tobytes())
        f.write(dim_scale.astype(np.float32).tobytes())

        # Centroids
        f.write(centroids.astype(np.float32).tobytes())

        # Labels
        f.write(labels.tobytes())

        # Quantized vectors
        f.write(vectors_q.tobytes())

        # Inverted lists
        for lst in lists:
            f.write(struct.pack("<I", len(lst)))
            for i in lst:
                f.write(struct.pack("<I", i))


def pack():
    """Pack references.json.gz into IVF index with int8 quantization."""
    resources_path = Path(__file__).parent.parent / "resources"
    data_path = Path(__file__).parent.parent / "data"
    data_path.mkdir(exist_ok=True)

    refs_file = resources_path / "references.json.gz"

    n_vectors, dim_min, dim_max = scan_quantization_params(refs_file)
    dim_scale = compute_dim_scale(dim_min, dim_max)

    sample_vectors, sample_size = sample_vectors_for_clustering(
        refs_file,
        n_vectors,
        dim_min,
        dim_scale,
    )
    centroids = train_centroids(sample_vectors, sample_size, n_centroids=N_CENTROIDS)

    labels, vectors_q, lists = assign_vectors_and_build_lists(
        refs_file,
        n_vectors,
        centroids,
        dim_min,
        dim_scale,
    )

    labels, vectors_q, lists = optimize_runtime_layout(
        labels,
        vectors_q,
        lists,
        centroids,
    )

    n_fraud = np.sum(labels)
    print(f"Fraud: {n_fraud} ({100*n_fraud/n_vectors:.2f}%)")

    list_sizes = [len(lst) for lst in lists]
    print(f"Cluster sizes: min={min(list_sizes)}, max={max(list_sizes)}, avg={sum(list_sizes)//len(list_sizes)}")

    output_file = data_path / "rinha.idx"
    write_index_file(
        output_file,
        n_vectors,
        dim_min,
        dim_scale,
        centroids,
        labels,
        vectors_q,
        lists,
    )

    file_size = output_file.stat().st_size / 1024 / 1024
    print(f"Index written: {file_size:.2f} MB")

    # Memory estimate
    vectors_mem = n_vectors * N_DIMS / 1024 / 1024  # int8
    labels_mem = n_vectors * 4 / 1024 / 1024  # int32
    centroids_mem = centroids.shape[0] * N_DIMS * 4 / 1024 / 1024  # float32
    print(f"Runtime memory: ~{vectors_mem + labels_mem + centroids_mem:.1f} MB")


if __name__ == "__main__":
    pack()
