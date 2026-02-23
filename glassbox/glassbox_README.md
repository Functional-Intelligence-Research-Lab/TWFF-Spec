# Glass Box — Reference Implementation

**Glass Box** is the reference implementation of the [TWFF specification](../spec/SPEC.md).
It is a local-first writing editor that records your process and exports
a PDF proof of your writing effort.

[![Try it](https://img.shields.io/badge/demo-demo.firl.nl-4dabf7?style=for-the-badge)](https://demo.firl.nl)
[![Spec](https://img.shields.io/badge/spec-v0.1.0-10b981?style=for-the-badge)](../spec/SPEC.md)
[![License](https://img.shields.io/badge/license-apache--2.0-f59e0b?style=for-the-badge)](../LICENSE)

---

## Quick start

```bash
git clone https://github.com/Functional-Intelligence-Research-Lab/TWFF-Spec
cd TWFF-Spec/glassbox
pip install -r requirements.txt
python app.py
# Open http://localhost:8080
```

PDF export works immediately. For AI features, install [Ollama](https://ollama.com):
```bash
ollama pull qwen2.5:0.5b   # ~400MB — runs on student hardware
```

---

## Why TWFF? (vs submitting a .docx or .txt)

| Capability | `.docx` / `.txt` | AI Detector | **TWFF** |
|---|---|---|---|
| Proves when edits were made | ✗ | ✗ | **✓** |
| Records AI interactions | depends on OS | ✗ | **✓** |
| Shows paste events | ✗ | ✗ | **✓** |
| Records revision history | Partial (Track Changes) | ✗ | **✓** |
| Cryptographically verifiable | ✗ | ✗ | **✓** |
| Open standard | Partially (OOXML) | ✗ (proprietary) | **✓** |
| Local-first / no cloud | ✓ | ✗ (sends text) | **✓** |
| Deterministic (not probabilistic) | N/A | **✗** | **✓** |
| Human-readable export | ✓ | Score only | **✓ PDF + JSON** |

> **The core difference:** A .docx tells you *what* was written.
> TWFF tells you *how* it was written — keystroke by keystroke, paste by paste, AI call by AI call.
> That's not an incremental improvement on a detector. It's a different primitive.

---

## Features

| Feature | Status | Notes |
|---|---|---|
| TWFF export (`.twff`) | ✅ | ZIP archive with XHTML + process-log.json |
| PDF export | ✅ | WeasyPrint or ReportLab (auto-selected) |
| PDF preview before export | ✅ | Template selector + live HTML preview |
| AI paraphrase | ✅ | Requires Ollama |
| AI continuation | ✅ | Requires Ollama |
| Ghost completion (Tab) | ✅ | Inline suggestion, Escape to dismiss |
| Command palette (Ctrl+K) | ✅ | Full keyboard navigation |
| Paste-at-cursor | ✅ | Annotated + logged, no blocking dialogs |
| Quote & cite | ✅ | AI citation suggestion |
| Offline fallback | ✅ | Rule-based completions without Ollama |
| Process log hash chain | ✅ | SHA-256 per-event chained hash |

---

## Project structure

```text
glassbox/
├── app.py                   Entry point (NiceGUI)
├── requirements.txt         Python dependencies
├── setup_weasyprint.py      WeasyPrint native library checker
├── css/
│   └── theme.css            Design tokens + component styles
├── components/
│   ├── editor.py            Main editor (paste, ghost, AI, export)
│   ├── layout.py            Page layout (header, legend, footer)
│   ├── command_palette.py   Ctrl+K command palette
│   ├── process_log.py       TWFF event log + export
│   ├── ollama_client.py     Async Ollama integration
│   └── pdf_exporter.py      Dual-engine PDF (WeasyPrint / ReportLab)
└── templates/
    └── academic_paper.py    PDF template: academic essay
```

---

## PDF export engines

| Engine | Platform | Install | Quality |
|---|---|---|---|
| **WeasyPrint** | Linux, macOS | `pip install weasyprint` + native libs | Full CSS, paginated A4 |
| **ReportLab** | All platforms | `pip install reportlab` (in requirements) | Clean layout, all features |

Glass Box auto-detects which engine is available and uses the best one.
On Windows, ReportLab is used automatically — no native library setup required.

Run `python setup_weasyprint.py --check` to see what's available on your system.

---

## Validate TWFF examples

```bash
# Install jsonschema (one-time)
pip install jsonschema

# Validate all examples against published schema
python spec/validate_examples.py

# Add _hash chain to examples (if missing)
python spec/validate_examples.py --fix
```

Expected output for a valid log:
```
✓ JSON Schema: valid
✓ Hash chain: intact (12 events)
✓ 1/1 files passed all checks.
```
