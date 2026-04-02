# Skills — Multimodal RAG Agent Guide

This file is the authoritative reference for any AI agent or LLM operating
inside this repository. It describes the data, the embedding schema, and the
exact commands needed to query the local RAG system and interpret its output.

---

## 1. Architecture Overview

This repository contains a **fully local, privacy-preserving Multimodal
Retrieval-Augmented Generation (RAG) system** built around a single source:

| Asset | File |
|---|---|
| Video | `Deploying a FIWARE Data Space Connector.mp4` |
| Transcript | `Deploying a FIWARE Data Space Connector [5qrhUCczk8w].en.vtt` |

The video is a technical tutorial covering the deployment of a FIWARE Data
Space Connector — a component enabling secure, standards-based data sharing
between organisations in a FIWARE data space.

### Data flow

```
video.mp4 ──→ ffmpeg ──→ /frames/*.jpg (1 frame / 5 s)
                                 │
                                 ▼
                         OpenCLIP ViT-B/32           → ChromaDB: video_frames
                         (image encoder, 512-d)

transcript.vtt ──→ VTT parser ──→ 30-second text chunks
                                           │
                                           ▼
                               sentence-transformers       → ChromaDB: text_chunks
                               (all-MiniLM-L6-v2, 384-d)
```

All models run **locally** (CPU or CUDA). No API keys required. No data leaves
the machine.

---

## 2. Vector Database Schema

**Engine:** ChromaDB (persistent), stored in `./chroma_db/`

### Collection: `text_chunks`

Holds 30-second windows of the video transcript.

| Field | Type | Description |
|---|---|---|
| `id` | string | `"chunk_NNNNN"` (zero-padded integer) |
| `embedding` | float32[384] | L2-normalised sentence-transformers embedding |
| `document` | string | Raw transcript text for this window |
| `metadata.timestamp` | float | Start of window in seconds (e.g. `90.5`) |
| `metadata.timestamp_str` | string | `"HH:MM:SS.mmm"` (e.g. `"00:01:30.500"`) |
| `metadata.text` | string | Same as `document` — duplicate for convenience |

**Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`  
**Distance metric:** cosine (stored as `hnsw:space = cosine`)

### Collection: `video_frames`

Holds one JPEG frame per 5 seconds of the video.

| Field | Type | Description |
|---|---|---|
| `id` | string | `"frame_NNNNN"` (zero-padded integer) |
| `embedding` | float32[512] | L2-normalised OpenCLIP image embedding |
| `metadata.timestamp` | float | Frame position in seconds (e.g. `40.0`) |
| `metadata.timestamp_str` | string | `"HH:MM:SS.mmm"` |
| `metadata.frame_path` | string | Relative path to the JPEG (e.g. `"frames/frame_0000040.jpg"`) |

**Embedding model:** OpenCLIP `ViT-B-32` (pretrained: `openai`)  
**Distance metric:** cosine (`hnsw:space = cosine`)

> **Important:** The CLIP text encoder and image encoder share the same
> embedding space. This means a text query such as *"kubernetes architecture
> diagram"* will meaningfully match frame images that contain such a diagram.

---

## 3. Setup Instructions

### Prerequisites

- Python 3.10+
- `ffmpeg` binary on `PATH`:
  - Windows: `winget install Gyan.FFmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`

### Create the virtual environment

```bash
# From the repository root
python -m venv .venv

# Activate (Windows / Git Bash)
source .venv/Scripts/activate

# Activate (Linux / macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run the ingestion pipeline (one-time)

```bash
python ingest.py
```

This will:
1. Extract ~N frames to `./frames/` (takes a few minutes for a long video).
2. Parse the VTT and create text chunks.
3. Download the embedding models on first run (sentence-transformers ~80 MB,
   OpenCLIP ViT-B/32 ~350 MB — cached by the framework after first download).
4. Embed and store everything in `./chroma_db/`.

To skip already-done steps on re-runs:

```bash
python ingest.py --skip-frames     # frames already extracted
python ingest.py --skip-images     # image embeddings already stored
```

---

## 4. How to Query the RAG System

### Basic usage

```bash
python query.py "USER_QUESTION"
```

### Examples

```bash
# Conceptual / transcript question
python query.py "How does the FIWARE connector handle identity verification?"

# Visual / diagram question
python query.py "Show me the Kubernetes deployment architecture"

# Narrow to text only (faster, no CLIP needed)
python query.py "What is iSHARE?" --text-only

# Narrow to images only
python query.py "helm chart installation steps" --image-only

# Get more results
python query.py "data space participants" --n 8
```

### Output format

The script prints a single JSON object to **stdout**:

```json
{
  "query": "How does the connector handle identity verification?",
  "results": {
    "text": [
      {
        "type": "text",
        "text": "the connector uses decentralized identity and access management ...",
        "timestamp": 90.5,
        "timestamp_str": "00:01:30.500",
        "score": 0.87
      }
    ],
    "images": [
      {
        "type": "image",
        "frame_path": "frames/frame_0000090.jpg",
        "timestamp": 90.0,
        "timestamp_str": "00:01:30.000",
        "score": 0.74
      }
    ]
  }
}
```

**`score`** is cosine similarity in [0, 1]. Higher is more relevant. Scores
above ~0.6 are typically strong matches; below ~0.4 may be weak or
coincidental.

---

## 5. How to Interpret Output and Answer Users

### Step-by-step reasoning process

1. **Run the query** with `python query.py "..."`.
2. **Read `results.text`** entries (sorted by score). The `text` field
   contains the verbatim transcript window. Paraphrase and synthesise across
   the top 2–3 hits to form a grounded answer.
3. **Check `results.images`** for visual confirmation. Use `frame_path` to
   locate the image and `timestamp_str` to tell the user exactly when in the
   video the visual appears.
4. **Cite timestamps** in your answer so the user can jump to the right moment
   in the video. Example: *"As shown at 01:30, the connector uses …"*

### Multimodal correlation

Text and image results are **independently ranked**. To find frames that
correspond to a text hit, compare timestamps:

- A text chunk starting at `timestamp = 90.5` corresponds to video content
  between roughly `90 s` and `120 s` (30-second window).
- The nearest frames are those with `timestamp` values in that range, e.g.,
  `90`, `95`, `100`, `105`, `110`, `115`.

### Example full answer workflow

**User question:** "How do I deploy the FIWARE connector with Helm?"

```bash
python query.py "How do I deploy the FIWARE connector with Helm?" --n 5
```

Suppose the top text result is:
```json
{ "text": "to deploy the fiber data space connector use the helm chart ...",
  "timestamp": 1320.0, "timestamp_str": "00:22:00.000", "score": 0.91 }
```

And the top image result is:
```json
{ "frame_path": "frames/frame_0001320.jpg",
  "timestamp": 1320.0, "timestamp_str": "00:22:00.000", "score": 0.79 }
```

**Agent response to user:**

> At **22:00** in the video, the presenter explains how to deploy the FIWARE
> Data Space Connector using a Helm chart. The relevant frame is at
> `frames/frame_0001320.jpg`. According to the transcript: *"to deploy the
> fiber data space connector use the helm chart …"*

### Score thresholds (guidelines)

| Score range | Interpretation |
|---|---|
| ≥ 0.80 | Very strong match — direct answer likely present |
| 0.60 – 0.79 | Good match — relevant context, may need synthesis |
| 0.40 – 0.59 | Weak match — tangentially related |
| < 0.40 | Poor match — query probably not covered in this video |

---

## 6. Key Scripts Reference

| Script | Purpose |
|---|---|
| `ingest.py` | One-time pipeline: extract frames → embed → store in ChromaDB |
| `query.py` | Real-time retrieval: embed query → search ChromaDB → JSON output |
| `requirements.txt` | Python dependencies |

### Important flags

```
ingest.py
  --skip-frames    Re-use existing ./frames/ JPEGs
  --skip-text      Skip text_chunks ingestion
  --skip-images    Skip video_frames ingestion

query.py
  --n INT          Results per modality (default 5)
  --text-only      Only search text_chunks
  --image-only     Only search video_frames
```

---

## 7. Limitations and Notes

- **Transcription accuracy:** The source is a YouTube auto-generated VTT file.
  Technical terms (e.g. "iSHARE", "Keycloak", "Kubernetes") may be
  mis-transcribed. If a query returns poor results, try alternate spellings or
  a broader phrasing.
- **Frame granularity:** Frames are extracted every 5 seconds. A slide that
  appears for < 5 seconds may be missed; use `--text-only` for those topics.
- **No generative model included:** `query.py` is a retrieval tool only. The
  consuming agent (this session) is responsible for synthesising the retrieved
  context into a final answer.
- **First run is slow:** Model weights are downloaded and cached on first use.
  Subsequent runs load from cache and are fast.
