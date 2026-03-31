from PyQt5.QtWidgets import QGraphicsScene, QGraphicsItem
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer, QDateTime
from PyQt5.QtGui import QColor
import json
import weakref
import time


class NodeScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        # 画布默认范围调大，减少一开始就碰到边界的情况
        self._base_size = 6000
        self._margin = 1200  # 边界外扩余量
        self._expand_threshold = 0.55  # 更早扩展，避免拖动时总感觉顶到边界
        self.setSceneRect(-self._base_size // 2, -self._base_size // 2,
                          self._base_size, self._base_size)
        self.nodes = {}
        self.edges = []
        self._grid_size = 20
        
        # 优化：缓存边界矩形计算结果
        self._cached_items_rect = None
        self._items_rect_dirty = True
        self._last_expand_time = 0
        self._expand_cooldown = 100  # 扩展冷却时间（毫秒）
    
    def _get_cached_items_rect(self):
        """获取缓存的边界矩形，如果脏则重新计算"""
        if self._items_rect_dirty or self._cached_items_rect is None:
            self._cached_items_rect = self.itemsBoundingRect()
            self._items_rect_dirty = False
        return self._cached_items_rect
    
    def _mark_items_rect_dirty(self):
        """标记边界矩形缓存为脏"""
        self._items_rect_dirty = True
    
    def _auto_expand_scene(self, target_rect=None):
        """根据节点位置自动扩展场景范围。

        拖动过程中优先使用当前移动节点的范围，避免频繁计算整场景边界。
        """
        if not self.nodes:
            return
        
        # 检查冷却时间，避免频繁扩展
        current_time = int(time.time() * 1000)  # 转换为毫秒
        if current_time - self._last_expand_time < self._expand_cooldown:
            return
        
        current = self.sceneRect()
        items_rect = target_rect if target_rect is not None else self._get_cached_items_rect()

        if items_rect.isNull() or items_rect.isEmpty():
            return
        
        # 如果所有节点都在当前场景范围内（留有余量），不需要扩展
        padded = current.adjusted(self._margin, self._margin,
                                  -self._margin, -self._margin)
        if padded.contains(items_rect):
            return
        
        # 扩展场景，确保所有节点都在范围内，并留足余量
        # 使用增量扩展策略：每次扩展50%，而不是一次性扩展到足够大
        expansion_factor = 1.8
        new_width = current.width() * expansion_factor
        new_height = current.height() * expansion_factor
        
        # 计算新的中心点（保持当前视图中心）
        center = current.center()
        new_rect = QRectF(
            center.x() - new_width / 2,
            center.y() - new_height / 2,
            new_width,
            new_height
        )
        
        # 确保目标节点（或全部节点）都在新范围内
        new_rect = new_rect.united(items_rect.adjusted(
            -self._margin, -self._margin,
            self._margin, self._margin
        ))
        
        self.setSceneRect(new_rect)
        self._last_expand_time = current_time
    
    def add_node(self, node):
        self.nodes[node.id] = node
        self.addItem(node)
        self._mark_items_rect_dirty()  # 标记缓存为脏
        self._auto_expand_scene()
    
    def remove_node(self, node):
        if node.id in self.nodes:
            del self.nodes[node.id]
        
        for socket in node.inputs + node.outputs:
            for edge in socket.edges[:]:
                edge.remove()
        
        self.removeItem(node)
        self._mark_items_rect_dirty()  # 标记缓存为脏
    
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
        
        # 优化：合并为单次延迟刷新，减少定时器开销
        # 解决 Qt proxy widget 布局延迟导致连线共维偏差问题
        QTimer.singleShot(0, self._refresh_all_edges)
    
    def _refresh_all_edges(self):
        """刷新所有连线的显示位置（优化版：合并两次刷新为一次）"""
        # 第一次刷新
        for edge in self.edges:
            edge.update_position()
        
        # 使用 singleShot 延迟一帧执行第二次刷新
        # 解决部分节点如 OutputNode 需要两次布局才稳定的问题
        QTimer.singleShot(50, self._refresh_all_edges_final)
    
    def _refresh_all_edges_final(self):
        """最终一次刷新，确保连线位置完全正确"""
        for edge in self.edges:
            edge.update_position()
