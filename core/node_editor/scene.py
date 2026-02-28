from PyQt5.QtWidgets import QGraphicsScene, QGraphicsItem
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor
import json


class NodeScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_size = 10000
        self._margin = 2000  # 边界外扩余量
        self.setSceneRect(-self._base_size // 2, -self._base_size // 2,
                          self._base_size, self._base_size)
        self.nodes = {}
        self.edges = []
        self._grid_size = 20
    
    def _auto_expand_scene(self):
        """根据所有节点的位置自动扩展场景范围"""
        if not self.nodes:
            return
        
        current = self.sceneRect()
        items_rect = self.itemsBoundingRect()
        
        # 如果所有节点都在当前场景范围内（留有余量），不需要扩展
        padded = current.adjusted(self._margin, self._margin,
                                  -self._margin, -self._margin)
        if padded.contains(items_rect):
            return
        
        # 扩展场景，确保所有节点都在范围内，并留足余量
        new_rect = current.united(items_rect.adjusted(
            -self._margin, -self._margin,
            self._margin, self._margin
        ))
        self.setSceneRect(new_rect)
    
    def add_node(self, node):
        self.nodes[node.id] = node
        self.addItem(node)
        self._auto_expand_scene()
    
    def remove_node(self, node):
        if node.id in self.nodes:
            del self.nodes[node.id]
        
        for socket in node.inputs + node.outputs:
            for edge in socket.edges[:]:
                edge.remove()
        
        self.removeItem(node)
    
    def add_edge(self, edge):
        self.edges.append(edge)
        self.addItem(edge)
    
    def remove_edge(self, edge):
        if edge in self.edges:
            self.edges.remove(edge)
        self.removeItem(edge)
    
    def get_node_by_id(self, node_id):
        return self.nodes.get(node_id)
    
    def clear_all(self):
        for node in list(self.nodes.values()):
            self.remove_node(node)
        self.edges.clear()
    
    def save_to_dict(self):
        data = {
            "nodes": [],
            "edges": []
        }
        
        for node in self.nodes.values():
            node_data = node.serialize()
            data["nodes"].append(node_data)
        
        for edge in self.edges:
            edge_data = edge.serialize()
            data["edges"].append(edge_data)
        
        return data
    
    def load_from_dict(self, data, node_registry):
        self.clear_all()
        
        node_id_map = {}
        
        for node_data in data.get("nodes", []):
            node_type = node_data.get("type")
            node_class = node_registry.get(node_type)
            if node_class:
                node = node_class()
                node.deserialize(node_data)
                node_id_map[node_data["id"]] = node
                self.add_node(node)
        
        for edge_data in data.get("edges", []):
            start_node_id = edge_data.get("start_node")
            end_node_id = edge_data.get("end_node")
            start_socket_index = edge_data.get("start_socket", 0)
            end_socket_index = edge_data.get("end_socket", 0)
            
            start_node = node_id_map.get(start_node_id)
            end_node = node_id_map.get(end_node_id)
            
            if start_node and end_node:
                # 检查 socket 索引是否越界
                if start_socket_index >= len(start_node.outputs):
                    print(f"Warning: start_socket_index {start_socket_index} out of range for node {start_node.title}")
                    continue
                if end_socket_index >= len(end_node.inputs):
                    print(f"Warning: end_socket_index {end_socket_index} out of range for node {end_node.title}")
                    continue
                
                from .edge import Edge
                start_socket = start_node.outputs[start_socket_index]
                end_socket = end_node.inputs[end_socket_index]
                edge = Edge(start_socket, end_socket)
                self.add_edge(edge)
        
        # 所有边恢复后，通知节点恢复保存的顺序
        for node in self.nodes.values():
            if hasattr(node, '_restore_image_order'):
                node._restore_image_order()
        
        # 延迟一帧全量刷新所有连线位置
        # 解决 Qt proxy widget 布局延迟导致连线共维偏差问题
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_all_edges)
    
    def _refresh_all_edges(self):
        """\u5237\u65b0\u6240\u6709\u8fde\u7ebf\u7684\u663e\u793a\u4f4d\u7f6e\uff08\u5ef6\u8fdf\u6267\u884c\u4ee5\u7b49\u5f85 Qt \u5e03\u5c40\u5b8c\u6210\uff09"""
        for edge in self.edges:
            edge.update_position()
        # \u518d\u6b21\u5ef6\u8fdf\u4e00\u5e27\uff08\u90e8\u5206\u8282\u70b9\u5982 OutputNode \u9700\u8981\u4e24\u6b21\u5e03\u5c40\u624d\u7a33\u5b9a\uff09
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, self._refresh_all_edges_final)
    
    def _refresh_all_edges_final(self):
        """\u6700\u7ec8\u4e00\u6b21\u5237\u65b0\uff0c\u786e\u4fdd\u8fde\u7ebf\u4f4d\u7f6e\u5b8c\u5168\u6b63\u786e"""
        for edge in self.edges:
            edge.update_position()
