from PyQt5.QtWidgets import (
    QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, 
    QTextEdit, QSpinBox, QComboBox, QWidget, QHBoxLayout, QMenu, QAction,
    QGraphicsProxyWidget, QSlider, QGridLayout, QSizePolicy, QDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QUrl, QTimer
from PyQt5.QtGui import QPixmap, QCursor, QStandardItem, QStandardItemModel, QColor, QIcon, QImage, QBrush
from core.node_editor.node_item import NodeItem
from .widgets import ImageThumbnailStrip, DraggableThumbnail
from pathlib import Path
import shutil
import os


class ThumbnailCache:
    """缩略图缓存管理器，避免重复加载和缩放大图片"""
    _cache = {}  # {image_path: QPixmap}
    _max_cache_size = 200
    
    @classmethod
    def get(cls, image_path, width, height):
        """获取缩略图，如果缓存中没有则创建并缓存"""
        cache_key = f"{image_path}_{width}x{height}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        pixmap = cls._load_and_scale(image_path, width, height)
        if pixmap and not pixmap.isNull():
            if len(cls._cache) >= cls._max_cache_size:
                cls._cache.popitem()
            cls._cache[cache_key] = pixmap
        return pixmap
    
    @classmethod
    def _load_and_scale(cls, image_path, width, height):
        """加载图片并缩放，优先使用cv2提高速度"""
        # 方法1: 使用 cv2（支持中文路径）
        try:
            import cv2
            import numpy as np
            # 使用 np.fromfile 读取文件，支持中文路径
            img_array = np.fromfile(str(image_path), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                scale = min(width / w, height / h)
                new_w, new_h = int(w * scale), int(h * scale)
                img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                q_img = QImage(img_rgb.tobytes(), new_w, new_h, new_w * 3, QImage.Format_RGB888).copy()
                return QPixmap.fromImage(q_img)
        except Exception:
            pass
        
        # 方法2: 使用 PIL
        try:
            from PIL import Image
            pil_img = Image.open(image_path)
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')
            pil_img.thumbnail((width, height))
            data = pil_img.tobytes('raw', 'RGB')
            q_img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format_RGB888).copy()
            return QPixmap.fromImage(q_img)
        except Exception:
            pass
        
        # 方法3: 使用 QPixmap
        return QPixmap(image_path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    
    @classmethod
    def clear(cls):
        """清空缓存"""
        cls._cache.clear()
    
    @classmethod
    def invalidate(cls, image_path):
        """清除指定图片路径的所有缓存"""
        keys_to_remove = [k for k in cls._cache if k.startswith(f"{image_path}_")]
        for k in keys_to_remove:
            del cls._cache[k]


class DoubleClickButton(QPushButton):
    """支持双击信号和拖拽文件的 QPushButton"""
    doubleClicked = pyqtSignal()
    drag_started = pyqtSignal(str)  # 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_start_pos = None
        self._file_path = None
        self.setAcceptDrops(True)
    
    def set_file_path(self, path):
        """设置要拖拽的文件路径"""
        self._file_path = path

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        event.accept()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and self._file_path:
            distance = (event.pos() - self._drag_start_pos).manhattanLength()
            if distance >= 10:  # 拖拽阈值
                self._start_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
    
    def _start_drag(self):
        """开始拖拽文件"""
        if not self._file_path or not Path(self._file_path).exists():
            return
        
        from PyQt5.QtCore import QMimeData, QUrl
        from PyQt5.QtGui import QDrag
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # 设置文件 URL
        url = QUrl.fromLocalFile(self._file_path)
        mime_data.setUrls([url])
        
        # 设置文本（用于某些应用）
        mime_data.setText(self._file_path)
        
        drag.setMimeData(mime_data)
        
        # 设置拖拽时的缩略图
        if self.icon():
            drag.setPixmap(self.icon().pixmap(64, 64))
        
        drag.exec_(Qt.CopyAction)


class MaskEditorDialog(QDialog):
    """蒙版绘制对话框 - 左键涂抹（白=255），右键擦除（黑=0）"""

    def __init__(self, image_path, mask_path=None, parent=None):
        super().__init__(parent)
        import cv2
        import numpy as np

        self.image_path = image_path
        self.setWindowTitle("🎨 绘制蒙版")
        self.setModal(True)
        self.setStyleSheet("""
            QDialog { background-color: #1a1a1a; color: #e0e0e0; }
            QLabel  { color: #e0e0e0; }
        """)

        # 用 cv2 加载原图（支持更多格式，支持中文路径）
        import numpy as np
        img_array = np.fromfile(str(image_path), dtype=np.uint8)
        orig_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if orig_bgr is None:
            orig_bgr = np.zeros((300, 400, 3), dtype=np.uint8)
        self._orig_arr = cv2.cvtColor(orig_bgr, cv2.COLOR_BGR2RGB)

        orig_h, orig_w = self._orig_arr.shape[:2]

        # 初始化蒙版（全黑 = 0）
        if mask_path and Path(mask_path).exists():
            mask_array = np.fromfile(str(mask_path), dtype=np.uint8)
            existing = cv2.imdecode(mask_array, cv2.IMREAD_GRAYSCALE)
            if existing is not None and existing.shape == (orig_h, orig_w):
                self._mask_arr = existing.copy()
            else:
                self._mask_arr = np.zeros((orig_h, orig_w), dtype=np.uint8)
        else:
            self._mask_arr = np.zeros((orig_h, orig_w), dtype=np.uint8)

        # 计算显示尺寸（最大 800×600）
        max_dw, max_dh = 800, 600
        scale = min(max_dw / orig_w, max_dh / orig_h, 1.0)
        self._disp_w = max(int(orig_w * scale), 200)
        self._disp_h = max(int(orig_h * scale), 150)
        self._canvas_scale = scale

        # 绘制状态
        self._brush_size = 30   # 显示坐标下的画笔半径（px）
        self._eraser_mode = False
        self._drawing = False
        self._right_erase = False
        self._last_pos = None

        self._setup_ui()
        self._render_canvas()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        hint = QLabel("背景显示原图轮廓，左键涂抹红色区域 = 蒙版255  |  右键擦除")
        hint.setStyleSheet("color: #aaa; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # 画布
        self._canvas = QLabel()
        self._canvas.setFixedSize(self._disp_w, self._disp_h)
        self._canvas.setCursor(Qt.CrossCursor)
        self._canvas.setStyleSheet("background-color: #111; border: 1px solid #444;")
        self._canvas.setMouseTracking(True)
        self._canvas.mousePressEvent  = self._on_press
        self._canvas.mouseMoveEvent   = self._on_move
        self._canvas.mouseReleaseEvent = self._on_release
        layout.addWidget(self._canvas, alignment=Qt.AlignCenter)

        # 控制行
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("画笔大小:"))

        self._brush_slider = QSlider(Qt.Horizontal)
        self._brush_slider.setRange(5, 150)
        self._brush_slider.setValue(self._brush_size)
        self._brush_slider.setFixedWidth(160)
        self._brush_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50; width: 14px; height: 14px;
                border-radius: 7px; margin: -4px 0;
            }
        """)
        self._brush_val_lbl = QLabel(str(self._brush_size))
        self._brush_val_lbl.setFixedWidth(30)
        self._brush_slider.valueChanged.connect(
            lambda v: (setattr(self, '_brush_size', v), self._brush_val_lbl.setText(str(v)))
        )
        ctrl.addWidget(self._brush_slider)
        ctrl.addWidget(self._brush_val_lbl)
        ctrl.addSpacing(15)

        self._eraser_btn = QPushButton("🧹 橡皮擦: 关")
        self._eraser_btn.setCheckable(True)
        self._eraser_btn.setStyleSheet("""
            QPushButton { background:#4a4a4a; color:white; border:none; padding:5px 10px; border-radius:3px; }
            QPushButton:checked { background:#FF9800; }
            QPushButton:hover:!checked { background:#5a5a5a; }
        """)
        self._eraser_btn.toggled.connect(self._on_eraser_toggled)
        ctrl.addWidget(self._eraser_btn)
        ctrl.addSpacing(10)

        clear_btn = QPushButton("🗑 清空")
        clear_btn.setStyleSheet("""
            QPushButton { background:#4a4a4a; color:white; border:none; padding:5px 10px; border-radius:3px; }
            QPushButton:hover { background:#5a5a5a; }
        """)
        clear_btn.clicked.connect(self._clear)
        ctrl.addWidget(clear_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 确认 / 取消
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        ok_btn = QPushButton("✅ 确认")
        ok_btn.setStyleSheet("""
            QPushButton { background:#4CAF50; color:white; border:none;
                          padding:8px 24px; border-radius:4px; font-size:13px; }
            QPushButton:hover { background:#43a047; }
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addSpacing(10)

        cancel_btn = QPushButton("❌ 取消")
        cancel_btn.setStyleSheet("""
            QPushButton { background:#f44336; color:white; border:none;
                          padding:8px 24px; border-radius:4px; font-size:13px; }
            QPushButton:hover { background:#e53935; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ---- 控件回调 ----

    def _on_eraser_toggled(self, checked):
        self._eraser_mode = checked
        self._eraser_btn.setText("🧹 橡皮擦: 开" if checked else "🧹 橡皮擦: 关")

    def _clear(self):
        import numpy as np
        self._mask_arr[:] = 0
        self._render_canvas()

    # ---- 坐标转换 & 绘制 ----

    def _canvas_to_orig(self, mx, my):
        """将画布坐标（显示像素）转换为原图坐标"""
        orig_h, orig_w = self._mask_arr.shape[:2]
        disp_iw = int(orig_w * self._canvas_scale)
        disp_ih = int(orig_h * self._canvas_scale)
        ox = (self._disp_w - disp_iw) // 2
        oy = (self._disp_h - disp_ih) // 2
        ix = (mx - ox) / self._canvas_scale
        iy = (my - oy) / self._canvas_scale
        return ix, iy

    def _do_paint(self, ix, iy, erase=False):
        import cv2
        orig_h, orig_w = self._mask_arr.shape[:2]
        cx = max(0, min(orig_w - 1, int(round(ix))))
        cy = max(0, min(orig_h - 1, int(round(iy))))
        r  = max(1, int(self._brush_size / self._canvas_scale))
        cv2.circle(self._mask_arr, (cx, cy), r, 0 if erase else 255, -1)

    def _do_line(self, ix1, iy1, ix2, iy2, erase=False):
        import cv2
        orig_h, orig_w = self._mask_arr.shape[:2]
        p1 = (max(0, min(orig_w - 1, int(round(ix1)))),
              max(0, min(orig_h - 1, int(round(iy1)))))
        p2 = (max(0, min(orig_w - 1, int(round(ix2)))),
              max(0, min(orig_h - 1, int(round(iy2)))))
        r  = max(1, int(self._brush_size / self._canvas_scale))
        cv2.line(self._mask_arr, p1, p2, 0 if erase else 255, max(1, r * 2))

    # ---- 鼠标事件 ----

    def _on_press(self, event):
        if event.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        self._right_erase = (event.button() == Qt.RightButton)
        self._drawing = True
        ix, iy = self._canvas_to_orig(event.x(), event.y())
        self._do_paint(ix, iy, erase=self._right_erase or self._eraser_mode)
        self._last_pos = (ix, iy)
        self._render_canvas()

    def _on_move(self, event):
        if not self._drawing:
            return
        if not (event.buttons() & (Qt.LeftButton | Qt.RightButton)):
            return
        erase = self._right_erase or self._eraser_mode
        ix, iy = self._canvas_to_orig(event.x(), event.y())
        if self._last_pos:
            self._do_line(self._last_pos[0], self._last_pos[1], ix, iy, erase=erase)
        else:
            self._do_paint(ix, iy, erase=erase)
        self._last_pos = (ix, iy)
        self._render_canvas()

    def _on_release(self, event):
        self._drawing = False
        self._last_pos = None

    # ---- 渲染 ----

    def _render_canvas(self):
        """将原图 + 蒙版叠加渲染到画布 QLabel
        
        显示逻辑：
        - 整个画布显示原图（作为背景，用户可看清轮廓）
        - 蒙版区域：叠加红色高亮（让用户知道涂了哪里）
        - 最终保存的蒙版：涂抹处=255，其他=0
        """
        import cv2
        import numpy as np

        orig_h, orig_w = self._orig_arr.shape[:2]
        disp_iw = max(1, int(orig_w * self._canvas_scale))
        disp_ih = max(1, int(orig_h * self._canvas_scale))
        ox = (self._disp_w - disp_iw) // 2
        oy = (self._disp_h - disp_ih) // 2

        # 缩放到显示尺寸
        scaled = cv2.resize(self._orig_arr, (disp_iw, disp_ih),
                            interpolation=cv2.INTER_AREA).astype(np.float32)
        scaled_mask = cv2.resize(self._mask_arr, (disp_iw, disp_ih),
                                 interpolation=cv2.INTER_NEAREST)

        # 创建画布：整个背景显示原图（半透明效果）
        # 画布背景色（深灰）
        canvas = np.full((self._disp_h, self._disp_w, 3), 40.0, dtype=np.float32)
        
        # 将缩放后的原图放到画布中央
        canvas[oy:oy + disp_ih, ox:ox + disp_iw] = scaled

        # 蒙版区域叠加红色高亮
        # region: H×W×1 float32，蒙版像素=1，其余=0
        region = (scaled_mask > 128)[:, :, np.newaxis].astype(np.float32)
        alpha_mask = 0.55  # 红色叠加不透明度
        red = np.array([[[255.0, 80.0, 80.0]]], dtype=np.float32)  # RGB红

        # 只在图片区域内叠加红色蒙版
        mask_region = canvas[oy:oy + disp_ih, ox:ox + disp_iw]
        mask_region[:, :] = mask_region * (1.0 - region * alpha_mask) + red * (region * alpha_mask)
        canvas[oy:oy + disp_ih, ox:ox + disp_iw] = mask_region

        canvas = np.clip(canvas, 0, 255).astype(np.uint8)

        qimg = QImage(canvas.tobytes(), self._disp_w, self._disp_h,
                      self._disp_w * 3, QImage.Format_RGB888)
        self._canvas.setPixmap(QPixmap.fromImage(qimg))

    def save_mask(self, save_path):
        """将蒙版（灰度，白=255）保存到文件"""
        import cv2
        # 使用 imencode + tofile 保存，支持中文路径
        cv2.imencode('.png', self._mask_arr)[1].tofile(str(save_path))


class ImageNode(NodeItem):
    node_type = "image"
    
    def __init__(self):
        super().__init__("图片上传")
        self.image_path = ""
        self.mask_path = ""
        self._has_mask_output = False
        self.project_path = None
        self.add_output("图片")
        self._update_size()
    
    def set_project_path(self, path):
        self.project_path = Path(path)
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.image_label = QLabel("点击选择图片")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(180, 100)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #2a2a2a;
                border: 2px dashed #555;
                border-radius: 5px;
                color: #888;
            }
        """)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.image_label.mousePressEvent = lambda e: self._select_image()
        layout.addWidget(self.image_label)
        
        self.select_btn = QPushButton("选择图片")
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        self.select_btn.clicked.connect(self._select_image)
        layout.addWidget(self.select_btn)
    
    def load_image_file(self, file_path):
        """加载图片到节点（供拖拽上传调用）"""
        if self.project_path:
            material_dir = self.project_path / "素材库"
            material_dir.mkdir(exist_ok=True)
            file_name = Path(file_path).name
            dest_path = material_dir / file_name
            counter = 1
            while dest_path.exists():
                stem = Path(file_path).stem
                suffix = Path(file_path).suffix
                dest_path = material_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            shutil.copy2(file_path, dest_path)
            self.image_path = str(dest_path)
        else:
            self.image_path = file_path
        self._update_image_display()
        self._notify_downstream_thumbnail_refresh()

    def _select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None, "选择图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            self.load_image_file(file_path)
    
    def _notify_downstream_thumbnail_refresh(self):
        """图片更换后，通知下游节点刷新缩略图（保持现有顺序）"""
        for socket in self.outputs:
            for edge in socket.edges:
                if edge.end_socket:
                    downstream = edge.end_socket.node
                    if hasattr(downstream, '_refresh_thumbnails'):
                        downstream._refresh_thumbnails()
    
    def _update_image_display(self):
        if self.image_path:
            if not Path(self.image_path).exists():
                # 文件不存在，显示丢失提示
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
                return
            pixmap = ThumbnailCache.get(self.image_path, 176, 96)
            if pixmap and not pixmap.isNull():
                self.image_label.setPixmap(pixmap)
                self.image_label.setStyleSheet("""
                    QLabel {
                        background-color: #2a2a2a;
                        border: 2px solid #4CAF50;
                        border-radius: 5px;
                    }
                """)
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
    
    def serialize_data(self):
        return {
            "image_path":      self.image_path,
            "mask_path":       self.mask_path,
            "has_mask_output": self._has_mask_output,
        }
    
    def deserialize_data(self, data):
        self.image_path      = data.get("image_path", "")
        self.mask_path       = data.get("mask_path", "")
        self._has_mask_output = data.get("has_mask_output", False)
        if self._has_mask_output and len(self.outputs) < 2:
            self.add_output("蒙版")
        if self.image_path:
            self._update_image_display()
    
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
        if self.image_path and Path(self.image_path).exists():
            import subprocess
            import platform
            
            file_path = Path(self.image_path).resolve()
            folder_path = file_path.parent
            
            system = platform.system()
            try:
                if system == "Windows":
                    # Windows: 使用 explorer /select 选中文件
                    subprocess.run(["explorer", "/select,", str(file_path)], check=True)
                elif system == "Darwin":
                    # macOS: 使用 open 打开文件夹
                    subprocess.run(["open", str(folder_path)], check=True)
                else:
                    # Linux: 使用 xdg-open 打开文件夹
                    subprocess.run(["xdg-open", str(folder_path)], check=True)
            except Exception as e:
                print(f"打开文件夹失败: {e}")

    def _copy_image_to_clipboard(self):
        """将图片数据复制到系统剪贴板（可粘贴到其他软件中显示图片）"""
        if not self.image_path or not Path(self.image_path).exists():
            return
        from PyQt5.QtWidgets import QApplication
        img = QImage(self.image_path)
        if not img.isNull():
            QApplication.clipboard().setImage(img)

    def _open_mask_editor(self):
        """打开蒙版绘制对话框，确认后为节点增加蒙版输出口"""
        if not self.image_path or not Path(self.image_path).exists():
            return
        dialog = MaskEditorDialog(
            self.image_path,
            self.mask_path if self.mask_path else None
        )
        if dialog.exec_() == QDialog.Accepted:
            # 蒙版保存在图片同目录，命名为 {stem}_mask.png
            img_p = Path(self.image_path)
            mask_save = img_p.parent / f"{img_p.stem}_mask.png"
            dialog.save_mask(str(mask_save))
            self.mask_path = str(mask_save)

            # 首次确认时才添加蒙版输出口
            if not self._has_mask_output:
                self.add_output("蒙版")
                self._has_mask_output = True
                self._update_size()


class KlingAPINode(NodeItem):
    node_type = "kling_api"
    
    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False
        
        super().__init__("可灵生视频")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()
    
    def _setup_sockets(self):
        # 保存第一个输入口的连线信息
        first_input_edges = []
        if self.inputs:
            for edge in self.inputs[0].edges[:]:
                first_input_edges.append(edge.start_socket)
        
        # 删除所有输入口和连线
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()
        
        # 创建新的输入口
        if self.generation_mode == "first_last_frame":
            self.add_input("首帧图片")
            self.add_input("尾帧图片")
        else:
            self.add_input("图片")
        
        if not self.outputs:
            self.add_output("视频")
        
        # 恢复第一个输入口的连线
        if first_input_edges and self.inputs:
            from core.node_editor.edge import Edge
            scene = self.scene()
            if scene:
                for start_socket in first_input_edges:
                    edge = Edge(start_socket, self.inputs[0])
                    scene.addItem(edge)
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        mode_label = QLabel("生成模式:")
        mode_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        # 使用 QStandardItemModel 以支持单独设置每个项的样式
        from PyQt5.QtGui import QStandardItem, QColor
        mode_model = QStandardItemModel()
        item1 = QStandardItem("图生视频")
        item1.setForeground(QColor("#ffffff"))
        mode_model.appendRow(item1)
        item2 = QStandardItem("首尾帧")
        item2.setForeground(QColor("#ffffff"))
        mode_model.appendRow(item2)
        self.mode_combo.setModel(mode_model)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-width: 160px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """)
        layout.addWidget(self.mode_combo)
        
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "kling-v3-omni",
            "kling-v3",
            "kling-video-o1",
            "kling-v2-6",
            "kling-v2-5-turbo",
            "kling-v2-master", "kling-v2-1-master",
            "kling-v2-1", "kling-v2",
            "kling-v1-6", "kling-v1-5", "kling-v1"
        ])
        self.model_combo.currentTextChanged.connect(self._on_kling_model_changed)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """)
        layout.addWidget(self.model_combo)
        
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setMinimumHeight(40)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-height: 40px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        options_layout = QHBoxLayout()
        
        duration_label = QLabel("时长:")
        duration_label.setStyleSheet("color: #aaa; font-size: 11px;")
        options_layout.addWidget(duration_label)
        
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["5s", "10s"])
        self.duration_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        options_layout.addWidget(self.duration_combo)
        
        resolution_label = QLabel("分辨率:")
        resolution_label.setStyleSheet("color: #aaa; font-size: 11px;")
        options_layout.addWidget(resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["720p", "1080p"])
        self.resolution_combo.currentTextChanged.connect(self._on_kling_resolution_changed)
        self.resolution_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        options_layout.addWidget(self.resolution_combo)
        
        layout.addLayout(options_layout)
        
        # cfg_scale 控制
        cfg_layout = QHBoxLayout()
        
        cfg_label = QLabel("CFG Scale:")
        cfg_label.setStyleSheet("color: #aaa; font-size: 11px;")
        cfg_layout.addWidget(cfg_label)
        
        self.cfg_slider = QSlider(Qt.Horizontal)
        self.cfg_slider.setRange(0, 100)
        self.cfg_slider.setValue(50)  # 默认 0.5
        self.cfg_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #3a3a3a;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                width: 12px;
                margin: -3px 0;
                border-radius: 6px;
            }
        """)
        self.cfg_slider.valueChanged.connect(self._on_cfg_changed)
        cfg_layout.addWidget(self.cfg_slider)
        
        self.cfg_value_label = QLabel("0.5")
        self.cfg_value_label.setStyleSheet("color: #aaa; font-size: 11px; min-width: 30px;")
        cfg_layout.addWidget(self.cfg_value_label)
        
        layout.addLayout(cfg_layout)
        
        # 初始化时长选项（根据默认模型）
        self._update_kling_duration_option()
    
    def _on_mode_changed(self, text):
        new_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if new_mode != self.generation_mode:
            self.generation_mode = new_mode
            if self._mode_initialized:
                self._setup_sockets()
                self.update_sockets_position()
                self.update()
    
    def _on_kling_model_changed(self, model):
        """模型变化时更新首尾帧选项和时长选项"""
        self._update_kling_first_last_frame_option()
        self._update_kling_duration_option()
    
    def _on_kling_resolution_changed(self, resolution):
        """分辨率变化时更新首尾帧选项"""
        self._update_kling_first_last_frame_option()
    
    def _update_kling_duration_option(self):
        """根据模型更新时长选项"""
        model = self.model_combo.currentText()
        
        # v3 和 v3-omni 支持 3-15 秒
        if model in ["kling-v3", "kling-v3-omni"]:
            new_durations = [f"{i}s" for i in range(3, 16)]  # 3s, 4s, ..., 15s
        else:
            new_durations = ["5s", "10s"]
        
        # 保存当前选择
        current = self.duration_combo.currentText()
        
        # 更新选项
        self.duration_combo.clear()
        self.duration_combo.addItems(new_durations)
        
        # 尝试恢复之前的选择
        idx = self.duration_combo.findText(current)
        if idx >= 0:
            self.duration_combo.setCurrentIndex(idx)
    
    def _update_kling_first_last_frame_option(self):
        """根据模型和分辨率（模式）控制首尾帧选项的显示"""
        model = self.model_combo.currentText()
        resolution = self.resolution_combo.currentText()
        # 720p = std模式, 1080p = pro模式
        is_pro_mode = (resolution == "1080p")
        
        # 根据能力地图，判断是否支持首尾帧
        # 支持首尾帧的模型（仅pro模式）：
        # kling-v1, kling-v1-5, kling-v1-6, kling-v2-1, kling-v2-5-turbo, kling-v2-6
        # 支持首尾帧的模型（std和pro模式都支持）：
        # kling-video-o1, kling-v3, kling-v3-omni
        # 不支持首尾帧的模型：
        # kling-v2, kling-v2-master, kling-v2-1-master
        
        models_with_first_last_frame_pro_only = [
            "kling-v1", "kling-v1-5", "kling-v1-6",
            "kling-v2-1", "kling-v2-5-turbo", "kling-v2-6"
        ]
        models_with_first_last_frame_always = [
            "kling-video-o1", "kling-v3", "kling-v3-omni"
        ]
        
        combo_model = self.mode_combo.model()
        
        if model in models_with_first_last_frame_always:
            # 始终支持首尾帧
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
        elif model in models_with_first_last_frame_pro_only and is_pro_mode:
            # 仅pro模式支持首尾帧
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
        else:
            # 不支持首尾帧，只显示图生视频
            if self.mode_combo.currentText() == "首尾帧":
                self.mode_combo.setCurrentIndex(0)
            combo_model.item(1).setEnabled(False)
            self.mode_combo.view().setRowHidden(1, True)
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_cfg_changed(self, value):
        cfg_value = value / 100.0
        self.cfg_value_label.setText(f"{cfg_value:.2f}")
    
    def get_params(self):
        cfg_value = self.cfg_slider.value() / 100.0
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText().replace("s", ""),
            "resolution": self.resolution_combo.currentText(),
            "cfg_scale": cfg_value,
            "mode": "pro" if self.resolution_combo.currentText() == "1080p" else "std"
        }
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "generation_mode": self.generation_mode,
            "cfg_scale": self.cfg_slider.value()
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        model_index = self.model_combo.findText(data.get("model", "kling-v1"))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

        duration_index = self.duration_combo.findText(data.get("duration", "5s"))
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)

        resolution_index = self.resolution_combo.findText(data.get("resolution", "720p"))
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)

        mode = data.get("generation_mode", "image_to_video")
        self.mode_combo.setCurrentText("首尾帧" if mode == "first_last_frame" else "图生视频")

        # 恢复 cfg_scale
        cfg_value = data.get("cfg_scale", 50)
        self.cfg_slider.setValue(cfg_value)
        self.cfg_value_label.setText(f"{cfg_value / 100.0:.2f}")


class JimengAPINode(NodeItem):
    node_type = "jimeng_api"
    
    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False
        
        super().__init__("即梦生视频")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()
    
    def _setup_sockets(self):
        # 保存第一个输入口的连线信息
        first_input_edges = []
        if self.inputs:
            for edge in self.inputs[0].edges[:]:
                first_input_edges.append(edge.start_socket)
        
        # 删除所有输入口和连线
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()
        
        # 创建新的输入口
        if self.generation_mode == "first_last_frame":
            self.add_input("首帧图片")
            self.add_input("尾帧图片")
        else:
            self.add_input("图片")
        
        if not self.outputs:
            self.add_output("视频")
        
        # 恢复第一个输入口的连线
        if first_input_edges and self.inputs:
            from core.node_editor.edge import Edge
            scene = self.scene()
            if scene:
                for start_socket in first_input_edges:
                    edge = Edge(start_socket, self.inputs[0])
                    scene.addItem(edge)
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        mode_label = QLabel("生成模式:")
        mode_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(mode_label)
        
        self.mode_combo = QComboBox()
        # 使用 QStandardItemModel 以支持单独设置每个项的样式
        mode_model = QStandardItemModel()
        item1 = QStandardItem("图生视频")
        item1.setForeground(QColor("#ffffff"))
        mode_model.appendRow(item1)
        item2 = QStandardItem("首尾帧")
        item2.setForeground(QColor("#ffffff"))
        mode_model.appendRow(item2)
        self.mode_combo.setModel(mode_model)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-width: 160px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """)
        layout.addWidget(self.mode_combo)
        
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems(["jimeng_v1", "jimeng_v2", "jimeng_v30", "jimeng_v30_pro"])
        self.model_combo.currentTextChanged.connect(self._on_jimeng_model_changed)
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """)
        layout.addWidget(self.model_combo)
        
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述视频内容...")
        self.prompt_edit.setMinimumHeight(40)
        self.prompt_edit.textChanged.connect(self._on_prompt_changed)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-height: 40px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        self.resolution_label = QLabel("分辨率:")
        self.resolution_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["720P", "1080P"])
        self.resolution_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        layout.addWidget(self.resolution_combo)
        
        duration_label = QLabel("时长:")
        duration_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(duration_label)
        
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["5s", "10s"])
        self.duration_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        layout.addWidget(self.duration_combo)
        
        # seed 参数 - 左对齐
        seed_layout = QHBoxLayout()
        
        seed_label = QLabel("Seed:")
        seed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        seed_layout.addWidget(seed_label)
        
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 2147483647)
        self.seed_spin.setValue(-1)
        self.seed_spin.setStyleSheet("""
            QSpinBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
        """)
        seed_layout.addWidget(self.seed_spin)
        
        seed_hint = QLabel("(-1随机)")
        seed_hint.setStyleSheet("color: #666; font-size: 10px;")
        seed_layout.addWidget(seed_hint)
        
        seed_layout.addStretch()
        layout.addLayout(seed_layout)
        
        self._on_jimeng_model_changed(self.model_combo.currentText())
    
    def _on_mode_changed(self, text):
        new_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if new_mode != self.generation_mode:
            self.generation_mode = new_mode
            if self._mode_initialized:
                self._setup_sockets()
                self.update_sockets_position()
                self.update()
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_jimeng_model_changed(self, model):
        """根据模型类型控制首尾帧模式和分辨率选择的可用性"""
        combo_model = self.mode_combo.model()
        
        if model == "jimeng_v30_pro":
            if self.mode_combo.currentText() == "首尾帧":
                self.mode_combo.setCurrentIndex(0)
            combo_model.item(1).setEnabled(False)
            self.mode_combo.view().setRowHidden(1, True)
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.hide()
            self.resolution_label.hide()
        elif model == "jimeng_v30":
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
            self.resolution_combo.setEnabled(True)
            self.resolution_combo.show()
            self.resolution_label.show()
        else:
            combo_model.item(1).setEnabled(True)
            self.mode_combo.view().setRowHidden(1, False)
            self.resolution_combo.setEnabled(False)
            self.resolution_combo.hide()
            self.resolution_label.hide()
    
    def get_params(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "video_duration": int(self.duration_combo.currentText().replace("s", "")),
            "fps": 24,
            "seed": self.seed_spin.value(),
            "resolution": self.resolution_combo.currentText()
        }
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "duration": self.duration_combo.currentText(),
            "fps": "24fps",
            "seed": self.seed_spin.value(),
            "generation_mode": self.generation_mode,
            "resolution": self.resolution_combo.currentText()
        }

    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        model_index = self.model_combo.findText(data.get("model", "jimeng_v1"))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)

        duration_index = self.duration_combo.findText(data.get("duration", "5s"))
        if duration_index >= 0:
            self.duration_combo.setCurrentIndex(duration_index)

        self.seed_spin.setValue(data.get("seed", -1))

        mode = data.get("generation_mode", "image_to_video")
        self.mode_combo.setCurrentText("首尾帧" if mode == "first_last_frame" else "图生视频")

        resolution = data.get("resolution", "720P")
        resolution_index = self.resolution_combo.findText(resolution)
        if resolution_index >= 0:
            self.resolution_combo.setCurrentIndex(resolution_index)


class GeminiAPINode(NodeItem):
    """香蕉生图节点 — Gemini (Nano Banana) 图片生成
    
    单个橙色输入接口支持同时连接多个图片上传节点（最多14张参考图片）。
    输出为生成的图片，可连接到可灵/即梦生视频节点或视频输出节点。
    支持动态文本输入口，接收文本节点的输出。
    """
    node_type = "gemini_api"
    
    def __init__(self):
        self.generated_image_path = ""  # 生成的图片路径，供下游节点读取
        self._image_order = []  # 用户自定义的图片node_id顺序
        self._upper_text = ""  # 上方输入的文本
        self._show_text_input = False  # 是否显示文本输入口
        self._text_input_socket = None  # 文本输入socket引用
        self._thumbnails_expanded = True
        
        super().__init__("香蕉生图")
        self.add_multi_input("参考图片")  # 橙色多连接输入
        self.add_output("图片")
        
        # 连接 socket 信号以自动更新缩略图
        if self.inputs:
            self.inputs[0].signals.connected.connect(self._on_edge_changed)
            self.inputs[0].signals.disconnected.connect(self._on_edge_changed)
        
        self._add_toggle_button()
        self._update_size()
    
    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        _combo_style = """
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """
        
        # ---- 模型选择 ----
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview",
            "gemini-2.5-flash-preview-image-generation",
            "gemini-2.0-flash-preview-image-generation",
        ])
        self.model_combo.setStyleSheet(_combo_style)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)
        
        # ---- 参考图片缩略图条（可拖拽排序） ----
        self.thumb_label = QLabel("参考图片:")
        self.thumb_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.thumb_label.hide()
        layout.addWidget(self.thumb_label)
        
        self.thumbnail_strip = ImageThumbnailStrip()
        self.thumbnail_strip.order_changed.connect(self._on_image_order_changed)
        layout.addWidget(self.thumbnail_strip)
        
        # ---- 提示词 ----
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("描述要生成的图片内容...")
        self.prompt_edit.setFixedHeight(80)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        # ---- 宽高比 ----
        ar_layout = QHBoxLayout()
        
        ar_label = QLabel("宽高比:")
        ar_label.setStyleSheet("color: #aaa; font-size: 11px;")
        ar_layout.addWidget(ar_label)
        
        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItems([
            "16:9", "1:1", "2:3", "3:2", "3:4", "4:3",
            "4:5", "5:4", "9:16", "21:9"
        ])
        self.aspect_ratio_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        ar_layout.addWidget(self.aspect_ratio_combo)
        layout.addLayout(ar_layout)
        
        # ---- 输出分辨率（仅 Pro 模型） ----
        self.resolution_layout = QHBoxLayout()
        
        self.resolution_label = QLabel("分辨率:")
        self.resolution_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.resolution_layout.addWidget(self.resolution_label)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1K", "2K", "4K"])
        self.resolution_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 3px;
            }
        """)
        self.resolution_layout.addWidget(self.resolution_combo)
        layout.addLayout(self.resolution_layout)
        
        # 默认选中 2K 分辨率
        self.resolution_combo.setCurrentIndex(1)  # "2K"
        
        # 默认模型是 3.1 flash，显示分辨率选项
        model_lower = self.model_combo.currentText().lower()
        self._set_resolution_visible("pro" in model_lower or "3.1-flash" in model_lower)
        
        # ---- 输入提示词接口按钮 ----
        self.text_input_btn = QPushButton("📝 输入提示词接口")
        self.text_input_btn.setCheckable(True)
        self.text_input_btn.setChecked(self._show_text_input)
        self.text_input_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #8B0000;
                border-color: #ff4444;
            }
        """)
        self.text_input_btn.clicked.connect(self._toggle_text_input)
        layout.addWidget(self.text_input_btn)
    
    def _toggle_text_input(self):
        """切换文本输入口的显示状态"""
        self._show_text_input = not self._show_text_input
        
        if self._show_text_input:
            self._add_text_input_socket()
        else:
            self._remove_text_input_socket()
        
        self._update_size()
    
    def _add_text_input_socket(self):
        """添加红色文本输入口（在节点最下面）"""
        if self._text_input_socket is not None:
            return
        
        from core.node_editor.node_item import Socket
        socket = Socket(self, "input", len(self.inputs), multi_input=False)
        socket.setParentItem(self)  # 关键：设置父项才能显示
        socket.color = QColor("#FF4444")
        socket.setBrush(QBrush(socket.color))
        self.inputs.append(socket)
        self._text_input_socket = socket
        
        self._update_size()
        # 延迟定位，确保节点尺寸已更新
        QTimer.singleShot(10, self._position_text_input_socket)
    
    def _remove_text_input_socket(self):
        """移除文本输入口"""
        if self._text_input_socket is None:
            return
        
        socket = self._text_input_socket
        for edge in socket.edges[:]:
            edge.remove()
        
        if socket in self.inputs:
            self.inputs.remove(socket)
        
        socket.setParentItem(None)
        if socket.scene():
            socket.scene().removeItem(socket)
        
        self._text_input_socket = None
        
        self._update_size()
    
    def _position_text_input_socket(self):
        """将文本输入口定位到节点最下面（独立于其他socket）"""
        if self._text_input_socket is None:
            return
        
        socket = self._text_input_socket
        # 定位到节点底部左侧
        socket.setPos(-socket.radius, self.height - 25)
    
    def _on_model_changed(self, model_name):
        """模型切换时显示/隐藏分辨率选项"""
        # Pro 模型和 3.1 flash 模型支持分辨率选项
        is_pro = "pro" in model_name.lower() or "3.1-flash" in model_name.lower()
        self._set_resolution_visible(is_pro)
        self._update_size()
    
    def _set_resolution_visible(self, visible):
        """设置分辨率选择器的可见性"""
        self.resolution_label.setVisible(visible)
        self.resolution_combo.setVisible(visible)
    
    def _on_prompt_changed(self):
        doc = self.prompt_edit.document()
        text_width = self.prompt_edit.width() - 10 if self.prompt_edit.width() > 10 else 195
        doc.setTextWidth(text_width)
        new_height = int(doc.size().height()) + 10
        self.prompt_edit.setMinimumHeight(max(40, new_height))
        self._update_size()
    
    def _on_edge_changed(self, edge=None):
        """输入边连接或断开时，刷新缩略图条"""
        QTimer.singleShot(0, self._refresh_thumbnails)
    
    def _refresh_thumbnails(self):
        """从当前连接收集图片并更新缩略图条"""
        connected_items = []
        # 跳过文本输入口（如果存在），处理图片输入
        start_idx = 1 if self._text_input_socket and len(self.inputs) > 1 else 0
        for socket in self.inputs[start_idx:]:
            for edge in socket.edges:
                if edge.start_socket:
                    src_node = edge.start_socket.node
                    img_path = ""
                    if src_node.node_type == "image":
                        img_path = getattr(src_node, 'image_path', '')
                    elif src_node.node_type == "gemini_api":
                        img_path = getattr(src_node, 'generated_image_path', '')
                    elif src_node.node_type == "output":
                        img_path = getattr(src_node, 'video_path', '')
                    elif src_node.node_type == "image_edit":
                        img_path = getattr(src_node, '_result_path', '')
                    if img_path and Path(img_path).exists():
                        connected_items.append((src_node.id, img_path))
        
        self.thumbnail_strip.update_thumbnails(connected_items)
        has_images = len(connected_items) > 0
        self.thumb_label.setVisible(has_images and self._thumbnails_expanded)
        self.thumbnail_strip.setVisible(self._thumbnails_expanded)
        self._update_size()
    
    def _on_toggle_clicked(self):
        """展开/收起缩略图区域"""
        self._thumbnails_expanded = not self._thumbnails_expanded
        has_images = self.thumbnail_strip and len(self.thumbnail_strip._ordered_items) > 0
        self.thumb_label.setVisible(has_images and self._thumbnails_expanded)
        self.thumbnail_strip.setVisible(self._thumbnails_expanded)
        self._update_size()
    
    def get_upper_text(self):
        """获取文本输入口连接的文本"""
        if not self._text_input_socket:
            return ""
        for edge in self._text_input_socket.edges:
            if edge.start_socket:
                src_node = edge.start_socket.node
                if src_node.node_type == "text_vision":
                    return getattr(src_node, 'generated_text', '')
                elif src_node.node_type == "text_display":
                    return getattr(src_node, 'display_text', '')
        return ""
    
    def _on_image_order_changed(self):
        """用户拖拽改变了图片顺序"""
        self._image_order = self.thumbnail_strip.get_ordered_node_ids()
        self._update_size()
    
    def get_ordered_image_paths(self):
        """获取用户排序后的图片路径列表（执行时使用）"""
        return self.thumbnail_strip.get_ordered_image_paths()
    
    def get_ordered_node_ids(self):
        """获取用户排序后的节点ID列表（执行时使用）"""
        return self._image_order if self._image_order else self.thumbnail_strip.get_ordered_node_ids()
    
    def _restore_image_order(self):
        """边恢复后，根据保存的顺序重排缩略图"""
        if self._image_order:
            self._refresh_thumbnails()
            self.thumbnail_strip.set_order(self._image_order)
    
    def get_params(self):
        params = {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
        }
        # Pro 模型和 3.1 flash 模型传递分辨率（API 需要 "1K"/"2K"/"4K" 大写字符串）
        model_lower = params["model"].lower()
        if "pro" in model_lower or "3.1-flash" in model_lower:
            params["image_size"] = self.resolution_combo.currentText()  # "1K"/"2K"/"4K"
        return params
    
    def set_generated_image(self, image_path):
        """记录生成的图片路径（供下游节点读取，不在节点上显示预览）"""
        self.generated_image_path = image_path
    
    def serialize_data(self):
        return {
            "prompt": self.prompt_edit.toPlainText(),
            "model": self.model_combo.currentText(),
            "aspect_ratio": self.aspect_ratio_combo.currentText(),
            "resolution": self.resolution_combo.currentText(),
            "generated_image_path": self.generated_image_path,
            "image_order": self.thumbnail_strip.get_ordered_node_ids(),
            "show_text_input": self._show_text_input,
        }
    
    def deserialize_data(self, data):
        self.prompt_edit.setPlainText(data.get("prompt", ""))
        
        model_index = self.model_combo.findText(data.get("model", ""))
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        
        ar_index = self.aspect_ratio_combo.findText(data.get("aspect_ratio", "1:1"))
        if ar_index >= 0:
            self.aspect_ratio_combo.setCurrentIndex(ar_index)
        
        # 兼容旧格式 ("1024 (1K)"/"2048 (2K)"/"4096 (4K)"/"1024"/"2048"/"4096") 统一映射到新格式
        _res_compat = {
            "1024 (1K)": "1K", "1024": "1K",
            "2048 (2K)": "2K", "2048": "2K",
            "4096 (4K)": "4K", "4096": "4K",
        }
        raw_res = data.get("resolution", "2K")
        res_val = _res_compat.get(raw_res, raw_res)  # 新格式直接透传
        res_index = self.resolution_combo.findText(res_val)
        if res_index >= 0:
            self.resolution_combo.setCurrentIndex(res_index)
        
        self.generated_image_path = data.get("generated_image_path", "")
        if self.generated_image_path and Path(self.generated_image_path).exists():
            self.set_generated_image(self.generated_image_path)
        
        # 恢复图片顺序（需要在连线恢复后调用 _refresh_thumbnails）
        self._image_order = data.get("image_order", [])
        
        # 恢复文本输入口状态
        if data.get("show_text_input", False):
            self._show_text_input = True
            self._add_text_input_socket()
            self.text_input_btn.setChecked(True)


class ImageEditNode(NodeItem):
    """图片修改节点：可灵扩图 / 即梦超清 / 即梦局部重绘"""
    node_type = "image_edit"

    MODES = ["可灵扩图", "即梦超清", "即梦局部重绘"]

    def __init__(self):
        self.edit_mode = "可灵扩图"
        self._mode_initialized = False
        super().__init__("图片修改")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()

    def _setup_sockets(self):
        # 保存第一个输入口的连线信息
        first_input_edges = []
        if self.inputs:
            for edge in self.inputs[0].edges[:]:
                first_input_edges.append(edge.start_socket)
        
        # 清除旧的输入 socket
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()

        if self.edit_mode == "即梦局部重绘":
            self.add_input("原图")
            self.add_input("遮罩")
        else:
            self.add_input("图片")

        if not self.outputs:
            self.add_output("图片")
        
        # 恢复第一个输入口的连线
        if first_input_edges and self.inputs:
            from core.node_editor.edge import Edge
            scene = self.scene()
            if scene:
                for start_socket in first_input_edges:
                    edge = Edge(start_socket, self.inputs[0])
                    scene.addItem(edge)

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # --- 模式选择 ---
        mode_label = QLabel("编辑模式:")
        mode_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(self.MODES)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a; color: white;
                border: 1px solid #444; border-radius: 3px; padding: 4px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a; color: white;
                selection-background-color: #4a4a4a;
            }
        """)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        # --- 可灵扩图参数面板 ---
        self.expand_widget = QWidget()
        expand_layout = QVBoxLayout(self.expand_widget)
        expand_layout.setContentsMargins(0, 0, 0, 0)
        expand_layout.setSpacing(2)

        dir_label = QLabel("扩展比例 (0~2.0):")
        dir_label.setStyleSheet("color: #aaa; font-size: 10px;")
        expand_layout.addWidget(dir_label)

        self._expand_sliders = {}
        for direction, zh in [("up", "上"), ("down", "下"), ("left", "左"), ("right", "右")]:
            row = QHBoxLayout()
            lbl = QLabel(f"{zh}:")
            lbl.setFixedWidth(20)
            lbl.setStyleSheet("color: #ccc; font-size: 11px;")
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(0)
            slider.setStyleSheet("QSlider::handle:horizontal { background: #4CAF50; width: 12px; }")
            val_lbl = QLabel("0.0")
            val_lbl.setFixedWidth(30)
            val_lbl.setStyleSheet("color: #4CAF50; font-size: 11px;")
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(f"{v / 100:.1f}"))
            slider.valueChanged.connect(self._update_expand_warning)
            self._expand_sliders[direction] = slider
            row.addWidget(lbl)
            row.addWidget(slider)
            row.addWidget(val_lbl)
            expand_layout.addLayout(row)

        # 面积超限警告标签
        self._expand_warn_label = QLabel()
        self._expand_warn_label.setWordWrap(True)
        self._expand_warn_label.setStyleSheet("color: #FF6B6B; font-size: 10px;")
        self._expand_warn_label.hide()
        expand_layout.addWidget(self._expand_warn_label)

        layout.addWidget(self.expand_widget)

        # --- 即梦超清参数面板 ---
        self.sr_widget = QWidget()
        sr_layout = QVBoxLayout(self.sr_widget)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        sr_layout.setSpacing(2)

        res_label = QLabel("目标分辨率:")
        res_label.setStyleSheet("color: #aaa; font-size: 11px;")
        sr_layout.addWidget(res_label)
        self.sr_resolution_combo = QComboBox()
        self.sr_resolution_combo.addItems(["4k", "8k"])
        self.sr_resolution_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: white; border: 1px solid #444; border-radius: 3px; padding: 4px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2a2a2a; color: white; selection-background-color: #4a4a4a; }
        """)
        sr_layout.addWidget(self.sr_resolution_combo)

        scale_label = QLabel("锐化强度 (0-100):")
        scale_label.setStyleSheet("color: #aaa; font-size: 11px;")
        sr_layout.addWidget(scale_label)
        scale_row = QHBoxLayout()
        self.sr_scale_slider = QSlider(Qt.Horizontal)
        self.sr_scale_slider.setRange(0, 100)
        self.sr_scale_slider.setValue(50)
        self.sr_scale_slider.setStyleSheet("QSlider::handle:horizontal { background: #2196F3; width: 12px; }")
        self.sr_scale_val = QLabel("50")
        self.sr_scale_val.setFixedWidth(30)
        self.sr_scale_val.setStyleSheet("color: #2196F3; font-size: 11px;")
        self.sr_scale_slider.valueChanged.connect(lambda v: self.sr_scale_val.setText(str(v)))
        scale_row.addWidget(self.sr_scale_slider)
        scale_row.addWidget(self.sr_scale_val)
        sr_layout.addLayout(scale_row)
        layout.addWidget(self.sr_widget)

        # --- 即梦局部重绘参数面板 ---
        self.inpaint_widget = QWidget()
        inpaint_layout = QVBoxLayout(self.inpaint_widget)
        inpaint_layout.setContentsMargins(0, 0, 0, 0)
        inpaint_layout.setSpacing(2)

        seed_label = QLabel("种子 (Seed):")
        seed_label.setStyleSheet("color: #aaa; font-size: 11px;")
        inpaint_layout.addWidget(seed_label)
        self.inpaint_seed_spin = QSpinBox()
        self.inpaint_seed_spin.setRange(-1, 999999)
        self.inpaint_seed_spin.setValue(101)
        self.inpaint_seed_spin.setStyleSheet("""
            QSpinBox { background-color: #2a2a2a; color: white; border: 1px solid #444; border-radius: 3px; padding: 4px; }
        """)
        inpaint_layout.addWidget(self.inpaint_seed_spin)
        layout.addWidget(self.inpaint_widget)

        # --- 提示词（可灵扩图 / 即梦局部重绘共用） ---
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMaximumHeight(60)
        self.prompt_edit.setPlaceholderText("可选提示词 (扩图/重绘)")
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a; color: white;
                border: 1px solid #444; border-radius: 3px; padding: 4px;
            }
        """)
        layout.addWidget(self.prompt_edit)

        # 初始化显示状态
        self._toggle_panels()

    def _on_mode_changed(self, mode_text):
        self.edit_mode = mode_text
        self._toggle_panels()
        if self._mode_initialized:
            self._setup_sockets()
        self._update_size()

    def _toggle_panels(self):
        """根据模式显示/隐藏对应的参数面板"""
        self.expand_widget.setVisible(self.edit_mode == "可灵扩图")
        self.sr_widget.setVisible(self.edit_mode == "即梦超清")
        self.inpaint_widget.setVisible(self.edit_mode == "即梦局部重绘")
        # 超清不需要提示词
        self.prompt_edit.setVisible(self.edit_mode != "即梦超清")

    def _update_expand_warning(self):
        """实时计算扩图面积倍数，超过 3 倍则显示红色警告"""
        up   = self._expand_sliders["up"].value() / 100.0
        down = self._expand_sliders["down"].value() / 100.0
        left = self._expand_sliders["left"].value() / 100.0
        right= self._expand_sliders["right"].value() / 100.0
        area_mult = (1 + up + down) * (1 + left + right)
        if area_mult > 3.0:
            self._expand_warn_label.setText(
                f"⚠ 面积 {area_mult:.1f}x > 3x，执行时将自动裁剪"
            )
            self._expand_warn_label.show()
        else:
            self._expand_warn_label.hide()
        self._update_size()

    def get_params(self):
        params = {"mode": self.edit_mode}
        if self.edit_mode == "可灵扩图":
            params["up_expansion_ratio"] = self._expand_sliders["up"].value() / 100.0
            params["down_expansion_ratio"] = self._expand_sliders["down"].value() / 100.0
            params["left_expansion_ratio"] = self._expand_sliders["left"].value() / 100.0
            params["right_expansion_ratio"] = self._expand_sliders["right"].value() / 100.0
            params["prompt"] = self.prompt_edit.toPlainText().strip()
        elif self.edit_mode == "即梦超清":
            params["resolution"] = self.sr_resolution_combo.currentText()
            params["scale"] = self.sr_scale_slider.value()
        elif self.edit_mode == "即梦局部重绘":
            params["prompt"] = self.prompt_edit.toPlainText().strip()
            params["seed"] = self.inpaint_seed_spin.value()
        return params

    def serialize_data(self):
        data = {
            "edit_mode": self.edit_mode,
            "prompt": self.prompt_edit.toPlainText(),
            "up_ratio": self._expand_sliders["up"].value(),
            "down_ratio": self._expand_sliders["down"].value(),
            "left_ratio": self._expand_sliders["left"].value(),
            "right_ratio": self._expand_sliders["right"].value(),
            "sr_resolution": self.sr_resolution_combo.currentText(),
            "sr_scale": self.sr_scale_slider.value(),
            "inpaint_seed": self.inpaint_seed_spin.value(),
        }
        return data

    def deserialize_data(self, data):
        mode = data.get("edit_mode", "可灵扩图")
        idx = self.mode_combo.findText(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.prompt_edit.setPlainText(data.get("prompt", ""))
        self._expand_sliders["up"].setValue(data.get("up_ratio", 0))
        self._expand_sliders["down"].setValue(data.get("down_ratio", 0))
        self._expand_sliders["left"].setValue(data.get("left_ratio", 0))
        self._expand_sliders["right"].setValue(data.get("right_ratio", 0))

        sr_res_idx = self.sr_resolution_combo.findText(data.get("sr_resolution", "4k"))
        if sr_res_idx >= 0:
            self.sr_resolution_combo.setCurrentIndex(sr_res_idx)
        self.sr_scale_slider.setValue(data.get("sr_scale", 50))
        self.inpaint_seed_spin.setValue(data.get("inpaint_seed", 101))


# =========================================================================== #
#  VeoAPINode  — Veo3 生视频节点
# =========================================================================== #

class VeoAPINode(NodeItem):
    """Veo3 生视频节点

    支持多种模型：
      - veo2, veo2-fast, veo2-pro
      - veo2-fast-frames (首尾帧, 最多2张图)
      - veo2-fast-components (最多3张元素图)
      - veo3, veo3-fast, veo3-pro
      - veo3-pro-frames (首帧, 最多1张图)
      - veo3-fast-frames, veo3-frames

    特性：
      - 支持中文提示词自动转英文
      - 支持图片输入（图生视频/首尾帧）
      - 支持视频超分
      - 支持动态文本输入口
    """
    node_type = "veo_api"

    def __init__(self):
        self.generation_mode = "image_to_video"
        self._mode_initialized = False
        self._upper_text = ""
        self._show_text_input = False  # 是否显示文本输入口
        self._text_input_socket = None  # 文本输入socket引用

        super().__init__("Veo生视频")
        self._mode_initialized = True
        self._setup_sockets()
        self._update_size()

    def _setup_sockets(self):
        """根据当前模式重建输入 socket"""
        first_input_edges = []
        if self.inputs:
            # 保存图片输入口的连线（跳过文本输入口）
            start_idx = 1 if self._text_input_socket and len(self.inputs) > 1 else 0
            for socket in self.inputs[start_idx:]:
                for edge in socket.edges[:]:
                    first_input_edges.append(edge.start_socket)
        
        # 清除所有输入socket
        for socket in self.inputs[:]:
            for edge in socket.edges[:]:
                edge.remove()
            socket.setParentItem(None)
            if socket.scene():
                socket.scene().removeItem(socket)
        self.inputs.clear()
        self._text_input_socket = None  # 清除引用
        
        # 先添加图片输入口
        if self.generation_mode == "first_last_frame":
            self.add_input("首帧图片")
            self.add_input("尾帧图片")
        else:
            self.add_input("图片")

        # 如果需要显示文本输入口，添加到最下面
        if self._show_text_input:
            from core.node_editor.node_item import Socket
            socket = Socket(self, "input", len(self.inputs), multi_input=False)
            socket.setParentItem(self)  # 关键：设置父项才能显示
            socket.color = QColor("#FF4444")
            socket.setBrush(QBrush(socket.color))
            self.inputs.append(socket)
            self._text_input_socket = socket

        if not self.outputs:
            self.add_output("视频")
        
        # 恢复图片输入口的连线
        if first_input_edges:
            from core.node_editor.edge import Edge
            scene = self.scene()
            if scene:
                for i, start_socket in enumerate(first_input_edges):
                    if i < len(self.inputs):
                        edge = Edge(start_socket, self.inputs[i])
                        scene.addItem(edge)
        
        self.update_sockets_position()
        
        # 延迟定位文本输入口到节点底部
        if self._text_input_socket:
            QTimer.singleShot(10, self._position_text_input_socket_for_veo)

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        _combo_style = """
            QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
                min-width: 160px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: white;
                selection-background-color: #4a4a4a;
                border: 1px solid #444;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }
        """

        # ---- 生成模式 ----
        mode_label = QLabel("生成模式:")
        mode_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["图生视频", "首尾帧"])
        self.mode_combo.setStyleSheet(_combo_style)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        # ---- 模型 ----
        model_label = QLabel("模型:")
        model_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "veo_3_1",
            "veo3.1",
            "veo3.1-fast",
            "veo3.1-pro",
            "veo3.1-4k",
            "veo3.1-pro-4k",
            "veo3",
            "veo3-pro",
            "veo3-fast",
            "veo3-fast-frames",
            "veo3-frames",
            "veo3-pro-frames",
            "veo2-pro",
            "veo2-fast",
            "veo2-fast-frames",
            "veo2-fast-components",
            "veo2-pro-components",
            "veo_3_1-fast"
        ])
        self.model_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.model_combo)

        # ---- 宽高比 (仅 veo3) ----
        ar_label = QLabel("宽高比 (Veo3):")
        ar_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(ar_label)

        self.ar_combo = QComboBox()
        self.ar_combo.addItems(["16:9", "9:16"])
        self.ar_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.ar_combo)

        # ---- 增强提示词 ----
        enhance_label = QLabel("中文转英文:")
        enhance_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(enhance_label)

        self.enhance_combo = QComboBox()
        self.enhance_combo.addItems(["是", "否"])
        self.enhance_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.enhance_combo)

        # ---- 超分 ----
        upsample_label = QLabel("视频超分:")
        upsample_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(upsample_label)

        self.upsample_combo = QComboBox()
        self.upsample_combo.addItems(["是", "否"])
        self.upsample_combo.setStyleSheet(_combo_style)
        layout.addWidget(self.upsample_combo)

        # ---- 提示词 ----
        prompt_label = QLabel("提示词:")
        prompt_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(prompt_label)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("支持中文，自动转英文…")
        self.prompt_edit.setFixedHeight(80)
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #666;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        layout.addWidget(self.prompt_edit)
        
        # ---- 输入提示词接口按钮 ----
        self.text_input_btn = QPushButton("📝 输入提示词接口")
        self.text_input_btn.setCheckable(True)
        self.text_input_btn.setChecked(self._show_text_input)
        self.text_input_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #8B0000;
                border-color: #ff4444;
            }
        """)
        self.text_input_btn.clicked.connect(self._toggle_text_input)
        layout.addWidget(self.text_input_btn)
    
    def _toggle_text_input(self):
        """切换文本输入口的显示状态"""
        self._show_text_input = not self._show_text_input
        self._setup_sockets()
        self._update_size()
    
    def _position_text_input_socket_for_veo(self):
        """将文本输入口定位到节点最下面（VeoAPINode专用）"""
        if self._text_input_socket is None:
            return
        
        socket = self._text_input_socket
        # 定位到节点底部左侧
        socket.setPos(-socket.radius, self.height - 25)
    
    def _reposition_sockets(self):
        """重新定位所有socket"""
        if hasattr(self, '_position_sockets'):
            self._position_sockets()

    # ---- 模式切换 ----

    def _on_mode_changed(self, text):
        if not self._mode_initialized:
            return
        old = self.generation_mode
        self.generation_mode = "first_last_frame" if text == "首尾帧" else "image_to_video"
        if old != self.generation_mode:
            self._setup_sockets()
            self._update_size()

    # ---- 参数 ----

    def get_upper_text(self):
        """获取文本输入口连接的文本"""
        if not self._text_input_socket:
            return ""
        for edge in self._text_input_socket.edges:
            if edge.start_socket:
                src_node = edge.start_socket.node
                if src_node.node_type == "text_vision":
                    return getattr(src_node, 'generated_text', '')
                elif src_node.node_type == "text_display":
                    return getattr(src_node, 'display_text', '')
        return ""

    def get_params(self):
        return {
            "mode":            self.generation_mode,
            "model":           self.model_combo.currentText(),
            "aspect_ratio":    self.ar_combo.currentText(),
            "enhance_prompt":  self.enhance_combo.currentText() == "是",
            "enable_upsample": self.upsample_combo.currentText() == "是",
            "prompt":          self.prompt_edit.toPlainText().strip(),
        }

    def serialize_data(self):
        return {
            "generation_mode": self.generation_mode,
            "model":           self.model_combo.currentText(),
            "aspect_ratio":    self.ar_combo.currentText(),
            "enhance_prompt":  self.enhance_combo.currentText(),
            "enable_upsample": self.upsample_combo.currentText(),
            "prompt":          self.prompt_edit.toPlainText(),
            "show_text_input": self._show_text_input,
        }

    def deserialize_data(self, data):
        self.generation_mode = data.get("generation_mode", "image_to_video")
        
        # 恢复文本输入口状态
        self._show_text_input = data.get("show_text_input", False)

        def _set(combo, key, default):
            idx = combo.findText(data.get(key, default))
            if idx >= 0:
                combo.setCurrentIndex(idx)

        _set(self.model_combo,    "model",           "veo_3_1")
        _set(self.ar_combo,       "aspect_ratio",    "16:9")
        _set(self.enhance_combo,  "enhance_prompt",  "是")
        _set(self.upsample_combo, "enable_upsample", "是")
        self.prompt_edit.setPlainText(data.get("prompt", ""))

        self._setup_sockets()
        
        # 更新按钮状态
        if hasattr(self, 'text_input_btn'):
            self.text_input_btn.setChecked(self._show_text_input)

        mode_text = "首尾帧" if self.generation_mode == "first_last_frame" else "图生视频"
        self._mode_initialized = False
        idx = self.mode_combo.findText(mode_text)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self._mode_initialized = True


class VideoNode(NodeItem):
    """视频上传节点：上传视频文件作为输入"""
    node_type = "video"

    def __init__(self):
        super().__init__("视频上传")
        self.video_path = ""
        self.project_path = None
        self.add_output("视频")
        self._update_size()

    def set_project_path(self, path):
        self.project_path = Path(path)

    def _setup_content(self):
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.video_label = QLabel("点击选择视频")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setFixedSize(180, 100)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #2a2a2a;
                border: 2px dashed #555;
                border-radius: 5px;
                color: #888;
            }
        """)
        self.video_label.setCursor(Qt.PointingHandCursor)
        self.video_label.mousePressEvent = lambda e: self._select_video()
        layout.addWidget(self.video_label)

        self.select_btn = QPushButton("选择视频")
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a; color: white;
                border: none; padding: 5px; border-radius: 3px;
            }
            QPushButton:hover { background-color: #5a5a5a; }
        """)
        self.select_btn.clicked.connect(self._select_video)
        layout.addWidget(self.select_btn)

    def load_video_file(self, file_path):
        """加载视频到节点（供拖拽上传调用）"""
        if self.project_path:
            material_dir = self.project_path / "素材库"
            material_dir.mkdir(exist_ok=True)
            file_name = Path(file_path).name
            dest_path = material_dir / file_name
            counter = 1
            while dest_path.exists():
                stem = Path(file_path).stem
                suffix = Path(file_path).suffix
                dest_path = material_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            shutil.copy2(file_path, dest_path)
            self.video_path = str(dest_path)
        else:
            self.video_path = file_path
        self._update_video_display()

    def _select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            None, "选择视频", "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.wmv *.flv *.webm)"
        )
        if file_path:
            self.load_video_file(file_path)

    def _update_video_display(self):
        if self.video_path and Path(self.video_path).exists():
            # 尝试用 OpenCV 提取第一帧作为缩略图
            thumb_pixmap = None
            try:
                import cv2
                cap = cv2.VideoCapture(self.video_path)
                ret, frame = cap.read()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    # 使用 copy() 确保数据被复制，避免 numpy 数组被垃圾回收
                    q_img = QImage(frame_rgb.tobytes(), w, h, ch * w, QImage.Format_RGB888).copy()
                    thumb_pixmap = QPixmap.fromImage(q_img)
                cap.release()
            except ImportError:
                pass

            if thumb_pixmap and not thumb_pixmap.isNull():
                scaled = thumb_pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.video_label.setPixmap(scaled)
            else:
                self.video_label.setText(f"🎬 {Path(self.video_path).name}")

            self.video_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #2196F3;
                    border-radius: 5px;
                    color: #2196F3; font-size: 11px;
                }
            """)
        elif self.video_path:
            self.video_label.setText("⚠ 视频已丢失")
            self.video_label.setStyleSheet("""
                QLabel {
                    background-color: #2a2a2a;
                    border: 2px solid #FF5722;
                    border-radius: 5px;
                    color: #FF5722; font-size: 12px;
                }
            """)

    def serialize_data(self):
        return {"video_path": self.video_path}

    def deserialize_data(self, data):
        self.video_path = data.get("video_path", "")
        if self.video_path:
            self._update_video_display()

    def _create_context_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d; color: #e0e0e0;
                border: 1px solid #444; border-radius: 5px; padding: 5px;
            }
            QMenu::item { padding: 8px 25px; border-radius: 3px; }
            QMenu::item:selected { background-color: #3d3d3d; }
        """)
        if self.video_path and Path(self.video_path).exists():
            open_folder_action = QAction("📁 打开所在文件夹", menu)
            open_folder_action.triggered.connect(self._open_video_folder)
            menu.addAction(open_folder_action)
        return menu

    def _open_video_folder(self):
        if self.video_path and Path(self.video_path).exists():
            import subprocess, platform
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


class OutputNode(NodeItem):
    node_type = "output"
    _counter = 0
    
    def __init__(self):
        self.video_path = ""          # 视频或图片的文件路径
        self.thumbnail_path = ""
        self.project_path = None
        self._status_color = None  # None=默认, 执行时变色
        self._status_timer = None
        self._is_image_output = False  # 当前输出是否为图片
        super().__init__("视频(图片)输出")
        self.output_name = "output"
        self.on_execute_requested = None
        self.on_execute_current_requested = None
        
        self.add_input("视频")
        self.add_output("输出")   # 新增输出端口，用于链式执行
        self._update_size()
    
    def set_execution_status(self, status):
        """设置执行状态，改变节点标题栏颜色
        status: 'executing'=蓝色, 'success'=绿色, 'error'=红色, 'cancelled'=灰色, None=恢复默认
        """
        color_map = {
            "executing": ("#1565C0", "#1976D2"),  # 蓝色
            "success": ("#2E7D32", "#388E3C"),     # 绿色
            "error": ("#C62828", "#D32F2F"),        # 红色
            "cancelled": ("#616161", "#757575"),    # 灰色
        }
        self._status_color = color_map.get(status)
        self.update()

        # 成功和失败状态自动恢复
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None

        if status == "success":
            self._status_timer = QTimer()
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self._reset_status_color)
            self._status_timer.start(5000)  # 5秒后恢复
        elif status in ("error", "cancelled"):
            self._status_timer = QTimer()
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self._reset_status_color)
            self._status_timer.start(8000)  # 8秒后恢复
    
    def _reset_status_color(self):
        """恢复默认标题栏颜色"""
        self._status_color = None
        self._status_timer = None
        self.update()
    
    def paint(self, painter, option, widget):
        """重写绘制方法，支持状态变色"""
        from PyQt5.QtGui import QPainterPath, QLinearGradient, QBrush, QPen
        
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 10, 10)
        
        gradient = QLinearGradient(0, 0, 0, self.height)
        gradient.setColorAt(0, QColor("#3d3d3d"))
        gradient.setColorAt(1, QColor("#2d2d2d"))
        
        painter.setBrush(QBrush(gradient))
        
        if self._status_color:
            # 执行状态：用状态色描边
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
        name_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(name_label)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("视频文件名")
        self.name_edit.setText("output")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 5px;
            }
        """)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        layout.addWidget(self.name_edit)
        
        hint_label = QLabel("将保存为: {名称}.mp4 或 .png")
        hint_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(hint_label)
        
        # 视频预览区域
        self.video_container = QWidget()
        self.video_container.setFixedSize(180, 100)
        self.video_container.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 2px dashed #555;
                border-radius: 5px;
            }
        """)
        
        # 视频帧显示标签 (底层)
        self.frame_label = QLabel(self.video_container)
        self.frame_label.setGeometry(2, 2, 176, 96)
        self.frame_label.setAlignment(Qt.AlignCenter)
        self.frame_label.setStyleSheet("background: black;")
        
        # 点击覆盖按钮 (顶层，始终接收点击)
        self.thumbnail_btn = DoubleClickButton(self.video_container)
        self.thumbnail_btn.setGeometry(2, 2, 176, 96)
        self.thumbnail_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
        """)
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
    
    def get_output_name(self):
        return self.name_edit.text() or "output"
    
    def set_project_path(self, path):
        """设置项目路径，并自动检测已有视频"""
        self.project_path = Path(path)
        self._auto_detect_video()
    
    def _on_name_changed(self):
        """输出名称修改后自动检测对应视频"""
        self._auto_detect_video()
    
    def _auto_detect_video(self):
        """根据输出名称自动检测项目文件夹中已有的视频/图片和缩略图"""
        if not self.project_path or not self.project_path.exists():
            return
        
        output_name = self.get_output_name()
        video_file = self.project_path / f"{output_name}.mp4"
        image_file = self.project_path / f"{output_name}.png"
        thumb_file = self.project_path / f"{output_name}_thumb.jpg"
        
        # 优先检测图片（来自 Gemini / 图片修改）
        if image_file.exists():
            self._is_image_output = True
            # 优先使用预生成的小缩略图，避免每次加载大 PNG 很卡
            thumb_from_png = self.project_path / f"{output_name}_thumb.jpg"
            if not thumb_from_png.exists():
                # 生成缩略图（最大 320px 宽，JPEG 85）
                try:
                    import cv2
                    import numpy as np
                    # 使用 np.fromfile 读取文件，支持中文路径
                    img_array = np.fromfile(str(image_file), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        if w > 320:
                            scale = 320 / w
                            img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
                        # 使用 imencode + tofile 保存，支持中文路径
                        ext = '.jpg'
                        cv2.imencode(ext, img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(thumb_from_png))
                except Exception:
                    pass
            if thumb_from_png.exists():
                self.set_video_thumbnail(str(thumb_from_png), str(image_file))
            else:
                self.set_video_thumbnail(str(image_file), str(image_file))
            return
        
        if video_file.exists():
            self._is_image_output = False
            # 如果没有缩略图，尝试从视频中提取
            if not thumb_file.exists():
                try:
                    import cv2
                    cap = cv2.VideoCapture(str(video_file))
                    ret, frame = cap.read()
                    if ret:
                        # 使用 imencode + tofile 保存，支持中文路径
                        cv2.imencode('.jpg', frame)[1].tofile(str(thumb_file))
                    cap.release()
                except Exception:
                    pass
            
            if thumb_file.exists():
                self.set_video_thumbnail(str(thumb_file), str(video_file))
            else:
                # 没有缩略图但有视频，直接设置视频路径并显示占位
                self.video_path = str(video_file)
                self.thumbnail_path = ""
                self.thumbnail_btn.setText("▶ 点击播放")
                self.thumbnail_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1a1a2e;
                        color: #4CAF50;
                        border: none;
                        font-size: 14px;
                    }
                """)
                self.video_container.setStyleSheet("""
                    QWidget {
                        background-color: #2a2a2a;
                        border: 2px solid #2196F3;
                        border-radius: 5px;
                    }
                """)
                self.video_container.setCursor(Qt.PointingHandCursor)
                self.video_container.show()
                self._update_size()
    
    def set_video_thumbnail(self, thumb_path, video_path):
        """设置视频/图片缩略图和文件路径"""
        self.thumbnail_path = thumb_path
        self.video_path = video_path
        # 根据文件扩展名判断是图片还是视频
        self._is_image_output = video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))
        
        p = Path(thumb_path)
        if not p.exists():
            return
        
        # 安全门：超过 500KB 的文件不直接加载为缩略图，防止卡顿
        # （正常缩略图经过压缩后应远小于 100KB）
        file_size = p.stat().st_size
        if file_size > 500 * 1024:
            # 尝试用 cv2 现场生成小缩略图到临时路径
            thumb_small = str(p.with_name(p.stem + "_thumb.jpg"))
            if not Path(thumb_small).exists():
                try:
                    import cv2
                    import numpy as np
                    # 使用 np.fromfile 读取文件，支持中文路径
                    img_array = np.fromfile(str(p), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        h, w = img.shape[:2]
                        if w > 320:
                            scale = 320 / w
                            img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
                        # 使用 imencode + tofile 保存，支持中文路径
                        cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(thumb_small)
                except Exception:
                    pass
            if Path(thumb_small).exists():
                self.thumbnail_path = thumb_small
                thumb_path = thumb_small
            # 如果仍然 > 500KB（cv2 不可用等情况），跳过显示
            if Path(thumb_path).stat().st_size > 500 * 1024:
                return
        
        # 清除该缩略图的缓存，确保加载最新图片（在最终确定路径后）
        ThumbnailCache.invalidate(thumb_path)
        
        # 尝试多种方式加载缩略图，提高兼容性
        pixmap = None
        
        # 方法1: 使用 QImage 加载后转 QPixmap
        try:
            from PyQt5.QtGui import QImage
            _img = QImage(thumb_path)
            if not _img.isNull():
                pixmap = QPixmap.fromImage(_img)
        except Exception:
            pass
        
        # 方法2: 直接使用 QPixmap 加载
        if pixmap is None or pixmap.isNull():
            try:
                pixmap = QPixmap(thumb_path)
            except Exception:
                pass
        
        # 方法3: 使用 cv2 读取并转换为 QPixmap
        if pixmap is None or pixmap.isNull():
            try:
                import cv2
                import numpy as np
                # 使用 np.fromfile 读取文件，支持中文路径
                img_array = np.fromfile(str(thumb_path), dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img is not None:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    h, w, ch = img_rgb.shape
                    bytes_per_line = ch * w
                    q_img = QImage(img_rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888).copy()
                    pixmap = QPixmap.fromImage(q_img)
            except Exception:
                pass
        
        # 方法4: 使用 PIL 读取并转换为 QPixmap
        if pixmap is None or pixmap.isNull():
            try:
                from PIL import Image
                pil_img = Image.open(thumb_path)
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                data = pil_img.tobytes('raw', 'RGB')
                q_img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(q_img)
            except Exception:
                pass
        
        if pixmap and not pixmap.isNull():
            scaled = ThumbnailCache.get(self.thumbnail_path, 176, 96) or pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_btn.setIcon(QIcon(scaled))
            self.thumbnail_btn.setIconSize(scaled.size())
            self.thumbnail_btn.set_file_path(self.video_path)  # 设置拖拽文件路径
            self.video_container.setStyleSheet("""
                QWidget {
                    background-color: #2a2a2a;
                    border: 2px solid #2196F3;
                    border-radius: 5px;
                }
            """)
            self.video_container.setCursor(Qt.PointingHandCursor)
            self.video_container.show()
            self._update_size()
    
    def _toggle_video_playback(self):
        """切换视频播放/暂停（使用OpenCV逐帧渲染），图片则直接用系统打开"""
        if not self.video_path or not Path(self.video_path).exists():
            return
        
        # 图片文件：单击也用系统默认工具打开
        if self._is_image_output:
            self._open_with_system_player()
            return
        
        if self._is_playing:
            # 暂停
            self._is_playing = False
            self._play_timer.stop()
            if self._cv_cap:
                self._cv_cap.release()
                self._cv_cap = None
            self._restore_thumbnail_icon()
        else:
            # 开始播放
            try:
                import cv2
                self._cv_cap = cv2.VideoCapture(self.video_path)
                if not self._cv_cap.isOpened():
                    return
                fps = self._cv_cap.get(cv2.CAP_PROP_FPS)
                if fps <= 0:
                    fps = 24
                self._is_playing = True
                # 清除按钮图标，让底层frame_label显示视频帧
                self.thumbnail_btn.setIcon(QIcon())
                self.thumbnail_btn.setText("")
                self._play_timer.start(int(1000 / fps))
            except ImportError:
                print("需要安装 opencv-python 才能播放视频")
    
    def _render_next_frame(self):
        """渲染下一帧视频到 frame_label"""
        if not self._cv_cap or not self._is_playing:
            self._play_timer.stop()
            return
        
        import cv2
        ret, frame = self._cv_cap.read()
        if not ret:
            # 播放结束
            self._is_playing = False
            self._play_timer.stop()
            self._cv_cap.release()
            self._cv_cap = None
            self._restore_thumbnail_icon()
            return
        
        # BGR -> RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        # 使用 copy() 确保数据被复制，避免 numpy 数组被垃圾回收
        q_img = QImage(frame_rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(q_img)
        scaled = pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.frame_label.setPixmap(scaled)
    
    def _restore_thumbnail_icon(self):
        """恢复缩略图显示到按钮上"""
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            pixmap = None
            
            # 方法1: 使用 QImage 加载
            try:
                from PyQt5.QtGui import QImage
                _img = QImage(self.thumbnail_path)
                if not _img.isNull():
                    pixmap = QPixmap.fromImage(_img)
            except Exception:
                pass
            
            # 方法2: 直接使用 QPixmap 加载
            if pixmap is None or pixmap.isNull():
                try:
                    pixmap = QPixmap(self.thumbnail_path)
                except Exception:
                    pass
            
            # 方法3: 使用 cv2 读取并转换
            if pixmap is None or pixmap.isNull():
                try:
                    import cv2
                    import numpy as np
                    # 使用 np.fromfile 读取文件，支持中文路径
                    img_array = np.fromfile(str(self.thumbnail_path), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        h, w, ch = img_rgb.shape
                        bytes_per_line = ch * w
                        q_img = QImage(img_rgb.tobytes(), w, h, bytes_per_line, QImage.Format_RGB888).copy()
                        pixmap = QPixmap.fromImage(q_img)
                except Exception:
                    pass
            
            # 方法4: 使用 PIL 读取并转换
            if pixmap is None or pixmap.isNull():
                try:
                    from PIL import Image
                    pil_img = Image.open(self.thumbnail_path)
                    if pil_img.mode in ('RGBA', 'P'):
                        pil_img = pil_img.convert('RGB')
                    data = pil_img.tobytes('raw', 'RGB')
                    q_img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format_RGB888).copy()
                    pixmap = QPixmap.fromImage(q_img)
                except Exception:
                    pass
            
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(176, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_btn.setIcon(QIcon(scaled))
                self.thumbnail_btn.setIconSize(scaled.size())
        self.frame_label.clear()
    
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
        
        return menu
    
    def _open_with_system_player(self):
        """双击：用系统默认工具打开文件（图片用图片查看器，视频用播放器）"""
        if not self.video_path or not Path(self.video_path).exists():
            return
        import subprocess
        import platform
        file_path = Path(self.video_path).resolve()
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
        """打开文件所在文件夹并选中文件"""
        if self.video_path and Path(self.video_path).exists():
            import subprocess
            import platform
            
            file_path = Path(self.video_path).resolve()
            folder_path = file_path.parent
            
            system = platform.system()
            try:
                if system == "Windows":
                    subprocess.run(["explorer", "/select,", str(file_path)], check=True)
                elif system == "Darwin":
                    subprocess.run(["open", str(folder_path)], check=True)
                else:
                    subprocess.run(["xdg-open", str(folder_path)], check=True)
            except Exception as e:
                print(f"打开文件夹失败: {e}")
    
    def _on_execute(self):
        if hasattr(self, 'on_execute_requested') and self.on_execute_requested:
            self.on_execute_requested(self)
    
    def _on_execute_current(self):
        if hasattr(self, 'on_execute_current_requested') and self.on_execute_current_requested:
            self.on_execute_current_requested(self)
    
    def _copy_output_path(self):
        """复制输出文件路径到剪贴板（同时标记来源类型）"""
        if self.video_path and Path(self.video_path).exists():
            from PyQt5.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            # 在路径前加标记前缀，粘贴时识别
            is_img = self.video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp'))
            prefix = "TAPNOW_IMG:" if is_img else "TAPNOW_VID:"
            clipboard.setText(prefix + self.video_path)
    
    def serialize_data(self):
        return {
            "output_name": self.name_edit.text(),
            "video_path": self.video_path,
            "thumbnail_path": self.thumbnail_path
        }
    
    def deserialize_data(self, data):
        self.name_edit.setText(data.get("output_name", "output"))
        self.video_path = data.get("video_path", "")
        self.thumbnail_path = data.get("thumbnail_path", "")
        
        if self.thumbnail_path and Path(self.thumbnail_path).exists():
            self.set_video_thumbnail(self.thumbnail_path, self.video_path)
        elif self.video_path and Path(self.video_path).exists():
            # 序列化数据中有路径但没有缩略图，尝试自动检测
            self._auto_detect_video()
        # 注意：如果序列化数据中没路径，set_project_path 调用时会自动检测
