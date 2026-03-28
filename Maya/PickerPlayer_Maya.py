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
        # リスト形式 [r, g, b, a] または QColor オブジェクトに対応
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class PickerCanvas(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_items = []
        self.selected_index = -1 
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setText("Drop Image or JSON here")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        painter = QtGui.QPainter(self)
        for i, item in enumerate(self.registered_items):
            # 選択中は太枠(4px)、通常は1px
            pen_width = 4 if i == self.selected_index else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(item.rect)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        hit = False
        
        # Shiftキーの状態を取得
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_shift = (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier)

        for i, region in enumerate(self.registered_items):
            if region.rect.contains(pos):
                hit = True
                self.selected_index = i
                self.update() 
                
                # シーン内に存在するノードのみを抽出
                valid_nodes = [n for n in region.names if cmds.objExists(n)]
                if valid_nodes:
                    # Shift押しで追加選択、なしで置き換え選択
                    cmds.select(valid_nodes, toggle=is_shift, replace=not is_shift)
                break
        
        if not hit:
            self.selected_index = -1
            # 何もないところをクリックしたら全選択解除
            cmds.select(clear=True)
            self.update()

class PickerPlayerMaya(QtWidgets.QWidget):
    def __init__(self, parent=get_maya_main_window()):
        super().__init__(parent)
        self.win_id = "MayaPickerPlayerWindow"
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
                
                # 画像と同名のJSONがあれば自動ロード
                json_path = os.path.splitext(path)[0] + ".json"
                if os.path.exists(json_path):
                    self.load_json(json_path)
        elif ext == ".json":
            self.load_json(path)

    def load_json(self, path):
        try:
            # UTF-8指定で読み込み
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.canvas.registered_items = []
            self.canvas.selected_index = -1 
            for d in data:
                # "names" がなければ古い形式の "name" を探す
                names = d.get("names", [d.get("name", "Unknown")])
                region = ClickRegion(names, d["rect"], d["color"])
                self.canvas.registered_items.append(region)
            
            self.canvas.update()
            print(f"// Loaded Picker JSON: {path}")
        except Exception as e:
            print(f"// Error loading JSON: {e}")

if __name__ == "__main__":
    # 二重起動防止のロジック
    win_title = "Maya Picker"
    for w in QtWidgets.QApplication.topLevelWidgets():
        # タイトル、またはクラス名で判定して既存ウィンドウを閉じる
        if w.windowTitle().startswith("Picker:") or w.windowTitle() == win_title:
            w.close()
            w.deleteLater()
            
    maya_picker_ui = PickerPlayerMaya()
    maya_picker_ui.show()