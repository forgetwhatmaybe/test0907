from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from pathlib import Path
import json
from datetime import datetime


class HistoryPanel(QWidget):
    load_requested = pyqtSignal(dict)
    
    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.history_file = self.project_path / "history.json"
        self._init_ui()
        self._load_history()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        header_layout = QHBoxLayout()
        
        title_label = QLabel("生成历史")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        clear_btn.clicked.connect(self._clear_history)
        header_layout.addWidget(clear_btn)
        
        layout.addLayout(header_layout)
        
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #3a3a3a;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #4a4a4a;
            }
        """)
        self.history_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.history_list)
        
        btn_layout = QHBoxLayout()
        
        load_btn = QPushButton("加载配置")
        load_btn.clicked.connect(self._load_selected)
        load_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5CBF60;
            }
        """)
        btn_layout.addWidget(load_btn)
        
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._export_selected)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #31A6FF;
            }
        """)
        btn_layout.addWidget(export_btn)
        
        layout.addLayout(btn_layout)
        
        self.setMinimumWidth(250)
    
    def _load_history(self):
        self.history_list.clear()
        
        if self.history_file.exists():
            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            for item in reversed(history):
                list_item = QListWidgetItem()
                
                timestamp = item.get("timestamp", "")
                node_name = item.get("node_name", "未知")
                model = item.get("model", "未知")
                status = item.get("status", "未知")
                
                text = f"{timestamp}\n节点: {node_name}\n模型: {model}\n状态: {status}"
                list_item.setText(text)
                list_item.setData(Qt.UserRole, item)
                
                self.history_list.addItem(list_item)
    
    def add_history(self, node_name: str, model: str, params: dict, video_path: str, status: str = "成功"):
        history = []
        
        if self.history_file.exists():
            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        
        new_item = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "node_name": node_name,
            "model": model,
            "params": params,
            "video_path": video_path,
            "status": status
        }
        
        history.append(new_item)
        
        if len(history) > 100:
            history = history[-100:]
        
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        
        self._load_history()
    
    def _on_item_double_clicked(self, item):
        self._load_selected()
    
    def _load_selected(self):
        current = self.history_list.currentItem()
        if current:
            data = current.data(Qt.UserRole)
            if data:
                self.load_requested.emit(data.get("params", {}))
    
    def _export_selected(self):
        current = self.history_list.currentItem()
        if current:
            data = current.data(Qt.UserRole)
            if data:
                video_path = data.get("video_path", "")
                if video_path and Path(video_path).exists():
                    save_path, _ = QFileDialog.getSaveFileName(
                        self, "导出视频", 
                        Path(video_path).name,
                        "视频文件 (*.mp4)"
                    )
                    if save_path:
                        import shutil
                        shutil.copy2(video_path, save_path)
                        QMessageBox.information(self, "成功", "视频已导出")
    
    def _clear_history(self):
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有历史记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.history_file.exists():
                self.history_file.unlink()
            self._load_history()
