"""Seedance 2.0 API 节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QSlider, QCheckBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from core.node_editor.node_item import NodeItem
from core.node_editor.edge import Edge
from ..widgets import ImageThumbnailStrip, VideoThumbnailStrip, AudioThumbnailStrip
from .. import styles


class Seedance2APINode(NodeItem):
    """Seedance 2.0 生视频节点 - 支持图生视频、首尾帧、多模态"""
    node_type = "seedance2_api"

    def __init__(self):
        self._image_order = []
        self._video_order = []
        self._audio_order = []
        self._images_expanded = True
        self._videos_expanded = True
        self._audios_expanded = True
        self.generation_mode = "multimodal"  # 默认参考生视频模式

        super().__init__("Seedance 2.0")
        self._setup_sockets()
        self.add_output("视频")

        self._update_size()

    def _setup_sockets(self):
        """根据当前模式重建输入 socket"""
        # 保存现有连接
        first_input_edges = []
        second_input_edges = []
        if self.inputs and len(self.inputs) >= 1:
            for edge in self.inputs[0].edges[:]:
                first_input_edges.append(edge.start_socket)
        if self.inputs and len(self.inputs) >= 2:
            for edge in self.inputs[1].edges[:]:
                second_input_edges.append(edge.start_socket)

        # 清除现有输入口
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()

        # 根据模式创建新的输入口
        if self.generation_mode == "multimodal":
            self.add_multi_input("参考图片")
            self.add_multi_input("参考视频")
            self.add_multi_input("参考音频")
        elif self.generation_mode == "image_to_video":
            self.add_input("图片")
        elif self.generation_mode == "first_last_frame":
            self.add_input("首帧图片")
            self.add_input("尾帧图片")

        # 恢复连接
        if first_input_edges and self.inputs:
            scene = self.scene()
            if scene:
                for start_socket in first_input_edges:
                    edge = Edge(start_socket, self.inputs[0])
                    scene.addItem(edge)
        if second_input_edges and len(self.inputs) >= 2:
            scene = self.scene()
            if scene:
                for start_socket in second_input_edges:
                    edge = Edge(start_socket, self.inputs[1])
                    scene.addItem(edge)

        # 重新连接信号
        if self.inputs and len(self.inputs) >= 1:
            self.inputs[0].signals.connected.connect(self._on_image_edge_changed)
            self.inputs[0].signals.disconnected.connect(self._on_image_edge_changed)
        if self.inputs and len(self.inputs) >= 2:
            self.inputs[1].signals.connected.connect(self._on_video_edge_changed)
            self.inputs[1].signals.disconnected.connect(self._on_video_edge_changed)
        if self.inputs and len(self.inputs) >= 3:
            self.inputs[2].signals.connected.connect(self._on_audio_edge_changed)
            self.inputs[2].signals.disconnected.connect(self._on_audio_edge_changed)

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # 生成模式选择
        mode_label = QLabel("生成模式:")
        mode_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["参考生视频", "图生视频", "首尾帧"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet(styles.COMBO_BOX)
        layout.addWidget(self.mode_combo)

        # 参考图片缩略图条
        self.img_toggle_label = QLabel("📷 参考图片")
        self.img_toggle_label.setStyleSheet(styles.LABEL_TITLE + " color: #FF9800;")
        self.img_toggle_label.setCursor(Qt.PointingHandCursor)
        self.img_toggle_label.mousePressEvent = lambda e: self._toggle_images()
        layout.addWidget(self.img_toggle_label)

        self.image_thumbnail_strip = ImageThumbnailStrip()
        self.image_thumbnail_strip.order_changed.connect(self._on_image_order_changed)
        layout.addWidget(self.image_thumbnail_strip)

        # 参考视频缩略图条
        self.vid_toggle_label = QLabel("🎬 参考视频")
        self.vid_toggle_label.setStyleSheet(styles.LABEL_TITLE + " color: #7B1FA2;")
        self.vid_toggle_label.setCursor(Qt.PointingHandCursor)
        self.vid_toggle_label.mousePressEvent = lambda e: self._toggle_videos()
        layout.addWidget(self.vid_toggle_label)

        self.video_thumbnail_strip = VideoThumbnailStrip()
        self.video_thumbnail_strip.order_changed.connect(self._on_video_order_changed)
        layout.addWidget(self.video_thumbnail_strip)

        # 参考音频缩略图条
        self.aud_toggle_label = QLabel("🎵 参考音频")
        self.aud_toggle_label.setStyleSheet(styles.LABEL_TITLE + " color: #00BCD4;")
        self.aud_toggle_label.setCursor(Qt.PointingHandCursor)
        self.aud_toggle_label.mousePressEvent = lambda e: self._toggle_audios()
        layout.addWidget(self.aud_toggle_label)

        self.audio_thumbnail_strip = AudioThumbnailStrip()
        self.audio_thumbnail_strip.order_changed.connect(self._on_audio_order_changed)
        layout.addWidget(self.audio_thumbnail_strip)

        # 提示词
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(prompt_label)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容... 支持 @tag 引用\n例如: @Image1 as first frame, @Audio1 for BGM rhythm")
        self.prompt_edit.setMinimumHeight(50)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet(styles.TEXT_EDIT)
        layout.addWidget(self.prompt_edit)

        # 选项行
        options_layout = QHBoxLayout()

        # 时长
        dur_label = QLabel("时长:")
        dur_label.setStyleSheet(styles.LABEL_TITLE)
        options_layout.addWidget(dur_label)

        self.duration_slider = QSlider(Qt.Horizontal)
        self.duration_slider.setRange(4, 15)
        self.duration_slider.setValue(5)
        self.duration_slider.setStyleSheet(styles.SLIDER_GREEN)
        self.duration_slider.valueChanged.connect(self._on_duration_changed)
        options_layout.addWidget(self.duration_slider)

        self.duration_value_label = QLabel("5s")
        self.duration_value_label.setStyleSheet(styles.LABEL_VALUE)
        options_layout.addWidget(self.duration_value_label)

        layout.addLayout(options_layout)

        # 质量和比例
        qr_layout = QHBoxLayout()

        quality_label = QLabel("质量:")
        quality_label.setStyleSheet(styles.LABEL_TITLE)
        qr_layout.addWidget(quality_label)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["720p", "1080p", "480p"])
        self.quality_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        qr_layout.addWidget(self.quality_combo)

        ar_label = QLabel("比例:")
        ar_label.setStyleSheet(styles.LABEL_TITLE)
        qr_layout.addWidget(ar_label)

        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems(["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"])
        self.aspect_ratio_combo.setStyleSheet(styles.COMBO_BOX_SMALL)
        qr_layout.addWidget(self.aspect_ratio_combo)

        layout.addLayout(qr_layout)

        # 生成音频开关
        self.generate_audio_cb = QCheckBox("生成同步音频")
        self.generate_audio_cb.setChecked(True)
        self.generate_audio_cb.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        layout.addWidget(self.generate_audio_cb)

        # 初始化模式显示
        self._update_mode_visibility()

    def _on_mode_changed(self, mode_text):
        """模式切换处理"""
        mode_map = {
            "参考生视频": "multimodal",
            "图生视频": "image_to_video",
            "首尾帧": "first_last_frame"
        }
        new_mode = mode_map.get(mode_text, "multimodal")
        if new_mode != self.generation_mode:
            self.generation_mode = new_mode
            self._setup_sockets()
            self._update_mode_visibility()
            self.update_sockets_position()
            self.update()

    def _update_mode_visibility(self):
        """根据模式更新 UI 可见性"""
        if self.generation_mode == "multimodal":
            # 参考生视频模式：显示所有缩略图条
            self.img_toggle_label.setVisible(True)
            self.image_thumbnail_strip.setVisible(self._images_expanded)
            self.vid_toggle_label.setVisible(True)
            self.video_thumbnail_strip.setVisible(self._videos_expanded)
            self.aud_toggle_label.setVisible(True)
            self.audio_thumbnail_strip.setVisible(self._audios_expanded)
        elif self.generation_mode == "image_to_video":
            # 图生视频模式：只显示图片缩略图条
            self.img_toggle_label.setVisible(True)
            self.image_thumbnail_strip.setVisible(self._images_expanded)
            self.vid_toggle_label.setVisible(False)
            self.video_thumbnail_strip.setVisible(False)
            self.aud_toggle_label.setVisible(False)
            self.audio_thumbnail_strip.setVisible(False)
        elif self.generation_mode == "first_last_frame":
            # 首尾帧模式：只显示图片缩略图条（用于首帧和尾帧）
            self.img_toggle_label.setVisible(True)
            self.image_thumbnail_strip.setVisible(self._images_expanded)
            self.vid_toggle_label.setVisible(False)
            self.video_thumbnail_strip.setVisible(False)
            self.aud_toggle_label.setVisible(False)
            self.audio_thumbnail_strip.setVisible(False)
        self._update_size()

    def _toggle_section(self, expanded_attr, strip, toggle_label):
        """通用的展开/收起切换方法"""
        current = getattr(self, expanded_attr)
        setattr(self, expanded_attr, not current)
        has_items = len(strip._ordered_items) > 0
        toggle_label.setVisible(has_items or not current)
        strip.setVisible(not current)
        self._update_size()

    def _toggle_images(self):
        self._toggle_section("_images_expanded", self.image_thumbnail_strip, self.img_toggle_label)

    def _toggle_videos(self):
        self._toggle_section("_videos_expanded", self.video_thumbnail_strip, self.vid_toggle_label)

    def _toggle_audios(self):
        self._toggle_section("_audios_expanded", self.audio_thumbnail_strip, self.aud_toggle_label)

    def _on_image_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_image_thumbnails)

    def _on_video_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_video_thumbnails)

    def _on_audio_edge_changed(self, edge=None):
        QTimer.singleShot(0, self._refresh_audio_thumbnails)

    def _refresh_thumbnails(self, input_idx, path_attrs, strip, toggle_label, expanded_attr):
        """通用的缩略图刷新方法"""
        from pathlib import Path
        connected_items = []
        if len(self.inputs) > input_idx:
            for edge in self.inputs[input_idx].edges:
                if edge.start_socket:
                    src_node = edge.start_socket.node
                    for attr in path_attrs:
                        path = getattr(src_node, attr, '')
                        if path and Path(path).exists():
                            connected_items.append((src_node.id, path))
                            break

        strip.update_thumbnails(connected_items)
        has_items = len(connected_items) > 0
        toggle_label.setVisible(has_items and getattr(self, expanded_attr))
        strip.setVisible(getattr(self, expanded_attr))
        self._update_size()

    def _refresh_image_thumbnails(self):
        self._refresh_thumbnails(
            0,
            ['image_path', 'generated_image_path', 'video_path', '_result_path'],
            self.image_thumbnail_strip,
            self.img_toggle_label,
            '_images_expanded'
        )

    def _refresh_video_thumbnails(self):
        self._refresh_thumbnails(
            1,
            ['video_path'],
            self.video_thumbnail_strip,
            self.vid_toggle_label,
            '_videos_expanded'
        )

    def _refresh_audio_thumbnails(self):
        self._refresh_thumbnails(
            2,
            ['audio_path'],
            self.audio_thumbnail_strip,
            self.aud_toggle_label,
            '_audios_expanded'
        )

    def _on_image_order_changed(self):
        self._image_order = self.image_thumbnail_strip.get_ordered_node_ids()
        self._update_size()

    def _on_video_order_changed(self):
        self._video_order = self.video_thumbnail_strip.get_ordered_node_ids()
        self._update_size()

    def _on_audio_order_changed(self):
        self._audio_order = self.audio_thumbnail_strip.get_ordered_node_ids()
        self._update_size()

    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(50, new_height))
        self._update_size()

    def _on_duration_changed(self, value):
        self.duration_value_label.setText(f"{value}s")

    def get_ordered_image_paths(self):
        return self.image_thumbnail_strip.get_ordered_image_paths()

    def get_ordered_video_paths(self):
        return self.video_thumbnail_strip.get_ordered_video_paths()

    def get_ordered_audio_paths(self):
        return self.audio_thumbnail_strip.get_ordered_audio_paths()

    def get_ordered_image_node_ids(self):
        return self._image_order if self._image_order else self.image_thumbnail_strip.get_ordered_node_ids()

    def get_ordered_video_node_ids(self):
        return self._video_order if self._video_order else self.video_thumbnail_strip.get_ordered_node_ids()

    def get_ordered_audio_node_ids(self):
        return self._audio_order if self._audio_order else self.audio_thumbnail_strip.get_ordered_node_ids()

    def get_params(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "duration": self.duration_slider.value(),
            "quality": self.quality_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
            "generate_audio": self.generate_audio_cb.isChecked(),
        }

    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "duration": self.duration_slider.value(),
            "quality": self.quality_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
            "generate_audio": self.generate_audio_cb.isChecked(),
            "generation_mode": self.generation_mode,
            "image_order": self.image_thumbnail_strip.get_ordered_node_ids(),
            "video_order": self.video_thumbnail_strip.get_ordered_node_ids(),
            "audio_order": self.audio_thumbnail_strip.get_ordered_node_ids(),
        }

    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        duration = data.get("duration", 5)
        self.duration_slider.setValue(duration)
        self.duration_value_label.setText(f"{duration}s")

        quality_index = self.quality_combo.findText(data.get("quality", "720p"))
        if quality_index >= 0:
            self.quality_combo.setCurrentIndex(quality_index)

        ar_index = self.aspect_ratio_combo.findText(data.get("aspect_ratio", "16:9"))
        if ar_index >= 0:
            self.aspect_ratio_combo.setCurrentIndex(ar_index)

        self.generate_audio_cb.setChecked(data.get("generate_audio", True))

        # 恢复生成模式
        saved_mode = data.get("generation_mode", "multimodal")
        self.generation_mode = saved_mode
        mode_text_map = {
            "multimodal": "参考生视频",
            "image_to_video": "图生视频",
            "first_last_frame": "首尾帧"
        }
        mode_text = mode_text_map.get(saved_mode, "参考生视频")
        mode_index = self.mode_combo.findText(mode_text)
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)

        self._image_order = data.get("image_order", [])
        self._video_order = data.get("video_order", [])
        self._audio_order = data.get("audio_order", [])
