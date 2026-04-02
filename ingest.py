#!/usr/bin/env python3
"""
ingest.py — Multimodal RAG ingestion pipeline
==============================================
1. Extracts frames from video.mp4 at FRAME_INTERVAL_SEC intervals.
2. Parses the .vtt transcript into text chunks of CHUNK_DURATION_SEC.
3. Embeds text chunks   → sentence-transformers (all-MiniLM-L6-v2, 384-d)
4. Embeds image frames  → OpenCLIP ViT-B/32 image encoder   (512-d)
5. Stores everything in ChromaDB (two collections: text_chunks, video_frames).

Usage:
    python ingest.py                    # full pipeline
    python ingest.py --skip-frames      # skip extraction, use existing /frames
    python ingest.py --skip-text        # skip text ingestion
    python ingest.py --skip-images      # skip image ingestion
"""

import os

# Disable TF/Flax backends in HuggingFace transformers BEFORE any import.
# Prevents a crash when keras/tf_keras is installed without a working tensorflow.
os.environ.setdefault("USE_TF",   "0")
os.environ.setdefault("USE_FLAX", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import re
import json
import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError for → … etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image
from tqdm import tqdm

# ── Configuration ──────────────────────────────────────────────────────────

VIDEO_PATH = Path("Deploying a FIWARE Data Space Connector.mp4")
VTT_PATH   = Path("Deploying a FIWARE Data Space Connector [5qrhUCczk8w].en.vtt")
FRAMES_DIR = Path("frames")
CHROMA_DIR = Path("chroma_db")

FRAME_INTERVAL_SEC = 5    # one frame every N seconds
CHUNK_DURATION_SEC = 30   # group captions into N-second text windows

TEXT_COLLECTION  = "text_chunks"
IMAGE_COLLECTION = "video_frames"

TEXT_MODEL      = "all-MiniLM-L6-v2"  # sentence-transformers model name
CLIP_MODEL      = "ViT-B-32"          # open_clip model name
CLIP_PRETRAINED = "openai"            # open_clip pretrained weights name


# ── Time helpers ───────────────────────────────────────────────────────────

def ts_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS.mmm string to float seconds."""
    h, m, s = ts.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def seconds_to_ts(secs: float) -> str:
    """Convert float seconds to HH:MM:SS.mmm string."""
    h   = int(secs // 3600)
    m   = int((secs % 3600) // 60)
    sec = secs % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


# ── VTT Parsing ────────────────────────────────────────────────────────────

def parse_vtt(vtt_path: Path) -> List[Tuple[float, str]]:
    """
    Parse a YouTube-style WebVTT file.

    YouTube VTT files alternate between two cue types:
      (A) "building" cues  – multi-second duration, inline word timestamps
      (B) "snapshot" cues  – ~0.01 s duration, plain-text caption window

    We collect only the snapshot cues (type B) because they carry clean,
    deduplicated text without embedded tags.

    Returns: list of (start_seconds, clean_text) sorted by time.
    """
    content = vtt_path.read_text(encoding="utf-8")
    blocks  = re.split(r"\n{2,}", content.strip())

    INLINE_TAG  = re.compile(r"<[^>]+>")
    TS_PATTERN  = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    )

    cues: List[Tuple[float, str]] = []

    for block in blocks:
        lines = block.split("\n")

        # Find the timestamp line within this block
        ts_idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ts_idx is None:
            continue

        m = TS_PATTERN.search(lines[ts_idx])
        if not m:
            continue

        start_s = ts_to_seconds(m.group(1))
        end_s   = ts_to_seconds(m.group(2))

        # Only keep snapshot cues (duration ≤ 0.05 s)
        if (end_s - start_s) > 0.05:
            continue

        # Take the first non-blank text line after the timestamp
        for line in lines[ts_idx + 1:]:
            clean = INLINE_TAG.sub("", line).strip()
            if clean:
                cues.append((start_s, clean))
                break

    # Deduplicate consecutive identical caption windows
    deduped: List[Tuple[float, str]] = []
    last_text: str | None = None
    for ts, text in cues:
        if text != last_text:
            deduped.append((ts, text))
            last_text = text

    return deduped


def group_into_chunks(
    cues: List[Tuple[float, str]],
    chunk_duration: float = CHUNK_DURATION_SEC,
) -> List[Tuple[float, str]]:
    """
    Merge consecutive caption cues into longer text chunks.

    Each chunk covers ~chunk_duration seconds of the video.
    Returns: list of (chunk_start_seconds, merged_text).
    """
    if not cues:
        return []

    chunks: List[Tuple[float, str]] = []
    chunk_start = cues[0][0]
    texts: List[str] = []

    for ts, text in cues:
        if ts - chunk_start >= chunk_duration and texts:
            chunks.append((chunk_start, " ".join(texts)))
            chunk_start = ts
            texts = [text]
        else:
            texts.append(text)

    if texts:
        chunks.append((chunk_start, " ".join(texts)))

    return chunks


# ── Frame Extraction ───────────────────────────────────────────────────────

def _ffmpeg_exe() -> str:
    """Return the path to the ffmpeg binary (from imageio-ffmpeg or system)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"   # fall back to system PATH


def _video_duration(video_path: Path) -> float:
    """
    Use the imageio-ffmpeg reader to retrieve video duration without
    decoding any frames.  Falls back to parsing ffmpeg stderr output.
    """
    try:
        import imageio_ffmpeg
        reader = imageio_ffmpeg.read_frames(str(video_path))
        meta = next(reader)     # first yield is the metadata dict
        try:
            reader.close()
        except Exception:
            pass
        if meta.get("duration"):
            return float(meta["duration"])
    except Exception:
        pass

    # Fallback: call ffmpeg -i and parse Duration from stderr
    exe = _ffmpeg_exe()
    result = subprocess.run(
        [exe, "-i", str(video_path)],
        capture_output=True, text=True,
    )
    for line in result.stderr.splitlines():
        if "Duration:" in line:
            dur_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = dur_str.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)

    raise RuntimeError(f"Could not determine duration of {video_path}")


def extract_frames(
    video_path: Path,
    frames_dir: Path,
    interval: int = FRAME_INTERVAL_SEC,
) -> List[Tuple[float, Path]]:
    """
    Extract one JPEG frame every `interval` seconds from the video.

    Uses imageio-ffmpeg's bundled binary — no system ffmpeg required.
    Skips frames that already exist on disk (safe to re-run).
    Returns: list of (timestamp_seconds, frame_path).
    """
    frames_dir.mkdir(exist_ok=True)
    exe = _ffmpeg_exe()

    duration   = _video_duration(video_path)
    timestamps = list(range(0, int(duration), interval))

    print(f"Video duration: {duration:.0f}s → extracting {len(timestamps)} frames …")
    frame_data: List[Tuple[float, Path]] = []

    for ts in tqdm(timestamps, desc="Frames"):
        out_path = frames_dir / f"frame_{ts:07d}.jpg"
        frame_data.append((float(ts), out_path))

        if out_path.exists():
            continue

        cmd = [
            exe,
            "-ss", str(ts),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",       # JPEG quality (2 = high quality, ~1 MB/frame)
            "-y",              # overwrite without asking
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            msg = result.stderr.decode(errors="replace")
            print(f"\n  Warning: frame at {ts}s failed: {msg}", file=sys.stderr)

    return frame_data


# ── Model Loading ──────────────────────────────────────────────────────────

def load_text_model():
    from sentence_transformers import SentenceTransformer
    print(f"Loading text model  : {TEXT_MODEL}")
    return SentenceTransformer(TEXT_MODEL)


def load_clip_model():
    import open_clip
    print(f"Loading CLIP model  : {CLIP_MODEL} / {CLIP_PRETRAINED}")
    model, _, preprocess = open_clip.create_model_and_transforms(
        CLIP_MODEL, pretrained=CLIP_PRETRAINED
    )
    model.eval()
    return model, preprocess


# ── Embedding ──────────────────────────────────────────────────────────────

def embed_texts(model, texts: List[str]) -> np.ndarray:
    """Encode texts with sentence-transformers; returns L2-normalised array."""
    return model.encode(texts, show_progress_bar=True, normalize_embeddings=True)


def embed_images(model, preprocess, paths: List[Path]) -> np.ndarray:
    """Encode images with the CLIP image encoder; returns L2-normalised array."""
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model  = model.to(device)
    all_emb: List[np.ndarray] = []

    for path in tqdm(paths, desc="Image embeddings"):
        img = (
            preprocess(Image.open(path).convert("RGB"))
            .unsqueeze(0)
            .to(device)
        )
        with torch.no_grad():
            emb = model.encode_image(img)
            emb = emb / emb.norm(dim=-1, keepdim=True)   # L2 normalise
        all_emb.append(emb.cpu().numpy().squeeze())

    return np.stack(all_emb)


# ── ChromaDB Ingestion ─────────────────────────────────────────────────────

def get_chroma_client(chroma_dir: Path):
    import chromadb
    return chromadb.PersistentClient(path=str(chroma_dir))


def ingest_text_chunks(
    client,
    chunks: List[Tuple[float, str]],
    text_model,
    batch_size: int = 500,
) -> None:
    """
    Embed text chunks and upsert into the 'text_chunks' ChromaDB collection.

    Schema
    ------
    id        : "chunk_NNNNN"
    embedding : 384-d float32  (sentence-transformers all-MiniLM-L6-v2)
    document  : raw text of the chunk
    metadata  :
        timestamp     (float)  – start of chunk in seconds
        timestamp_str (str)    – "HH:MM:SS.mmm"
        text          (str)    – duplicate of document for easy retrieval
    """
    collection = client.get_or_create_collection(
        name=TEXT_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    texts     = [c[1] for c in chunks]
    ids       = [f"chunk_{i:05d}" for i in range(len(chunks))]
    metadatas = [
        {
            "timestamp":     ts,
            "timestamp_str": seconds_to_ts(ts),
            "text":          text,
        }
        for ts, text in chunks
    ]

    print(f"\nEmbedding {len(texts)} text chunks …")
    embeddings = embed_texts(text_model, texts).tolist()

    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids       =ids[i : i + batch_size],
            embeddings=embeddings[i : i + batch_size],
            documents =texts[i : i + batch_size],
            metadatas =metadatas[i : i + batch_size],
        )
    print(f"  → Stored {len(ids)} chunks in '{TEXT_COLLECTION}'")


def ingest_frames(
    client,
    frame_data: List[Tuple[float, Path]],
    clip_model,
    preprocess,
    batch_size: int = 500,
) -> None:
    """
    Embed video frames and upsert into the 'video_frames' ChromaDB collection.

    Schema
    ------
    id        : "frame_NNNNN"
    embedding : 512-d float32  (OpenCLIP ViT-B/32 image encoder)
    metadata  :
        timestamp     (float)  – frame position in seconds
        timestamp_str (str)    – "HH:MM:SS.mmm"
        frame_path    (str)    – relative path to the JPEG file
    """
    collection = client.get_or_create_collection(
        name=IMAGE_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    paths     = [fd[1] for fd in frame_data]
    ids       = [f"frame_{i:05d}" for i in range(len(frame_data))]
    metadatas = [
        {
            "timestamp":     ts,
            "timestamp_str": seconds_to_ts(ts),
            "frame_path":    str(path),
        }
        for ts, path in frame_data
    ]

    print(f"\nEmbedding {len(paths)} frames …")
    embeddings = embed_images(clip_model, preprocess, paths).tolist()

    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids       =ids[i : i + batch_size],
            embeddings=embeddings[i : i + batch_size],
            metadatas =metadatas[i : i + batch_size],
        )
    print(f"  → Stored {len(ids)} frames in '{IMAGE_COLLECTION}'")


# ── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest FIWARE video + transcript into ChromaDB for multimodal RAG."
    )
    parser.add_argument(
        "--skip-frames",
        action="store_true",
        help="Skip frame extraction; re-use JPEGs already in ./frames/",
    )
    parser.add_argument(
        "--skip-text",
        action="store_true",
        help="Skip text chunk ingestion",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip image frame ingestion",
    )
    args = parser.parse_args()

    # ── 1. Frame extraction ─────────────────────────────────────────────
    if not args.skip_frames:
        frame_data = extract_frames(VIDEO_PATH, FRAMES_DIR)
    else:
        print("Re-using existing frames …")
        frame_data = sorted(
            [
                (float(p.stem.split("_")[1]), p)
                for p in FRAMES_DIR.glob("frame_*.jpg")
            ],
            key=lambda x: x[0],
        )
        print(f"  Found {len(frame_data)} frames")

    # ── 2. Transcript parsing ───────────────────────────────────────────
    print(f"\nParsing transcript: {VTT_PATH.name}")
    cues   = parse_vtt(VTT_PATH)
    chunks = group_into_chunks(cues)
    print(f"  {len(cues)} caption cues  →  {len(chunks)} text chunks "
          f"(~{CHUNK_DURATION_SEC}s each)")

    # ── 3. Load models ──────────────────────────────────────────────────
    text_model              = None if args.skip_text   else load_text_model()
    clip_model, preprocess  = (None, None) if args.skip_images else load_clip_model()

    # ── 4. Ingest into ChromaDB ─────────────────────────────────────────
    client = get_chroma_client(CHROMA_DIR)

    if not args.skip_text:
        ingest_text_chunks(client, chunks, text_model)

    if not args.skip_images:
        ingest_frames(client, frame_data, clip_model, preprocess)

    # ── Summary ─────────────────────────────────────────────────────────
    summary = {
        "text_chunks":  len(chunks),
        "video_frames": len(frame_data),
        "chroma_dir":   str(CHROMA_DIR),
    }
    print("\nIngestion complete.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
