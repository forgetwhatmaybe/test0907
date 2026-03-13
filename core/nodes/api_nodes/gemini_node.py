"""Gemini (香蕉生图) API 节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor

from core.node_editor.node_item import NodeItem
from ..widgets import ImageThumbnailStrip
from .. import styles


class GeminiAPINode(NodeItem):
    """香蕉生图节点 - Gemini 图片生成，支持多张参考图"""
    node_type = "gemini_api"
    
    def __init__(self):
        self.generated_image_path = ""
        self._image_order = []
        self._thumbnails_expanded = True
        
        super().__init__("香蕉生图")
        self.add_multi_input("参考图片")
        self.add_output("图片")
        
        if self.inputs:
            self.inputs[0].signals.connected.connect(self._on_edge_changed)
            self.inputs[0].signals.disconnected.connect(self._on_edge_changed)
        
        self._add_toggle_button()
        self._update_size()
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        # 模型选择
        model_label = QLabel("模型:")
        model_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
            "gemini-2.5-flash-preview-image-generation",
            "gemini-2.0-flash-preview-image-generation",
        ])
        self.model_combo.setStyleSheet(styles.COMBO_BOX)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)
        
        # 参考图片缩略图条
        self.thumb_label = QLabel("参考图片:")
        self.thumb_label.setStyleSheet(styles.LABEL_TITLE)
        self.thumb_label.hide()
        layout.addWidget(self.thumb_label)
        
        self.thumbnail_strip = ImageThumbnailStrip()
        self.thumbnail_strip.order_changed.connect(self._on_image_order_changed)
        layout.addWidget(self.thumbnail_strip)
        
        # 提示词
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述要生成的图片内容...")
        self.prompt_edit.setMinimumHeight(40)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)
        
        # 宽高比
        ar_layout = QHBoxLayout()
        ar_label = QLabel("宽高比:")
        ar_label.setStyleSheet(styles.LABEL_TITLE)
        ar_layout.addWidget(ar_label)
        
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems([
            "16:9", "1:1", "2:3", "3:2", "3:4", "4:3",
            "4:5", "5:4", "9:16", "21:9"
        ])
        self.aspect_ratio_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        ar_layout.addWidget(self.aspect_ratio_combo)
        layout.addLayout(ar_layout)
        
        # 分辨率
        self.resolution_layout = QHBoxLayout()
        self.resolution_label = QLabel("分辨率:")
        self.resolution_label.setStyleSheet(styles.LABEL_TITLE)
        self.resolution_layout.addWidget(self.resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1K", "2K", "4K"])
        self.resolution_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        self.resolution_layout.addWidget(self.resolution_combo)
        layout.addLayout(self.resolution_layout)
        
        self.resolution_combo.setCurrentIndex(1)
        model_lower = self.model_combo.currentText().lower()
        self._set_resolution_visible("pro" in model_lower or "3.1-flash" in model_lower)
    
    def _on_model_changed(self, model_name):
        is_pro = "pro" in model_name.lower() or "3.1-flash" in model_name.lower()
        self._set_resolution_visible(is_pro)
        self._update_size()
    
    def _set_resolution_visible(self, visible):
        self.resolution_label.setVisible(visible)
        self.resolution_combo.setVisible(visible)
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_thumbnails)
    
    def _refresh_thumbnails(self):
        from pathlib import Path
        connected_items = []
        for socket in self.inputs:
            for edge in socket.edges:
                if edge.start_socket:
                    src_node = edge.start_socket.node
                    img_path = ""
                    if src_node.node_type == "image":
                        img_path = getattr(src_node, 'image_path', '')
                    elif src_node.node_type == "gemini_api":
                        img_path = getattr(src_node, 'generated_image_path', '')
                    elif src_node.node_type == "output":
                        img_path = getattr(src_node, 'video_path', '')
                    elif src_node.node_type == "image_edit":
                        img_path = getattr(src_node, '_result_path', '')
                    if img_path and Path(img_path).exists():
                        connected_items.append((src_node.id, img_path))
        
        self.thumbnail_strip.update_thumbnails(connected_items)
        has_images = len(connected_items) > 0
        self.thumb_label.setVisible(has_images and self._thumbnails_expanded)
        self.thumbnail_strip.setVisible(self._thumbnails_expanded)
        self._update_size()
    
    def _on_toggle_clicked(self):
        """展开/收起缩略图区域"""
        self._thumbnails_expanded = not self._thumbnails_expanded
        has_images = self.thumbnail_strip and len(self.thumbnail_strip._ordered_items) > 0
        self.thumb_label.setVisible(has_images and self._thumbnails_expanded)
        self.thumbnail_strip.setVisible(self._thumbnails_expanded)
        self._update_size()
    
    def _on_image_order_changed(self):
        self._image_order = self.thumbnail_strip.get_ordered_node_ids()
        self._update_size()
    
    def get_ordered_image_paths(self):
        return self.thumbnail_strip.get_ordered_image_paths()
    
    def get_ordered_node_ids(self):
        return self._image_order if self._image_order else self.thumbnail_strip.get_ordered_node_ids()
    
    def _restore_image_order(self):
        if self._image_order:
            self._refresh_thumbnails()
            self.thumbnail_strip.set_order(self._image_order)
    
    def get_params(self):
        params = {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
        }
        model_lower = params["model"].lower()
        if "pro" in model_lower or "3.1-flash" in model_lower:
            params["image_size"] = self.resolution_combo.currentText()
        return params
    
    def set_generated_image(self, image_path):
        self.generated_image_path = image_path
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "generated_image_path": self.generated_image_path,
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))
        
        model_index = self.model_combo.findText(data.get("model", ""))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        
        ar_index = self.aspect_ratio_combo.findText(data.get("aspect_ratio", "1:1"))
        if ar_index >= 0:
            self.aspect_ratio_combo.setCurrentIndex(ar_index)
        
        _res_compat = {
            "1024 (1K)": "1K", "1024": "1K",
            "2048 (2K)": "2K", "2048": "2K",
            "4096 (4K)": "4K", "4096": "4K",
        }
        raw_res = data.get("resolution", "2K")
        res_val = _res_compat.get(raw_res, raw_res)
        res_index = self.resolution_combo.findText(res_val)
        if res_index >= 0:
            self.resolution_combo.setCurrentIndex(res_index)
        
        self.generated_image_path = data.get("generated_image_path", "")
        if self.generated_image_path:
            self.set_generated_image(self.generated_image_path)
        
        self._image_order = data.get("image_order", [])
