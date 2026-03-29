# -*- coding: utf-8 -*-
import json
import os
import maya.cmds as cmds
import maya.OpenMayaUI as omui
from PySide6 import QtWidgets, QtCore, QtGui
from shiboken6 import wrapInstance

def get_maya_main_window():
    """Mayaのメインウィンドウを親として取得"""
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class PickerCanvas(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_items = []
        self.selected_indices = set()  # 複数選択の状態を保持
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setText("Drop Image or JSON here")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        for i, item in enumerate(self.registered_items):
            # 選択中のインデックスに含まれていれば太枠 (4px)
            is_selected = i in self.selected_indices
            pen_width = 4 if is_selected else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(item.rect)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        
        # Mayaの流儀に合わせてShiftキーを判定（Ctrlに変更も可能）
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_shift = (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier)

        hit_index = -1
        for i, region in enumerate(self.registered_items):
            if region.rect.contains(pos):
                hit_index = i
                break

        if hit_index != -1:
            region = self.registered_items[hit_index]
            valid_nodes = [n for n in region.names if cmds.objExists(n)]

            if is_shift:
                # --- Shift+クリック: トグル動作 (追加/解除) ---
                if hit_index in self.selected_indices:
                    self.selected_indices.remove(hit_index)
                    if valid_nodes:
                        cmds.select(valid_nodes, deselect=True)
                else:
                    self.selected_indices.add(hit_index)
                    if valid_nodes:
                        cmds.select(valid_nodes, add=True)
            else:
                # --- 通常クリック: 単一選択 ---
                self.selected_indices = {hit_index}
                if valid_nodes:
                    cmds.select(valid_nodes, replace=True)
                else:
                    cmds.select(clear=True)
        else:
            # 何もないところをクリック
            if not is_shift:
                self.selected_indices.clear()
                cmds.select(clear=True)

        self.update()

class PickerPlayerMaya(QtWidgets.QWidget):
    def __init__(self, parent=get_maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Maya Picker")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAcceptDrops(True)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.canvas = PickerCanvas()
        self.main_layout.addWidget(self.canvas)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            self.load_resource(path)
        event.acceptProposedAction()

    def load_resource(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg"]:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                self.setWindowTitle(f"Picker: {os.path.basename(path)}")
                self.canvas.setText("")
                self.canvas.setPixmap(pix)
                self.canvas.setFixedSize(pix.size())
                self.setFixedSize(pix.size())
                
                json_path = os.path.splitext(path)[0] + ".json"
                if os.path.exists(json_path):
                    self.load_json(json_path)
        elif ext == ".json":
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.canvas.registered_items = []
            self.canvas.selected_indices.clear() 
            for d in data:
                names = d.get("names", [d.get("name", "Unknown")])
                region = ClickRegion(names, d["rect"], d["color"])
                self.canvas.registered_items.append(region)
            
            self.canvas.update()
            print(f"// Loaded Picker JSON: {path}")
        except Exception as e:
            print(f"// Error loading JSON: {e}")

# --- 実行 ---
if __name__ == "__main__":
    win_title_prefix = "Picker:"
    win_title_main = "Maya Picker"
    
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.windowTitle().startswith(win_title_prefix) or w.windowTitle() == win_title_main:
            w.close()
            w.deleteLater()
            
    maya_picker_ui = PickerPlayerMaya()
    maya_picker_ui.show()