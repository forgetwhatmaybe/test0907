"""输出节点 - 支持视频预览和播放"""

from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QWidget, QMenu, QAction, QApplication, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainterPath, QLinearGradient, QBrush, QPen, QColor, QIcon, QImage, QPixmap
from pathlib import Path
import platform
import subprocess
import shutil
import os

from core.node_editor.node_item import NodeItem
from .cache import ThumbnailCache
from .widgets import DoubleClickButton
from . import styles

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
IMAGE_FILE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"


class ImageDropZone(QWidget):
    """支持拖入图片的容器区域"""

    def __init__(self, on_image_dropped, parent=None):
        super().__init__(parent)
        self._on_image_dropped = on_image_dropped
        self.setAcceptDrops(True)

    @staticmethod
    def _first_image_path(mime_data) -> str:
        if not mime_data.hasUrls():
            return ""
        for url in mime_data.urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(IMAGE_EXTENSIONS):
                return path
        return ""

    def dragEnterEvent(self, event):
        if self._first_image_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._first_image_path(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._first_image_path(event.mimeData())
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        self._on_image_dropped(path)


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
        self.upload_image_path = ""
        super().__init__("视频(图片)输出")
        self.output_name = "output"
        self.on_execute_requested = None
        
        self.add_input("视频")
        self.add_output("输出")
        self._update_size()
    
    def set_execution_status(self, status):
        """设置执行状态，改变节点标题栏颜色

        Args:
            status: 'executing'=蓝色, 'success'=绿色, 'error'=红色, 'cancelled'=灰色, None=恢复默认
        """
        color_map = {
            "executing": ("#1565C0", "#1976D2"),
            "success": ("#2E7D32", "#388E3C"),
            "error": ("#C62828", "#D32F2F"),
            "cancelled": ("#616161", "#757575"),
        }
        self._status_color = color_map.get(status)
        self.update()

        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None

        if status in ("success", "error", "cancelled"):
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

        # 图片上传区域：点击选择或拖入图片
        upload_title = QLabel("图片上传:")
        upload_title.setStyleSheet(styles.LABEL_TITLE)
        layout.addWidget(upload_title)

        self.upload_container = ImageDropZone(self.load_upload_image)
        self.upload_container.setFixedSize(180, 100)

        self.upload_image_label = QLabel(self.upload_container)
        self.upload_image_label.setGeometry(2, 2, 176, 96)
        self.upload_image_label.setAlignment(Qt.AlignCenter)

        self.upload_btn = DoubleClickButton(self.upload_container)
        self.upload_btn.setGeometry(2, 2, 176, 96)
        self.upload_btn.setStyleSheet("background: transparent; border: none;")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.clicked.connect(self._handle_upload_clicked)
        self.upload_btn.doubleClicked.connect(self._select_upload_image)
        self.upload_btn.raise_()

        self._update_upload_image_display()
        layout.addWidget(self.upload_container)
    
    def load_upload_image(self, file_path):
        """加载上传的图片（点击选择或拖入），并复制到项目素材库"""
        if not file_path or not Path(file_path).exists():
            return
        self.upload_image_path = self._copy_to_material_library(file_path)
        # 尚无生成结果时，把上传图作为本节点的输出，使下游节点可直接读取
        if not self.video_path:
            self.video_path = self.upload_image_path
        self._update_upload_image_display()

    def _copy_to_material_library(self, file_path: str) -> str:
        """复制图片到项目素材库，失败时保留原路径"""
        if not self.project_path:
            return file_path
        try:
            material_dir = Path(self.project_path) / "素材库"
            material_dir.mkdir(parents=True, exist_ok=True)
            src = Path(file_path)
            dest = material_dir / src.name
            counter = 1
            while dest.exists():
                dest = material_dir / f"{src.stem}_{counter}{src.suffix}"
                counter += 1
            shutil.copy2(src, dest)
            return str(dest)
        except Exception as e:
            print(f"复制图片到素材库失败: {e}")
            return file_path

    def _handle_upload_clicked(self):
        """点击图片框：已有图片则系统打开，否则弹出选择框"""
        if self.upload_image_path and Path(self.upload_image_path).exists():
            self._open_file_with_system(self.upload_image_path)
            return
        self._select_upload_image()

    def _select_upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(None, "选择图片", "", IMAGE_FILE_FILTER)
        if file_path:
            self.load_upload_image(file_path)

    def _update_upload_image_display(self):
        """刷新上传图片区域的显示状态"""
        label = self.upload_image_label
        label.clear()

        if not self.upload_image_path:
            label.setText("点击选择图片\n或拖入图片")
            label.setStyleSheet(styles.IMAGE_PLACEHOLDER)
            self.upload_btn.set_file_path("")
            return

        if not Path(self.upload_image_path).exists():
            label.setText("⚠ 图片已丢失")
            label.setStyleSheet(styles.IMAGE_MISSING)
            self.upload_btn.set_file_path("")
            return

        pixmap = self._load_thumbnail_pixmap(self.upload_image_path)
        if pixmap is None:
            label.setText("⚠ 图片加载失败")
            label.setStyleSheet(styles.IMAGE_MISSING)
            self.upload_btn.set_file_path("")
            return

        label.setPixmap(pixmap)
        label.setStyleSheet(styles.IMAGE_LOADED)
        self.upload_btn.set_file_path(self.upload_image_path)

    def _clear_upload_image(self):
        if self.video_path and self.video_path == self.upload_image_path:
            self.video_path = ""
            self.thumbnail_path = ""
        self.upload_image_path = ""
        self._update_upload_image_display()

    def get_effective_output_path(self) -> str:
        """对外提供的结果路径：优先生成结果，其次为上传的图片"""
        for path in (self.video_path, self.upload_image_path):
            if path and Path(path).exists():
                return path
        return ""

    def get_output_name(self):
        return self.name_edit.text() or "output"
    
    def set_project_path(self, path):
        self.project_path = Path(path)
        self._auto_detect_video()
        if self.upload_image_path and hasattr(self, "upload_image_label"):
            self._update_upload_image_display()
    
    def _on_name_changed(self):
        self._auto_detect_video()
    
    @staticmethod
    def _make_image_thumbnail(image_file: Path, thumb_file: Path):
        """为图片生成缩略图，失败则静默跳过"""
        try:
            import cv2
            import numpy as np
            img_array = np.fromfile(str(image_file), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return
            h, w = img.shape[:2]
            if w > 320:
                scale = 320 / w
                img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
            cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(thumb_file))
        except Exception as e:
            print(f"生成图片缩略图失败: {e}")

    @staticmethod
    def _make_video_thumbnail(video_file: Path, thumb_file: Path):
        """为视频生成首帧缩略图，失败则静默跳过"""
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_file))
            ret, frame = cap.read()
            if ret:
                cv2.imencode('.jpg', frame)[1].tofile(str(thumb_file))
            cap.release()
        except Exception as e:
            print(f"生成视频缩略图失败: {e}")

    def _auto_detect_video(self):
        """根据输出名称自动检测项目文件夹中已有的视频/图片"""
        if not self.project_path or not self.project_path.exists():
            return

        output_name = self.get_output_name()
        image_file = self.project_path / f"{output_name}.png"
        if image_file.exists():
            self._load_detected_image(image_file)
            return

        video_file = self.project_path / f"{output_name}.mp4"
        if video_file.exists():
            self._load_detected_video(video_file)

    def _load_detected_image(self, image_file: Path):
        self._is_image_output = True
        thumb_file = self.project_path / f"{image_file.stem}_thumb.jpg"
        if not thumb_file.exists():
            self._make_image_thumbnail(image_file, thumb_file)
        source = thumb_file if thumb_file.exists() else image_file
        self.set_video_thumbnail(str(source), str(image_file))

    def _load_detected_video(self, video_file: Path):
        self._is_image_output = False
        thumb_file = self.project_path / f"{video_file.stem}_thumb.jpg"
        if not thumb_file.exists():
            self._make_video_thumbnail(video_file, thumb_file)

        if thumb_file.exists():
            self.set_video_thumbnail(str(thumb_file), str(video_file))
            return

        self._show_video_placeholder(video_file)

    def _show_video_placeholder(self, video_file: Path):
        """无缩略图可用时，显示可点击播放的占位按钮"""
        self.video_path = str(video_file)
        self.thumbnail_path = ""
        self.thumbnail_btn.setText("▶ 点击播放")
        self.video_container.setStyleSheet(styles.VIDEO_CONTAINER)
        self.video_container.setCursor(Qt.PointingHandCursor)
        self.video_container.show()
        self._update_size()

    def _shrink_thumbnail(self, source: Path) -> str:
        """为过大的图片生成小缩略图，返回可用的缩略图路径"""
        small = source.with_name(source.stem + "_thumb.jpg")
        if small.exists():
            return str(small)

        self._make_image_thumbnail(source, small)
        return str(small) if small.exists() else str(source)

    def _load_thumbnail_pixmap(self, thumb_path, width=176, height=96):
        """加载缩略图，优先走缓存"""
        pixmap = ThumbnailCache.get(thumb_path, width, height)
        if pixmap is not None:
            return pixmap
        pixmap = QPixmap(thumb_path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return pixmap if not pixmap.isNull() else None

    def set_video_thumbnail(self, thumb_path, video_path):
        """设置视频/图片缩略图"""
        self.thumbnail_path = thumb_path
        self.video_path = video_path
        self._is_image_output = video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))

        source = Path(thumb_path)
        if not source.exists():
            return

        # 大文件处理：超过 500KB 改用小缩略图
        if source.stat().st_size > 500 * 1024:
            thumb_path = self._shrink_thumbnail(source)
            self.thumbnail_path = thumb_path
            if Path(thumb_path).stat().st_size > 500 * 1024:
                return

        ThumbnailCache.invalidate(thumb_path)
        pixmap = self._load_thumbnail_pixmap(thumb_path)
        if pixmap is None:
            return

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
        """用系统默认工具打开当前结果文件"""
        self._open_file_with_system(self.video_path)

    def _open_file_with_system(self, file_path):
        """用系统默认工具打开指定文件"""
        if not file_path or not Path(file_path).exists():
            return
        file_path = Path(file_path).resolve()
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
    
    def _open_upload_image_folder(self):
        """打开上传图片所在文件夹并选中文件"""
        if not self.upload_image_path or not Path(self.upload_image_path).exists():
            return
        file_path = Path(self.upload_image_path).resolve()
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
    
    def _on_execute_current(self):
        if hasattr(self, 'on_execute_current_requested') and self.on_execute_current_requested:
            self.on_execute_current_requested(self)
    
    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(styles.CONTEXT_MENU)
        
        execute_current_action = QAction("▶ 执行当前节点", menu)
        execute_current_action.triggered.connect(lambda: self._on_execute_current())
        menu.addAction(execute_current_action)
        
        execute_workflow_action = QAction("▶ 执行工作流", menu)
        execute_workflow_action.triggered.connect(self._on_execute)
        menu.addAction(execute_workflow_action)
        
        if self.video_path and Path(self.video_path).exists():
            copy_action = QAction("📋 复制输出文件路径", menu)
            copy_action.triggered.connect(self._copy_output_path)
            menu.addAction(copy_action)
            
            open_folder_action = QAction("📁 打开文件所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_video_folder)
            menu.addAction(open_folder_action)

        if self.upload_image_path and Path(self.upload_image_path).exists():
            upload_open_action = QAction("🖼 打开上传的图片", menu)
            upload_open_action.triggered.connect(
                lambda: self._open_file_with_system(self.upload_image_path)
            )
            menu.addAction(upload_open_action)

            upload_change_action = QAction("🔄 更换上传图片", menu)
            upload_change_action.triggered.connect(self._select_upload_image)
            menu.addAction(upload_change_action)

            upload_folder_action = QAction("📁 打开图片所在文件夹", menu)
            upload_folder_action.triggered.connect(self._open_upload_image_folder)
            menu.addAction(upload_folder_action)

            upload_clear_action = QAction("🧹 清除上传图片", menu)
            upload_clear_action.triggered.connect(self._clear_upload_image)
            menu.addAction(upload_clear_action)
        else:
            upload_add_action = QAction("🖼 上传图片", menu)
            upload_add_action.triggered.connect(self._select_upload_image)
            menu.addAction(upload_add_action)

        return menu
    
    def serialize_data(self):
        return {
            "output_name": self.name_edit.text(),
            "video_path": self.video_path,
            "thumbnail_path": self.thumbnail_path,
            "upload_image_path": self.upload_image_path
        }
    
    def deserialize_data(self, data):
        self.name_edit.setText(data.get("output_name", "output"))
        self.video_path = data.get("video_path", "")
        self.thumbnail_path = data.get("thumbnail_path", "")
        self.upload_image_path = data.get("upload_image_path", "")
        self._update_upload_image_display()
        
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            self.set_video_thumbnail(self.thumbnail_path, self.video_path)
        elif self.video_path and Path(self.video_path).exists():
            self._auto_detect_video()
