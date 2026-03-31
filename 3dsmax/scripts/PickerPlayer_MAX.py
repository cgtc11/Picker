# -*- coding: utf-8 -*-
import json
import os
from PySide6 import QtWidgets, QtCore, QtGui
from pymxs import runtime as mxs

class ClickRegion:
    def __init__(self, names, rect_data, color):
        self.names = names if isinstance(names, list) else [names]
        self.rect = QtCore.QRect(*rect_data)
        self.color = QtGui.QColor(*color) if isinstance(color, list) else QtGui.QColor(color)

class PickerCanvas(QtWidgets.QLabel):
    pan_requested = QtCore.Signal(QtCore.QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered_items = []
        self.selected_indices = set()
        
        self.origin = QtCore.QPoint()
        self.selection_rect = QtCore.QRect()
        self.is_dragging = False
        
        # ズーム・パン用
        self.scale = 1.0
        self.pixmap_original = None
        self.last_pan_pos = None
        
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.setText("Drop Image or JSON here")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")

    def set_image(self, pixmap):
        self.pixmap_original = pixmap
        self.scale = 1.0
        self.update_canvas_size()

    def update_canvas_size(self):
        if self.pixmap_original:
            new_size = self.pixmap_original.size() * self.scale
            self.setPixmap(self.pixmap_original.scaled(
                new_size, 
                QtCore.Qt.AspectRatioMode.KeepAspectRatio, 
                QtCore.Qt.TransformationMode.SmoothTransformation
            ))
            self.setFixedSize(new_size)

    def wheelEvent(self, event):
        if not self.pixmap_original: return
        delta = event.angleDelta().y()
        old_scale = self.scale
        if delta > 0: self.scale *= 1.1
        else: self.scale /= 1.1
        self.scale = max(0.1, min(self.scale, 10.0))
        if old_scale != self.scale:
            self.update_canvas_size()
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        for i, item in enumerate(self.registered_items):
            is_selected = i in self.selected_indices
            scaled_rect = QtCore.QRect(
                item.rect.x() * self.scale, item.rect.y() * self.scale,
                item.rect.width() * self.scale, item.rect.height() * self.scale
            )
            pen_width = 4 if is_selected else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(scaled_rect)

        if self.is_dragging and not self.selection_rect.isNull():
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1, QtCore.Qt.PenStyle.DashLine))
            painter.setBrush(QtGui.QColor(255, 255, 255, 40))
            painter.drawRect(self.selection_rect)

    def mousePressEvent(self, event):
        # パン操作 (中クリック または Alt+左クリック)
        if event.button() == QtCore.Qt.MouseButton.MiddleButton or \
           (event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self.last_pan_pos = event.globalPosition().toPoint()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.selection_rect = QtCore.QRect(self.origin, QtCore.QSize())
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if self.last_pan_pos:
            delta = event.globalPosition().toPoint() - self.last_pan_pos
            self.pan_requested.emit(delta)
            self.last_pan_pos = event.globalPosition().toPoint()
            return

        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self.origin).manhattanLength() > 5:
                self.is_dragging = True
            
            if self.is_dragging:
                self.selection_rect = QtCore.QRect(self.origin, event.position().toPoint()).normalized()
                self.update()

    def mouseReleaseEvent(self, event):
        self.last_pan_pos = None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
                return

            modifiers = QtWidgets.QApplication.keyboardModifiers()
            is_ctrl = (modifiers == QtCore.Qt.KeyboardModifier.ControlModifier)
            
            if self.is_dragging:
                # --- ドラッグ範囲選択 ---
                new_selections = set()
                for i, item in enumerate(self.registered_items):
                    scaled_rect = QtCore.QRect(
                        item.rect.x() * self.scale, item.rect.y() * self.scale,
                        item.rect.width() * self.scale, item.rect.height() * self.scale
                    )
                    if self.selection_rect.intersects(scaled_rect):
                        new_selections.add(i)
                
                if is_ctrl: self.selected_indices |= new_selections
                else: self.selected_indices = new_selections
            else:
                # --- クリック単一選択 ---
                raw_pos = QtCore.QPoint(self.origin.x() / self.scale, self.origin.y() / self.scale)
                hit_index = -1
                for i, region in enumerate(self.registered_items):
                    if region.rect.contains(raw_pos):
                        hit_index = i
                        break

                if hit_index != -1:
                    if is_ctrl:
                        if hit_index in self.selected_indices: self.selected_indices.remove(hit_index)
                        else: self.selected_indices.add(hit_index)
                    else:
                        self.selected_indices = {hit_index}
                else:
                    if not is_ctrl:
                        self.selected_indices.clear()

            self._update_max_selection(is_ctrl)
            self.is_dragging = False
            self.selection_rect = QtCore.QRect()
            self.update()

    def _update_max_selection(self, is_ctrl):
        """現在の選択状態を3ds Maxに反映"""
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
        
        # 起動時は最小サイズ
        self.setFixedSize(160, 25)
        self.first_load = True
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setStyleSheet("background-color: #1a1a1a; border: none;")
        
        self.canvas = PickerCanvas()
        self.scroll.setWidget(self.canvas)
        self.main_layout.addWidget(self.scroll)
        
        self.canvas.pan_requested.connect(self.handle_pan)

    def handle_pan(self, delta):
        h = self.scroll.horizontalScrollBar()
        v = self.scroll.verticalScrollBar()
        h.setValue(h.value() - delta.x())
        v.setValue(v.value() - delta.y())

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
                self.canvas.set_image(pix)
                
                # 初回読み込み時のみウィンドウサイズを調整
                if self.first_load:
                    self.setMinimumSize(0, 0)
                    self.setMaximumSize(16777215, 16777215)
                    self.setFixedSize(pix.size())
                    self.setMinimumSize(100, 100)
                    self.setMaximumSize(16777215, 16777215)
                    self.first_load = False
                
                json_path = os.path.splitext(path)[0] + ".json"
                if os.path.exists(json_path): self.load_json(json_path)
        elif ext == ".json":
            self.load_json(path)

    def load_json(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.canvas.registered_items = []
            self.canvas.selected_indices.clear()
            for d in data:
                color = d.get("color", [0, 255, 0])
                names = d.get("names", [d.get("name", "Unknown")])
                region = ClickRegion(names, d["rect"], color)
                self.canvas.registered_items.append(region)
            self.canvas.update()
        except Exception as e:
            print(f"Load Error: {e}")

if __name__ == "__main__":
    # 既存のウィンドウを閉じる
    for w in QtWidgets.QApplication.allWidgets():
        if isinstance(w, PickerPlayer):
            w.close()
            w.deleteLater()
            
    ui = PickerPlayer()
    ui.show()