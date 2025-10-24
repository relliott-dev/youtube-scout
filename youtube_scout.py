from __future__ import annotations

import csv
import io
import os
import time
import webbrowser
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import requests
from tkcalendar import DateEntry

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

# ─────────────────────────────
# CONFIGURATION SETUP
# ─────────────────────────────

API_KEY_DEFAULT = "AIzaSyChrz-xgGS26Z7X6oZFFZ4iTFM6rtimEIc"

VIEW_THRESHOLDS: List[Tuple[str, int]] = [
("Any", 0),
("10K+", 10_000),
("50K+", 50_000),
("100K+", 100_000),
("250K+", 250_000),
("1M+", 1_000_000),
]

DURATIONS: List[Tuple[str, str]] = [
("Any", "any"),
("< 4 min (Short)", "short"),
("4–20 min (Medium)", "medium"),
("> 20 min (Long)", "long"),
("≥ 60 min", "over1h"),
("≥ 180 min", "over3h"),
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

# ─────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────

def parse_iso_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None

def to_rfc3339_day_start(d: str) -> str:
    return f"{d}T00:00:00Z"

def to_rfc3339_day_end(d: str) -> str:
    return f"{d}T23:59:59Z"

def iso8601_duration_to_seconds(iso: str) -> int:
    total = 0
    num = ""
    iso = iso.replace("P", "")
    t_part = False
    for ch in iso:
        if ch == "T":
            t_part = True
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

def seconds_to_hms(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

def duration_ok(filter_key: str, seconds: int) -> bool:
    if filter_key == "any":
        return True
    if filter_key == "short":
        return seconds < 4 * 60
    if filter_key == "medium":
        return 4*60 <= seconds <= 20*60
    if filter_key == "long":
        return seconds > 20*60
    if filter_key == "over1h":
        return seconds >= 60*60
    if filter_key == "over3h":
        return seconds >= 3*60*60
    return True

# ─────────────────────────────
# MAIN FUNCTIONS
# ─────────────────────────────

class YouTubeScoutApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=12)
        self.master.title("YouTube Scout")
        self.master.geometry("1200x760")
        self.master.minsize(1000, 640)
        self.master.configure(bg="#f6f7fb")
        self._apply_style()

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self._build_controls()
        self._build_results_table()
        self._build_preview()
        self._build_statusbar()

        self._make_context_menu()
        self._bind_shortcuts()

        self.pack(fill=tk.BOTH, expand=True)
        self._center_window()

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

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))
        for i in range(12): controls.columnconfigure(i, weight=1)

        ttk.Label(controls, text="Search criteria", style="Header.TLabel").grid(
            row=0, column=0, columnspan=12, sticky="w", pady=(0, 6)
        )

        ttk.Label(controls, text="Query:").grid(row=1, column=0, sticky="w")
        self.entry_query = ttk.Entry(controls)
        self.entry_query.grid(row=1, column=1, columnspan=11, sticky="ew", padx=(6, 0))
        self.entry_query.insert(0, "e.g., python tutorial, guitar pedal review, fitness tips…")
        self.entry_query.bind("<FocusIn>", self._placeholder_clear)

        # Type toggles
        types_frame = ttk.Frame(controls)
        types_frame.grid(row=2, column=0, columnspan=12, sticky="w", pady=(8, 0))
        self.var_inc_videos = tk.BooleanVar(value=True)
        self.var_inc_playlists = tk.BooleanVar(value=True)
        self.var_inc_channels = tk.BooleanVar(value=False)
        ttk.Checkbutton(types_frame, text="Videos", variable=self.var_inc_videos).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(types_frame, text="Playlists", variable=self.var_inc_playlists).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(types_frame, text="Channels", variable=self.var_inc_channels).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(controls, text="Min views:").grid(row=3, column=0, sticky="e", pady=(8, 0))
        self.combo_views = ttk.Combobox(controls, state="readonly", values=[label for label, _ in VIEW_THRESHOLDS])
        self.combo_views.current(0)
        self.combo_views.grid(row=3, column=1, sticky="w", padx=(6, 12), pady=(8, 0))

        ttk.Label(controls, text="Duration:").grid(row=3, column=2, sticky="e", pady=(8, 0))
        self.combo_duration = ttk.Combobox(controls, state="readonly", values=[label for label, _ in DURATIONS])
        self.combo_duration.current(0)
        self.combo_duration.grid(row=3, column=3, sticky="w", padx=(6, 12), pady=(8, 0))

        # Published After/Before with DateEntry
        ttk.Label(controls, text="Published After:").grid(row=3, column=4, sticky="e", pady=(8, 0))
        self.entry_after = DateEntry(controls, date_pattern="yyyy-mm-dd", width=12)
        self.entry_after.delete(0, tk.END)  # start empty

        self.entry_after.grid(row=3, column=5, sticky="w", padx=(6, 12), pady=(8, 0))

        ttk.Label(controls, text="Published Before:").grid(row=3, column=6, sticky="e", pady=(8, 0))
        self.entry_before = DateEntry(controls, date_pattern="yyyy-mm-dd", width=12)
        self.entry_before.delete(0, tk.END)

        self.entry_before.grid(row=3, column=7, sticky="w", padx=(6, 12), pady=(8, 0))

        # Buttons + count + progress
        btns = ttk.Frame(controls)
        btns.grid(row=4, column=0, columnspan=12, sticky="ew", pady=(10, 0))
        btns.columnconfigure(0, weight=1)
        left = ttk.Frame(btns); left.grid(row=0, column=0, sticky="w")
        right = ttk.Frame(btns); right.grid(row=0, column=1, sticky="e")

        self.btn_search = ttk.Button(left, text="Search", command=self.on_search)
        self.btn_search.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left, text="Clear", command=self.on_clear).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(left, text="Export CSV", command=self.on_export_csv).pack(side=tk.LEFT, padx=(0, 8))

    def _build_results_table(self) -> None:
        wrapper = ttk.Frame(self)
        wrapper.grid(row=1, column=0, sticky="nsew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)

        cols = ("title", "channel", "kind", "views", "likes", "comments", "duration", "published", "url")
        self.tree = ttk.Treeview(wrapper, columns=cols, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        for cid, label in zip(
            cols,
            ["Title", "Channel", "Type", "Views", "Likes", "Comments", "Duration", "Published", "URL / ID"]
        ):
            self.tree.heading(cid, text=label, command=lambda c=cid: self._sort_by(c, False))

        self.tree.column("title", anchor="w", width=420)
        self.tree.column("channel", anchor="w", width=220)
        self.tree.column("kind", anchor="center", width=90)
        self.tree.column("views", anchor="e", width=110)
        self.tree.column("likes", anchor="e", width=100)
        self.tree.column("comments", anchor="e", width=110)
        self.tree.column("duration", anchor="center", width=110)
        self.tree.column("published", anchor="center", width=120)
        self.tree.column("url", anchor="w", width=320)

        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)
        self.tree.bind("<Double-1>", self._on_open_current)
        self.tree.bind("<Button-3>", self._on_right_click)

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

    def _build_statusbar(self) -> None:
        self.status = ttk.Label(self, text="Ready", style="Status.TLabel", relief=tk.SOLID, padding=(8, 4))
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _make_context_menu(self):
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Open in browser", command=self._on_open_current)
        self.menu.add_command(label="Copy URL", command=self._on_copy_url)

    def _bind_shortcuts(self):
        self.master.bind("<Return>", lambda e: self.on_search())
        self.master.bind("<Control-l>", lambda e: (self.entry_query.focus_set(), self.entry_query.select_range(0, tk.END)))
        self.master.bind("<Control-e>", lambda e: self.on_export_csv())
        self.master.bind("<Control-c>", lambda e: self._on_copy_url())
        self.master.bind("<Control-o>", lambda e: self._on_open_current())

    def _placeholder_clear(self, event: tk.Event) -> None:
        if self.entry_query.get().startswith("e.g., "):
            self.entry_query.delete(0, tk.END)

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
        if after and not parse_iso_date(after): raise ValueError("'Published After' must be YYYY-MM-DD")
        if before and not parse_iso_date(before): raise ValueError("'Published Before' must be YYYY-MM-DD")

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
        )

    # ----------------- YouTube API -----------------
    def _yt_search(self, q: str, part_type: str, published_after: str | None, published_before: str | None, page_token: str | None = None):
        params = {
            "part": "snippet",
            "q": q,
            "type": part_type,
            "maxResults": 50,
            "key": API_KEY,
            # Sort by most viewed among matches:
            "order": "viewCount",
            # SafeSearch could be "none", "moderate", "strict" (optional)
            # "safeSearch": "moderate",
        }
        # Optional server-side duration filter (YouTube only supports short/medium/long)
        # If you later pass the chosen duration into this function, you can map it here.

        if published_after:
            params["publishedAfter"] = to_rfc3339_day_start(published_after)
        if published_before:
            params["publishedBefore"] = to_rfc3339_day_end(published_before)
        if page_token:
            params["pageToken"] = page_token

        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _yt_most_popular(self, region_code: str = "US", max_pages: int = 2):
        ids = []
        page_token = None
        pages = 0
        while True:
            params = {
                "part": "snippet",
                "chart": "mostPopular",
                "regionCode": region_code,
                "maxResults": 50,
                "key": API_KEY,
            }
            if page_token:
                params["pageToken"] = page_token
            r = requests.get("https://www.googleapis.com/youtube/v3/videos", params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            for it in data.get("items", []):
                ids.append(it["id"])
            page_token = data.get("nextPageToken")
            pages += 1
            if not page_token or pages >= max_pages:
                break
        return ids


    def _yt_videos(self, ids: list[str]):
        if not ids: return {}
        params = {
            "part": "contentDetails,statistics,snippet",
            "id": ",".join(ids),
            "key": API_KEY,
            "maxResults": 50
        }
        r = requests.get("https://www.googleapis.com/youtube/v3/videos", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        by_id = {}
        for it in data.get("items", []):
            vid = it["id"]
            stats = it.get("statistics", {}) or {}
            details = it.get("contentDetails", {}) or {}
            snip = it.get("snippet", {}) or {}
            by_id[vid] = {
                "viewCount": int(stats.get("viewCount", 0)) if stats.get("viewCount") else 0,
                "likeCount": int(stats.get("likeCount", 0)) if stats.get("likeCount") else 0,
                "commentCount": int(stats.get("commentCount", 0)) if stats.get("commentCount") else 0,
                "durationSec": iso8601_duration_to_seconds(details.get("duration", "PT0S")),
                "publishedAt": snip.get("publishedAt", ""),
                "thumb": (snip.get("thumbnails", {}).get("medium") or snip.get("thumbnails", {}).get("default") or {}).get("url", ""),
                "title": snip.get("title", ""),
                "channelTitle": snip.get("channelTitle", ""),
            }
        return by_id


    def on_search(self) -> None:
        if not API_KEY:
            messagebox.showerror("Missing API key", "Set environment variable YT_API_KEY (or paste key into the script).")
            return

        try:
            opts = self._collect_options()
        except ValueError as e:
            messagebox.showwarning("Missing/invalid input.", str(e))
            self.status.configure(text=str(e)); self.entry_query.focus_set()
            return

        self.progress.start(8); self.status.configure(text="Searching…"); self.update_idletasks()
        for row in self.tree.get_children(): self.tree.delete(row)

        # Query per type, merge results
        want_types = []
        if opts.include_videos: want_types.append("video")
        if opts.include_playlists: want_types.append("playlist")
        if opts.include_channels: want_types.append("channel")
        total_items = []

        try:
            for t in want_types:
                page_token = None
                fetched = 0
                while True:
                    data = self._yt_search(opts.query, t, opts.published_after, opts.published_before, page_token)
                    items = data.get("items", [])
                    for it in items:
                        id_block = it.get("id", {})
                        snip = it.get("snippet", {})
                        thumb = (snip.get("thumbnails", {}).get("medium") or snip.get("thumbnails", {}).get("default") or {}).get("url", "")
                        ch_title = snip.get("channelTitle", "")

                        if t == "video":
                            vid = id_block.get("videoId")
                            if vid:
                                total_items.append(("video", vid, snip.get("title",""), ch_title, snip.get("publishedAt",""), thumb))
                        elif t == "playlist":
                            pid = id_block.get("playlistId")
                            if pid:
                                total_items.append(("playlist", pid, snip.get("title",""), ch_title, snip.get("publishedAt",""), thumb))
                        elif t == "channel":
                            cid = id_block.get("channelId")
                            if cid:
                                total_items.append(("channel", cid, snip.get("title",""), snip.get("title",""), snip.get("publishedAt",""), thumb))

                    fetched += len(items)
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

            # ---------- Enrich videos with stats/duration ----------
            video_ids = [x[1] for x in total_items if x[0] == "video" and x[1]]
            details = {}
            for i in range(0, len(video_ids), 50):
                details.update(self._yt_videos(video_ids[i:i+50]))

            # ---------- Apply filters & insert rows ----------
            inserted = 0
            for kind, obj_id, title, channel_title, publishedAt, thumb in total_items:
                url = ""
                views_disp = ""
                likes_disp = ""
                comments_disp = ""
                duration_disp = ""
                pub_date = publishedAt[:10] if publishedAt else ""

                if kind == "video":
                    url = f"https://youtu.be/{obj_id}"
                    meta = details.get(obj_id, {})
                    views = meta.get("viewCount", 0)
                    dur_s = meta.get("durationSec", 0)
                    if opts.min_views_value and views < opts.min_views_value:
                        continue
                    if not duration_ok(opts.duration_value, dur_s):
                        continue

                    # Display fields
                    views_disp = f"{views:,}"
                    likes_disp = f"{meta.get('likeCount', 0):,}"
                    comments_disp = f"{meta.get('commentCount', 0):,}"
                    duration_disp = seconds_to_hms(dur_s)
                    title = meta.get("title") or title
                    channel_title = meta.get("channelTitle") or channel_title
                    if not thumb and meta.get("thumb"):
                        thumb = meta["thumb"]

                elif kind == "playlist":
                    url = f"https://www.youtube.com/playlist?list={obj_id}"

                elif kind == "channel":
                    url = f"https://www.youtube.com/channel/{obj_id}"

                self.tree.insert(
                    "", tk.END,
                    values=(title, channel_title, kind, views_disp, likes_disp, comments_disp, duration_disp, pub_date, url),
                    tags=(thumb,)
                )
                inserted += 1


            self._sort_by('views', True)
            self.count_var.set(f"Count: {inserted}")
            self.status.configure(text=(
                f"Query='{opts.query}' | Min views={opts.min_views_label} | Duration={opts.duration_label} | "
                f"After={opts.published_after or '—'} | Before={opts.published_before or '—'} | Showing {inserted}"
            ))

        except requests.HTTPError as e:
            messagebox.showerror("YouTube API error", f"{e}\n\nResponse: {getattr(e, 'response', None) and e.response.text}")
            self.status.configure(text="API error")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status.configure(text="Search failed")
        finally:
            self.progress.stop()

    # -------- row interactions / preview / sorting / export ----------
    def _on_select_row(self, event=None):
        sel = self._current_values()
        if not sel: return
        title, channel, kind, views, likes, comments, duration, pub, url = sel
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

        # thumb
        item = self.tree.focus()
        tags = self.tree.item(item, 'tags') if item else []
        thumb_url = tags[0] if tags else None
        self._load_thumbnail(thumb_url)

    def _load_thumbnail(self, url: str | None):
        try:
            if not url or not url.startswith("http"):
                self.thumb_label.configure(image='', text="No thumbnail"); return
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = resp.read()
            if PIL_OK:
                im = Image.open(io.BytesIO(data))
                im.thumbnail((360, 220))
                self._thumb_img = ImageTk.PhotoImage(im)
                self.thumb_label.configure(image=self._thumb_img, text='')
            else:
                self.thumb_label.configure(image='', text="(Thumb loaded, but Pillow not installed)")
        except Exception:
            self.thumb_label.configure(image='', text="No thumbnail")

    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.menu.tk_popup(event.x_root, event.y_root)

    def _current_values(self):
        sel = self.tree.selection()
        if not sel: return None
        return self.tree.item(sel[0], 'values')

    def _on_open_current(self, event=None):
        sel = self._current_values()
        if not sel: return
        url = sel[8]
        if url: webbrowser.open(url)

    def _on_copy_url(self, event=None):
        sel = self._current_values()
        if not sel: return
        url = sel[8]
        self.clipboard_clear(); self.clipboard_append(url)
        self.status.configure(text="Copied URL to clipboard")

    def _sort_by(self, col: str, descending: bool):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

        def to_key(val: str):
            if col in ('views', 'likes', 'comments'):
                try: return int((val or "0").replace(',', ''))
                except: return 0
            if col == 'published':
                d = parse_iso_date(val); return d or datetime.min
            if col == 'duration':
                parts = [int(p) for p in val.split(':')] if val else [0,0]
                if len(parts) == 2: return parts[0]*60 + parts[1]
                if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
                return 0
            return val.lower() if isinstance(val, str) else val

        data.sort(key=lambda t: to_key(t[0]), reverse=descending)
        for idx, item in enumerate(data):
            self.tree.move(item[1], '', idx)
        self.tree.heading(col, command=lambda c=col: self._sort_by(c, not descending))

    def on_clear(self) -> None:
        self.entry_query.delete(0, tk.END)
        self.combo_views.current(0)
        self.combo_duration.current(0)
        self.entry_after.delete(0, tk.END)
        self.entry_before.delete(0, tk.END)
        self.var_inc_videos.set(True)
        self.var_inc_playlists.set(True)
        self.var_inc_channels.set(False)
        for row in self.tree.get_children(): self.tree.delete(row)
        self.thumb_label.configure(image='', text="No thumbnail")
        self.detail_text.configure(state="normal"); self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", "Cleared. Ready."); self.detail_text.configure(state="disabled")
        self.status.configure(text="Cleared. Ready"); self.count_var.set("Count: 0")
        self.entry_query.focus_set()

    def on_export_csv(self) -> None:
        rows = [self.tree.item(i, "values") for i in self.tree.get_children()]
        if not rows:
            messagebox.showinfo("Export CSV", "No rows to export. Run a search first."); return
        path = filedialog.asksaveasfilename(
            title="Export results to CSV",
            defaultextension=".csv",
            initialfile="ytscout_results.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path: return
        headers = ("Title", "Channel", "Type", "Views", "Likes", "Comments", "Duration", "Published", "URL")
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f); writer.writerow(headers); writer.writerows(rows)
            self.status.configure(text=f"Exported {len(rows)} row(s) → {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export failed", f"Could not write CSV: {e}")

    def _center_window(self):
        self.master.update_idletasks()
        w = self.master.winfo_width(); h = self.master.winfo_height()
        sw = self.master.winfo_screenwidth(); sh = self.master.winfo_screenheight()
        x = (sw // 2) - (w // 2); y = (sh // 2) - (h // 2)
        self.master.geometry(f"{w}x{h}+{x}+{y}")

def main():
    root = tk.Tk()
    app = YouTubeScoutApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
