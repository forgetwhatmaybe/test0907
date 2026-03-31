"""图片上传节点"""

from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QPushButton, QMenu, QAction, QApplication, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from pathlib import Path
import os
import platform
import subprocess

from .base_media_node import BaseMediaNode
from .cache import ThumbnailCache
from .mask_editor import MaskEditorDialog
from .widgets import DoubleClickButton
from . import styles


class ImageNode(BaseMediaNode):
    """图片上传节点 - 支持图片选择、蒙版绘制、拖拽导出"""
    node_type = "image"
    
    def __init__(self):
        super().__init__("图片上传")
        self.image_path = ""
        self.mask_path = ""
        self._has_mask_output = False
        self.add_output("图片")
        self._update_size()
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.image_container = QWidget()
        self.image_container.setFixedSize(180, 100)
        self.image_container.setStyleSheet(styles.IMAGE_PLACEHOLDER)

        self.image_label = QLabel(self.image_container)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setGeometry(2, 2, 176, 96)
        self.image_label.setStyleSheet(styles.IMAGE_PLACEHOLDER)

        self.preview_btn = DoubleClickButton(self.image_container)
        self.preview_btn.setGeometry(2, 2, 176, 96)
        self.preview_btn.setStyleSheet("background: transparent; border: none;")
        self.preview_btn.setCursor(Qt.PointingHandCursor)
        self.preview_btn.clicked.connect(self._handle_preview_clicked)
        self.preview_btn.doubleClicked.connect(self._handle_preview_clicked)
        self.preview_btn.raise_()

        self._reset_image_placeholder()
        layout.addWidget(self.image_container)
        
        self.select_btn = QPushButton("选择图片")
        self.select_btn.setStyleSheet(styles.BUTTON)
        self.select_btn.clicked.connect(self._select_image)
        layout.addWidget(self.select_btn)
    
    def load_image_file(self, file_path):
        """加载图片到节点（供拖拽上传调用）"""
        self.image_path = self.copy_to_material_library(file_path)
        self._update_image_display()
        self._notify_downstream_thumbnail_refresh()

    def _handle_preview_clicked(self):
        """点击预览图：有图片则系统打开，否则选择图片"""
        if self.image_path and Path(self.image_path).exists():
            self._open_with_system_viewer()
            return
        self._select_image()

    def _reset_image_placeholder(self):
        """恢复默认占位样式"""
        self.image_label.clear()
        self.image_label.setText("点击选择图片")
        self.image_label.setStyleSheet(styles.IMAGE_PLACEHOLDER)
        self.preview_btn.set_file_path("")

    def _open_with_system_viewer(self):
        """用系统默认图片查看器打开当前图片"""
        if not self.image_path or not Path(self.image_path).exists():
            return

        file_path = Path(self.image_path).resolve()
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(str(file_path))
            elif system == "Darwin":
                subprocess.run(["open", str(file_path)])
            else:
                subprocess.run(["xdg-open", str(file_path)])
        except Exception as e:
            print(f"打开图片失败: {e}")

    def _select_image(self):
        file_path = self.create_file_dialog("选择图片", "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_path:
            self.load_image_file(file_path)
    
    def _notify_downstream_thumbnail_refresh(self):
        """图片更换后，通知下游节点刷新缩略图"""
        for socket in self.outputs:
            for edge in socket.edges:
                if edge.end_socket:
                    downstream = edge.end_socket.node
                    if hasattr(downstream, '_refresh_thumbnails'):
                        downstream._refresh_thumbnails()
    
    def _update_image_display(self):
        if self.image_path:
            if not Path(self.image_path).exists():
                self.image_label.clear()
                self.image_label.setText("⚠ 图片已丢失")
                self.image_label.setStyleSheet("""
                    QLabel {
                        background-color: #2a2a2a;
                        border: 2px solid #FF5722;
                        border-radius: 5px;
                        color: #FF5722;
                        font-size: 12px;
                    }
                """)
                self.preview_btn.set_file_path("")
                return
            pixmap = ThumbnailCache.get(self.image_path, 176, 96)
            if pixmap and not pixmap.isNull():
                self.image_label.setPixmap(pixmap)
                self.image_label.setStyleSheet(styles.IMAGE_LOADED)
                self.preview_btn.set_file_path(self.image_path)
            else:
                self.image_label.clear()
                self.image_label.setText("⚠ 图片加载失败")
                self.image_label.setStyleSheet("""
                    QLabel {
                        background-color: #2a2a2a;
                        border: 2px solid #FF9800;
                        border-radius: 5px;
                        color: #FF9800;
                        font-size: 12px;
                    }
                """)
                self.preview_btn.set_file_path("")
        else:
            self._reset_image_placeholder()
    
    def serialize_data(self):
        return {
            "image_path": self.image_path,
            "mask_path": self.mask_path,
            "has_mask_output": self._has_mask_output,
        }
    
    def deserialize_data(self, data):
        self.image_path = data.get("image_path", "")
        self.mask_path = data.get("mask_path", "")
        self._has_mask_output = data.get("has_mask_output", False)
        if self._has_mask_output and len(self.outputs) < 2:
            self.add_output("蒙版")
        if self.image_path:
            self._update_image_display()
    
    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet(styles.CONTEXT_MENU)
        
        if self.image_path and Path(self.image_path).exists():
            open_folder_action = QAction("📁 打开所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_image_folder)
            menu.addAction(open_folder_action)

            copy_img_action = QAction("📋 复制图片", menu)
            copy_img_action.triggered.connect(self._copy_image_to_clipboard)
            menu.addAction(copy_img_action)

            menu.addSeparator()

            mask_label = "🎨 重新绘制蒙版" if self._has_mask_output else "🎨 绘制蒙版"
            mask_action = QAction(mask_label, menu)
            mask_action.triggered.connect(self._open_mask_editor)
            menu.addAction(mask_action)
        
        return menu
    
    def _open_image_folder(self):
        """打开图片所在文件夹并选中文件"""
        self.open_file_folder(self.image_path)

    def _copy_image_to_clipboard(self):
        """将图片复制到剪贴板"""
        if not self.image_path or not Path(self.image_path).exists():
            return
        img = QImage(self.image_path)
        if not img.isNull():
            QApplication.clipboard().setImage(img)

    def _open_mask_editor(self):
        """打开蒙版绘制对话框"""
        if not self.image_path or not Path(self.image_path).exists():
            return
        dialog = MaskEditorDialog(
            self.image_path,
            self.mask_path if self.mask_path else None
        )
        if dialog.exec_() == MaskEditorDialog.Accepted:
            img_p = Path(self.image_path)
            mask_save = img_p.parent / f"{img_p.stem}_mask.png"
            dialog.save_mask(str(mask_save))
            self.mask_path = str(mask_save)

            if not self._has_mask_output:
                self.add_output("蒙版")
                self._has_mask_output = True
                self._update_size()
