# Tracked Writing File Format (TWFF) Specification v0.1

<center>
<img src=image.png width=50%>
</center>

## Overview

TWFF is a ZIP-based container format that stores both the final written work and the metadata of how it was created. It enables Verifiable Effort; a cryptographic proof of labor that a student or author can voluntarily disclose to verify the authenticity of their work.

Unlike probabilistic AI detectors that guess authorship from final text, TWFF provides a deterministic audit trail of the composition process. It is the Glass Box counterpart to the black-box detection industry.

> For the sake of simplicity GenAI/LLMs will be referenced as 'AI' in this version of the README

## Why a Container Format?

By packaging content and metadata together (similar to EPUB), TWFF enables:

| Use Case     | Components Shared     |What It Enables|
| ------------- | ------------- |-------------|
| Research & Analytics |JSON log only | Privacy-preserving studies of AI usage patterns |
| Verification & Audit | Full container | Cryptographic proof of work |
| Visualization | Content + JSON | Rich, annotated views of the writing process|
| Archival | Full container + assets | Complete record of the creative process|

<!-- ## The Glass Box Container

AI detection is probabilistic. It relies on statistical patterns to "guess" human authorship, leading to high false-positive rates and a lack of auditability.

TWFF is a deterministic container that separates content from process. Like EPUB, it packages:

- **The final work** (XHTML, plain text, images, etc.)
- **The process log** (JSON metadata of composition events)
- **Optional assets** (references, citations, chat transcripts)

This separation allows:
- **Full transparency:** Share the complete container for verification.
- **Privacy-preserving sharing:** User can Share only the JSON metadata for research.
- **Rich visualization:** Render the final work with inline annotations from the process log. -->

## Design Philosophy

| Principle     | Description     |
| ------------- | ------------- |
| Local-First |All telemetry is generated and stored on the creator's machine. No third-party servers are involved unless the user chooses to share. |
| Deterministic | Events are recorded in real time, providing a complete, non‑probabilistic audit trail.|
|Privacy-Preserving|	The final content is stored separately from process metadata. Users control what to share.|
| Extensible | The container format allows for additional assets, transcripts, and signatures.|
|Open Standard	| TWFF is free to implement, with no proprietary lock-in.|

## Container Structure
A TWFF file is a ZIP archive with the following recommended structure:

```text
document.twff
├── content/
│   ├── document.xhtml          # The final written work (XHTML recommended)
│   ├── images/                  # Embedded images (if any)
│   │   └── figure1.png
│   └── assets/                   # Other supporting files
│       ├── references.bib
|       └── style
├── meta/
│   ├── process-log.json         # Core event log (REQUIRED)
│   ├── chat-transcript.json      # Optional: full AI chat history
│   └── manifest.xml              # Container manifest
└── META-INF/
    └── signatures.xml             # Integrity verification (optional)
```

### File Naming Convention

| File    | Convention     | Required? |
| ------------- | ------------- |------------- |
Primary content	| `content/document.xhtml`	| Yes |
Process log	| `meta/process-log.json`	| Yes |
Manifest	| `meta/manifest.xml` | Recommended | 
Signatures | `META-INF/signatures.xml`	| Optional |
Chat transcript	| `meta/chat-transcript.json` | Optional |
Images | `content/images/*`	| As needed |

### Content Format

TWFF recommends XHTML for the primary content because:
- It is XML-based and strict, making parsing and validation reliable.
- It supports embedded semantic markup (e.g., <span> with @data-* attributes).
- It is human-readable and widely supported.
- It can be easily transformed into other formats (pdf, Docx, HTML)

## Process Log Schema (process-log.json)

The process log (meta/process-log.json) captures how the document was constructed. It does not duplicate content; it references positions within the content file using character offsets (or XPath + text offsets for XML-savvy implementations).

### Schema Overview

| Field     | Type    | Description |
| ------------- | ------------- |-------------|
| `version` |string | Schema version (e.g., "0.1.0") |
| `session_id` | string |UUID for the writing session |
|`user_id` |string| Anonymous user identifier (user-generated, can be rotated)|
|`start_time`|string| ISO 8601 timestamp of session start|
|`end_time`|string| ISO 8601 timestamp of session end|
|`content_source`|string| Path to primary content file (e.g., "content/document.xhtml")|
|`events`|array| Array of event objects|

### Event Object

| Field     | Type    | Description |
| ------------- | ------------- |-------------|
| `timestamp` |string | ISO 8601 timestamp|
| `type` | string |Event type (see Event Types Reference) |
|`meta` |object| Type-specific metadata|

### Example

```json
{
  "version": "0.1.0",
  "session_id": "uuid-session-12345",
  "user_id": "anon-hash-6789",
  "start_time": "2026-02-16T09:00:00Z",
  "end_time": "2026-02-16T11:30:00Z",
  "content_source": "content/document.xhtml",
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
        "char_delta": 15,
        "position_start": 0,
        "position_end": 15,
        "source": "human"
      }
    },
    {
      "timestamp": "2026-02-16T09:05:20Z",
      "type": "paste",
      "meta": {
        "char_count": 450,
        "source": "external",
        "position_start": 125,
        "position_end": 575
      }
    },
    {
      "timestamp": "2026-02-16T09:10:45Z",
      "type": "ai_interaction",
      "meta": {
        "interaction_type": "paraphrase",
        "model": "integrated-llm-v1",
        "input_preview": "make this more formal",  // optional prompt preview,
        "output_preview": "subsequently, the implementation...", // first 50 chars
        "output_length": 320,
        "position_start": 575,
        "position_end": 895,
        "acceptance": "fully_accepted"
      }
    },
    {
      "timestamp": "2026-02-16T09:15:30Z",
      "type": "chat_interaction",
      "meta": {
        "message_count": 3,
        "message_preview": "can you help me outline...", // first message preview
        "source_file": "meta/chat-transcript.json"
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

### Event Types Reference

| Field     | Type    | Description |
| ------------- | ------------- |-------------|
|`session_start`|	Beginning of a writing session	|(none)|
|`session_end`	|End of session|	(none)|
|`edit`	|Human typing or deletion|	`char_delta`, `position_start`, p`osition_end`, `source` ("human")
|`paste`	|Text pasted from external source|	`char_count`, `source` ("external" or "ai"), `position_start`, `position_end`|
|`ai_interaction`	|AI assistant invoked	|`interaction_type`, `model`, `input_preview`, `output_preview`, `output_length`, `position_start`, `position_end`, `acceptance`|
|`chat_interaction`|	Multi-turn chat with AI|	`message_count`, `message_preview`, `source_file` (link to full transcript)|
|`focus_change`	|User switcd away from editor|`duration_ms`|
|`checkpoint`	|Auto-save snapshot|	`char_count_total`, `position` (cursr position)|

#### `interaction_type` Values (for `ai_interaction`)

|Value	|Description|
| ------------- | ------------- |
|`brainstorm`	| AI generated ideas or outline |
|`draft`	|AI wrote thye full pasage|
| `paraphrase`| AI rewrote existing text|
|`summarize`	|AI summarized content|
|`expand`	| AI expanded a short phrase|
|`continue`	| AI continued from cursor|

#### `acceptance` Values

|Value |Description |
| ------------- | ------------- |
|`fully_accepted`|	All output used as-is|
|`partially_accepted`|	Some output used, some edited|
|`rejected`|	Output discarded (optional)|
|`modified`|	Output used but significantly edited|

### Chat Transcript Schema (chat-transcript.json) — Optional

For complete transparency, the container may include the full chat history with AI assistants.

```json
{
  "session_id": "uuid-session-12345",
  "messages": [
  
```
### Generating Visualizations
