"""视频上传节点"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QPushButton, QMenu, QAction
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from pathlib import Path

from .base_media_node import BaseMediaNode
from . import styles


class VideoNode(BaseMediaNode):
    """视频上传节点：上传视频文件作为输入"""
    node_type = "video"

    def __init__(self):
        super().__init__("视频上传")
        self.video_path = ""
        self.add_output("视频")
        self._update_size()

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.video_label = QLabel("点击选择视频")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setFixedSize(180, 100)
        self.video_label.setStyleSheet(styles.IMAGE_PLACEHOLDER)
        self.video_label.setCursor(Qt.PointingHandCursor)
        self.video_label.mousePressEvent = lambda e: self._select_video()
        layout.addWidget(self.video_label)

        self.select_btn = QPushButton("选择视频")
        self.select_btn.setStyleSheet(styles.BUTTON)
        self.select_btn.clicked.connect(self._select_video)
        layout.addWidget(self.select_btn)

    def load_video_file(self, file_path):
        """加载视频到节点（供拖拽上传调用）"""
        self.video_path = self.copy_to_material_library(file_path)
        self._update_video_display()

    def _select_video(self):
        file_path = self.create_file_dialog("选择视频", "视频文件 (*.mp4 *.mov *.avi *.mkv *.wmv *.flv *.webm)")
        if file_path:
            self.load_video_file(file_path)

    def _update_video_display(self):
        if self.video_path and Path(self.video_path).exists():
            # 尝试用 OpenCV 提取第一帧作为缩略图
            thumb_pixmap = None
            try:
                import cv2
                cap = cv2.VideoCapture(self.video_path)
                ret, frame = cap.read()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    q_img = QImage(frame_rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888).copy()
                    thumb_pixmap = QPixmap.fromImage(q_img)
                cap.release()
            except ImportError:
                pass

            if thumb_pixmap and not thumb_pixmap.isNull():
                scaled = thumb_pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.video_label.setPixmap(scaled)
            else:
                self.video_label.setText(f"🎬 {Path(self.video_path).name}")

            self.video_label.setStyleSheet(styles.VIDEO_CONTAINER)
        elif self.video_path:
            self.video_label.setText("⚠ 视频已丢失")
            self.video_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #FF5722;
                    border-radius: 5px;
                    color: #FF5722; font-size: 12px;
                }
            """)

    def serialize_data(self):
        return {"video_path": self.video_path}

    def deserialize_data(self, data):
        self.video_path = data.get("video_path", "")
        if self.video_path:
            self._update_video_display()

    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(styles.CONTEXT_MENU)
        if self.video_path and Path(self.video_path).exists():
            open_folder_action = QAction("📁 打开所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_video_folder)
            menu.addAction(open_folder_action)
        return menu

    def _open_video_folder(self):
        self.open_file_folder(self.video_path)
