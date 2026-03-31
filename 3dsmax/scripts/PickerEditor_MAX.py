# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

# --- スタイル設定 ---
STYLESHEET = """
    QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: 'Segoe UI', sans-serif; font-size: 12px; }
    QWidget:disabled { color: #666666; }
    QGroupBox { border: 1px solid #3a3a3a; margin-top: 15px; padding-top: 10px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #aaaaaa; }
    QPushButton { background-color: #3f3f3f; border: 1px solid #555; border-radius: 3px; padding: 3px; color: #ffffff; }
    QPushButton:hover { background-color: #4f4f4f; }
    QPushButton:disabled { background-color: #2a2a2a; color: #666; border: 1px solid #333; }
    QLineEdit { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333; padding: 2px; }
    QListWidget { background-color: #1a1a1a; border: 1px solid #333; outline: none; }
    QListWidget::item:selected { background-color: #3d5a73; }
    QScrollArea { border: none; background-color: #1a1a1a; }
    DraggableLabel { background-color: #212121; color: #aaaaaa; font-weight: bold; border-radius: 3px; padding: 0 3px; }
"""

class MaxStyleSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setRange(-20000, 20000)
        self.setFixedWidth(45)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    def mouseReleaseEvent(self, event):
        self.selectAll()
        super().mouseReleaseEvent(event)

class DraggableLabel(QtWidgets.QLabel):
    def __init__(self, text, target_spin, parent=None):
        super().__init__(text, parent)
        self.target_spin = target_spin
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.last_mouse_pos = None
        self.setFixedWidth(18)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        if not self.isEnabled(): return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.globalPosition().toPoint()
            self.target_spin.setFocus()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos.x() - self.last_mouse_pos.x()
            if delta != 0:
                self.target_spin.setValue(self.target_spin.value() + delta)
                self.last_mouse_pos = current_pos
                event.accept()

    def mouseReleaseEvent(self, event):
        self.last_mouse_pos = None

class ListColorItem(QtWidgets.QWidget):
    color_changed = QtCore.Signal(int, QtGui.QColor)
    rect_changed = QtCore.Signal(int, str, int)
    names_changed = QtCore.Signal(int, list)

    def __init__(self, names, rect, color, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.block_signals = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 5, 2)
        layout.setSpacing(5)
        layout.addSpacing(40) 
        
        self.names_edit = QtWidgets.QLineEdit(", ".join(names))
        self.names_edit.setMinimumWidth(120)
        self.names_edit.editingFinished.connect(self.on_names_ui_changed)
        layout.addWidget(self.names_edit, 1)
        
        self.spins = {}
        for label_text, key in [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]:
            sb = MaxStyleSpinBox()
            sb.valueChanged.connect(lambda val, k=key: self.on_rect_ui_changed(k, val))
            lbl = DraggableLabel(label_text, sb)
            layout.addWidget(lbl); layout.addWidget(sb)
            self.spins[key] = sb
            
        self.sync_spins(rect)
        self.color_btn = QtWidgets.QPushButton("■")
        self.color_btn.setFixedSize(22, 22)
        self.set_btn_style(color)
        self.color_btn.clicked.connect(self.pick_new_color)
        layout.addWidget(self.color_btn)

    def sync_spins(self, rect):
        self.block_signals = True
        self.spins["x"].setValue(rect.x()); self.spins["y"].setValue(rect.y())
        self.spins["w"].setValue(rect.width()); self.spins["h"].setValue(rect.height())
        self.block_signals = False

    def on_names_ui_changed(self):
        new_list = [n.strip() for n in self.names_edit.text().split(",") if n.strip()]
        self.names_changed.emit(self.index, new_list)

    def on_rect_ui_changed(self, key, value):
        if not self.block_signals: self.rect_changed.emit(self.index, key, value)

    def set_btn_style(self, color):
        self.current_color = color
        self.color_btn.setStyleSheet(f"color: {color.name()}; font-size: 16px; background-color: #1a1a1a; border: 1px solid #555;")

    def pick_new_color(self):
        c = QtWidgets.QColorDialog.getColor(self.current_color, self)
        if c.isValid():
            self.color_changed.emit(self.index, c)

    def set_edit_enabled(self, enabled):
        self.names_edit.setEnabled(enabled); self.color_btn.setEnabled(enabled)
        for sb in self.spins.values(): sb.setEnabled(enabled)

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class ImageCanvas(QtWidgets.QLabel):
    request_deselect = QtCore.Signal(); region_clicked = QtCore.Signal(int)
    pan_requested = QtCore.Signal(QtCore.QPoint)

    def __init__(self, parent=None):
        super().__init__(parent); self.start_pos = None; self.temp_rect = QtCore.QRect()
        self.registered_items = []; self.mode = "setup"; self.selected_index = -1
        self.scale = 1.0; self.pixmap_original = None; self.last_pan_pos = None
        
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet("background-color: #1a1a1a;")

    def set_image(self, pixmap):
        self.pixmap_original = pixmap; self.scale = 1.0; self.update_canvas_size()

    def update_canvas_size(self):
        if self.pixmap_original:
            new_size = self.pixmap_original.size() * self.scale
            self.setPixmap(self.pixmap_original.scaled(new_size, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
            self.setFixedSize(new_size)

    def wheelEvent(self, event):
        if not self.pixmap_original: return
        delta = event.angleDelta().y()
        old_scale = self.scale
        if delta > 0: self.scale *= 1.1
        else: self.scale /= 1.1
        self.scale = max(0.1, min(self.scale, 10.0))
        if old_scale != self.scale:
            self.update_canvas_size(); self.update()

    def paintEvent(self, event):
        super().paintEvent(event); painter = QtGui.QPainter(self)
        for i, item in enumerate(self.registered_items):
            scaled_rect = QtCore.QRect(
                item.rect.x() * self.scale, item.rect.y() * self.scale,
                item.rect.width() * self.scale, item.rect.height() * self.scale
            )
            painter.setPen(QtGui.QPen(item.color, 4 if i == self.selected_index else 1))
            painter.drawRect(scaled_rect)
        if self.mode == "setup" and not self.temp_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.red, 2, QtCore.Qt.PenStyle.DashLine))
            painter.drawRect(self.temp_rect)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.MiddleButton or \
           (event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self.last_pan_pos = event.globalPosition().toPoint()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            return

        pos = event.position().toPoint(); raw_pos = pos / self.scale; hit = False
        for i, reg in enumerate(self.registered_items):
            if reg.rect.contains(raw_pos):
                hit = True; self.region_clicked.emit(i)
                if self.mode == "selector":
                    nodes = [mxs.getNodeByName(n) for n in reg.names if mxs.getNodeByName(n)]
                    if nodes: mxs.select(nodes)
                break
        if not hit:
            self.start_pos = pos if self.mode == "setup" else None
            self.request_deselect.emit()
            if self.mode == "selector": mxs.select(mxs.EMPTY_ARRAY)

    def mouseMoveEvent(self, event):
        if self.last_pan_pos:
            delta = event.globalPosition().toPoint() - self.last_pan_pos
            self.pan_requested.emit(delta)
            self.last_pan_pos = event.globalPosition().toPoint()
            return
        if self.mode == "setup" and self.start_pos:
            self.temp_rect = QtCore.QRect(self.start_pos, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        self.start_pos = None; self.last_pan_pos = None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

class PickerEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("PickerEditor - Max Version"); self.resize(1200, 800)
        self.setWindowFlags(QtCore.Qt.Window); self.setAcceptDrops(True); self.setStyleSheet(STYLESHEET)
        
        main_v = QtWidgets.QVBoxLayout(self); self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        left_w = QtWidgets.QWidget(); left_v = QtWidgets.QVBoxLayout(left_w); left_v.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea(); self.canvas = ImageCanvas()
        self.scroll.setWidget(self.canvas); left_v.addWidget(self.scroll)
        self.btn_mode = QtWidgets.QPushButton("Switch to SELECTOR Mode"); self.btn_mode.setCheckable(True); self.btn_mode.setFixedHeight(40)
        self.btn_mode.toggled.connect(self.toggle_mode); left_v.addWidget(self.btn_mode)

        right_w = QtWidgets.QWidget(); right_panel = QtWidgets.QVBoxLayout(right_w)
        self.setup_group = QtWidgets.QGroupBox("Registration"); setup_v = QtWidgets.QVBoxLayout(self.setup_group)
        
        rep_h = QtWidgets.QHBoxLayout(); self.edit_f = QtWidgets.QLineEdit(); self.edit_f.setPlaceholderText("Find...")
        self.edit_r = QtWidgets.QLineEdit(); self.edit_r.setPlaceholderText("Replace...")
        btn_rep = QtWidgets.QPushButton("Replace All"); btn_rep.clicked.connect(self.batch_replace)
        rep_h.addWidget(self.edit_f); rep_h.addWidget(self.edit_r); rep_h.addWidget(btn_rep); setup_v.addLayout(rep_h)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_widget.currentRowChanged.connect(self.sync_canvas); setup_v.addWidget(self.list_widget)

        get_h = QtWidgets.QHBoxLayout(); self.edit_names = QtWidgets.QLineEdit()
        btn_get = QtWidgets.QPushButton("Get Selected"); btn_get.clicked.connect(lambda: self.edit_names.setText(", ".join([o.name for o in list(mxs.selection)])))
        get_h.addWidget(self.edit_names); get_h.addWidget(btn_get); setup_v.addLayout(get_h)

        self.btn_reg = QtWidgets.QPushButton("Register Area"); self.btn_reg.setFixedHeight(35); self.btn_reg.clicked.connect(self.do_register); setup_v.addWidget(self.btn_reg)
        self.btn_del = QtWidgets.QPushButton("Delete Selected"); self.btn_del.clicked.connect(self.delete_items); setup_v.addWidget(self.btn_del)
        right_panel.addWidget(self.setup_group)
        
        file_h = QtWidgets.QHBoxLayout(); btn_save = QtWidgets.QPushButton("Save JSON"); btn_load = QtWidgets.QPushButton("Load JSON")
        btn_save.clicked.connect(self.save_json); btn_load.clicked.connect(self.load_json); file_h.addWidget(btn_save); file_h.addWidget(btn_load); right_panel.addLayout(file_h)

        self.splitter.addWidget(left_w); self.splitter.addWidget(right_w)
        # --- 修正箇所: Blender版に合わせてスプリッターの初期比率を調整 ---
        self.splitter.setSizes([350, 800])
        main_v.addWidget(self.splitter)

        self.canvas.request_deselect.connect(lambda: self.list_widget.setCurrentRow(-1))
        self.canvas.region_clicked.connect(lambda i: self.list_widget.setCurrentRow(i))
        self.canvas.pan_requested.connect(self.handle_pan)

    def handle_pan(self, delta):
        h = self.scroll.horizontalScrollBar(); v = self.scroll.verticalScrollBar()
        h.setValue(h.value() - delta.x()); v.setValue(v.value() - delta.y())

    def sync_canvas(self, row): self.canvas.selected_index = row; self.canvas.update()

    def handle_rect_sync(self, origin_idx, key, value):
        selected_rows = [i.row() for i in self.list_widget.selectedIndexes()]
        targets = selected_rows if origin_idx in selected_rows else [origin_idx]
        for row in targets:
            reg = self.canvas.registered_items[row]; r = list(reg.rect.getRect())
            r[{"x":0,"y":1,"w":2,"h":3}[key]] = value; reg.rect = QtCore.QRect(*r)
            w = self.list_widget.itemWidget(self.list_widget.item(row))
            if w and row != origin_idx: w.block_signals = True; w.spins[key].setValue(value); w.block_signals = False
        self.canvas.update()

    def handle_color_sync(self, origin_idx, color):
        selected_rows = [i.row() for i in self.list_widget.selectedIndexes()]
        targets = selected_rows if origin_idx in selected_rows else [origin_idx]
        for row in targets:
            self.canvas.registered_items[row].color = color
            w = self.list_widget.itemWidget(self.list_widget.item(row))
            if w: w.set_btn_style(color)
        self.canvas.update()

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e):
        path = e.mimeData().urls()[0].toLocalFile(); ext = os.path.splitext(path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg"]:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                self.canvas.set_image(pix)
                j = os.path.splitext(path)[0] + ".json"; (self.load_json_at_path(j) if os.path.exists(j) else None)
        elif ext == ".json": self.load_json_at_path(path)
        e.acceptProposedAction()

    def batch_replace(self):
        f, r = self.edit_f.text(), self.edit_r.text()
        if not f: return
        for i, reg in enumerate(self.canvas.registered_items):
            reg.names = [n.replace(f, r) for n in reg.names]
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.names_edit.setText(", ".join(reg.names))

    def do_register(self):
        names = [n.strip() for n in self.edit_names.text().split(",") if n.strip()]
        if not self.canvas.temp_rect.isNull() and names:
            raw_rect = [
                int(self.canvas.temp_rect.x() / self.canvas.scale),
                int(self.canvas.temp_rect.y() / self.canvas.scale),
                int(self.canvas.temp_rect.width() / self.canvas.scale),
                int(self.canvas.temp_rect.height() / self.canvas.scale)
            ]
            reg = ClickRegion(names, raw_rect, [0, 255, 0])
            self.canvas.registered_items.append(reg)
            self.add_list_item(names, reg.rect, QtGui.QColor(0, 255, 0))
            self.canvas.temp_rect = QtCore.QRect(); self.canvas.update()

    def add_list_item(self, names, rect, color):
        item = QtWidgets.QListWidgetItem(self.list_widget)
        w = ListColorItem(names, rect, color, self.list_widget.count()-1)
        w.names_changed.connect(lambda i, n: setattr(self.canvas.registered_items[i], 'names', n))
        w.rect_changed.connect(self.handle_rect_sync)
        w.color_changed.connect(self.handle_color_sync)
        item.setSizeHint(w.sizeHint()); self.list_widget.addItem(item); self.list_widget.setItemWidget(item, w)

    def delete_items(self):
        rows = sorted([self.list_widget.row(it) for it in self.list_widget.selectedItems()], reverse=True)
        for r in rows: self.list_widget.takeItem(r); self.canvas.registered_items.pop(r)
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.index = i
        self.canvas.update()

    def toggle_mode(self, checked):
        is_edit = not checked; self.canvas.mode = "selector" if checked else "setup"
        self.btn_mode.setText("SELECTOR Mode (Active)" if checked else "Switch to SELECTOR Mode")
        self.setup_group.setEnabled(is_edit); self.btn_reg.setEnabled(is_edit); self.btn_del.setEnabled(is_edit)
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.set_edit_enabled(is_edit)

    def save_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save JSON", "", "*.json")
        if path:
            data = [{"names": i.names, "rect": list(i.rect.getRect()), "color": list(i.color.getRgb())} for i in self.canvas.registered_items]
            with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open JSON", "", "*.json")
        if path: self.load_json_at_path(path)

    def load_json_at_path(self, path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
            self.canvas.registered_items = []; self.list_widget.clear()
            for d in data:
                reg = ClickRegion(d.get("names", [d.get("name", "Unknown")]), d["rect"], d["color"])
                self.canvas.registered_items.append(reg)
                self.add_list_item(reg.names, reg.rect, reg.color)
            self.canvas.update()

if __name__ == "__main__":
    for w in QtWidgets.QApplication.allWidgets():
        if w.windowTitle() == "PickerEditor - Max Version": w.close(); w.deleteLater()
    ui = PickerEditor(); ui.show()