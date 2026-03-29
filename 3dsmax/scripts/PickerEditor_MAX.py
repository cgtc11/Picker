# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

# --- スタイル設定 (Maya/Max風のダークテーマ) ---
STYLESHEET = """
    QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: 'Segoe UI', sans-serif; font-size: 12px; }
    QGroupBox { border: 1px solid #3a3a3a; margin-top: 15px; padding-top: 10px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #aaaaaa; }
    QPushButton { background-color: #3f3f3f; border: 1px solid #555; border-radius: 3px; padding: 3px; color: #ffffff; }
    QPushButton:hover { background-color: #4f4f4f; }
    QPushButton:disabled { background-color: #2a2a2a; color: #666; border: 1px solid #333; }
    QLineEdit { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333; padding: 2px; }
    QLineEdit:disabled { background-color: #222; color: #666; border: 1px solid #2a2a2a; }
    QListWidget { background-color: #1a1a1a; border: 1px solid #333; outline: none; }
    QListWidget::item:selected { background-color: #3d5a73; }
    QScrollArea { border: none; background-color: #1a1a1a; }
    QLabel { background-color: transparent; color: #aaaaaa; }
"""

class MaxStyleSpinBox(QtWidgets.QSpinBox):
    """数値入力に特化したスピンボックス"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setRange(-10000, 10000)
        self.setFixedWidth(45)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

    def mouseReleaseEvent(self, event):
        # クリックして離した瞬間に全選択状態にする（即上書き可能）
        self.selectAll()
        super().mouseReleaseEvent(event)

class DraggableLabel(QtWidgets.QLabel):
    """ラベルをドラッグして数値を変えるクラス"""
    def __init__(self, text, spinbox, parent=None):
        super().__init__(text, parent)
        self.spinbox = spinbox
        self.setFixedWidth(15)
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor) # 左右矢印カーソル
        self.last_mouse_pos = None
        self.setStyleSheet("color: #aaaaaa; font-weight: bold;")

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            curr_pos = event.globalPosition().toPoint()
            delta = curr_pos.x() - self.last_mouse_pos.x()
            if delta != 0:
                # 紐付いたスピンボックスの値を更新
                self.spinbox.setValue(self.spinbox.value() + delta)
                self.last_mouse_pos = curr_pos
                event.accept()

    def mouseReleaseEvent(self, event):
        self.last_mouse_pos = None

class ListColorItem(QtWidgets.QWidget):
    color_changed = QtCore.Signal(int, QtGui.QColor)
    rect_changed = QtCore.Signal(int, list)
    names_changed = QtCore.Signal(int, list)

    def __init__(self, names, rect, color, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.block_signals = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)
        
        self.names_edit = QtWidgets.QLineEdit(", ".join(names))
        self.names_edit.setMinimumWidth(120)
        self.names_edit.editingFinished.connect(self.on_names_ui_changed)
        layout.addWidget(self.names_edit)
        
        self.spins = {}
        for label_text, key in [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]:
            sb = MaxStyleSpinBox()
            sb.valueChanged.connect(self.on_rect_ui_changed)
            
            # X, Y, W, H の文字部分をドラッグ可能ラベルにする
            lbl = DraggableLabel(label_text, sb)
            
            layout.addWidget(lbl)
            layout.addWidget(sb)
            self.spins[key] = sb
            
        self.update_spins(rect)
        self.color_btn = QtWidgets.QPushButton("■")
        self.color_btn.setFixedSize(22, 22)
        self.set_btn_color(color)
        self.color_btn.clicked.connect(self.pick_new_color)
        layout.addWidget(self.color_btn)

    def update_spins(self, rect):
        self.block_signals = True
        self.spins["x"].setValue(rect.x())
        self.spins["y"].setValue(rect.y())
        self.spins["w"].setValue(rect.width())
        self.spins["h"].setValue(rect.height())
        self.block_signals = False

    def on_names_ui_changed(self):
        new_list = [n.strip() for n in self.names_edit.text().split(",") if n.strip()]
        self.names_changed.emit(self.index, new_list)

    def on_rect_ui_changed(self):
        if self.block_signals: return
        r = [self.spins["x"].value(), self.spins["y"].value(), self.spins["w"].value(), self.spins["h"].value()]
        self.rect_changed.emit(self.index, r)

    def set_btn_color(self, color):
        self.current_color = color
        self.color_btn.setStyleSheet(f"color: {color.name()}; font-size: 16px; background-color: #1a1a1a; border: 1px solid #555;")

    def pick_new_color(self):
        new_color = QtWidgets.QColorDialog.getColor(self.current_color, self)
        if new_color.isValid():
            self.set_btn_color(new_color)
            self.color_changed.emit(self.index, new_color)

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class ImageCanvas(QtWidgets.QLabel):
    request_deselect = QtCore.Signal(); region_clicked = QtCore.Signal(int) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_pos = None; self.temp_rect = QtCore.QRect()
        self.registered_items = []; self.mode = "setup"; self.selected_index = -1
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet("background-color: #1a1a1a; color: #444;")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        for i, item in enumerate(self.registered_items):
            pen_width = 4 if i == self.selected_index else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(item.rect)
        if self.mode == "setup" and not self.temp_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.red, 2, QtCore.Qt.PenStyle.DashLine))
            painter.drawRect(self.temp_rect)

    def mousePressEvent(self, event):
        pos = event.position().toPoint(); hit = False
        for i, region in enumerate(self.registered_items):
            if region.rect.contains(pos):
                hit = True; self.region_clicked.emit(i)
                if self.mode == "selector":
                    nodes = [mxs.getNodeByName(name) for name in region.names]
                    valid_nodes = [n for n in nodes if n]
                    if valid_nodes: mxs.select(valid_nodes)
                break
        if not hit:
            self.start_pos = pos if self.mode == "setup" else None
            self.request_deselect.emit()

    def mouseMoveEvent(self, event):
        if self.mode == "setup" and self.start_pos:
            self.temp_rect = QtCore.QRect(self.start_pos, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event): self.start_pos = None

class PickerEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PickerEditor - Max Version")
        self.setWindowFlags(QtCore.Qt.Window); self.setAcceptDrops(True)
        self.setStyleSheet(STYLESHEET)
        self.resize(1200, 800)

        main_v = QtWidgets.QVBoxLayout(self)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        left_w = QtWidgets.QWidget(); left_v = QtWidgets.QVBoxLayout(left_w)
        left_v.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea(); self.canvas = ImageCanvas()
        self.canvas.request_deselect.connect(self.clear_ui_selection)
        self.canvas.region_clicked.connect(self.select_list_from_canvas) 
        self.scroll.setWidget(self.canvas); left_v.addWidget(self.scroll)
        
        self.btn_mode = QtWidgets.QPushButton("Switch to SELECTOR Mode")
        self.btn_mode.setCheckable(True); self.btn_mode.setFixedHeight(40)
        self.btn_mode.toggled.connect(self.toggle_mode); left_v.addWidget(self.btn_mode)

        right_w = QtWidgets.QWidget(); right_panel = QtWidgets.QVBoxLayout(right_w)
        self.setup_group = QtWidgets.QGroupBox("Registration"); setup_v = QtWidgets.QVBoxLayout(self.setup_group)
        
        replace_h = QtWidgets.QHBoxLayout()
        self.edit_find = QtWidgets.QLineEdit(); self.edit_find.setPlaceholderText("Find...")
        self.edit_replace = QtWidgets.QLineEdit(); self.edit_replace.setPlaceholderText("Replace...")
        btn_rep = QtWidgets.QPushButton("Replace All"); btn_rep.clicked.connect(self.batch_replace_names)
        replace_h.addWidget(self.edit_find); replace_h.addWidget(self.edit_replace); replace_h.addWidget(btn_rep)
        setup_v.addLayout(replace_h)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.currentRowChanged.connect(self.sync_list_to_canvas) 
        setup_v.addWidget(self.list_widget)

        form_h = QtWidgets.QHBoxLayout()
        self.edit_names = QtWidgets.QLineEdit()
        btn_get = QtWidgets.QPushButton("Get Selected")
        btn_get.clicked.connect(self.get_max_selection_names)
        form_h.addWidget(self.edit_names); form_h.addWidget(btn_get)
        setup_v.addLayout(form_h)

        self.btn_reg = QtWidgets.QPushButton("Register Area"); self.btn_reg.setFixedHeight(35)
        self.btn_reg.clicked.connect(self.do_register); setup_v.addWidget(self.btn_reg)

        self.btn_del = QtWidgets.QPushButton("Delete Selected"); self.btn_del.clicked.connect(self.delete_item)
        setup_v.addWidget(self.btn_del)
        right_panel.addWidget(self.setup_group)
        
        btn_lay = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Save JSON"); btn_save.clicked.connect(self.save_json)
        btn_load = QtWidgets.QPushButton("Load JSON"); btn_load.clicked.connect(self.load_json)
        btn_lay.addWidget(btn_save); btn_lay.addWidget(btn_load)
        right_panel.addLayout(btn_lay)

        self.splitter.addWidget(left_w); self.splitter.addWidget(right_w)
        self.splitter.setStretchFactor(1, 1)
        main_v.addWidget(self.splitter)

    def save_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if path:
            rows = [json.dumps({"names": item.names, "rect": item.rect.getRect(), "color": item.color.getRgb()}, ensure_ascii=False) for item in self.canvas.registered_items]
            with open(path, 'w', encoding='utf-8') as f: f.write("[\n " + ",\n ".join(rows) + "\n]")

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", "", "JSON (*.json)")
        if path: self.load_json_at_path(path)

    def load_json_at_path(self, path):
        if not os.path.exists(path): return
        with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
        self.canvas.registered_items = []; self.list_widget.clear()
        for d in data:
            reg = ClickRegion(d.get("names", [d.get("name", "Unknown")]), d["rect"], d["color"])
            self.canvas.registered_items.append(reg)
            self.add_list_item(reg.names, reg.rect, reg.color)
        self.canvas.update()

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e):
        path = e.mimeData().urls()[0].toLocalFile()
        ext = os.path.splitext(path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg"]:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                self.canvas.setPixmap(pix); self.canvas.setFixedSize(pix.size()); self.canvas.update()
                j_path = os.path.splitext(path)[0] + ".json"
                if os.path.exists(j_path): self.load_json_at_path(j_path)
        elif ext == ".json": self.load_json_at_path(path)
        e.acceptProposedAction()

    def do_register(self):
        names = [n.strip() for n in self.edit_names.text().split(",") if n.strip()]
        if not self.canvas.temp_rect.isNull() and names:
            reg = ClickRegion(names, self.canvas.temp_rect.getRect(), [0, 255, 0])
            self.canvas.registered_items.append(reg)
            self.add_list_item(names, self.canvas.temp_rect, QtGui.QColor(0, 255, 0))
            self.canvas.temp_rect = QtCore.QRect(); self.canvas.update()

    def add_list_item(self, names, rect, color):
        item = QtWidgets.QListWidgetItem(self.list_widget)
        w = ListColorItem(names, rect, color, self.list_widget.count() - 1)
        w.names_changed.connect(self.update_item_names)
        w.color_changed.connect(self.update_item_color)
        w.rect_changed.connect(self.update_item_rect)
        item.setSizeHint(w.sizeHint()); self.list_widget.addItem(item); self.list_widget.setItemWidget(item, w)

    def update_item_names(self, index, new_names_list):
        if index < len(self.canvas.registered_items): self.canvas.registered_items[index].names = new_names_list

    def batch_replace_names(self):
        f, r = self.edit_find.text(), self.edit_replace.text()
        if not f: return
        for i, reg in enumerate(self.canvas.registered_items):
            reg.names = [n.replace(f, r) for n in reg.names]
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.names_edit.setText(", ".join(reg.names))

    def update_item_color(self, index, new_color): self.canvas.registered_items[index].color = new_color; self.canvas.update()
    def update_item_rect(self, index, rect_list): self.canvas.registered_items[index].rect = QtCore.QRect(*rect_list); self.canvas.update()

    def delete_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row); self.canvas.registered_items.pop(row)
            for i in range(self.list_widget.count()):
                w = self.list_widget.itemWidget(self.list_widget.item(i))
                if w: w.index = i
            self.clear_ui_selection()

    def toggle_mode(self, checked):
        self.canvas.mode = "selector" if checked else "setup"
        self.btn_mode.setText("SELECTOR Mode (Active)" if checked else "Switch to SELECTOR Mode")
        self.setup_group.setEnabled(not checked)

    def select_list_from_canvas(self, index): self.list_widget.setCurrentRow(index)
    def sync_list_to_canvas(self, row): self.canvas.selected_index = row; self.canvas.update()
    def clear_ui_selection(self): self.list_widget.setCurrentRow(-1) 
    def get_max_selection_names(self): self.edit_names.setText(", ".join([n.name for n in list(mxs.selection)]))

if __name__ == "__main__":
    for w in QtWidgets.QApplication.allWidgets():
        if w.windowTitle() == "PickerEditor - Max Version": w.close()
    ui = PickerEditor()
    ui.show()