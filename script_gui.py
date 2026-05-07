import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import json
from parse_json import parse_skillogs_json
from dotenv import load_dotenv
import io
import queue as queue_module

load_dotenv()

email = os.getenv("MAIL")
password = os.getenv("PASSWORD")

# Cache pour le token
_TOKEN = None


def get_token():
    global _TOKEN
    if _TOKEN:
        return _TOKEN

    resp = requests.post(
        "https://ensupsqy.skillogs.info/api/auth/token",
        data={"email": email, "password": password},
    )
    resp.raise_for_status()
    _TOKEN = resp.json()["token"]
    return _TOKEN


def parse_link(url):
    parts = url.split('/')
    if 'cohort' in parts:
        cohort_idx = parts.index('cohort')
        cohort_id = parts[cohort_idx + 1]
    else:
        raise ValueError("URL invalide: 'cohort' manquant")

    if 'module' in parts:
        module_idx = parts.index('module')
        module_id = parts[module_idx + 1]
    else:
        raise ValueError("URL invalide: 'module' manquant")

    if 'session' in parts:
        session_idx = parts.index('session')
        session_id = parts[session_idx + 1]
    else:
        raise ValueError("URL invalide: 'session' manquant")

    return cohort_id, module_id, session_id


def scrape_page_data(cohort_id, module_id, session_id, log_func):
    url = f"https://ensupsqy.skillogs.info/api/user/cohort/{cohort_id}/module/{module_id}/session/{session_id}/content"
    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://ensupsqy.skillogs.io",
        "Referer": "https://ensupsqy.skillogs.io/",
        "Priority": "u=1, i",
        "Sec-Ch-Ua": '"Opera";v="127", "Chromium";v="143", "Not A(Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 OPR/127.0.0.0",
        "X-Language": "fr"
    }
    log_func(f"Récupération des données depuis: {url}")
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    with open("index.json", "w", encoding="utf-8") as f:
        f.write(resp.text)

    return "index.json"


def validate_content(cohort_id, module_id, session_id, content_id, global_key, global_layout, flexible_contents, log_func):
    endpoint_suffix = "flexible_content"

    url = f"https://ensupsqy.skillogs.info/api/user/cohort/{cohort_id}/module/{module_id}/session/{session_id}/content/{content_id}/{endpoint_suffix}"

    headers = {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://ensupsqy.skillogs.io",
        "Referer": "https://ensupsqy.skillogs.io/",
        "Priority": "u=1, i",
        "Sec-Ch-Ua": '"Opera";v="127", "Chromium";v="143", "Not A(Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 OPR/127.0.0.0",
        "X-Language": "fr"
    }

    inner_data = []

    if global_layout == "flexible_quiz":
        log_func(f"   Recherche des réponses pour le quiz {content_id}...")
        correct_answers_map = {}

        for content in flexible_contents:
            question_data = {
                "done": True,
                "time": 30
            }

            q_key = content['key']

            if q_key in correct_answers_map:
                question_data["answer"] = correct_answers_map[q_key]
                log_func(f"   -> Réponse trouvée pour {q_key}: {question_data['answer']}")
            elif 'answers' in content and content['answers']:
                question_data["answer"] = [content['answers'][0]]
                log_func(f"   -> Fallback sur la 1ère réponse pour {q_key}")

            inner_data.append({
                "key": content['key'],
                "layout": content['layout'],
                "data": question_data
            })
    else:
        for content in flexible_contents:
            inner_data.append({
                "key": content['key'],
                "layout": content['layout'],
                "data": {
                    "done": True,
                    "time": 30
                }
            })

    payload_data = {
        "key": global_key,
        "layout": global_layout,
        "data": inner_data
    }

    final_payload = {
        "payload": payload_data
    }

    try:
        log_func(f"\n--- Validation {content_id} ---")
        log_func(f"Request URL: {url}")

        resp = requests.put(url, json=final_payload, headers=headers)

        log_func(f"Status Code: {resp.status_code}")
        try:
            log_func(f"Response JSON: {json.dumps(resp.json(), indent=2)}")
        except json.JSONDecodeError:
            log_func("Response is not JSON (likely HTML):")
            log_func(resp.text[:200] + "...")

        resp.raise_for_status()
        log_func(f"✓ Contenu validé {content_id} (Global: {global_key})")
    except Exception as e:
        log_func(f"✗ Erreur validant {content_id}: {e}")
        log_func(f"Payload qui a échoué: {json.dumps(final_payload, indent=2)}")


def process_single_url(url, log_func):
    """Process a single URL — equivalent to the old main()."""
    if '#' in url:
        url = url.split('#')[0]

    log_func(f"Traitement de l'URL: {url}")

    cohort_id, module_id, session_id = parse_link(url)

    json_file = scrape_page_data(cohort_id, module_id, session_id, log_func)

    parsed_data = parse_skillogs_json(json_file)

    if not parsed_data:
        log_func("Aucune donnée trouvable à valider.")
        return

    log_func(f"Trouvé {len(parsed_data)} éléments à valider.")

    for content_id, layouts in parsed_data.items():
        for layout in layouts:
            validate_content(
                cohort_id,
                module_id,
                session_id,
                content_id,
                layout['global_key'],
                layout['global_layout'],
                layout['flexible_contents'],
                log_func
            )

    log_func("\nToutes les validations sont terminées. Arrêt du script.")


# ─── Couleurs & constantes du thème ───────────────────────────────────────────
BG_DARK       = "#0f1117"
BG_CARD       = "#1a1d27"
BG_INPUT      = "#252836"
BG_HOVER      = "#2d3142"
ACCENT        = "#6c5ce7"
ACCENT_HOVER  = "#7e6ff0"
ACCENT_DIM    = "#4a3fb5"
GREEN         = "#00cec9"
RED           = "#ff6b6b"
RED_HOVER     = "#ff4757"
TEXT_PRIMARY  = "#e8e8e8"
TEXT_SECONDARY= "#8b8fa3"
TEXT_MUTED    = "#555a6e"
BORDER        = "#2d3142"
BORDER_FOCUS  = "#6c5ce7"
FONT_FAMILY   = "Segoe UI"


class SkillogsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Skillogs AutoCompleter")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("820x720")
        self.root.minsize(700, 600)

        self.url_entries = []       # list of (frame, entry_widget, url_string_var)
        self.is_running = False
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue_module.Queue()

        self._build_ui()
        self._poll_log_queue()

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=BG_DARK)
        header.pack(fill="x", padx=28, pady=(22, 0))

        tk.Label(
            header, text="⚡", font=(FONT_FAMILY, 22),
            bg=BG_DARK, fg=ACCENT
        ).pack(side="left")
        tk.Label(
            header, text="Skillogs AutoCompleter",
            font=(FONT_FAMILY, 18, "bold"), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            header, text="File d'attente",
            font=(FONT_FAMILY, 10), bg=BG_DARK, fg=TEXT_SECONDARY
        ).pack(side="right")

        # Separator line
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.pack(fill="x", padx=28, pady=(14, 0))

        # ── URL list area ────────────────────────────────────────────────────
        list_header = tk.Frame(self.root, bg=BG_DARK)
        list_header.pack(fill="x", padx=28, pady=(16, 6))

        tk.Label(
            list_header, text="URLs de session",
            font=(FONT_FAMILY, 11, "bold"), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(side="left")

        self.count_label = tk.Label(
            list_header, text="0 lien(s)",
            font=(FONT_FAMILY, 10), bg=BG_DARK, fg=TEXT_SECONDARY
        )
        self.count_label.pack(side="right")

        # Scrollable container for URL rows
        self.list_container = tk.Frame(self.root, bg=BG_DARK)
        self.list_container.pack(fill="both", expand=False, padx=28)

        self.canvas = tk.Canvas(
            self.list_container, bg=BG_DARK, highlightthickness=0, height=180
        )
        self.scrollbar = tk.Scrollbar(
            self.list_container, orient="vertical", command=self.canvas.yview,
            bg=BG_DARK, troughcolor=BG_CARD, width=8
        )
        self.scroll_frame = tk.Frame(self.canvas, bg=BG_DARK)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw"
        )

        # Make inner frame match canvas width
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Mouse-wheel scrolling — only when cursor is over the URL list
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        # ── Add button ───────────────────────────────────────────────────────
        add_frame = tk.Frame(self.root, bg=BG_DARK)
        add_frame.pack(fill="x", padx=28, pady=(6, 4))

        self.add_btn = tk.Label(
            add_frame,
            text="＋  Ajouter un lien",
            font=(FONT_FAMILY, 11),
            bg=BG_CARD, fg=ACCENT,
            padx=16, pady=10,
            cursor="hand2",
            relief="flat",
            bd=0
        )
        self.add_btn.pack(fill="x")
        self.add_btn.bind("<Button-1>", lambda e: self._add_url_row())
        self.add_btn.bind("<Enter>", lambda e: self.add_btn.configure(bg=BG_HOVER))
        self.add_btn.bind("<Leave>", lambda e: self.add_btn.configure(bg=BG_CARD))

        # ── Action buttons ───────────────────────────────────────────────────
        btn_frame = tk.Frame(self.root, bg=BG_DARK)
        btn_frame.pack(fill="x", padx=28, pady=(10, 6))

        self.start_btn = tk.Label(
            btn_frame,
            text="▶  Lancer la file d'attente",
            font=(FONT_FAMILY, 12, "bold"),
            bg=ACCENT, fg="#ffffff",
            padx=20, pady=12,
            cursor="hand2",
            relief="flat",
            bd=0
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.start_btn.bind("<Button-1>", lambda e: self._start_queue())
        self.start_btn.bind("<Enter>", lambda e: self.start_btn.configure(bg=ACCENT_HOVER) if not self.is_running else None)
        self.start_btn.bind("<Leave>", lambda e: self.start_btn.configure(bg=ACCENT) if not self.is_running else None)

        self.stop_btn = tk.Label(
            btn_frame,
            text="■  Stop",
            font=(FONT_FAMILY, 12, "bold"),
            bg=BG_CARD, fg=RED,
            padx=20, pady=12,
            cursor="hand2",
            relief="flat",
            bd=0
        )
        self.stop_btn.pack(side="left", expand=False, padx=(6, 0))
        self.stop_btn.bind("<Button-1>", lambda e: self._stop_queue())
        self.stop_btn.bind("<Enter>", lambda e: self.stop_btn.configure(bg=BG_HOVER))
        self.stop_btn.bind("<Leave>", lambda e: self.stop_btn.configure(bg=BG_CARD))

        # ── Console / Log area ───────────────────────────────────────────────
        console_header = tk.Frame(self.root, bg=BG_DARK)
        console_header.pack(fill="x", padx=28, pady=(10, 4))

        tk.Label(
            console_header, text="Console",
            font=(FONT_FAMILY, 11, "bold"), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(side="left")

        self.clear_btn = tk.Label(
            console_header, text="Effacer",
            font=(FONT_FAMILY, 9), bg=BG_DARK, fg=TEXT_MUTED, cursor="hand2"
        )
        self.clear_btn.pack(side="right")
        self.clear_btn.bind("<Button-1>", lambda e: self._clear_console())
        self.clear_btn.bind("<Enter>", lambda e: self.clear_btn.configure(fg=TEXT_SECONDARY))
        self.clear_btn.bind("<Leave>", lambda e: self.clear_btn.configure(fg=TEXT_MUTED))

        self.console = tk.Text(
            self.root,
            wrap="word",
            font=("Consolas", 10),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            padx=14,
            pady=10,
            state="disabled",
            height=12
        )
        self.console.pack(fill="both", expand=True, padx=28, pady=(0, 20))

        # Configure text tags for coloured output
        self.console.tag_configure("success", foreground=GREEN)
        self.console.tag_configure("error", foreground=RED)
        self.console.tag_configure("info", foreground=ACCENT)
        self.console.tag_configure("dim", foreground=TEXT_MUTED)

        # Add first empty row
        self._add_url_row()

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _update_count(self):
        n = len(self.url_entries)
        self.count_label.configure(text=f"{n} lien(s)")

    def _add_url_row(self, initial_text=""):
        row = tk.Frame(self.scroll_frame, bg=BG_CARD, pady=4, padx=8)
        row.pack(fill="x", pady=(0, 4))

        idx_label = tk.Label(
            row,
            text=f"#{len(self.url_entries) + 1}",
            font=(FONT_FAMILY, 10, "bold"),
            bg=BG_CARD, fg=TEXT_MUTED,
            width=4
        )
        idx_label.pack(side="left")

        sv = tk.StringVar(value=initial_text)
        entry = tk.Entry(
            row,
            textvariable=sv,
            font=(FONT_FAMILY, 10),
            bg=BG_INPUT,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            relief="flat",
            bd=0
        )
        entry.pack(side="left", fill="x", expand=True, padx=(4, 8), ipady=6)
        entry.insert(0, "")
        # Placeholder
        if not initial_text:
            entry.insert(0, "https://ensupsqy.skillogs.io/cohort/.../module/.../session/...")
            entry.configure(fg=TEXT_MUTED)
            entry.bind("<FocusIn>", lambda e, ent=entry: self._clear_placeholder(ent))
            entry.bind("<FocusOut>", lambda e, ent=entry: self._set_placeholder(ent))

        # Status indicator (dot)
        status = tk.Label(
            row, text="●", font=(FONT_FAMILY, 10),
            bg=BG_CARD, fg=TEXT_MUTED
        )
        status.pack(side="left", padx=(0, 4))

        # Remove button
        remove_btn = tk.Label(
            row, text="✕", font=(FONT_FAMILY, 11, "bold"),
            bg=BG_CARD, fg=TEXT_MUTED, cursor="hand2",
            padx=6
        )
        remove_btn.pack(side="right")
        remove_btn.bind("<Button-1>", lambda e, r=row: self._remove_url_row(r))
        remove_btn.bind("<Enter>", lambda e, b=remove_btn: b.configure(fg=RED))
        remove_btn.bind("<Leave>", lambda e, b=remove_btn: b.configure(fg=TEXT_MUTED))

        self.url_entries.append((row, entry, sv, status))
        self._update_count()
        self._renumber_rows()

        # Scroll to bottom
        self.root.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def _remove_url_row(self, row_frame):
        if self.is_running:
            return
        self.url_entries = [(r, e, s, st) for (r, e, s, st) in self.url_entries if r != row_frame]
        row_frame.destroy()
        self._update_count()
        self._renumber_rows()

        if len(self.url_entries) == 0:
            self._add_url_row()

    def _renumber_rows(self):
        for i, (row, entry, sv, status) in enumerate(self.url_entries):
            for child in row.winfo_children():
                if isinstance(child, tk.Label) and child.cget("width") == 4:
                    child.configure(text=f"#{i + 1}")
                    break

    def _clear_placeholder(self, entry):
        if entry.cget("fg") == TEXT_MUTED:
            entry.delete(0, "end")
            entry.configure(fg=TEXT_PRIMARY)

    def _set_placeholder(self, entry):
        if not entry.get().strip():
            entry.delete(0, "end")
            entry.insert(0, "https://ensupsqy.skillogs.io/cohort/.../module/.../session/...")
            entry.configure(fg=TEXT_MUTED)

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _log(self, message, tag=None):
        """Thread-safe logging: push to queue, polled from main thread."""
        self.log_queue.put((message, tag))

    def _poll_log_queue(self):
        """Drain the log queue from the main thread."""
        while True:
            try:
                message, tag = self.log_queue.get_nowait()
            except queue_module.Empty:
                break
            self.console.configure(state="normal")
            if tag:
                self.console.insert("end", message + "\n", tag)
            else:
                self.console.insert("end", message + "\n")
            self.console.see("end")
            self.console.configure(state="disabled")
        self.root.after(100, self._poll_log_queue)

    # ── Queue execution ──────────────────────────────────────────────────────
    def _set_row_status(self, index, color):
        """Update the status dot color for a row (must be called from main thread)."""
        if 0 <= index < len(self.url_entries):
            _, _, _, status = self.url_entries[index]
            status.configure(fg=color)

    def _start_queue(self):
        if self.is_running:
            return

        # Collect URLs
        urls = []
        for i, (row, entry, sv, status) in enumerate(self.url_entries):
            text = sv.get().strip()
            if text and text != "https://ensupsqy.skillogs.io/cohort/.../module/.../session/...":
                urls.append((i, text))
            self._set_row_status(i, TEXT_MUTED)  # reset status

        if not urls:
            messagebox.showwarning("Aucun lien", "Ajoutez au moins un lien valide avant de lancer.")
            return

        self.is_running = True
        self.stop_event.clear()
        self.start_btn.configure(bg=ACCENT_DIM, fg="#aaa")
        self._log("═" * 50, "dim")
        self._log(f"Lancement de la file d'attente ({len(urls)} lien(s))…", "info")
        self._log("═" * 50, "dim")

        self.worker_thread = threading.Thread(target=self._worker, args=(urls,), daemon=True)
        self.worker_thread.start()

    def _worker(self, urls):
        for idx, (row_index, url) in enumerate(urls):
            if self.stop_event.is_set():
                self._log("\n⛔ File d'attente interrompue par l'utilisateur.", "error")
                break

            self._log(f"\n{'─' * 40}", "dim")
            self._log(f"📌  Lien {idx + 1}/{len(urls)}", "info")
            self._log(f"{'─' * 40}", "dim")

            # Update status to "in progress"
            self.root.after(0, lambda ri=row_index: self._set_row_status(ri, ACCENT))

            try:
                process_single_url(url, self._log)
                # Success
                self.root.after(0, lambda ri=row_index: self._set_row_status(ri, GREEN))
            except Exception as e:
                self._log(f"❌ Erreur lors du traitement: {e}", "error")
                self.root.after(0, lambda ri=row_index: self._set_row_status(ri, RED))

        self._log("\n" + "═" * 50, "dim")
        self._log("✅  Tous les liens ont été traités !", "success")
        self._log("═" * 50, "dim")

        # Re-enable start button from main thread
        self.root.after(0, self._finish_queue)

    def _finish_queue(self):
        self.is_running = False
        self.start_btn.configure(bg=ACCENT, fg="#ffffff")

    def _stop_queue(self):
        if self.is_running:
            self.stop_event.set()
            self._log("⏳ Arrêt demandé… le lien en cours se terminera d'abord.", "error")


def main():
    root = tk.Tk()

    # Try setting DPI awareness on Windows for sharp rendering
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = SkillogsGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
