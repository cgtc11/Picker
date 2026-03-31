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
            # 5ピクセル以上の移動があればドラッグとみなす
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
            is_shift = (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier)
            
            if self.is_dragging:
                # --- ドラッグ範囲選択の確定 ---
                new_selections = set()
                for i, item in enumerate(self.registered_items):
                    scaled_rect = QtCore.QRect(
                        item.rect.x() * self.scale, item.rect.y() * self.scale,
                        item.rect.width() * self.scale, item.rect.height() * self.scale
                    )
                    if self.selection_rect.intersects(scaled_rect):
                        new_selections.add(i)
                
                if is_shift:
                    self.selected_indices |= new_selections
                else:
                    self.selected_indices = new_selections
            else:
                # --- クリック単一選択の確定 ---
                # scaleを考慮してクリック位置を画像上の座標に変換
                raw_pos = QtCore.QPoint(self.origin.x() / self.scale, self.origin.y() / self.scale)
                hit_index = -1
                for i, region in enumerate(self.registered_items):
                    if region.rect.contains(raw_pos):
                        hit_index = i
                        break

                if hit_index != -1:
                    if is_shift:
                        if hit_index in self.selected_indices:
                            self.selected_indices.remove(hit_index)
                        else:
                            self.selected_indices.add(hit_index)
                    else:
                        self.selected_indices = {hit_index}
                else:
                    # 何もないところをクリックしたら解除
                    if not is_shift:
                        self.selected_indices.clear()

            # 最終的な選択リストに基づいてMayaを更新
            self._update_maya_selection(is_shift)
            
            self.is_dragging = False
            self.selection_rect = QtCore.QRect()
            self.update()

    def _update_maya_selection(self, is_shift):
        """現在の選択状態をMayaに反映"""
        nodes_to_select = []
        for idx in self.selected_indices:
            region = self.registered_items[idx]
            valid_nodes = [n for n in region.names if cmds.objExists(n)]
            nodes_to_select.extend(valid_nodes)

        if nodes_to_select:
            # Shift時は追加選択(add=True)、通常時は置換(replace=True)
            cmds.select(nodes_to_select, replace=not is_shift, add=is_shift)
        else:
            # 選択リストが空でShiftも押されていない場合は全解除
            if not is_shift:
                cmds.select(clear=True)

class PickerPlayerMaya(QtWidgets.QWidget):
    def __init__(self, parent=get_maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Maya Picker")
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
            self.load_resource(path)
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
        try:
            if w.windowTitle().startswith(win_title_prefix) or w.windowTitle() == win_title_main:
                w.close()
                w.deleteLater()
        except: pass
            
    maya_picker_ui = PickerPlayerMaya()
    maya_picker_ui.show()