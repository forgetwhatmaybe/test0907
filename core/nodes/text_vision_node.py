from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSlider, QWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from core.node_editor.node_item import NodeItem
from core.nodes.widgets import ImageThumbnailStrip, collect_reference_items_from_inputs
from core.nodes import styles


class TextVisionNode(NodeItem):
    """文本视觉节点 - 支持多图片输入和文本输出
    
    使用GPT-5.4或Gemini-3.1 Pro进行图片理解和文本生成。
    支持最多14张参考图片输入。
    """
    node_type = "text_vision"
    FORMAT_OPTIONS = ["无", "图片反推json", "json格式"]
    GPT_THINKING_OPTIONS = ["none", "low", "medium", "high", "xhigh"]
    GEMINI_THINKING_OPTIONS = ["low", "medium", "high"]
    
    def __init__(self):
        self.generated_text = ""
        self._image_order = []
        self._estimated_tokens = 0
        self._thumbnails_expanded = True
        self._temperature = 0.8
        self._format_mode = "无"
        self._thinking_mode = "none"
        
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
            "gemini-3.1-pro-preview",
        ])
        self.model_combo.setStyleSheet(_combo_style)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)

        thinking_label = QLabel("思考模式:")
        thinking_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(thinking_label)

        self.thinking_combo = QComboBox()
        self.thinking_combo.setStyleSheet(_combo_style)
        self.thinking_combo.currentIndexChanged.connect(self._on_thinking_mode_changed)
        layout.addWidget(self.thinking_combo)

        format_label = QLabel("格式:")
        format_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(format_label)

        self.format_combo = QComboBox()
        self.format_combo.addItems(self.FORMAT_OPTIONS)
        self.format_combo.setCurrentText(self._format_mode)
        self.format_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.format_combo)
        
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
        self.prompt_edit.setFixedHeight(80)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        self.temp_widget = QWidget()
        temp_layout = QHBoxLayout(self.temp_widget)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.setSpacing(6)

        self.temp_label = QLabel("温度:")
        self.temp_label.setStyleSheet("color: #aaa; font-size: 11px;")
        temp_layout.addWidget(self.temp_label)
        
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
        layout.addWidget(self.temp_widget)
        
        token_layout = QHBoxLayout()
        self.token_label = QLabel("预估Token: 0")
        self.token_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        token_layout.addWidget(self.token_label)
        token_layout.addStretch()
        layout.addLayout(token_layout)

        self._update_thinking_options(self.model_combo.currentText(), preserve_current=False)
        self._update_temperature_state()
    
    def _on_temp_changed(self, value):
        self._temperature = value / 100.0
        self.temp_value_label.setText(f"{self._temperature:.1f}")

    def _is_gpt_model(self):
        return self.model_combo.currentText().startswith("gpt")

    def _update_thinking_options(self, model, preserve_current=True):
        options = self.GPT_THINKING_OPTIONS if model.startswith("gpt") else self.GEMINI_THINKING_OPTIONS
        current_mode = self._thinking_mode if preserve_current else None

        self.thinking_combo.blockSignals(True)
        self.thinking_combo.clear()
        self.thinking_combo.addItems(options)

        if current_mode in options:
            target_mode = current_mode
        else:
            target_mode = "none" if model.startswith("gpt") else "low"

        self._thinking_mode = target_mode
        self.thinking_combo.setCurrentText(target_mode)
        self.thinking_combo.blockSignals(False)

    def _update_temperature_state(self):
        temp_visible = (not self._is_gpt_model()) or self._thinking_mode == "none"
        self.temp_widget.setVisible(temp_visible)
        self.temp_slider.setEnabled(temp_visible)
        self.temp_label.setEnabled(temp_visible)
        self.temp_value_label.setEnabled(temp_visible)
        self._update_size()

    def _on_model_changed(self):
        self._update_thinking_options(self.model_combo.currentText())
        self._update_temperature_state()

    def _on_thinking_mode_changed(self):
        self._thinking_mode = self.thinking_combo.currentText()
        self._update_temperature_state()
    
    def _on_prompt_changed(self):
        self._update_token_estimate()
    
    def _on_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_thumbnails)
    
    def _refresh_thumbnails(self):
        connected_items = collect_reference_items_from_inputs(self.inputs)
        
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
        image_paths = self.get_ordered_image_paths()
        
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
            "format_mode": self.format_combo.currentText(),
            "thinking_mode": self.thinking_combo.currentText(),
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
            "temperature": self._temperature,
        }
    
    def set_generated_text(self, text):
        self.generated_text = text
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "format_mode": self.format_combo.currentText(),
            "thinking_mode": self.thinking_combo.currentText(),
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
            "generated_text": self.generated_text,
            "temperature": self._temperature,
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))
        
        model_text = data.get("model", "gpt-5.4")
        if model_text == "gemini-3.1-flash-lite-preview":
            model_text = "gemini-3.1-pro-preview"
        model_index = self.model_combo.findText(model_text)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        self._update_thinking_options(self.model_combo.currentText(), preserve_current=False)

        thinking_mode = data.get("thinking_mode")
        if thinking_mode == "minimal":
            thinking_mode = "low"
        if thinking_mode in self.GPT_THINKING_OPTIONS + self.GEMINI_THINKING_OPTIONS:
            self._thinking_mode = thinking_mode
            self._update_thinking_options(self.model_combo.currentText())

        format_mode = data.get("format_mode", "无")
        format_index = self.format_combo.findText(format_mode)
        if format_index >= 0:
            self.format_combo.setCurrentIndex(format_index)
        self._format_mode = self.format_combo.currentText()
        
        self._temperature = data.get("temperature", 0.8)
        if hasattr(self, 'temp_slider'):
            self.temp_slider.setValue(int(self._temperature * 100))
            self.temp_value_label.setText(f"{self._temperature:.1f}")
            self._update_temperature_state()
        
        self.generated_text = data.get("generated_text", "")
        self._image_order = data.get("image_order", [])
