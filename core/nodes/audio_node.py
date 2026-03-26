"""音频上传节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QPushButton, QMenu, QAction
from PyQt5.QtCore import Qt
from pathlib import Path

from .base_media_node import BaseMediaNode
from . import styles


class AudioNode(BaseMediaNode):
    """音频上传节点：上传音频文件作为输入"""
    node_type = "audio"

    def __init__(self):
        super().__init__("音频上传")
        self.audio_path = ""
        self.add_output("音频")
        self._update_size()

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.audio_label = QLabel("🎵 点击选择音频")
        self.audio_label.setAlignment(Qt.AlignCenter)
        self.audio_label.setFixedSize(180, 60)
        self.audio_label.setStyleSheet(styles.IMAGE_PLACEHOLDER)
        self.audio_label.setCursor(Qt.PointingHandCursor)
        self.audio_label.mousePressEvent = lambda e: self._select_audio()
        layout.addWidget(self.audio_label)

        self.select_btn = QPushButton("选择音频")
        self.select_btn.setStyleSheet(styles.BUTTON)
        self.select_btn.clicked.connect(self._select_audio)
        layout.addWidget(self.select_btn)

    def load_audio_file(self, file_path):
        """加载音频到节点（供拖拽上传调用）"""
        self.audio_path = self.copy_to_material_library(file_path)
        self._update_audio_display()

    def _select_audio(self):
        file_path = self.create_file_dialog("选择音频", "音频文件 (*.mp3 *.wav)")
        if file_path:
            self.load_audio_file(file_path)

    def _update_audio_display(self):
        if self.audio_path and Path(self.audio_path).exists():
            name = Path(self.audio_path).name
            # 截断过长的文件名
            if len(name) > 20:
                name = name[:17] + "..."
            self.audio_label.setText(f"🎵 {name}")
            self.audio_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #00BCD4;
                    border-radius: 5px;
                    color: #00BCD4;
                    font-size: 11px;
                    padding: 5px;
                }
            """)
        elif self.audio_path:
            self.audio_label.setText("⚠ 音频已丢失")
            self.audio_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #FF5722;
                    border-radius: 5px;
                    color: #FF5722;
                    font-size: 12px;
                }
            """)

    def serialize_data(self):
        return {"audio_path": self.audio_path}

    def deserialize_data(self, data):
        self.audio_path = data.get("audio_path", "")
        if self.audio_path:
            self._update_audio_display()

    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(styles.CONTEXT_MENU)
        if self.audio_path and Path(self.audio_path).exists():
            open_folder_action = QAction("📁 打开所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_audio_folder)
            menu.addAction(open_folder_action)
        return menu

    def _open_audio_folder(self):
        self.open_file_folder(self.audio_path)
