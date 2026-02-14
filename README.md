# Tracked Writing File Format (TWFF) Specification v1.0

## Overview

The Tracked Writing File Format (TWFF) is an open, deterministic metadata container designed to capture the provenance of written work in the age of generative AI. Unlike probabilistic AI detectors that guess authorship from final text, TWFF records the process of composition through a structured, auditable event log. It enables *Verifiable Effort*; a cryptographic proof of labor that a student or author can voluntarily disclose to verify the authenticity of their work.

TWFF is built on three core principles:

- **Local-First**: All telemetry is generated and stored on the creator's machine. No third-party servers are involved unless the user chooses to share.

- **Deterministic**: Events are recorded in real time, providing a complete, non‑probabilistic audit trail.

- **Privacy-Preserving**: Only structural metadata is captured *never keystroke content*, screen recordings, or raw prompts. The final text remains separate, sharable as a standard PDF or document.

## Design Philosophy

TWFF is the Glass Box counterpart to the black‑box detection industry. It shifts the foundation from statistical guessing to cryptographic verification. By recording the “diff of thought,” it provides:
- For students: A cryptographic asset to prove their work is their own.
- For educators: Diagnostic insights into writing habits and AI use.
- For researchers: High‑fidelity, ethical datasets on human‑AI collaboration.

Core Architecture
File Format

A TWFF file is a ZIP archive similar to EPUB containing:

- events.json – The core event log (JSON).

- metadata.json – Session metadata and integrity signatures (optional, can be embedded in events.json).

- Optional assets (e.g., exported final draft, embedded references) – but these are not required.

Simplified alternative: a single JSON file with all data, optionally compressed (.twff.json). We recommend the ZIP approach for extensibility.

Event Log Schema

The event log is a JSON array of timestamped events. Each event has a common structure:

```json
{
  "version": "0.1.0",
  "session_id": "uuid-session-12345",
  "user_id": "anon-hash-6789",   // persistent anonymous identifier (user‑generated)
  "start_time": "2026-02-16T09:00:00Z",
  "end_time": "2026-02-16T11:30:00Z",
  "events": [
    {
      "timestamp": "2026-02-16T09:00:01Z",
      "type": "session_start",
      "meta": {}
    },
    {
      "timestamp": "2026-02-16T09:01:15Z",
      "type": "edit",
      "meta": {
        "char_delta": 15,          // net characters added (positive) or removed (negative)
        "source": "human"          // "human", "ai", or "external"
      }
    },
    {
      "timestamp": "2026-02-16T09:05:20Z",
      "type": "paste",
      "meta": {
        "char_count": 450,
        "source": "external"       // pasted from outside the editor
      }
    },
    {
      "timestamp": "2026-02-16T09:10:45Z",
      "type": "ai_interaction",
      "meta": {
        "interaction_type": "paraphrase",   // "brainstorm", "draft", "paraphrase", "summarize"
        "model": "integrated-llm-v1",
        "input_length": 120,
        "output_length": 110,
        "acceptance": "fully_accepted"      // "fully", "partially", "rejected"
      }
    },
    {
      "timestamp": "2026-02-16T11:30:00Z",
      "type": "session_end",
      "meta": {}
    }
  ]
}
```

### Event Types

| Type     | Description     |Meta Fields|
| ------------- | ------------- |-------------|
| session_start |Marks beginning of a writing session. | (none) |
| session_end | Marks end of a session (user closes document or idle timeout). | (none) |
|edit |A contiguous block of characters added or removed.| char_delta (integer, positive for addition, negative for removal), source (string: "human", "ai", "external")|

## Privacy Guarantees

TWFF explicitly does not store:
The raw content of the document.
Individual keystroke content (only aggregated character counts per edit block).
Original prompts or full AI responses (only metadata like length and type).
Personally identifiable information beyond an anonymized user ID (which is user‑generated and can be rotated).

All data is generated locally; the user decides when and with whom to share it.
