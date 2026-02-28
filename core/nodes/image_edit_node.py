"""图片编辑节点 - 支持可灵扩图、即梦超清、即梦局部重绘"""

from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSlider, QSpinBox, QWidget
)
from PyQt5.QtCore import Qt

from core.node_editor.node_item import NodeItem
from core.node_editor.edge import Edge
from . import styles


class ImageEditNode(NodeItem):
    """图片修改节点：可灵扩图 / 即梦超清 / 即梦局部重绘"""
    node_type = "image_edit"

    MODES = ["可灵扩图", "即梦超清", "即梦局部重绘"]

    def __init__(self):
        self.edit_mode = "可灵扩图"
        self._mode_initialized = False
        self._result_path = ""  # 执行结果图片路径
        super().__init__("图片修改")
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

        if self.edit_mode == "即梦局部重绘":
            self.add_input("原图")
            self.add_input("遮罩")
        else:
            self.add_input("图片")

        if not self.outputs:
            self.add_output("图片")
        
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

        # 模式选择
        mode_label = QLabel("编辑模式:")
        mode_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.mode_combo.setStyleSheet(styles.COMBO_BOX)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        # 可灵扩图参数
        self.expand_widget = QWidget()
        expand_layout = QVBoxLayout(self.expand_widget)
        expand_layout.setContentsMargins(0, 0, 0, 0)
        expand_layout.setSpacing(2)

        dir_label = QLabel("扩展比例 (0~2.0):")
        dir_label.setStyleSheet("color: #aaa; font-size: 10px;")
        expand_layout.addWidget(dir_label)

        self._expand_sliders = {}
        for direction, zh in [("up", "上"), ("down", "下"), ("left", "左"), ("right", "右")]:
            row = QHBoxLayout()
            lbl = QLabel(f"{zh}:")
            lbl.setFixedWidth(20)
            lbl.setStyleSheet("color: #ccc; font-size: 11px;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(0)
            slider.setStyleSheet(styles.SLIDER_GREEN)
            val_lbl = QLabel("0.0")
            val_lbl.setFixedWidth(30)
            val_lbl.setStyleSheet(styles.LABEL_VALUE)
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(f"{v / 100:.1f}"))
            slider.valueChanged.connect(self._update_expand_warning)
            self._expand_sliders[direction] = slider
            row.addWidget(lbl)
            row.addWidget(slider)
            row.addWidget(val_lbl)
            expand_layout.addLayout(row)

        self._expand_warn_label = QLabel()
        self._expand_warn_label.setWordWrap(True)
        self._expand_warn_label.setStyleSheet(styles.WARNING_TEXT)
        self._expand_warn_label.hide()
        expand_layout.addWidget(self._expand_warn_label)

        layout.addWidget(self.expand_widget)

        # 即梦超清参数
        self.sr_widget = QWidget()
        sr_layout = QVBoxLayout(self.sr_widget)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        sr_layout.setSpacing(2)

        res_label = QLabel("目标分辨率:")
        res_label.setStyleSheet(styles.LABEL_TITLE)
        sr_layout.addWidget(res_label)
        self.sr_resolution_combo = QComboBox()
        self.sr_resolution_combo.addItems(["4k", "8k"])
        self.sr_resolution_combo.setStyleSheet(styles.COMBO_BOX)
        sr_layout.addWidget(self.sr_resolution_combo)

        scale_label = QLabel("锐化强度 (0-100):")
        scale_label.setStyleSheet(styles.LABEL_TITLE)
        sr_layout.addWidget(scale_label)
        scale_row = QHBoxLayout()
        self.sr_scale_slider = QSlider(Qt.Horizontal)
        self.sr_scale_slider.setRange(0, 100)
        self.sr_scale_slider.setValue(50)
        self.sr_scale_slider.setStyleSheet(styles.SLIDER_BLUE)
        self.sr_scale_val = QLabel("50")
        self.sr_scale_val.setFixedWidth(30)
        self.sr_scale_val.setStyleSheet(styles.LABEL_VALUE_BLUE)
        self.sr_scale_slider.valueChanged.connect(lambda v: self.sr_scale_val.setText(str(v)))
        scale_row.addWidget(self.sr_scale_slider)
        scale_row.addWidget(self.sr_scale_val)
        sr_layout.addLayout(scale_row)
        layout.addWidget(self.sr_widget)

        # 即梦局部重绘参数
        self.inpaint_widget = QWidget()
        inpaint_layout = QVBoxLayout(self.inpaint_widget)
        inpaint_layout.setContentsMargins(0, 0, 0, 0)
        inpaint_layout.setSpacing(2)

        seed_label = QLabel("种子 (Seed):")
        seed_label.setStyleSheet(styles.LABEL_TITLE)
        inpaint_layout.addWidget(seed_label)
        self.inpaint_seed_spin = QSpinBox()
        self.inpaint_seed_spin.setRange(-1, 999999)
        self.inpaint_seed_spin.setValue(101)
        self.inpaint_seed_spin.setStyleSheet(styles.SPIN_BOX)
        inpaint_layout.addWidget(self.inpaint_seed_spin)
        layout.addWidget(self.inpaint_widget)

        # 提示词
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("可选提示词 (扩图/重绘)")
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)

        self._toggle_panels()

    def _on_mode_changed(self, mode_text):
        self.edit_mode = mode_text
        self._toggle_panels()
        if self._mode_initialized:
            self._setup_sockets()
        self._update_size()

    def _toggle_panels(self):
        """根据模式显示/隐藏对应的参数面板"""
        self.expand_widget.setVisible(self.edit_mode == "可灵扩图")
        self.sr_widget.setVisible(self.edit_mode == "即梦超清")
        self.inpaint_widget.setVisible(self.edit_mode == "即梦局部重绘")
        self.prompt_edit.setVisible(self.edit_mode != "即梦超清")

    def _update_expand_warning(self):
        """实时计算扩图面积倍数"""
        up = self._expand_sliders["up"].value() / 100.0
        down = self._expand_sliders["down"].value() / 100.0
        left = self._expand_sliders["left"].value() / 100.0
        right = self._expand_sliders["right"].value() / 100.0
        area_mult = (1 + up + down) * (1 + left + right)
        if area_mult > 3.0:
            self._expand_warn_label.setText(f"⚠ 面积 {area_mult:.1f}x > 3x，执行时将自动裁剪")
            self._expand_warn_label.show()
        else:
            self._expand_warn_label.hide()
        self._update_size()

    def get_params(self):
        params = {"mode": self.edit_mode}
        if self.edit_mode == "可灵扩图":
            params["up_expansion_ratio"] = self._expand_sliders["up"].value() / 100.0
            params["down_expansion_ratio"] = self._expand_sliders["down"].value() / 100.0
            params["left_expansion_ratio"] = self._expand_sliders["left"].value() / 100.0
            params["right_expansion_ratio"] = self._expand_sliders["right"].value() / 100.0
            params["prompt"] = self.prompt_edit.toPlainText().strip()
        elif self.edit_mode == "即梦超清":
            params["resolution"] = self.sr_resolution_combo.currentText()
            params["scale"] = self.sr_scale_slider.value()
        elif self.edit_mode == "即梦局部重绘":
            params["prompt"] = self.prompt_edit.toPlainText().strip()
            params["seed"] = self.inpaint_seed_spin.value()
        return params

    def serialize_data(self):
        return {
            "edit_mode": self.edit_mode,
            "prompt": self.prompt_edit.toPlainText(),
            "up_ratio": self._expand_sliders["up"].value(),
            "down_ratio": self._expand_sliders["down"].value(),
            "left_ratio": self._expand_sliders["left"].value(),
            "right_ratio": self._expand_sliders["right"].value(),
            "sr_resolution": self.sr_resolution_combo.currentText(),
            "sr_scale": self.sr_scale_slider.value(),
            "inpaint_seed": self.inpaint_seed_spin.value(),
        }

    def deserialize_data(self, data):
        mode = data.get("edit_mode", "可灵扩图")
        idx = self.mode_combo.findText(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.prompt_edit.setPlainText(data.get("prompt", ""))
        self._expand_sliders["up"].setValue(data.get("up_ratio", 0))
        self._expand_sliders["down"].setValue(data.get("down_ratio", 0))
        self._expand_sliders["left"].setValue(data.get("left_ratio", 0))
        self._expand_sliders["right"].setValue(data.get("right_ratio", 0))

        sr_res_idx = self.sr_resolution_combo.findText(data.get("sr_resolution", "4k"))
        if sr_res_idx >= 0:
            self.sr_resolution_combo.setCurrentIndex(sr_res_idx)
        self.sr_scale_slider.setValue(data.get("sr_scale", 50))
        self.inpaint_seed_spin.setValue(data.get("inpaint_seed", 101))
