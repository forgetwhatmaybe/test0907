from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLineEdit, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen, QLinearGradient, QBrush, QPainterPath
from pathlib import Path

from core.node_editor.node_item import NodeItem


class TextDisplayNode(NodeItem):
    """文本显示节点 - 显示生成的文本，支持复制，有执行按钮
    
    连接文本节点的输出，点击执行按钮触发上游文本节点执行。
    执行完成后显示生成的文本。
    """
    node_type = "text_display"
    
    def __init__(self):
        self.display_text = ""
        self._status_color = None
        self._status_timer = None
        self._actual_tokens = 0
        
        super().__init__("文本显示")
        self.add_input("文本")
        self.add_output("文本")
        
        self.on_execute_requested = None
        self._update_size()
    
    def set_execution_status(self, status):
        """设置执行状态，改变节点标题栏颜色
        
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
        
        if status == "success":
            self._status_timer = QTimer()
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self._reset_status_color)
            self._status_timer.start(5000)
        elif status in ("error", "cancelled"):
            self._status_timer = QTimer()
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self._reset_status_color)
            self._status_timer.start(8000)
    
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
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        name_label = QLabel("输出名称:")
        name_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(name_label)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("文本输出名称")
        self.name_edit.setText("text_output")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        layout.addWidget(self.name_edit)
        
        text_label = QLabel("生成文本:")
        text_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(text_label)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setPlaceholderText("执行后显示生成的文本...")
        self.text_display.setMinimumHeight(80)
        self.text_display.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 5px;
                min-height: 80px;
            }
        """)
        layout.addWidget(self.text_display)
        
        token_layout = QHBoxLayout()
        self.token_label = QLabel("Token: 0")
        self.token_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        token_layout.addWidget(self.token_label)
        token_layout.addStretch()
        layout.addLayout(token_layout)
        
        btn_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton("📋 复制")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        self.copy_btn.clicked.connect(self._copy_text)
        btn_layout.addWidget(self.copy_btn)
        
        self.execute_btn = QPushButton("▶ 执行")
        self.execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #43a047;
            }
        """)
        self.execute_btn.clicked.connect(self._on_execute)
        btn_layout.addWidget(self.execute_btn)
        
        layout.addLayout(btn_layout)
    
    def get_output_name(self):
        return self.name_edit.text() or "text_output"
    
    def set_display_text(self, text, tokens=0):
        """设置显示的文本"""
        self.display_text = text
        self._actual_tokens = tokens
        self.text_display.setPlainText(text)
        self.token_label.setText(f"Token: {tokens}")
    
    def get_display_text(self):
        return self.display_text
    
    def set_actual_tokens(self, tokens):
        self._actual_tokens = tokens
        self.token_label.setText(f"Token: {tokens}")
    
    def _copy_text(self):
        """复制文本到剪贴板"""
        if self.display_text:
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(self.display_text)
    
    def _on_execute(self):
        """点击执行按钮"""
        if self.on_execute_requested:
            self.on_execute_requested(self)
    
    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #3d3d3d;
            }
        """)
        
        execute_action = QAction("▶ 执行工作流", menu)
        execute_action.triggered.connect(self._on_execute)
        menu.addAction(execute_action)
        
        if self.display_text:
            copy_action = QAction("📋 复制文本", menu)
            copy_action.triggered.connect(self._copy_text)
            menu.addAction(copy_action)
        
        return menu
    
    def serialize_data(self):
        return {
            "output_name": self.name_edit.text(),
            "display_text": self.display_text,
            "actual_tokens": self._actual_tokens,
        }
    
    def deserialize_data(self, data):
        self.name_edit.setText(data.get("output_name", "text_output"))
        self.display_text = data.get("display_text", "")
        self._actual_tokens = data.get("actual_tokens", 0)
        
        if self.display_text:
            self.text_display.setPlainText(self.display_text)
            self.token_label.setText(f"Token: {self._actual_tokens}")
