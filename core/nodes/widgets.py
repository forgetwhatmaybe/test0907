"""共享的自定义 UI 组件"""

from PyQt5.QtWidgets import (
    QPushButton, QLabel, QWidget, QVBoxLayout, QGridLayout, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QMimeData, QUrl, QTimer
from PyQt5.QtGui import QDrag, QCursor, QColor, QIcon
from pathlib import Path

from .cache import ThumbnailCache
from . import styles


class DoubleClickButton(QPushButton):
    """支持双击信号和拖拽文件的 QPushButton"""
    doubleClicked = pyqtSignal()
    drag_started = pyqtSignal(str)  # 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self._file_path = None
        self.setAcceptDrops(True)
    
    def set_file_path(self, path):
        """设置要拖拽的文件路径"""
        self._file_path = path

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and self._file_path:
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= 10:  # 拖拽阈值
                self._start_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
    
    def _start_drag(self):
        """开始拖拽文件"""
        if not self._file_path or not Path(self._file_path).exists():
            return
        
        drag = QDrag(self)
        mime_data = QMimeData()
        url = QUrl.fromLocalFile(self._file_path)
        mime_data.setUrls([url])
        mime_data.setText(self._file_path)
        drag.setMimeData(mime_data)
        
        if self.icon():
            drag.setPixmap(self.icon().pixmap(64, 64))
        
        drag.exec_(Qt.CopyAction)


class DraggableThumbnail(QLabel):
    """可拖拽的缩略图标签，通过鼠标拖放排序
    
    在 ImageThumbnailStrip 中使用，支持拖拽排序功能。
    """
    
    def __init__(self, node_id, image_path, index, parent_strip):
        super().__init__()
        self.node_id = node_id
        self.image_path = image_path
        self.index = index
        self._parent_strip = parent_strip
        
        self.setFixedSize(40, 40)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(f"#{index + 1} {Path(image_path).name}")
        self._update_style(False)
        
        # 加载缩略图（使用缓存）
        pixmap = ThumbnailCache.get(image_path, 36, 36)
        if pixmap and not pixmap.isNull():
            self.setPixmap(pixmap)
        else:
            self.setText("?")
            self.setStyleSheet(self.styleSheet() + "color: #888; font-size: 11px;")
    
    def _update_style(self, dragging):
        """更新样式状态"""
        if dragging:
            self.setStyleSheet(styles.THUMBNAIL_DRAGGING)
        else:
            self.setStyleSheet(styles.THUMBNAIL)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.ClosedHandCursor)
            self._update_style(True)
            self._parent_strip._start_drag(self.index, event.globalPos())
            event.accept()
            return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._parent_strip._update_drag(event.globalPos())
            event.accept()
            return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.OpenHandCursor)
            self._update_style(False)
            self._parent_strip._finish_drag(event.globalPos())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ImageThumbnailStrip(QWidget):
    """可拖拽排序的图片缩略图条
    
    显示在提示词上方，使用鼠标事件（非 QDrag）实现拖拽排序，
    因为 QGraphicsProxyWidget 内部无法正常使用 QDrag。
    使用 QGridLayout 实现自动换行，每行4张缩略图。
    
    Signals:
        order_changed: 当用户完成拖拽排序后发射
    """
    
    order_changed = pyqtSignal()
    COLS = 4  # 每行显示4张
    THUMB_SIZE = 40
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ordered_items = []  # [(node_id, image_path), ...]
        self._dragging = False
        self._drag_source_idx = -1
        self._drag_start_global = None
        self._highlight_idx = -1
        
        self._grid_layout = QGridLayout(self)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        self._grid_layout.setSpacing(3)
        
        self.setFixedHeight(0)  # 无图片时隐藏
    
    def update_thumbnails(self, connected_items):
        """更新缩略图列表
        
        Args:
            connected_items: [(node_id, image_path), ...] 当前所有连接的图片
        """
        old_ids = {item[0] for item in self._ordered_items}
        new_ids = {item[0] for item in connected_items}
        new_map = {item[0]: item[1] for item in connected_items}
        
        # 保留还在连接中的旧顺序项
        kept = [(nid, new_map[nid]) for nid, _ in self._ordered_items if nid in new_ids]
        
        # 追加新连接的到末尾
        added_ids = new_ids - old_ids
        for nid, path in connected_items:
            if nid in added_ids:
                kept.append((nid, path))
        
        self._ordered_items = kept
        self._rebuild_widgets()
    
    def get_ordered_node_ids(self):
        """获取排序后的节点 ID 列表"""
        return [nid for nid, _ in self._ordered_items]
    
    def get_ordered_image_paths(self):
        """获取排序后的图片路径列表"""
        return [path for _, path in self._ordered_items]
    
    def set_order(self, node_ids):
        """根据节点 ID 列表重新排序"""
        id_map = {nid: path for nid, path in self._ordered_items}
        reordered = []
        used = set()
        for nid in node_ids:
            if nid in id_map and nid not in used:
                reordered.append((nid, id_map[nid]))
                used.add(nid)
        # 补充未在指定顺序中的项
        for nid, path in self._ordered_items:
            if nid not in used:
                reordered.append((nid, path))
        self._ordered_items = reordered
        self._rebuild_widgets()
    
    def _rebuild_widgets(self):
        """重建所有缩略图控件"""
        # 清空现有控件
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._ordered_items:
            self.setFixedHeight(0)
            return
        
        for i, (node_id, path) in enumerate(self._ordered_items):
            thumb = DraggableThumbnail(node_id, path, i, self)
            row = i // self.COLS
            col = i % self.COLS
            self._grid_layout.addWidget(thumb, row, col)
        
        count = len(self._ordered_items)
        rows = (count + self.COLS - 1) // self.COLS
        row_height = self.THUMB_SIZE + 6
        self.setFixedHeight(rows * row_height + 6)
    
    # ---- 鼠标拖拽排序（由 DraggableThumbnail 触发） ----
    
    def _start_drag(self, source_idx, global_pos):
        """开始拖拽"""
        self._dragging = True
        self._drag_source_idx = source_idx
        self._drag_start_global = global_pos
        self._highlight_idx = source_idx
    
    def _update_drag(self, global_pos):
        """更新拖拽位置"""
        if not self._dragging:
            return
        target_idx = self._find_closest_index(self.mapFromGlobal(global_pos))
        if target_idx != self._highlight_idx:
            self._highlight_idx = target_idx
            self._update_highlight(target_idx)
    
    def _finish_drag(self, global_pos):
        """完成拖拽"""
        if not self._dragging:
            return
        self._dragging = False
        
        target_idx = self._find_closest_index(self.mapFromGlobal(global_pos))
        source_idx = self._drag_source_idx
        self._drag_source_idx = -1
        self._highlight_idx = -1
        
        if source_idx < 0 or source_idx == target_idx:
            self._rebuild_widgets()
            return
        
        # 移动元素
        item = self._ordered_items.pop(source_idx)
        if target_idx > source_idx:
            target_idx -= 1
        target_idx = max(0, min(target_idx, len(self._ordered_items)))
        self._ordered_items.insert(target_idx, item)
        
        self._rebuild_widgets()
        self.order_changed.emit()
    
    def _find_closest_index(self, local_pos):
        """根据鼠标位置找到最近的缩略图索引"""
        if not self._ordered_items:
            return 0
        
        min_dist = float('inf')
        target_idx = len(self._ordered_items)
        
        for i in range(self._grid_layout.count()):
            w = self._grid_layout.itemAt(i).widget()
            if w and isinstance(w, DraggableThumbnail):
                center = w.geometry().center()
                dx = local_pos.x() - center.x()
                dy = local_pos.y() - center.y()
                dist = dx * dx + dy * dy
                if dist < min_dist:
                    min_dist = dist
                    if local_pos.x() < center.x():
                        target_idx = w.index
                    else:
                        target_idx = w.index + 1
        return target_idx
    
    def _update_highlight(self, target_idx):
        """高亮目标位置"""
        for i in range(self._grid_layout.count()):
            w = self._grid_layout.itemAt(i).widget()
            if w and isinstance(w, DraggableThumbnail):
                if w.index == target_idx and w.index != self._drag_source_idx:
                    w.setStyleSheet(styles.THUMBNAIL_HIGHLIGHT)
                elif w.index == self._drag_source_idx:
                    w._update_style(True)
                else:
                    w._update_style(False)
