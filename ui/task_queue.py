"""任务队列管理器 + 队列查看对话框

支持多任务并行执行，每个 OutputNode 对应一个独立任务线程。
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QSizePolicy, QMenu, QApplication
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer, QPoint
from PyQt5.QtGui import QColor, QCursor
from enum import Enum, auto
import time


class TaskState(Enum):
    QUEUED = auto()     # 排队中
    RUNNING = auto()    # 执行中
    SUCCESS = auto()    # 完成
    FAILED = auto()     # 失败
    CANCELLED = auto()  # 已取消


_STATE_LABEL = {
    TaskState.QUEUED:    ("⏳ 排队中", "#888888"),
    TaskState.RUNNING:   ("🔄 执行中", "#2196F3"),
    TaskState.SUCCESS:   ("✅ 完成",   "#4CAF50"),
    TaskState.FAILED:    ("❌ 失败",   "#F44336"),
    TaskState.CANCELLED: ("⬛ 已取消", "#777777"),
}


# ─── TaskQueueManager ────────────────────────────────────────────────

class TaskQueueManager(QObject):
    """管理多个并行工作流任务"""

    task_added      = pyqtSignal(str)           # task_id
    task_updated    = pyqtSignal(str)           # task_id
    task_finished   = pyqtSignal(str)           # task_id
    queue_empty     = pyqtSignal()              # 所有任务都完成
    active_count_changed = pyqtSignal(int)      # 正在执行的任务数变化
    task_stopped    = pyqtSignal(str)           # task_id - 任务被用户停止

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = {}       # task_id -> dict{state, thread, output_name, message, type_label}
        self._task_order = []  # 保持插入顺序

    # ── 外部接口 ──

    @property
    def tasks(self):
        return self._tasks

    @property
    def task_order(self):
        return list(self._task_order)

    def active_count(self):
        return sum(1 for t in self._tasks.values() if t["state"] == TaskState.RUNNING)

    def has_running(self):
        return self.active_count() > 0

    def add_task(self, task_id, output_name, type_label, thread):
        """注册一个新任务并立即启动线程
        
        task_id:     唯一标识（一般用 output_node.id）
        output_name: 显示名称（输出节点名）
        type_label:  类型描述（如 "可灵生视频" / "即梦生视频" / "生图"）
        thread:      ExecuteThread 实例
        """
        self._tasks[task_id] = {
            "state": TaskState.RUNNING,
            "output_name": output_name,
            "type_label": type_label,
            "message": "正在执行...",
            "thread": thread,
            "start_time": time.time(),
        }
        if task_id not in self._task_order:
            self._task_order.append(task_id)

        thread.progress.connect(lambda msg, tid=task_id: self._on_progress(tid, msg))
        thread.finished_signal.connect(lambda ok, msg, tid=task_id: self._on_finished(tid, ok, msg))
        thread.start()

        self.task_added.emit(task_id)
        self.active_count_changed.emit(self.active_count())

    def stop_task(self, task_id):
        t = self._tasks.get(task_id)
        if t and t["state"] == TaskState.RUNNING:
            t["thread"].requestInterruption()
            t["state"] = TaskState.CANCELLED
            t["message"] = "正在停止..."
            self.task_updated.emit(task_id)
            self.task_stopped.emit(task_id)

    def stop_all(self):
        for tid in list(self._tasks):
            self.stop_task(tid)

    def remove_finished(self):
        """清除所有已完成/失败/取消的任务"""
        to_remove = [tid for tid, t in self._tasks.items()
                     if t["state"] in (TaskState.SUCCESS, TaskState.FAILED, TaskState.CANCELLED)]
        for tid in to_remove:
            self._tasks.pop(tid, None)
            if tid in self._task_order:
                self._task_order.remove(tid)
        if to_remove:
            self.active_count_changed.emit(self.active_count())

    # ── 内部回调 ──

    def _on_progress(self, task_id, message):
        t = self._tasks.get(task_id)
        if t:
            t["message"] = message
            self.task_updated.emit(task_id)

    def _on_finished(self, task_id, success, message):
        t = self._tasks.get(task_id)
        if not t:
            return
        if t["state"] == TaskState.CANCELLED:
            t["message"] = "已取消"
        elif success:
            t["state"] = TaskState.SUCCESS
            t["message"] = message
        else:
            t["state"] = TaskState.FAILED
            t["message"] = message

        self.task_finished.emit(task_id)
        self.task_updated.emit(task_id)
        self.active_count_changed.emit(self.active_count())

        if not self.has_running():
            self.queue_empty.emit()


# ─── TaskRowWidget ────────────────────────────────────────────────────

class TaskRowWidget(QFrame):
    """队列对话框中的单行任务条目"""

    stop_requested = pyqtSignal(str)  # task_id
    double_clicked = pyqtSignal(str)  # task_id - 双击定位到节点

    def __init__(self, task_id, info, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self._info = info
        self.setFrameShape(QFrame.StyledPanel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setMouseTracking(True)
        self.setStyleSheet("""
            TaskRowWidget {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self.name_label = QLabel(info["output_name"])
        self.name_label.setStyleSheet("color: #e0e0e0; font-weight: bold; font-size: 13px;")
        self.name_label.setFixedWidth(120)
        layout.addWidget(self.name_label)

        self.type_label = QLabel(info["type_label"])
        self.type_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self.type_label.setFixedWidth(90)
        layout.addWidget(self.type_label)

        self.state_label = QLabel()
        self.state_label.setFixedWidth(80)
        layout.addWidget(self.state_label)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("color: #888; font-size: 11px;")
        self.time_label.setFixedWidth(60)
        layout.addWidget(self.time_label)

        self.msg_label = QLabel()
        self.msg_label.setStyleSheet("color: #999; font-size: 11px;")
        self.msg_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.msg_label)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setFixedSize(50, 24)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit(self.task_id))
        layout.addWidget(self.stop_btn)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_elapsed_time)
        self._update_timer.start(1000)

        self.update_info(info)

    def _update_elapsed_time(self):
        """每秒更新已执行时间"""
        if self._info and self._info.get("state") == TaskState.RUNNING:
            start_time = self._info.get("start_time", time.time())
            elapsed = int(time.time() - start_time)
            self.time_label.setText(self._format_time(elapsed))
        else:
            # 任务不在运行状态时，停止定时器
            self._update_timer.stop()

    def _format_time(self, seconds):
        """格式化时间为 MM:SS 或 HH:MM:SS"""
        if seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{m:02d}:{s:02d}"
        else:
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h:d}:{m:02d}:{s:02d}"

    def update_info(self, info):
        self._info = info
        state = info["state"]
        label_text, color = _STATE_LABEL.get(state, ("?", "#888"))
        self.state_label.setText(label_text)
        self.state_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        self.msg_label.setText(info["message"])
        self.name_label.setText(info["output_name"])
        self.stop_btn.setEnabled(state == TaskState.RUNNING)
        
        if state != TaskState.RUNNING:
            self._update_timer.stop()
            start_time = info.get("start_time", time.time())
            elapsed = int(time.time() - start_time)
            self.time_label.setText(self._format_time(elapsed))
        else:
            start_time = info.get("start_time", time.time())
            elapsed = int(time.time() - start_time)
            self.time_label.setText(self._format_time(elapsed))

    def _show_context_menu(self, pos: QPoint):
        """显示右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #4a4a4a;
            }
        """)
        
        copy_action = menu.addAction("📋 复制错误信息")
        copy_action.triggered.connect(self._copy_message)
        
        menu.exec_(self.mapToGlobal(pos))

    def _copy_message(self):
        """复制消息到剪贴板"""
        if self._info:
            message = self._info.get("message", "")
            if message:
                clipboard = QApplication.clipboard()
                clipboard.setText(message)
    
    def mouseDoubleClickEvent(self, event):
        """双击定位到对应节点"""
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.task_id)
        super().mouseDoubleClickEvent(event)


# ─── QueueDialog ──────────────────────────────────────────────────────

class QueueDialog(QDialog):
    """任务队列查看器对话框"""
    
    locate_node_requested = pyqtSignal(str)  # task_id - 请求定位到节点

    def __init__(self, queue_manager: TaskQueueManager, parent=None):
        super().__init__(parent)
        self.queue = queue_manager
        self._rows = {}  # task_id -> TaskRowWidget

        self.setWindowTitle("任务队列")
        self.setMinimumSize(680, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
        """)

        self._build_ui()
        self._connect_signals()
        self._rebuild_all()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 顶部统计
        top = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        top.addWidget(self.count_label)
        top.addStretch()

        self.clear_btn = QPushButton("🗑 清除已完成")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: none;
                padding: 5px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """)
        self.clear_btn.clicked.connect(self._clear_finished)
        top.addWidget(self.clear_btn)

        self.stop_all_btn = QPushButton("⏹ 全部停止")
        self.stop_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        self.stop_all_btn.clicked.connect(self.queue.stop_all)
        top.addWidget(self.stop_all_btn)

        root.addLayout(top)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical {
                background-color: #2a2a2a; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a4a; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll)

    def _connect_signals(self):
        self.queue.task_added.connect(self._on_task_added)
        self.queue.task_updated.connect(self._on_task_updated)
        self.queue.task_finished.connect(self._on_task_updated)

    def _rebuild_all(self):
        """从头重建所有行"""
        # 清除旧行
        for row in self._rows.values():
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        for tid in self.queue.task_order:
            info = self.queue.tasks.get(tid)
            if info:
                self._add_row(tid, info)
        self._update_count()

    def _add_row(self, task_id, info):
        row = TaskRowWidget(task_id, info)
        row.stop_requested.connect(self.queue.stop_task)
        row.double_clicked.connect(self._on_row_double_clicked)
        # 插到 stretch 之前
        idx = self._list_layout.count() - 1
        self._list_layout.insertWidget(idx, row)
        self._rows[task_id] = row
    
    def _on_row_double_clicked(self, task_id):
        """双击任务行时，发出定位信号"""
        self.locate_node_requested.emit(task_id)

    def _on_task_added(self, task_id):
        info = self.queue.tasks.get(task_id)
        if info and task_id not in self._rows:
            self._add_row(task_id, info)
        self._update_count()

    def _on_task_updated(self, task_id):
        info = self.queue.tasks.get(task_id)
        row = self._rows.get(task_id)
        if info and row:
            row.update_info(info)
        self._update_count()

    def _clear_finished(self):
        self.queue.remove_finished()
        self._rebuild_all()

    def _update_count(self):
        total = len(self.queue.tasks)
        running = self.queue.active_count()
        done = sum(1 for t in self.queue.tasks.values() if t["state"] == TaskState.SUCCESS)
        failed = sum(1 for t in self.queue.tasks.values()
                     if t["state"] in (TaskState.FAILED, TaskState.CANCELLED))
        self.count_label.setText(
            f"总计 {total} 个任务  |  🔄 执行中 {running}  ✅ 完成 {done}  ❌ 失败/取消 {failed}"
        )
