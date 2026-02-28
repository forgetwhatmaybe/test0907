from PyQt5.QtWidgets import QGraphicsPathItem
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPen, QColor, QPainterPath


class Edge(QGraphicsPathItem):
    edge_type = "edge"
    
    def __init__(self, start_socket, end_socket, dragging=False):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self._dragging = dragging
        self._selected = False
        
        self.setZValue(-1)
        self.setPen(QPen(QColor("#88aaff"), 3))
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsPathItem.ItemIsSelectable)
        
        if start_socket:
            start_socket.add_edge(self)
        if end_socket:
            end_socket.add_edge(self)
        
        self.update_position()
    
    def update_position(self):
        path = QPainterPath()
        
        if self.start_socket:
            start_pos = self.start_socket.get_pos()
        else:
            start_pos = QPointF(0, 0)
        
        if self.end_socket:
            end_pos = self.end_socket.get_pos()
        elif self._dragging:
            end_pos = self.end_pos if hasattr(self, 'end_pos') else start_pos
        else:
            end_pos = start_pos
        
        path.moveTo(start_pos)
        
        dx = end_pos.x() - start_pos.x()
        control_offset = abs(dx) * 0.5
        control_offset = max(50, min(control_offset, 200))
        
        ctrl1 = QPointF(start_pos.x() + control_offset, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - control_offset, end_pos.y())
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        
        self.setPath(path)
    
    def set_end_pos(self, pos):
        self.end_pos = pos
        self.update_position()
    
    def remove(self):
        if self.start_socket:
            self.start_socket.remove_edge(self)
        if self.end_socket:
            self.end_socket.remove_edge(self)
        
        if self.scene():
            self.scene().remove_edge(self)
        
        self.start_socket = None
        self.end_socket = None
    
    def setSelected(self, selected):
        self._selected = selected
        if selected:
            self.setPen(QPen(QColor("#ff8800"), 4))
        else:
            self.setPen(QPen(QColor("#88aaff"), 3))
        super().setSelected(selected)
    
    def hoverEnterEvent(self, event):
        if not self._selected:
            self.setPen(QPen(QColor("#aaccff"), 3))
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        if not self._selected:
            self.setPen(QPen(QColor("#88aaff"), 3))
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setSelected(True)
            self.scene().clearSelection()
            self.setSelected(True)
        super().mousePressEvent(event)
    
    def serialize(self):
        return {
            "start_node": self.start_socket.node.id if self.start_socket else None,
            "start_socket": self.start_socket.index if self.start_socket else None,
            "end_node": self.end_socket.node.id if self.end_socket else None,
            "end_socket": self.end_socket.index if self.end_socket else None
        }
