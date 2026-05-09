"""Generate binary index from references.json.gz."""

import gzip
import json
import struct
from pathlib import Path


def pack():
    resources_path = Path(__file__).parent.parent / "resources"
    data_path = Path(__file__).parent.parent / "data"
    data_path.mkdir(exist_ok=True)

    refs_file = resources_path / "references.json.gz"
    output_file = data_path / "index.bin"

    print(f"Reading {refs_file}...")
    with gzip.open(refs_file, "rt") as f:
        references = json.load(f)

    print(f"Packing {len(references)} vectors...")
    with open(output_file, "wb") as f:
        # TODO: Implement actual packing logic
        for ref in references:
            # Placeholder: write vector and label
            pass

    print(f"Index written to {output_file}")


if __name__ == "__main__":
    pack()
