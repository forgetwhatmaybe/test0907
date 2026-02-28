"""蒙版编辑器对话框"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSlider
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage
from pathlib import Path

from . import styles


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
        self._brush_size = 30
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
        self._brush_slider.setStyleSheet(styles.SLIDER_GREEN)
        self._brush_val_lbl = QLabel(str(self._brush_size))
        self._brush_val_lbl.setFixedWidth(30)
        self._brush_val_lbl.setStyleSheet(styles.LABEL_VALUE)
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
        clear_btn.setStyleSheet(styles.BUTTON)
        clear_btn.clicked.connect(self._clear)
        ctrl.addWidget(clear_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 确认 / 取消
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        ok_btn = QPushButton("✅ 确认")
        ok_btn.setStyleSheet(styles.BUTTON_GREEN)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        btn_row.addSpacing(10)

        cancel_btn = QPushButton("❌ 取消")
        cancel_btn.setStyleSheet(styles.BUTTON_RED)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_eraser_toggled(self, checked):
        self._eraser_mode = checked
        self._eraser_btn.setText("🧹 橡皮擦: 开" if checked else "🧹 橡皮擦: 关")

    def _clear(self):
        import numpy as np
        self._mask_arr[:] = 0
        self._render_canvas()

    def _canvas_to_orig(self, mx, my):
        """将画布坐标转换为原图坐标"""
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
        r = max(1, int(self._brush_size / self._canvas_scale))
        cv2.circle(self._mask_arr, (cx, cy), r, 0 if erase else 255, -1)

    def _do_line(self, ix1, iy1, ix2, iy2, erase=False):
        import cv2
        orig_h, orig_w = self._mask_arr.shape[:2]
        p1 = (max(0, min(orig_w - 1, int(round(ix1)))),
              max(0, min(orig_h - 1, int(round(iy1)))))
        p2 = (max(0, min(orig_w - 1, int(round(ix2)))),
              max(0, min(orig_h - 1, int(round(iy2)))))
        r = max(1, int(self._brush_size / self._canvas_scale))
        cv2.line(self._mask_arr, p1, p2, 0 if erase else 255, max(1, r * 2))

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

    def _render_canvas(self):
        """将原图 + 蒙版叠加渲染到画布"""
        import cv2
        import numpy as np

        orig_h, orig_w = self._orig_arr.shape[:2]
        disp_iw = max(1, int(orig_w * self._canvas_scale))
        disp_ih = max(1, int(orig_h * self._canvas_scale))
        ox = (self._disp_w - disp_iw) // 2
        oy = (self._disp_h - disp_ih) // 2

        scaled = cv2.resize(self._orig_arr, (disp_iw, disp_ih),
                            interpolation=cv2.INTER_AREA).astype(np.float32)
        scaled_mask = cv2.resize(self._mask_arr, (disp_iw, disp_ih),
                                 interpolation=cv2.INTER_NEAREST)

        canvas = np.full((self._disp_h, self._disp_w, 3), 40.0, dtype=np.float32)
        canvas[oy:oy + disp_ih, ox:ox + disp_iw] = scaled

        region = (scaled_mask > 128)[:, :, np.newaxis].astype(np.float32)
        alpha_mask = 0.55
        red = np.array([[[255.0, 80.0, 80.0]]], dtype=np.float32)

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
        cv2.imencode('.png', self._mask_arr)[1].tofile(str(save_path))
