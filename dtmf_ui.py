"""
dtmf_ui.py — DTMF Commander UI
Run this file to launch the application.

Aesthetic: Precision industrial / pro-audio rack unit.
Tight grid, amber+cyan on near-black, crisp monospace, no fluff.

Requires: pip install sounddevice numpy scipy pyserial
"""

import tkinter as tk
from tkinter import messagebox, font as tkfont
import threading
import queue
import sys
import time

from dtmf_engine import (
    load_config, save_config,
    list_audio_devices, list_com_ports, send_to_com,
    RuleMatcher, DTMFListener,
)

# ═══════════════════════════════════════════════════════
#  THEMES  (dark is default, light is the toggle target)
# ═══════════════════════════════════════════════════════

THEMES = {
    "dark": {
        "bg0":        "#080A0C",
        "bg1":        "#0D1117",
        "bg2":        "#12181F",
        "bg3":        "#1A2130",
        "border":     "#1E2D3D",
        "border_hi":  "#2A4060",
        "amber":      "#FFA600",
        "amber_dim":  "#CC8C00",
        "amber_fade": "#FFB30018",
        "cyan":       "#00D0E8",
        "cyan_dim":   "#009DB0",
        "cyan_fade":  "#00D0E818",
        "green":      "#00E676",
        "red":        "#FF3D3D",
        "red_dim":    "#CC2A2A",
        "text0":      "#E8F0FE",
        "text1":      "#8899AA",
        "text2":      "#445566",
        "text3":      "#2A3A4A",
    },
    "light": {
        "bg0":        "#F0F2F5",
        "bg1":        "#FFFFFF",
        "bg2":        "#E8ECF0",
        "bg3":        "#D8DDE5",
        "border":     "#C0CAD4",
        "border_hi":  "#8AABB8",
        "amber":      "#C07800",
        "amber_dim":  "#9A6000",
        "amber_fade": "#C0780018",
        "cyan":       "#006E8A",
        "cyan_dim":   "#005268",
        "cyan_fade":  "#006E8A18",
        "green":      "#007A3D",
        "red":        "#C0222A",
        "red_dim":    "#96181E",
        "text0":      "#0D1117",
        "text1":      "#334455",
        "text2":      "#6677AA",
        "text3":      "#AABBCC",
    },
}

# Active theme — mutated by toggle
C = dict(THEMES["dark"])
_current_theme = ["dark"]

FONT_MONO    = ("Courier New", 10)
FONT_MONO_SM = ("Courier New", 8)
FONT_MONO_LG = ("Courier New", 13, "bold")
FONT_MONO_XL = ("Courier New", 42, "bold")
FONT_LABEL   = ("Courier New", 9)
FONT_HEAD    = ("Courier New", 10, "bold")
FONT_TITLE   = ("Courier New", 14, "bold")


def _apply_theme(name: str):
    """Swap the global C dict in-place so all widget refs see new colors."""
    _current_theme[0] = name
    C.update(THEMES[name])


# ═══════════════════════════════════════════════════════
#  SMALL REUSABLE WIDGETS
# ═══════════════════════════════════════════════════════

def sep(parent, orient="h", **pack_kw):
    if orient == "h":
        f = tk.Frame(parent, bg=C["border"], height=1)
    else:
        f = tk.Frame(parent, bg=C["border"], width=1)
    f.pack(**pack_kw)
    return f


def label(parent, text, style="normal", **kw):
    styles = {
        "normal":  dict(fg=C["text1"], font=FONT_LABEL),
        "head":    dict(fg=C["text0"], font=FONT_HEAD),
        "muted":   dict(fg=C["text2"], font=FONT_LABEL),
        "amber":   dict(fg=C["amber"], font=FONT_HEAD),
        "cyan":    dict(fg=C["cyan"],  font=FONT_HEAD),
        "title":   dict(fg=C["amber"], font=FONT_TITLE),
    }
    cfg = {**styles.get(style, styles["normal"]), **kw}
    return tk.Label(parent, text=text, bg=parent["bg"], **cfg)


class FlatButton(tk.Frame):
    """A button with a solid block style — primary (amber fill) or ghost."""

    def __init__(self, parent, text, command, variant="ghost", width=None, **kw):
        self._variant = variant
        self._cmd = command
        bg, ho, fg = self._resolve(variant)
        self._bg = bg
        self._ho = ho
        self._fg = fg

        super().__init__(parent, bg=self._bg, cursor="hand2",
                          highlightbackground=C["border"], highlightthickness=1)
        w_kw = {"width": width} if width else {}
        self._lbl = tk.Label(self, text=text, bg=self._bg, fg=self._fg,
                              font=FONT_HEAD, padx=14, pady=6, **w_kw)
        self._lbl.pack(fill="both")

        for w in (self, self._lbl):
            w.bind("<Enter>",    self._enter)
            w.bind("<Leave>",    self._leave)
            w.bind("<Button-1>", self._click)

    @staticmethod
    def _resolve(variant):
        bg_map = {
            "primary": C["amber"],
            "danger":  C["red"],
            "ghost":   C["bg3"],
            "ghost2":  C["bg2"],
        }
        fg_map = {
            "primary": C["bg0"],
            "danger":  C["text0"],
            "ghost":   C["text1"],
            "ghost2":  C["text1"],
        }
        ho_map = {
            "primary": C["amber_dim"],
            "danger":  C["red_dim"],
            "ghost":   C["border_hi"],
            "ghost2":  C["bg3"],
        }
        return bg_map.get(variant, C["bg3"]), ho_map.get(variant, C["border_hi"]), fg_map.get(variant, C["text1"])

    def _enter(self, _): self._set_color(self._ho)
    def _leave(self, _): self._set_color(self._bg)
    def _click(self, _): self._cmd()

    def _set_color(self, c):
        self.configure(bg=c)
        self._lbl.configure(bg=c)

    def set_text(self, t):     self._lbl.configure(text=t)
    def set_variant(self, v):
        self._variant = v
        self._bg, self._ho, self._fg = self._resolve(v)
        self._set_color(self._bg)
        self._lbl.configure(fg=self._fg)

    def refresh_theme(self):
        self._bg, self._ho, self._fg = self._resolve(self._variant)
        self.configure(bg=self._bg, highlightbackground=C["border"])
        self._lbl.configure(bg=self._bg, fg=self._fg)


class FlatEntry(tk.Entry):
    def __init__(self, parent, textvariable=None, **kw):
        super().__init__(
            parent,
            bg=C["bg3"], fg=C["text0"], insertbackground=C["amber"],
            relief="flat", bd=0, font=FONT_MONO,
            highlightbackground=C["border"],
            highlightcolor=C["amber"],
            highlightthickness=1,
            textvariable=textvariable,
            **kw,
        )


class FlatDropdown(tk.Frame):
    """Styled OptionMenu wrapper."""

    def __init__(self, parent, variable, values, **kw):
        super().__init__(parent, bg=C["bg3"],
                          highlightbackground=C["border"], highlightthickness=1)
        self._var    = variable
        self._values = values
        self._menu_btn = tk.Menubutton(
            self, textvariable=variable, bg=C["bg3"], fg=C["text0"],
            activebackground=C["border_hi"], activeforeground=C["text0"],
            font=FONT_MONO, relief="flat", bd=0, padx=10, pady=6,
            indicatoron=False, anchor="w",
        )
        self._menu = tk.Menu(self._menu_btn, tearoff=0,
                              bg=C["bg2"], fg=C["text0"],
                              activebackground=C["border_hi"],
                              activeforeground=C["amber"],
                              font=FONT_MONO, bd=0, relief="flat")
        self._menu_btn.configure(menu=self._menu)
        self._rebuild(values)
        # Arrow indicator
        self._arrow = tk.Label(self, text="▾", bg=C["bg3"], fg=C["amber"],
                                font=FONT_LABEL, padx=6)
        self._arrow.pack(side="right")
        self._menu_btn.pack(side="left", fill="both", expand=True)

    def _rebuild(self, values):
        self._menu.delete(0, "end")
        for v in values:
            self._menu.add_command(label=v, command=lambda val=v: self._var.set(val))

    def update_values(self, values):
        self._values = values
        self._rebuild(values)
        if values:
            self._var.set(values[0])
        else:
            self._var.set("")

    def refresh_theme(self):
        self.configure(bg=C["bg3"], highlightbackground=C["border"])
        self._menu_btn.configure(bg=C["bg3"], fg=C["text0"],
                                  activebackground=C["border_hi"])
        self._menu.configure(bg=C["bg2"], fg=C["text0"],
                              activebackground=C["border_hi"],
                              activeforeground=C["amber"])
        self._arrow.configure(bg=C["bg3"], fg=C["amber"])


class FlatScrollbar(tk.Canvas):
    """
    Fully themed scrollbar drawn on a Canvas — no OS chrome, matches app palette.
    Drop-in for tk.Scrollbar: supports yscrollcommand= and command= protocols.
    """
    _WIDTH = 5      # track width in px
    _MIN_THUMB = 24 # minimum thumb length in px
    _PAD = 2        # padding between thumb and track edge

    def __init__(self, parent, command=None, orient="vertical", **kw):
        # Inherit parent bg so the track blends in seamlessly
        parent_bg = C["bg1"]
        try:
            parent_bg = parent["bg"]
        except Exception:
            pass
        kw.setdefault("bg", parent_bg)
        kw.setdefault("highlightthickness", 0)
        bg = kw.pop("bg")
        kw.pop("highlightthickness", None)
        if orient == "vertical":
            super().__init__(parent, width=self._WIDTH + self._PAD * 2,
                             bg=bg, highlightthickness=0, **kw)
        else:
            super().__init__(parent, height=self._WIDTH + self._PAD * 2,
                             bg=bg, highlightthickness=0, **kw)

        self._bg       = bg
        self._command  = command
        self._orient   = orient
        self._first    = 0.0
        self._last     = 1.0
        self._drag_start_pos  = None
        self._drag_start_frac = None

        # Track is same as canvas bg (invisible); thumb is a dim border color
        self._track = self.create_rectangle(0, 0, 0, 0,
                                            fill=bg, outline="", width=0)
        self._thumb = self.create_rectangle(0, 0, 0, 0,
                                            fill=C["border_hi"], outline="", width=0)

        self.bind("<Configure>",       self._redraw)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>",           self._on_enter)
        self.bind("<Leave>",           self._on_leave)
        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<Button-4>",        self._on_wheel)
        self.bind("<Button-5>",        self._on_wheel)

    # ── Scrollable widget calls this (the yscrollcommand= target) ─────
    def set(self, first, last):
        self._first = float(first)
        self._last  = float(last)
        self._redraw()
        # Hide when content fits
        if self._first <= 0.0 and self._last >= 1.0:
            self.itemconfigure(self._thumb, state="hidden")
        else:
            self.itemconfigure(self._thumb, state="normal")

    def _redraw(self, *_):
        w = self.winfo_width()
        h = self.winfo_height()
        p = self._PAD
        sw = self._WIDTH

        if self._orient == "vertical":
            tx0, ty0, tx1, ty1 = p, 0, p + sw, h
            track_len = h
            thumb_start = int(self._first * track_len)
            thumb_end   = max(thumb_start + self._MIN_THUMB,
                              int(self._last  * track_len))
            thumb_end   = min(thumb_end, track_len)
            self.coords(self._track, tx0, ty0, tx1, ty1)
            self.coords(self._thumb, tx0, thumb_start, tx1, thumb_end)
        else:
            tx0, ty0, tx1, ty1 = 0, p, w, p + sw
            track_len = w
            thumb_start = int(self._first * track_len)
            thumb_end   = max(thumb_start + self._MIN_THUMB,
                              int(self._last  * track_len))
            thumb_end   = min(thumb_end, track_len)
            self.coords(self._track, tx0, ty0, tx1, ty1)
            self.coords(self._thumb, thumb_start, ty0, thumb_end, ty1)

    def _on_enter(self, _):
        self.itemconfigure(self._thumb, fill=C["amber_dim"])
        self.itemconfigure(self._track, fill=C["bg3"])

    def _on_leave(self, _):
        self.itemconfigure(self._thumb, fill=C["border_hi"])
        self.itemconfigure(self._track, fill=self._bg)

    def _pos(self, e):
        return e.y if self._orient == "vertical" else e.x

    def _track_len(self):
        return self.winfo_height() if self._orient == "vertical" else self.winfo_width()

    def _on_press(self, e):
        pos = self._pos(e)
        tl  = self._track_len()
        thumb_s = int(self._first * tl)
        thumb_e = max(thumb_s + self._MIN_THUMB, int(self._last * tl))
        if thumb_s <= pos <= thumb_e:
            # clicked on thumb → start drag
            self._drag_start_pos  = pos
            self._drag_start_frac = self._first
        else:
            # clicked on track → page scroll
            if self._command:
                if pos < thumb_s:
                    self._command("scroll", -1, "pages")
                else:
                    self._command("scroll",  1, "pages")

    def _on_drag(self, e):
        if self._drag_start_pos is None:
            return
        delta = self._pos(e) - self._drag_start_pos
        tl    = self._track_len()
        frac  = self._drag_start_frac + delta / tl
        frac  = max(0.0, min(1.0, frac))
        if self._command:
            self._command("moveto", frac)

    def _on_release(self, _):
        self._drag_start_pos  = None
        self._drag_start_frac = None

    def _on_wheel(self, e):
        if not self._command:
            return
        if e.num == 4 or e.delta > 0:
            self._command("scroll", -3, "units")
        else:
            self._command("scroll",  3, "units")

    def configure(self, **kw):
        # Eat bg/troughcolor/relief/width so callers don't need to change
        kw.pop("troughcolor", None)
        kw.pop("relief", None)
        super().configure(**kw)

    config = configure


class LEDIndicator(tk.Canvas):
    """Small circular LED — solid color circle."""

    def __init__(self, parent, size=10, **kw):
        super().__init__(parent, width=size, height=size,
                          bg=parent["bg"], highlightthickness=0, **kw)
        pad = 1
        self._oval = self.create_oval(pad, pad, size-pad, size-pad, fill=C["text3"], outline="")
        self._size = size

    def set_color(self, color):
        self.itemconfigure(self._oval, fill=color)


# ═══════════════════════════════════════════════════════
#  CUSTOM DIALOG BASE  (frameless, close-only titlebar)
# ═══════════════════════════════════════════════════════

class CustomDialog(tk.Toplevel):
    """
    Base class for all sub-windows.
    • Frameless (overrideredirect=True) so it matches the app chrome.
    • Has a custom titlebar with *only* a close button (red dot, same style
      as the main window's close button).
    • Draggable via the titlebar.
    • Stays on top of the main window (grab_set) but is not system-modal.
    """

    def __init__(self, parent, title_text, width, height):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=C["bg0"],
                       highlightbackground=C["border"], highlightthickness=1)
        self.grab_set()
        self.resizable(False, False)

        self._drag_x = 0
        self._drag_y = 0

        # ── Custom titlebar ───────────────────────────────────
        tbar = tk.Frame(self, bg=C["bg0"], height=34)
        tbar.pack(fill="x", side="top")
        tbar.pack_propagate(False)

        tbar.bind("<ButtonPress-1>", self._drag_start)
        tbar.bind("<B1-Motion>",     self._drag_move)

        # Close-only control cluster
        ctrl = tk.Frame(tbar, bg=C["bg0"])
        ctrl.pack(side="left", padx=(10, 0))
        ctrl.bind("<ButtonPress-1>", self._drag_start)
        ctrl.bind("<B1-Motion>",     self._drag_move)

        self._close_btn = self._make_close_btn(ctrl)
        self._close_btn.pack(side="left")

        # Centered title
        title_lbl = tk.Label(
            tbar,
            text=title_text,
            font=("Courier New", 10, "bold"),
            bg=C["bg0"], fg=C["amber"],
        )
        title_lbl.place(relx=0.5, rely=0.5, anchor="center")
        title_lbl.bind("<ButtonPress-1>", self._drag_start)
        title_lbl.bind("<B1-Motion>",     self._drag_move)

        # Separator under titlebar
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")

        # ── Centre on parent ──────────────────────────────────
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + (pw - width)  // 2
        y = py + (ph - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ── Smooth anti-aliased close dot ─────────────────────────

    def _make_close_btn(self, parent):
        size  = 14
        color = "#FF5F57"
        img   = tk.PhotoImage(width=size, height=size)

        def parse(h):
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        cr, cg, cb = parse(color)
        br, bg_c, bb = parse(C["bg0"])
        cx = cy = size / 2.0
        r  = size / 2.0 - 0.5
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                hits = sum(
                    1 for sy in range(3) for sx in range(3)
                    if (x + (sx + 0.5) / 3 - cx) ** 2 + (y + (sy + 0.5) / 3 - cy) ** 2 <= r * r
                )
                a = hits / 9.0
                row.append(f"#{int(cr*a+br*(1-a)):02x}{int(cg*a+bg_c*(1-a)):02x}{int(cb*a+bb*(1-a)):02x}")
            rows.append("{" + " ".join(row) + "}")
        img.put(" ".join(rows))

        c = tk.Canvas(parent, width=size, height=size,
                      bg=C["bg0"], highlightthickness=0, cursor="hand2")
        c.create_image(0, 0, anchor="nw", image=img)
        c._img_ref = img
        c.bind("<Button-1>", lambda _: self.destroy())
        return c

    # ── Drag ──────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")


# ═══════════════════════════════════════════════════════
#  RULE EDITOR DIALOG
# ═══════════════════════════════════════════════════════

class RuleEditorDialog(CustomDialog):
    # How often (ms) to re-scan for COM ports while the dialog is open
    _PORT_POLL_MS = 1500

    def __init__(self, parent, on_save, existing_rule=None):
        title = "✦  EDIT RULE" if existing_rule else "✦  NEW RULE"
        super().__init__(parent, title, 800, 700)
        self.on_save = on_save

        self.configure(bg=C["bg1"])

        is_edit = existing_rule is not None
        rule    = existing_rule or {}

        # ── Header bar ─────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["bg0"], height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=C["amber"], width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="EDIT RULE" if is_edit else "NEW RULE",
                  font=FONT_TITLE, bg=C["bg0"], fg=C["amber"],
                  padx=16).pack(side="left", pady=12)

        # ── Form ───────────────────────────────────────────────
        form = tk.Frame(self, bg=C["bg1"])
        form.pack(fill="both", expand=True, padx=24, pady=16)

        self._vars = {}

        # Fields that use a plain FlatEntry (port handled separately below)
        plain_fields = [
            ("label",    "RULE LABEL",               rule.get("label", ""),        False),
            ("password", "DTMF SEQUENCE  (password)", rule.get("password", ""),    False),
            ("command",  "COMMAND STRING",             rule.get("command", ""),     False),
            ("baud",     "BAUD RATE",                 str(rule.get("baud", 9600)), False),
        ]

        # We will insert the COM PORT row between password (row 1) and command (row 2)
        # Layout rows: label=0/1, password=2/3, port=4/5/6, command=7/8 (hint is row 6),
        # baud=9/10 — keep it tidy by building a row map.
        row_map = [
            (0, plain_fields[0]),   # label
            (1, plain_fields[1]),   # password
        ]

        PORT_LABEL_ROW   = 4   # grid row for "COM PORT" label
        PORT_WIDGET_ROW  = 5   # grid row for the dropdown
        PORT_STATUS_ROW  = 6   # grid row for the live-status label

        remaining_plain = [
            (7,  plain_fields[2]),  # command
            (9,  plain_fields[3]),  # baud
        ]

        for grid_label_row, (key, lbl_text, default, secret) in row_map:
            tk.Label(form, text=lbl_text, font=FONT_LABEL, bg=C["bg1"],
                      fg=C["text2"]).grid(row=grid_label_row*2, column=0, sticky="w",
                                           pady=(0, 2))
            var = tk.StringVar(value=default)
            self._vars[key] = var
            kw = {"show": "●"} if secret else {}
            e = FlatEntry(form, textvariable=var, **kw)
            e.grid(row=grid_label_row*2+1, column=0, sticky="ew", ipady=6)

        # ── COM PORT — live-polling dropdown ──────────────────
        tk.Label(form, text="COM PORT", font=FONT_LABEL, bg=C["bg1"],
                  fg=C["text2"]).grid(row=PORT_LABEL_ROW, column=0, sticky="w",
                                       pady=(8, 2))

        self._port_var = tk.StringVar(value=rule.get("port", ""))
        self._vars["port"] = self._port_var

        # Initial port scan
        self._last_ports = self._scan_ports()

        # If saved port is not in detected list, still keep it selectable
        initial_ports = list(self._last_ports)
        saved_port    = rule.get("port", "")
        if saved_port and saved_port not in initial_ports:
            initial_ports.insert(0, saved_port)

        # Build the dropdown (or a plain entry fallback when no ports detected)
        port_row_frame = tk.Frame(form, bg=C["bg1"])
        port_row_frame.grid(row=PORT_WIDGET_ROW, column=0, sticky="ew")
        port_row_frame.columnconfigure(0, weight=1)

        if initial_ports:
            self._port_drop = FlatDropdown(port_row_frame, self._port_var, initial_ports)
            self._port_drop.grid(row=0, column=0, sticky="ew")
            # If saved port present in list, select it; else pick first available
            if saved_port in initial_ports:
                self._port_var.set(saved_port)
            else:
                self._port_var.set(initial_ports[0])
            self._port_entry = None
        else:
            # No ports yet — show an entry so the user can type manually
            self._port_entry = FlatEntry(port_row_frame, textvariable=self._port_var)
            self._port_entry.grid(row=0, column=0, sticky="ew", ipady=6)
            self._port_drop = None
            if saved_port:
                self._port_var.set(saved_port)

        # Refresh button (small, to the right of the dropdown)
        FlatButton(port_row_frame, "⟳", self._refresh_ports_now,
                   variant="ghost2", width=3).grid(row=0, column=1, padx=(6, 0))

        # Live status label (shows count + port names or a "no ports" message)
        self._port_status_var = tk.StringVar()
        self._port_status_lbl = tk.Label(
            form,
            textvariable=self._port_status_var,
            font=FONT_LABEL, bg=C["bg1"], fg=C["text2"],
            anchor="w",
        )
        self._port_status_lbl.grid(row=PORT_STATUS_ROW, column=0, sticky="w", pady=(2, 0))
        self._update_port_status(self._last_ports)

        # Remaining plain fields (command, baud)
        for grid_label_row, (key, lbl_text, default, secret) in remaining_plain:
            tk.Label(form, text=lbl_text, font=FONT_LABEL, bg=C["bg1"],
                      fg=C["text2"]).grid(row=grid_label_row, column=0, sticky="w",
                                           pady=(8, 2))
            var = tk.StringVar(value=default)
            self._vars[key] = var
            kw = {"show": "●"} if secret else {}
            e = FlatEntry(form, textvariable=var, **kw)
            e.grid(row=grid_label_row+1, column=0, sticky="ew", ipady=6)

        form.columnconfigure(0, weight=1)

        # Start live polling
        self._polling = True
        self._poll_ports()

        # ── Footer buttons ─────────────────────────────────────
        sep(self, fill="x")
        footer = tk.Frame(self, bg=C["bg1"])
        footer.pack(fill="x", padx=24, pady=14)

        FlatButton(footer, "CANCEL", self.destroy, variant="ghost").pack(side="right", padx=(6, 0))
        FlatButton(footer, "SAVE RULE", self._save, variant="primary").pack(side="right")

    # ── COM-port live detection helpers ───────────────────────

    @staticmethod
    def _scan_ports():
        """Return a sorted list of available COM / serial port names."""
        ports = list(list_com_ports())
        if not ports and sys.platform.startswith("linux"):
            import glob as _glob
            linux_ports = (
                _glob.glob("/dev/ttyUSB*") +
                _glob.glob("/dev/ttyACM*") +
                _glob.glob("/dev/ttyS[0-9]*")
            )
            ports = sorted(linux_ports)
        return ports

    def _update_port_status(self, ports):
        """Refresh the status label under the COM port widget."""
        if ports:
            if len(ports) == 1:
                self._port_status_var.set(f"● 1 port detected: {ports[0]}")
            else:
                self._port_status_var.set(
                    f"● {len(ports)} ports detected: " + "  ".join(ports)
                )
            self._port_status_lbl.configure(fg=C["text2"])
        else:
            if sys.platform.startswith("linux"):
                self._port_status_var.set(
                    "○ no ports — check /dev/ttyUSB* or run: sudo usermod -aG dialout $USER"
                )
            else:
                self._port_status_var.set("○ no COM ports detected")
            self._port_status_lbl.configure(fg=C["red"])

    def _rebuild_port_widget(self, form_frame, ports):
        """
        Swap between FlatDropdown and FlatEntry depending on whether ports
        are available.  Only rebuilds when the port list actually changes.
        """
        current_val = self._port_var.get()

        if ports:
            # Ensure the currently-typed value stays selectable if not detected
            all_choices = list(ports)
            if current_val and current_val not in all_choices:
                all_choices.insert(0, current_val)

            if self._port_drop is not None:
                # Already a dropdown — just update its values
                self._port_drop.update_values(all_choices)
                # Restore selection: prefer currently selected → first detected port
                if current_val in all_choices:
                    self._port_var.set(current_val)
                else:
                    self._port_var.set(all_choices[0])
            else:
                # Was a plain entry — replace with dropdown
                if self._port_entry:
                    self._port_entry.destroy()
                    self._port_entry = None
                # Find the port_row_frame (column=0, row=PORT_WIDGET_ROW inside form)
                for child in form_frame.grid_slaves(row=5, column=0):
                    port_row_frame = child
                    break
                else:
                    return
                self._port_drop = FlatDropdown(port_row_frame, self._port_var, all_choices)
                self._port_drop.grid(row=0, column=0, sticky="ew")
                if current_val in all_choices:
                    self._port_var.set(current_val)
                else:
                    self._port_var.set(all_choices[0])
        else:
            if self._port_drop is not None:
                # No ports left — replace dropdown with plain entry
                self._port_drop.destroy()
                self._port_drop = None
                for child in form_frame.grid_slaves(row=5, column=0):
                    port_row_frame = child
                    break
                else:
                    return
                self._port_entry = FlatEntry(port_row_frame, textvariable=self._port_var)
                self._port_entry.grid(row=0, column=0, sticky="ew", ipady=6)
                self._port_var.set(current_val)
            # else: already a plain entry, leave as-is

    def _refresh_ports_now(self):
        """Immediate rescan triggered by the ⟳ button."""
        ports = self._scan_ports()
        if ports != self._last_ports:
            self._last_ports = ports
            # Walk up to the form frame
            try:
                form_frame = self._port_status_lbl.master
                self._rebuild_port_widget(form_frame, ports)
            except Exception:
                pass
        self._update_port_status(ports)

    def _poll_ports(self):
        """Called repeatedly via after() while the dialog is open."""
        if not self._polling:
            return
        try:
            ports = self._scan_ports()
            if ports != self._last_ports:
                self._last_ports = ports
                try:
                    form_frame = self._port_status_lbl.master
                    self._rebuild_port_widget(form_frame, ports)
                except Exception:
                    pass
                self._update_port_status(ports)
        except Exception:
            pass
        # Schedule next poll (only if the widget still exists)
        try:
            self._poll_id = self.after(self._PORT_POLL_MS, self._poll_ports)
        except Exception:
            pass

    def destroy(self):
        """Stop polling before closing."""
        self._polling = False
        try:
            self.after_cancel(self._poll_id)
        except Exception:
            pass
        super().destroy()

    def _save(self):
        vals = {k: v.get().strip() for k, v in self._vars.items()}
        if not vals["label"]:
            messagebox.showerror("Missing field", "Label is required.", parent=self); return
        if not vals["password"]:
            messagebox.showerror("Missing field", "DTMF sequence is required.", parent=self); return
        if not vals["port"]:
            messagebox.showerror("Missing field", "COM Port is required.", parent=self); return
        if not vals["command"]:
            messagebox.showerror("Missing field", "Command string is required.", parent=self); return
        try:
            vals["baud"] = int(vals["baud"])
        except ValueError:
            messagebox.showerror("Invalid", "Baud rate must be an integer.", parent=self); return

        self.on_save(vals)
        self.destroy()


# ═══════════════════════════════════════════════════════
#  CONFIRM DELETE DIALOG  (styled, replaces messagebox)
# ═══════════════════════════════════════════════════════

class _ConfirmDeleteDialog(CustomDialog):
    """Styled confirmation dialog that matches the rest of the app chrome."""

    def __init__(self, parent, rule_label: str, on_confirm):
        super().__init__(parent, "✦  CONFIRM DELETE", 420, 210)
        self._on_confirm = on_confirm
        self.configure(bg=C["bg1"])

        # ── Header accent bar ─────────────────────────────────
        hdr = tk.Frame(self, bg=C["bg0"], height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=C["red"], width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="DELETE RULE", font=FONT_TITLE,
                  bg=C["bg0"], fg=C["red"], padx=16).pack(side="left", pady=12)

        # ── Body ──────────────────────────────────────────────
        body = tk.Frame(self, bg=C["bg1"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(body,
                  text="This action cannot be undone.",
                  font=FONT_LABEL, bg=C["bg1"], fg=C["text2"]).pack(anchor="w")

        tk.Label(body,
                  text=f"  {rule_label}",
                  font=("Courier New", 11, "bold"),
                  bg=C["bg1"], fg=C["text0"],
                  pady=6).pack(anchor="w")

        # ── Footer buttons ─────────────────────────────────────
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x")
        footer = tk.Frame(self, bg=C["bg1"])
        footer.pack(fill="x", padx=24, pady=14)

        FlatButton(footer, "CANCEL", self.destroy, variant="ghost").pack(side="right", padx=(6, 0))
        FlatButton(footer, "DELETE", self._confirm, variant="danger").pack(side="right")

    def _confirm(self):
        self._on_confirm()
        self.destroy()


# ═══════════════════════════════════════════════════════
#  MAIN APPLICATION WINDOW
# ═══════════════════════════════════════════════════════

class DTMFCommander(tk.Toplevel):
    """
    Main application window.

    We use a Toplevel (not Tk) so that we can keep a hidden root Tk window
    as the real OS-level window.  That hidden root is what Windows shows in
    the taskbar.  The Toplevel carries overrideredirect(True) for our custom
    chrome, while the hidden root keeps a normal WM frame (but is 1×1 and
    off-screen so the user never sees it).  Clicking the taskbar button
    correctly minimises/restores the Toplevel via the root's iconify/deiconify.
    """

    def __init__(self, root):
        super().__init__(root)
        self._root = root
        self.title("DTMF COMMANDER")
        self.geometry("1100x720")
        self._min_w = 900
        self._min_h = 620
        self.configure(bg=C["bg0"])

        # Remove the default OS titlebar so we can paint our own.
        # The taskbar icon comes from the hidden root window instead.
        self.overrideredirect(True)
        self._drag_x = 0
        self._drag_y = 0
        self._resize_edge        = None
        self._resize_start_state = None
        self._snap_active        = None

        # Keep Toplevel in sync with the hidden root so taskbar clicks work.
        self._root.bind("<Map>",   self._on_root_map)
        self._root.bind("<Unmap>", self._on_root_unmap)

        self.config_data  = load_config()
        self.stop_event   = threading.Event()
        self.result_queue = queue.Queue()
        self.is_listening = False
        self.listener     = None
        self.decoded_seq  = ""
        self.matcher      = RuleMatcher(self.config_data.get("rules", []))
        self._device_list = []

        self._build()
        self._populate_devices()
        self._refresh_rules()
        self._poll()
        self._add_resize_grip()
        if sys.platform.startswith("linux"):
            self.after(500, self._check_linux_permissions)

        # Maximize to fill work area — taskbar stays visible.
        # NOTE: overrideredirect(True) disables state("zoomed") on Windows,
        # so we measure the usable work area ourselves via wm_maxsize which
        # returns the largest geometry the window manager will allow (i.e.
        # screen minus taskbar). We then position at (0, 0) and let the WM
        # clip naturally, OR we use the SystemParametersInfo trick on Windows.
        self.update_idletasks()
        self._maximize_to_workarea()

    # ──────────────────────────────────────────────────────────
    #  LAYOUT CONSTRUCTION
    # ──────────────────────────────────────────────────────────

    def _build(self):
        # ── Custom Titlebar ───────────────────────────────────
        self._tbar = tk.Frame(self, bg=C["bg0"], height=38)
        self._tbar.pack(fill="x", side="top")
        self._tbar.pack_propagate(False)

        # Drag bindings
        self._tbar.bind("<ButtonPress-1>",   self._drag_start)
        self._tbar.bind("<B1-Motion>",        self._drag_move)
        self._tbar.bind("<ButtonRelease-1>",  self._drag_end)
        self._tbar.bind("<Double-Button-1>",  lambda e: self._toggle_maximize())

        # Window control buttons (macOS style ordering: close · min · max)
        ctrl = tk.Frame(self._tbar, bg=C["bg0"])
        ctrl.pack(side="left", padx=(10, 0), pady=0)
        ctrl.bind("<ButtonPress-1>",   self._drag_start)
        ctrl.bind("<B1-Motion>",        self._drag_move)

        self._btn_close = self._wm_btn(ctrl, "#FF5F57", self.destroy)
        self._btn_close.pack(side="left", padx=(0, 6))
        self._btn_min   = self._wm_btn(ctrl, "#FEBC2E", self._minimize)
        self._btn_min.pack(side="left", padx=(0, 6))
        self._btn_max   = self._wm_btn(ctrl, "#28C840", self._toggle_maximize)
        self._btn_max.pack(side="left")

        # Centered app name
        self._title_lbl = tk.Label(
            self._tbar,
            text="✦  DTMF COMMANDER",
            font=("Courier New", 11, "bold"),
            bg=C["bg0"], fg=C["amber"],
        )
        self._title_lbl.place(relx=0.5, rely=0.5, anchor="center")
        self._title_lbl.bind("<ButtonPress-1>",  self._drag_start)
        self._title_lbl.bind("<B1-Motion>",      self._drag_move)
        self._title_lbl.bind("<ButtonRelease-1>",self._drag_end)

        # Right cluster: status
        right_tbar = tk.Frame(self._tbar, bg=C["bg0"])
        right_tbar.pack(side="right", padx=(0, 14))

        # LED + status
        self._led = LEDIndicator(right_tbar, size=12)
        self._led.pack(side="right", pady=12, padx=(6, 2))
        self._status_lbl = tk.Label(
            right_tbar, text="IDLE",
            font=("Courier New", 9, "bold"),
            bg=C["bg0"], fg=C["text2"],
        )
        self._status_lbl.pack(side="right")

        # Thin separator under titlebar
        self._tbar_sep = tk.Frame(self, bg=C["border"], height=1)
        self._tbar_sep.pack(fill="x")

        # ── Body: three columns ───────────────────────────────
        body = tk.Frame(self, bg=C["bg0"])
        body.pack(fill="both", expand=True)

        col_left   = tk.Frame(body, bg=C["bg0"], width=270)
        col_left.pack(side="left", fill="y")
        col_left.pack_propagate(False)

        self._col_div1 = tk.Frame(body, bg=C["border"], width=1)
        self._col_div1.pack(side="left", fill="y")

        col_mid    = tk.Frame(body, bg=C["bg0"], width=360)
        col_mid.pack(side="left", fill="y")
        col_mid.pack_propagate(False)

        self._col_div2 = tk.Frame(body, bg=C["border"], width=1)
        self._col_div2.pack(side="left", fill="y")

        col_right  = tk.Frame(body, bg=C["bg0"])
        col_right.pack(side="left", fill="both", expand=True)

        self._build_col_left(col_left)
        self._build_col_mid(col_mid)
        self._build_col_right(col_right)

        # ── Footer ────────────────────────────────────────────
        self._footer_sep = tk.Frame(self, bg=C["border"], height=1)
        self._footer_sep.pack(fill="x", side="bottom")
        self._footer = tk.Frame(self, bg=C["bg1"], height=26)
        self._footer.pack(fill="x", side="bottom")
        self._footer.pack_propagate(False)
        self._footer_lbl = tk.Label(
            self._footer,
            text="Made with ♥ by Edward Stark",
            font=("Courier New", 8),
            bg=C["bg1"], fg=C["text2"],
        )
        self._footer_lbl.pack(side="right", padx=16, pady=4)
        self._footer_ver = tk.Label(
            self._footer,
            text="v2.1  //  DTMF Commander",
            font=("Courier New", 8),
            bg=C["bg1"], fg=C["text3"],
        )
        self._footer_ver.pack(side="left", padx=16, pady=4)

    # ── Window manager button helper ──────────────────────────

    def _wm_btn(self, parent, color, cmd):
        size = 14
        img  = tk.PhotoImage(width=size, height=size)

        hx = color.lstrip("#")
        if len(hx) == 3:
            hx = "".join(c*2 for c in hx)
        cr, cg, cb = int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)

        bghx = C["bg0"].lstrip("#")
        if len(bghx) == 3:
            bghx = "".join(c*2 for c in bghx)
        br, bg_c, bb = int(bghx[0:2], 16), int(bghx[2:4], 16), int(bghx[4:6], 16)

        cx = cy = size / 2.0
        r  = size / 2.0 - 0.5

        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                hits = 0
                for sy in range(3):
                    for sx in range(3):
                        fx = x + (sx + 0.5) / 3.0
                        fy = y + (sy + 0.5) / 3.0
                        if (fx - cx) ** 2 + (fy - cy) ** 2 <= r * r:
                            hits += 1
                alpha = hits / 9.0
                pr = int(cr * alpha + br * (1 - alpha))
                pg = int(cg * alpha + bg_c * (1 - alpha))
                pb = int(cb * alpha + bb * (1 - alpha))
                row.append(f"#{pr:02x}{pg:02x}{pb:02x}")
            rows.append("{" + " ".join(row) + "}")

        img.put(" ".join(rows))

        c = tk.Canvas(parent, width=size, height=size,
                       bg=C["bg0"], highlightthickness=0, cursor="hand2")
        c.create_image(0, 0, anchor="nw", image=img)
        c._img_ref = img

        c.bind("<Button-1>", lambda _: cmd())
        c._circle_color = color
        if not hasattr(self, "_wm_canvases"):
            self._wm_canvases = []
        self._wm_canvases.append(c)
        return c

    # ── Drag / window management ──────────────────────────────

    def _drag_start(self, e):
        if getattr(self, "_snap_active", None):
            # Un-snap: restore pre-snap size, re-anchor drag under cursor
            geo = getattr(self, "_pre_snap_geo", None)
            self._snap_active  = None
            self._is_maximized = False
            if geo:
                try:
                    pw = int(geo.split("x")[0])
                except Exception:
                    pw = self.winfo_width()
                self.geometry(geo)
                self.update_idletasks()
                self._drag_x = min(e.x_root - self.winfo_x(), pw - 20)
                self._drag_y = e.y_root - self.winfo_y()
            else:
                self._drag_x = e.x_root - self.winfo_x()
                self._drag_y = e.y_root - self.winfo_y()
            return
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        if getattr(self, "_resize_edge", None):
            return
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _drag_end(self, e):
        """On release, apply snap if cursor is near a screen edge."""
        target = self._snap_check(e.x_root, e.y_root)
        if target:
            self._snap_apply(target)

    # ── Snap (no preview overlay — just snap on release) ──────

    _SNAP_ZONE = 8   # px from screen edge that triggers snap

    def _snap_check(self, x_root, y_root):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        z  = self._SNAP_ZONE
        if y_root <= z:             return "top"
        if x_root <= z:             return "left"
        if x_root >= sw - z - 1:   return "right"
        return None

    def _snap_apply(self, target):
        wa_w, wa_h, wa_x, wa_y = self._get_workarea()
        self._pre_snap_geo = self.geometry()
        self._snap_active  = target
        if target == "left":
            self.geometry(f"{wa_w//2}x{wa_h}+{wa_x}+{wa_y}")
        elif target == "right":
            half = wa_w // 2
            self.geometry(f"{half}x{wa_h}+{wa_x + half}+{wa_y}")
        elif target == "top":
            self._pre_max_geo  = self.geometry()
            self._is_maximized = True
            self.geometry(f"{wa_w}x{wa_h}+{wa_x}+{wa_y}")

    # ── Root ↔ Toplevel sync (taskbar integration) ────────────

    def _on_root_map(self, e):
        """Hidden root was restored → bring the Toplevel back."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_root_unmap(self, e):
        """Hidden root was minimised → hide the Toplevel too."""
        self.withdraw()

    def _minimize(self):
        """Minimise via the hidden root so the taskbar button works."""
        self._root.iconify()   # triggers _on_root_unmap → withdraw()

    def _on_restore(self, e):
        pass

    def _get_workarea(self):
        # ── Windows ──────────────────────────────────────────────
        if sys.platform == "win32":
            try:
                import ctypes
                class RECT(ctypes.Structure):
                    _fields_ = [("left", ctypes.c_long), ("top",    ctypes.c_long),
                                 ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
                rect = RECT()
                ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
                if ok:
                    return (rect.right - rect.left,
                            rect.bottom - rect.top,
                            rect.left, rect.top)
            except Exception:
                pass

        # ── Linux / macOS fallback — use wm_maxsize + screen dims ─
        # wm_maxsize() returns the usable area on many Linux WMs.
        try:
            mw, mh = self.wm_maxsize()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            # Some WMs return absurdly large values; cap to screen
            w = min(mw, sw) if mw > 0 else sw
            h = min(mh, sh) if mh > 0 else sh
            # On many Linux DEs, work area starts at (0,0) but
            # the WM clips naturally, so we just use (0,0).
            return w, h, 0, 0
        except Exception:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            return sw, sh, 0, 0

    # ──────────────────────────────────────────────────────────
    #  RESIZE  — corner grip + edge cursor hints
    # ──────────────────────────────────────────────────────────

    _EDGE = 6   # px from window border that counts as resize zone

    def _add_resize_grip(self):
        """
        Resize via the corner grip widget only.
        No bindings on the Toplevel itself — those cause X11 crashes on Linux
        when overrideredirect is active and motion events fire across child widgets.
        """
        grip = tk.Frame(self, bg=C["border"], width=10, height=10,
                        cursor="bottom_right_corner")
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.lift()
        grip.bind("<ButtonPress-1>",   lambda e: self._resize_begin(e, "se"))
        grip.bind("<B1-Motion>",       self._resize_do)
        grip.bind("<ButtonRelease-1>", self._resize_finish)
        self._grip = grip

        self._resize_edge        = None
        self._resize_start_state = None
        self._resize_motion_id   = None
        self._resize_release_id  = None

    def _edge_zone(self, ex, ey):
        E = self._EDGE
        w = self.winfo_width()
        h = self.winfo_height()
        on_r = ex >= w - E;  on_b = ey >= h - E
        on_l = ex <= E;      on_t = ey <= E
        if on_r and on_b: return "se"
        if on_l and on_b: return "sw"
        if on_r and on_t: return "ne"
        if on_l and on_t: return "nw"
        if on_r: return "e"
        if on_b: return "s"
        if on_l: return "w"
        if on_t: return "n"
        return None

    def _resize_begin(self, e, edge):
        self._resize_edge = edge
        self._resize_start_state = (
            e.x_root, e.y_root,
            self.winfo_x(), self.winfo_y(),
            self.winfo_width(), self.winfo_height(),
        )

    def _resize_do(self, e):
        if not getattr(self, "_resize_edge", None) or not self._resize_start_state:
            return
        rx0, ry0, wx, wy, ww, wh = self._resize_start_state
        dx   = e.x_root - rx0
        dy   = e.y_root - ry0
        edge = self._resize_edge
        nx, ny, nw, nh = wx, wy, ww, wh
        if "e" in edge: nw = max(self._min_w, ww + dx)
        if "s" in edge: nh = max(self._min_h, wh + dy)
        if "w" in edge:
            nw = max(self._min_w, ww - dx)
            nx = wx + (ww - nw)
        if "n" in edge:
            nh = max(self._min_h, wh - dy)
            ny = wy + (wh - nh)
        self.geometry(f"{nw}x{nh}+{nx}+{ny}")

    def _resize_finish(self, e=None):
        self._resize_edge        = None
        self._resize_start_state = None
        self._resize_motion_id   = None
        self._resize_release_id  = None

    # ──────────────────────────────────────────────────────────
    #  SNAP  (Aero-style: half-screen on left/right, full on top)
    # ──────────────────────────────────────────────────────────

    _SNAP_ZONE = 8   # px from screen edge that triggers snap preview

    def _snap_check(self, x_root, y_root):
        """Return snap target ('left','right','top') or None."""
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        z  = self._SNAP_ZONE
        if y_root <= z:
            return "top"
        if x_root <= z:
            return "left"
        if x_root >= sw - z - 1:
            return "right"
        return None

    def _maximize_to_workarea(self):
        w, h, x, y = self._get_workarea()
        self.geometry(f"{w}x{h}+{x}+{y}")
        try:
            self._root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def destroy(self):
        """Close both the Toplevel and the hidden root."""
        try:
            self._root.destroy()
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass

    def _toggle_maximize(self):
        if getattr(self, "_is_maximized", False):
            geo = getattr(self, "_pre_max_geo", None)
            if geo:
                self.geometry(geo)
            self._is_maximized = False
            self._snap_active  = None
        else:
            self._pre_max_geo  = self.geometry()
            self._maximize_to_workarea()
            self._is_maximized = True
            self._snap_active  = "top"

    # ── LEFT: input selector + controls ───────────────────────

    def _build_col_left(self, col):
        self._section_header(col, "INPUT")

        inner = tk.Frame(col, bg=C["bg0"])
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        tk.Label(inner, text="AUDIO DEVICE", font=FONT_LABEL,
                  bg=C["bg0"], fg=C["text2"]).pack(anchor="w", pady=(0, 4))
        self._dev_var = tk.StringVar()
        self._dev_drop = FlatDropdown(inner, self._dev_var, [])
        self._dev_drop.pack(fill="x")
        self._dev_var.trace_add("write", self._on_device_change)

        sep(inner, fill="x", pady=(14, 14))

        self._btn_listen = FlatButton(inner, "▶  START LISTENING",
                                       self._toggle_listen, variant="primary")
        self._btn_listen.pack(fill="x")

        FlatButton(inner, "⟳  REFRESH DEVICES",
                    self._populate_devices, variant="ghost").pack(fill="x", pady=(8, 0))

        sep(inner, fill="x", pady=(20, 16))

        FlatButton(inner, "✕  CLEAR OUTPUT",
                    self._clear_decoded, variant="ghost").pack(fill="x")

        tk.Frame(inner, bg=C["bg0"]).pack(fill="both", expand=True)

    # ── MIDDLE: decoded display + log ─────────────────────────

    def _build_col_mid(self, col):
        self._section_header(col, "DECODED OUTPUT")

        disp_frame = tk.Frame(col, bg=C["bg1"],
                               highlightbackground=C["border"], highlightthickness=1)
        disp_frame.pack(fill="x", padx=16, pady=(12, 0))

        self._last_key_lbl = tk.Label(
            disp_frame, text="—", font=("Courier New", 72, "bold"),
            bg=C["bg1"], fg=C["amber"], width=4, height=2, anchor="center",
        )
        self._last_key_lbl.pack(fill="x")

        seq_row = tk.Frame(disp_frame, bg=C["bg2"])
        seq_row.pack(fill="x")
        tk.Label(seq_row, text="SEQ:", font=FONT_LABEL,
                  bg=C["bg2"], fg=C["text2"], padx=8, pady=6).pack(side="left")
        self._seq_lbl = tk.Label(seq_row, text="",
                                  font=("Courier New", 11, "bold"),
                                  bg=C["bg2"], fg=C["cyan"],
                                  anchor="w", padx=4)
        self._seq_lbl.pack(side="left", fill="x", expand=True)

        self._section_header(col, "ACTIVITY LOG", pady=(20, 0))

        log_outer = tk.Frame(col, bg=C["bg1"],
                              highlightbackground=C["border"], highlightthickness=1)
        log_outer.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self._log_text = tk.Text(
            log_outer, bg=C["bg1"], fg=C["text1"],
            font=("Courier New", 8), relief="flat", bd=0, state="disabled",
            wrap="char", insertbackground=C["amber"],
            selectbackground=C["border_hi"], selectforeground=C["text0"],
        )
        sb = FlatScrollbar(log_outer, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True, padx=2, pady=2)
        # Forward mousewheel from text widget to the custom scrollbar
        self._log_text.bind("<MouseWheel>", sb._on_wheel)
        self._log_text.bind("<Button-4>",   sb._on_wheel)
        self._log_text.bind("<Button-5>",   sb._on_wheel)

        self._log_text.tag_configure("ts",      foreground=C["text3"])
        self._log_text.tag_configure("digit",   foreground=C["amber"],  font=("Courier New", 8, "bold"))
        self._log_text.tag_configure("trigger", foreground=C["green"],  font=("Courier New", 8, "bold"))
        self._log_text.tag_configure("error",   foreground=C["red"])
        self._log_text.tag_configure("info",    foreground=C["text2"])
        self._log_text.tag_configure("success", foreground=C["green"])

    # ── RIGHT: rules panel ────────────────────────────────────

    def _build_col_right(self, col):
        hdr = tk.Frame(col, bg=C["bg0"], height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Frame(hdr, bg=C["border"], width=1).pack(side="left", fill="y")

        tk.Label(hdr, text="COMMAND RULES", font=FONT_HEAD,
                  bg=C["bg0"], fg=C["text0"], padx=16).pack(side="left", pady=12)

        FlatButton(hdr, "+  NEW RULE",
                    lambda: self._open_editor(), variant="primary").pack(side="right", padx=14, pady=8)

        sep(col, fill="x")

        rules_outer = tk.Frame(col, bg=C["bg0"])
        rules_outer.pack(fill="both", expand=True)

        self._rules_canvas = tk.Canvas(rules_outer, bg=C["bg0"], highlightthickness=0)
        rules_sb = FlatScrollbar(rules_outer, orient="vertical",
                                  command=self._rules_canvas.yview)
        self._rules_canvas.configure(yscrollcommand=rules_sb.set)
        rules_sb.pack(side="right", fill="y")
        self._rules_canvas.pack(side="left", fill="both", expand=True)
        # Forward mousewheel from canvas to the custom scrollbar
        self._rules_canvas.bind("<MouseWheel>", rules_sb._on_wheel)
        self._rules_canvas.bind("<Button-4>",   rules_sb._on_wheel)
        self._rules_canvas.bind("<Button-5>",   rules_sb._on_wheel)

        self._rules_frame = tk.Frame(self._rules_canvas, bg=C["bg0"])
        self._rules_win   = self._rules_canvas.create_window(
            (0, 0), window=self._rules_frame, anchor="nw")

        self._rules_frame.bind("<Configure>",
            lambda e: self._rules_canvas.configure(
                scrollregion=self._rules_canvas.bbox("all")))
        self._rules_canvas.bind("<Configure>",
            lambda e: self._rules_canvas.itemconfig(self._rules_win, width=e.width))

        btm = tk.Frame(col, bg=C["bg1"], height=32)
        btm.pack(fill="x", side="bottom")
        btm.pack_propagate(False)
        sep(col, orient="h", fill="x", side="bottom")
        tk.Label(btm,
                  text="Rules fire when the decoded sequence ends with the configured DTMF password.",
                  font=("Courier New", 7), bg=C["bg1"], fg=C["text3"],
                  padx=12).pack(side="left", pady=8)

    # ──────────────────────────────────────────────────────────
    #  SECTION HEADER helper
    # ──────────────────────────────────────────────────────────

    def _section_header(self, parent, title, pady=(0, 0)):
        f = tk.Frame(parent, bg=C["bg0"], height=32)
        f.pack(fill="x", pady=pady)
        f.pack_propagate(False)
        tk.Frame(f, bg=C["amber"], width=3).pack(side="left", fill="y")
        tk.Label(f, text=title, font=("Courier New", 8, "bold"),
                  bg=C["bg0"], fg=C["amber"], padx=14).pack(side="left", pady=8)

    # ──────────────────────────────────────────────────────────
    #  LINUX PERMISSION DIAGNOSTICS
    # ──────────────────────────────────────────────────────────

    def _check_linux_permissions(self):
        """
        On Linux, warn the user if they are not in the 'audio' or 'dialout'
        groups, which are required for microphone and serial port access.
        Running as root bypasses this, but group membership is the clean fix.
        """
        import subprocess, os
        warnings = []
        try:
            groups_out = subprocess.check_output(["groups"], text=True).strip()
            groups = groups_out.split()
            if "audio" not in groups and os.geteuid() != 0:
                warnings.append(
                    "Not in 'audio' group → mic may be blocked.  "
                    "Fix: sudo usermod -aG audio $USER  (then log out/in)"
                )
            if "dialout" not in groups and "uucp" not in groups and os.geteuid() != 0:
                warnings.append(
                    "Not in 'dialout' group → serial ports may be blocked.  "
                    "Fix: sudo usermod -aG dialout $USER  (then log out/in)"
                )
        except Exception:
            pass

        for w in warnings:
            self._log(f"⚠ LINUX: {w}", "error")

    # ──────────────────────────────────────────────────────────
    #  DEVICE MANAGEMENT
    # ──────────────────────────────────────────────────────────

    def _populate_devices(self, *_):
        self._device_list = list_audio_devices()

        # ── Linux fallback: if sounddevice returned nothing, try to enumerate
        #    ALSA/PulseAudio input devices via arecord / pactl ────────────────
        if not self._device_list and sys.platform.startswith("linux"):
            self._device_list = self._linux_enum_audio()

        names = [f"[{i}] {n}" for i, n in self._device_list] if self._device_list \
                else ["(no audio devices found)"]

        if not self._device_list:
            self._log(
                "No audio inputs found.  On Linux, try: "
                "sudo usermod -aG audio $USER  then log out/in, "
                "or run with:  python3 dtmf_ui.py  (no sudo needed if in 'audio' group)",
                "error",
            )

        self._dev_drop.update_values(names)

        saved = self.config_data.get("audio_device_index")
        if saved is not None and self._device_list:
            for j, (idx, _) in enumerate(self._device_list):
                if idx == saved:
                    self._dev_var.set(names[j])
                    return
        if names:
            self._dev_var.set(names[0])

    @staticmethod
    def _linux_enum_audio():
        """
        Best-effort audio device enumeration on Linux when sounddevice fails.
        Tries sounddevice with ALSA env hint, then falls back to arecord -l.
        Returns list of (index, name) tuples compatible with list_audio_devices().
        """
        import os, subprocess, re

        # 1. Retry sounddevice with ALSA backend forced
        try:
            import sounddevice as sd
            os.environ.setdefault("AUDIODEV", "hw:0,0")
            devs = sd.query_devices()
            result = [
                (i, d["name"])
                for i, d in enumerate(devs)
                if d.get("max_input_channels", 0) > 0
            ]
            if result:
                return result
        except Exception:
            pass

        # 2. Parse `arecord -l` output for capture devices
        try:
            out = subprocess.check_output(["arecord", "-l"], stderr=subprocess.DEVNULL,
                                           timeout=3).decode("utf-8", errors="replace")
            cards = []
            for line in out.splitlines():
                m = re.match(r"card\s+(\d+).*?:\s+(.+?)\s*(?:\[.*?\])?\s*$", line)
                if m:
                    cards.append((int(m.group(1)), m.group(2).strip()))
            if cards:
                return cards
        except Exception:
            pass

        return []

    def _on_device_change(self, *_):
        sel_name = self._dev_var.get()
        for j, (idx, _) in enumerate(self._device_list):
            if sel_name.startswith(f"[{idx}]"):
                self.config_data["audio_device_index"] = idx
                save_config(self.config_data)
                return

    def _get_device_index(self):
        sel = self._dev_var.get()
        for idx, name in self._device_list:
            if sel.startswith(f"[{idx}]"):
                return idx
        return None

    # ──────────────────────────────────────────────────────────
    #  LISTEN CONTROL
    # ──────────────────────────────────────────────────────────

    def _toggle_listen(self):
        if self.is_listening:
            self._stop()
        else:
            self._start()

    def _start(self):
        self.stop_event.clear()
        dev = self._get_device_index()
        self.listener = DTMFListener(dev, self.result_queue, self.stop_event)
        self.listener.start()
        self.is_listening = True
        self._btn_listen.set_text("■  STOP LISTENING")
        self._btn_listen.set_variant("danger")

    def _stop(self):
        self.stop_event.set()
        self.is_listening = False
        self._btn_listen.set_text("▶  START LISTENING")
        self._btn_listen.set_variant("primary")

    # ──────────────────────────────────────────────────────────
    #  QUEUE POLLING
    # ──────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "digit":
                    self._on_digit(payload)
                elif kind == "status":
                    self._set_status(payload)
                elif kind == "error":
                    self._log(f"ERROR: {payload}", "error")
                    self._set_status("error")
                    self._stop()
        except queue.Empty:
            pass
        self.after(60, self._poll)

    # ──────────────────────────────────────────────────────────
    #  DIGIT HANDLING
    # ──────────────────────────────────────────────────────────

    def _on_digit(self, digits):
        self.decoded_seq += digits

        self._last_key_lbl.configure(text=digits[-1])
        self._last_key_lbl.configure(fg=C["text0"])
        self.after(120, lambda: self._last_key_lbl.configure(fg=C["amber"]))

        display_seq = self.decoded_seq[-20:]
        self._seq_lbl.configure(text=display_seq)

        self._log(f"DTMF  {digits}", "digit")

        triggered = self.matcher.feed(digits)
        for rule in triggered:
            self._fire(rule)

    def _fire(self, rule):
        lbl     = rule.get("label", "?")
        port    = rule["port"]
        command = rule["command"]
        baud    = int(rule.get("baud", 9600))
        self._log(f"MATCH '{lbl}'  →  {port}", "trigger")
        ok, err = send_to_com(port, command, baud)
        if ok:
            self._log(f"SENT  {repr(command)}  [{port}]", "success")
        else:
            self._log(f"FAIL  {err}", "error")

    def _clear_decoded(self):
        self.decoded_seq = ""
        self._last_key_lbl.configure(text="—")
        self._seq_lbl.configure(text="")
        self.matcher.reset()

    # ──────────────────────────────────────────────────────────
    #  STATUS / LOG
    # ──────────────────────────────────────────────────────────

    def _set_status(self, status):
        mapping = {
            "listening": ("LISTENING", C["green"]),
            "stopped":   ("IDLE",      C["text3"]),
            "error":     ("ERROR",     C["red"]),
            "idle":      ("IDLE",      C["text3"]),
        }
        text, color = mapping.get(status, ("IDLE", C["text3"]))
        self._status_lbl.configure(text=text, fg=color)
        self._led.set_color(color)

    def _log(self, message, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"{ts}  ", "ts")
        self._log_text.insert("end", f"{message}\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    # ──────────────────────────────────────────────────────────
    #  RULES LIST
    # ──────────────────────────────────────────────────────────

    def _refresh_rules(self):
        for w in self._rules_frame.winfo_children():
            w.destroy()

        rules = self.config_data.get("rules", [])
        self.matcher = RuleMatcher(rules)

        if not rules:
            tk.Label(self._rules_frame,
                      text="\n\n  No rules defined.\n  Click  +  NEW RULE  to add one.",
                      font=FONT_LABEL, bg=C["bg0"], fg=C["text3"],
                      justify="left").pack(padx=16, pady=16, anchor="w")
            return

        for i, rule in enumerate(rules):
            self._build_rule_card(i, rule)

    def _build_rule_card(self, idx, rule):
        lbl_text = rule.get("label",   f"Rule {idx+1}")
        pw       = rule.get("password","")
        port     = rule.get("port",    "")
        command  = rule.get("command", "")
        baud     = rule.get("baud",    9600)

        card = tk.Frame(self._rules_frame, bg=C["bg1"],
                         highlightbackground=C["border"], highlightthickness=1)
        card.pack(fill="x", padx=12, pady=5)

        tk.Frame(card, bg=C["cyan"], width=3).pack(side="left", fill="y")

        inner = tk.Frame(card, bg=C["bg1"])
        inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        r1 = tk.Frame(inner, bg=C["bg1"])
        r1.pack(fill="x")

        tk.Label(r1, text=lbl_text, font=FONT_MONO_LG,
                  bg=C["bg1"], fg=C["text0"]).pack(side="left")

        self._chip(r1, pw,   C["amber"], C["bg0"]).pack(side="left", padx=(12, 4))
        self._chip(r1, port, C["cyan"],  C["bg0"]).pack(side="left", padx=2)

        r2 = tk.Frame(inner, bg=C["bg1"])
        r2.pack(fill="x", pady=(4, 0))
        tk.Label(r2, text=f"  cmd: {command}",
                  font=("Courier New", 8), bg=C["bg1"], fg=C["text2"]).pack(side="left")
        tk.Label(r2, text=f"  {baud} baud",
                  font=("Courier New", 8), bg=C["bg1"], fg=C["text3"]).pack(side="left")

        btns = tk.Frame(card, bg=C["bg1"])
        btns.pack(side="right", padx=10)

        FlatButton(btns, "EDIT", lambda i=idx: self._open_editor(i),
                    variant="ghost2").pack(pady=(10, 4))
        del_b = FlatButton(btns, "DEL", lambda i=idx: self._delete(i),
                            variant="ghost2")
        del_b._lbl.configure(fg=C["red"])
        del_b.pack()

    def _chip(self, parent, text, fg, bg):
        return tk.Label(parent, text=f" {text} ", font=("Courier New", 8, "bold"),
                         bg=bg, fg=fg, padx=4, pady=1, relief="flat")

    def _delete(self, idx):
        rules = self.config_data.get("rules", [])
        lbl   = rules[idx].get("label", f"Rule {idx+1}")

        def _do_delete():
            rules.pop(idx)
            self.config_data["rules"] = rules
            save_config(self.config_data)
            self._refresh_rules()
            self._log(f"DELETED rule '{lbl}'", "info")

        _ConfirmDeleteDialog(self, lbl, _do_delete)

    def _open_editor(self, edit_idx=None):
        rules    = self.config_data.get("rules", [])
        existing = rules[edit_idx] if edit_idx is not None else None

        def on_save(new_rule):
            if edit_idx is not None:
                rules[edit_idx] = new_rule
            else:
                rules.append(new_rule)
            self.config_data["rules"] = rules
            save_config(self.config_data)
            self._refresh_rules()
            verb = "UPDATED" if edit_idx is not None else "CREATED"
            self._log(f"{verb} rule '{new_rule['label']}'", "success")

        RuleEditorDialog(self, on_save, existing_rule=existing)


# ═══════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════

def main():
    # ── FIX: suppress console window on Windows (was only running inside
    #    the pyw guard, but also safe to do here since dtmf_ui.pyw imports
    #    this function directly) ──────────────────────────────────────────
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

    # Hidden root = real OS window that owns the taskbar button.
    # FIXED: do NOT call root.withdraw() here.  withdraw() hides the root
    # from the WM entirely; when the splash finishes and we call
    # deiconify(), Windows briefly has zero mapped windows which causes
    # the app to vanish from the taskbar (and sometimes not re-appear).
    # Instead we keep the root mapped but invisible via alpha=0 and the
    # 1x1 off-screen geometry — the taskbar button stays alive the whole
    # time, and deiconify() in launch_app() is then a no-op (already
    # mapped) so there is no flicker or race.
    root = tk.Tk()
    root.title("DTMF COMMANDER")
    root.geometry("1x1+-9999+-9999")   # off-screen, invisible
    root.overrideredirect(False)        # keeps the OS taskbar button
    root.attributes("-alpha", 0.0)     # fully transparent — user never sees it
    # NOTE: root.withdraw() intentionally removed — see comment above.

    # ── Custom icon ───────────────────────────────────────────
    def _make_app_icon(size=64):
        img = tk.PhotoImage(width=size, height=size)
        bg_hex  = "#080A0C"
        fg_hex  = "#FFA600"

        def parse(h):
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        br, bg_c, bb = parse(bg_hex)
        fr, fg_c, fb = parse(fg_hex)
        cx = cy = size / 2.0

        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                hits = 0
                for sy in range(3):
                    for sx in range(3):
                        px = x + (sx + 0.5) / 3 - cx
                        py = y + (sy + 0.5) / 3 - cy
                        nx = px / (size / 2.0)
                        ny = py / (size / 2.0)
                        k   = 0.45
                        r   = 0.72
                        in_star = (
                            (abs(nx) + abs(ny) * k < r) and
                            (abs(nx) * k + abs(ny) < r)
                        )
                        in_dot = (nx * nx + ny * ny) < 0.04
                        if in_star or in_dot:
                            hits += 1
                a = hits / 9.0
                row.append(
                    f"#{int(fr*a + br*(1-a)):02x}"
                    f"{int(fg_c*a + bg_c*(1-a)):02x}"
                    f"{int(fb*a + bb*(1-a)):02x}"
                )
            rows.append("{" + " ".join(row) + "}")
        img.put(" ".join(rows))
        return img

    _icon_img = _make_app_icon(64)
    root.iconphoto(True, _icon_img)

    def launch_app():
        # FIXED: root is already mapped (never withdrawn), so this is
        # just a safety call — but it is harmless and ensures the
        # taskbar button is definitely visible before the main window
        # appears.  Do NOT call root.withdraw() earlier in this function.
        root.deiconify()
        DTMFCommander(root)

    class _Splash(tk.Toplevel):
        DURATION_MS = 3000

        def __init__(self, parent, on_done):
            super().__init__(parent)
            self.on_done = on_done
            self.overrideredirect(True)
            self.configure(bg=C["bg0"])
            self.attributes("-topmost", True)
            self._build()
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w  = self.winfo_width()
            h  = self.winfo_height()
            self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
            self.after(self.DURATION_MS, self._finish)

        def _build(self):
            import os, glob
            script_dir = os.path.dirname(os.path.abspath(__file__))
            img_widget = None
            candidates = (
                sorted(glob.glob(os.path.join(script_dir, "*.png"))) +
                sorted(glob.glob(os.path.join(script_dir, "*.gif")))
            )
            for path in candidates:
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(path)
                    try:
                        resample = Image.Resampling.LANCZOS
                    except AttributeError:
                        resample = Image.LANCZOS
                    pil_img = pil_img.resize((500, 500), resample)
                    img = ImageTk.PhotoImage(pil_img)
                    lbl = tk.Label(self, image=img, bg=C["bg0"], bd=0)
                    lbl.image = img
                    lbl.pack()
                    img_widget = lbl
                    break
                except ImportError as e:
                    print("Pillow is required to display the splash image:", e)
                    break
                except Exception as e:
                    print("Failed to load splash image:", path, e)

            if img_widget is None:
                outer = tk.Frame(self, bg=C["bg0"], padx=80, pady=50)
                outer.pack()
                tk.Label(outer, text="\u2726",
                         font=("Courier New", 48), bg=C["bg0"], fg=C["amber"]).pack()
                tk.Label(outer, text="DTMF",
                         font=("Courier New", 36, "bold"), bg=C["bg0"], fg=C["amber"]).pack()
                tk.Label(outer, text="COMMANDER",
                         font=("Courier New", 22, "bold"), bg=C["bg0"], fg=C["text0"]).pack()
                tk.Frame(outer, bg=C["amber"], height=2, width=260).pack(pady=(18, 14))
                tk.Label(outer, text="Made with \u2665 by Edward Stark",
                         font=("Courier New", 9), bg=C["bg0"], fg=C["text2"]).pack()

        def _finish(self):
            self.destroy()
            self.on_done()

    _Splash(root, on_done=launch_app)
    root.mainloop()


if __name__ == "__main__":
    main()