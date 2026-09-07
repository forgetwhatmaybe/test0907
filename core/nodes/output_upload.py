"""输出节点图片上传功能扩展

背景：项目里存在两份 OutputNode 定义，真正被 editor_window 使用的是
``core/nodes/nodes.py`` 中的那份（带「批次」控件）。该巨型文件当前圈复杂度已超标、
暂不可直接编辑，因此本模块采用运行时注入的方式，为 OutputNode 增加图片上传区域，
不改动 nodes.py 本体。

用法：在程序入口处执行::

    from core.nodes.nodes import OutputNode
    from core.nodes.output_upload import install_output_upload
    install_output_upload(OutputNode)
"""

from PyQt5.QtWidgets import QLabel, QWidget, QFileDialog, QAction
from PyQt5.QtCore import Qt
from pathlib import Path
import platform
import shutil
import subprocess

from .cache import ThumbnailCache
from .widgets import DoubleClickButton

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
IMAGE_FILE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"

PLACEHOLDER_STYLE = """
    QLabel {
        background-color: #2a2a2a; border: 2px dashed #555;
        border-radius: 5px; color: #888;
    }
"""

LOADED_STYLE = """
    QLabel {
        background-color: #2a2a2a; border: 2px solid #4CAF50;
        border-radius: 5px;
    }
"""

MISSING_STYLE = """
    QLabel {
        background-color: #2a2a2a; border: 2px solid #FF5722;
        border-radius: 5px; color: #FF5722; font-size: 12px;
    }
"""


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


def _open_file_with_system(node, file_path):
    """用系统默认工具打开文件"""
    if not file_path or not Path(file_path).exists():
        return
    resolved = Path(file_path).resolve()
    system = platform.system()
    try:
        if system == "Windows":
            import os
            os.startfile(str(resolved))
        elif system == "Darwin":
            subprocess.run(["open", str(resolved)])
        else:
            subprocess.run(["xdg-open", str(resolved)])
    except Exception as e:
        print(f"打开文件失败: {e}")


def _load_thumbnail_pixmap(path, width=176, height=96):
    """加载缩略图，优先走缓存"""
    pixmap = ThumbnailCache.get(path, width, height)
    if pixmap is not None:
        return pixmap
    from PyQt5.QtGui import QPixmap
    pixmap = QPixmap(path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pixmap if not pixmap.isNull() else None


def _build_upload_area(self):
    """在原内容下方追加图片上传区域"""
    if getattr(self, "_upload_area_built", False):
        return

    layout = self._content_widget.layout()
    if layout is None:
        return

    title = QLabel("图片上传:")
    title.setStyleSheet("color: #aaa; font-size: 11px;")
    layout.addWidget(title)

    container = ImageDropZone(self.load_upload_image)
    container.setFixedSize(180, 100)

    label = QLabel(container)
    label.setGeometry(2, 2, 176, 96)
    label.setAlignment(Qt.AlignCenter)

    button = DoubleClickButton(container)
    button.setGeometry(2, 2, 176, 96)
    button.setStyleSheet("background: transparent; border: none;")
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(self._handle_upload_clicked)
    button.doubleClicked.connect(self._select_upload_image)
    button.raise_()

    self.upload_container = container
    self.upload_image_label = label
    self.upload_btn = button
    self._upload_area_built = True

    layout.addWidget(container)
    self._update_upload_image_display()
    self._update_size()


def load_upload_image(self, file_path):
    """加载上传的图片（点击选择或拖入），并复制到项目素材库"""
    if not file_path or not Path(file_path).exists():
        return
    self.upload_image_path = self._copy_to_material_library(file_path)
    # 尚无生成结果时，把上传图作为本节点输出，使下游节点可直接读取
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
        _open_file_with_system(self, self.upload_image_path)
        return
    self._select_upload_image()


def _select_upload_image(self):
    file_path, _ = QFileDialog.getOpenFileName(None, "选择图片", "", IMAGE_FILE_FILTER)
    if file_path:
        self.load_upload_image(file_path)


def _update_upload_image_display(self):
    """刷新上传图片区域的显示状态"""
    if not getattr(self, "_upload_area_built", False):
        return

    label = self.upload_image_label
    label.clear()

    if not getattr(self, "upload_image_path", ""):
        label.setText("点击选择图片\n或拖入图片")
        label.setStyleSheet(PLACEHOLDER_STYLE)
        self.upload_btn.set_file_path("")
        return

    if not Path(self.upload_image_path).exists():
        label.setText("⚠ 图片已丢失")
        label.setStyleSheet(MISSING_STYLE)
        self.upload_btn.set_file_path("")
        return

    pixmap = _load_thumbnail_pixmap(self.upload_image_path)
    if pixmap is None:
        label.setText("⚠ 图片加载失败")
        label.setStyleSheet(MISSING_STYLE)
        self.upload_btn.set_file_path("")
        return

    label.setPixmap(pixmap)
    label.setStyleSheet(LOADED_STYLE)
    self.upload_btn.set_file_path(self.upload_image_path)


def _clear_upload_image(self):
    if self.video_path and self.video_path == self.upload_image_path:
        self.video_path = ""
        self.thumbnail_path = ""
    self.upload_image_path = ""
    self._update_upload_image_display()


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


def get_effective_output_path(self) -> str:
    """对外提供的结果路径：优先生成结果，其次为上传的图片"""
    for path in (self.video_path, self.upload_image_path):
        if path and Path(path).exists():
            return path
    return ""


def _append_upload_actions(self, menu):
    """在右键菜单中追加上传图片相关操作"""
    if not getattr(self, "_upload_area_built", False):
        return menu

    has_image = bool(self.upload_image_path) and Path(self.upload_image_path).exists()
    if has_image:
        open_action = QAction("🖼 打开上传的图片", menu)
        open_action.triggered.connect(lambda: _open_file_with_system(self, self.upload_image_path))
        menu.addAction(open_action)

        change_action = QAction("🔄 更换上传图片", menu)
        change_action.triggered.connect(self._select_upload_image)
        menu.addAction(change_action)

        folder_action = QAction("📁 打开图片所在文件夹", menu)
        folder_action.triggered.connect(self._open_upload_image_folder)
        menu.addAction(folder_action)

        clear_action = QAction("🧹 清除上传图片", menu)
        clear_action.triggered.connect(self._clear_upload_image)
        menu.addAction(clear_action)
    else:
        add_action = QAction("🖼 上传图片", menu)
        add_action.triggered.connect(self._select_upload_image)
        menu.addAction(add_action)

    return menu


def install_output_upload(node_cls):
    """将图片上传能力注入到 OutputNode 类"""
    if getattr(node_cls, "_upload_installed", False):
        return node_cls

    original_setup = node_cls._setup_content
    original_serialize = node_cls.serialize_data
    original_deserialize = node_cls.deserialize_data
    original_menu = node_cls._create_context_menu

    def _setup_content(self):
        original_setup(self)
        _build_upload_area(self)

    def serialize_data(self):
        data = original_serialize(self)
        data["upload_image_path"] = getattr(self, "upload_image_path", "")
        return data

    def deserialize_data(self, data):
        original_deserialize(self, data)
        self.upload_image_path = data.get("upload_image_path", "")
        self._update_upload_image_display()

    def _create_context_menu(self):
        return _append_upload_actions(self, original_menu(self))

    node_cls._setup_content = _setup_content
    node_cls.serialize_data = serialize_data
    node_cls.deserialize_data = deserialize_data
    node_cls._create_context_menu = _create_context_menu

    # 类级默认值：实例未显式赋值时也能安全读取
    node_cls.upload_image_path = ""
    node_cls.upload_container = None
    node_cls.upload_image_label = None
    node_cls.upload_btn = None

    node_cls._build_upload_area = _build_upload_area
    node_cls.load_upload_image = load_upload_image
    node_cls._copy_to_material_library = _copy_to_material_library
    node_cls._handle_upload_clicked = _handle_upload_clicked
    node_cls._select_upload_image = _select_upload_image
    node_cls._update_upload_image_display = _update_upload_image_display
    node_cls._clear_upload_image = _clear_upload_image
    node_cls._open_upload_image_folder = _open_upload_image_folder
    node_cls.get_effective_output_path = get_effective_output_path
    node_cls._upload_installed = True

    return node_cls
