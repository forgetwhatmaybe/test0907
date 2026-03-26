from PyQt5.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsProxyWidget, QLabel, QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QGraphicsRectItem
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPainterPath, QLinearGradient, QFontMetrics
import uuid


class SocketSignal(QObject):
    connected = pyqtSignal(object)
    disconnected = pyqtSignal(object)


class ToggleButtonSignals(QObject):
    """ToggleButton 的信号对象"""
    clicked = pyqtSignal()


class ToggleButton(QGraphicsRectItem):
    """展开/收起按钮"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_expanded = True
        self.signals = ToggleButtonSignals()
        self.setRect(0, 0, 24, 24)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setBrush(QBrush(QColor("#3a3a3a")))
        self.setPen(QPen(QColor("#5a5a5a"), 1))
        self.setZValue(100)
    
    def set_expanded(self, expanded):
        self._is_expanded = expanded
        self.update()
    
    def is_expanded(self):
        return self._is_expanded
    
    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        
        painter.setPen(QPen(QColor("#ffffff"), 2))
        center_x = int(self.rect().center().x())
        center_y = int(self.rect().center().y())
        
        if self._is_expanded:
            painter.drawLine(center_x - 5, center_y - 2, center_x + 5, center_y - 2)
            painter.drawLine(center_x - 5, center_y + 2, center_x + 5, center_y + 2)
        else:
            painter.drawLine(center_x - 5, center_y, center_x + 5, center_y)
            painter.drawLine(center_x, center_y - 5, center_x, center_y + 5)
    
    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor("#4a4a4a")))
        self.setPen(QPen(QColor("#6a6a6a"), 1))
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor("#3a3a3a")))
        self.setPen(QPen(QColor("#5a5a5a"), 1))
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_expanded = not self._is_expanded
            self.update()
            self.signals.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class Socket(QGraphicsEllipseItem):
    def __init__(self, node, socket_type, index, parent=None, multi_input=False):
        super().__init__(parent)
        self.node = node
        self.socket_type = socket_type
        self.index = index
        self.multi_input = multi_input  # True 时允许多条连线接入同一输入
        self.edges = []
        self.signals = SocketSignal()
        
        self.radius = 10
        self.setRect(-self.radius, -self.radius, self.radius * 2, self.radius * 2)
        
        if multi_input:
            self.color = QColor("#FF9800")  # 橙色表示多连接输入
        elif socket_type == "input":
            self.color = QColor("#4CAF50")
        else:
            self.color = QColor("#2196F3")
        
        self.setBrush(QBrush(self.color))
        self.setPen(QPen(QColor("white"), 2))
        self.setZValue(1000)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
    
    def add_edge(self, edge):
        if edge not in self.edges:
            self.edges.append(edge)
            self.signals.connected.emit(edge)
    
    def remove_edge(self, edge):
        if edge in self.edges:
            self.edges.remove(edge)
            self.signals.disconnected.emit(edge)
    
    def get_pos(self):
        return self.node.pos() + self.pos()
    
    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(self.color.lighter(130)))
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(self.color))
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 输入接口只允许一条连线，拖线前先移除已有连线
            # multi_input 接口跳过此限制
            if self.socket_type == "input" and self.edges and not self.multi_input:
                for edge in self.edges[:]:
                    edge.remove()
            
            scene = self.scene()
            view = scene.views()[0] if scene and scene.views() else None
            if view and hasattr(view, 'start_edge_drag'):
                view.start_edge_drag(self)
        
        super().mousePressEvent(event)


class NodeItem(QGraphicsItem):
    node_type = "base"
    
    def __init__(self, title="Node"):
        super().__init__()
        self.id = str(uuid.uuid4())
        self.title = title
        self.width = 220
        self.height = 150
        
        self.inputs = []
        self.outputs = []
        
        self._title_item = None
        self._content_widget = None
        self._proxy = None
        self._toggle_button = None
        
        # 标记是否正在执行Ctrl+点击全选操作
        self._is_selecting_connected = False
        
        # 优化：批量更新机制
        self._batch_update_pending = False
        self._edges_need_update = set()
        
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(10)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        
        self._setup_ui()
    
    def _setup_ui(self):
        self._title_item = QGraphicsTextItem(self.title, self)
        self._title_item.setDefaultTextColor(QColor("white"))
        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        self._title_item.setFont(font)
        self._title_item.setPos(10, 5)
        
        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        self._setup_content()
        
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(self._content_widget)
        self._proxy.setPos(10, 40)
        self._proxy.setFlag(QGraphicsItem.ItemIsFocusable, True)
        
        self._update_size()
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Base Node")
        label.setStyleSheet("color: white;")
        layout.addWidget(label)
    
    def _add_toggle_button(self):
        """添加展开/收起按钮，由子类调用"""
        self._toggle_button = ToggleButton(self)
        self._toggle_button.signals.clicked.connect(self._on_toggle_clicked)
        self._update_toggle_button_position()
    
    def _update_toggle_button_position(self):
        if self._toggle_button:
            self._toggle_button.setPos(self.width - 28, 3)
    
    def _on_toggle_clicked(self):
        """展开/收起按钮点击回调，由子类重写"""
        pass
    
    def _update_size(self):
        self.prepareGeometryChange()
        if self._content_widget:
            self._content_widget.adjustSize()
            content_size = self._content_widget.sizeHint()
            self.height = max(120, content_size.height() + 60)
            self.width = max(220, content_size.width() + 40)
        self.update_sockets_position()
        self._update_toggle_button_position()
        self.update()
        # 优化：使用批量更新机制，避免频繁更新连线
        self._schedule_edge_updates()
    
    def _schedule_edge_updates(self):
        """调度批量连线更新"""
        if not self._batch_update_pending:
            self._batch_update_pending = True
            QTimer.singleShot(0, self._batch_update_edges)
    
    def _batch_update_edges(self):
        """批量更新所有连线位置"""
        self._batch_update_pending = False
        for socket in self.inputs + self.outputs:
            for edge in socket.edges:
                edge.update_position()
    
    def add_input(self, name="Input"):
        socket = Socket(self, "input", len(self.inputs))
        socket.setParentItem(self)
        self.inputs.append(socket)
        self.update_sockets_position()
        return socket
    
    def add_multi_input(self, name="Multi Input"):
        """添加允许多条连线的输入接口（橙色）"""
        socket = Socket(self, "input", len(self.inputs), multi_input=True)
        socket.setParentItem(self)
        self.inputs.append(socket)
        self.update_sockets_position()
        return socket
    
    def add_output(self, name="Output"):
        socket = Socket(self, "output", len(self.outputs))
        socket.setParentItem(self)
        self.outputs.append(socket)
        self.update_sockets_position()
        return socket
    
    def update_sockets_position(self):
        input_count = len(self.inputs)
        output_count = len(self.outputs)
        
        for i, socket in enumerate(self.inputs):
            y = 50 + (i + 1) * (self.height - 60) / (input_count + 1)
            socket.setPos(-socket.radius, y)
        
        for i, socket in enumerate(self.outputs):
            y = 50 + (i + 1) * (self.height - 60) / (output_count + 1)
            socket.setPos(self.width + socket.radius, y)
    
    def boundingRect(self):
        m = 15  # socket 半径 10 + 边框余量，防止拖动时出现残影
        return QRectF(-m, -m, self.width + m * 2, self.height + m * 2)
    
    def paint(self, painter, option, widget):
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        gradient = QLinearGradient(0, 0, 0, self.height)
        gradient.setColorAt(0, QColor("#3d3d3d"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        
        painter.setBrush(QBrush(gradient))
        
        if self.isSelected():
            painter.setPen(QPen(QColor("#00aaff"), 3))
        else:
            painter.setPen(QPen(QColor("#555555"), 1))
        
        painter.drawPath(path)
        
        header_path = QPainterPath()
        header_path.addRoundedRect(0, 0, self.width, 30, 10, 10)
        header_path.addRect(0, 15, self.width, 15)
        
        header_gradient = QLinearGradient(0, 0, 0, 30)
        header_gradient.setColorAt(0, QColor("#5c5c5c"))
        header_gradient.setColorAt(1, QColor("#4a4a4a"))
        
        painter.setBrush(QBrush(header_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(header_path)
    
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            # 优化：使用批量更新机制，避免频繁更新连线
            self._schedule_edge_updates()
        
        # 拦截选中状态变化，在Ctrl+点击全选时阻止Qt的默认toggle行为
        if change == QGraphicsItem.ItemSelectedChange:
            if self._is_selecting_connected:
                # 如果正在执行Ctrl+点击全选，且即将被设置为未选中，则阻止
                # value 是即将设置的新状态，True=选中，False=未选中
                if not value:  # 如果要取消选中，强制保持选中
                    return True
        
        return super().itemChange(change, value)
    
    def contextMenuEvent(self, event):
        menu = self._create_context_menu()
        if menu:
            menu.exec_(event.screenPos())
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.ControlModifier:
            # 标记正在执行Ctrl+点击全选操作
            self._is_selecting_connected = True
            # 先清除当前选中状态，避免Qt的toggle行为
            self.setSelected(False)
            self._select_connected_nodes()
            event.accept()
            return
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        # Ctrl+点击操作完成后，延迟重置标记并确保选中状态
        if self._is_selecting_connected:
            # 使用定时器延迟执行，确保在Qt的默认toggle行为之后
            QTimer.singleShot(0, self._ensure_selected_after_ctrl_click)
        super().mouseReleaseEvent(event)
    
    def _ensure_selected_after_ctrl_click(self):
        """Ctrl+点击后确保当前节点保持选中状态"""
        self._is_selecting_connected = False
        self.setSelected(True)
    
    def _select_connected_nodes(self):
        """优化：使用迭代替代递归，避免栈溢出风险"""
        connected_nodes = set()
        visited = set()
        stack = [self]
        
        while stack:
            node = stack.pop()
            if node.id in visited:
                continue
            visited.add(node.id)
            connected_nodes.add(node)
            
            # 收集上游节点
            for socket in node.inputs:
                for edge in socket.edges:
                    if edge.start_socket and edge.start_socket.node:
                        stack.append(edge.start_socket.node)
            
            # 收集下游节点
            for socket in node.outputs:
                for edge in socket.edges:
                    if edge.end_socket and edge.end_socket.node:
                        stack.append(edge.end_socket.node)
        
        scene = self.scene()
        if scene:
            scene.clearSelection()
        
        for node in connected_nodes:
            node.setSelected(True)
        
        # 确保当前节点被选中（解决 Ctrl+点击时当前节点选中状态问题）
        self.setSelected(True)
    
    def _create_context_menu(self):
        return None
    
    def serialize(self):
        return {
            "id": self.id,
            "type": self.node_type,
            "title": self.title,
            "pos": {"x": self.pos().x(), "y": self.pos().y()},
            "data": self.serialize_data()
        }
    
    def serialize_data(self):
        return {}
    
    def deserialize(self, data):
        self.id = data.get("id", self.id)
        self.title = data.get("title", self.title)
        pos = data.get("pos", {"x": 0, "y": 0})
        self.setPos(pos["x"], pos["y"])
        self.deserialize_data(data.get("data", {}))
    
    def deserialize_data(self, data):
        pass
