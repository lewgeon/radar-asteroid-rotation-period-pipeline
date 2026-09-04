from __future__ import annotations

import copy
import shutil
from pathlib import Path

import numpy as np

from ... import storage
from ...qt_compat import QCheckBox, QComboBox, QFileDialog, QMessageBox, Qt
from ...schema import (
    COMMON_FIELD_ORDER, EPHEMERIS_FIELD_DEFAULTS, EPHEMERIS_FIELD_ORDER,
    SCATTERING_SPOT_DEFAULTS, STATE_DEFAULTS, STATE_FIELDS,
)
from ...storage import assign_path, flatten, now_text, parse_value
from ...widgets import BooleanFieldWidget


class FormStateMixin:
    def _is_monostatic_observation(self) -> bool:
        observation = self.config_data.get("observation", {})
        transmitter = observation.get("transmitter")
        receiver = observation.get("receiver")
        return isinstance(transmitter, dict) and isinstance(receiver, dict) and transmitter == receiver

    def _on_monostatic_toggled(self, checked: bool) -> None:
        try:
            self._sync_stage_from_fields()
        except Exception:
            pass
        self.monostatic_observation = bool(checked)
        if self.monostatic_observation:
            self._apply_monostatic_receiver()
        self._save_state()
        self._render_current_stage()
        if self.monostatic_checkbox:
            self.monostatic_checkbox.setFocus(Qt.FocusReason.OtherFocusReason)
        self.config_path_edit.deselect()

    def _on_reuse_observation_toggled(self, checked: bool) -> None:
        self.reuse_observation_info = bool(checked)
        if self.reuse_observation_edit:
            self.reuse_observation_edit.setEnabled(checked)
        self._save_state()

    def _on_reuse_observation_path_changed(self, path: str) -> None:
        self.reuse_observation_path = path.strip()

    def _choose_observation_info(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("选择视线向量文件", "Select Line-of-Sight Vector File"),
            str(storage.ROOT / "runs"),
            "NumPy (*.npz);;All Files (*)",
        )
        if not filename:
            return
        try:
            self._validate_observation_info(Path(filename))
        except Exception as exc:
            QMessageBox.critical(self, self._tr("文件无效", "Invalid File"), str(exc))
            return
        self.reuse_observation_path = filename
        self.reuse_observation_info = True
        if self.reuse_observation_edit:
            self.reuse_observation_edit.setText(filename)
        if self.reuse_observation_checkbox:
            self.reuse_observation_checkbox.setChecked(True)
        self._save_state()

    @staticmethod
    def _validate_observation_info(path: Path) -> None:
        required = {
            "start_utc", "elapsed_s", "scatter_elapsed_s", "emit_elapsed_s",
            "tx_los_icrs", "rx_los_icrs", "tx_range_m", "rx_range_m",
        }
        if not path.is_file():
            raise FileNotFoundError(f"视线向量文件不存在：{path}")
        with np.load(path, allow_pickle=False) as data:
            missing = sorted(required.difference(data.files))
            if missing:
                raise ValueError(f"视线向量文件缺少字段：{missing}")
            length = len(data["elapsed_s"])
            if length < 1 or any(len(data[key]) != length for key in required - {"start_utc"}):
                raise ValueError("视线向量文件字段长度不一致或时间轴为空")

    def _export_observation_info(self) -> None:
        source = self.latest_observation_path
        if not source or not source.exists():
            QMessageBox.information(self, self._tr("没有结果", "No Result"), self._tr("请先完成观测解算。", "Run observation first."))
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("另存视线向量", "Save Line-of-Sight Vectors As"),
            str(storage.ROOT / "runs" / "observation_info.npz"),
            "NumPy (*.npz)",
        )
        if filename:
            shutil.copy2(source, filename)
            self._append_log(f"[{now_text()}] 视线向量已另存为：{filename}")

    def _apply_monostatic_receiver(self) -> None:
        observation = self.config_data.setdefault("observation", {})
        transmitter = observation.get("transmitter")
        if isinstance(transmitter, dict):
            observation["receiver"] = copy.deepcopy(transmitter)

    def _ordered_group_fields(self, values: dict):
        flat = dict(flatten("", values))
        ordered = []
        for key in COMMON_FIELD_ORDER:
            if key in flat:
                ordered.append((key, flat.pop(key)))
        if "enabled" in flat:
            ordered.append(("enabled", flat.pop("enabled")))
            if values.get("enabled") is False or str(values.get("enabled")).lower() == "false":
                return ordered
        state = values.get("state")
        if state in STATE_FIELDS:
            for key in STATE_FIELDS[state]:
                if key in flat:
                    ordered.append((key, flat.pop(key)))
        spin_frame = str(values.get("spin_pole_frame", "equatorial")).lower()
        if spin_frame in {"icrs", "equatorial", "equtorial"}:
            flat.pop("spin_pole_ecliptic_deg", None)
        elif spin_frame == "ecliptic":
            flat.pop("spin_pole_icrs_deg", None)
        waveform_type = values.get("type")
        if waveform_type == "continuous_wave":
            for key in ("pulse_width_s", "bandwidth_hz", "fast_sample_rate_hz", "receive_window_start_s", "receive_window_duration_s", "pri_s", "first_pulse_start_s", "pulse_count", "pulse_start_s"):
                flat.pop(key, None)
        spin_coord_key = "spin_pole_ecliptic_deg" if spin_frame == "ecliptic" else "spin_pole_icrs_deg"
        for key in (
            "rotation_period_s",
            "initial_phase_deg",
            "spin_pole_frame",
            spin_coord_key,
            "direction_body",
            "radius_deg",
            "strength",
            "carrier_frequency_hz",
            "type",
            "amplitude",
            "pulse_width_s",
            "bandwidth_hz",
            "fast_sample_rate_hz",
            "receive_window_start_s",
            "receive_window_duration_s",
            "pri_s",
            "first_pulse_start_s",
            "pulse_count",
            "pulse_start_s",
        ):
            if key in flat:
                ordered.append((key, flat.pop(key)))
        ordered.extend(flat.items())
        return ordered

    def _migrate_config(self) -> None:
        echo_target = self.config_data.get("echo", {}).get("target")
        if isinstance(echo_target, dict):
            if str(echo_target.get("spin_pole_frame", "equatorial")).lower() in {"icrs", "equtorial"}:
                echo_target["spin_pole_frame"] = "equatorial"
            echo_target.setdefault("spin_pole_frame", "equatorial")
        echo_spot = self.config_data.get("echo", {}).get("scattering_spot")
        if isinstance(echo_spot, dict):
            echo_spot.setdefault("enabled", True)
            if str(echo_spot.get("enabled", True)).lower() != "false":
                for key, value in SCATTERING_SPOT_DEFAULTS.items():
                    echo_spot.setdefault(key, copy.deepcopy(value))
        echo_waveform = self.config_data.get("echo", {}).get("waveform")
        if isinstance(echo_waveform, dict) and echo_waveform.get("type") == "chirp_pulse_train":
            echo_waveform.setdefault("pulse_width_s", 20.0e-6)
            echo_waveform.setdefault("bandwidth_hz", 4.0e6)
            echo_waveform.setdefault("fast_sample_rate_hz", 8.0e6)
            echo_waveform.setdefault("receive_window_start_s", -25.0e-6)
            echo_waveform.setdefault("receive_window_duration_s", 50.0e-6)
            echo_waveform.setdefault("pri_s", 180.0)
            echo_waveform.setdefault("first_pulse_start_s", 0.0)

        observation = self.config_data.get("observation")
        if not isinstance(observation, dict):
            return
        target = observation.get("target")
        if not isinstance(target, dict):
            return

        if "horizons_id" in target:
            if "id" not in target:
                target["id"] = target["horizons_id"]
            target.pop("horizons_id", None)
        if "id_type" in target:
            if "object_type" not in target:
                target["object_type"] = target["id_type"]
            target.pop("id_type", None)

        ephemeris = observation.setdefault("ephemeris", {})
        if target.get("state") == "horizons_vectors":
            for key in EPHEMERIS_FIELD_ORDER:
                if key in target:
                    ephemeris.setdefault(key, target[key])
                    target.pop(key, None)
            for key, value in EPHEMERIS_FIELD_DEFAULTS.items():
                ephemeris.setdefault(key, copy.deepcopy(value))

    def _select_stage(self, stage: str) -> None:
        self._sync_stage_from_fields()
        self.current_stage = stage
        self._render_stage_buttons()
        self._render_current_stage()
        self.stage_buttons[stage].setFocus(Qt.FocusReason.OtherFocusReason)
        self.config_path_edit.deselect()

    def _focus_rebuilt_field(self, full_path: str) -> None:
        widget = self.field_widgets.get(full_path)
        if widget is not None:
            widget.setFocus(Qt.FocusReason.OtherFocusReason)
        self.config_path_edit.deselect()

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
        self._focus_rebuilt_field(full_path)

    def _on_spin_pole_frame_changed(self, full_path: str) -> None:
        self._sync_stage_from_fields()
        target = self.config_data.get("echo", {}).get("target")
        if not isinstance(target, dict):
            return
        frame = str(target.get("spin_pole_frame", "icrs")).lower()
        if frame == "ecliptic":
            target.setdefault("spin_pole_ecliptic_deg", copy.deepcopy(target.get("spin_pole_icrs_deg", [0.0, 90.0])))
        else:
            target["spin_pole_frame"] = "equatorial"
            target.setdefault("spin_pole_icrs_deg", copy.deepcopy(target.get("spin_pole_ecliptic_deg", [0.0, 90.0])))
        self._save_state()
        self._render_current_stage()
        self._focus_rebuilt_field(full_path)

    def _on_waveform_type_changed(self) -> None:
        self._sync_stage_from_fields()
        waveform = self.config_data.get("echo", {}).get("waveform")
        if not isinstance(waveform, dict):
            return
        if waveform.get("type") == "chirp_pulse_train":
            waveform.setdefault("pulse_width_s", 20.0e-6)
            waveform.setdefault("bandwidth_hz", 4.0e6)
            waveform.setdefault("fast_sample_rate_hz", 8.0e6)
            waveform.setdefault("receive_window_start_s", -25.0e-6)
            waveform.setdefault("receive_window_duration_s", 50.0e-6)
            waveform.setdefault("pri_s", 180.0)
            waveform.setdefault("first_pulse_start_s", 0.0)
        self._save_state()
        self._render_current_stage()
        self._focus_rebuilt_field("waveform.type")

    def _on_spot_enabled_changed(self) -> None:
        self._sync_stage_from_fields()
        spot = self.config_data.get("echo", {}).get("scattering_spot")
        if isinstance(spot, dict) and str(spot.get("enabled", True)).lower() != "false":
            for key, value in SCATTERING_SPOT_DEFAULTS.items():
                spot.setdefault(key, copy.deepcopy(value))
        self._save_state()
        self._render_current_stage()
        self._focus_rebuilt_field("scattering_spot.enabled")

    def _on_station_motion_changed(self, full_path: str) -> None:
        self._sync_stage_from_fields()
        group_name = full_path.split(".", 1)[0]
        group = self.config_data.get("observation", {}).get(group_name)
        if isinstance(group, dict):
            self.config_data["observation"][group_name] = self._normalize_state_group(group)
        self._save_state()
        self._render_current_stage()
        self._focus_rebuilt_field(full_path)

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
        existing = self.config_data.get(self.current_stage, {})
        stage_payload = copy.deepcopy(existing) if isinstance(existing, dict) else {}
        geodetic_rotation: dict[str, bool] = {}
        linear_motion: dict[str, bool] = {}
        for path, widget in self.field_widgets.items():
            if hasattr(widget, "value"):
                value = widget.value()
            elif isinstance(widget, (QCheckBox, BooleanFieldWidget)):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                text = widget.currentText() if data is None else str(data)
                value = parse_value(text)
            else:
                value = parse_value(widget.text())
            if path.endswith(".geodetic_time_dependent"):
                geodetic_rotation[path.split(".", 1)[0]] = bool(value)
                continue
            if path.endswith(".linear_motion"):
                linear_motion[path.split(".", 1)[0]] = bool(value)
                continue
            assign_path(stage_payload, path, value)
        if self.current_stage == "observation":
            for role in ("transmitter", "receiver"):
                group = stage_payload.get(role)
                if not isinstance(group, dict):
                    continue
                if group.get("state") == "geodetic":
                    group["state"] = (
                        "astropy_geodetic" if geodetic_rotation.get(role, True) else "geodetic_fixed"
                    )
                elif group.get("state") == "cartesian":
                    group["state"] = "linear" if linear_motion.get(role, False) else "static"
        self.config_data[self.current_stage] = stage_payload
        if self.current_stage == "observation" and self.monostatic_observation:
            self._apply_monostatic_receiver()
        self._migrate_config()
        self._normalize_horizons_object_type()
