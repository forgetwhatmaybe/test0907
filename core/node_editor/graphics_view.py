from PyQt5.QtWidgets import QGraphicsView, QGraphicsItem, QMenu, QAction, QApplication
from PyQt5.QtCore import Qt, QPointF, QRectF, QEvent
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QMouseEvent, QCursor
from pathlib import Path
import uuid


class GraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self._zoom = 1.0
        self._zoom_min = 0.2
        self._zoom_max = 5.0
        
        self.dragging_edge = False
        self.drag_edge = None
        self.drag_start_socket = None
        self._pan_mode = False
    
    def wheelEvent(self, event):
        zoom_factor = 1.15
        
        if event.angleDelta().y() < 0:
            zoom_factor = 1.0 / zoom_factor
        
        new_zoom = self._zoom * zoom_factor
        
        if self._zoom_min <= new_zoom <= self._zoom_max:
            self._zoom = new_zoom
            self.scale(zoom_factor, zoom_factor)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_mode = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self._pan_start = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.LeftButton:
            if hasattr(self, 'on_template_place') and self.cursor().shape() == Qt.CrossCursor:
                pos = self.mapToScene(event.pos())
                self.on_template_place(pos)
                return
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_mode = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.viewport().setCursor(Qt.ArrowCursor)
        
        if self.dragging_edge and event.button() == Qt.LeftButton:
            self._finish_dragging_edge(event.pos())
        
        super().mouseReleaseEvent(event)
        
        # 节点拖拽结束后自动扩展场景
        if event.button() == Qt.LeftButton:
            scene = self.scene()
            if scene and hasattr(scene, '_auto_expand_scene'):
                scene._auto_expand_scene()
    
    def mouseMoveEvent(self, event):
        if self._pan_mode:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            return
        
        if self.dragging_edge and self.drag_edge:
            pos = self.mapToScene(event.pos())
            self.drag_edge.set_end_pos(pos)
        
        super().mouseMoveEvent(event)
    
    def _finish_dragging_edge(self, pos):
        edge_created = False
        if self.drag_edge:
            scene_pos = self.mapToScene(pos)
            # 使用矩形区域搜索，命中区域扩大到 24px
            hit = 24
            search_rect = QRectF(scene_pos.x() - hit, scene_pos.y() - hit, hit * 2, hit * 2)
            items = self.scene().items(search_rect)

            start_type = self.drag_start_socket.socket_type
            target_type = 'input' if start_type == 'output' else 'output'

            end_socket = None
            for item in items:
                if hasattr(item, 'socket_type') and item.socket_type == target_type:
                    if item.node != self.drag_start_socket.node:
                        end_socket = item
                        break

            if end_socket:
                from core.node_editor.edge import Edge

                # 确定输入/输出端口
                if start_type == 'output':
                    out_socket, in_socket = self.drag_start_socket, end_socket
                else:
                    out_socket, in_socket = end_socket, self.drag_start_socket

                # 输入端口只允许一条连线（multi_input 除外）
                if not getattr(in_socket, 'multi_input', False):
                    for edge in in_socket.edges[:]:
                        edge.remove()

                new_edge = Edge(out_socket, in_socket)
                self.scene().add_edge(new_edge)
                edge_created = True

                # —— multi_input 批量连接：把所有选中的同类节点也连上 ——
                if getattr(in_socket, 'multi_input', False) and start_type == 'output':
                    drag_src_node = self.drag_start_socket.node
                    drag_src_type = drag_src_node.node_type
                    drag_src_idx = drag_src_node.outputs.index(self.drag_start_socket)
                    # 已经连接的节点 id 集合，避免重复
                    connected_ids = {e.start_socket.node.id for e in in_socket.edges if e.start_socket}
                    for item in self.scene().selectedItems():
                        if (hasattr(item, 'node_type')
                                and item.node_type == drag_src_type
                                and item.id != drag_src_node.id
                                and item.id not in connected_ids
                                and len(item.outputs) > drag_src_idx):
                            extra_edge = Edge(item.outputs[drag_src_idx], in_socket)
                            self.scene().add_edge(extra_edge)
            else:
                # 未命中目标 socket —— 弹出快捷创建菜单
                self._show_edge_drop_menu(pos, scene_pos, start_type)

            if self.drag_edge in self.scene().edges:
                self.scene().remove_edge(self.drag_edge)

            self.drag_edge = None

        self.dragging_edge = False
        self.drag_start_socket = None

        if edge_created and hasattr(self, 'on_edge_created'):
            self.on_edge_created()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_selected_items()
        super().keyPressEvent(event)
    
    def delete_selected_items(self):
        scene = self.scene()
        selected = scene.selectedItems()
        
        for item in selected:
            if hasattr(item, 'node_type'):
                scene.remove_node(item)
            elif hasattr(item, 'edge_type'):
                item.remove()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            pos = self.mapToScene(event.pos())
            IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff'}
            VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'}
            image_files = []
            video_files = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path:
                    ext = Path(file_path).suffix.lower()
                    if ext in IMAGE_EXTS:
                        image_files.append(file_path)
                    elif ext in VIDEO_EXTS:
                        video_files.append(file_path)
            if image_files and hasattr(self, 'on_image_file_drop'):
                self.on_image_file_drop(image_files, pos)
            if video_files and hasattr(self, 'on_video_file_drop'):
                self.on_video_file_drop(video_files, pos)
            event.acceptProposedAction()
        elif event.mimeData().hasText():
            node_type = event.mimeData().text()
            pos = self.mapToScene(event.pos())
            if hasattr(self, 'on_node_drop'):
                self.on_node_drop(node_type, pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    
    def contextMenuEvent(self, event):
        """右键菜单：快速添加节点"""
        # 如果右键点击在已有节点上，交给节点自己处理
        item = self.itemAt(event.pos())
        if item is not None:
            super().contextMenuEvent(event)
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 0px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 30px;
                border-radius: 4px;
                margin: 2px 6px;
            }
            QMenu::item:selected {
                background-color: #3d6ea5;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 4px 10px;
            }
        """)

        node_items = [
            ("🖼  图片上传", "image"),
            ("🎞  视频上传", "video"),
            ("🎬  可灵生视频", "kling_api"),
            ("🎥  即梦生视频", "jimeng_api"),
            ("🍌  香蕉生图", "gemini_api"),
            ("🎬  Veo生视频", "veo_api"),
            ("✏  图片修改", "image_edit"),
            ("📤  视频(图片)输出", "output"),
        ]

        for label, node_type in node_items:
            action = QAction(label, menu)
            action.setData(node_type)
            menu.addAction(action)

        chosen = menu.exec_(event.globalPos())
        if chosen:
            node_type = chosen.data()
            pos = self.mapToScene(event.pos())
            if hasattr(self, 'on_node_drop'):
                self.on_node_drop(node_type, pos)

    def _show_edge_drop_menu(self, view_pos, scene_pos, start_type):
        """从 socket 拖线到空白处松开时，弹出快捷菜单创建节点并自动连线"""
        source_node = self.drag_start_socket.node
        source_node_type = getattr(source_node, 'node_type', '')

        # 根据拖线方向和来源节点类型决定菜单项
        menu_items = []
        if start_type == 'output':
            # 从输出口拖出：可以创建下游节点
            if source_node_type in ('kling_api', 'jimeng_api', 'gemini_api', 'veo_api', 'image', 'image_edit'):
                menu_items.append(("📤  视频(图片)输出", "output"))
            if source_node_type in ('image', 'gemini_api', 'output', 'image_edit'):
                # 图片/输出可连到API节点或图片修改节点
                menu_items.append(("🎬  可灵生视频", "kling_api"))
                menu_items.append(("🎥  即梦生视频", "jimeng_api"))
                menu_items.append(("🍌  香蕉生图", "gemini_api"))
                menu_items.append(("🎬  Veo生视频", "veo_api"))
                menu_items.append(("✏  图片修改", "image_edit"))
            if source_node_type == 'video':
                menu_items.append(("📤  视频(图片)输出", "output"))
        else:
            # 从输入口拖出：可以创建上游节点
            if source_node_type in ('kling_api', 'jimeng_api', 'gemini_api', 'veo_api', 'image_edit'):
                menu_items.append(("🖼  图片上传", "image"))
                menu_items.append(("🍌  香蕉生图", "gemini_api"))
                menu_items.append(("📤  视频(图片)输出", "output"))
            if source_node_type == 'output':
                menu_items.append(("🎬  可灵生视频", "kling_api"))
                menu_items.append(("🎥  即梦生视频", "jimeng_api"))
                menu_items.append(("🍌  香蕉生图", "gemini_api"))
                menu_items.append(("🎬  Veo生视频", "veo_api"))
                menu_items.append(("✏  图片修改", "image_edit"))
                menu_items.append(("🎞  视频上传", "video"))

        if not menu_items:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 0px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 30px;
                border-radius: 4px;
                margin: 2px 6px;
            }
            QMenu::item:selected {
                background-color: #3d6ea5;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 4px 10px;
            }
        """)

        for label, node_type in menu_items:
            action = QAction(label, menu)
            action.setData(node_type)
            menu.addAction(action)

        # 保存拖线源信息（菜单执行期间 drag_start_socket 可能已清空）
        saved_socket = self.drag_start_socket
        saved_start_type = start_type

        chosen = menu.exec_(QCursor.pos())
        if chosen and hasattr(self, 'on_edge_drop_create'):
            node_type = chosen.data()
            self.on_edge_drop_create(node_type, scene_pos, saved_socket, saved_start_type)

    def start_edge_drag(self, start_socket):
        self.dragging_edge = True
        self.drag_start_socket = start_socket
        
        from core.node_editor.edge import Edge
        self.drag_edge = Edge(start_socket, None, dragging=True)
        self.scene().add_edge(self.drag_edge)
