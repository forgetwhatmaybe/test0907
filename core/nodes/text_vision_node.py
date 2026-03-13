from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSlider
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from pathlib import Path

from core.node_editor.node_item import NodeItem
from core.nodes.widgets import ImageThumbnailStrip
from core.nodes import styles


class TextVisionNode(NodeItem):
    """文本视觉节点 - 支持多图片输入和文本输出
    
    使用GPT-5.4或Gemini-3 Flash进行图片理解和文本生成。
    支持最多14张参考图片输入。
    """
    node_type = "text_vision"
    
    def __init__(self):
        self.generated_text = ""
        self._image_order = []
        self._estimated_tokens = 0
        self._thumbnails_expanded = True
        self._temperature = 0.8
        
        super().__init__("文本识图")
        self.add_multi_input("参考图片")
        self.add_output("文本")
        
        if self.inputs:
            self.inputs[0].signals.connected.connect(self._on_edge_changed)
            self.inputs[0].signals.disconnected.connect(self._on_edge_changed)
        
        self._add_toggle_button()
        self._update_size()
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        _combo_style = """
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """
        
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gpt-5.4",
            "gemini-3.1-flash-lite-preview",
        ])
        self.model_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.model_combo)
        
        self.thumb_label = QLabel("参考图片:")
        self.thumb_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.thumb_label.hide()
        layout.addWidget(self.thumb_label)
        
        self.thumbnail_strip = ImageThumbnailStrip()
        self.thumbnail_strip.order_changed.connect(self._on_image_order_changed)
        layout.addWidget(self.thumbnail_strip)
        
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述图片内容或提出问题...")
        self.prompt_edit.setMinimumHeight(60)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-height: 60px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        temp_layout = QHBoxLayout()
        temp_label = QLabel("温度:")
        temp_label.setStyleSheet("color: #aaa; font-size: 11px;")
        temp_layout.addWidget(temp_label)
        
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(0, 200)
        self.temp_slider.setValue(int(self._temperature * 100))
        self.temp_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50; width: 14px; height: 14px;
                border-radius: 7px; margin: -4px 0;
            }
        """)
        self.temp_slider.valueChanged.connect(self._on_temp_changed)
        temp_layout.addWidget(self.temp_slider)
        
        self.temp_value_label = QLabel(f"{self._temperature:.1f}")
        self.temp_value_label.setStyleSheet("color: #aaa; font-size: 11px; min-width: 30px;")
        temp_layout.addWidget(self.temp_value_label)
        layout.addLayout(temp_layout)
        
        token_layout = QHBoxLayout()
        self.token_label = QLabel("预估Token: 0")
        self.token_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        token_layout.addWidget(self.token_label)
        token_layout.addStretch()
        layout.addLayout(token_layout)
    
    def _on_temp_changed(self, value):
        self._temperature = value / 100.0
        self.temp_value_label.setText(f"{self._temperature:.1f}")
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(60, new_height))
        self._update_token_estimate()
        self._update_size()
    
    def _on_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_thumbnails)
    
    def _refresh_thumbnails(self):
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
        self._update_token_estimate()
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
        self._update_token_estimate()
        self._update_size()
    
    def _update_token_estimate(self):
        """更新token估算"""
        from api.text_vision_api import TextVisionAPI
        
        prompt = self.prompt_edit.toPlainText()
        image_paths = self.thumbnail_strip.get_ordered_image_paths()
        
        self._estimated_tokens = TextVisionAPI.estimate_tokens(prompt, image_paths)
        self.token_label.setText(f"预估Token: {self._estimated_tokens}")
    
    def get_ordered_image_paths(self):
        return self.thumbnail_strip.get_ordered_image_paths()
    
    def get_ordered_node_ids(self):
        return self._image_order if self._image_order else self.thumbnail_strip.get_ordered_node_ids()
    
    def get_estimated_tokens(self):
        return self._estimated_tokens
    
    def get_params(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
            "temperature": self._temperature,
        }
    
    def set_generated_text(self, text):
        self.generated_text = text
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
            "generated_text": self.generated_text,
            "temperature": self._temperature,
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))
        
        model_index = self.model_combo.findText(data.get("model", "gpt-5.4"))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        
        self._temperature = data.get("temperature", 0.8)
        if hasattr(self, 'temp_slider'):
            self.temp_slider.setValue(int(self._temperature * 100))
            self.temp_value_label.setText(f"{self._temperature:.1f}")
        
        self.generated_text = data.get("generated_text", "")
        self._image_order = data.get("image_order", [])
