from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QMessageBox, QFormLayout, QGroupBox,
    QListWidget, QListWidgetItem, QSplitter, QFileDialog, QWidget,
    QListView
)
from PyQt5.QtCore import Qt
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import Config
from utils.project_manager import ProjectManager
from utils.file_utils import get_available_disks


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = Config()
        self.setWindowTitle("新建项目")
        self.setMinimumSize(400, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QComboBox {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QComboBox:hover {
                border: 1px solid #555;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #e0e0e0;
                selection-background-color: #3d6ea5;
                selection-color: #ffffff;
                border: 1px solid #555;
                outline: none;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 6px 8px;
                min-height: 24px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #3d6ea5;
                color: #ffffff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0;
                margin-right: 8px;
            }
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
            QMessageBox {
                background-color: #1a1a1a;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
            }
            QMessageBox QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
            }
        """)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.disk_combo = QComboBox()
        # 使用 QListView 替代原生下拉，确保 Windows 下暗色样式生效
        list_view = QListView()
        list_view.setUniformItemSizes(True)
        list_view.setSpacing(2)
        list_view.setStyleSheet("""
            QListView {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                outline: none;
                font-size: 13px;
            }
            QListView::item {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 8px 10px;
                min-height: 20px;
                height: 28px;
            }
            QListView::item:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QListView::item:selected {
                background-color: #3d6ea5;
                color: #ffffff;
            }
        """)
        self.disk_combo.setView(list_view)
        # 关键：给弹出容器 QFrame 也设置暗色背景，否则 Windows 下仍显示白底
        popup_container = list_view.parentWidget()
        if popup_container:
            popup_container.setStyleSheet("""
                QFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #555;
                }
            """)
        # 直接给 combo 设置样式
        self.disk_combo.setStyleSheet("""
            QComboBox {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #555;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #555;
                selection-background-color: #3d6ea5;
                selection-color: #ffffff;
                outline: none;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0;
                margin-right: 8px;
            }
        """)
        disks = get_available_disks()
        self.disk_combo.addItems([f"{d}:" for d in disks])
        
        default_disk = self.config.get_default_disk()
        index = self.disk_combo.findText(f"{default_disk}:")
        if index >= 0:
            self.disk_combo.setCurrentIndex(index)
        
        form_layout.addRow("保存磁盘:", self.disk_combo)
        
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("请输入项目名称")
        form_layout.addRow("项目名称:", self.project_name_edit)
        
        layout.addLayout(form_layout)
        
        self.path_preview = QLabel()
        self.path_preview.setStyleSheet("color: #888; font-size: 11px;")
        self._update_path_preview()
        self.disk_combo.currentTextChanged.connect(self._update_path_preview)
        self.project_name_edit.textChanged.connect(self._update_path_preview)
        layout.addWidget(self.path_preview)
        
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        create_btn = QPushButton("创建")
        create_btn.clicked.connect(self._create_project)
        create_btn.setMinimumWidth(80)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumWidth(80)
        
        button_layout.addWidget(create_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _update_path_preview(self):
        disk = self.disk_combo.currentText()
        project_name = self.project_name_edit.text() or "项目名"
        self.path_preview.setText(f"项目路径: {disk}\\AIVIDEO\\{project_name}")
    
    def _create_project(self):
        project_name = self.project_name_edit.text().strip()
        
        if not project_name:
            QMessageBox.warning(self, "警告", "请输入项目名称")
            return
        
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            if char in project_name:
                QMessageBox.warning(self, "警告", f"项目名称不能包含以下字符: {char}")
                return
        
        disk = self.disk_combo.currentText().replace(":", "")
        self.project_path = f"{disk}:/AIVIDEO/{project_name}"
        self.accept()
    
    def get_project_info(self):
        return {
            "disk": self.disk_combo.currentText().replace(":", ""),
            "name": self.project_name_edit.text().strip(),
            "path": getattr(self, "project_path", "")
        }


class ProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = Config()
        self.project_manager = ProjectManager(self.config)
        self.setWindowTitle("项目管理")
        self.setMinimumSize(600, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()
        self._apply_style()
        self._load_projects()
    
    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QListWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #3d3d3d;
            }
            QListWidget::item:hover {
                background-color: #353535;
            }
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
            QSplitter::handle {
                background-color: #2d2d2d;
            }
            QMessageBox {
                background-color: #1a1a1a;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
            }
            QMessageBox QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
            }
        """)
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("项目列表:"))
        
        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(self._open_selected_project)
        left_layout.addWidget(self.project_list)
        
        list_buttons = QHBoxLayout()
        
        new_btn = QPushButton("新建项目")
        new_btn.clicked.connect(self._new_project)
        
        open_folder_btn = QPushButton("打开文件夹")
        open_folder_btn.clicked.connect(self._open_project_folder)
        
        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(self._delete_project)
        
        list_buttons.addWidget(new_btn)
        list_buttons.addWidget(open_folder_btn)
        list_buttons.addWidget(delete_btn)
        
        left_layout.addLayout(list_buttons)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_layout.addWidget(QLabel("项目信息:"))
        
        self.info_label = QLabel("请选择一个项目")
        self.info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.info_label)
        
        right_layout.addStretch()
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 200])
        
        layout.addWidget(splitter)
        
        self.project_list.currentItemChanged.connect(self._update_info)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        open_btn = QPushButton("打开项目")
        open_btn.clicked.connect(self._open_selected_project)
        open_btn.setMinimumWidth(100)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_btn.setMinimumWidth(80)
        
        button_layout.addWidget(open_btn)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def _load_projects(self):
        self.project_list.clear()
        projects = self.config.get_projects()
        for project_path in projects:
            path = Path(project_path)
            if path.exists():
                item = QListWidgetItem(path.name)
                item.setData(Qt.UserRole, str(path))
                self.project_list.addItem(item)
    
    def _update_info(self, current, previous):
        if current is None:
            self.info_label.setText("请选择一个项目")
            return
        
        project_path = current.data(Qt.UserRole)
        path = Path(project_path)
        
        info_text = f"项目名称: {path.name}\n"
        info_text += f"路径: {project_path}\n\n"
        
        workflows_dir = path / "workflows"
        if workflows_dir.exists():
            workflows = list(workflows_dir.glob("*.json"))
            info_text += f"工作流数量: {len(workflows)}\n"
        
        videos = list(path.glob("*.mp4"))
        if videos:
            info_text += f"视频数量: {len(videos)}"
        
        self.info_label.setText(info_text)
    
    def _new_project(self):
        dialog = NewProjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            info = dialog.get_project_info()
            try:
                self.project_manager.create_project(info["disk"], info["name"])
                self._load_projects()
                QMessageBox.information(self, "成功", f"项目 '{info['name']}' 创建成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建项目失败: {str(e)}")
    
    def _open_project_folder(self):
        current = self.project_list.currentItem()
        if current is None:
            QMessageBox.warning(self, "警告", "请先选择一个项目")
            return
        
        project_path = current.data(Qt.UserRole)
        import subprocess
        import platform
        
        if platform.system() == "Windows":
            subprocess.run(["explorer", project_path])
        elif platform.system() == "Darwin":
            subprocess.run(["open", project_path])
        else:
            subprocess.run(["xdg-open", project_path])
    
    def _delete_project(self):
        current = self.project_list.currentItem()
        if current is None:
            QMessageBox.warning(self, "警告", "请先选择一个项目")
            return
        
        project_path = current.data(Qt.UserRole)
        project_name = Path(project_path).name
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从列表中移除项目 '{project_name}' 吗？\n\n"
            "注意：这只会从列表中移除，不会删除实际文件。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.config.remove_project(project_path)
            self._load_projects()
    
    def _open_selected_project(self, item=None):
        if item is None:
            item = self.project_list.currentItem()
        
        if item is None:
            return
        
        self.selected_project = item.data(Qt.UserRole)
        self.accept()
    
    def get_selected_project(self):
        return getattr(self, "selected_project", None)
