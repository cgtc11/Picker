# -*- coding: utf-8 -*-
import json
import os
import math
import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore, QtGui

# --- スタイル設定 ---
STYLESHEET = """
    QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: 'Segoe UI', sans-serif; font-size: 12px; }
    QGroupBox { border: 1px solid #3a3a3a; margin-top: 10px; padding-top: 10px; font-weight: bold; }
    QPushButton { background-color: #3f3f3f; border: 1px solid #555; border-radius: 3px; padding: 2px; color: #ffffff; }
    QPushButton:hover { background-color: #4f4f4f; }
    QLineEdit { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333; padding: 2px; }
    QLineEdit:disabled { color: #666; background-color: #222; }
    QComboBox { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333; }
    QComboBox:disabled { color: #666; }
    QListWidget { background-color: #1a1a1a; border: 1px solid #333; outline: none; }
    QListWidget::item:selected { background-color: #3d5a73; }
    QLabel#DragLabel { color: #888; font-weight: bold; }
    QLabel#DragLabel:hover { color: #aaa; }
"""

SHAPE_TYPES = [
    "rect", "rect_fill", "circle", "circle_fill", "cross", 
    "diamond", "diamond_fill", "tri_up", "tri_up_fill", 
    "tri_down", "tri_down_fill", "tri_left", "tri_left_fill", 
    "tri_right", "tri_right_fill", "double_circle", "star", "star_fill"
]

# --- ヘルパー関数: 図形描画 ---
def draw_shape(painter, t, sr, color, is_selected):
    painter.setPen(QtGui.QPen(color, 4 if is_selected else 1))
    if t == "rect": painter.drawRect(sr)
    elif t == "rect_fill": painter.fillRect(sr, color)
    elif t == "circle": painter.drawEllipse(sr)
    elif t == "circle_fill":
        painter.setBrush(color); painter.drawEllipse(sr); painter.setBrush(QtCore.Qt.NoBrush)
    elif t == "cross":
        cx, cy = sr.center().x(), sr.center().y()
        painter.drawLine(sr.left(), cy, sr.right(), cy); painter.drawLine(cx, sr.top(), cx, sr.bottom())
    elif "diamond" in t:
        poly = QtGui.QPolygon([QtCore.QPoint(sr.center().x(), sr.top()), QtCore.QPoint(sr.right(), sr.center().y()), QtCore.QPoint(sr.center().x(), sr.bottom()), QtCore.QPoint(sr.left(), sr.center().y())])
        if "fill" in t: painter.setBrush(color)
        painter.drawPolygon(poly); painter.setBrush(QtCore.Qt.NoBrush)
    elif "tri_" in t:
        if "up" in t: pts = [sr.bottomLeft(), sr.bottomRight(), QtCore.QPoint(sr.center().x(), sr.top())]
        elif "down" in t: pts = [sr.topLeft(), sr.topRight(), QtCore.QPoint(sr.center().x(), sr.bottom())]
        elif "left" in t: pts = [sr.topRight(), sr.bottomRight(), QtCore.QPoint(sr.left(), sr.center().y())]
        elif "right" in t: pts = [sr.topLeft(), sr.bottomLeft(), QtCore.QPoint(sr.right(), sr.center().y())]
        poly = QtGui.QPolygon(pts); (painter.setBrush(color) if "fill" in t else None); painter.drawPolygon(poly); painter.setBrush(QtCore.Qt.NoBrush)
    elif t == "double_circle":
        painter.drawEllipse(sr)
        inner = sr.adjusted(sr.width()*0.2, sr.height()*0.2, -sr.width()*0.2, -sr.height()*0.2); painter.drawEllipse(inner)
    elif "star" in t:
        poly = QtGui.QPolygon(); center = sr.center(); ro = min(sr.width(), sr.height())/2; ri = ro/2.5
        for j in range(10):
            r = ro if j%2==0 else ri; angle = (j*36-90)*math.pi/180; poly << QtCore.QPoint(center.x()+r*math.cos(angle), center.y()+r*math.sin(angle))
        if "fill" in t: painter.setBrush(color)
        painter.drawPolygon(poly); painter.setBrush(QtCore.Qt.NoBrush)
    else: painter.drawRect(sr)

def create_shape_icon(shape_type, color=QtCore.Qt.white):
    pixmap = QtGui.QPixmap(20, 20); pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap); painter.setRenderHint(QtGui.QPainter.Antialiasing)
    draw_shape(painter, shape_type, QtCore.QRect(2, 2, 16, 16), QtGui.QColor(color), False)
    painter.end(); return QtGui.QIcon(pixmap)

class DragLabel(QtWidgets.QLabel):
    def __init__(self, text, target_spin, parent=None):
        super().__init__(text, parent)
        self.setObjectName("DragLabel"); self.target_spin = target_spin; self.setCursor(QtCore.Qt.SizeHorCursor); self.last_x = 0
    def mousePressEvent(self, event): self.last_x = event.globalPos().x()
    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton:
            dx = event.globalPos().x() - self.last_x
            self.target_spin.setValue(self.target_spin.value() + dx); self.last_x = event.globalPos().x()

class ClickRegion:
    def __init__(self, names, rect_data, color, shape_type="rect", next_json=""):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)
        self.shape_type = shape_type
        self.next_json = next_json

class ListColorItem(QtWidgets.QWidget):
    color_changed = QtCore.Signal(int, QtGui.QColor); rect_changed = QtCore.Signal(int, str, int); names_changed = QtCore.Signal(int, list); type_changed = QtCore.Signal(int, str); next_json_changed = QtCore.Signal(int, str)
    def __init__(self, names, rect, color, shape_type, next_json, index, parent=None):
        super().__init__(parent)
        self.index = index; self.block_signals = False
        layout = QtWidgets.QHBoxLayout(self); layout.setContentsMargins(0, 2, 5, 2); layout.setSpacing(3)
        layout.addSpacing(40) # リスト左側の余白
        
        display_text = os.path.basename(next_json) if next_json else ", ".join(names)
        self.names_edit = QtWidgets.QLineEdit(display_text); self.names_edit.editingFinished.connect(self.on_ui_data_changed); layout.addWidget(self.names_edit, 1)

        self.btn_path = QtWidgets.QPushButton("..."); self.btn_path.setFixedWidth(22); self.btn_path.clicked.connect(self.browse_path); layout.addWidget(self.btn_path)
        
        self.type_combo = QtWidgets.QComboBox(); self.type_combo.setIconSize(QtCore.QSize(16, 16)); self.type_combo.setFixedWidth(55)
        for st in SHAPE_TYPES: self.type_combo.addItem(create_shape_icon(st, color), "", st)
        if shape_type in SHAPE_TYPES: self.type_combo.setCurrentIndex(SHAPE_TYPES.index(shape_type))
        self.type_combo.currentIndexChanged.connect(self.on_type_ui_changed); layout.addWidget(self.type_combo)

        self.spins = {}; self.labels = []
        for lbl_t, key in [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]:
            sb = QtWidgets.QSpinBox(); sb.setButtonSymbols(QtWidgets.QSpinBox.NoButtons); sb.setRange(-20000, 20000); sb.setFixedWidth(40)
            sb.valueChanged.connect(lambda val, k=key: self.on_rect_ui_changed(k, val))
            lbl = DragLabel(lbl_t, sb); lbl.setFixedWidth(12); self.labels.append(lbl); layout.addWidget(lbl); layout.addWidget(sb); self.spins[key] = sb
        
        self.sync_spins(rect)
        self.color_btn = QtWidgets.QPushButton("■"); self.color_btn.setFixedSize(20, 20)
        self.set_btn_color(color); self.color_btn.clicked.connect(self.pick_new_color); layout.addWidget(self.color_btn)

    def browse_path(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select JSON", "", "*.json")
        if p: rel = os.path.basename(p); self.names_edit.setText(rel); self.on_ui_data_changed()

    def on_ui_data_changed(self):
        text = self.names_edit.text()
        if text.endswith(".json"):
            rel = os.path.basename(text); (self.names_edit.setText(rel) if text != rel else None)
            self.next_json_changed.emit(self.index, rel); self.names_changed.emit(self.index, [])
        else:
            self.next_json_changed.emit(self.index, ""); self.names_changed.emit(self.index, [n.strip() for n in text.split(",") if n.strip()])

    def sync_spins(self, rect):
        self.block_signals = True; self.spins["x"].setValue(rect.x()); self.spins["y"].setValue(rect.y()); self.spins["w"].setValue(rect.width()); self.spins["h"].setValue(rect.height()); self.block_signals = False

    def on_rect_ui_changed(self, k, v): (self.rect_changed.emit(self.index, k, v) if not self.block_signals else None)
    def on_type_ui_changed(self, idx): (self.type_changed.emit(self.index, SHAPE_TYPES[idx]) if not self.block_signals else None)
    def set_btn_color(self, c):
        self.current_color = c; self.color_btn.setStyleSheet(f"color: {c.name()}; background-color: #2b2b2b; border: 1px solid #555;")
        self.block_signals = True
        for i in range(self.type_combo.count()): self.type_combo.setItemIcon(i, create_shape_icon(SHAPE_TYPES[i], c))
        self.block_signals = False

    def pick_new_color(self):
        c = QtWidgets.QColorDialog.getColor(self.current_color, self, "Color", QtWidgets.QColorDialog.ShowAlphaChannel)
        if c.isValid(): self.set_btn_color(c); self.color_changed.emit(self.index, c)
    def set_edit_enabled(self, e):
        self.names_edit.setEnabled(e); self.color_btn.setEnabled(e); self.type_combo.setEnabled(e); self.btn_path.setEnabled(e)
        for sb in self.spins.values(): sb.setEnabled(e)
        for lb in self.labels: lb.setEnabled(e)

class ImageCanvas(QtWidgets.QLabel):
    request_deselect = QtCore.Signal(bool); region_clicked = QtCore.Signal(int, bool)
    multi_region_moved = QtCore.Signal(list, int, int); file_dropped = QtCore.Signal(str); pan_requested = QtCore.Signal(QtCore.QPoint)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_pos = None; self.temp_rect = QtCore.QRect(); self.registered_items = []
        self.mode = "setup"; self.scale = 1.0; self.pixmap_original = None; self.last_pan_pos = None 
        self.selected_indices = set(); self.is_dragging_items = False; self.drag_start_pt = None
        self.setMouseTracking(True); self.setAcceptDrops(True); self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a; color: #555; border: 2px dashed #333;"); self.setText("DROP IMAGE OR JSON")
    def set_image(self, pix):
        self.pixmap_original = pix; self.scale = 1.0; self.update_canvas_size()
        self.setStyleSheet("background-color: #111; border: none;"); self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
    def update_canvas_size(self):
        if self.pixmap_original: ns = self.pixmap_original.size() * self.scale; self.setPixmap(self.pixmap_original.scaled(ns, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)); self.setFixedSize(ns)
    def paintEvent(self, event):
        super().paintEvent(event); painter = QtGui.QPainter(self); painter.setRenderHint(QtGui.QPainter.Antialiasing)
        for i, item in enumerate(self.registered_items):
            sr = QtCore.QRect(item.rect.x()*self.scale, item.rect.y()*self.scale, item.rect.width()*self.scale, item.rect.height()*self.scale)
            draw_shape(painter, item.shape_type, sr, item.color, i in self.selected_indices)
        if self.mode == "setup" and not self.temp_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.red, 1, QtCore.Qt.DashLine)); painter.drawRect(self.temp_rect)
    def mousePressEvent(self, event):
        mod = event.modifiers(); pos = event.pos(); raw = pos / self.scale; is_mod = bool(mod & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier))
        if event.button() == QtCore.Qt.MiddleButton or (event.button() == QtCore.Qt.LeftButton and mod & QtCore.Qt.AltModifier):
            self.last_pan_pos = event.globalPos(); self.setCursor(QtCore.Qt.ClosedHandCursor); return
        idx = next((i for i, r in enumerate(self.registered_items) if r.rect.contains(raw)), -1)
        if idx != -1:
            item = self.registered_items[idx]
            if self.mode == "selector" and item.next_json and not is_mod: 
                target = item.next_json
                if not os.path.isabs(target) and self.window().current_json_path: target = os.path.join(os.path.dirname(self.window().current_json_path), target)
                self.window().load_json(target); return
            if self.mode == "setup" and not is_mod:
                if idx not in self.selected_indices: self.region_clicked.emit(idx, False)
                self.is_dragging_items = True; self.drag_start_pt = raw
            else:
                self.region_clicked.emit(idx, is_mod)
                if self.mode == "selector" and not item.next_json: cmds.select(item.names, toggle=is_mod, replace=not is_mod)
        else:
            self.start_pos = pos if self.mode == "setup" else None; self.request_deselect.emit(is_mod)
            if self.mode == "selector" and not is_mod: cmds.select(cl=True)
    def mouseMoveEvent(self, event):
        if self.last_pan_pos: d = event.globalPos() - self.last_pan_pos; self.pan_requested.emit(d); self.last_pan_pos = event.globalPos(); return
        if self.is_dragging_items and self.drag_start_pt:
            raw = event.pos()/self.scale; dx, dy = int(raw.x()-self.drag_start_pt.x()), int(raw.y()-self.drag_start_pt.y())
            if dx!=0 or dy!=0: self.multi_region_moved.emit(list(self.selected_indices), dx, dy); self.drag_start_pt = raw; return
        if self.mode == "setup" and self.start_pos: self.temp_rect = QtCore.QRect(self.start_pos, event.pos()).normalized(); self.update()
    def mouseReleaseEvent(self, event): self.start_pos = self.last_pan_pos = None; self.is_dragging_items = False; self.setCursor(QtCore.Qt.ArrowCursor); self.temp_rect = QtCore.QRect(); self.update()
    def wheelEvent(self, event): self.scale *= (1.1 if event.angleDelta().y() > 0 else 0.9); self.scale = max(0.1, min(self.scale, 10.0)); self.update_canvas_size(); self.update()
    def dragEnterEvent(self, e): (e.acceptProposedAction() if e.mimeData().hasUrls() else None)
    def dropEvent(self, e):
        for u in e.mimeData().urls(): self.file_dropped.emit(u.toLocalFile())
        e.acceptProposedAction()

class MayaPickerEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Maya Picker Editor"); self.resize(1100, 750); self.setStyleSheet(STYLESHEET)
        
        # ウィンドウアイコン
        icon_path = os.path.join(os.path.dirname(__file__), "PickerEditor.png")
        if os.path.exists(icon_path): self.setWindowIcon(QtGui.QIcon(icon_path))

        self.current_json_path = ""; self.last_used_color = QtGui.QColor(255, 255, 255, 255)
        main_layout = QtWidgets.QVBoxLayout(self); self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        left_w = QtWidgets.QWidget(); left_v = QtWidgets.QVBoxLayout(left_w)
        self.scroll = QtWidgets.QScrollArea(); self.scroll.setWidgetResizable(True); self.canvas = ImageCanvas(); self.scroll.setWidget(self.canvas); left_v.addWidget(self.scroll)
        self.btn_mode = QtWidgets.QPushButton("Switch to SELECTOR Mode"); self.btn_mode.setCheckable(True); self.btn_mode.setFixedHeight(40); self.btn_mode.toggled.connect(self.toggle_mode); left_v.addWidget(self.btn_mode)

        right_w = QtWidgets.QWidget(); right_v = QtWidgets.QVBoxLayout(right_w)
        self.setup_group = QtWidgets.QGroupBox("Registration"); setup_v = QtWidgets.QVBoxLayout(self.setup_group)
        rep_h = QtWidgets.QHBoxLayout(); self.edit_f = QtWidgets.QLineEdit(); self.edit_r = QtWidgets.QLineEdit(); btn_rep = QtWidgets.QPushButton("Replace All")
        btn_rep.clicked.connect(self.batch_replace); rep_h.addWidget(self.edit_f); rep_h.addWidget(self.edit_r); rep_h.addWidget(btn_rep); setup_v.addLayout(rep_h)
        self.list_widget = QtWidgets.QListWidget(); self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection); self.list_widget.itemSelectionChanged.connect(self.on_list_selection_changed); setup_v.addWidget(self.list_widget)
        get_h = QtWidgets.QHBoxLayout(); self.edit_names = QtWidgets.QLineEdit(); btn_get = QtWidgets.QPushButton("Get Selected")
        btn_get.clicked.connect(lambda: self.edit_names.setText(", ".join(cmds.ls(sl=True)))); get_h.addWidget(self.edit_names); get_h.addWidget(btn_get); setup_v.addLayout(get_h)
        right_v.addWidget(self.setup_group)

        self.btn_reg = QtWidgets.QPushButton("Register Area"); self.btn_reg.setFixedHeight(30); self.btn_reg.clicked.connect(self.do_register)
        self.btn_del = QtWidgets.QPushButton("Delete Selected"); self.btn_del.setFixedHeight(30); self.btn_del.clicked.connect(self.delete_items); right_v.addWidget(self.btn_reg); right_v.addWidget(self.btn_del)
        file_h = QtWidgets.QHBoxLayout(); btn_save = QtWidgets.QPushButton("Save JSON"); btn_load = QtWidgets.QPushButton("Load JSON")
        btn_save.clicked.connect(self.save_json); btn_load.clicked.connect(lambda: self.load_json()); file_h.addWidget(btn_save); file_h.addWidget(btn_load); right_v.addLayout(file_h)
        
        self.splitter.addWidget(left_w); self.splitter.addWidget(right_w); self.splitter.setSizes([300, 800]); main_layout.addWidget(self.splitter)
        self.canvas.request_deselect.connect(lambda mod: (self.list_widget.clearSelection() if not mod else None))
        self.canvas.region_clicked.connect(self.handle_canvas_region_click); self.canvas.multi_region_moved.connect(self.handle_multi_move); self.canvas.file_dropped.connect(self.handle_drop_file); self.canvas.pan_requested.connect(self.handle_pan)

    def on_list_selection_changed(self): self.canvas.selected_indices = {i.row() for i in self.list_widget.selectedIndexes()}; self.canvas.update()
    def handle_canvas_region_click(self, row, is_mod):
        it = self.list_widget.item(row); (it.setSelected(not it.isSelected()) if is_mod else (self.list_widget.clearSelection(), self.list_widget.setCurrentRow(row), it.setSelected(True)) if it else None)
    def handle_multi_move(self, rows, dx, dy):
        for r in rows:
            reg = self.canvas.registered_items[r]; reg.rect.translate(dx, dy); w = self.list_widget.itemWidget(self.list_widget.item(r)); (w.sync_spins(reg.rect) if w else None)
        self.canvas.update()
    def handle_pan(self, d): self.scroll.horizontalScrollBar().setValue(self.scroll.horizontalScrollBar().value()-d.x()); self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value()-d.y())
    
    def handle_drop_file(self, p):
        ext = os.path.splitext(p)[1].lower()
        if ext in [".png", ".jpg", ".jpeg"]:
            self.canvas.set_image(QtGui.QPixmap(p)); self.scroll.setWidgetResizable(False)
            json_path = os.path.splitext(p)[0] + ".json"
            if os.path.exists(json_path): self.load_json(json_path)
        elif ext == ".json": self.load_json(p)

    def batch_replace(self):
        f, r = self.edit_f.text(), self.edit_r.text()
        if f:
            for i, reg in enumerate(self.canvas.registered_items):
                if not reg.next_json:
                    reg.names = [n.replace(f, r) for n in reg.names]
                    w = self.list_widget.itemWidget(self.list_widget.item(i)); (w.names_edit.setText(", ".join(reg.names)) if w else None)
    
    def do_register(self):
        s = self.canvas.scale; r = self.canvas.temp_rect; raw = [int(r.x()/s), int(r.y()/s), int(r.width()/s), int(r.height()/s)] if not r.isNull() else [10, 10, 50, 50]
        names = [n.strip() for n in self.edit_names.text().split(",") if n.strip()] or ["Control"]
        reg = ClickRegion(names, raw, self.last_used_color); self.canvas.registered_items.append(reg); self.add_list_item(reg.names, reg.rect, reg.color, reg.shape_type); self.canvas.update()

    def add_list_item(self, names, rect, color, shape_type, next_json=""):
        it = QtWidgets.QListWidgetItem(self.list_widget); w = ListColorItem(names, rect, color, shape_type, next_json, self.list_widget.count()-1)
        w.names_changed.connect(lambda i, n: setattr(self.canvas.registered_items[i], 'names', n)); w.rect_changed.connect(self.handle_rect_sync); w.color_changed.connect(self.handle_color_sync); w.type_changed.connect(self.handle_type_sync); w.next_json_changed.connect(lambda i, p: setattr(self.canvas.registered_items[i], 'next_json', p))
        it.setSizeHint(w.sizeHint()); self.list_widget.addItem(it); self.list_widget.setItemWidget(it, w)
        w.set_edit_enabled(not self.btn_mode.isChecked())

    # --- 複数選択同期ロジック ---
    def handle_rect_sync(self, idx, k, v):
        sel_rows = [i.row() for i in self.list_widget.selectedIndexes()]
        targets = sel_rows if idx in sel_rows else [idx]
        for r in targets:
            reg = self.canvas.registered_items[r]; rect = list(reg.rect.getRect())
            rect[{"x":0,"y":1,"w":2,"h":3}[k]] = v; reg.rect = QtCore.QRect(*rect)
            w = self.list_widget.itemWidget(self.list_widget.item(r))
            if w and r != idx:
                w.block_signals = True; w.spins[k].setValue(v); w.block_signals = False
        self.canvas.update()

    def handle_color_sync(self, idx, c):
        self.last_used_color = c
        sel_rows = [i.row() for i in self.list_widget.selectedIndexes()]
        targets = sel_rows if idx in sel_rows else [idx]
        for r in targets:
            self.canvas.registered_items[r].color = c
            w = self.list_widget.itemWidget(self.list_widget.item(r))
            if w and r != idx: w.set_btn_color(c)
        self.canvas.update()

    def handle_type_sync(self, idx, t):
        sel_rows = [i.row() for i in self.list_widget.selectedIndexes()]
        targets = sel_rows if idx in sel_rows else [idx]
        for r in targets:
            self.canvas.registered_items[r].shape_type = t
            w = self.list_widget.itemWidget(self.list_widget.item(r))
            if w and r != idx:
                w.block_signals = True; w.type_combo.setCurrentIndex(SHAPE_TYPES.index(t)); w.block_signals = False
        self.canvas.update()

    def delete_items(self):
        for r in sorted([self.list_widget.row(it) for it in self.list_widget.selectedItems()], reverse=True): self.list_widget.takeItem(r); self.canvas.registered_items.pop(r)
        for i in range(self.list_widget.count()): (setattr(self.list_widget.itemWidget(self.list_widget.item(i)), 'index', i) if self.list_widget.itemWidget(self.list_widget.item(i)) else None)
        self.canvas.update()

    def toggle_mode(self, checked):
        self.canvas.mode = "selector" if checked else "setup"; self.setup_group.setEnabled(not checked); self.btn_reg.setEnabled(not checked); self.btn_del.setEnabled(not checked)
        for i in range(self.list_widget.count()): (self.list_widget.itemWidget(self.list_widget.item(i)).set_edit_enabled(not checked) if self.list_widget.itemWidget(self.list_widget.item(i)) else None)

    def save_json(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save JSON", self.current_json_path, "*.json")
        if p:
            lines = []
            for i in self.canvas.registered_items:
                path = os.path.basename(i.next_json) if i.next_json else ""
                # 辞書の作成順序を明示
                d = {}
                d["names"] = i.names
                d["rect"] = list(i.rect.getRect())
                d["color"] = list(i.color.getRgb())
                d["shape_type"] = i.shape_type
                d["next_json"] = path
                lines.append(json.dumps(d, ensure_ascii=False))
            with open(p, 'w', encoding='utf-8') as f:
                f.write("[\n" + ",\n".join(lines) + "\n]")
            self.current_json_path = p

    def load_json(self, p=None):
        if not p: p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open JSON", self.current_json_path, "*.json")
        if p and os.path.exists(p):
            self.current_json_path = p; base_dir = os.path.dirname(p)
            with open(p, 'r', encoding='utf-8') as f: data = json.load(f)
            self.canvas.registered_items = []; self.list_widget.clear()
            for d in data:
                path = d.get("next_json", ""); rel = os.path.basename(path) if path else ""
                full = os.path.join(base_dir, rel) if rel else ""
                reg = ClickRegion(d.get("names", []), d["rect"], d["color"], d.get("shape_type", "rect"), full)
                self.canvas.registered_items.append(reg); self.add_list_item(reg.names, reg.rect, reg.color, reg.shape_type, rel)
            self.canvas.update()

maya_picker_editor_instance = None
def show():
    global maya_picker_editor_instance
    try: (maya_picker_editor_instance.close(), maya_picker_editor_instance.deleteLater()) if maya_picker_editor_instance else None
    except: pass
    parent = next((w for w in QtWidgets.QApplication.topLevelWidgets() if w.objectName() == "MayaWindow"), None)
    maya_picker_editor_instance = MayaPickerEditor(parent=parent)
    if parent: maya_picker_editor_instance.setWindowFlags(QtCore.Qt.Window)
    maya_picker_editor_instance.show()

if __name__ == "__main__": show()