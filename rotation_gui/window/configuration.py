from __future__ import annotations

from pathlib import Path

import pipeline

from .. import storage
from ..qt_compat import QFileDialog, QMessageBox
from ..schema import HORIZONS_ID_TYPE_ALIASES, HORIZONS_OBJECT_TYPES, STAGES
from ..storage import now_text, read_json, write_json


class ConfigurationMixin:
    def _load_initial_config(self):
        disk_config = read_json(storage.DEFAULT_CONFIG_PATH, pipeline.DEFAULT_CONFIG)
        state = read_json(storage.STATE_PATH, {})
        if isinstance(state, dict) and isinstance(state.get("config"), dict):
            self.config_source_text = f"GUI 状态文件 {storage.STATE_PATH}"
            saved_path = state.get("config_path")
            if saved_path:
                self.config_path = Path(saved_path)
            return pipeline.pipeline_config_from_any(state["config"])
        self.config_source_text = f"磁盘配置 {storage.DEFAULT_CONFIG_PATH}"
        return pipeline.pipeline_config_from_any(disk_config)

    def _save_current_config(self) -> None:
        try:
            self._sync_stage_from_fields()
            self._save_state()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._append_log(f"[{now_text()}] 参数已保存，下次打开会使用当前值。")
        self.status_label.setText("参数已保存")

    def _save_config_as_json(self) -> None:
        try:
            self._sync_stage_from_fields()
            pipeline.require_sections(self.config_data)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        default_name = f"{self.run_name_edit.text().strip() or self.config_path.stem}.json"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "将当前参数保存为 JSON",
            str(storage.ROOT / "configs" / default_name),
            "JSON (*.json);;全部文件 (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            export_payload = pipeline.gui_config_from_pipeline_config(self.config_data, self.language)
            write_json(path, export_payload)
            self.config_path = path
            self.config_path_edit.setText(str(path))
            # “另存 JSON”只记录参数快照到哪个文件，不应改动实验名（输出目录）。
            # 实验名决定 runs/<实验名>/ 下的中间结果位置，若随文件名变化，已算好的
            # observation_info.npz 就会“消失”，导致同一组视线数据无法复用。
            self._save_state()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._append_log(f"[{now_text()}] 当前参数已另存为：{path}（实验名保持为 {self.run_name_edit.text().strip() or self.config_path.stem}）")
        self.status_label.setText(f"已保存 JSON：{path}")

    def _save_state(self) -> None:
        write_json(
            storage.STATE_PATH,
            {
                "config_path": str(self.config_path),
                "config": self.config_data,
                "reuse_observation_info": self.reuse_observation_info,
                "reuse_observation_path": self.reuse_observation_path,
                "saved_at": now_text(),
            },
        )

    def _choose_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择 pipeline JSON 配置",
            str(storage.ROOT / "configs"),
            "JSON (*.json);;全部文件 (*)",
        )
        if filename:
            self.config_path_edit.setText(filename)
            self._load_config_from_entry()

    def _load_config_from_entry(self) -> None:
        path = Path(self.config_path_edit.text()).expanduser()
        if not path.is_absolute():
            path = storage.ROOT / path
        try:
            data = read_json(path, {})
            data = pipeline.pipeline_config_from_any(data)
            pipeline.require_sections(data)
        except Exception as exc:
            QMessageBox.critical(self, "载入失败", str(exc))
            return
        self.config_path = path
        self.config_data = data
        self._migrate_config()
        self.monostatic_observation = False
        self.reuse_observation_info = False
        self.reuse_observation_path = ""
        self.run_name_edit.setText(path.stem)
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self._render_stage_buttons()
        self._render_current_stage()
        self._save_state()
        self._append_log(f"[{now_text()}] 已载入配置：{path}")

    def _validate_role_states(self) -> None:
        self._normalize_horizons_object_type()
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

        target = observation.get("target", {})
        if target.get("state") == "horizons_vectors":
            if "id_type" in target or "horizons_id" in target:
                raise ValueError("target 中不再支持 id_type/horizons_id，请使用 id 和 object_type。")
            object_type = target.get("object_type")
            if object_type not in HORIZONS_OBJECT_TYPES:
                raise ValueError(
                    f"target.object_type={object_type!r} 不是当前配置支持的目标类型。"
                    "当前 GUI 仅支持 null 或 smallbody。"
                )

    def _normalize_horizons_object_type(self) -> None:
        target = self.config_data.get("observation", {}).get("target", {})
        if not isinstance(target, dict) or target.get("state") != "horizons_vectors":
            return
        if "horizons_id" in target:
            if "id" not in target:
                target["id"] = target["horizons_id"]
                self._append_log(f"[{now_text()}] 已将弃用字段 target.horizons_id 迁移为 target.id。")
            target.pop("horizons_id", None)
        if "id_type" in target:
            if "object_type" not in target:
                target["object_type"] = target["id_type"]
                self._append_log(f"[{now_text()}] 已将弃用字段 target.id_type 迁移为 target.object_type。")
            target.pop("id_type", None)
        value = target.get("object_type")
        if isinstance(value, str):
            normalized = HORIZONS_ID_TYPE_ALIASES.get(value.strip().lower(), value.strip())
        else:
            normalized = value
        if normalized != value:
            target["object_type"] = normalized
            self._append_log(f"[{now_text()}] 已将 target.object_type 从 {value!r} 归一化为 {normalized!r}。")
