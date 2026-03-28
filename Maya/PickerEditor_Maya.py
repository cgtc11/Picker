# -*- coding: utf-8 -*-
import json
import os
import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore, QtGui

# --- スタイル設定 ---
STYLESHEET = """
    QWidget { background-color: #2b2b2b; color: #dcdcdc; font-family: 'Segoe UI', sans-serif; }
    QGroupBox { border: 1px solid #3a3a3a; margin-top: 15px; padding-top: 10px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; color: #aaaaaa; }
    QPushButton { background-color: #3f3f3f; border: 1px solid #555; border-radius: 3px; padding: 5px; color: #ffffff; }
    QPushButton:hover { background-color: #4f4f4f; }
    QPushButton:disabled { background-color: #2a2a2a; color: #666; border: 1px solid #333; }
    QLineEdit { background-color: #1a1a1a; color: #ffffff; border: 1px solid #333; padding: 3px; }
    QLineEdit:disabled { background-color: #222; color: #666; border: 1px solid #2a2a2a; }
    QListWidget { background-color: #1a1a1a; border: 1px solid #333; }
    QListWidget::item:selected { background-color: #3d5a73; }
"""

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class MaxStyleSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setRange(-10000, 10000)
        self.setFixedWidth(45)
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.last_mouse_pos = None

    def mousePressEvent(self, event):
        if not self.isEnabled(): return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.globalPosition().toPoint()
            self.setFocus()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            delta = event.globalPosition().toPoint().x() - self.last_mouse_pos.x()
            if delta != 0:
                self.setValue(self.value() + delta)
                self.last_mouse_pos = event.globalPosition().toPoint()
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
        layout.setSpacing(8)

        self.names_edit = QtWidgets.QLineEdit(", ".join(names))
        self.names_edit.editingFinished.connect(self.on_names_ui_changed)
        layout.addWidget(self.names_edit, 1)
        
        self.spin_container = QtWidgets.QWidget()
        spin_layout = QtWidgets.QHBoxLayout(self.spin_container)
        spin_layout.setContentsMargins(0, 0, 0, 0)
        spin_layout.setSpacing(4)
        
        self.spins = {}
        for label_text, key in [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]:
            lbl = QtWidgets.QLabel(label_text); lbl.setFixedWidth(12)
            spin_layout.addWidget(lbl)
            sb = MaxStyleSpinBox()
            sb.valueChanged.connect(self.on_rect_ui_changed)
            spin_layout.addWidget(sb)
            self.spins[key] = sb
            
        layout.addWidget(self.spin_container)
        self.update_spins(rect)

        self.color_btn = QtWidgets.QPushButton("■")
        self.color_btn.setFixedSize(22, 22)
        self.set_btn_color(color)
        self.color_btn.clicked.connect(self.pick_new_color)
        layout.addWidget(self.color_btn)

    def set_edit_enabled(self, enabled):
        self.names_edit.setEnabled(enabled)
        self.spin_container.setEnabled(enabled)
        self.color_btn.setEnabled(enabled)

    def update_spins(self, rect):
        self.block_signals = True
        self.spins["x"].setValue(rect.x()); self.spins["y"].setValue(rect.y())
        self.spins["w"].setValue(rect.width()); self.spins["h"].setValue(rect.height())
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
        self.color_btn.setStyleSheet(f"color: {color.name()}; background-color: #2b2b2b; border: 1px solid #555; padding: 0px;")

    def pick_new_color(self):
        c = QtWidgets.QColorDialog.getColor(self.current_color, self)
        if c.isValid():
            self.set_btn_color(c)
            self.color_changed.emit(self.index, c)

class ImageCanvas(QtWidgets.QLabel):
    request_deselect = QtCore.Signal(); region_clicked = QtCore.Signal(int)
    def __init__(self, parent=None):
        super().__init__(parent); self.start_pos = None; self.temp_rect = QtCore.QRect()
        self.registered_items = []; self.mode = "setup"; self.selected_index = -1
        self.setMouseTracking(True); self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet("background-color: #1a1a1a;")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        for i, item in enumerate(self.registered_items):
            painter.setPen(QtGui.QPen(item.color, 4 if i == self.selected_index else 1))
            painter.drawRect(item.rect)
        if self.mode == "setup" and not self.temp_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.red, 1, QtCore.Qt.PenStyle.DashLine))
            painter.drawRect(self.temp_rect)

    def mousePressEvent(self, event):
        pos = event.position().toPoint(); hit = False
        for i, reg in enumerate(self.registered_items):
            if reg.rect.contains(pos):
                hit = True; self.region_clicked.emit(i)
                if self.mode == "selector":
                    cmds.select(reg.names, replace=True)
                break
        if not hit:
            self.start_pos = pos if self.mode == "setup" else None
            self.request_deselect.emit()

    def mouseMoveEvent(self, event):
        if self.mode == "setup" and self.start_pos:
            self.temp_rect = QtCore.QRect(self.start_pos, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event): self.start_pos = None

class MayaPickerEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Maya Picker Editor")
        self.resize(1200, 800)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLESHEET)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # --- 左: Canvas ---
        left_w = QtWidgets.QWidget(); left_v = QtWidgets.QVBoxLayout(left_w)
        self.scroll = QtWidgets.QScrollArea(); self.scroll.setWidgetResizable(True)
        self.canvas = ImageCanvas(); self.scroll.setWidget(self.canvas)
        self.canvas.request_deselect.connect(lambda: self.list_widget.setCurrentRow(-1))
        self.canvas.region_clicked.connect(lambda i: self.list_widget.setCurrentRow(i))
        left_v.addWidget(self.scroll)
        
        self.btn_mode = QtWidgets.QPushButton("Switch to SELECTOR Mode"); self.btn_mode.setCheckable(True); self.btn_mode.setFixedHeight(40)
        self.btn_mode.toggled.connect(self.toggle_mode); left_v.addWidget(self.btn_mode)

        # --- 右: Controls ---
        right_w = QtWidgets.QWidget(); right_w.setMinimumWidth(550); self.right_v = QtWidgets.QVBoxLayout(right_w)
        self.setup_group = QtWidgets.QGroupBox("Registration"); setup_v = QtWidgets.QVBoxLayout(self.setup_group)
        
        rep_h = QtWidgets.QHBoxLayout(); self.edit_f = QtWidgets.QLineEdit(); self.edit_f.setPlaceholderText("Find...")
        self.edit_r = QtWidgets.QLineEdit(); self.edit_r.setPlaceholderText("Replace...")
        btn_rep = QtWidgets.QPushButton("Replace All"); btn_rep.clicked.connect(self.batch_replace)
        rep_h.addWidget(self.edit_f); rep_h.addWidget(self.edit_r); rep_h.addWidget(btn_rep); setup_v.addLayout(rep_h)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.currentRowChanged.connect(self.sync_canvas)
        setup_v.addWidget(self.list_widget)

        get_h = QtWidgets.QHBoxLayout(); self.edit_names = QtWidgets.QLineEdit()
        btn_get = QtWidgets.QPushButton("Get Selected")
        btn_get.clicked.connect(lambda: self.edit_names.setText(", ".join(cmds.ls(sl=True))))
        get_h.addWidget(self.edit_names); get_h.addWidget(btn_get); setup_v.addLayout(get_h)
        self.right_v.addWidget(self.setup_group)

        self.btn_reg = QtWidgets.QPushButton("Register Area"); self.btn_reg.setFixedHeight(30); self.btn_reg.clicked.connect(self.do_register)
        self.btn_del = QtWidgets.QPushButton("Delete Selected"); self.btn_del.setFixedHeight(30); self.btn_del.clicked.connect(self.delete_item)
        self.right_v.addWidget(self.btn_reg); self.right_v.addWidget(self.btn_del)

        file_h = QtWidgets.QHBoxLayout(); btn_save = QtWidgets.QPushButton("Save JSON"); btn_load = QtWidgets.QPushButton("Load JSON")
        btn_save.clicked.connect(self.save_json); btn_load.clicked.connect(self.load_json)
        file_h.addWidget(btn_save); file_h.addWidget(btn_load); self.right_v.addLayout(file_h)

        self.splitter.addWidget(left_w); self.splitter.addWidget(right_w); main_layout.addWidget(self.splitter)

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e):
        path = e.mimeData().urls()[0].toLocalFile()
        ext = os.path.splitext(path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg"]:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                self.canvas.setPixmap(pix); self.canvas.setFixedSize(pix.size())
                j = os.path.splitext(path)[0] + ".json"
                if os.path.exists(j): self.load_json(j)
        elif ext == ".json": self.load_json(path)
        e.acceptProposedAction()

    def sync_canvas(self, row): self.canvas.selected_index = row; self.canvas.update()

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
            reg = ClickRegion(names, self.canvas.temp_rect.getRect(), [0, 255, 0])
            self.canvas.registered_items.append(reg)
            self.add_list_item(names, self.canvas.temp_rect, QtGui.QColor(0, 255, 0))
            self.canvas.temp_rect = QtCore.QRect(); self.canvas.update()

    def add_list_item(self, names, rect, color):
        item = QtWidgets.QListWidgetItem(self.list_widget)
        w = ListColorItem(names, rect, color, self.list_widget.count()-1)
        w.names_changed.connect(lambda i, n: setattr(self.canvas.registered_items[i], 'names', n))
        w.rect_changed.connect(lambda i, r: (setattr(self.canvas.registered_items[i], 'rect', QtCore.QRect(*r)), self.canvas.update()))
        w.color_changed.connect(lambda i, c: (setattr(self.canvas.registered_items[i], 'color', c), self.canvas.update()))
        item.setSizeHint(w.sizeHint()); self.list_widget.addItem(item); self.list_widget.setItemWidget(item, w)

    def delete_item(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row); self.canvas.registered_items.pop(row)
            for i in range(self.list_widget.count()):
                w = self.list_widget.itemWidget(self.list_widget.item(i))
                if w: w.index = i
            self.canvas.update()

    def toggle_mode(self, checked):
        is_edit_mode = not checked
        self.canvas.mode = "selector" if checked else "setup"
        self.btn_mode.setText("SELECTOR Mode (Active)" if checked else "Switch to SELECTOR Mode")
        self.setup_group.setEnabled(is_edit_mode)
        self.btn_reg.setEnabled(is_edit_mode); self.btn_del.setEnabled(is_edit_mode)
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.set_edit_enabled(is_edit_mode)

    def save_json(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save JSON", "", "*.json")
        if p:
            json_rows = []
            for item in self.canvas.registered_items:
                d = {"names": item.names, "rect": item.rect.getRect(), "color": item.color.getRgb()}
                json_rows.append(f" {json.dumps(d, ensure_ascii=False)}")
            final_json = "[\n" + ",\n".join(json_rows) + "\n]"
            with open(p, 'w', encoding='utf-8') as f: f.write(final_json)

    def load_json(self, p=None):
        if not p: p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open JSON", "", "*.json")
        if p and os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f: data = json.load(f)
            self.canvas.registered_items = []; self.list_widget.clear()
            for d in data:
                reg = ClickRegion(d.get("names", [d.get("name", "Unknown")]), d["rect"], d["color"])
                self.canvas.registered_items.append(reg)
                self.add_list_item(reg.names, reg.rect, reg.color)
            self.canvas.update()

# --- Maya用ヘルパー関数 ---
def get_maya_main_window():
    """Mayaのメインウィンドウを探して返す"""
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == "MayaWindow":
            return widget
    return None

# インスタンス保持用
maya_picker_editor_instance = None

def show():
    """Mayaから呼び出すメイン関数"""
    global maya_picker_editor_instance
    
    # すでに開いていたら閉じる
    try:
        if maya_picker_editor_instance:
            maya_picker_editor_instance.close()
            maya_picker_editor_instance.deleteLater()
    except:
        pass

    parent = get_maya_main_window()
    maya_picker_editor_instance = MayaPickerEditor(parent=parent)
    
    # Mayaウィンドウの子として振る舞う設定
    if parent:
        maya_picker_editor_instance.setWindowFlags(QtCore.Qt.Window)
        
    maya_picker_editor_instance.show()

if __name__ == "__main__":
    show()