"""Generate binary index from references.json.gz using class-separated IVF."""

import gzip
import json
import struct
import random
from pathlib import Path

import numpy as np


def kmeans_vectorized(data: np.ndarray, n_clusters: int, max_iter: int = 20) -> np.ndarray:
    """Vectorized K-means clustering."""
    n_samples = data.shape[0]
    
    if n_samples < n_clusters:
        # Not enough samples, return all as centroids
        return data.copy()
    
    # Initialize centroids randomly
    indices = random.sample(range(n_samples), n_clusters)
    centroids = data[indices].copy()
    
    for iteration in range(max_iter):
        # Compute distances: (n_samples, n_clusters)
        diff = data[:, np.newaxis, :] - centroids[np.newaxis, :, :]
        distances = np.sum(diff ** 2, axis=2)
        assignments = np.argmin(distances, axis=1)
        
        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for j in range(n_clusters):
            mask = assignments == j
            if np.any(mask):
                new_centroids[j] = data[mask].mean(axis=0)
            else:
                new_centroids[j] = centroids[j]
        
        centroids = new_centroids
    
    return centroids


def pack():
    """Pack references.json.gz into binary index with class-separated clusters."""
    resources_path = Path(__file__).parent.parent / "resources"
    data_path = Path(__file__).parent.parent / "data"
    data_path.mkdir(exist_ok=True)
    
    refs_file = resources_path / "references.json.gz"
    output_file = data_path / "rinha.idx"
    
    print(f"Reading {refs_file}...")
    with gzip.open(refs_file, "rt") as f:
        references = json.load(f)
    
    print(f"Processing {len(references)} vectors...")
    
    # Separate vectors by class (fraud vs legit)
    legit_vectors = []
    fraud_vectors = []
    
    for ref in references:
        vec = np.array(ref["vector"], dtype=np.float32)
        if ref["label"] == "fraud":
            fraud_vectors.append(vec)
        else:
            legit_vectors.append(vec)
    
    legit_vectors = np.array(legit_vectors, dtype=np.float32)
    fraud_vectors = np.array(fraud_vectors, dtype=np.float32)
    
    n_legit = len(legit_vectors)
    n_fraud = len(fraud_vectors)
    print(f"Legit: {n_legit}, Fraud: {n_fraud} ({100*n_fraud/(n_legit+n_fraud):.2f}% fraud)")
    
    # Cluster each class separately (key insight from GUIDELINES.md)
    # Use more centroids for the larger class to balance search
    n_centroids_legit = 20
    n_centroids_fraud = 12  # Fewer since fraud is smaller
    
    print(f"Clustering legit vectors into {n_centroids_legit} centroids...")
    random.seed(42)
    np.random.seed(42)
    legit_centroids = kmeans_vectorized(legit_vectors, n_centroids_legit)
    
    print(f"Clustering fraud vectors into {n_centroids_fraud} centroids...")
    fraud_centroids = kmeans_vectorized(fraud_vectors, n_centroids_fraud)
    
    # Assign each vector to its nearest centroid
    print("Assigning vectors to centroids...")
    
    # Legit assignments
    diff_legit = legit_vectors[:, np.newaxis, :] - legit_centroids[np.newaxis, :, :]
    legit_distances = np.sum(diff_legit ** 2, axis=2)
    legit_assignments = np.argmin(legit_distances, axis=1)
    
    # Fraud assignments
    diff_fraud = fraud_vectors[:, np.newaxis, :] - fraud_centroids[np.newaxis, :, :]
    fraud_distances = np.sum(diff_fraud ** 2, axis=2)
    fraud_assignments = np.argmin(fraud_distances, axis=1)
    
    # Build inverted lists (indices relative to each class)
    legit_lists = [[] for _ in range(n_centroids_legit)]
    for i, cluster in enumerate(legit_assignments):
        legit_lists[cluster].append(i)
    
    fraud_lists = [[] for _ in range(n_centroids_fraud)]
    for i, cluster in enumerate(fraud_assignments):
        fraud_lists[cluster].append(i)
    
    # Print cluster sizes
    legit_sizes = [len(lst) for lst in legit_lists]
    fraud_sizes = [len(lst) for lst in fraud_lists]
    print(f"Legit clusters: min={min(legit_sizes)}, max={max(legit_sizes)}, avg={sum(legit_sizes)//len(legit_sizes)}")
    print(f"Fraud clusters: min={min(fraud_sizes)}, max={max(fraud_sizes)}, avg={sum(fraud_sizes)//len(fraud_sizes)}")
    
    print(f"Writing {output_file}...")
    with open(output_file, "wb") as f:
        # Header (version 3 - with exact counts)
        f.write(struct.pack("<I", 0x52494E48))  # "RINH" magic
        f.write(struct.pack("<I", 3))  # version 3 (with n_legit and n_fraud)
        f.write(struct.pack("<I", n_legit + n_fraud))  # total vectors
        f.write(struct.pack("<I", n_legit))  # exact legit count
        f.write(struct.pack("<I", n_fraud))  # exact fraud count
        f.write(struct.pack("<I", n_centroids_legit))  # legit centroids
        f.write(struct.pack("<I", n_centroids_fraud))  # fraud centroids
        f.write(struct.pack("<I", 14))  # dimensions
        
        # Legit vectors (float32)
        f.write(legit_vectors.tobytes())
        
        # Fraud vectors (float32)
        f.write(fraud_vectors.tobytes())
        
        # Legit centroids (float32)
        f.write(legit_centroids.astype(np.float32).tobytes())
        
        # Fraud centroids (float32)
        f.write(fraud_centroids.astype(np.float32).tobytes())
        
        # Legit inverted lists
        for lst in legit_lists:
            f.write(struct.pack("<I", len(lst)))
            for idx in lst:
                f.write(struct.pack("<I", idx))
        
        # Fraud inverted lists
        for lst in fraud_lists:
            f.write(struct.pack("<I", len(lst)))
            for idx in lst:
                f.write(struct.pack("<I", idx))
    
    print(f"Index written to {output_file}")
    print(f"File size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    pack()
