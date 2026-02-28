from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtGui import QDrag


class NodePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        title = QLabel("节点列表")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        layout.addWidget(title)
        
        self.node_list = QListWidget()
        self.node_list.setDragEnabled(True)
        self.node_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 8px;
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
        
        nodes = [
            ("图片上传", "image", "上传图片作为输入"),
            ("视频上传", "video", "上传视频文件作为输入"),
            ("可灵生视频", "kling_api", "使用可灵AI生成视频"),
            ("即梦生视频", "jimeng_api", "使用即梦AI生成视频"),
            ("🍌 香蕉生图", "gemini_api", "橙色输入口支持多条连线，最多连14张图片"),
            ("Veo生视频", "veo_api", "向量引擎中转，支持中文提示词自动转英文"),
            ("✏ 图片修改", "image_edit", "可灵扩图 / 即梦超清 / 即梦局部重绘"),
            ("视频(图片)输出", "output", "保存生成的视频或图片，支持链式输出")
        ]
        
        for name, node_type, description in nodes:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, node_type)
            item.setToolTip(description)
            self.node_list.addItem(item)
        
        self.node_list.startDrag = self._start_drag
        layout.addWidget(self.node_list)
        
        hint = QLabel("拖拽节点到画布")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
    
    def _start_drag(self, supportedActions):
        item = self.node_list.currentItem()
        if item is None:
            return
        
        node_type = item.data(Qt.UserRole)
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(node_type)
        drag.setMimeData(mime_data)
        drag.exec_(Qt.CopyAction)
