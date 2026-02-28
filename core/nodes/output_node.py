"""输出节点 - 支持视频预览和播放"""

from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QWidget, QMenu, QAction, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainterPath, QLinearGradient, QBrush, QPen, QColor, QIcon, QImage, QPixmap
from pathlib import Path
import platform
import subprocess
import os

from core.node_editor.node_item import NodeItem
from .cache import ThumbnailCache
from .widgets import DoubleClickButton
from . import styles


class OutputNode(NodeItem):
    """输出节点 - 显示生成结果，支持视频播放和图片预览"""
    node_type = "output"
    _counter = 0
    
    def __init__(self):
        self.video_path = ""
        self.thumbnail_path = ""
        self.project_path = None
        self._status_color = None
        self._status_timer = None
        self._is_image_output = False
        super().__init__("视频(图片)输出")
        self.output_name = "output"
        self.on_execute_requested = None
        
        self.add_input("视频")
        self.add_output("输出")
        self._update_size()
    
    def set_execution_status(self, status):
        """设置执行状态，改变节点标题栏颜色
        
        Args:
            status: 'executing'=蓝色, 'success'=绿色, 'error'=红色, None=恢复默认
        """
        color_map = {
            "executing": ("#1565C0", "#1976D2"),
            "success": ("#2E7D32", "#388E3C"),
            "error": ("#C62828", "#D32F2F"),
        }
        self._status_color = color_map.get(status)
        self.update()
        
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None
        
        if status in ("success", "error"):
            self._status_timer = QTimer()
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self._reset_status_color)
            self._status_timer.start(5000 if status == "success" else 8000)
    
    def _reset_status_color(self):
        self._status_color = None
        self._status_timer = None
        self.update()
    
    def paint(self, painter, option, widget):
        """重写绘制方法，支持状态变色"""
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        gradient = QLinearGradient(0, 0, 0, self.height)
        gradient.setColorAt(0, QColor("#3d3d3d"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        
        painter.setBrush(QBrush(gradient))
        
        if self._status_color:
            painter.setPen(QPen(QColor(self._status_color[1]), 3))
        elif self.isSelected():
            painter.setPen(QPen(QColor("#00aaff"), 3))
        else:
            painter.setPen(QPen(QColor("#555555"), 1))
        
        painter.drawPath(path)
        
        # 标题栏
        header_path = QPainterPath()
        header_path.addRoundedRect(0, 0, self.width, 30, 10, 10)
        header_path.addRect(0, 15, self.width, 15)
        
        header_gradient = QLinearGradient(0, 0, 0, 30)
        if self._status_color:
            header_gradient.setColorAt(0, QColor(self._status_color[0]))
            header_gradient.setColorAt(1, QColor(self._status_color[1]))
        else:
            header_gradient.setColorAt(0, QColor("#5c5c5c"))
            header_gradient.setColorAt(1, QColor("#4a4a4a"))
        
        painter.setBrush(QBrush(header_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(header_path)
    
    def set_unique_name(self, existing_names=None):
        if existing_names is None:
            existing_names = set()
        
        counter = OutputNode._counter + 1
        while f"output_{counter}" in existing_names:
            counter += 1
        
        self.name_edit.setText(f"output_{counter}")
        OutputNode._counter = counter
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        name_label = QLabel("输出名称:")
        name_label.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(name_label)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("视频文件名")
        self.name_edit.setText("output")
        self.name_edit.setStyleSheet(styles.LINE_EDIT)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        layout.addWidget(self.name_edit)
        
        hint_label = QLabel("将保存为: {名称}.mp4 或 .png")
        hint_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(hint_label)
        
        # 视频预览区域
        self.video_container = QWidget()
        self.video_container.setFixedSize(180, 100)
        self.video_container.setStyleSheet(styles.IMAGE_PLACEHOLDER)
        
        self.frame_label = QLabel(self.video_container)
        self.frame_label.setGeometry(2, 2, 176, 96)
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setStyleSheet("background: black;")
        
        self.thumbnail_btn = DoubleClickButton(self.video_container)
        self.thumbnail_btn.setGeometry(2, 2, 176, 96)
        self.thumbnail_btn.setStyleSheet("background: transparent; border: none;")
        self.thumbnail_btn.clicked.connect(self._toggle_video_playback)
        self.thumbnail_btn.doubleClicked.connect(self._open_with_system_player)
        self.thumbnail_btn.raise_()
        
        # OpenCV 播放器状态
        self._cv_cap = None
        self._is_playing = False
        self._play_timer = QTimer()
        self._play_timer.timeout.connect(self._render_next_frame)
        
        self.video_container.hide()
        layout.addWidget(self.video_container)
    
    def get_output_name(self):
        return self.name_edit.text() or "output"
    
    def set_project_path(self, path):
        self.project_path = Path(path)
        self._auto_detect_video()
    
    def _on_name_changed(self):
        self._auto_detect_video()
    
    def _auto_detect_video(self):
        """根据输出名称自动检测项目文件夹中已有的视频/图片"""
        if not self.project_path or not self.project_path.exists():
            return
        
        output_name = self.get_output_name()
        video_file = self.project_path / f"{output_name}.mp4"
        image_file = self.project_path / f"{output_name}.png"
        
        if image_file.exists():
            self._is_image_output = True
            thumb_from_png = self.project_path / f"{output_name}_thumb.jpg"
            if not thumb_from_png.exists():
                try:
                    import cv2
                    import numpy as np
                    img_array = np.fromfile(str(image_file), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        if w > 320:
                            scale = 320 / w
                            img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
                        cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(thumb_from_png))
                except Exception:
                    pass
            if thumb_from_png.exists():
                self.set_video_thumbnail(str(thumb_from_png), str(image_file))
            else:
                self.set_video_thumbnail(str(image_file), str(image_file))
            return
        
        if video_file.exists():
            self._is_image_output = False
            thumb_file = self.project_path / f"{output_name}_thumb.jpg"
            if not thumb_file.exists():
                try:
                    import cv2
                    cap = cv2.VideoCapture(str(video_file))
                    ret, frame = cap.read()
                    if ret:
                        cv2.imencode('.jpg', frame)[1].tofile(str(thumb_file))
                    cap.release()
                except Exception:
                    pass
            
            if thumb_file.exists():
                self.set_video_thumbnail(str(thumb_file), str(video_file))
            else:
                self.video_path = str(video_file)
                self.thumbnail_path = ""
                self.thumbnail_btn.setText("▶ 点击播放")
                self.video_container.setStyleSheet(styles.VIDEO_CONTAINER)
                self.video_container.setCursor(Qt.PointingHandCursor)
                self.video_container.show()
                self._update_size()
    
    def set_video_thumbnail(self, thumb_path, video_path):
        """设置视频/图片缩略图"""
        self.thumbnail_path = thumb_path
        self.video_path = video_path
        self._is_image_output = video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))
        
        p = Path(thumb_path)
        if not p.exists():
            return
        
        # 大文件处理：超过 500KB 生成小缩略图
        file_size = p.stat().st_size
        if file_size > 500 * 1024:
            thumb_small = str(p.with_name(p.stem + "_thumb.jpg"))
            if not Path(thumb_small).exists():
                try:
                    import cv2
                    import numpy as np
                    img_array = np.fromfile(str(p), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        if w > 320:
                            scale = 320 / w
                            img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
                        cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(thumb_small)
                except Exception:
                    pass
            if Path(thumb_small).exists():
                self.thumbnail_path = thumb_small
                thumb_path = thumb_small
            if Path(thumb_path).stat().st_size > 500 * 1024:
                return
        
        ThumbnailCache.invalidate(thumb_path)
        
        # 尝试多种方式加载缩略图
        pixmap = ThumbnailCache.get(thumb_path, 176, 96)
        if pixmap is None:
            pixmap = QPixmap(thumb_path).scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        if pixmap and not pixmap.isNull():
            self.thumbnail_btn.setIcon(QIcon(pixmap))
            self.thumbnail_btn.setIconSize(pixmap.size())
            self.thumbnail_btn.set_file_path(self.video_path)
            self.video_container.setStyleSheet(styles.VIDEO_CONTAINER)
            self.video_container.setCursor(Qt.PointingHandCursor)
            self.video_container.show()
            self._update_size()
    
    def _toggle_video_playback(self):
        """切换视频播放/暂停"""
        if not self.video_path or not Path(self.video_path).exists():
            return
        
        if self._is_image_output:
            self._open_with_system_player()
            return
        
        if self._is_playing:
            self._is_playing = False
            self._play_timer.stop()
            if self._cv_cap:
                self._cv_cap.release()
                self._cv_cap = None
            self._restore_thumbnail_icon()
        else:
            try:
                import cv2
                self._cv_cap = cv2.VideoCapture(self.video_path)
                if not self._cv_cap.isOpened():
                    return
                fps = self._cv_cap.get(cv2.CAP_PROP_FPS)
                if fps <= 0:
                    fps = 24
                self._is_playing = True
                self.thumbnail_btn.setIcon(QIcon())
                self.thumbnail_btn.setText("")
                self._play_timer.start(int(1000 / fps))
            except ImportError:
                print("需要安装 opencv-python 才能播放视频")
    
    def _render_next_frame(self):
        """渲染下一帧"""
        if not self._cv_cap or not self._is_playing:
            self._play_timer.stop()
            return
        
        import cv2
        ret, frame = self._cv_cap.read()
        if not ret:
            self._is_playing = False
            self._play_timer.stop()
            self._cv_cap.release()
            self._cv_cap = None
            self._restore_thumbnail_icon()
            return
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        q_img = QImage(frame_rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(q_img)
        scaled = pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.frame_label.setPixmap(scaled)
    
    def _restore_thumbnail_icon(self):
        """恢复缩略图显示"""
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            pixmap = ThumbnailCache.get(self.thumbnail_path, 176, 96)
            if pixmap is None:
                pixmap = QPixmap(self.thumbnail_path).scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if pixmap and not pixmap.isNull():
                self.thumbnail_btn.setIcon(QIcon(pixmap))
                self.thumbnail_btn.setIconSize(pixmap.size())
        self.frame_label.clear()
    
    def _open_with_system_player(self):
        """用系统默认工具打开文件"""
        if not self.video_path or not Path(self.video_path).exists():
            return
        file_path = Path(self.video_path).resolve()
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(str(file_path))
            elif system == "Darwin":
                subprocess.run(["open", str(file_path)])
            else:
                subprocess.run(["xdg-open", str(file_path)])
        except Exception as e:
            print(f"打开文件失败: {e}")

    def _open_video_folder(self):
        """打开文件所在文件夹"""
        if self.video_path and Path(self.video_path).exists():
            file_path = Path(self.video_path).resolve()
            system = platform.system()
            try:
                if system == "Windows":
                    subprocess.run(["explorer", "/select,", str(file_path)], check=True)
                elif system == "Darwin":
                    subprocess.run(["open", str(file_path.parent)], check=True)
                else:
                    subprocess.run(["xdg-open", str(file_path.parent)], check=True)
            except Exception as e:
                print(f"打开文件夹失败: {e}")
    
    def _copy_output_path(self):
        """复制输出文件路径到剪贴板"""
        if self.video_path and Path(self.video_path).exists():
            clipboard = QApplication.clipboard()
            is_img = self.video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))
            prefix = "TAPNOW_IMG:" if is_img else "TAPNOW_VID:"
            clipboard.setText(prefix + self.video_path)
    
    def _on_execute(self):
        if hasattr(self, 'on_execute_requested') and self.on_execute_requested:
            self.on_execute_requested(self)
    
    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(styles.CONTEXT_MENU)
        
        execute_action = QAction("▶ 执行工作流", menu)
        execute_action.triggered.connect(self._on_execute)
        menu.addAction(execute_action)
        
        if self.video_path and Path(self.video_path).exists():
            copy_action = QAction("📋 复制输出文件路径", menu)
            copy_action.triggered.connect(self._copy_output_path)
            menu.addAction(copy_action)
            
            open_folder_action = QAction("📁 打开文件所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_video_folder)
            menu.addAction(open_folder_action)
        
        return menu
    
    def serialize_data(self):
        return {
            "output_name": self.name_edit.text(),
            "video_path": self.video_path,
            "thumbnail_path": self.thumbnail_path
        }
    
    def deserialize_data(self, data):
        self.name_edit.setText(data.get("output_name", "output"))
        self.video_path = data.get("video_path", "")
        self.thumbnail_path = data.get("thumbnail_path", "")
        
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            self.set_video_thumbnail(self.thumbnail_path, self.video_path)
        elif self.video_path and Path(self.video_path).exists():
            self._auto_detect_video()
