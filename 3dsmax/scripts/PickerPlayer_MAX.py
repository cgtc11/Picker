# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

class ClickRegion:
    def __init__(self, names, rect_data, color):
        # namesが単一文字列の場合もリストとして扱う
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        # リスト(RGBA)でもQColorオブジェクトでも柔軟に受け取る
        if isinstance(color, list):
            self.color = QtGui.QColor(*color)
        else:
            self.color = QtGui.QColor(color)

class PickerCanvas(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_items = []
        self.selected_index = -1 
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setText("Drop Picker File")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        painter = QtGui.QPainter(self)
        # 高品質な描画設定
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        for i, item in enumerate(self.registered_items):
            # 選択中の枠を太く (4px)、それ以外を (1px)
            pen_width = 4 if i == self.selected_index else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(item.rect)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        hit = False
        
        for i, region in enumerate(self.registered_items):
            if region.rect.contains(pos):
                hit = True
                self.selected_index = i
                self.update() 
                
                # Max上のノードを選択
                nodes = [mxs.getNodeByName(name) for name in region.names]
                valid_nodes = [n for n in nodes if n]
                if valid_nodes: 
                    mxs.select(valid_nodes)
                else:
                    # ノードが見つからない場合は選択解除（任意）
                    mxs.deselect(mxs.selection)
                break

        if not hit:
            self.selected_index = -1
            mxs.deselect(mxs.selection)
            self.update()

class PickerPlayer(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Picker Player - Max")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAcceptDrops(True)
        self.resize(300, 300)

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
            if os.path.exists(path): self.load_resource(path)
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
                
                # 画像と同名のJSONを自動検索
                json_path = os.path.splitext(path)[0] + ".json"
                if os.path.exists(json_path): 
                    self.load_json(json_path)
        elif ext == ".json": 
            self.load_json(path)

    def load_json(self, path):
        try:
            # エディタ側の出力に合わせてUTF-8指定で読み込み
            with open(path, 'r', encoding='utf-8') as f: 
                data = json.load(f)
            
            self.canvas.registered_items = []
            self.canvas.selected_index = -1 
            
            for d in data:
                # エディタ側のキー名称（names, rect, color）に準拠
                names = d.get("names", [d.get("name", "Unknown")])
                rect_data = d.get("rect")
                color_data = d.get("color")
                
                if rect_data and color_data:
                    region = ClickRegion(names, rect_data, color_data)
                    self.canvas.registered_items.append(region)
            
            self.canvas.update()
        except Exception as e: 
            print(f"Load Error: {e}")

# --- 実行セクション ---
if __name__ == "__main__":
    # 既存の同名ウィンドウを安全に破棄（二重起動防止）
    for w in QtWidgets.QApplication.allWidgets():
        if w.windowTitle().startswith("Picker Player - Max") or w.windowTitle().startswith("Picker:"):
            w.close()
            w.deleteLater()
            
    ui = PickerPlayer()
    ui.show()