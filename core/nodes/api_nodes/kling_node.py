"""可灵 API 节点"""

from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSlider
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from core.node_editor.node_item import NodeItem
from core.node_editor.edge import Edge
from .. import styles


class KlingAPINode(NodeItem):
    """可灵生视频节点 - 支持图生视频和首尾帧模式"""
    node_type = "kling_api"
    
    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False
        
        super().__init__("可灵生视频")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()
    
    def _setup_sockets(self):
        """根据当前模式重建输入 socket"""
        first_input_edges = []
        if self.inputs:
            for edge in self.inputs[0].edges[:]:
                first_input_edges.append(edge.start_socket)
        
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()
        
        if self.generation_mode == "first_last_frame":
            self.add_input("首帧图片")
            self.add_input("尾帧图片")
        else:
            self.add_input("图片")
        
        if not self.outputs:
            self.add_output("视频")
        
        if first_input_edges and self.inputs:
            scene = self.scene()
            if scene:
                for start_socket in first_input_edges:
                    edge = Edge(start_socket, self.inputs[0])
                    scene.addItem(edge)
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        # 生成模式
        mode_label = QLabel("生成模式:")
        mode_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        mode_model = QStandardItemModel()
        for text in ["图生视频", "首尾帧"]:
            item = QStandardItem(text)
            item.setForeground(QColor("#ffffff"))
            mode_model.appendRow(item)
        self.mode_combo.setModel(mode_model)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.mode_combo)
        
        # 模型
        model_label = QLabel("模型:")
        model_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "kling-v3-omni", "kling-v3", "kling-video-o1", "kling-v2-6",
            "kling-v2-5-turbo", "kling-v2-master", "kling-v2-1-master",
            "kling-v2-1", "kling-v2", "kling-v1-6", "kling-v1-5", "kling-v1"
        ])
        self.model_combo.currentTextChanged.connect(self._on_kling_model_changed)
        self.model_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.model_combo)
        
        # 提示词
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setMinimumHeight(40)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)
        
        # 选项
        options_layout = QHBoxLayout()
        
        duration_label = QLabel("时长:")
        duration_label.setStyleSheet(styles.LABEL_TITLE)
        options_layout.addWidget(duration_label)
        
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["5s", "10s"])
        self.duration_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        options_layout.addWidget(self.duration_combo)
        
        resolution_label = QLabel("分辨率:")
        resolution_label.setStyleSheet(styles.LABEL_TITLE)
        options_layout.addWidget(resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["720p", "1080p"])
        self.resolution_combo.currentTextChanged.connect(self._on_kling_resolution_changed)
        self.resolution_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        options_layout.addWidget(self.resolution_combo)
        
        layout.addLayout(options_layout)
        
        # CFG Scale
        cfg_layout = QHBoxLayout()
        cfg_label = QLabel("CFG Scale:")
        cfg_label.setStyleSheet(styles.LABEL_TITLE)
        cfg_layout.addWidget(cfg_label)
        
        self.cfg_slider = QSlider(Qt.Horizontal)
        self.cfg_slider.setRange(0, 100)
        self.cfg_slider.setValue(50)
        self.cfg_slider.setStyleSheet(styles.SLIDER_GREEN)
        self.cfg_slider.valueChanged.connect(self._on_cfg_changed)
        cfg_layout.addWidget(self.cfg_slider)
        
        self.cfg_value_label = QLabel("0.5")
        self.cfg_value_label.setStyleSheet(styles.LABEL_VALUE)
        cfg_layout.addWidget(self.cfg_value_label)
        
        layout.addLayout(cfg_layout)
        self._update_kling_duration_option()
    
    def _on_mode_changed(self, text):
        new_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if new_mode != self.generation_mode:
            self.generation_mode = new_mode
            if self._mode_initialized:
                self._setup_sockets()
                self.update_sockets_position()
                self.update()
    
    def _on_kling_model_changed(self, model):
        """模型变化时更新首尾帧选项和时长选项"""
        self._update_kling_first_last_frame_option()
        self._update_kling_duration_option()
    
    def _on_kling_resolution_changed(self, resolution):
        """分辨率变化时更新首尾帧选项"""
        self._update_kling_first_last_frame_option()
    
    def _update_kling_duration_option(self):
        """根据模型更新时长选项"""
        model = self.model_combo.currentText()
        
        if model in ["kling-v3", "kling-v3-omni"]:
            new_durations = [f"{i}s" for i in range(3, 16)]
        else:
            new_durations = ["5s", "10s"]
        
        current = self.duration_combo.currentText()
        self.duration_combo.clear()
        self.duration_combo.addItems(new_durations)
        idx = self.duration_combo.findText(current)
        if idx >= 0:
            self.duration_combo.setCurrentIndex(idx)
    
    def _update_kling_first_last_frame_option(self):
        """根据模型和分辨率控制首尾帧选项的显示"""
        model = self.model_combo.currentText()
        resolution = self.resolution_combo.currentText()
        is_pro_mode = (resolution == "1080p")
        
        models_pro_only = ["kling-v1", "kling-v1-5", "kling-v1-6",
                          "kling-v2-1", "kling-v2-5-turbo", "kling-v2-6"]
        models_always = ["kling-video-o1", "kling-v3", "kling-v3-omni"]
        
        combo_model = self.mode_combo.model()
        
        if model in models_always:
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
        elif model in models_pro_only and is_pro_mode:
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
        else:
            if self.mode_combo.currentText() == "首尾帧":
                self.mode_combo.setCurrentIndex(0)
            combo_model.item(1).setEnabled(False)
            self.mode_combo.view().setRowHidden(1, True)
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_cfg_changed(self, value):
        cfg_value = value / 100.0
        self.cfg_value_label.setText(f"{cfg_value:.2f}")
    
    def get_params(self):
        cfg_value = self.cfg_slider.value() / 100.0
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText().replace("s", ""),
            "resolution": self.resolution_combo.currentText(),
            "cfg_scale": cfg_value,
            "mode": "pro" if self.resolution_combo.currentText() == "1080p" else "std"
        }
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "generation_mode": self.generation_mode,
            "cfg_scale": self.cfg_slider.value()
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        model_index = self.model_combo.findText(data.get("model", "kling-v1"))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

        duration_index = self.duration_combo.findText(data.get("duration", "5s"))
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)

        resolution_index = self.resolution_combo.findText(data.get("resolution", "720p"))
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)

        mode = data.get("generation_mode", "image_to_video")
        self.generation_mode = mode
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText("首尾帧" if mode == "first_last_frame" else "图生视频")
        self.mode_combo.blockSignals(False)
        self._setup_sockets()

        cfg_value = data.get("cfg_scale", 50)
        self.cfg_slider.setValue(cfg_value)
        self.cfg_value_label.setText(f"{cfg_value / 100.0:.2f}")
