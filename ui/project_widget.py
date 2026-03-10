from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QMenu, QAction, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QFont
from pathlib import Path


class ProjectWidget(QWidget):
    clicked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    rename_requested = pyqtSignal(str)
    icon_imported = pyqtSignal(str)  # 图标导入完成信号，传递项目路径
    
    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self.project_path = project_path
        self.project_name = Path(project_path).name
        self._init_ui()
        self._load_thumbnail()
    
    def _init_ui(self):
        self.setFixedSize(180, 200)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(160, 120)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                background-color: #2a2a2a;
                border: 2px solid #3a3a3a;
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.thumbnail_label)
        
        self.name_label = QLabel(self.project_name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("""
            QLabel {
                color: #ddd;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)
        
        self.setStyleSheet("""
            ProjectWidget {
                background-color: #2d2d2d;
                border-radius: 10px;
            }
            ProjectWidget:hover {
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
            }
        """)
    
    def _load_thumbnail(self):
        thumb_path = Path(self.project_path) / "thumbnail.jpg"
        if thumb_path.exists():
            pixmap = QPixmap(str(thumb_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(156, 116, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled)
                self.thumbnail_label.setStyleSheet("""
                    QLabel {
                        background-color: #2a2a2a;
                        border: 2px solid #4CAF50;
                        border-radius: 8px;
                    }
                """)
        else:
            self.thumbnail_label.setText("📁")
            self.thumbnail_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #3a3a3a;
                    border-radius: 8px;
                    font-size: 40px;
                }
            """)
    
    def update_thumbnail(self, image_path: str):
        if image_path and Path(image_path).exists():
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(156, 116, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.thumbnail_label.setPixmap(scaled)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.project_path)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.pos())
    
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
            }
            QMenu::item:selected {
                background-color: #4a4a4a;
            }
        """)
        
        open_action = QAction("📂 打开项目", self)
        open_action.triggered.connect(lambda: self.clicked.emit(self.project_path))
        menu.addAction(open_action)
        
        icon_action = QAction("🖼 导入项目图标", self)
        icon_action.triggered.connect(self._import_project_icon)
        menu.addAction(icon_action)
        
        menu.addSeparator()
        
        delete_action = QAction("🗑 删除项目", self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.project_path))
        menu.addAction(delete_action)
        
        menu.exec_(self.mapToGlobal(pos))
    
    def _import_project_icon(self):
        """导入项目图标，大于512x512时自动压缩"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择项目图标", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        
        try:
            from PIL import Image
            
            # 创建图标文件夹
            icon_dir = Path(self.project_path) / "图标"
            icon_dir.mkdir(exist_ok=True)
            
            # 打开并处理图片
            img = Image.open(file_path)
            
            # 如果图片大于 512x512，等比缩放
            max_size = 512
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)
            
            # 保存为 icon.png
            icon_path = icon_dir / "icon.png"
            # 转为 RGB 再保存（处理 RGBA/P 等模式）
            if img.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', img.size, (42, 42, 42))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img.save(str(icon_path), 'PNG', quality=95)
            
            # 同时保存为项目缩略图 thumbnail.jpg
            thumb_path = Path(self.project_path) / "thumbnail.jpg"
            img.save(str(thumb_path), 'JPEG', quality=90)
            
            # 更新当前显示
            self._load_thumbnail()
            
            # 发射信号通知外部
            self.icon_imported.emit(self.project_path)
            
        except ImportError:
            QMessageBox.warning(self, "错误", "缺少 Pillow 库，请安装: pip install Pillow")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入图标失败: {str(e)}")
    
    def enterEvent(self, event):
        self.setStyleSheet("""
            ProjectWidget {
                background-color: #3a3a3a;
                border: 1px solid #5a5a5a;
                border-radius: 10px;
            }
        """)
    
    def set_loading(self, is_loading: bool):
        """设置项目卡片的加载状态"""
        if is_loading:
            self.name_label.setText(f"⏳ {self.project_name}")
            self.setStyleSheet("""
                ProjectWidget {
                    background-color: #4a4a4a;
                    border: 2px solid #2196F3;
                    border-radius: 10px;
                }
            """)
        else:
            self.name_label.setText(self.project_name)
            self.setStyleSheet("""
                ProjectWidget {
                    background-color: #2d2d2d;
                    border-radius: 10px;
                }
                ProjectWidget:hover {
                    background-color: #3a3a3a;
                    border: 1px solid #4a4a4a;
                }
            """)
    
    def leaveEvent(self, event):
        self.setStyleSheet("""
            ProjectWidget {
                background-color: #2d2d2d;
                border-radius: 10px;
            }
            ProjectWidget:hover {
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
            }
        """)
