"""Veo API 节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QTextEdit, QComboBox

from core.node_editor.node_item import NodeItem
from core.node_editor.edge import Edge
from .. import styles


class VeoAPINode(NodeItem):
    """Veo3 生视频节点"""
    node_type = "veo_api"

    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False

        super().__init__("Veo生视频")
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
        self.mode_combo.addItems(["图生视频", "首尾帧"])
        self.mode_combo.setStyleSheet(styles.COMBO_BOX)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        model_label = QLabel("模型:")
        model_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "veo_3_1", "veo3.1", "veo3.1-fast", "veo3.1-pro", "veo3.1-4k", "veo3.1-pro-4k",
            "veo3", "veo3-pro", "veo3-fast", "veo3-fast-frames", "veo3-frames", "veo3-pro-frames",
            "veo2-pro", "veo2-fast", "veo2-fast-frames", "veo2-fast-components", "veo2-pro-components",
        ])
        self.model_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.model_combo)

        ar_label = QLabel("宽高比 (Veo3):")
        ar_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(ar_label)

        self.ar_combo = QComboBox()
        self.ar_combo.addItems(["16:9", "9:16"])
        self.ar_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.ar_combo)

        enhance_label = QLabel("中文转英文:")
        enhance_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(enhance_label)

        self.enhance_combo = QComboBox()
        self.enhance_combo.addItems(["是", "否"])
        self.enhance_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.enhance_combo)

        upsample_label = QLabel("视频超分:")
        upsample_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(upsample_label)

        self.upsample_combo = QComboBox()
        self.upsample_combo.addItems(["是", "否"])
        self.upsample_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.upsample_combo)

        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("支持中文，自动转英文...")
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)

    def _on_mode_changed(self, text):
        if not self._mode_initialized:
            return
        old = self.generation_mode
        self.generation_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if old != self.generation_mode:
            self._setup_sockets()
            self._update_size()

    def get_params(self):
        return {
            "mode": self.generation_mode,
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.ar_combo.currentText(),
            "enhance_prompt": self.enhance_combo.currentText() == "是",
            "enable_upsample": self.upsample_combo.currentText() == "是",
            "prompt": self.prompt_edit.toPlainText().strip(),
        }

    def serialize_data(self):
        return {
            "generation_mode": self.generation_mode,
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.ar_combo.currentText(),
            "enhance_prompt": self.enhance_combo.currentText(),
            "enable_upsample": self.upsample_combo.currentText(),
            "prompt": self.prompt_edit.toPlainText(),
        }

    def deserialize_data(self, data):
        self.generation_mode = data.get("generation_mode", "image_to_video")

        def _set(combo, key, default):
            idx = combo.findText(data.get(key, default))
            if idx >= 0:
                combo.setCurrentIndex(idx)

        _set(self.model_combo, "model", "veo_3_1")
        _set(self.ar_combo, "aspect_ratio", "16:9")
        _set(self.enhance_combo, "enhance_prompt", "是")
        _set(self.upsample_combo, "enable_upsample", "是")
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        self._setup_sockets()

        mode_text = "首尾帧" if self.generation_mode == "first_last_frame" else "图生视频"
        self._mode_initialized = False
        idx = self.mode_combo.findText(mode_text)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self._mode_initialized = True
