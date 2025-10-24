"""
Author: Russell Elliott
Date: 2025-10-24
Search and analyze YouTube videos, playlists, and channels
For full documentation, see the README in this tool's directory
"""

# ─── STANDARD LIBRARIES ──────────────────────────────────────────────
from __future__ import annotations
import csv
import io
import os
import threading
import time
import urllib.request
import webbrowser

# ─── TKINTER MODULES ─────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ─── THIRD-PARTY LIBRARIES ───────────────────────────────────────────
from dataclasses import dataclass
from datetime import datetime
from PIL import Image, ImageTk
import requests
from tkcalendar import DateEntry
from typing import List, Tuple

# ─────────────────────────────
# CONFIGURATION SETUP
# ─────────────────────────────

# API Key from Google
API_KEY = "AIzaSyCywVcWUL24bl4NpiCUGfwtpMKdtW3hvVo"

# Shared HTTP defaults
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

# View Thresholds
VIEW_THRESHOLDS: List[Tuple[str, int]] = [
    ("Any",   0),
    ("10K+",  10_000),
    ("50K+",  50_000),
    ("100K+", 100_000),
    ("250K+", 250_000),
    ("1M+",   1_000_000),
    ("5M+",   5_000_000),
    ("10M+",  10_000_000),
    ("50M+",  50_000_000),
    ("100M+", 100_000_000),
]

#Duration Thresholds
DURATIONS: List[Tuple[str, str]] = [
    ("Any",              "any"),
    ("< 4 min (Short)",  "short"),
    ("4–20 min (Medium)","medium"),
    ("> 20 min (Long)",  "long"),
    ("≥ 60 min",         "over1h"),
    ("≥ 180 min",        "over3h"),
]

# ─────────────────────────────
# DATA TYPES
# ─────────────────────────────

@dataclass
class SearchOptions:
    query: str
    include_videos: bool
    include_playlists: bool
    include_channels: bool
    min_views_label: str
    min_views_value: int
    duration_label: str
    duration_value: str
    published_after: str | None
    published_before: str | None
    max_pages_per_type: int

# ─────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────

# Parse YYYY-MM-DD safely; return None on failure
def parse_iso_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None

# Convert date (YYYY-MM-DD) to RFC3339 start of day
def to_rfc3339_day_start(d: str) -> str:
    return f"{d}T00:00:00Z"

# Convert date (YYYY-MM-DD) to RFC3339 end of day
def to_rfc3339_day_end(d: str) -> str:
    return f"{d}T23:59:59Z"

# Convert ISO8601 duration (e.g., PT1H2M3S) to seconds
def iso8601_duration_to_seconds(iso: str) -> int:
    total = 0
    num = ""
    iso = iso.replace("P", "")
    for ch in iso:
        if ch == "T":
            continue
        elif ch.isdigit():
            num += ch
        else:
            if ch == "H":
                total += int(num or 0) * 3600
            elif ch == "M":
                total += int(num or 0) * 60
            elif ch == "S":
                total += int(num or 0)
            num = ""
    return total

# Format seconds as mm:ss or hh:mm:ss
def seconds_to_hms(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

# Check if a given duration (in seconds) matches the chosen filter
def duration_ok(filter_key: str, seconds: int) -> bool:
    if filter_key == "any":
        return True
    if filter_key == "short":
        return seconds < 4 * 60
    if filter_key == "medium":
        return 4 * 60 <= seconds <= 20 * 60
    if filter_key == "long":
        return seconds > 20 * 60
    if filter_key == "over1h":
        return seconds >= 60 * 60
    if filter_key == "over3h":
        return seconds >= 3 * 60 * 60
    return True

# ─────────────────────────────
# MAIN FUNCTIONS
# ─────────────────────────────

class YouTubeScoutApp(ttk.Frame):
    
    # Initialize UI, state, and event bindings
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        
        # Basic window config
        self.master.title("YouTube Scout")
        self.master.geometry("1660x860")
        self.master.minsize(1280, 680)
        self.master.configure(bg="#f6f7fb")
        self._apply_style()

        # Layout policy: 2 columns (table + preview), results row grows
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        # Build distinct UI sections
        self._build_controls()
        self._build_results_table()
        self._build_preview()
        self._build_statusbar()

        # Context menu on table rows + keyboard shortcuts
        self._make_context_menu()
        self._bind_shortcuts()

        self.pack(fill=tk.BOTH, expand=True)
        self._center_window()

    # Configure ttk styles and colors once
    def _apply_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
            
        style.configure("TLabel", background="#f6f7fb", foreground="#1f2430")
        style.configure("TFrame", background="#f6f7fb")
        style.configure("TCheckbutton", background="#f6f7fb", foreground="#1f2430")
        style.configure("TButton", padding=(10, 6))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#566176")
        style.configure("Status.TLabel", background="#eef1f7", anchor="w")
        style.map("TButton", relief=[("pressed", "sunken"), ("!pressed", "raised")])

    # Top control strip: query input, type toggles, filters, and action buttons
    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        # Let the query entry stretch
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Search criteria", style="Header.TLabel")\
            .grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # Query row
        ttk.Label(controls, text="Query:").grid(row=1, column=0, sticky="w")
        self.entry_query = ttk.Entry(controls)
        self.entry_query.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        self.entry_query.insert(0, "e.g., python tutorial, guitar pedal review, fitness tips…")
        self.entry_query.bind("<FocusIn>", self._placeholder_clear)

        # Second row: everything else in one horizontal strip
        row = ttk.Frame(controls)
        row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Toggles
        self.var_inc_videos    = tk.BooleanVar(value=True)
        self.var_inc_playlists = tk.BooleanVar(value=False)
        self.var_inc_channels  = tk.BooleanVar(value=False)

        ttk.Checkbutton(row, text="Videos",   variable=self.var_inc_videos).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(row, text="Playlists",variable=self.var_inc_playlists).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(row, text="Channels", variable=self.var_inc_channels).pack(side=tk.LEFT, padx=(0, 20))

        # Min views
        ttk.Label(row, text="Min views:").pack(side=tk.LEFT)
        self.combo_views = ttk.Combobox(row, state="readonly",
                                        width=8,
                                        values=[label for label, _ in VIEW_THRESHOLDS])
        self.combo_views.current(0)
        self.combo_views.pack(side=tk.LEFT, padx=(6, 18))

        # Duration
        ttk.Label(row, text="Duration:").pack(side=tk.LEFT)
        self.combo_duration = ttk.Combobox(row, state="readonly",
                                           width=10,
                                           values=[label for label, _ in DURATIONS])
        self.combo_duration.current(0)
        self.combo_duration.pack(side=tk.LEFT, padx=(6, 18))

        # Published After
        ttk.Label(row, text="Published After:").pack(side=tk.LEFT)
        self.entry_after = DateEntry(row, date_pattern="yyyy-mm-dd", width=12)
        self.entry_after.delete(0, tk.END)
        self.entry_after.pack(side=tk.LEFT, padx=(6, 18))

        # Published Before
        ttk.Label(row, text="Published Before:").pack(side=tk.LEFT)
        self.entry_before = DateEntry(row, date_pattern="yyyy-mm-dd", width=12)
        self.entry_before.delete(0, tk.END)
        self.entry_before.pack(side=tk.LEFT, padx=(6, 18))

        # Pages per type
        ttk.Label(row, text="Pages:").pack(side=tk.LEFT)
        self.pages_var = tk.IntVar(value=5)
        self.spin_pages = ttk.Spinbox(
            row, from_=1, to=10, textvariable=self.pages_var, width=4, state="readonly"
        )
        self.spin_pages.pack(side=tk.LEFT, padx=(6, 18))

        # Buttons row
        btns = ttk.Frame(controls)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.btn_search = ttk.Button(btns, text="Search", command=self.on_search)
        self.btn_search.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Clear",     command=self.on_clear).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text="Export CSV",command=self.on_export_csv).pack(side=tk.LEFT, padx=(0, 8))

    # Center pane: searchable results table with sortable columns
    def _build_results_table(self) -> None:
        wrapper = ttk.Frame(self)
        wrapper.grid(row=1, column=0, sticky="nsew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)

        cols = ("title", "channel", "kind", "views", "likes", "comments", "duration", "published", "url")
        self.tree = ttk.Treeview(wrapper, columns=cols, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Headings
        headings = {
            "title": "Title",
            "channel": "Channel",
            "kind": "Type",
            "views": "Views",
            "likes": "Likes",
            "comments": "Comments",
            "duration": "Duration",
            "published": "Published",
            "url": "URL / ID",
        }
        for cid in cols:
            self.tree.heading(cid, text=headings[cid], command=lambda c=cid: self._sort_by(c, False))

        # Compact widths: let Title/Channel stretch
        self.tree.column("title",    anchor="w", width=200, minwidth=200, stretch=False)
        self.tree.column("channel",  anchor="w", width=150, minwidth=150, stretch=False)
        self.tree.column("kind",     anchor="center", width=100, minwidth=80,  stretch=False)
        self.tree.column("views",    anchor="e", width=50, minwidth=50,  stretch=False)
        self.tree.column("likes",    anchor="e", width=50, minwidth=50,  stretch=False)
        self.tree.column("comments", anchor="e", width=70, minwidth=70, stretch=False)
        self.tree.column("duration", anchor="center", width=70, minwidth=70,  stretch=False)
        self.tree.column("published",anchor="center", width=70, minwidth=70, stretch=False)
        self.tree.column("url",      anchor="w", width=200, minwidth=200, stretch=False)

        # Scrollbars
        vsb = ttk.Scrollbar(wrapper, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Selection & interactions
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.tree.bind("<Double-1>",         self._on_open_current)
        self.tree.bind("<Button-3>",         self._on_right_click)


    # Right panel: thumbnail and details for the selected row
    def _build_preview(self) -> None:
        preview = ttk.Frame(self)
        preview.grid(row=1, column=1, sticky="nsew", padx=(12, 0))
        preview.columnconfigure(0, weight=1)
        ttk.Label(preview, text="Preview", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        
        self.thumb_label = ttk.Label(preview, text="No thumbnail")
        self.thumb_label.grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.detail_text = tk.Text(preview, height=14, wrap="word")
        self.detail_text.insert("1.0", "Select a row to see details here.")
        self.detail_text.configure(state="disabled")
        self.detail_text.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        
        preview.rowconfigure(2, weight=1)

    # Bottom bar: text status (left) and spinner (right)
    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        bar.columnconfigure(0, weight=1)

        # Left: status text
        self.status = ttk.Label(bar, text="Ready", style="Status.TLabel", relief=tk.SOLID, padding=(8, 4))
        self.status.grid(row=0, column=0, sticky="ew")

        # Right: indeterminate spinner
        right = ttk.Frame(bar)
        right.grid(row=0, column=1, sticky="e", padx=(8, 0))
    
        self.progress = ttk.Progressbar(right, mode="indeterminate", length=160)
        self.progress.pack(side=tk.LEFT) 


    # Context menu for the results table (open/copy)
    def _make_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Open in browser", command=self._on_open_current)
        self.menu.add_command(label="Copy URL", command=self._on_copy_url)


    # A few handy keyboard shortcuts
    def _bind_shortcuts(self):
        self.master.bind("<Return>", lambda e: self.on_search())
        self.master.bind("<Control-l>", lambda e: (self.entry_query.focus_set(), self.entry_query.select_range(0, tk.END)))
        self.master.bind("<Control-e>", lambda e: self.on_export_csv())
        self.master.bind("<Control-c>", lambda e: self._on_copy_url())
        self.master.bind("<Control-o>", lambda e: self._on_open_current())

    # Clear the example text the first time the Entry is focused
    def _placeholder_clear(self, event: tk.Event) -> None:
        if self.entry_query.get().startswith("e.g., "):
            self.entry_query.delete(0, tk.END)


    # Read widgets to typed dataclass we pass through the pipeline
    def _collect_options(self) -> SearchOptions:
        q = self.entry_query.get().strip()
        if not q or q.startswith("e.g., "):
            raise ValueError("Please enter a search query.")

        views_label = self.combo_views.get()
        min_views_val = next((v for l, v in VIEW_THRESHOLDS if l == views_label), 0)

        dur_label = self.combo_duration.get()
        dur_val = next((v for l, v in DURATIONS if l == dur_label), "any")

        after = self.entry_after.get().strip() or None
        before = self.entry_before.get().strip() or None
        if after and not parse_iso_date(after):
            raise ValueError("'Published After' must be YYYY-MM-DD")
        if before and not parse_iso_date(before):
            raise ValueError("'Published Before' must be YYYY-MM-DD")

        return SearchOptions(
            query=q,
            include_videos=self.var_inc_videos.get(),
            include_playlists=self.var_inc_playlists.get(),
            include_channels=self.var_inc_channels.get(),
            min_views_label=views_label,
            min_views_value=min_views_val,
            duration_label=dur_label,
            duration_value=dur_val,
            published_after=after,
            published_before=before,
            max_pages_per_type=max(1, min(10, int(self.pages_var.get()))),
        )

    # ─────────────────────────────
    # YOUTUBE API
    # ─────────────────────────────
    
    # Return True if the user's query looks present in the given title
    def _title_matches(self, query: str, title: str) -> bool:
        if not query or not title:
            return False
        q = query.lower().strip()
        t = title.lower()
        
        # Require all non-empty query tokens to be present in title
        tokens = [tok for tok in q.split() if tok]
        return all(tok in t for tok in tokens) if tokens else q in t
        
    # Searches YouTube for videos, playlists, or channels matching the query
    def _yt_search(
        self,
        q: str,
        part_type: str,
        published_after: str | None,
        published_before: str | None,
        page_token: str | None = None
    ):
        params = {
            "part": "snippet",
            "q": q,
            "type": part_type,
            "maxResults": 50,
            "key": API_KEY,
        }

        # Only sort by viewCount for video searches; use default relevance for others
        if part_type == "video":
            params["order"] = "viewCount"

        # Date fences (RFC3339); we snap the day to start/end to include full days
        if published_after:
            params["publishedAfter"] = to_rfc3339_day_start(published_after)
        if published_before:
            params["publishedBefore"] = to_rfc3339_day_end(published_before)

        if page_token:
            params["pageToken"] = page_token

        try:
            r = SESSION.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            reason = ""
            try:
                payload = r.json()
                reason = payload.get("error", {}).get("errors", [{}])[0].get("reason", "")
                message = payload.get("error", {}).get("message", "")
            except Exception:
                message = r.text

            raise requests.HTTPError(f"{e} | reason={reason!r} | message={message}") from e

    # Batch-enrich a list of video IDs with duration and statistics
    def _yt_videos(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}

        params = {
            "part": "contentDetails,statistics,snippet",
            "id": ",".join(ids[:50]),
            "key": API_KEY,
            "maxResults": 50,
        }

        try:
            r = SESSION.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except requests.HTTPError as e:
            try:
                payload = r.json()
                reason = payload.get("error", {}).get("errors", [{}])[0].get("reason", "")
                message = payload.get("error", {}).get("message", "")
            except Exception:
                reason = ""
                message = r.text
            raise requests.HTTPError(f"{e} | reason={reason!r} | message={message}") from e

        by_id: dict[str, dict] = {}
        for it in data.get("items", []):
            vid = it.get("id", "")
            stats = it.get("statistics", {}) or {}
            details = it.get("contentDetails", {}) or {}
            snip = it.get("snippet", {}) or {}

            by_id[vid] = {
                "viewCount": int(stats.get("viewCount", 0) or 0),
                "likeCount": int(stats.get("likeCount", 0) or 0),
                "commentCount": int(stats.get("commentCount", 0) or 0),
                "durationSec": iso8601_duration_to_seconds(details.get("duration", "PT0S")),
                "publishedAt": snip.get("publishedAt", ""),
                "thumb": (
                    (snip.get("thumbnails", {}) or {}).get("medium")
                    or (snip.get("thumbnails", {}) or {}).get("default")
                    or {}
                ).get("url", ""),
                "title": snip.get("title", ""),
                "channelTitle": snip.get("channelTitle", ""),
            }

        return by_id

    # Entry point when the user clicks Search
    def on_search(self) -> None:
        if not API_KEY:
            messagebox.showerror("Missing API key", "Set environment variable YT_API_KEY (or paste key into the script).")
            return
            
        if not (self.var_inc_videos.get() or self.var_inc_playlists.get() or self.var_inc_channels.get()):
            messagebox.showwarning("Nothing to search", "Please select at least one type (Videos, Playlists, or Channels).")
            return

        try:
            opts = self._collect_options()
        except ValueError as e:
            messagebox.showwarning("Missing/invalid input.", str(e))
            self.status.configure(text=str(e))
            self.entry_query.focus_set()
            return

        # UI: start spinner + disable controls
        self._set_controls_enabled(False)
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.status.configure(text="Searching…")
        self.progress.start(8)

        start_ts = time.time()

        # Kick off background work
        t = threading.Thread(target=self._search_worker, args=(opts, start_ts), daemon=True)
        t.start()

    # Gathers results
    def _search_worker(self, opts, start_ts):
        try:
            total_items: list[tuple[str, str, str, str, str, str]] = []
            want_types: list[str] = []
            if opts.include_videos:
                want_types.append("video")
            if opts.include_playlists:
                want_types.append("playlist")
            if opts.include_channels:
                want_types.append("channel")

            # Cap pages per type to save quota during testing
            MAX_PAGES_PER_TYPE = opts.max_pages_per_type

            # 1) fetch ids/snippets per type
            for t in want_types:
                page_token = None
                pages = 0
                while True:
                    data = self._yt_search(
                        opts.query, t, opts.published_after, opts.published_before, page_token
                    )
                    items = data.get("items", [])

                    # 2) Post-filter to emulate "title-only" behavior
                    for it in items:
                        id_block = it.get("id", {})
                        snip = it.get("snippet", {}) or {}

                        thumb = (
                            (snip.get("thumbnails", {}) or {}).get("medium")
                            or (snip.get("thumbnails", {}) or {}).get("default")
                            or {}
                        ).get("url", "")
                        published_at = snip.get("publishedAt", "")
                        channel_title = snip.get("channelTitle", "") or ""
                        title = snip.get("title", "") or ""

                        if t == "video":
                            vid = id_block.get("videoId")
                            if not vid:
                                continue
                            if not self._title_matches(opts.query, title):
                                continue
                            total_items.append(("video", vid, title, channel_title, published_at, thumb))

                        elif t == "playlist":
                            pid = id_block.get("playlistId")
                            if not pid:
                                continue
                            if not self._title_matches(opts.query, title):
                                continue
                            total_items.append(("playlist", pid, title, channel_title, published_at, thumb))

                        elif t == "channel":
                            cid = id_block.get("channelId")
                            if not cid:
                                continue
                            if not self._title_matches(opts.query, title):
                                continue
                            total_items.append(("channel", cid, title, title, published_at, thumb))

                    page_token = data.get("nextPageToken")
                    pages += 1
                    if not page_token or pages >= MAX_PAGES_PER_TYPE:
                        break

            # 3) Enrich video rows with stats/duration
            video_ids = [x[1] for x in total_items if x[0] == "video"]
            details: dict[str, dict] = {}
            for i in range(0, len(video_ids), 50):
                details.update(self._yt_videos(video_ids[i : i + 50]))

            # 4) Apply filters (min views, duration) and build UI rows
            rows = []
            for kind, obj_id, title, channel_title, publishedAt, thumb in total_items:
                url = ""
                views_disp = likes_disp = comments_disp = duration_disp = ""
                pub_date = publishedAt[:10] if publishedAt else ""

                if kind == "video":
                    url = f"https://youtu.be/{obj_id}"
                    meta = details.get(obj_id, {})
                    views = meta.get("viewCount", 0)
                    dur_s = meta.get("durationSec", 0)

                    # apply UI filters
                    if opts.min_views_value and views < opts.min_views_value:
                        continue
                    if not duration_ok(opts.duration_value, dur_s):
                        continue

                    # display fields
                    views_disp = f"{views:,}"
                    likes_disp = f"{meta.get('likeCount', 0):,}"
                    comments_disp = f"{meta.get('commentCount', 0):,}"
                    duration_disp = seconds_to_hms(dur_s)
                    # prefer enriched titles/channel names if present
                    title = meta.get("title") or title
                    channel_title = meta.get("channelTitle") or channel_title

                elif kind == "playlist":
                    url = f"https://www.youtube.com/playlist?list={obj_id}"

                elif kind == "channel":
                    url = f"https://www.youtube.com/channel/{obj_id}"

                rows.append(
                    (title, channel_title, kind, views_disp, likes_disp, comments_disp, duration_disp, pub_date, url, thumb)
                )

            # 5) hand rows back to the UI thread
            self.master.after(0, lambda: self._apply_search_results(rows, opts, start_ts))

        except requests.HTTPError as e:
            err = str(e)
            self.master.after(0, lambda err=err: self._search_error(err))
        except Exception as e:
            err = str(e)
            self.master.after(0, lambda err=err: self._search_error(err))

    # Inserts rows into the results table and updates the status bar
    def _apply_search_results(self, rows, opts, start_ts):
        # Insert rows
        for (title, channel_title, kind, views, likes, comments, duration, pub, url, thumb) in rows:
            self.tree.insert(
                "", tk.END,
                values=(title, channel_title, kind, views, likes, comments, duration, pub, url),
                tags=(thumb,)
            )

        # Sort by views (desc) if we have any rows
        if rows:
            self._sort_by('views', True)

        # Compute elapsed
        elapsed = time.time() - start_ts

        # Status message: special text for empty vs normal summary
        if not rows:
            status_text = "No results matched your filters. Try lowering min views or changing duration/date."
        else:
            status_text = (
                f"Query='{opts.query}' | Min views={opts.min_views_label} | Duration={opts.duration_label} | "
                f"After={opts.published_after or '—'} | Before={opts.published_before or '—'} | "
                f"Pages={opts.max_pages_per_type} | Rows={len(rows)} | Elapsed: {elapsed:.2f}s"
            )
        self.status.configure(text=status_text)

        # Stop spinner + re-enable controls
        self.progress.stop()
        self._set_controls_enabled(True)

    # Handles all search errors
    def _search_error(self, msg: str):
        # Try to map common API limit reasons to friendlier text
        friendly = None
        low = (msg or "").lower()
        if "quotaexceeded" in low or "dailylimitexceeded" in low:
            friendly = (
                "YouTube Data API daily quota has been exhausted. "
                "Wait for the daily reset or reduce pages/types, and ensure you’re using your own API key."
            )
        elif "ratelimitexceeded" in low or "userRateLimitExceeded".lower() in low:
            friendly = (
                "You’re sending requests too quickly for the current quota. "
                "Lower the Pages setting, disable Playlists/Channels, or try again shortly."
            )
        elif "forbidden" in low and "quota" in low:
            friendly = (
                "Access forbidden due to quota restrictions. Verify your API key is enabled for YouTube Data API v3 "
                "and that the project has available quota."
            )

        self.progress.stop()
        self._set_controls_enabled(True)
        self.status.configure(text="Search failed")
        messagebox.showerror("Error", friendly or msg)

    # Utility to enable/disable main search controls while a background job runs
    def _set_controls_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for w in (self.btn_search,):
            w.configure(state=state)
    
    # ─────────────────────────────
    # ROW SELECTION / PREVIEW PANEL
    # ─────────────────────────────
    
    # When user selects a row in the table - show detailed info on right panel
    def _on_select_row(self, event=None):
        sel = self._current_values()
        if not sel: return
        title, channel, kind, views, likes, comments, duration, pub, url = sel
        
        # Fill text box with formatted details for the selected item
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0",
            f"Title: {title}\n"
            f"Channel: {channel}\n"
            f"Type: {kind}\n"
            f"Views: {views}\n"
            f"Likes: {likes}\n"
            f"Comments: {comments}\n"
            f"Duration: {duration}\n"
            f"Published: {pub}\n"
            f"URL: {url}"
        )
        self.detail_text.configure(state="disabled")

        # Load thumbnail for the selected video (if available)
        item = self.tree.focus()
        tags = self.tree.item(item, 'tags') if item else []
        thumb_url = tags[0] if tags else None
        self._load_thumbnail(thumb_url)

    # Downloads and displays thumbnail image in the preview panel
    def _load_thumbnail(self, url: str | None):
        try:
            if not url or not url.startswith("http"):
                self.thumb_label.configure(image='', text="No thumbnail"); return

            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            im = Image.open(io.BytesIO(data))
            im.thumbnail((360, 220))
            self._thumb_img = ImageTk.PhotoImage(im)
            self.thumb_label.configure(image=self._thumb_img, text='')
        except Exception:
            self.thumb_label.configure(image='', text="No thumbnail")

    # ─────────────────────────────
    # CONTEXT MENU / RIGHT-CLICK
    # ─────────────────────────────
    
    # When user right-clicks a row, open context menu (Copy URL / Open in Browser)
    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    # Retrieve tuple of values for the currently selected table row
    def _current_values(self):
        sel = self.tree.selection()
        if not sel: return None
        return self.tree.item(sel[0], 'values')
        
    # ─────────────────────────────
    # ACTIONS
    # ─────────────────────────────
    
    # Opens the selected video, playlist, or channel in the default web browser
    def _on_open_current(self, event=None):
        sel = self._current_values()
        if not sel: return
        url = sel[8]
        if url: webbrowser.open(url)

    # Copies the selected item’s URL to clipboard
    def _on_copy_url(self, event=None):
        sel = self._current_values()
        if not sel: return
        url = sel[8]
        self.clipboard_clear(); self.clipboard_append(url)
        self.status.configure(text="Copied URL to clipboard")
        
    # Reset all inputs and clear the results table/preview
    def on_clear(self) -> None:
        # Reset query and filters to defaults
        self.entry_query.delete(0, tk.END)
        self.combo_views.current(0)
        self.combo_duration.current(0)
        self.entry_after.delete(0, tk.END)
        self.entry_before.delete(0, tk.END)
        
        # Default toggles: Videos & Playlists ON, Channels OFF
        self.var_inc_videos.set(True)
        self.var_inc_playlists.set(True)
        self.var_inc_channels.set(False)
        
        # Remove all rows from the results table
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        # Reset preview panel
        self.thumb_label.configure(image='', text="No thumbnail")
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", "Cleared. Ready.")
        self.detail_text.configure(state="disabled")

        # Put focus back to query field for quick re-entry
        self.entry_query.focus_set()

    # Export current table rows to a CSV file
    def on_export_csv(self) -> None:
        # Snapshot rows from the Treeview
        rows = [self.tree.item(i, "values") for i in self.tree.get_children()]
        if not rows:
            messagebox.showinfo("Export CSV", "No rows to export. Run a search first."); return
        
        # Ask user for destination path
        path = filedialog.asksaveasfilename(
            title="Export results to CSV",
            defaultextension=".csv",
            initialfile="ytscout_results.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        
        # Column headers must match the values order above
        headers = ("Title", "Channel", "Type", "Views", "Likes", "Comments", "Duration", "Published", "URL")
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f); writer.writerow(headers); writer.writerows(rows)
            self.status.configure(text=f"Exported {len(rows)} row(s) → {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export failed", f"Could not write CSV: {e}")
            
    # Sort the Treeview by the given column
    def _sort_by(self, col: str, descending: bool):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

        # Convert display strings to comparable keys per column type
        def to_key(val: str):
            # Numeric columns stored as strings with commas - normalize to int
            if col in ('views', 'likes', 'comments'):
                try: return int((val or "0").replace(',', ''))
                except: return 0
            # Date column stored as 'YYYY-MM-DD' - convert to datetime for correct ordering
            if col == 'published':
                d = parse_iso_date(val); return d or datetime.min
            # Duration column stored as "mm:ss" or "hh:mm:ss" - convert to total seconds
            if col == 'duration':
                parts = [int(p) for p in val.split(':')] if val else [0,0]
                if len(parts) == 2: return parts[0]*60 + parts[1]
                if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
                return 0
            return val.lower() if isinstance(val, str) else val

        # Sort the data using our key function and order
        data.sort(key=lambda t: to_key(t[0]), reverse=descending)
        
        # Reinsert rows in sorted order
        for idx, item in enumerate(data):
            self.tree.move(item[1], '', idx)
            
        # Toggle sort direction next time the header is clicked
        self.tree.heading(col, command=lambda c=col: self._sort_by(c, not descending))

    # Center the window on the current screen after initial layout
    def _center_window(self):
        self.master.update_idletasks()
        w = self.master.winfo_width(); h = self.master.winfo_height()
        sw = self.master.winfo_screenwidth(); sh = self.master.winfo_screenheight()
        x = (sw // 2) - (w // 2); y = (sh // 2) - (h // 2)
        self.master.geometry(f"{w}x{h}+{x}+{y}")
        
# ─────────────────────────────
# MAIN FUNCTIONS
# ─────────────────────────────

def main():
    root = tk.Tk()
    app = YouTubeScoutApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()