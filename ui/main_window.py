from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QToolBar, QAction, QLabel, QMessageBox, QFileDialog, QInputDialog
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.project_widget import ProjectWidget
from ui.project_dialog import NewProjectDialog
from ui.api_settings_dialog import APISettingsDialog
from utils.config import Config
from utils.project_manager import ProjectManager
from utils.file_utils import get_available_disks


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.project_manager = ProjectManager(self.config)
        self.editor_window = None
        self.setWindowTitle("AI视频创作工具")
        self.setMinimumSize(1000, 700)
        
        self._init_ui()
        self._init_toolbar()
        self._load_projects()
    
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        
        title_label = QLabel("我的项目")
        title_label.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            color: #e0e0e0;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        hint_label = QLabel("点击项目进入编辑，或新建项目开始创作")
        hint_label.setStyleSheet("""
            color: #888; 
            font-size: 13px;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        """)
        header_layout.addWidget(hint_label)
        
        layout.addLayout(header_layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2a2a2a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a4a;
                border-radius: 5px;
            }
        """)
        
        self.projects_container = QWidget()
        self.projects_layout = QGridLayout(self.projects_container)
        self.projects_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.projects_layout.setSpacing(20)
        self.projects_layout.setContentsMargins(0, 20, 0, 0)
        self._projects_per_row = 4
        
        scroll_area.setWidget(self.projects_container)
        layout.addWidget(scroll_area)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: transparent;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QToolBar {
                background-color: #1a1a1a;
                border: none;
                spacing: 10px;
                padding: 8px;
            }
            QToolBar QToolButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 13px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QToolBar QToolButton:hover {
                background-color: #3d3d3d;
            }
            QToolBar QToolButton:pressed {
                background-color: #4d4d4d;
            }
            QMessageBox {
                background-color: #1a1a1a;
            }
            QMessageBox QLabel {
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QMessageBox QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QMessageBox QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)
    
    def _init_toolbar(self):
        toolbar = self.addToolBar("主工具栏")
        toolbar.setMovable(False)
        
        new_project_action = QAction("➕ 新建项目", self)
        new_project_action.triggered.connect(self._new_project)
        toolbar.addAction(new_project_action)
        
        open_folder_action = QAction("📂 打开文件夹", self)
        open_folder_action.triggered.connect(self._open_aivideo_folder)
        toolbar.addAction(open_folder_action)
        
        toolbar.addSeparator()
        
        settings_action = QAction("⚙️ API设置", self)
        settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(settings_action)
    
    def _load_projects(self):
        for i in reversed(range(self.projects_layout.count())):
            widget = self.projects_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        
        projects = self.config.get_projects()
        
        col = 0
        row = 0
        for project_path in projects:
            path = Path(project_path)
            if path.exists():
                widget = ProjectWidget(project_path)
                widget.clicked.connect(self._open_project)
                widget.delete_requested.connect(self._delete_project)
                widget.icon_imported.connect(lambda p: self._load_projects())
                self.projects_layout.addWidget(widget, row, col)
                col += 1
                if col >= self._projects_per_row:
                    col = 0
                    row += 1
        
        add_btn = QWidget()
        add_btn.setFixedSize(180, 200)
        add_btn_layout = QVBoxLayout(add_btn)
        add_btn_layout.setContentsMargins(10, 10, 10, 10)
        
        add_label = QLabel("➕\n新建项目")
        add_label.setAlignment(Qt.AlignCenter)
        add_label.setStyleSheet("""
            QLabel {
                background-color: #2a2a2a;
                border: 2px dashed #4a4a4a;
                border-radius: 10px;
                color: #888;
                font-size: 16px;
            }
        """)
        add_btn_layout.addWidget(add_label)
        
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.mousePressEvent = lambda e: self._new_project()
        
        self.projects_layout.addWidget(add_btn, row, col)
    
    def _new_project(self):
        dialog = NewProjectDialog(self)
        if dialog.exec_() == NewProjectDialog.Accepted:
            info = dialog.get_project_info()
            try:
                path = self.project_manager.create_project(info["disk"], info["name"])
                
                material_dir = Path(path) / "素材库"
                material_dir.mkdir(exist_ok=True)
                
                self._load_projects()
                QMessageBox.information(self, "成功", f"项目 '{info['name']}' 创建成功")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建项目失败: {str(e)}")
    
    def _open_project(self, project_path: str):
        if hasattr(self, 'editor_window') and self.editor_window is not None:
            self.editor_window.close()
        
        from ui.editor_window import EditorWindow
        
        self.editor_window = EditorWindow(project_path, self)
        self.editor_window.show()
        self.editor_window.raise_()
        self.editor_window.activateWindow()
    
    def _delete_project(self, project_path: str):
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
    
    def _open_aivideo_folder(self):
        disk = self.config.get_default_disk()
        aivideo_path = Path(f"{disk}:/AIVIDEO")
        aivideo_path.mkdir(parents=True, exist_ok=True)
        
        import subprocess
        import platform
        
        if platform.system() == "Windows":
            subprocess.run(["explorer", str(aivideo_path)])
    
    def _open_settings(self):
        dialog = APISettingsDialog(self)
        dialog.exec_()
