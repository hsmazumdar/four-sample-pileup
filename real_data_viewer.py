"""Reviewer GUI for the measured SDD + Fe-55 dataset.

    python real_data_viewer.py

Keys: Up / Dn (or Left / Right) step pulses; Space scan/pause;
Home / End first/last; + / − scan speed.
"""

from __future__ import annotations

from pathlib import Path
import csv
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sparse_pileup.real_sdd import (  # noqa: E402
    ADC_CHANNELS,
    DEFAULT_LEAVE_CH,
    DEFAULT_PULSE_THR,
    NOISE_FLOOR_CH,
    SAMPLE_PERIOD_US,
    filter_pulses,
    find_pulses,
    find_trigger,
    four_taps,
    load_all_samples,
    load_metadata,
)

FILTERS = (
    ("Fe-55 window (1100–1400 ch)", "fe55"),
    ("All pulses above threshold", "all"),
    ("Close Fe-55 pairs (< 8 µs)", "close"),
    ("High periodic (~3650 ch)", "high"),
    ("Other amplitudes", "other"),
)


class RealDataViewer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SDD + Fe-55 pulse viewer — four-sample radiation source counting")
        self.geometry("1180x760")
        self.minsize(960, 640)

        self.samples: np.ndarray | None = None
        self.segments = []
        self.pulses = []
        self.view: list = []
        self.index = 0
        self.scanning = False
        self._scan_job: str | None = None
        self.meta = {}

        self.filter_label = tk.StringVar(value=FILTERS[0][0])
        self.threshold = tk.IntVar(value=DEFAULT_PULSE_THR)
        self.stride = tk.IntVar(value=3)
        self.context = tk.IntVar(value=40)
        self.speed_ms = tk.IntVar(value=400)
        self.jump_to = tk.IntVar(value=1)
        self.show_taps = tk.BooleanVar(value=True)
        self.show_trigger = tk.BooleanVar(value=True)
        self.axis_us = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Loading measured traces…")

        self._build()
        self.after(80, self._start_load)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Filter").grid(row=0, column=0, sticky="w")
        filt = ttk.Combobox(
            top,
            textvariable=self.filter_label,
            values=[a for a, _ in FILTERS],
            width=32,
            state="readonly",
        )
        filt.grid(row=0, column=1, padx=(4, 12))
        filt.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Label(top, text="Threshold").grid(row=0, column=2)
        thr = ttk.Spinbox(top, from_=20, to=2000, increment=10, textvariable=self.threshold, width=6)
        thr.grid(row=0, column=3, padx=(4, 4))
        ttk.Button(top, text="Re-find", command=self._refind).grid(row=0, column=4, padx=(0, 12))

        ttk.Label(top, text="Tap stride").grid(row=0, column=5)
        ttk.Spinbox(top, from_=1, to=15, textvariable=self.stride, width=4, command=self._redraw).grid(
            row=0, column=6, padx=(4, 12)
        )

        ttk.Label(top, text="Context").grid(row=0, column=7)
        ttk.Spinbox(top, from_=10, to=400, increment=10, textvariable=self.context, width=5, command=self._redraw).grid(
            row=0, column=8, padx=(4, 0)
        )

        nav = ttk.Frame(self, padding=(8, 0, 8, 4))
        nav.pack(fill=tk.X)
        for i, (label, cmd) in enumerate(
            (
                ("|< First", self.first_pulse),
                ("Up", self.prev_pulse),
                ("Scan", self.start_scan),
                ("Pause", self.pause_scan),
                ("Dn", self.next_pulse),
                ("Last >|", self.last_pulse),
            )
        ):
            ttk.Button(nav, text=label, command=cmd, width=10).grid(row=0, column=i, padx=2)

        ttk.Label(nav, text="Speed ms").grid(row=0, column=6, padx=(16, 4))
        ttk.Scale(nav, from_=80, to=2000, variable=self.speed_ms, orient=tk.HORIZONTAL, length=160).grid(
            row=0, column=7, padx=(0, 8)
        )
        ttk.Label(nav, text="Jump").grid(row=0, column=8)
        ttk.Entry(nav, textvariable=self.jump_to, width=7).grid(row=0, column=9, padx=4)
        ttk.Button(nav, text="Go", command=self.jump, width=5).grid(row=0, column=10)
        ttk.Button(nav, text="Export pulse", command=self.export_pulse).grid(row=0, column=11, padx=(12, 0))

        opts = ttk.Frame(self, padding=(8, 0, 8, 4))
        opts.pack(fill=tk.X)
        ttk.Checkbutton(opts, text="Four-sample taps", variable=self.show_taps, command=self._redraw).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Checkbutton(opts, text="Trigger", variable=self.show_trigger, command=self._redraw).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Checkbutton(opts, text="Time in µs", variable=self.axis_us, command=self._redraw).pack(side=tk.LEFT)

        self.info = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.info, padding=(8, 2), font=("Consolas", 10)).pack(fill=tk.X)

        fig = Figure(figsize=(11.2, 5.6), dpi=100)
        self.ax_wave = fig.add_subplot(2, 1, 1)
        self.ax_hist = fig.add_subplot(2, 1, 2)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.12, hspace=0.38)
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill=tk.X)

        ttk.Label(self, textvariable=self.status, padding=6, relief=tk.SUNKEN, anchor="w").pack(fill=tk.X)

        self.bind("<Up>", lambda _e: self.prev_pulse())
        self.bind("<Down>", lambda _e: self.next_pulse())
        self.bind("<Left>", lambda _e: self.prev_pulse())
        self.bind("<Right>", lambda _e: self.next_pulse())
        self.bind("<space>", lambda _e: self.toggle_scan())
        self.bind("<Home>", lambda _e: self.first_pulse())
        self.bind("<End>", lambda _e: self.last_pulse())
        self.bind("<plus>", lambda _e: self._nudge_speed(-80))
        self.bind("<minus>", lambda _e: self._nudge_speed(80))
        self.bind("<Escape>", lambda _e: self.pause_scan())

    def _nudge_speed(self, delta: int) -> None:
        self.speed_ms.set(min(2000, max(80, int(self.speed_ms.get()) + delta)))

    def _start_load(self) -> None:
        def worker() -> None:
            try:
                meta = load_metadata(ROOT)

                def progress(i, n, name):
                    self.after(0, lambda i=i, n=n, name=name: self.status.set(f"Loading {i}/{n}  {name}"))

                samples, segments = load_all_samples(ROOT, progress=progress)
                self.after(0, lambda: self.status.set("Finding pulses…"))
                pulses = find_pulses(samples, segments, threshold=int(self.threshold.get()))
                self.after(0, lambda: self._on_loaded(meta, samples, segments, pulses))
            except Exception as exc:
                self.after(0, lambda: self._load_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _load_failed(self, exc: Exception) -> None:
        self.status.set(f"Load failed: {exc}")
        messagebox.showerror("Load failed", str(exc))

    def _on_loaded(self, meta, samples, segments, pulses) -> None:
        self.meta = meta
        self.samples = samples
        self.segments = segments
        self.pulses = pulses
        who = meta.get("acquired_by", {})
        self.status.set(
            f"{len(segments)} segments, {samples.size:,} samples, {len(pulses)} pulses  |  "
            f"10 MSPS, 12-bit, peaking {meta.get('peaking_time_us')} µs  |  "
            f"{who.get('name', '')}, {who.get('affiliation', '')}"
        )
        self._apply_filter()

    def _refind(self) -> None:
        if self.samples is None:
            return
        self.pause_scan()
        self.status.set("Finding pulses…")
        self.update_idletasks()
        self.pulses = find_pulses(
            self.samples,
            self.segments,
            threshold=int(self.threshold.get()),
            leave=DEFAULT_LEAVE_CH,
        )
        self.status.set(f"Re-found {len(self.pulses)} pulses at threshold {self.threshold.get()}")
        self._apply_filter()

    def _filter_mode(self) -> str:
        label = self.filter_label.get()
        for text, key in FILTERS:
            if text == label:
                return key
        return "fe55"

    def _apply_filter(self) -> None:
        self.pause_scan()
        self.view = filter_pulses(self.pulses, self._filter_mode())
        self.index = 0
        self.jump_to.set(1)
        self._redraw()

    def _current(self):
        if not self.view:
            return None
        self.index = max(0, min(self.index, len(self.view) - 1))
        return self.view[self.index]

    def first_pulse(self) -> None:
        self.index = 0
        self._redraw()

    def last_pulse(self) -> None:
        self.index = max(0, len(self.view) - 1)
        self._redraw()

    def prev_pulse(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._redraw()

    def next_pulse(self) -> None:
        if self.index + 1 < len(self.view):
            self.index += 1
            self._redraw()
        elif self.scanning:
            self.pause_scan()

    def jump(self) -> None:
        n = int(self.jump_to.get())
        self.index = max(0, min(n - 1, len(self.view) - 1))
        self._redraw()

    def start_scan(self) -> None:
        if not self.view:
            return
        self.scanning = True
        self._scan_tick()

    def pause_scan(self) -> None:
        self.scanning = False
        if self._scan_job is not None:
            try:
                self.after_cancel(self._scan_job)
            except (tk.TclError, ValueError):
                pass
            self._scan_job = None

    def toggle_scan(self) -> None:
        if self.scanning:
            self.pause_scan()
        else:
            self.start_scan()

    def _scan_tick(self) -> None:
        if not self.scanning:
            return
        self.next_pulse()
        if self.scanning:
            self._scan_job = self.after(int(self.speed_ms.get()), self._scan_tick)

    def _window(self, pulse) -> tuple[int, int]:
        ctx = int(self.context.get())
        extra = 0
        if self._filter_mode() == "close" and pulse.dt_prev:
            extra = min(int(pulse.dt_prev) + ctx, 400)
        lo = max(0, pulse.global_peak - pulse.width - ctx - extra)
        hi = min(int(self.samples.size), pulse.global_peak + ctx + pulse.width)
        return lo, hi

    def _redraw(self) -> None:
        self.ax_wave.clear()
        self.ax_hist.clear()
        pulse = self._current()
        if self.samples is None:
            self.ax_wave.text(0.5, 0.5, "Loading…", ha="center", va="center", transform=self.ax_wave.transAxes)
            self.canvas.draw_idle()
            return
        if pulse is None:
            self.info.set("No pulses in this filter.")
            self.ax_wave.text(0.5, 0.5, "No pulses in this filter.", ha="center", va="center", transform=self.ax_wave.transAxes)
            self._draw_hist(None)
            self.canvas.draw_idle()
            return

        lo, hi = self._window(pulse)
        y = self.samples[lo:hi]
        n = np.arange(lo, hi)
        if self.axis_us.get():
            t = (n - pulse.global_peak) * SAMPLE_PERIOD_US
            xlab = "Time from peak (µs)"
        else:
            t = n.astype(float)
            xlab = "Sample index"

        self.ax_wave.plot(t, y, color="#1f4e79", lw=1.4)
        self.ax_wave.axhline(NOISE_FLOOR_CH, color="#888888", ls=":", lw=0.8, label="noise floor 50 ch")
        peak_x = 0.0 if self.axis_us.get() else float(pulse.global_peak)
        self.ax_wave.plot([peak_x], [pulse.amplitude], "o", color="#c0392b", ms=6, label=f"peak {pulse.amplitude} ch")

        trig = find_trigger(self.samples, lo, hi, level=100)
        if self.show_trigger.get() and trig is not None:
            tx = (trig - pulse.global_peak) * SAMPLE_PERIOD_US if self.axis_us.get() else float(trig)
            self.ax_wave.axvline(tx, color="#27ae60", ls="--", lw=1.0, label=f"trigger n={trig}")
            if self.show_taps.get():
                idx, vals = four_taps(self.samples, trig, int(self.stride.get()))
                txp = (idx - pulse.global_peak) * SAMPLE_PERIOD_US if self.axis_us.get() else idx.astype(float)
                self.ax_wave.plot(txp, vals, "s", color="#e67e22", ms=7, label=f"4 taps stride={self.stride.get()}")
                for xi, vi in zip(txp, vals):
                    self.ax_wave.annotate(str(int(vi)), (xi, vi), textcoords="offset points", xytext=(4, 6), fontsize=8)

        self.ax_wave.set_ylabel("ADC channel")
        self.ax_wave.set_xlabel(xlab)
        self.ax_wave.set_ylim(bottom=-20)
        self.ax_wave.grid(True, ls=":", lw=0.5, color="#aaaaaa")
        self.ax_wave.legend(loc="upper right", fontsize=8, framealpha=0.92)
        self.ax_wave.set_title(
            f"Pulse {self.index + 1} / {len(self.view)}   {pulse.segment_name}   "
            f"kind={pulse.kind}   width={pulse.width_us:.1f} µs"
        )

        self._draw_hist(pulse)
        self.canvas.draw_idle()
        self.jump_to.set(self.index + 1)

        dt = "—" if pulse.dt_prev is None else f"{pulse.dt_prev * SAMPLE_PERIOD_US:.1f} µs"
        self.info.set(
            f"#{pulse.pulse_id:04d}  {pulse.segment_name}  "
            f"local_peak={pulse.local_peak}  global={pulse.global_peak}  "
            f"A={pulse.amplitude} ch  width={pulse.width} sa ({pulse.width_us:.1f} µs)  "
            f"rise10-90={pulse.rise_us:.2f} µs  Δt_prev={dt}  "
            f"scan={'ON' if self.scanning else 'pause'}"
        )

    def _draw_hist(self, current) -> None:
        amps = [p.amplitude for p in self.view]
        self.ax_hist.set_xlabel("Peak amplitude (ADC channels)")
        self.ax_hist.set_ylabel("Pulses")
        if not amps:
            return
        lo, hi = min(amps), max(amps)
        bins = np.arange(max(0, lo - 25), hi + 50, 10)
        self.ax_hist.hist(amps, bins=bins, color="#2e86ab", edgecolor="none")
        if current is not None:
            self.ax_hist.axvline(current.amplitude, color="#c0392b", lw=1.4)
        self.ax_hist.set_xlim(0, ADC_CHANNELS)
        self.ax_hist.set_title("Peak-height histogram of the current filter")
        self.ax_hist.grid(True, ls=":", lw=0.5, color="#aaaaaa", axis="y")

    def export_pulse(self) -> None:
        pulse = self._current()
        if pulse is None or self.samples is None:
            return
        lo, hi = self._window(pulse)
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"pulse_{pulse.pulse_id:04d}_{pulse.segment_name.replace('.txt', '')}.csv",
        )
        if not path:
            return
        with Path(path).open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sample_index", "time_us_from_peak", "adc"])
            for n in range(lo, hi):
                w.writerow([n, (n - pulse.global_peak) * SAMPLE_PERIOD_US, int(self.samples[n])])
        self.status.set(f"Wrote {path}")

    def _on_close(self) -> None:
        self.pause_scan()
        self.destroy()


def main() -> None:
    app = RealDataViewer()
    app.mainloop()


if __name__ == "__main__":
    main()
