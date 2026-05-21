"""Standalone color ramp editor for TColorRamp."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

import nuke  # ty:ignore[unresolved-import]

try:
    from PySide2 import QtCore, QtGui, QtWidgets  # ty:ignore[import-not-found]
except Exception:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets  # ty:ignore[import-not-found]
    except Exception:
        QtCore = None
        QtGui = None
        QtWidgets = None

_SERIALIZED_KNOB = "color_ramp_serialized"
_INTERPOLATION_MODE_BY_NAME = {
    "linear": 0,
    "constant": 1,
    "smooth": 2,
    "smoother": 3,
}

_RAMP_PRESETS: Dict[str, Sequence[Tuple[float, Tuple[float, float, float]]]] = {
    "Grayscale": (
        (0.0, (0.0, 0.0, 0.0)),
        (1.0, (1.0, 1.0, 1.0)),
    ),
    "Heat": (
        (0.0, (0.02, 0.02, 0.02)),
        (0.28, (0.72, 0.05, 0.0)),
        (0.62, (0.95, 0.45, 0.0)),
        (1.0, (1.0, 0.92, 0.5)),
    ),
    "Ocean": (
        (0.0, (0.02, 0.09, 0.18)),
        (0.35, (0.0, 0.36, 0.7)),
        (0.7, (0.0, 0.72, 0.82)),
        (1.0, (0.75, 0.95, 1.0)),
    ),
    "Toxic": (
        (0.0, (0.03, 0.03, 0.03)),
        (0.35, (0.08, 0.65, 0.08)),
        (0.7, (0.55, 0.95, 0.1)),
        (1.0, (0.95, 1.0, 0.45)),
    ),
    "Sunset": (
        (0.0, (0.12, 0.03, 0.22)),
        (0.35, (0.62, 0.12, 0.44)),
        (0.72, (0.95, 0.42, 0.2)),
        (1.0, (1.0, 0.86, 0.45)),
    ),
}

_CUSTOM_PRESET_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_color_ramp_presets.json",
)


def _jsonable_stops(stops: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    safe = _normalize_stops(stops)
    out: List[Dict[str, object]] = []
    for stop in safe:
        c = stop["color"]  # type:ignore[index]
        out.append(
            {
                "pos": float(stop["pos"]),
                "color": [float(c[0]), float(c[1]), float(c[2])],
            },
        )
    return out


def _stops_from_jsonable(raw_stops: object) -> List[Dict[str, object]]:
    if not isinstance(raw_stops, list):
        return _normalize_stops([])
    parsed: List[Dict[str, object]] = []
    for stop in raw_stops:
        if not isinstance(stop, dict):
            continue
        pos = stop.get("pos", 0.0)
        color = stop.get("color", (0.0, 0.0, 0.0))
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            color = (0.0, 0.0, 0.0)
        parsed.append(
            {
                "pos": float(pos),
                "color": (float(color[0]), float(color[1]), float(color[2])),
            },
        )
    return _normalize_stops(parsed)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _clean_preset_name(name: object) -> str:
    cleaned = str(name).strip()
    if cleaned.startswith("★"):
        cleaned = cleaned[1:].strip()
    return cleaned


def _load_preset_store() -> Tuple[Dict[str, List[Dict[str, object]]], List[str]]:
    if not os.path.isfile(_CUSTOM_PRESET_FILE):
        return ({}, [])
    try:
        with open(_CUSTOM_PRESET_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return ({}, [])
    if not isinstance(payload, dict):
        return ({}, [])

    raw_custom: object = payload
    raw_favorites: object = []
    if (
        isinstance(payload.get("custom_presets"), dict)
        or payload.get("format") == "TColorRampPresetStore"
    ):
        raw_custom = payload.get("custom_presets", {})
        raw_favorites = payload.get("favorites", [])

    custom: Dict[str, List[Dict[str, object]]] = {}
    if isinstance(raw_custom, dict):
        for name, stops in raw_custom.items():
            safe_name = _clean_preset_name(name)
            if not safe_name:
                continue
            safe_stops = _stops_from_jsonable(stops)
            if safe_stops:
                custom[safe_name] = safe_stops

    favorites: List[str] = []
    if isinstance(raw_favorites, list):
        for name in raw_favorites:
            safe_name = _clean_preset_name(name)
            if safe_name:
                favorites.append(safe_name)
    return (custom, favorites)


def _write_custom_presets_file() -> bool:
    known_names = set(_RAMP_PRESETS.keys()) | set(_CUSTOM_PRESETS.keys())
    favorites = sorted({name for name in _FAVORITE_PRESETS if name in known_names})
    payload = {
        "format": "TColorRampPresetStore",
        "version": 2,
        "custom_presets": {
            name: _jsonable_stops(stops)
            for name, stops in _CUSTOM_PRESETS.items()
        },
        "favorites": favorites,
    }
    try:
        with open(_CUSTOM_PRESET_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        return False
    return True


def _preset_names() -> List[str]:
    names = list(_RAMP_PRESETS.keys())
    for custom_name in sorted(_CUSTOM_PRESETS.keys()):
        if custom_name not in names:
            names.append(custom_name)
    favorites = [name for name in names if name in _FAVORITE_PRESETS]
    others = [name for name in names if name not in _FAVORITE_PRESETS]
    return favorites + others


def _preset_stops(name: str) -> List[Dict[str, object]]:
    safe_name = _clean_preset_name(name)
    custom = _CUSTOM_PRESETS.get(safe_name)
    if custom:
        return _normalize_stops(custom)
    raw = _RAMP_PRESETS.get(safe_name)
    if not raw:
        return _normalize_stops([])
    return _normalize_stops([{"pos": pos, "color": color} for pos, color in raw])


def _save_custom_preset(name: str, stops: Sequence[Dict[str, object]]) -> bool:
    preset_name = _clean_preset_name(name)
    if not preset_name:
        return False
    _CUSTOM_PRESETS[preset_name] = _normalize_stops(stops)
    return _write_custom_presets_file()


def _rename_custom_preset(old_name: str, new_name: str) -> bool:
    old_key = _clean_preset_name(old_name)
    new_key = _clean_preset_name(new_name)
    if not old_key or not new_key or old_key not in _CUSTOM_PRESETS:
        return False
    data = _CUSTOM_PRESETS.pop(old_key)
    _CUSTOM_PRESETS[new_key] = data
    if old_key in _FAVORITE_PRESETS:
        _FAVORITE_PRESETS.discard(old_key)
        _FAVORITE_PRESETS.add(new_key)
    return _write_custom_presets_file()


def _delete_custom_preset(name: str) -> bool:
    key = _clean_preset_name(name)
    if not key or key not in _CUSTOM_PRESETS:
        return False
    _CUSTOM_PRESETS.pop(key, None)
    _FAVORITE_PRESETS.discard(key)
    return _write_custom_presets_file()


def _is_custom_preset(name: str) -> bool:
    return _clean_preset_name(name) in _CUSTOM_PRESETS


def _is_favorite_preset(name: str) -> bool:
    return _clean_preset_name(name) in _FAVORITE_PRESETS


def _set_favorite_preset(name: str, favorite: bool) -> bool:
    key = _clean_preset_name(name)
    if not key:
        return False
    if favorite:
        _FAVORITE_PRESETS.add(key)
    else:
        _FAVORITE_PRESETS.discard(key)
    return _write_custom_presets_file()


def _display_preset_name(name: str) -> str:
    key = _clean_preset_name(name)
    return "★ {}".format(key) if key in _FAVORITE_PRESETS else key


def _export_presets_to_file(path: str, names: Sequence[str]) -> bool:
    chosen = [_clean_preset_name(name) for name in names if _clean_preset_name(name)]
    if not chosen:
        return False
    presets_payload: Dict[str, List[Dict[str, object]]] = {}
    for name in chosen:
        presets_payload[name] = _jsonable_stops(_preset_stops(name))
    payload = {
        "format": "TColorRampPresets",
        "version": 2,
        "presets": presets_payload,
        "favorites": [name for name in chosen if name in _FAVORITE_PRESETS],
    }
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    except Exception:
        return False
    return True


def _import_presets_from_file(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []

    raw_presets: object = payload
    if isinstance(payload, dict) and isinstance(payload.get("presets"), dict):
        raw_presets = payload.get("presets")

    if not isinstance(raw_presets, dict):
        return []

    imported_names: List[str] = []
    for name, stops in raw_presets.items():
        safe_name = _clean_preset_name(name)
        if not safe_name:
            continue
        safe_stops = _stops_from_jsonable(stops)
        if not safe_stops:
            continue
        _CUSTOM_PRESETS[safe_name] = safe_stops
        imported_names.append(safe_name)

    if isinstance(payload, dict) and isinstance(payload.get("favorites"), list):
        for fav_name in payload.get("favorites", []):
            safe_fav = _clean_preset_name(fav_name)
            if safe_fav:
                _FAVORITE_PRESETS.add(safe_fav)

    if not imported_names:
        return []
    if not _write_custom_presets_file():
        return []
    imported_names.sort()
    return imported_names


def _pack_rgb8(color: Tuple[float, float, float]) -> int:
    r = int(round(_clamp01(color[0]) * 255.0))
    g = int(round(_clamp01(color[1]) * 255.0))
    b = int(round(_clamp01(color[2]) * 255.0))
    return (r << 16) | (g << 8) | b


def _unpack_rgb8(value: int) -> Tuple[float, float, float]:
    value = int(value)
    r = ((value >> 16) & 0xFF) / 255.0
    g = ((value >> 8) & 0xFF) / 255.0
    b = (value & 0xFF) / 255.0
    return (r, g, b)


def _normalize_stops(stops: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for stop in stops:
        pos = _clamp01(float(stop.get("pos", 0.0)))
        color = stop.get("color", (0.0, 0.0, 0.0))
        if not isinstance(color, (tuple, list)) or len(color) != 3:
            color = (0.0, 0.0, 0.0)
        c = (_clamp01(float(color[0])), _clamp01(float(color[1])), _clamp01(float(color[2])))
        out.append({"pos": pos, "color": c})
    if len(out) < 1:
        out = [
            {"pos": 0.0, "color": (0.0, 0.0, 0.0)},
            {"pos": 1.0, "color": (1.0, 1.0, 1.0)},
        ]
    out.sort(key=lambda s: float(s["pos"]))
    return out


_CUSTOM_PRESETS, _loaded_favorites = _load_preset_store()
_FAVORITE_PRESETS = {
    _clean_preset_name(name)
    for name in _loaded_favorites
    if _clean_preset_name(name)
}


def _serialize_stops(stops: Sequence[Dict[str, object]]) -> str:
    safe_stops = _normalize_stops(stops)
    return ";".join(
        "{:.6f}|{:.6f}|{:.6f}|{:.6f}".format(
            float(stop["pos"]),
            float(stop["color"][0]),  # type:ignore[index]
            float(stop["color"][1]),  # type:ignore[index]
            float(stop["color"][2]),  # type:ignore[index]
        )
        for stop in safe_stops
    )


def _deserialize_stops(payload: str) -> List[Dict[str, object]]:
    if not payload:
        return _normalize_stops([])
    parsed: List[Dict[str, object]] = []
    for token in str(payload).split(";"):
        token = token.strip()
        if not token:
            continue
        parts = [p.strip() for p in token.split("|")]
        if len(parts) != 4:
            continue
        try:
            pos = float(parts[0])
            r = float(parts[1])
            g = float(parts[2])
            b = float(parts[3])
        except Exception:
            continue
        parsed.append({"pos": pos, "color": (_clamp01(r), _clamp01(g), _clamp01(b))})
    return _normalize_stops(parsed)


def _table_iface(node) -> Optional[object]:
    knob = node.knob("color_ramp_stops")
    if knob is None:
        return None
    candidates = [knob]
    for accessor in ("tableKnob", "table"):
        fn = getattr(knob, accessor, None)
        if callable(fn):
            try:
                obj = fn()
            except Exception:
                obj = None
            if obj is not None:
                candidates.append(obj)
    required = ("getRowCount", "getColumnIndex", "addRow", "setCellFloat", "setCellColor")
    for candidate in candidates:
        if all(hasattr(candidate, name) for name in required):
            return candidate
    return None


def _read_stops_from_node(node) -> List[Dict[str, object]]:
    serialized_knob = node.knob(_SERIALIZED_KNOB)
    if serialized_knob is not None:
        try:
            payload = str(serialized_knob.value())
        except Exception:
            payload = ""
        if payload:
            return _deserialize_stops(payload)
    iface = _table_iface(node)
    if iface is None:
        return _normalize_stops([])
    try:
        row_count = int(iface.getRowCount())
        pos_col = int(iface.getColumnIndex("pos"))
        color_col = int(iface.getColumnIndex("color"))
    except Exception:
        return _normalize_stops([])
    if row_count <= 0 or pos_col < 0 or color_col < 0:
        return _normalize_stops([])
    stops: List[Dict[str, object]] = []
    for row in range(row_count):
        try:
            pos = float(iface.getCellFloat(row, pos_col))
            color = _unpack_rgb8(int(iface.getCellColor(row, color_col)))
        except Exception:
            continue
        stops.append({"pos": pos, "color": color})
    return _normalize_stops(stops)


def _clear_table_rows(iface) -> None:
    if hasattr(iface, "deleteAllItems"):
        iface.deleteAllItems()
        return
    if hasattr(iface, "deleteRow") and hasattr(iface, "getRowCount"):
        for row in reversed(range(int(iface.getRowCount()))):
            iface.deleteRow(row)


def _write_stops_to_node(node, stops: Sequence[Dict[str, object]]) -> bool:
    safe_stops = _normalize_stops(stops)
    wrote = False
    serialized_knob = node.knob(_SERIALIZED_KNOB)
    if serialized_knob is not None:
        try:
            serialized_knob.setValue(_serialize_stops(safe_stops))
            wrote = True
        except Exception:
            pass
    iface = _table_iface(node)
    if iface is not None:
        try:
            pos_col = int(iface.getColumnIndex("pos"))
            color_col = int(iface.getColumnIndex("color"))
            if pos_col >= 0 and color_col >= 0:
                _clear_table_rows(iface)
                for stop in safe_stops:
                    row = int(iface.addRow())
                    iface.setCellFloat(row, pos_col, float(stop["pos"]))
                    iface.setCellColor(row, color_col, _pack_rgb8(stop["color"]))  # type:ignore[arg-type]
                wrote = True
        except Exception:
            pass
    try:
        node.forceValidate()
    except Exception:
        pass
    return wrote


if QtWidgets is not None:

    class _RampWidget(QtWidgets.QWidget):
        stopsChanged = QtCore.Signal()
        selectionChanged = QtCore.Signal(int)

        def __init__(self, stops: Sequence[Dict[str, object]], parent=None):
            super().__init__(parent)
            self.setMinimumHeight(92)
            self.setMaximumHeight(92)
            self.setSizePolicy(
                QtWidgets.QSizePolicy(
                    QtWidgets.QSizePolicy.Expanding,
                    QtWidgets.QSizePolicy.Fixed,
                ),
            )
            self._stops = _normalize_stops(stops)
            self._selected = 0
            self._dragging = False
            self._interpolation_mode = 0

        def _bar_rect(self):
            return QtCore.QRectF(14.0, 14.0, max(10.0, self.width() - 28.0), 26.0)

        def _x_from_pos(self, pos: float, rect: QtCore.QRectF) -> float:
            return rect.left() + _clamp01(pos) * rect.width()

        def _pos_from_x(self, x: float, rect: QtCore.QRectF) -> float:
            return _clamp01((x - rect.left()) / max(1.0, rect.width()))

        def _qcolor(self, c: Tuple[float, float, float]):
            return QtGui.QColor.fromRgbF(c[0], c[1], c[2], 1.0)

        def _event_xy(self, event) -> Tuple[float, float]:
            x = float(event.position().x()) if hasattr(event, "position") else float(event.x())
            y = float(event.position().y()) if hasattr(event, "position") else float(event.y())
            return (x, y)

        def _is_outside_delete_zone(self, x: float, y: float, rect: QtCore.QRectF) -> bool:
            return (
                x < (rect.left() - 34.0)
                or x > (rect.right() + 34.0)
                or y < (rect.top() - 26.0)
                or y > (rect.bottom() + 54.0)
            )

        def _open_color_picker_for_selected(self) -> None:
            stop = self._stops[self._selected]
            c = stop["color"]  # type:ignore[assignment]
            initial = QtGui.QColor.fromRgbF(c[0], c[1], c[2], 1.0)
            chosen = QtWidgets.QColorDialog.getColor(initial, self, "Pick Ramp Color")
            if not chosen.isValid():
                return
            self.set_selected_color((chosen.redF(), chosen.greenF(), chosen.blueF()))

        def _sample_color(self, pos: float) -> Tuple[float, float, float]:
            p = _clamp01(pos)
            if p <= float(self._stops[0]["pos"]):
                return self._stops[0]["color"]  # type:ignore[return-value]
            if p >= float(self._stops[-1]["pos"]):
                return self._stops[-1]["color"]  # type:ignore[return-value]
            for i in range(1, len(self._stops)):
                l = self._stops[i - 1]
                r = self._stops[i]
                lp = float(l["pos"])
                rp = float(r["pos"])
                if p <= rp:
                    t = 0.0 if rp <= lp else (p - lp) / (rp - lp)
                    if self._interpolation_mode == 1:
                        t = 0.0 if p < rp else 1.0
                    elif self._interpolation_mode == 2:
                        t = t * t * (3.0 - 2.0 * t)
                    elif self._interpolation_mode == 3:
                        t = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
                    lc = l["color"]  # type:ignore[assignment]
                    rc = r["color"]  # type:ignore[assignment]
                    return (
                        lc[0] + (rc[0] - lc[0]) * t,
                        lc[1] + (rc[1] - lc[1]) * t,
                        lc[2] + (rc[2] - lc[2]) * t,
                    )
            return (0.0, 0.0, 0.0)

        def stops(self) -> List[Dict[str, object]]:
            return _normalize_stops(self._stops)

        def selected_index(self) -> int:
            return int(self._selected)

        def set_selected_index(self, idx: int) -> None:
            idx = max(0, min(int(idx), len(self._stops) - 1))
            if idx != self._selected:
                self._selected = idx
                self.selectionChanged.emit(self._selected)
                self.update()

        def set_stops(self, stops: Sequence[Dict[str, object]]) -> None:
            self._stops = _normalize_stops(stops)
            self._selected = max(0, min(self._selected, len(self._stops) - 1))
            self.stopsChanged.emit()
            self.selectionChanged.emit(self._selected)
            self.update()

        def set_interpolation_mode(self, mode: int) -> None:
            m = max(0, min(int(mode), 3))
            if m != self._interpolation_mode:
                self._interpolation_mode = m
                self.update()

        def add_stop(self, pos: float) -> None:
            p = _clamp01(pos)
            c = self._sample_color(p)
            stop = {"pos": p, "color": c}
            self._stops.append(stop)
            self._stops.sort(key=lambda s: float(s["pos"]))
            self._selected = self._stops.index(stop)
            self.stopsChanged.emit()
            self.selectionChanged.emit(self._selected)
            self.update()

        def remove_selected(self) -> None:
            if len(self._stops) <= 1:
                return
            del self._stops[self._selected]
            self._selected = max(0, min(self._selected, len(self._stops) - 1))
            self.stopsChanged.emit()
            self.selectionChanged.emit(self._selected)
            self.update()

        def set_selected_color(self, color: Tuple[float, float, float]) -> None:
            self._stops[self._selected]["color"] = (
                _clamp01(color[0]),
                _clamp01(color[1]),
                _clamp01(color[2]),
            )
            self.stopsChanged.emit()
            self.update()

        def set_selected_pos(self, pos: float) -> None:
            stop = self._stops[self._selected]
            stop["pos"] = _clamp01(pos)
            self._stops.sort(key=lambda s: float(s["pos"]))
            self._selected = self._stops.index(stop)
            self.stopsChanged.emit()
            self.selectionChanged.emit(self._selected)
            self.update()

        def paintEvent(self, _event):
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            rect = self._bar_rect()
            width = max(2, int(rect.width()))
            gradient_img = QtGui.QImage(width, 1, QtGui.QImage.Format_RGB32)
            for ix in range(width):
                t = float(ix) / float(width - 1)
                c = self._sample_color(t)
                gradient_img.setPixelColor(
                    ix,
                    0,
                    QtGui.QColor.fromRgbF(_clamp01(c[0]), _clamp01(c[1]), _clamp01(c[2]), 1.0),
                )
            path = QtGui.QPainterPath()
            path.addRoundedRect(rect, 4.0, 4.0)
            p.save()
            p.setClipPath(path)
            p.drawImage(rect, gradient_img, QtCore.QRectF(0.0, 0.0, float(width), 1.0))
            p.restore()
            p.setBrush(QtCore.Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 1.0))
            p.drawRoundedRect(rect, 4.0, 4.0)
            for i, stop in enumerate(self._stops):
                x = self._x_from_pos(float(stop["pos"]), rect)
                top = rect.bottom() + 4.0
                poly = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(x, top),
                        QtCore.QPointF(x - 6.0, top + 10.0),
                        QtCore.QPointF(x + 6.0, top + 10.0),
                    ],
                )
                p.setBrush(self._qcolor(stop["color"]))  # type:ignore[arg-type]
                border = QtGui.QColor(255, 255, 255) if i == self._selected else QtGui.QColor(20, 20, 20)
                p.setPen(QtGui.QPen(border, 1.3))
                p.drawPolygon(poly)
                square_size = 9.0
                square_rect = QtCore.QRectF(
                    x - (square_size * 0.5),
                    top + 12.0,
                    square_size,
                    square_size,
                )
                p.setBrush(self._qcolor(stop["color"]))  # type:ignore[arg-type]
                p.setPen(QtGui.QPen(border, 1.1))
                p.drawRect(square_rect)

        def _pick_handle(self, x: float, y: float) -> int:
            rect = self._bar_rect()
            hy0 = rect.bottom() + 2.0
            hy1 = rect.bottom() + 28.0
            if y < hy0 or y > hy1:
                return -1
            best = -1
            best_d = 1e9
            for i, stop in enumerate(self._stops):
                sx = self._x_from_pos(float(stop["pos"]), rect)
                d = abs(sx - x)
                if d < best_d and d <= 9.0:
                    best = i
                    best_d = d
            return best

        def mousePressEvent(self, event):
            if event.button() != QtCore.Qt.LeftButton:
                return
            rect = self._bar_rect()
            x, y = self._event_xy(event)
            handle = self._pick_handle(x, y)
            if handle >= 0:
                self.set_selected_index(handle)
                self._dragging = True
                return
            if rect.contains(QtCore.QPointF(x, y)):
                self.add_stop(self._pos_from_x(x, rect))
                self._dragging = True

        def mouseMoveEvent(self, event):
            if not self._dragging:
                return
            rect = self._bar_rect()
            x, y = self._event_xy(event)
            if self._is_outside_delete_zone(x, y, rect):
                if len(self._stops) > 1:
                    self.remove_selected()
                self._dragging = False
                return
            self.set_selected_pos(self._pos_from_x(x, rect))

        def mouseReleaseEvent(self, _event):
            self._dragging = False

        def mouseDoubleClickEvent(self, event):
            if event.button() != QtCore.Qt.LeftButton:
                return
            x, y = self._event_xy(event)
            handle = self._pick_handle(x, y)
            if handle < 0:
                return
            self.set_selected_index(handle)
            self._open_color_picker_for_selected()


    class _InlineRampEditorWidget(QtWidgets.QWidget):
        def __init__(self, node, parent=None):
            super().__init__(parent)
            self._node = node
            self._suspend_write = False
            self._selected_index_cache = 0
            self._pos_cache = 0.0
            self._color_cache = (0.0, 0.0, 0.0)
            self._interpolation_cache = 0
            self.setSizePolicy(
                QtWidgets.QSizePolicy(
                    QtWidgets.QSizePolicy.Preferred,
                    QtWidgets.QSizePolicy.Fixed,
                ),
            )

            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(6)

            controls = QtWidgets.QHBoxLayout()
            self._add_btn = QtWidgets.QPushButton("+")
            self._remove_btn = QtWidgets.QPushButton("-")
            self._add_btn.setFixedWidth(30)
            self._remove_btn.setFixedWidth(30)
            controls.addWidget(self._add_btn)
            controls.addWidget(self._remove_btn)
            controls.addStretch(1)
            root.addLayout(controls)

            self._ramp = _RampWidget(_read_stops_from_node(node), self)
            root.addWidget(self._ramp)

            self._ramp.selectionChanged.connect(self._on_selection_changed)
            self._ramp.stopsChanged.connect(self._on_stops_changed)
            self._add_btn.clicked.connect(lambda: self._ramp.add_stop(0.5))
            self._remove_btn.clicked.connect(self._ramp.remove_selected)

            self._serialized_cache = _serialize_stops(self._ramp.stops())
            self._selected_index_cache = self._ramp.selected_index()
            selected_stop = self._selected_stop()
            self._pos_cache = float(selected_stop["pos"])
            self._color_cache = tuple(float(c) for c in selected_stop["color"])  # type:ignore[index]
            self._interpolation_cache = self._read_node_interpolation_knob()
            self._ramp.set_interpolation_mode(self._interpolation_cache)
            self._sync_selected_knobs_to_node()
            self._remove_btn.setEnabled(len(self._ramp.stops()) > 1)

            self._poll_timer = QtCore.QTimer(self)
            self._poll_timer.setInterval(140)
            self._poll_timer.timeout.connect(self._poll_node_state)
            self._poll_timer.start()

            fixed_h = int(self.sizeHint().height())
            self.setMinimumHeight(fixed_h)
            self.setMaximumHeight(fixed_h)

        def _selected_stop(self) -> Dict[str, object]:
            return self._ramp.stops()[self._ramp.selected_index()]

        def _read_node_color_knob(self) -> Tuple[float, float, float]:
            knob = self._node.knob("color_ramp_color")
            if knob is None:
                fallback = getattr(self, "_color_cache", (0.0, 0.0, 0.0))
                return (float(fallback[0]), float(fallback[1]), float(fallback[2]))
            try:
                raw = knob.value()
                if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                    return (
                        _clamp01(float(raw[0])),
                        _clamp01(float(raw[1])),
                        _clamp01(float(raw[2])),
                    )
            except Exception:
                pass
            fallback = getattr(self, "_color_cache", (0.0, 0.0, 0.0))
            out = [0.0, 0.0, 0.0]
            for idx in range(3):
                try:
                    out[idx] = _clamp01(float(knob.value(idx)))
                except Exception:
                    out[idx] = float(fallback[idx])
            return (out[0], out[1], out[2])

        def _read_node_pos_knob(self) -> float:
            knob = self._node.knob("color_ramp_pos")
            if knob is None:
                return float(getattr(self, "_pos_cache", 0.0))
            try:
                return _clamp01(float(knob.value()))
            except Exception:
                return float(getattr(self, "_pos_cache", 0.0))

        def _read_node_interpolation_knob(self) -> int:
            knob = self._node.knob("color_ramp_interpolation")
            if knob is None:
                return int(getattr(self, "_interpolation_cache", 0))
            fallback = int(getattr(self, "_interpolation_cache", 0))
            try:
                raw = knob.value()
                if isinstance(raw, str):
                    name = raw.strip().lower()
                    if name in _INTERPOLATION_MODE_BY_NAME:
                        return _INTERPOLATION_MODE_BY_NAME[name]
                    try:
                        return max(0, min(int(float(name)), 3))
                    except Exception:
                        return fallback
                if isinstance(raw, (int, float)):
                    return max(0, min(int(raw), 3))
            except Exception:
                pass
            return fallback

        def _set_node_rgb_knob(self, knob, color: Tuple[float, float, float]) -> None:
            if knob is None:
                return
            try:
                knob.setValue(float(color[0]), 0)
                knob.setValue(float(color[1]), 1)
                knob.setValue(float(color[2]), 2)
                return
            except Exception:
                pass
            try:
                knob.setValue([float(color[0]), float(color[1]), float(color[2])])
            except Exception:
                pass

        def _sync_selected_knobs_to_node(self) -> None:
            stop = self._selected_stop()
            idx = int(self._ramp.selected_index())
            color = stop["color"]  # type:ignore[assignment]
            pos = float(stop["pos"])

            idx_knob = self._node.knob("color_ramp_selected_index")
            if idx_knob is not None:
                try:
                    idx_knob.setValue(idx)
                except Exception:
                    pass

            pos_knob = self._node.knob("color_ramp_pos")
            if pos_knob is not None:
                try:
                    pos_knob.setValue(pos)
                except Exception:
                    pass

            self._set_node_rgb_knob(self._node.knob("color_ramp_color"), color)
            self._selected_index_cache = idx
            self._pos_cache = pos
            self._color_cache = (
                float(color[0]),
                float(color[1]),
                float(color[2]),
            )

        def _commit(self) -> None:
            if self._suspend_write:
                return
            _write_stops_to_node(self._node, self._ramp.stops())
            self._serialized_cache = _serialize_stops(self._ramp.stops())

        def _on_selection_changed(self, *_args) -> None:
            if self._suspend_write:
                return
            self._remove_btn.setEnabled(len(self._ramp.stops()) > 1)
            self._sync_selected_knobs_to_node()

        def _on_stops_changed(self, *_args) -> None:
            self._remove_btn.setEnabled(len(self._ramp.stops()) > 1)
            self._sync_selected_knobs_to_node()
            self._commit()

        def _poll_node_state(self) -> None:
            if self._suspend_write:
                return

            serialized_knob = self._node.knob(_SERIALIZED_KNOB)
            index_knob = self._node.knob("color_ramp_selected_index")

            serialized = ""
            if serialized_knob is not None:
                try:
                    serialized = str(serialized_knob.value())
                except Exception:
                    serialized = ""

            node_index = self._selected_index_cache
            if index_knob is not None:
                try:
                    node_index = int(index_knob.value())
                except Exception:
                    node_index = self._selected_index_cache

            node_pos = self._read_node_pos_knob()
            node_color = self._read_node_color_knob()
            node_interpolation = self._read_node_interpolation_knob()
            if node_interpolation != self._interpolation_cache:
                self._ramp.set_interpolation_mode(node_interpolation)
                self._interpolation_cache = node_interpolation

            # Serialized ramp changes (preset apply/import) must be consumed first.
            # If we handle knob deltas before this, we can accidentally write old stops back.
            if serialized != self._serialized_cache:
                self._suspend_write = True
                try:
                    self._ramp.set_stops(_read_stops_from_node(self._node))
                    stop_count = len(self._ramp.stops())
                    if stop_count > 0:
                        self._ramp.set_selected_index(max(0, min(node_index, stop_count - 1)))
                    self._remove_btn.setEnabled(stop_count > 1)
                finally:
                    self._suspend_write = False

                self._serialized_cache = _serialize_stops(self._ramp.stops())
                self._selected_index_cache = self._ramp.selected_index()
                selected_stop = self._selected_stop()
                self._pos_cache = float(selected_stop["pos"])
                self._color_cache = tuple(float(c) for c in selected_stop["color"])  # type:ignore[index]
                self._interpolation_cache = self._read_node_interpolation_knob()
                self._ramp.set_interpolation_mode(self._interpolation_cache)
                return

            knobs_changed = (
                abs(node_pos - self._pos_cache) > 1e-6
                or abs(node_color[0] - self._color_cache[0]) > 1e-6
                or abs(node_color[1] - self._color_cache[1]) > 1e-6
                or abs(node_color[2] - self._color_cache[2]) > 1e-6
            )

            if knobs_changed:
                self._suspend_write = True
                try:
                    stop_count = len(self._ramp.stops())
                    if stop_count > 0:
                        clamped_idx = max(0, min(int(node_index), stop_count - 1))
                        self._ramp.set_selected_index(clamped_idx)
                        self._ramp.set_selected_pos(node_pos)
                        self._ramp.set_selected_color(node_color)
                finally:
                    self._suspend_write = False

                _write_stops_to_node(self._node, self._ramp.stops())
                self._serialized_cache = _serialize_stops(self._ramp.stops())
                self._selected_index_cache = self._ramp.selected_index()
                self._pos_cache = node_pos
                self._color_cache = node_color
                self._remove_btn.setEnabled(len(self._ramp.stops()) > 1)
                return

            if serialized == self._serialized_cache and node_index == self._selected_index_cache:
                return

            self._suspend_write = True
            try:
                self._ramp.set_stops(_read_stops_from_node(self._node))
                stop_count = len(self._ramp.stops())
                if stop_count > 0:
                    self._ramp.set_selected_index(max(0, min(node_index, stop_count - 1)))
                self._remove_btn.setEnabled(stop_count > 1)
            finally:
                self._suspend_write = False

            self._serialized_cache = _serialize_stops(self._ramp.stops())
            self._selected_index_cache = self._ramp.selected_index()
            selected_stop = self._selected_stop()
            self._pos_cache = float(selected_stop["pos"])
            self._color_cache = tuple(float(c) for c in selected_stop["color"])  # type:ignore[index]
            self._interpolation_cache = self._read_node_interpolation_knob()
            self._ramp.set_interpolation_mode(self._interpolation_cache)


    class _PresetEditorWidget(QtWidgets.QWidget):
        def __init__(self, node, parent=None):
            super().__init__(parent)
            self._node = node

            root = QtWidgets.QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(6)

            row1 = QtWidgets.QHBoxLayout()
            row1.setSpacing(6)
            row1.addWidget(QtWidgets.QLabel("Preset"))

            self._preset_combo = QtWidgets.QComboBox()
            self._preset_combo.setMinimumWidth(170)
            row1.addWidget(self._preset_combo)

            self._preset_apply_btn = QtWidgets.QPushButton("Apply")
            self._preset_apply_btn.setFixedWidth(64)
            row1.addWidget(self._preset_apply_btn)

            self._preset_fav_btn = QtWidgets.QPushButton("Fav")
            self._preset_fav_btn.setFixedWidth(56)
            row1.addWidget(self._preset_fav_btn)

            row1.addStretch(1)
            root.addLayout(row1)

            row2 = QtWidgets.QHBoxLayout()
            row2.setSpacing(6)

            self._preset_save_btn = QtWidgets.QPushButton("Save")
            self._preset_save_btn.setFixedWidth(60)
            row2.addWidget(self._preset_save_btn)

            self._preset_rename_btn = QtWidgets.QPushButton("Rename")
            self._preset_rename_btn.setFixedWidth(70)
            row2.addWidget(self._preset_rename_btn)

            self._preset_delete_btn = QtWidgets.QPushButton("Delete")
            self._preset_delete_btn.setFixedWidth(64)
            row2.addWidget(self._preset_delete_btn)

            self._preset_import_btn = QtWidgets.QPushButton("Import")
            self._preset_import_btn.setFixedWidth(66)
            row2.addWidget(self._preset_import_btn)

            self._preset_export_sel_btn = QtWidgets.QPushButton("Export Sel")
            self._preset_export_sel_btn.setFixedWidth(82)
            row2.addWidget(self._preset_export_sel_btn)

            self._preset_export_btn = QtWidgets.QPushButton("Export All")
            self._preset_export_btn.setFixedWidth(82)
            row2.addWidget(self._preset_export_btn)

            row2.addStretch(1)
            root.addLayout(row2)

            self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
            self._preset_apply_btn.clicked.connect(self._apply_selected_preset)
            self._preset_fav_btn.clicked.connect(self._on_toggle_favorite)
            self._preset_save_btn.clicked.connect(self._on_save_preset)
            self._preset_rename_btn.clicked.connect(self._on_rename_preset)
            self._preset_delete_btn.clicked.connect(self._on_delete_preset)
            self._preset_import_btn.clicked.connect(self._on_import_presets)
            self._preset_export_sel_btn.clicked.connect(self._on_export_selected_preset)
            self._preset_export_btn.clicked.connect(self._on_export_presets)

            self._refresh_preset_combo("Grayscale")
            self._update_buttons_state()

        def _refresh_preset_combo(self, selected_name: str) -> None:
            current = _clean_preset_name(selected_name)
            self._preset_combo.blockSignals(True)
            self._preset_combo.clear()
            names = _preset_names()
            for raw_name in names:
                self._preset_combo.addItem(_display_preset_name(raw_name), raw_name)
            target = current if current else (names[0] if names else "")
            if target:
                for i in range(self._preset_combo.count()):
                    if _clean_preset_name(self._preset_combo.itemData(i)) == target:
                        self._preset_combo.setCurrentIndex(i)
                        break
            self._preset_combo.blockSignals(False)
            self._update_buttons_state()

        def _selected_preset_name(self) -> str:
            raw = self._preset_combo.currentData()
            if raw is not None:
                cleaned = _clean_preset_name(raw)
                if cleaned:
                    return cleaned
            return _clean_preset_name(self._preset_combo.currentText())

        def _update_buttons_state(self) -> None:
            selected = self._selected_preset_name()
            is_custom = _is_custom_preset(selected)
            is_favorite = _is_favorite_preset(selected)
            self._preset_rename_btn.setEnabled(is_custom)
            self._preset_delete_btn.setEnabled(is_custom)
            self._preset_export_sel_btn.setEnabled(bool(selected))
            self._preset_fav_btn.setText("Unfav" if is_favorite else "Fav")

        def _on_preset_selected(self, _index: int) -> None:
            self._update_buttons_state()
            self._apply_selected_preset()

        def _apply_selected_preset(self) -> None:
            name = self._selected_preset_name()
            stops = _preset_stops(name)
            if not _write_stops_to_node(self._node, stops):
                nuke.message("Unable to apply preset on this node.")
                return
            idx_knob = self._node.knob("color_ramp_selected_index")
            if idx_knob is not None:
                try:
                    idx_knob.setValue(0)
                except Exception:
                    pass

        def _on_save_preset(self) -> None:
            name, ok = QtWidgets.QInputDialog.getText(self, "Save Ramp Preset", "Preset name:")
            if not ok:
                return
            stops = _read_stops_from_node(self._node)
            if not _save_custom_preset(str(name), stops):
                nuke.message("Unable to save preset.")
                return
            self._refresh_preset_combo(_clean_preset_name(name))

        def _on_rename_preset(self) -> None:
            current = self._selected_preset_name()
            if not _is_custom_preset(current):
                nuke.message("Only custom presets can be renamed.")
                return
            new_name, ok = QtWidgets.QInputDialog.getText(
                self,
                "Rename Ramp Preset",
                "New preset name:",
                text=current,
            )
            if not ok:
                return
            new_key = _clean_preset_name(new_name)
            if not new_key or new_key == current:
                return
            if _is_custom_preset(new_key) and new_key != current:
                if not nuke.ask("Preset '{}' exists. Replace it?".format(new_key)):
                    return
                _CUSTOM_PRESETS.pop(new_key, None)
                _FAVORITE_PRESETS.discard(new_key)
            if not _rename_custom_preset(current, new_key):
                nuke.message("Unable to rename preset.")
                return
            self._refresh_preset_combo(new_key)

        def _on_delete_preset(self) -> None:
            current = self._selected_preset_name()
            if not _is_custom_preset(current):
                nuke.message("Only custom presets can be deleted.")
                return
            if not nuke.ask("Delete preset '{}' ?".format(current)):
                return
            if not _delete_custom_preset(current):
                nuke.message("Unable to delete preset.")
                return
            fallback = _preset_names()[0] if _preset_names() else ""
            self._refresh_preset_combo(fallback)

        def _on_toggle_favorite(self) -> None:
            current = self._selected_preset_name()
            target_state = not _is_favorite_preset(current)
            if not _set_favorite_preset(current, target_state):
                nuke.message("Unable to update favorite state.")
                return
            self._refresh_preset_combo(current)

        def _on_import_presets(self) -> None:
            file_path = None
            try:
                file_path = nuke.getFilename("Import TColorRamp Presets", "*.json")
            except Exception:
                file_path = None
            if not file_path:
                return
            imported = _import_presets_from_file(file_path)
            if not imported:
                nuke.message("No valid presets found in file.")
                return
            self._refresh_preset_combo(imported[0])
            self._apply_selected_preset()
            nuke.message("Imported {} preset(s).".format(len(imported)))

        def _pick_export_path(self) -> str:
            file_path = None
            try:
                file_path = nuke.getFilename(
                    "Export TColorRamp Presets",
                    "*.json",
                    "tcolorramp_presets.json",
                )
            except Exception:
                file_path = None
            if not file_path:
                return ""
            if not str(file_path).lower().endswith(".json"):
                file_path = "{}.json".format(file_path)
            return str(file_path)

        def _on_export_selected_preset(self) -> None:
            current = self._selected_preset_name()
            if not current:
                return
            file_path = self._pick_export_path()
            if not file_path:
                return
            if not _export_presets_to_file(file_path, [current]):
                nuke.message("Unable to export selected preset.")
                return
            nuke.message("Exported selected preset '{}'.".format(current))

        def _on_export_presets(self) -> None:
            file_path = self._pick_export_path()
            if not file_path:
                return
            names = _preset_names()
            if not _export_presets_to_file(file_path, names):
                nuke.message("Unable to export presets.")
                return
            nuke.message("Exported {} preset(s).".format(len(names)))


def _context_node():
    try:
        node = nuke.thisNode()
        if node is not None:
            return node
    except Exception:
        pass
    try:
        knob = nuke.thisKnob()
        if knob is not None and hasattr(knob, "node"):
            return knob.node()
    except Exception:
        pass
    return None


class TColorRampInlineKnob:
    """Bridge object used by Nuke PythonKnob to create the inline ramp UI."""

    def makeUI(self):
        if QtWidgets is None:
            return None
        node = _context_node()
        if node is None or node.knob(_SERIALIZED_KNOB) is None:
            return QtWidgets.QLabel("TColorRamp node context not available.")
        try:
            return _InlineRampEditorWidget(node)
        except Exception as error:
            try:
                nuke.tprint("TColorRamp inline UI failed: {}".format(error))
            except Exception:
                pass
            return QtWidgets.QLabel("TColorRamp inline UI error. See Script Editor.")


class TColorRampPresetKnob:
    """Bridge object used by Nuke PythonKnob to create the presets UI."""

    def makeUI(self):
        if QtWidgets is None:
            return None
        node = _context_node()
        if node is None or node.knob(_SERIALIZED_KNOB) is None:
            return QtWidgets.QLabel("TColorRamp node context not available.")
        return _PresetEditorWidget(node)
