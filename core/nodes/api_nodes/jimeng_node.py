"""即梦 API 节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSpinBox
from PyQt5.QtGui import QStandardItem, QStandardItemModel, QColor

from core.node_editor.node_item import NodeItem
from core.node_editor.edge import Edge
from .. import styles


class JimengAPINode(NodeItem):
    """即梦生视频节点"""
    node_type = "jimeng_api"
    
    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False
        
        super().__init__("即梦生视频")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()
    
    def _setup_sockets(self):
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
        
        model_label = QLabel("模型:")
        model_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems(["jimeng_v1", "jimeng_v2", "jimeng_v30", "jimeng_v30_pro"])
        self.model_combo.currentTextChanged.connect(self._on_jimeng_model_changed)
        self.model_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.model_combo)
        
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setMinimumHeight(40)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)
        
        self.resolution_label = QLabel("分辨率:")
        self.resolution_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(self.resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["720P", "1080P"])
        self.resolution_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.resolution_combo)
        
        duration_label = QLabel("时长:")
        duration_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(duration_label)
        
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["5s", "10s"])
        self.duration_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        layout.addWidget(self.duration_combo)
        
        seed_layout = QHBoxLayout()
        seed_label = QLabel("Seed:")
        seed_label.setStyleSheet(styles.LABEL_TITLE)
        seed_layout.addWidget(seed_label)
        
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2147483647)
        self.seed_spin.setValue(-1)
        self.seed_spin.setStyleSheet(styles.SPIN_BOX)
        seed_layout.addWidget(self.seed_spin)
        
        seed_hint = QLabel("(-1随机)")
        seed_hint.setStyleSheet("color: #666; font-size: 10px;")
        seed_layout.addWidget(seed_hint)
        seed_layout.addStretch()
        layout.addLayout(seed_layout)
        
        self._on_jimeng_model_changed(self.model_combo.currentText())
    
    def _on_mode_changed(self, text):
        new_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if new_mode != self.generation_mode:
            self.generation_mode = new_mode
            if self._mode_initialized:
                self._setup_sockets()
                self.update_sockets_position()
                self.update()
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_jimeng_model_changed(self, model):
        combo_model = self.mode_combo.model()
        
        if model == "jimeng_v30_pro":
            if self.mode_combo.currentText() == "首尾帧":
                self.mode_combo.setCurrentIndex(0)
            combo_model.item(1).setEnabled(False)
            self.mode_combo.view().setRowHidden(1, True)
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.hide()
            self.resolution_label.hide()
        elif model == "jimeng_v30":
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
            self.resolution_combo.setEnabled(True)
            self.resolution_combo.show()
            self.resolution_label.show()
        else:
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.hide()
            self.resolution_label.hide()
    
    def get_params(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "video_duration": int(self.duration_combo.currentText().replace("s", "")),
            "fps": 24,
            "seed": self.seed_spin.value(),
            "resolution": self.resolution_combo.currentText()
        }
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText(),
            "fps": "24fps",
            "seed": self.seed_spin.value(),
            "generation_mode": self.generation_mode,
            "resolution": self.resolution_combo.currentText()
        }

    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        model_index = self.model_combo.findText(data.get("model", "jimeng_v1"))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

        duration_index = self.duration_combo.findText(data.get("duration", "5s"))
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)

        self.seed_spin.setValue(data.get("seed", -1))

        mode = data.get("generation_mode", "image_to_video")
        self.generation_mode = mode
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText("首尾帧" if mode == "first_last_frame" else "图生视频")
        self.mode_combo.blockSignals(False)
        self._setup_sockets()

        resolution = data.get("resolution", "720P")
        resolution_index = self.resolution_combo.findText(resolution)
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)
