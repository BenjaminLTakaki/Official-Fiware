# Official-Fiware — Multimodal RAG Agent

A fully local, privacy-preserving Multimodal Retrieval-Augmented Generation (RAG) system built around a FIWARE Data Space Connector deployment tutorial.

## Overview

The system indexes a technical tutorial video (transcript + frames) into a local vector store and exposes a query interface for AI agents.

## Files

| File | Description |
|------|-------------|
| `ingest.py` | Ingest transcript and frames into the vector DB |
| `query.py` | Query the RAG system |
| `skills.md` | Agent guide — schema, embedding layout, example queries |
| `deploy/` | Deployment scripts |
| `frames/` | Extracted video frames |

## Setup

```bash
pip install -r requirements.txt
python ingest.py
python query.py
```

See `skills.md` for the full agent interface reference.
