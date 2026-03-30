# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        if isinstance(color, list):
            self.color = QtGui.QColor(*color)
        else:
            self.color = QtGui.QColor(color)

class PickerCanvas(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_items = []
        self.selected_indices = set()
        
        # ドラッグ選択用の管理変数
        self.origin = QtCore.QPoint()
        self.selection_rect = QtCore.QRect()
        self.is_dragging = False
        
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setText("Drop Picker File")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        for i, item in enumerate(self.registered_items):
            is_selected = i in self.selected_indices
            pen_width = 4 if is_selected else 1
            color = item.color
            painter.setPen(QtGui.QPen(color, pen_width))
            painter.drawRect(item.rect)

        if self.is_dragging and not self.selection_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1, QtCore.Qt.PenStyle.DashLine))
            painter.setBrush(QtGui.QColor(255, 255, 255, 40))
            painter.drawRect(self.selection_rect)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.selection_rect = QtCore.QRect(self.origin, QtCore.QSize())
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self.origin).manhattanLength() > 5:
                self.is_dragging = True
            
            if self.is_dragging:
                self.selection_rect = QtCore.QRect(self.origin, event.position().toPoint()).normalized()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            is_ctrl = modifiers == QtCore.Qt.KeyboardModifier.ControlModifier
            
            if self.is_dragging:
                new_selections = set()
                for i, item in enumerate(self.registered_items):
                    if self.selection_rect.intersects(item.rect):
                        new_selections.add(i)
                
                if is_ctrl:
                    self.selected_indices |= new_selections
                else:
                    self.selected_indices = new_selections
                
                self._update_max_selection(is_ctrl)
            else:
                pos = self.origin
                hit_index = -1
                for i, region in enumerate(self.registered_items):
                    if region.rect.contains(pos):
                        hit_index = i
                        break

                if hit_index != -1:
                    if is_ctrl:
                        if hit_index in self.selected_indices:
                            self.selected_indices.remove(hit_index)
                        else:
                            self.selected_indices.add(hit_index)
                    else:
                        self.selected_indices = {hit_index}
                    self._update_max_selection(is_ctrl)
                else:
                    if not is_ctrl:
                        self.selected_indices.clear()
                        mxs.deselect(mxs.selection)

            self.is_dragging = False
            self.selection_rect = QtCore.QRect()
            self.update()

    def _update_max_selection(self, is_ctrl):
        nodes_to_select = []
        for idx in self.selected_indices:
            region = self.registered_items[idx]
            nodes = [mxs.getNodeByName(name) for name in region.names]
            nodes_to_select.extend([n for n in nodes if n])

        if nodes_to_select:
            if is_ctrl:
                mxs.selectMore(nodes_to_select)
            else:
                mxs.select(nodes_to_select)
        else:
            if not is_ctrl:
                mxs.deselect(mxs.selection)

class PickerPlayer(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Picker")
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAcceptDrops(True)

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.canvas = PickerCanvas()
        self.main_layout.addWidget(self.canvas)
        
        # 初期状態を極小に固定（テキストの長さに合わせる）
        self.setFixedSize(150, 30)

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
                
                # 画像読み込み時に固定サイズを解除して画像サイズで再固定
                self.setMinimumSize(0, 0)
                self.setMaximumSize(16777215, 16777215)
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
                rect_data = d.get("rect")
                color_data = d.get("color")
                
                if rect_data and color_data:
                    region = ClickRegion(names, rect_data, color_data)
                    self.canvas.registered_items.append(region)
            
            self.canvas.update()
        except Exception as e: 
            print(f"Load Error: {e}")

if __name__ == "__main__":
    for w in QtWidgets.QApplication.allWidgets():
        if isinstance(w, PickerPlayer):
            w.close()
            w.deleteLater()
            
    ui = PickerPlayer()
    ui.show()