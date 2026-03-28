# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

# --- データ保持用クラス ---
class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

# --- 数値入力用カスタムスピンボックス ---
class MaxStyleSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setRange(-5000, 5000)
        self.setFixedWidth(45)
        self.lineEdit().setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.last_mouse_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.globalPosition().toPoint()
            self.setFocus()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            curr_pos = event.globalPosition().toPoint()
            delta = curr_pos.x() - self.last_mouse_pos.x()
            if delta != 0:
                self.setValue(self.value() + delta)
                self.last_mouse_pos = curr_pos
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.last_mouse_pos = None
        super().mouseReleaseEvent(event)

# --- リスト内の各行UI ---
class ListColorItem(QtWidgets.QWidget):
    color_changed = QtCore.Signal(int, QtGui.QColor)
    rect_changed = QtCore.Signal(int, list)
    names_changed = QtCore.Signal(int, list)

    def __init__(self, names, rect, color, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.block_signals = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.addSpacing(10) 
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(8)
        
        self.names_edit = QtWidgets.QLineEdit(", ".join(names))
        self.names_edit.setMinimumWidth(150)
        self.names_edit.editingFinished.connect(self.on_names_ui_changed)
        layout.addWidget(self.names_edit)
        
        self.spins = {}
        for label_text, key in [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]:
            layout.addWidget(QtWidgets.QLabel(label_text))
            sb = MaxStyleSpinBox()
            sb.valueChanged.connect(self.on_rect_ui_changed)
            layout.addWidget(sb)
            self.spins[key] = sb
            
        self.update_spins(rect)
        self.color_btn = QtWidgets.QPushButton("■")
        self.color_btn.setFixedSize(25, 22)
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
        text = self.names_edit.text()
        new_list = [n.strip() for n in text.split(",") if n.strip()]
        self.names_changed.emit(self.index, new_list)

    def on_rect_ui_changed(self):
        if self.block_signals: return
        rect_list = [self.spins["x"].value(), self.spins["y"].value(),
                     self.spins["w"].value(), self.spins["h"].value()]
        self.rect_changed.emit(self.index, rect_list)

    def set_btn_color(self, color):
        self.current_color = color
        self.color_btn.setStyleSheet(f"color: {color.name()}; font-size: 16px; background-color: #333; border: 1px solid #555;")

    def pick_new_color(self):
        new_color = QtWidgets.QColorDialog.getColor(self.current_color, self)
        if new_color.isValid():
            self.set_btn_color(new_color)
            self.color_changed.emit(self.index, new_color)

# --- 画像表示と枠描画キャンバス ---
class ImageCanvas(QtWidgets.QLabel):
    request_deselect = QtCore.Signal()
    region_clicked = QtCore.Signal(int) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(False) 
        self.start_pos = None
        self.temp_rect = QtCore.QRect()
        self.registered_items = []
        self.mode = "setup"
        self.selected_index = -1
        self.setMouseTracking(True)
        self.setText("Drop Image Anywhere")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #111; color: #444;")

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
        pos = event.position().toPoint()
        hit = False
        
        for i, region in enumerate(self.registered_items):
            if region.rect.contains(pos):
                hit = True
                self.region_clicked.emit(i) 
                
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
            curr_pos = event.position().toPoint()
            self.temp_rect = QtCore.QRect(self.start_pos, curr_pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event): 
        self.start_pos = None

# --- メインウィンドウ ---
class PickerEditor(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PickerEditor - Max Version")
        self.setWindowFlags(QtCore.Qt.Window)
        self.setAcceptDrops(True) 
        self.resize(1200, 800)

        self.main_v_layout = QtWidgets.QVBoxLayout(self)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        # Left Panel
        self.left_container = QtWidgets.QWidget()
        self.left_v_layout = QtWidgets.QVBoxLayout(self.left_container)
        self.left_v_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QtWidgets.QScrollArea()
        self.canvas = ImageCanvas()
        self.canvas.request_deselect.connect(self.clear_ui_selection)
        self.canvas.region_clicked.connect(self.select_list_from_canvas) 
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setStyleSheet("background-color: #222; border: none;")
        self.left_v_layout.addWidget(self.scroll_area)
        
        self.btn_mode = QtWidgets.QPushButton("Switch to SELECTOR Mode")
        self.btn_mode.setCheckable(True)
        self.btn_mode.setFixedHeight(40)
        self.btn_mode.toggled.connect(self.toggle_mode)
        self.left_v_layout.addWidget(self.btn_mode)

        # Right Panel
        self.right_container = QtWidgets.QWidget()
        self.right_panel = QtWidgets.QVBoxLayout(self.right_container)
        self.setup_group = QtWidgets.QGroupBox("Registration")
        setup_v = QtWidgets.QVBoxLayout(self.setup_group)
        
        replace_h = QtWidgets.QHBoxLayout()
        self.edit_find = QtWidgets.QLineEdit(); self.edit_find.setPlaceholderText("Find...")
        self.edit_replace = QtWidgets.QLineEdit(); self.edit_replace.setPlaceholderText("Replace...")
        self.btn_replace_all = QtWidgets.QPushButton("Replace All")
        self.btn_replace_all.clicked.connect(self.batch_replace_names)
        replace_h.addWidget(self.edit_find); replace_h.addWidget(self.edit_replace); replace_h.addWidget(self.btn_replace_all)
        setup_v.addLayout(replace_h)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.currentRowChanged.connect(self.sync_list_to_canvas) 
        setup_v.addWidget(self.list_widget)

        form_h = QtWidgets.QHBoxLayout()
        self.edit_names = QtWidgets.QLineEdit()
        self.btn_get_names = QtWidgets.QPushButton("Get Selected")
        self.btn_get_names.clicked.connect(self.get_max_selection_names)
        form_h.addWidget(self.edit_names); form_h.addWidget(self.btn_get_names)
        setup_v.addLayout(form_h)

        self.btn_reg = QtWidgets.QPushButton("Register Area")
        self.btn_reg.setFixedHeight(35); self.btn_reg.clicked.connect(self.do_register)
        setup_v.addWidget(self.btn_reg)

        self.btn_del = QtWidgets.QPushButton("Delete Selected")
        self.btn_del.clicked.connect(self.delete_item)
        setup_v.addWidget(self.btn_del)
        self.right_panel.addWidget(self.setup_group)
        
        btn_lay = QtWidgets.QHBoxLayout()
        self.btn_save = QtWidgets.QPushButton("Save JSON"); self.btn_save.clicked.connect(self.save_json)
        self.btn_load = QtWidgets.QPushButton("Load JSON"); self.btn_load.clicked.connect(self.load_json)
        btn_lay.addWidget(self.btn_save); btn_lay.addWidget(self.btn_load)
        self.right_panel.addLayout(btn_lay)

        self.splitter.addWidget(self.left_container)
        self.splitter.addWidget(self.right_container)
        self.splitter.setStretchFactor(1, 1)
        self.main_v_layout.addWidget(self.splitter)

    # --- 保存・読み込みロジック (ここが今回の肝) ---
    def save_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save", "", "JSON (*.json)")
        if path:
            json_rows = []
            for item in self.canvas.registered_items:
                d = {
                    "names": item.names,
                    "rect": item.rect.getRect(),
                    "color": item.color.getRgb()
                }
                # 1要素を1行のJSON文字列にする
                row_str = json.dumps(d, ensure_ascii=False)
                json_rows.append(f" {row_str}")

            # 連結して [ \n 行, \n 行 \n ] の形にする
            final_json = "[\n" + ",\n".join(json_rows) + "]"

            with open(path, 'w', encoding='utf-8') as f:
                f.write(final_json)

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open", "", "JSON (*.json)")
        if path: self.load_json_at_path(path)

    def load_json_at_path(self, path):
        if not os.path.exists(path): return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.canvas.registered_items = []
        self.list_widget.clear()
        
        for d in data:
            color = d["color"]
            rect_data = d["rect"]
            names = d.get("names", [d.get("name", "Unknown")])
            
            # ClickRegionを作成してキャンバスに追加
            region = ClickRegion(names, rect_data, color)
            self.canvas.registered_items.append(region)
            
            # UIリストに追加
            self.add_list_item(names, region.rect, region.color)
            
        self.canvas.update()

    # --- その他のヘルパー関数 ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in [".png", ".jpg", ".jpeg"]:
                self.load_image_logic(path)
            elif ext == ".json":
                self.load_json_at_path(path)
        event.acceptProposedAction()

    def load_image_logic(self, path):
        pix = QtGui.QPixmap(path)
        if not pix.isNull():
            self.canvas.setPixmap(pix)
            self.canvas.setFixedSize(pix.size())
            self.splitter.setSizes([pix.width() + 20, self.width() - pix.width()])
            self.canvas.update()
            
            base_path = os.path.splitext(path)[0]
            json_path = base_path + ".json"
            if os.path.exists(json_path):
                self.load_json_at_path(json_path)

    def do_register(self):
        text = self.edit_names.text()
        names = [n.strip() for n in text.split(",") if n.strip()]
        if not self.canvas.temp_rect.isNull() and names:
            color = [0, 255, 0]
            region = ClickRegion(names, self.canvas.temp_rect.getRect(), color)
            self.canvas.registered_items.append(region)
            self.add_list_item(names, self.canvas.temp_rect, QtGui.QColor(*color))
            self.canvas.temp_rect = QtCore.QRect(); self.canvas.update()

    def add_list_item(self, names, rect, color):
        item = QtWidgets.QListWidgetItem(self.list_widget)
        idx = self.list_widget.count() - 1
        item_widget = ListColorItem(names, rect, color, idx)
        item_widget.names_changed.connect(self.update_item_names)
        item_widget.color_changed.connect(self.update_item_color)
        item_widget.rect_changed.connect(self.update_item_rect)
        item.setSizeHint(item_widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)

    def update_item_names(self, index, new_names_list):
        if index < len(self.canvas.registered_items):
            self.canvas.registered_items[index].names = new_names_list

    def batch_replace_names(self):
        f, r = self.edit_find.text(), self.edit_replace.text()
        if not f: return
        for i, region in enumerate(self.canvas.registered_items):
            region.names = [n.replace(f, r) for n in region.names]
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w: w.names_edit.setText(", ".join(region.names))

    def update_item_color(self, index, new_color):
        self.canvas.registered_items[index].color = new_color; self.canvas.update()

    def update_item_rect(self, index, rect_list):
        self.canvas.registered_items[index].rect = QtCore.QRect(*rect_list); self.canvas.update()

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

    def select_list_from_canvas(self, index):
        self.list_widget.setCurrentRow(index)

    def sync_list_to_canvas(self, row):
        self.canvas.selected_index = row
        self.canvas.update()

    def clear_ui_selection(self):
        self.list_widget.setCurrentRow(-1) 

    def get_max_selection_names(self):
        sel = list(mxs.selection)
        if sel:
            names = [n.name for n in sel]
            self.edit_names.setText(", ".join(names))

if __name__ == "__main__":
    for w in QtWidgets.QApplication.allWidgets():
        if w.windowTitle() == "PickerEditor - Max Version": w.close()
    ui = PickerEditor()
    ui.show()