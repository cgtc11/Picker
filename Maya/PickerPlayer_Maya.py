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
        
        # ドラッグ選択用の管理変数
        self.origin = QtCore.QPoint()
        self.selection_rect = QtCore.QRect()
        self.is_dragging = False
        
        self.setMouseTracking(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setText("Drop Image or JSON here")
        self.setStyleSheet("color: #888; background-color: #1a1a1a; border: None;")
        self.setContentsMargins(0, 0, 0, 0)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.pixmap(): return
        
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # 登録アイテム（枠）の描画
        for i, item in enumerate(self.registered_items):
            is_selected = i in self.selected_indices
            pen_width = 4 if is_selected else 1
            painter.setPen(QtGui.QPen(item.color, pen_width))
            painter.drawRect(item.rect)

        # ドラッグ中の選択範囲枠（点線）を表示
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
            # 5ピクセル以上の移動でドラッグ開始と判定
            if (event.position().toPoint() - self.origin).manhattanLength() > 5:
                self.is_dragging = True
            
            if self.is_dragging:
                self.selection_rect = QtCore.QRect(self.origin, event.position().toPoint()).normalized()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            is_shift = (modifiers == QtCore.Qt.KeyboardModifier.ShiftModifier)
            
            if self.is_dragging:
                # --- ドラッグによる範囲選択 ---
                new_selections = set()
                for i, item in enumerate(self.registered_items):
                    # 範囲と交差するアイテムを抽出
                    if self.selection_rect.intersects(item.rect):
                        new_selections.add(i)
                
                if is_shift:
                    self.selected_indices |= new_selections
                else:
                    self.selected_indices = new_selections
                
                self._update_maya_selection(is_shift)
            else:
                # --- 通常のクリック処理 ---
                pos = self.origin
                hit_index = -1
                for i, region in enumerate(self.registered_items):
                    if region.rect.contains(pos):
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
                    self._update_maya_selection(is_shift)
                else:
                    if not is_shift:
                        self.selected_indices.clear()
                        cmds.select(clear=True)

            self.is_dragging = False
            self.selection_rect = QtCore.QRect()
            self.update()

    def _update_maya_selection(self, is_shift):
        """現在の選択インデックスに基づいてMayaの選択状態を更新"""
        nodes_to_select = []
        for idx in self.selected_indices:
            region = self.registered_items[idx]
            valid_nodes = [n for n in region.names if cmds.objExists(n)]
            nodes_to_select.extend(valid_nodes)

        if nodes_to_select:
            if is_shift:
                cmds.select(nodes_to_select, add=True)
            else:
                cmds.select(nodes_to_select, replace=True)
        else:
            if not is_shift:
                cmds.select(clear=True)

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
        
        # 起動時はコンパクトなサイズに（必要に応じて数値を調整）
        self.setFixedSize(160, 25)

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
                
                # 固定解除して画像サイズにリサイズ
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
        except:
            pass
            
    maya_picker_ui = PickerPlayerMaya()
    maya_picker_ui.show()