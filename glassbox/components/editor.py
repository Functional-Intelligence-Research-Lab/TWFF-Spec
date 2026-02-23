"""
editor.py — Glass Box Editor (NiceGUI / Quasar)
fixes in this version:
  - Paste-at-cursor: uses NiceGUI dialog instead of browser confirm()/prompt()
  - Ghost completion: proper inline floating suggestion with CSS
  - Model selector: fully wired — shows only when Ollama is online
  - PDF preview: inline HTML preview modal before export + template selector
  - PDF export: dual engine (WeasyPrint → ReportLab fallback)
"""
from __future__ import annotations

import asyncio
import os
import sys

import bleach
from components.ollama_client import OllamaClient
from components.process_log import ANNOTATION_TYPES, ProcessLog
from nicegui import ui

# Canonical PDF engine check
try:
    from components.pdf_exporter import PDFExporter, _reportlab_ok, _weasyprint_ok
    def _pdf_ok() -> bool:
        return _weasyprint_ok() or _reportlab_ok()
except ImportError:
    def _pdf_ok() -> bool:
        return False

#  PDF Templates

PDF_TEMPLATES = {
    "academic":    {"label": "Academic Essay",       "desc": "A4, double-spaced, AI appendix"},
    "report":      {"label": "Report / Case Study",  "desc": "A4, single-spaced, section headers"},
    "blog":        {"label": "Blog / Article",       "desc": "Wide margins, informal headers"},
    "assignment":  {"label": "Assignment Submission", "desc": "Cover page, word count, AI declaration"},
}


class Editor:
    def __init__(self):
        # State
        self.content:    str = ""
        self.word_count: int = 0
        self.char_count: int = 0
        self.editor_ref      = None

        # AI
        self.ollama        = OllamaClient()
        self.ghost_enabled = True
        self._selected_text = ""

        # TWFF
        self.process_log = ProcessLog()

        # Export meta
        self._doc_title       = "Untitled Document"
        self._doc_author      = ""
        self._doc_institution = ""
        self._pdf_template    = "academic"

        # UI refs
        self._status_label = None
        self._model_select = None
        self._export_pdf_button = None

    #  Build UI

    def create(self) -> None:
        with ui.column().classes("editor-container w-full h-full flex flex-col"):
            self._build_editor()

        self._attach_paste_handler()
        self._attach_selection_capture()
        self._attach_ghost_completion()
        ui.timer(30.0, self._on_checkpoint)

    def build_model_selector(self) -> None:
        """
        Build Ollama status badge + model dropdown in the header.
        The dropdown is hidden until Ollama is discovered and models are loaded.
        """
        with ui.row().classes("items-center gap-2"):
            # Status dot
            self._status_label = ui.label("● –").classes("ollama-status ollama-offline")

            # Model selector — only visible when Ollama online
            self._model_select = ui.select(
                options=[],
                value=None,
                label=None,
                on_change=self._on_model_change,
            ).classes("model-select").props("dense borderless emit-value map-options")
            self._model_select.set_visibility(False)

        # Discover Ollama after a tick
        ui.timer(0.15, self.init_ollama, once=True)

    async def init_ollama(self) -> None:
        status = await self.ollama.discover()
        if not self._status_label:
            return
        if status.available:
            model_short = (status.active_model or "").split(":")[0]
            self._status_label.set_text(f"● {model_short}")
            self._status_label.classes(remove="ollama-offline", add="ollama-online")
            if self._model_select and status.models:
                options = [{"label": m, "value": m} for m in status.models]
                self._model_select.options = options
                self._model_select.value   = status.active_model
                self._model_select.set_visibility(True)
                self._model_select.update()
        else:
            self._status_label.set_text("● offline")
            self._status_label.classes(remove="ollama-online", add="ollama-offline")
            self._model_select.set_visibility(False)

    #  Editor core ─

    def _build_editor(self) -> None:
        toolbar = (
            ':toolbar="['
            "['bold','italic','underline','subscript','superscript'],"
            "['h1','h2','h3'],"
            "['unordered','ordered'],"
            "['blockquote','code'],"
            "['ann-paraphrase','ann-generated','ann-external'],"
            "['export-twff','export-pdf'],"
            ']"'
        )

        self.editor_ref = ui.editor(
            placeholder="Start writing here. Your process is being recorded.",
            value=self._initial_content(),
            on_change=self._on_content_change,
        ).props(toolbar).classes("w-full h-full border-0")

        # Annotation toolbar buttons
        for ann_key in ("ai_paraphrase", "ai_generated", "external_paste"):
            ann    = ANNOTATION_TYPES[ann_key]
            suffix = ann_key.split("_")[1]
            with self.editor_ref.add_slot(f"ann-{suffix}"):
                ui.button(
                    ann["label"],
                    on_click=lambda a=ann: self._run_annotation_ai(a),
                ).props("flat dense").classes("ann-toolbar-btn")

        with self.editor_ref.add_slot("export-twff"):
            ui.button("Export .twff", on_click=self.export_twff).props(
                "flat dense").classes("ann-toolbar-btn export-btn-twff")

        with self.editor_ref.add_slot("export-pdf"):
            self._export_pdf_button = ui.button(
                "PDF Preview", on_click=self.export_pdf,
            ).props("flat dense").classes("ann-toolbar-btn export-btn-pdf")
            if not _pdf_ok():
                self._export_pdf_button.props(add="disable")
                self._export_pdf_button.tooltip = (
                    "Install reportlab: pip install reportlab"
                )

    #  Paste — no blocking browser dialogs

    def _attach_paste_handler(self) -> None:
        """
        Intercept paste. Inserts annotated span at cursor position.
        Sends event to Python for logging. NO browser confirm() or prompt().
        """
        ui.run_javascript("""
        (function() {
            setTimeout(function() {
                const ed = document.querySelector(
                    '.q-editor__content[contenteditable="true"]'
                );
                if (!ed) return;

                ed.addEventListener('paste', function(e) {
                    e.preventDefault();
                    const cd  = e.clipboardData || window.clipboardData;
                    const txt = cd.getData('text/plain') || '';
                    if (!txt) return;

                    const span = document.createElement('span');
                    span.className = 'ann-external';
                    span.setAttribute('data-tooltip',
                        'External paste — ' + new Date().toISOString());
                    span.textContent = txt;   // plain text only — XSS safe

                    const sel = window.getSelection();
                    if (sel && sel.rangeCount) {
                        const range = sel.getRangeAt(0);
                        range.deleteContents();
                        range.insertNode(span);
                        range.setStartAfter(span);
                        range.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(range);
                    } else {
                        ed.appendChild(span);
                    }

                    window.emitEvent('gb_paste', {
                        length:  txt.length,
                        preview: txt.substring(0, 100)
                    });

                    // Sync content back to Python
                    window.emitEvent('gb_content_sync',
                        {html: ed.innerHTML});
                });
            }, 700);
        })();
        """)

        def _handle_paste(e) -> None:
            data    = e.args or {}
            length  = data.get("length", 0)
            preview = data.get("preview", "")
            pos     = self.char_count
            self.process_log.log_paste(
                char_count=length,
                position_start=pos,
                position_end=pos + length,
                source="external",
                preview=preview,
            )
            # Show a non-blocking NiceGUI notification
            ui.notify(
                f"Pasted {length} chars — logged as external source",
                type="info", position="top-right", timeout=3000,
            )

        def _handle_sync(e) -> None:
            html = (e.args or {}).get("html", "")
            if html:
                self._on_content_change({"value": html})

        ui.on("gb_paste",        _handle_paste)
        ui.on("gb_content_sync", _handle_sync)

    #  Selection capture ─

    def _attach_selection_capture(self) -> None:
        ui.run_javascript("""
        (function() {
            setTimeout(function() {
                document.addEventListener('mouseup', function() {
                    const sel = window.getSelection();
                    const txt = sel ? sel.toString().trim() : '';
                    if (txt.length > 0) {
                        window.emitEvent('gb_selection', {text: txt});
                    }
                });
            }, 700);
        })();
        """)

        def _handle_selection(e) -> None:
            self._selected_text = (e.args or {}).get("text", "")

        ui.on("gb_selection", _handle_selection)

    #  Ghost completion — inline floating suggestion ─

    def _attach_ghost_completion(self) -> None:
        """
        Tab key:
          - If no ghost shown: request a completion from Ollama/fallback
          - If ghost shown: accept it (insert as real text)
        Escape: dismiss ghost.
        Any other key: dismiss ghost.

        Ghost is rendered as a <span id="gb-ghost"> styled via CSS:
          italic, muted colour, not selectable, positioned inline.
        """
        ui.run_javascript("""
        (function() {
            setTimeout(function() {
                const ed = document.querySelector(
                    '.q-editor__content[contenteditable="true"]'
                );
                if (!ed) return;

                let ghostNode = null;

                function removeGhost() {
                    if (ghostNode && ghostNode.parentNode) {
                        ghostNode.parentNode.removeChild(ghostNode);
                    }
                    ghostNode = null;
                }

                // Called from Python with the ghost text
                window._gbShowGhost = function(text) {
                    removeGhost();
                    if (!text) return;
                    const sel = window.getSelection();
                    if (!sel || !sel.rangeCount) return;
                    const range = sel.getRangeAt(0).cloneRange();
                    range.collapse(false);   // collapse to cursor end

                    ghostNode = document.createElement('span');
                    ghostNode.id = 'gb-ghost';
                    ghostNode.className = 'gb-ghost-text';
                    ghostNode.contentEditable = 'false';
                    ghostNode.setAttribute('aria-hidden', 'true');
                    ghostNode.textContent = text;

                    range.insertNode(ghostNode);

                    // Restore cursor to before the ghost
                    const r2 = document.createRange();
                    r2.setStartBefore(ghostNode);
                    r2.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(r2);
                };

                window._gbAcceptGhost = function() {
                    if (!ghostNode) return '';
                    const text = ghostNode.textContent;
                    const parent = ghostNode.parentNode;
                    const textNode = document.createTextNode(text);
                    parent.replaceChild(textNode, ghostNode);
                    ghostNode = null;
                    // Move cursor after accepted text
                    const sel = window.getSelection();
                    const r = document.createRange();
                    r.setStartAfter(textNode);
                    r.collapse(true);
                    sel.removeAllRanges();
                    sel.addRange(r);
                    return text;
                };

                ed.addEventListener('keydown', function(e) {
                    if (e.key === 'Tab') {
                        e.preventDefault();
                        if (ghostNode) {
                            const accepted = window._gbAcceptGhost();
                            window.emitEvent('gb_ghost_accepted', {text: accepted});
                            window.emitEvent('gb_content_sync', {html: ed.innerHTML});
                        } else {
                            // Request ghost from Python
                            const ctx = ed.innerText || '';
                            if (ctx.trim().length >= 8) {
                                window.emitEvent('gb_ghost_request', {context: ctx});
                            }
                        }
                    } else if (e.key === 'Escape') {
                        removeGhost();
                    } else if (!e.ctrlKey && !e.metaKey && !e.altKey
                               && e.key.length === 1) {
                        // Regular typing dismisses ghost
                        removeGhost();
                    }
                });
            }, 700);
        })();
        """)

        async def _handle_ghost_request(e) -> None:
            if not self.ghost_enabled:
                return
            ctx = (e.args or {}).get("context", "")
            if len(ctx.strip()) < 8:
                return
            try:
                if self.ollama.status.available:
                    text = await self.ollama.ghost_completion(ctx)
                else:
                    text = OllamaClient.fallback_completion(ctx)
                if text:
                    ui.run_javascript(f"window._gbShowGhost({repr(text)});")
            except Exception:
                pass  # Ghost is best-effort

        async def _handle_ghost_accepted(e) -> None:
            text = (e.args or {}).get("text", "")
            if text:
                pos = self.char_count
                self.process_log.log_ai_interaction(
                    interaction_type="completion",
                    model=self.ollama.status.active_model or "rule-based",
                    output_length=len(text),
                    position_start=pos,
                    position_end=pos + len(text),
                    output_preview=text[:50],
                    acceptance="fully_accepted",
                )

        ui.on("gb_ghost_request",  _handle_ghost_request)
        ui.on("gb_ghost_accepted", _handle_ghost_accepted)

    #  AI toolbar actions

    async def _run_annotation_ai(self, ann: dict) -> None:
        if ann["log_type"] == "ai_interaction":
            if self.ollama.status.available:
                await self._ai_insert(ann)
            else:
                self._demo_insert(ann)
                ui.notify(
                    "Ollama offline — demo text inserted. Install from ollama.com for real AI.",
                    type="warning", position="top-right",
                )
        else:
            self._demo_insert(ann)

    async def _ai_insert(self, ann: dict) -> None:
        notif = ui.notification(
            f"Running {ann['label']}…", spinner=True, timeout=None,
            position="top-right",
        )
        try:
            ctx = self._strip_html(self.content)[-800:]
            if ann["interaction"] == "paraphrase":
                src    = self._selected_text or self._last_paragraph(ctx)
                result = await self.ollama.paraphrase(src)
            else:
                result = await self.ollama.draft_continuation(ctx)
            model   = self.ollama.status.active_model or "rule-based"
            tooltip = f"{ann['label']} — {model}"
            self._insert_annotated_at_cursor(result, ann, tooltip)
            pos = self.char_count
            self.process_log.log_ai_interaction(
                interaction_type=ann["interaction"],
                model=model,
                output_length=len(result),
                position_start=pos,
                position_end=pos + len(result),
                output_preview=result[:50],
            )
            ui.notify(f"{ann['label']} complete", type="positive", position="top-right")
        except Exception as exc:
            ui.notify(f"AI error: {exc}", type="negative", position="top-right")
        finally:
            notif.dismiss()

    def _demo_insert(self, ann: dict) -> None:
        fixtures = {
            "ai_paraphrase":  "This sentence was rewritten by an AI to improve clarity.",
            "ai_generated":   "This paragraph was drafted entirely by an AI assistant.",
            "external_paste": "This content was pasted from an external source.",
        }
        key  = next((k for k, v in ANNOTATION_TYPES.items() if v == ann), "")
        text = fixtures.get(key, "Sample annotated content.")
        self._insert_annotated_at_cursor(text, ann, f"{ann['label']} — demo")
        pos = self.char_count
        if ann["log_type"] == "ai_interaction":
            self.process_log.log_ai_interaction(
                interaction_type=ann["interaction"],
                model="demo-glass-box",
                output_length=len(text),
                position_start=pos,
                position_end=pos + len(text),
                output_preview=text[:50],
            )

    def _insert_annotated_at_cursor(self, text: str, ann: dict, tooltip: str) -> None:
        css          = ann["css_class"]
        safe_text    = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        safe_tooltip = tooltip.replace("'", "\\'")
        ui.run_javascript(f"""
        (function() {{
            const ed = document.querySelector(
                '.q-editor__content[contenteditable="true"]'
            );
            if (!ed) return;
            const span = document.createElement('span');
            span.className = '{css}';
            span.setAttribute('data-tooltip', '{safe_tooltip}');
            span.textContent = '{safe_text}';
            const sel = window.getSelection();
            if (sel && sel.rangeCount) {{
                const range = sel.getRangeAt(0);
                range.collapse(false);
                range.insertNode(span);
                range.setStartAfter(span);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            }} else {{
                ed.appendChild(span);
            }}
            window.emitEvent('gb_content_sync', {{html: ed.innerHTML}});
        }})();
        """)

    #  Command palette hooks ─

    async def cmd_paraphrase_selection(self) -> None:
        await self._run_annotation_ai(ANNOTATION_TYPES["ai_paraphrase"])

    async def cmd_continue_writing(self) -> None:
        await self._run_annotation_ai(ANNOTATION_TYPES["ai_generated"])

    async def cmd_quote_and_cite(self) -> None:
        selection = self._selected_text
        if not selection:
            ui.notify("Select some text first", type="warning", position="top-right")
            return
        with ui.dialog() as dlg, ui.card().classes("post-export-dialog"):
            ui.label("Quote & Cite").classes("dialog-title")
            ui.label(f'"{selection[:80]}{"…" if len(selection)>80 else ""}"').classes("dialog-meta")
            result_label = ui.label("Analysing…").classes("text-sm text-gray-600")
            cite_label   = ui.label("").classes("text-sm mt-2")

            async def _analyse():
                try:
                    if self.ollama.status.available:
                        res  = await self.ollama.quote_and_cite(
                            selection, self._strip_html(self.content))
                        result_label.set_text(f'Quoted: {res.get("quoted", selection)}')
                        needs = res.get("needs_citation", True)
                        sugg  = res.get("suggestion", "")
                        cite_label.set_text(
                            ("⚠ Likely needs citation. " if needs else "✓ Looks original. ") + sugg
                        )
                    else:
                        result_label.set_text(f'"{selection}"')
                        cite_label.set_text("Ollama offline — AI citation analysis unavailable.")
                except Exception as exc:
                    result_label.set_text(f"Error: {exc}")

            ui.timer(0.1, _analyse, once=True)
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Insert quoted", on_click=lambda: (
                    self._insert_annotated_at_cursor(
                        f'"{selection}"', ANNOTATION_TYPES["external_paste"], "Quoted passage",
                    ), dlg.close(),
                )).props("flat").classes("gb-btn-primary text-xs")
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    def cmd_show_word_count(self) -> None:
        ai_count = sum(1 for e in self.process_log.events if e["type"] == "ai_interaction")
        with ui.dialog() as dlg, ui.card().classes("post-export-dialog"):
            ui.label("Document Stats").classes("dialog-title")
            with ui.column().classes("gap-1"):
                ui.label(f"Words:      {self.word_count:,}").classes("dialog-meta")
                ui.label(f"Characters: {self.char_count:,}").classes("dialog-meta")
                ui.label(f"AI events:  {ai_count}").classes("dialog-meta")
                ui.label(f"Session:    {self.process_log.session_id[:8]}…").classes("dialog-meta")
            with ui.row().classes("justify-end w-full"):
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    def cmd_toggle_ghost(self) -> None:
        self.ghost_enabled = not self.ghost_enabled
        ui.notify(
            f"Ghost completion {'on' if self.ghost_enabled else 'off'}",
            position="top-right",
        )

    def cmd_clear_annotations(self) -> None:
        ui.run_javascript("""
        (function() {
            const ed = document.querySelector('.q-editor__content[contenteditable="true"]');
            if (!ed) return;
            ed.querySelectorAll('.ann-paraphrase,.ann-generated,.ann-external,.ann-completion')
              .forEach(span => span.parentNode.replaceChild(
                  document.createTextNode(span.textContent), span));
            window.emitEvent('gb_content_sync', {html: ed.innerHTML});
        })();
        """)
        ui.notify("Annotations cleared", position="top-right")

    #  Export

    def export_twff(self) -> None:
        xhtml      = self._wrap_xhtml(self.editor_ref.value or "")
        twff_bytes = self.process_log.export(xhtml)
        ui.download(twff_bytes, "document.twff")
        ui.notify("TWFF exported", type="positive", position="top-right")
        self._show_export_dialog()

    def export_pdf(self) -> None:
        """Show PDF preview + metadata + template selector before exporting."""
        self._show_pdf_preview_dialog()

    def _show_pdf_preview_dialog(self) -> None:
        """
        Full-featured PDF export dialog:
          - Template selector (academic, report, blog, assignment)
          - Metadata fields (title, author, institution)
          - Live HTML preview of the annotated content
          - Export button
        """
        with ui.dialog().props("maximized") as dlg, \
             ui.card().classes("w-full h-full flex flex-col gap-0 p-0"):

            #  Header bar
            with ui.row().classes(
                "w-full items-center justify-between px-4 py-3 "
                "border-b border-gray-200 bg-gray-50"
            ):
                ui.label("PDF Preview").classes("text-lg font-semibold")
                ui.button(icon="close", on_click=dlg.close).props("flat round dense")

            #  Two-column layout
            with ui.row().classes("w-full flex-1 min-h-0 gap-0"):

                # Left panel: settings
                with ui.column().classes(
                    "w-80 flex-shrink-0 h-full overflow-y-auto "
                    "border-r border-gray-200 p-4 gap-4"
                ):
                    ui.label("Template").classes("text-xs font-bold uppercase tracking-wider text-gray-500")
                    template_select = ui.select(
                        options={k: v["label"] for k, v in PDF_TEMPLATES.items()},
                        value=self._pdf_template,
                        label=None,
                    ).classes("w-full").props("dense outlined")

                    ui.separator()

                    ui.label("Document Details").classes("text-xs font-bold uppercase tracking-wider text-gray-500")
                    title_input  = ui.input("Title",       value=self._doc_title).classes("w-full")
                    author_input = ui.input("Author",      value=self._doc_author).classes("w-full")
                    inst_input   = ui.input("Institution", value=self._doc_institution).classes("w-full")

                    ui.separator()

                    # Template description
                    tmpl_desc = ui.label(
                        PDF_TEMPLATES[self._pdf_template]["desc"]
                    ).classes("text-xs text-gray-500")

                    def _update_desc(e) -> None:
                        tmpl_desc.set_text(PDF_TEMPLATES.get(e.value, {}).get("desc", ""))

                    template_select.on_value_change(_update_desc)

                    ui.separator()

                    # Stats summary
                    ai_count = sum(
                        1 for e in self.process_log.events if e["type"] == "ai_interaction"
                    )
                    ui.label("Session Stats").classes("text-xs font-bold uppercase tracking-wider text-gray-500")
                    ui.label(f"{self.word_count:,} words").classes("text-xs text-gray-600")
                    ui.label(f"{ai_count} AI interactions").classes("text-xs text-gray-600")
                    ui.label(f"Session {self.process_log.session_id[:8]}…").classes(
                        "text-xs text-gray-400 font-mono"
                    )

                    ui.separator()

                    # Export button
                    status_label = ui.label("").classes("text-xs text-gray-500")

                    async def _do_export() -> None:
                        self._doc_title       = title_input.value or "Untitled"
                        self._doc_author      = author_input.value or ""
                        self._doc_institution = inst_input.value or ""
                        self._pdf_template    = template_select.value or "academic"
                        status_label.set_text("Generating PDF…")
                        dlg.close()
                        try:
                            exporter  = PDFExporter(process_log=self.process_log)
                            pdf_bytes = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: exporter.export(
                                    html_content=self.editor_ref.value or "",
                                    title=self._doc_title,
                                    author=self._doc_author,
                                    institution=self._doc_institution,
                                )
                            )
                            filename = (self._doc_title.replace(" ", "_")[:40]) + ".pdf"
                            ui.download(pdf_bytes, filename)
                            engine   = exporter.engine_name()
                            ui.notify(
                                f"PDF exported ({engine})",
                                type="positive", position="top-right",
                            )
                        except RuntimeError as exc:
                            ui.notify(str(exc), type="negative", position="top-right")

                    ui.button(
                        "Export PDF",
                        icon="picture_as_pdf",
                        on_click=_do_export,
                    ).classes("gb-btn-primary w-full mt-2")

                # Right panel: HTML preview
                with ui.column().classes("flex-1 h-full overflow-y-auto p-6"):
                    ui.label("Preview").classes(
                        "text-xs font-bold uppercase tracking-wider text-gray-500 mb-4"
                    )
                    # Inline preview of annotated HTML
                    preview_html = self._build_preview_html(
                        self.editor_ref.value or "",
                        self._doc_title,
                        self._doc_author,
                        self._doc_institution,
                    )
                    ui.html(preview_html, sanitize=False).classes(
                        "preview-doc border border-gray-200 rounded-lg p-8 bg-white "
                        "shadow-sm font-serif text-gray-900 leading-relaxed"
                    )

        dlg.open()

    def _build_preview_html(
        self, content: str, title: str, author: str, institution: str
    ) -> str:
        """Build an HTML preview of the document with annotation highlights."""
        import datetime
        now = datetime.datetime.utcnow().strftime("%B %d, %Y")
        meta = ""
        if title:       meta += f"<p style='margin:0;font-size:.9rem;color:#666'><strong>Title:</strong> {title}</p>"
        if author:      meta += f"<p style='margin:0;font-size:.9rem;color:#666'><strong>Author:</strong> {author}</p>"
        if institution: meta += f"<p style='margin:0;font-size:.9rem;color:#666'><strong>Institution:</strong> {institution}</p>"
        meta += f"<p style='margin:0;font-size:.9rem;color:#666'><strong>Date:</strong> {now}</p>"
        stats = f"{self.word_count:,} words"
        return f"""
<div style="max-width:700px;margin:0 auto;font-family:'Times New Roman',serif;font-size:11.5pt;line-height:1.75">
<div style="margin-bottom:1.5rem;padding-bottom:1rem;border-bottom:1px solid #e5e7eb">{meta}</div>
<div style="display:flex;gap:1rem;margin-bottom:1.5rem;padding:.5rem .75rem;background:#f9f8f5;border:1px solid #e5e7eb;font-size:.8rem;color:#6b7280">
  <span><span style="background:#3b82f6;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px"></span>AI Paraphrase</span>
  <span><span style="background:#10b981;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px"></span>AI Generated</span>
  <span><span style="background:#f59e0b;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px"></span>External Source</span>
</div>
{content}
<div style="margin-top:2rem;padding-top:1rem;border-top:1px solid #e5e7eb;font-size:.75rem;color:#9ca3af">
  {stats} · Appendix A (AI Usage Report) will be included in the exported PDF
</div>
</div>
"""

    def _show_export_dialog(self) -> None:
        """Post-export TWFF dialog with Tally newsletter embed."""
        with ui.dialog() as dlg, ui.card().classes("post-export-dialog"):
            ui.label("Session exported").classes("dialog-title")
            ui.label(
                f"Session {self.process_log.session_id[:8]}… — "
                f"{len(self.process_log.events)} events recorded"
            ).classes("dialog-meta")
            ui.html("""
                <iframe scrolling="no"
                    style="overflow:hidden;width:100%;height:168px;border:none;"
                    data-tally-src="https://tally.so/embed/jaQNE9?hideTitle=1&transparentBackground=1&dynamicHeight=1"
                    loading="lazy" frameborder="0" title="FIRL Newsletter"></iframe>
            """, sanitize=False)
            ui.run_javascript("if (typeof Tally !== 'undefined') { Tally.loadEmbeds(); }")
            with ui.row().classes("w-full justify-end mt-2"):
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    #  Model change

    def _on_model_change(self, e) -> None:
        model = e.value
        if model:
            self.ollama.set_model(model)
            model_short = model.split(":")[0]
            if self._status_label:
                self._status_label.set_text(f"● {model_short}")
            ui.notify(f"Model: {model}", position="top-right", timeout=2000)

    #  Content change / stats

    def _on_content_change(self, e) -> None:
        if hasattr(e, "value"):
            self.content = e.value
        elif isinstance(e, dict):
            self.content = e.get("value", "")
        plain           = self._strip_html(self.content)
        self.word_count = len(plain.split()) if plain.strip() else 0
        self.char_count = len(plain)

    def _on_checkpoint(self) -> None:
        self.process_log.log_checkpoint(
            char_count=self.char_count,
            word_count=self.word_count,
            cursor_position=self.char_count,
        )

    #  Helpers ─

    @staticmethod
    def _strip_html(html: str) -> str:
        return bleach.clean(html, tags=[], strip=True)

    @staticmethod
    def _last_paragraph(text: str) -> str:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        return paragraphs[-1] if paragraphs else text[-500:]

    @staticmethod
    def _wrap_xhtml(body_html: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            "<head><title>Glass Box Document</title></head>\n"
            f"<body>\n{body_html}\n</body>\n"
            "</html>"
        )

    @staticmethod
    def _initial_content() -> str:
        return """
<h1>Welcome to Glass Box</h1>
<p>This editor records your writing process as a TWFF session. Every edit, paste,
and AI interaction is logged locally — nothing leaves your machine until you export.</p>
<p>Press <code>Tab</code> to see a ghost completion suggestion.
Press <code>Ctrl+K</code> to open the command palette.
Use the toolbar to paraphrase or generate text with AI.</p>
<blockquote><p>Verifiable Effort — not probabilistic detection.</p></blockquote>
"""
