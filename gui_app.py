"""Tkinter GUI for the rotation-period measurement pipeline."""

from __future__ import annotations

import copy
import ctypes
import datetime as dt
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pipeline


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "configs" / "pipeline_example.json"
STATE_DIR = ROOT / ".gui_state"
STATE_PATH = STATE_DIR / "pipeline_gui_state.json"
HISTORY_PATH = STATE_DIR / "history.json"
PREVIEW_DIR = STATE_DIR / "previews"
STAGES = ("observation", "echo", "inversion")
STAGE_LABELS = {
    "observation": "1. 观测解算",
    "echo": "2. 回波仿真",
    "inversion": "3. 周期反演",
}
GROUP_LABELS = {
    "target": "目标参数",
    "transmitter": "发射站",
    "receiver": "接收站",
    "receive": "接收设置",
    "solver": "求解器",
    "compute": "计算设置",
    "scattering_spot": "散射热点",
    "radar": "雷达参数",
    "waveform": "波形参数",
}
CHOICES = {
    "state": ("static", "linear", "geodetic_fixed", "astropy_geodetic", "horizons_vectors"),
    "device": ("auto", "cuda:0", "cpu"),
    "dtype": ("float32", "float64"),
    "type": ("continuous_wave",),
}
STATE_FIELDS = {
    "static": ("position_m",),
    "linear": ("position0_m", "velocity_m_s"),
    "geodetic_fixed": ("lat_deg", "lon_deg", "height_m"),
    "astropy_geodetic": ("lat_deg", "lon_deg", "height_m"),
    "horizons_vectors": ("id", "object_type", "location", "refplane", "query_step_s", "padding_s"),
}
STATE_DEFAULTS = {
    "position_m": [0.0, 0.0, 0.0],
    "position0_m": [0.0, 0.0, 0.0],
    "velocity_m_s": [0.0, 0.0, 0.0],
    "lat_deg": 0.0,
    "lon_deg": 0.0,
    "height_m": 0.0,
    "object_type": None,
    "location": "@399",
    "refplane": "earth",
    "query_step_s": 60.0,
    "padding_s": 7200.0,
}
COMMON_FIELD_ORDER = ("id", "name", "state")
DPI_AWARENESS_SET = False


def enable_dpi_awareness() -> None:
    """Avoid blurry bitmap scaling on high-DPI Windows displays."""

    global DPI_AWARENESS_SET
    if DPI_AWARENESS_SET or sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    DPI_AWARENESS_SET = True


def read_json(path: Path, fallback):
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是有效 JSON：{exc}") from exc


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_value(raw: str):
    text = raw.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw


def format_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flatten(prefix: str, value):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            yield from flatten(child_prefix, child)
    else:
        yield prefix, value


def assign_path(payload: dict, dotted_path: str, value) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


class ScrollFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.inner = ttk.Frame(self.canvas)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._sync_scroll_region)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _sync_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -int(event.delta / 120)
        self.canvas.yview_scroll(delta, "units")


class PipelineGui(tk.Tk):
    def __init__(self):
        enable_dpi_awareness()
        super().__init__()
        self.title("自转周期测量流水线")
        self.geometry("1280x820")
        self.minsize(1060, 680)

        self.config_path = DEFAULT_CONFIG_PATH
        self.config_data = self._load_initial_config()
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self.field_vars: dict[str, tk.StringVar] = {}
        self.preview_photo = None
        self.preview_source_path: Path | None = None
        self.preview_source_image = None
        self.preview_resize_after_id = None
        self.latest_image_path: Path | None = None
        self.latest_plotly_path: Path | None = None
        self.latest_result_path: Path | None = None
        self.command_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.run_name_var = tk.StringVar(value=self._default_run_name())
        self.runs_dir_var = tk.StringVar(value="runs")
        self.python_var = tk.StringVar(value=sys.executable)
        self.config_path_var = tk.StringVar(value=str(self.config_path))
        self.status_var = tk.StringVar(value="就绪")

        self._build_ui()
        self._render_stage_buttons()
        self._render_current_stage()
        self._render_history()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._drain_command_queue)

    def _load_initial_config(self):
        disk_config = read_json(DEFAULT_CONFIG_PATH, pipeline.DEFAULT_CONFIG)
        state = read_json(STATE_PATH, {})
        if isinstance(state, dict) and isinstance(state.get("config"), dict):
            return state["config"]
        return disk_config

    def _default_run_name(self) -> str:
        return self.config_path.stem if self.config_path else "pipeline_gui"

    def _build_ui(self) -> None:
        self._setup_style()
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="配置文件").grid(row=0, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.config_path_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(header, text="打开", command=self._choose_config).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(header, text="载入", command=self._load_config_from_entry).grid(row=0, column=3)

        runbar = ttk.Frame(self, padding=(14, 0, 14, 8))
        runbar.grid(row=1, column=0, columnspan=2, sticky="new")
        runbar.columnconfigure(1, weight=1)
        runbar.columnconfigure(3, weight=1)
        ttk.Label(runbar, text="实验名").grid(row=0, column=0, sticky="w")
        ttk.Entry(runbar, textvariable=self.run_name_var, width=28).grid(row=0, column=1, sticky="ew", padx=(8, 18))
        ttk.Label(runbar, text="输出目录").grid(row=0, column=2, sticky="w")
        ttk.Entry(runbar, textvariable=self.runs_dir_var, width=18).grid(row=0, column=3, sticky="ew", padx=(8, 18))
        ttk.Label(runbar, text="Python").grid(row=0, column=4, sticky="w")
        ttk.Entry(runbar, textvariable=self.python_var, width=28).grid(row=0, column=5, sticky="ew", padx=(8, 0))

        content_pane = self._paned_window(self, orient=tk.HORIZONTAL)
        content_pane.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(14, 14), pady=(8, 12))

        sidebar = ttk.Frame(content_pane, padding=(0, 0, 8, 0))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(4, weight=1)
        self.stage_button_frame = ttk.LabelFrame(sidebar, text="流水线阶段", padding=8)
        self.stage_button_frame.grid(row=0, column=0, sticky="ew")
        self.next_button = ttk.Button(sidebar, text="执行下一步", command=self._run_current_stage, style="Accent.TButton")
        self.next_button.grid(row=1, column=0, sticky="ew", pady=(12, 6))
        ttk.Button(sidebar, text="保存参数", command=self._save_current_config).grid(row=2, column=0, sticky="ew")
        ttk.Button(sidebar, text="另存 JSON", command=self._save_config_as_json).grid(row=3, column=0, sticky="ew", pady=(6, 0))

        self.history_tree = ttk.Treeview(sidebar, columns=("time", "stage", "status"), show="headings", height=15)
        self.history_tree.heading("time", text="时间")
        self.history_tree.heading("stage", text="阶段")
        self.history_tree.heading("status", text="状态")
        self.history_tree.column("time", width=132, anchor="w")
        self.history_tree.column("stage", width=86, anchor="w")
        self.history_tree.column("status", width=64, anchor="center", stretch=True)
        self.history_tree.grid(row=4, column=0, sticky="nsew", pady=(12, 0))

        main = ttk.Frame(content_pane, padding=(8, 0, 0, 0))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        content_pane.add(sidebar, minsize=240, stretch="never")
        content_pane.add(main, minsize=640, stretch="always")

        vertical_pane = self._paned_window(main, orient=tk.VERTICAL)
        vertical_pane.grid(row=0, column=0, sticky="nsew")

        self.params_frame = ttk.LabelFrame(vertical_pane, text="阶段参数", padding=8)
        self.params_frame.columnconfigure(0, weight=1)
        self.params_scroll = ScrollFrame(self.params_frame)
        self.params_scroll.grid(row=0, column=0, sticky="nsew")
        self.params_frame.rowconfigure(0, weight=1)

        bottom = self._paned_window(vertical_pane, orient=tk.HORIZONTAL)
        vertical_pane.add(self.params_frame, minsize=260, stretch="always")
        vertical_pane.add(bottom, minsize=220, stretch="always")

        log_frame = ttk.LabelFrame(bottom, text="执行日志", padding=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

        preview_frame = ttk.LabelFrame(bottom, text="结果预览", padding=8)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)
        result_actions = ttk.Frame(preview_frame)
        result_actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        result_actions.columnconfigure(0, weight=1)
        self.result_status_var = tk.StringVar(value="执行阶段后会在这里显示关键结果。")
        ttk.Label(result_actions, textvariable=self.result_status_var).grid(row=0, column=0, sticky="w")
        self.open_result_button = ttk.Button(result_actions, text="打开结果", command=self._open_latest_result, state="disabled")
        self.open_result_button.grid(row=0, column=1, padx=(8, 0))
        self.open_plotly_button = ttk.Button(result_actions, text="打开 3D", command=self._open_plotly, state="disabled")
        self.open_plotly_button.grid(row=0, column=2, padx=(8, 0))
        self.result_canvas = tk.Canvas(preview_frame, height=260, borderwidth=0, highlightthickness=0)
        self.result_canvas.grid(row=1, column=0, sticky="nsew")
        self.result_canvas.bind("<Configure>", lambda _event: self._schedule_display_latest_image())

        bottom.add(log_frame, minsize=320, stretch="always")
        bottom.add(preview_frame, minsize=320, stretch="always")

        footer = ttk.Frame(self, padding=(14, 0, 14, 10))
        footer.grid(row=3, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self._draw_result_placeholder("执行阶段后会在这里显示关键结果。")

    def _paned_window(self, master, orient):
        return tk.PanedWindow(
            master,
            orient=orient,
            opaqueresize=False,
            sashwidth=7,
            sashrelief=tk.FLAT,
            borderwidth=0,
            showhandle=False,
        )

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        for theme in ("vista", "xpnative", "winnative"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        try:
            self.tk.call("tk", "scaling", max(1.0, self.winfo_fpixels("1i") / 72.0))
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", padding=(10, 5))
        style.configure("Accent.TButton", padding=(12, 8), font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Treeview", rowheight=28)

    def _render_stage_buttons(self) -> None:
        for child in self.stage_button_frame.winfo_children():
            child.destroy()
        for index, stage in enumerate(STAGES):
            text = f"{STAGE_LABELS[stage]}  {self.stage_status[stage]}"
            button = ttk.Button(
                self.stage_button_frame,
                text=text,
                command=lambda value=stage: self._select_stage(value),
            )
            button.grid(row=index, column=0, sticky="ew", pady=3)

    def _render_current_stage(self) -> None:
        for child in self.params_scroll.inner.winfo_children():
            child.destroy()
        self.field_vars.clear()

        stage_data = self.config_data.get(self.current_stage, {})
        groups = self._stage_groups(stage_data)
        for index, (group_name, values) in enumerate(groups):
            frame = ttk.LabelFrame(
                self.params_scroll.inner,
                text=GROUP_LABELS.get(group_name, group_name),
                padding=(10, 8),
            )
            frame.grid(row=index, column=0, sticky="nsew", padx=6, pady=6)
            self._render_group_fields(frame, group_name, values)

        self.params_scroll.inner.columnconfigure(0, weight=1)
        self.params_frame.configure(text=f"{STAGE_LABELS[self.current_stage]} 参数")

    def _stage_groups(self, stage_data: dict):
        groups = []
        loose = {}
        for key, value in stage_data.items():
            if isinstance(value, dict):
                groups.append((key, value))
            else:
                loose[key] = value
        if loose:
            groups.insert(0, ("通用参数", loose))
        return groups

    def _render_group_fields(self, frame: ttk.LabelFrame, group_name: str, values: dict) -> None:
        fields = self._ordered_group_fields(values)
        row = 0
        compact_col = 0
        for relative_path, value in fields:
            label_text = relative_path.split(".")[-1]
            full_path = relative_path if group_name == "通用参数" else f"{group_name}.{relative_path}"
            var = tk.StringVar(value=format_value(value))
            widget = self._field_widget(frame, full_path, var, value)
            self.field_vars[full_path] = var

            wide = self._is_wide_field(relative_path, value)
            if wide:
                if compact_col:
                    row += 1
                    compact_col = 0
                ttk.Label(frame, text=label_text).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
                widget.grid(row=row, column=1, columnspan=3, sticky="ew", padx=(0, 6), pady=4)
                row += 1
            else:
                col = compact_col * 2
                ttk.Label(frame, text=label_text).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
                widget.grid(row=row, column=col + 1, sticky="ew", padx=(0, 14), pady=4)
                compact_col += 1
                if compact_col >= 2:
                    compact_col = 0
                    row += 1

        frame.columnconfigure(1, weight=1, minsize=300)
        frame.columnconfigure(3, weight=1, minsize=220)

    def _ordered_group_fields(self, values: dict):
        flat = dict(flatten("", values))
        ordered = []
        for key in COMMON_FIELD_ORDER:
            if key in flat:
                ordered.append((key, flat.pop(key)))
        state = values.get("state")
        if state in STATE_FIELDS:
            for key in STATE_FIELDS[state]:
                if key in flat:
                    ordered.append((key, flat.pop(key)))
        for key, value in flat.items():
            ordered.append((key, value))
        return ordered

    def _is_wide_field(self, relative_path: str, value) -> bool:
        key = relative_path.split(".")[-1]
        return isinstance(value, list) or key.endswith("_utc") or key in {
            "position_m",
            "position0_m",
            "velocity_m_s",
            "spin_pole_icrs_deg",
            "direction_body",
            "model_path",
            "observation_info_path",
        }

    def _field_widget(self, parent, full_path: str, var: tk.StringVar, value):
        key = full_path.split(".")[-1]
        if isinstance(value, bool):
            widget = ttk.Combobox(parent, textvariable=var, values=("true", "false"), state="readonly", width=18)
            var.set("true" if value else "false")
            return widget
        if key in CHOICES:
            values = self._choices_for_field(full_path)
            if str(value) not in values:
                values = (str(value), *values)
            widget = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=22)
            if key == "state":
                widget.bind("<<ComboboxSelected>>", lambda _event, path=full_path: self._on_state_changed(path))
            return widget
        width = 44 if self._is_wide_field(full_path, value) else 24
        return ttk.Entry(parent, textvariable=var, width=width)

    def _choices_for_field(self, full_path: str) -> tuple[str, ...]:
        key = full_path.split(".")[-1]
        if key != "state":
            return CHOICES[key]
        group_name = full_path.split(".")[0]
        if self.current_stage == "observation" and group_name == "target":
            return ("linear", "static", "horizons_vectors")
        if self.current_stage == "observation" and group_name in {"transmitter", "receiver"}:
            return ("static", "geodetic_fixed", "astropy_geodetic", "linear")
        return CHOICES[key]

    def _render_history(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        history = read_json(HISTORY_PATH, [])
        for record in reversed(history[-80:]):
            self.history_tree.insert(
                "",
                "end",
                values=(record.get("time", ""), STAGE_LABELS.get(record.get("stage"), record.get("stage", "")), record.get("status", "")),
            )

    def _choose_config(self) -> None:
        filename = filedialog.askopenfilename(
            title="选择 pipeline JSON 配置",
            initialdir=str(ROOT / "configs"),
            filetypes=(("JSON", "*.json"), ("全部文件", "*.*")),
        )
        if filename:
            self.config_path_var.set(filename)
            self._load_config_from_entry()

    def _load_config_from_entry(self) -> None:
        path = Path(self.config_path_var.get()).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        try:
            data = read_json(path, {})
            pipeline.require_sections(data)
        except Exception as exc:
            messagebox.showerror("载入失败", str(exc))
            return
        self.config_path = path
        self.config_data = data
        self.run_name_var.set(path.stem)
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self._render_stage_buttons()
        self._render_current_stage()
        self._save_state()
        self._append_log(f"[{now_text()}] 已载入配置：{path}")

    def _select_stage(self, stage: str) -> None:
        self._sync_stage_from_fields()
        self.current_stage = stage
        self._render_current_stage()

    def _on_state_changed(self, full_path: str) -> None:
        self._sync_stage_from_fields()
        parts = full_path.split(".")
        if len(parts) < 2:
            return
        group_name = parts[0]
        group = self.config_data.get(self.current_stage, {}).get(group_name)
        if not isinstance(group, dict):
            return
        self.config_data[self.current_stage][group_name] = self._normalize_state_group(group)
        self._save_state()
        self._render_current_stage()

    def _normalize_state_group(self, group: dict) -> dict:
        state = group.get("state", "static")
        if state not in STATE_FIELDS:
            return group

        all_state_fields = set()
        for fields in STATE_FIELDS.values():
            all_state_fields.update(fields)
        all_state_fields.discard("id")

        normalized = {}
        for key in COMMON_FIELD_ORDER:
            if key in group:
                normalized[key] = group[key]
        normalized["state"] = state

        for key in STATE_FIELDS[state]:
            normalized[key] = self._state_field_value(key, group)

        for key, value in group.items():
            if key in normalized or key in all_state_fields:
                continue
            normalized[key] = value
        return normalized

    def _state_field_value(self, key: str, group: dict):
        if key in group:
            return group[key]
        if key == "position_m" and "position0_m" in group:
            return group["position0_m"]
        if key == "position0_m" and "position_m" in group:
            return group["position_m"]
        if key == "id" and "name" in group:
            return group["name"]
        return copy.deepcopy(STATE_DEFAULTS.get(key, ""))

    def _sync_stage_from_fields(self) -> None:
        stage_payload = {}
        for path, var in self.field_vars.items():
            assign_path(stage_payload, path, parse_value(var.get()))
        self.config_data[self.current_stage] = stage_payload

    def _save_current_config(self) -> None:
        try:
            self._sync_stage_from_fields()
            self._save_state()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self._append_log(f"[{now_text()}] 参数已保存，下次打开会使用当前值。")
        self.status_var.set("参数已保存")

    def _save_config_as_json(self) -> None:
        try:
            self._sync_stage_from_fields()
            pipeline.require_sections(self.config_data)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        default_name = f"{self.run_name_var.get().strip() or self.config_path.stem}.json"
        filename = filedialog.asksaveasfilename(
            title="将当前参数保存为 JSON",
            initialdir=str(ROOT / "configs"),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("全部文件", "*.*")),
        )
        if not filename:
            return

        path = Path(filename)
        try:
            write_json(path, self.config_data)
            self.config_path = path
            self.config_path_var.set(str(path))
            self.run_name_var.set(path.stem)
            self._save_state()
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return

        self._append_log(f"[{now_text()}] 当前参数已另存为：{path}")
        self.status_var.set(f"已保存 JSON：{path}")

    def _save_state(self) -> None:
        write_json(
            STATE_PATH,
            {
                "config_path": str(self.config_path),
                "config": self.config_data,
                "saved_at": now_text(),
            },
        )

    def _validate_role_states(self) -> None:
        observation = self.config_data.get("observation", {})
        target_state = observation.get("target", {}).get("state")
        if target_state not in {"linear", "static", "horizons_vectors"}:
            raise ValueError(
                "target.state 不应设置为 geodetic_fixed/astropy_geodetic。"
                "这些状态表示地面测站；目标建议使用 linear、static 或 horizons_vectors。"
            )
        station_allowed = {"static", "geodetic_fixed", "astropy_geodetic", "linear"}
        for role in ("transmitter", "receiver"):
            state = observation.get(role, {}).get("state")
            if state not in station_allowed:
                raise ValueError(f"{role}.state 当前不支持 {state}，请使用 static/geodetic_fixed/astropy_geodetic/linear。")

    def _on_close(self) -> None:
        try:
            if self.preview_resize_after_id is not None:
                self.after_cancel(self.preview_resize_after_id)
                self.preview_resize_after_id = None
            if self.preview_source_image is not None:
                self.preview_source_image.close()
            self._sync_stage_from_fields()
            self._save_state()
        except Exception:
            pass
        self.destroy()

    def _run_current_stage(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("正在执行", "当前已有阶段在执行，请等待完成。")
            return
        try:
            self._sync_stage_from_fields()
            pipeline.require_sections(self.config_data)
            self._validate_role_states()
            self._save_state()
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        stage = self.current_stage
        run_name = self.run_name_var.get().strip() or self.config_path.stem
        runs_dir = self.runs_dir_var.get().strip() or "runs"
        python_exe = self.python_var.get().strip() or sys.executable
        self.stage_status[stage] = "执行中"
        self._render_stage_buttons()
        self.next_button.configure(state="disabled")
        self.status_var.set(f"正在执行：{STAGE_LABELS[stage]}")
        self._append_log(f"\n[{now_text()}] 开始执行 {STAGE_LABELS[stage]}")

        self.worker = threading.Thread(
            target=self._run_stage_worker,
            args=(stage, run_name, runs_dir, python_exe, copy.deepcopy(self.config_data)),
            daemon=True,
        )
        self.worker.start()

    def _run_stage_worker(self, stage: str, run_name: str, runs_dir: str, python_exe: str, config_data: dict) -> None:
        try:
            run_dir = pipeline.abs_path(runs_dir) / run_name
            config_dir = run_dir / "configs"
            prepared = pipeline.prepared_configs(config_data, run_dir)
            write_json(config_dir / "experiment.json", config_data)
            write_json(config_dir / "observation.generated.json", prepared["observation"])
            write_json(config_dir / "echo.generated.json", prepared["echo"])
            write_json(config_dir / "inversion.generated.json", prepared["inversion"])

            command, cwd, env = self._stage_command(stage, python_exe, config_dir, prepared)
            self.command_queue.put(("log", f"命令：{' '.join(map(str, command))}\n工作目录：{cwd}"))
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.command_queue.put(("log", line.rstrip()))
            code = process.wait()
            if code != 0:
                raise RuntimeError(f"{STAGE_LABELS[stage]} 失败，退出码 {code}")
            self.command_queue.put(("done", json.dumps({"stage": stage, "run_dir": str(run_dir)}, ensure_ascii=False)))
        except Exception as exc:
            self.command_queue.put(("failed", json.dumps({"stage": stage, "error": str(exc)}, ensure_ascii=False)))

    def _stage_command(self, stage: str, python_exe: str, config_dir: Path, prepared: dict):
        env = None
        if stage == "observation":
            return (
                [
                    python_exe,
                    "solve_observation_info.py",
                    "--config",
                    str(config_dir / "observation.generated.json"),
                    "--output",
                    str(prepared["observation_output"]),
                ],
                ROOT / "observation",
                env,
            )
        if stage == "echo":
            return (
                [
                    python_exe,
                    "simulate_echo.py",
                    "--config",
                    str(config_dir / "echo.generated.json"),
                    "--output",
                    str(prepared["echo_output_dir"]),
                ],
                ROOT / "echo",
                env,
            )
        env = os.environ.copy()
        inversion_src = str(ROOT / "inversion" / "src")
        env["PYTHONPATH"] = inversion_src + os.pathsep + env.get("PYTHONPATH", "")
        return (
            [
                python_exe,
                "scripts/estimate_period.py",
                "--echo",
                str(prepared["echo_output_dir"] / "echo.npz"),
                "--config",
                str(config_dir / "inversion.generated.json"),
                "--output",
                str(prepared["inversion_output_dir"]),
            ],
            ROOT / "inversion",
            env,
        )

    def _drain_command_queue(self) -> None:
        try:
            while True:
                kind, payload = self.command_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "done":
                    data = json.loads(payload)
                    self._handle_stage_done(data["stage"], data["run_dir"])
                elif kind == "failed":
                    data = json.loads(payload)
                    self._handle_stage_failed(data["stage"], data["error"])
        except queue.Empty:
            pass
        self.after(120, self._drain_command_queue)

    def _handle_stage_done(self, stage: str, run_dir: str) -> None:
        self.stage_status[stage] = "完成"
        self._append_history(stage, "成功", run_dir, "")
        self._update_result_preview(stage, Path(run_dir))
        next_stage = self._next_stage(stage)
        if next_stage:
            self.current_stage = next_stage
            self.status_var.set(f"{STAGE_LABELS[stage]} 完成，已切换到 {STAGE_LABELS[next_stage]}")
            self._render_current_stage()
        else:
            self.status_var.set(f"全部阶段已完成。实验目录：{run_dir}")
        self.next_button.configure(state="normal")
        self._render_stage_buttons()
        self._render_history()
        self._append_log(f"[{now_text()}] {STAGE_LABELS[stage]} 完成。实验目录：{run_dir}")

    def _handle_stage_failed(self, stage: str, error: str) -> None:
        self.stage_status[stage] = "失败"
        self._append_history(stage, "失败", "", error)
        self.next_button.configure(state="normal")
        self.status_var.set(f"{STAGE_LABELS[stage]} 失败")
        self._render_stage_buttons()
        self._render_history()
        self._append_log(f"[{now_text()}] {STAGE_LABELS[stage]} 失败：{error}")
        messagebox.showerror("执行失败", error)

    def _append_history(self, stage: str, status: str, run_dir: str, error: str) -> None:
        history = read_json(HISTORY_PATH, [])
        history.append(
            {
                "time": now_text(),
                "stage": stage,
                "status": status,
                "run_name": self.run_name_var.get().strip(),
                "run_dir": run_dir,
                "error": error,
            }
        )
        write_json(HISTORY_PATH, history[-300:])

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _update_result_preview(self, stage: str, run_dir: Path) -> None:
        try:
            image_path, result_path, plotly_path, message = self._create_stage_preview(stage, run_dir)
        except Exception as exc:
            self.latest_image_path = None
            self.latest_result_path = run_dir
            self.latest_plotly_path = None
            self.result_status_var.set(f"结果预览生成失败：{exc}")
            self._draw_result_placeholder("结果已生成，但预览图创建失败。")
            self._append_log(f"[{now_text()}] 结果预览生成失败：{exc}")
            return

        self.latest_image_path = image_path
        self.preview_source_path = None
        self.preview_source_image = None
        self.latest_result_path = result_path
        self.latest_plotly_path = plotly_path
        self.open_result_button.configure(state="normal" if result_path else "disabled")
        self.open_plotly_button.configure(state="normal" if plotly_path else "disabled")
        self.result_status_var.set(message)
        self._schedule_display_latest_image(delay_ms=0)

    def _create_stage_preview(self, stage: str, run_dir: Path):
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = run_dir.name.replace(" ", "_")
        preview_dir = PREVIEW_DIR / safe_name
        preview_dir.mkdir(parents=True, exist_ok=True)
        if stage == "observation":
            image_path = preview_dir / "observation_preview.png"
            html_path = preview_dir / "observation_3d.html"
            result_path = run_dir / "observation_info.npz"
            self._make_observation_preview(result_path, image_path, html_path)
            return image_path, result_path, html_path, "观测解算完成：已生成距离/视线预览和可拖动 3D 画布。"
        if stage == "echo":
            image_path = preview_dir / "echo_preview.png"
            result_path = run_dir / "echo" / "echo.npz"
            self._make_echo_preview(result_path, image_path)
            return image_path, result_path, None, "回波仿真完成：已生成 I/Q、幅度与相位预览。"
        image_path = run_dir / "inversion" / "periodogram.png"
        result_path = run_dir / "inversion" / "summary.json"
        return image_path, result_path, None, "周期反演完成：已显示 periodogram，可打开 summary 查看候选周期。"

    def _make_observation_preview(self, npz_path: Path, image_path: Path, html_path: Path) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import plotly.graph_objects as go

        data = np.load(npz_path, allow_pickle=True)
        elapsed = data["elapsed_s"]
        tx_range_km = data["tx_range_m"] / 1000.0
        rx_range_km = data["rx_range_m"] / 1000.0
        tx_los = data["tx_los_icrs"]
        rx_los = data["rx_los_icrs"]

        fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.5), sharex=True)
        axes[0].plot(elapsed, tx_range_km, label="tx range", linewidth=1.4)
        axes[0].plot(elapsed, rx_range_km, label="rx range", linewidth=1.4, linestyle="--")
        axes[0].set_ylabel("Range (km)")
        axes[0].legend(loc="best")
        axes[1].plot(elapsed, tx_los[:, 1], label="tx y", linewidth=1.2)
        axes[1].plot(elapsed, rx_los[:, 1], label="rx y", linewidth=1.2, linestyle="--")
        axes[1].set_xlabel("Elapsed (s)")
        axes[1].set_ylabel("LOS y")
        axes[1].legend(loc="best")
        fig.tight_layout()
        fig.savefig(image_path, dpi=150)
        plt.close(fig)

        stride = max(1, len(elapsed) // 800)
        tx_pos = tx_los[::stride] * tx_range_km[::stride, None]
        rx_pos = rx_los[::stride] * rx_range_km[::stride, None]
        plot = go.Figure()
        plot.add_trace(
            go.Scatter3d(
                x=tx_pos[:, 0],
                y=tx_pos[:, 1],
                z=tx_pos[:, 2],
                mode="lines",
                name="Tx LOS trajectory",
                line={"width": 5},
            )
        )
        plot.add_trace(
            go.Scatter3d(
                x=rx_pos[:, 0],
                y=rx_pos[:, 1],
                z=rx_pos[:, 2],
                mode="lines",
                name="Rx LOS trajectory",
                line={"width": 5, "dash": "dash"},
            )
        )
        plot.update_layout(
            title="Observation LOS trajectory",
            scene={
                "xaxis_title": "ICRS x (km)",
                "yaxis_title": "ICRS y (km)",
                "zaxis_title": "ICRS z (km)",
                "aspectmode": "data",
            },
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
        )
        plot.write_html(html_path, include_plotlyjs="cdn")

    def _make_echo_preview(self, npz_path: Path, image_path: Path) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        data = np.load(npz_path, allow_pickle=True)
        elapsed = data["elapsed_s"]
        iq = data["iq"]
        clean_iq = data["clean_iq"] if "clean_iq" in data.files else None
        fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.2), sharex=True)
        axes[0].plot(elapsed, iq.real, label="I", linewidth=1.0)
        axes[0].plot(elapsed, iq.imag, label="Q", linewidth=1.0)
        axes[0].set_ylabel("I/Q")
        axes[0].legend(loc="best")
        axes[1].plot(elapsed, np.abs(iq), label="noisy", linewidth=1.0)
        if clean_iq is not None:
            axes[1].plot(elapsed, np.abs(clean_iq), label="clean", linewidth=1.0, alpha=0.8)
        axes[1].set_ylabel("Amplitude")
        axes[1].legend(loc="best")
        axes[2].plot(elapsed, np.unwrap(np.angle(iq)), linewidth=1.0)
        axes[2].set_xlabel("Elapsed (s)")
        axes[2].set_ylabel("Phase (rad)")
        fig.tight_layout()
        fig.savefig(image_path, dpi=150)
        plt.close(fig)

    def _display_latest_image(self) -> None:
        if not self.latest_image_path or not self.latest_image_path.exists():
            self._draw_result_placeholder(self.result_status_var.get())
            return
        try:
            from PIL import Image, ImageTk

            if self.preview_source_path != self.latest_image_path or self.preview_source_image is None:
                if self.preview_source_image is not None:
                    self.preview_source_image.close()
                self.preview_source_image = Image.open(self.latest_image_path).copy()
                self.preview_source_path = self.latest_image_path
            image = self.preview_source_image
            width = max(240, self.result_canvas.winfo_width())
            height = max(180, self.result_canvas.winfo_height())
            scale = min(width / image.width, height / image.height)
            size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            resized = image.resize(size, Image.BILINEAR)
            self.preview_photo = ImageTk.PhotoImage(resized)
            self.result_canvas.delete("all")
            self.result_canvas.create_image(width // 2, height // 2, image=self.preview_photo, anchor="center")
        except Exception as exc:
            self._draw_result_placeholder(f"无法显示预览图：{exc}")

    def _schedule_display_latest_image(self, delay_ms: int = 80) -> None:
        if self.preview_resize_after_id is not None:
            self.after_cancel(self.preview_resize_after_id)
        self.preview_resize_after_id = self.after(delay_ms, self._run_scheduled_image_resize)

    def _run_scheduled_image_resize(self) -> None:
        self.preview_resize_after_id = None
        self._display_latest_image()

    def _draw_result_placeholder(self, text: str) -> None:
        self.result_canvas.delete("all")
        width = max(240, self.result_canvas.winfo_width())
        height = max(180, self.result_canvas.winfo_height())
        self.result_canvas.configure(background="#eef2f6")
        self.result_canvas.create_text(
            width // 2,
            height // 2,
            text=text,
            fill="#617083",
            width=max(220, width - 40),
            justify="center",
        )

    def _open_latest_result(self) -> None:
        if self.latest_result_path and self.latest_result_path.exists():
            webbrowser.open(self.latest_result_path.resolve().as_uri())

    def _open_plotly(self) -> None:
        if self.latest_plotly_path and self.latest_plotly_path.exists():
            webbrowser.open(self.latest_plotly_path.resolve().as_uri())

    @staticmethod
    def _next_stage(stage: str) -> str | None:
        index = STAGES.index(stage)
        if index + 1 >= len(STAGES):
            return None
        return STAGES[index + 1]


def main() -> None:
    app = PipelineGui()
    app.mainloop()


if __name__ == "__main__":
    main()
