"""媒体文件上传节点基类 - 封装公共逻辑"""

from PyQt5.QtWidgets import QFileDialog
from pathlib import Path
import shutil
import platform
import subprocess

from core.node_editor.node_item import NodeItem


class BaseMediaNode(NodeItem):
    """媒体文件上传节点基类，封装文件加载、文件夹打开等公共逻辑"""

    def __init__(self, title: str):
        super().__init__(title)
        self.file_path = ""
        self.project_path = None

    def set_project_path(self, path):
        self.project_path = Path(path)

    def copy_to_material_library(self, file_path: str) -> str:
        """复制文件到项目素材库，返回目标路径

        Args:
            file_path: 源文件路径

        Returns:
            目标文件路径
        """
        if not self.project_path:
            return file_path

        material_dir = self.project_path / "素材库"
        material_dir.mkdir(exist_ok=True)

        file_name = Path(file_path).name
        dest_path = material_dir / file_name

        # 处理重名文件
        counter = 1
        while dest_path.exists():
            stem = Path(file_path).stem
            suffix = Path(file_path).suffix
            dest_path = material_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        shutil.copy2(file_path, dest_path)
        return str(dest_path)

    def open_file_folder(self, file_path: str):
        """打开文件所在文件夹并选中文件

        Args:
            file_path: 文件路径
        """
        if not file_path or not Path(file_path).exists():
            return

        resolved_path = Path(file_path).resolve()
        system = platform.system()

        try:
            if system == "Windows":
                subprocess.run(["explorer", "/select,", str(resolved_path)], check=True)
            elif system == "Darwin":
                subprocess.run(["open", str(resolved_path.parent)], check=True)
            else:
                subprocess.run(["xdg-open", str(resolved_path.parent)], check=True)
        except Exception as e:
            print(f"打开文件夹失败: {e}")

    def create_file_dialog(self, title: str, file_filter: str) -> str:
        """创建文件选择对话框

        Args:
            title: 对话框标题
            file_filter: 文件过滤器

        Returns:
            选择的文件路径，未选择返回空字符串
        """
        file_path, _ = QFileDialog.getOpenFileName(None, title, "", file_filter)
        return file_path if file_path else ""