from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from .data import Operator, load_operators, refresh_data
from .images import operator_image_path
from .ocr import (
    ScanResult,
    ScreenRegion,
    scan_screen_text,
    tags_from_slot_texts,
    tags_from_text,
)
from .solver import available_tags, solve_combinations


class RecruitmentApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Arknights Recruitment Helper")
        self.geometry("1180x760")
        self.minsize(980, 620)

        self.operators: list[Operator] = []
        self.tag_vars: dict[str, tk.BooleanVar] = {}
        self.region: ScreenRegion | None = None
        self.status = tk.StringVar(value="Loading game data...")
        self.row_operators: dict[str, list[Operator]] = {}
        self.operator_tiles: list[ttk.Frame] = []
        self.operator_images: dict[str, tk.PhotoImage] = {}

        self._build_layout()
        self._load_data()

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0, minsize=330)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self, padding=12)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.rowconfigure(5, weight=1)

        ttk.Label(sidebar, text="Recruitment Tags", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        actions = ttk.Frame(sidebar)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        actions.columnconfigure((0, 1), weight=1)

        ttk.Button(actions, text="Scan Screen Tags", command=self.scan_screen).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(actions, text="Set Screen Region", command=self.pick_region).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )
        ttk.Button(actions, text="Analyze Selected Tags", command=self.analyze).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        ttk.Button(actions, text="Refresh Game Data", command=self.refresh).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        self.detected_var = tk.StringVar(value="Detected: none yet")
        ttk.Label(sidebar, textvariable=self.detected_var, wraplength=300).grid(
            row=2, column=0, sticky="ew", pady=(4, 10)
        )

        ttk.Label(sidebar, text="Scan Debug", font=("Segoe UI", 10, "bold")).grid(
            row=3, column=0, sticky="w", pady=(0, 4)
        )
        self.debug_text = tk.Text(sidebar, height=10, width=38, wrap="word")
        self.debug_text.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self.debug_text.insert("1.0", "No scan yet.")
        self.debug_text.configure(state="disabled")

        tag_canvas = tk.Canvas(sidebar, highlightthickness=0)
        tag_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=tag_canvas.yview)
        self.tag_frame = ttk.Frame(tag_canvas)
        self.tag_frame.bind(
            "<Configure>",
            lambda _event: tag_canvas.configure(scrollregion=tag_canvas.bbox("all")),
        )
        tag_canvas.create_window((0, 0), window=self.tag_frame, anchor="nw")
        tag_canvas.configure(yscrollcommand=tag_scroll.set)
        tag_canvas.grid(row=5, column=0, sticky="nsew")
        tag_scroll.grid(row=5, column=1, sticky="ns")

        main = ttk.Frame(self, padding=(0, 12, 12, 12))
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        ttk.Label(main, text="Possible Outcomes", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        columns = ("tags", "lowest", "count", "operators")
        self.tree = ttk.Treeview(main, columns=columns, show="headings")
        self.tree.heading("tags", text="Tags")
        self.tree.heading("lowest", text="Lowest")
        self.tree.heading("count", text="Count")
        self.tree.heading("operators", text="Operators")
        self.tree.column("tags", width=250, anchor="w")
        self.tree.column("lowest", width=80, anchor="center")
        self.tree.column("count", width=70, anchor="center")
        self.tree.column("operators", width=560, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_outcome_selected)

        tree_scroll = ttk.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=1, column=1, sticky="ns")

        preview = ttk.Frame(main)
        preview.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        preview.columnconfigure(0, weight=1)
        ttk.Label(preview, text="Operator Preview", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.preview_canvas = tk.Canvas(preview, height=124, highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="ew")
        preview_scroll = ttk.Scrollbar(
            preview,
            orient="horizontal",
            command=self.preview_canvas.xview,
        )
        preview_scroll.grid(row=2, column=0, sticky="ew")
        self.preview_frame = ttk.Frame(self.preview_canvas)
        self.preview_frame.bind(
            "<Configure>",
            lambda _event: self.preview_canvas.configure(
                scrollregion=self.preview_canvas.bbox("all")
            ),
        )
        self.preview_canvas.create_window((0, 0), window=self.preview_frame, anchor="nw")
        self.preview_canvas.configure(xscrollcommand=preview_scroll.set)

        ttk.Label(main, textvariable=self.status).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _load_data(self) -> None:
        self._run_background(self._load_data_worker)

    def _load_data_worker(self) -> None:
        try:
            operators = load_operators()
        except Exception as exc:
            self._show_error_later("Could not load game data", exc)
            return
        self.after(0, lambda: self._set_operators(operators))

    def _set_operators(self, operators: list[Operator]) -> None:
        self.operators = operators
        self._render_tags()
        self.status.set(f"Loaded {len(operators)} recruitable operators.")

    def _render_tags(self) -> None:
        for child in self.tag_frame.winfo_children():
            child.destroy()

        self.tag_vars.clear()
        for index, tag in enumerate(available_tags(self.operators)):
            var = tk.BooleanVar(value=False)
            self.tag_vars[tag] = var
            ttk.Checkbutton(
                self.tag_frame,
                text=tag,
                variable=var,
                command=self.analyze,
            ).grid(row=index, column=0, sticky="w", pady=1)

    def scan_screen(self) -> None:
        self.status.set("Scanning screen...")
        self._run_background(self._scan_screen_worker)

    def _scan_screen_worker(self) -> None:
        try:
            scan = scan_screen_text(self.region)
            tags = tags_from_slot_texts(scan.button_texts, self.tag_vars.keys())
            if not tags:
                tags = tags_from_text(scan.text, self.tag_vars.keys())
        except Exception as exc:
            self._show_error_later("Could not scan the screen", exc)
            return
        self.after(0, lambda: self._apply_scan_result(scan, tags))

    def _apply_scan_result(self, scan: ScanResult, tags: list[str]) -> None:
        self._set_scan_debug(scan, tags)
        self._apply_detected_tags(tags)

    def _apply_detected_tags(self, tags: list[str]) -> None:
        for var in self.tag_vars.values():
            var.set(False)
        for tag in tags:
            if tag in self.tag_vars:
                self.tag_vars[tag].set(True)

        self.detected_var.set("Detected: " + (", ".join(tags) if tags else "none"))
        self.status.set(f"Detected {len(tags)} tag(s).")
        self.analyze()

    def analyze(self) -> None:
        selected = [tag for tag, var in self.tag_vars.items() if var.get()]
        self.row_operators.clear()
        self._clear_operator_preview()
        for row in self.tree.get_children():
            self.tree.delete(row)

        if not selected:
            self.status.set("Select or scan tags to see possible outcomes.")
            return

        results = solve_combinations(selected, self.operators)
        for combo, operators in results:
            lowest = min(operator.rarity for operator in operators)
            names = ", ".join(f"{op.name} ({op.rarity_label})" for op in operators)
            row_id = self.tree.insert(
                "",
                "end",
                values=(
                    " + ".join(combo),
                    f"{lowest + 1}★+",
                    str(len(operators)),
                    names,
                ),
            )
            self.row_operators[row_id] = operators

        self.status.set(f"Found {len(results)} matching tag combination(s).")
        rows = self.tree.get_children()
        if rows:
            self.tree.selection_set(rows[0])
            self._show_operator_preview(self.row_operators[rows[0]])

    def _on_outcome_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self._show_operator_preview(self.row_operators.get(selection[0], []))

    def _show_operator_preview(self, operators: list[Operator]) -> None:
        self._clear_operator_preview()
        for index, operator in enumerate(operators):
            tile = ttk.Frame(self.preview_frame, padding=(4, 2))
            tile.grid(row=0, column=index, sticky="n", padx=(0, 6))

            image_label = ttk.Label(tile, text="Loading", anchor="center", width=10)
            image_label.grid(row=0, column=0)
            ttk.Label(tile, text=operator.name, width=12, anchor="center").grid(
                row=1, column=0
            )
            ttk.Label(tile, text=operator.rarity_label, anchor="center").grid(
                row=2, column=0
            )

            self.operator_tiles.append(tile)
            self._load_operator_image_later(operator, image_label)

    def _clear_operator_preview(self) -> None:
        for tile in self.operator_tiles:
            tile.destroy()
        self.operator_tiles.clear()

    def _load_operator_image_later(self, operator: Operator, label: ttk.Label) -> None:
        cached = self.operator_images.get(operator.id)
        if cached:
            label.configure(image=cached, text="")
            return

        def worker() -> None:
            path = operator_image_path(operator)
            self.after(0, lambda: self._apply_operator_image(operator, label, path))

        self._run_background(worker)

    def _apply_operator_image(self, operator: Operator, label: ttk.Label, path) -> None:
        if not label.winfo_exists():
            return
        if not path:
            label.configure(text="No image")
            return
        try:
            image = self._photo_image_from_path(path)
        except Exception:
            label.configure(text="No image")
            return

        self.operator_images[operator.id] = image
        label.configure(image=image, text="")

    def _photo_image_from_path(self, path) -> tk.PhotoImage:
        from PIL import Image, ImageTk

        image = Image.open(path).convert("RGBA")
        image = _avatar_thumbnail(image)
        return ImageTk.PhotoImage(image)

    def pick_region(self) -> None:
        selector = RegionSelector(self, self._set_region)
        selector.focus_force()

    def _set_region(self, region: ScreenRegion) -> None:
        self.region = region
        self.status.set(
            f"Screen region set: left {region.left}, top {region.top}, "
            f"{region.width}x{region.height}."
        )

    def refresh(self) -> None:
        self.status.set("Refreshing game data...")
        self._run_background(self._refresh_worker)

    def _refresh_worker(self) -> None:
        try:
            refresh_data()
            operators = load_operators()
        except Exception as exc:
            self._show_error_later("Could not refresh game data", exc)
            return
        self.after(0, lambda: self._set_operators(operators))

    def _show_error_later(self, title: str, exc: Exception) -> None:
        message = str(exc)
        self.after(0, lambda: self._show_error(title, message))

    def _show_error(self, title: str, message: str) -> None:
        self.status.set(f"{title}: {message}")

    def _set_scan_debug(self, scan: ScanResult, tags: list[str]) -> None:
        text = (
            f"Capture: {scan.capture_area}\n"
            f"Screen size: {scan.screen_size[0]}x{scan.screen_size[1]}\n"
            f"Image size: {scan.image_size[0]}x{scan.image_size[1]}\n"
            f"Saved image: {scan.image_path}\n"
            f"Detected tags: {', '.join(tags) if tags else 'none'}\n"
            f"Tag slot OCR: {', '.join(scan.button_texts) if scan.button_texts else 'none'}\n"
            f"Tag slot boxes: {'; '.join(scan.button_boxes) if scan.button_boxes else 'none'}\n"
            "\nRaw OCR text:\n"
            f"{scan.text.strip() or '(empty)'}"
        )
        self.debug_text.configure(state="normal")
        self.debug_text.delete("1.0", "end")
        self.debug_text.insert("1.0", text)
        self.debug_text.configure(state="disabled")

    def _run_background(self, target) -> None:
        threading.Thread(target=target, daemon=True).start()


class RegionSelector(tk.Toplevel):
    def __init__(self, parent: tk.Tk, callback) -> None:
        super().__init__(parent)
        self.callback = callback
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.25)
        self.configure(background="black")
        self.start_x = 0
        self.start_y = 0
        self.rect: int | None = None

        self.canvas = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._start)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish)
        self.bind("<Escape>", lambda _event: self.destroy())

    def _start(self, event) -> None:
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.rect = self.canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="white",
            width=3,
        )

    def _drag(self, event) -> None:
        if self.rect is not None:
            self.canvas.coords(
                self.rect,
                self.start_x,
                self.start_y,
                event.x_root,
                event.y_root,
            )

    def _finish(self, event) -> None:
        left = min(self.start_x, event.x_root)
        top = min(self.start_y, event.y_root)
        width = abs(event.x_root - self.start_x)
        height = abs(event.y_root - self.start_y)
        self.destroy()
        if width > 10 and height > 10:
            self.callback(ScreenRegion(left, top, width, height))


def _avatar_thumbnail(image):
    from PIL import Image, ImageOps

    width, height = image.size
    if height > width:
        top = 0
        bottom = min(height, int(width * 1.15))
        image = image.crop((0, top, width, bottom))
    image = ImageOps.fit(image, (72, 72), method=Image.Resampling.LANCZOS)
    return image


def main() -> None:
    app = RecruitmentApp()
    app.mainloop()
