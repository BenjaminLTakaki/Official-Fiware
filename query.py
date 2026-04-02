#!/usr/bin/env python3
"""
query.py — Multimodal RAG retrieval pipeline
=============================================
Embeds a user query with both text and CLIP models, searches the two
ChromaDB collections, and returns a JSON object with the most relevant
text chunks and video frames.

Usage:
    python query.py "How does the FIWARE connector handle authentication?"
    python query.py "Show me the architecture diagram" --n 3
    python query.py "What is the deployment process?" --text-only
    python query.py "kubernetes setup" --image-only

Output (stdout):
    {
      "query": "...",
      "results": {
        "text":   [ { "type": "text",  "text": "...", "timestamp": 42.5,
                      "timestamp_str": "00:00:42.500", "score": 0.87 }, ... ],
        "images": [ { "type": "image", "frame_path": "frames/frame_0000040.jpg",
                      "timestamp": 40.0, "timestamp_str": "00:00:40.000",
                      "score": 0.76 }, ... ]
      }
    }
"""

import os

# Disable TF/Flax backends before any HuggingFace imports
os.environ.setdefault("USE_TF",   "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import json
import sys
import argparse
from pathlib import Path

# ── Configuration (must match ingest.py) ──────────────────────────────────

CHROMA_DIR       = Path("chroma_db")
TEXT_COLLECTION  = "text_chunks"
IMAGE_COLLECTION = "video_frames"

TEXT_MODEL      = "all-MiniLM-L6-v2"
CLIP_MODEL      = "ViT-B-32"
CLIP_PRETRAINED = "openai"

DEFAULT_N_RESULTS = 5


# ── Model helpers ──────────────────────────────────────────────────────────

def load_text_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(TEXT_MODEL)


def load_clip_model():
    import open_clip
    model, _, _ = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    model.eval()
    return model


# ── Embedding ──────────────────────────────────────────────────────────────

def embed_query_text(model, query: str) -> list:
    """Encode query with sentence-transformers; returns normalised list."""
    emb = model.encode([query], normalize_embeddings=True)
    return emb[0].tolist()


def embed_query_clip(model, query: str) -> list:
    """
    Encode a text query with the CLIP *text* encoder.
    This sits in the same embedding space as the CLIP image embeddings,
    so it can be used to search the video_frames collection.
    """
    import torch
    import open_clip

    tokenizer = open_clip.get_tokenizer(CLIP_MODEL)
    tokens    = tokenizer([query])

    with torch.no_grad():
        emb = model.encode_text(tokens)
        emb = emb / emb.norm(dim=-1, keepdim=True)   # L2 normalise

    return emb.cpu().numpy().squeeze().tolist()


# ── Search ─────────────────────────────────────────────────────────────────

def search_text_chunks(client, query_emb: list, n: int) -> list:
    """
    Query the text_chunks collection.
    Returns hits sorted by cosine similarity (highest first).
    """
    collection = client.get_collection(TEXT_COLLECTION)
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=min(n, count),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append(
            {
                "type":          "text",
                "text":          doc,
                "timestamp":     meta.get("timestamp"),
                "timestamp_str": meta.get("timestamp_str"),
                # ChromaDB cosine distance ∈ [0, 2]; similarity = 1 − distance
                "score":         round(1.0 - float(dist), 4),
            }
        )
    return hits


def search_video_frames(client, query_emb: list, n: int) -> list:
    """
    Query the video_frames collection.
    Returns hits sorted by cosine similarity (highest first).
    """
    collection = client.get_collection(IMAGE_COLLECTION)
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=min(n, count),
        include=["metadatas", "distances"],
    )

    hits = []
    for meta, dist in zip(
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append(
            {
                "type":          "image",
                "frame_path":    meta.get("frame_path"),
                "timestamp":     meta.get("timestamp"),
                "timestamp_str": meta.get("timestamp_str"),
                "score":         round(1.0 - float(dist), 4),
            }
        )
    return hits


# ── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the FIWARE multimodal RAG system."
    )
    parser.add_argument(
        "query",
        help="Natural-language question or search phrase",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N_RESULTS,
        help=f"Number of results per modality (default: {DEFAULT_N_RESULTS})",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Search text_chunks only (no image search)",
    )
    parser.add_argument(
        "--image-only",
        action="store_true",
        help="Search video_frames only (no text search)",
    )
    args = parser.parse_args()

    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    output = {
        "query":   args.query,
        "results": {"text": [], "images": []},
    }

    if not args.image_only:
        text_model = load_text_model()
        text_emb   = embed_query_text(text_model, args.query)
        output["results"]["text"] = search_text_chunks(client, text_emb, args.n)

    if not args.text_only:
        clip_model = load_clip_model()
        clip_emb   = embed_query_clip(clip_model, args.query)
        output["results"]["images"] = search_video_frames(client, clip_emb, args.n)

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
