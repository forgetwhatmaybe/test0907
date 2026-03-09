from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTabWidget, QWidget, QGroupBox, QMessageBox,
    QComboBox, QFormLayout, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import Config
from api.kling_api import KlingAPI
from api.jimeng_api import JimengAPI
from api.gemini_api import GeminiAPI
from api.text_vision_api import TextVisionAPI


class TestConnectionThread(QThread):
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, api_instance, platform_name, model=None):
        super().__init__()
        self.api = api_instance
        self.platform_name = platform_name
        self.model = model
    
    def run(self):
        try:
            if self.model:
                result = self.api.test_connection(self.model)
            else:
                result = self.api.test_connection()
            if self.isInterruptionRequested():
                return
            if result:
                self.finished_signal.emit(True, f"{self.platform_name} 连接成功！")
            else:
                self.finished_signal.emit(False, f"{self.platform_name} 连接失败，请检查密钥是否正确")
        except Exception as e:
            if self.isInterruptionRequested():
                return
            self.finished_signal.emit(False, f"{self.platform_name} 连接错误: {str(e)}")


class APISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = Config()
        self.setWindowTitle("API 密钥设置")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._apply_style()
        self._init_ui()
        self._load_settings()

    def _apply_style(self):
        self.setStyleSheet("""
            * {
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                color: #e0e0e0;
            }
            QDialog {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: transparent;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QPushButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            QGroupBox {
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #e0e0e0;
            }
            QGroupBox QLabel {
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 1px solid #444;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 8px 16px;
                border: 1px solid #444;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                border-bottom: 1px solid #1a1a1a;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3d3d3d;
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
                selection-background-color: #3d3d3d;
                border: 1px solid #444;
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
            QCheckBox {
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: #2d2d2d;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
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
        
        tab_widget = QTabWidget()
        
        kling_tab = self._create_kling_tab()
        tab_widget.addTab(kling_tab, "可灵 AI")
        
        jimeng_tab = self._create_jimeng_tab()
        tab_widget.addTab(jimeng_tab, "即梦 AI")
        
        gemini_tab = self._create_gemini_tab()
        tab_widget.addTab(gemini_tab, "🍌 香蕉模型")
        
        veo3_tab = self._create_veo3_tab()
        tab_widget.addTab(veo3_tab, "🎬 Veo3视频")
        
        gemini3_tab = self._create_gemini3_tab()
        tab_widget.addTab(gemini3_tab, "🔮 Gemini")
        
        gpt52_tab = self._create_gpt52_tab()
        tab_widget.addTab(gpt52_tab, "🤖 GPT")
        
        general_tab = self._create_general_tab()
        tab_widget.addTab(general_tab, "通用设置")
        
        layout.addWidget(tab_widget)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save_settings)
        save_btn.setMinimumWidth(80)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumWidth(80)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _create_kling_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("可灵 AI API 密钥")
        form_layout = QFormLayout(group)
        
        self.kling_access_key_edit = QLineEdit()
        self.kling_access_key_edit.setPlaceholderText("请输入 Access Key")
        self.kling_access_key_edit.setEchoMode(QLineEdit.Password)
        ak_label = QLabel("Access Key:")
        ak_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(ak_label, self.kling_access_key_edit)
        
        self.kling_secret_key_edit = QLineEdit()
        self.kling_secret_key_edit.setPlaceholderText("请输入 Secret Key")
        self.kling_secret_key_edit.setEchoMode(QLineEdit.Password)
        sk_label = QLabel("Secret Key:")
        sk_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(sk_label, self.kling_secret_key_edit)
        
        self.kling_show_keys_cb = QPushButton("显示密钥")
        self.kling_show_keys_cb.setCheckable(True)
        self.kling_show_keys_cb.toggled.connect(self._toggle_kling_keys_visibility)
        form_layout.addRow("", self.kling_show_keys_cb)
        
        layout.addWidget(group)
        
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_kling_connection)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        hint_label = QLabel("提示：请前往可灵AI开发者中心申请API密钥\nhttps://klingai.kuaishou.com/")
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        hint_label.setOpenExternalLinks(True)
        layout.addWidget(hint_label)

        return widget

    def _create_jimeng_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("即梦 AI API 密钥 (火山引擎)")
        form_layout = QFormLayout(group)
        
        self.jimeng_access_key_edit = QLineEdit()
        self.jimeng_access_key_edit.setPlaceholderText("请输入 Access Key")
        self.jimeng_access_key_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Access Key:", self.jimeng_access_key_edit)
        
        self.jimeng_secret_key_edit = QLineEdit()
        self.jimeng_secret_key_edit.setPlaceholderText("请输入 Secret Key")
        self.jimeng_secret_key_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Secret Key:", self.jimeng_secret_key_edit)
        
        self.jimeng_show_keys_cb = QPushButton("显示密钥")
        self.jimeng_show_keys_cb.setCheckable(True)
        self.jimeng_show_keys_cb.toggled.connect(self._toggle_jimeng_keys_visibility)
        form_layout.addRow("", self.jimeng_show_keys_cb)
        
        layout.addWidget(group)
        
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_jimeng_connection)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        hint_label = QLabel("提示：请前往火山引擎控制台申请API密钥\nhttps://console.volcengine.com/iam/keymanage")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        hint_label.setOpenExternalLinks(True)
        layout.addWidget(hint_label)
        
        return widget
    
    def _create_gemini_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("🍌 香蕉模型 (Gemini) API 密钥")
        form_layout = QFormLayout(group)
        
        self.gemini_api_key_edit = QLineEdit()
        self.gemini_api_key_edit.setPlaceholderText("请输入 Gemini API Key（SK 开头的令牌）")
        self.gemini_api_key_edit.setEchoMode(QLineEdit.Password)
        ak_label = QLabel("API Key:")
        ak_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(ak_label, self.gemini_api_key_edit)

        self.gemini_show_keys_cb = QPushButton("显示密钥")
        self.gemini_show_keys_cb.setCheckable(True)
        self.gemini_show_keys_cb.toggled.connect(self._toggle_gemini_keys_visibility)
        form_layout.addRow("", self.gemini_show_keys_cb)
        
        layout.addWidget(group)
        
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_gemini_connection)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        hint_label = QLabel(
            "提示：\n"
            "1. 使用 SK 开头的 API 令牌\n"
            "   ⚠ 注意：请使用 API 令牌，不要填兑换码\n\n"
            "支持模型：\n"
            "• Gemini 2.5 Flash Image (快速)\n"
            "• Gemini 2.0 Flash Image (快速)\n"
            "• Gemini 3 Pro Image (专业版, 支持4K, 14张参考图)\n\n"
            "最多支持 14 张参考图片输入"
        )
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        hint_label.setWordWrap(True)
        hint_label.setOpenExternalLinks(True)
        layout.addWidget(hint_label)
        
        return widget
    
    def _create_veo3_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("🎬 Veo3 视频生成 API 密钥 ")
        form_layout = QFormLayout(group)
        
        self.veo3_api_key_edit = QLineEdit()
        self.veo3_api_key_edit.setPlaceholderText("请输入 API Key")
        self.veo3_api_key_edit.setEchoMode(QLineEdit.Password)
        ak_label = QLabel("API Key:")
        ak_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(ak_label, self.veo3_api_key_edit)
        
        self.veo3_show_keys_cb = QPushButton("显示密钥")
        self.veo3_show_keys_cb.setCheckable(True)
        self.veo3_show_keys_cb.toggled.connect(self._toggle_veo3_keys_visibility)
        form_layout.addRow("", self.veo3_show_keys_cb)
        
        layout.addWidget(group)
        
        layout.addStretch()
        
        hint_label = QLabel(
            "提示：\n"
            "1. 支持模型（默认: veo3.1-pro）：\n"
            "   • veo3.1-pro (高质量, 自适应首尾帧/文生视频)\n"
            "   • veo3.1-fast, veo3.1, veo3.1-4k, veo3.1-pro-4k\n"
            "   • veo3-pro, veo3-fast, veo3-fast-frames\n"
            "   • veo3-frames, veo3-pro-frames\n"
            "   • veo2-pro, veo2-fast, veo2-fast-frames\n"
            "   • veo2-fast-components, veo2-pro-components\n\n"
            "2. 特性：\n"
            "   • 所有视频均为无声版本\n"
            "   • 支持中文提示词自动转英文\n"
            "   • 支持图片输入（图生视频/首尾帧）\n"
            "   • 支持视频超分\n"
            "   • veo3/veo3.1 支持 16:9 和 9:16 宽高比\n"
        )
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        return widget
    
    def _create_gemini3_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("🔮 Gemini API 密钥")
        form_layout = QFormLayout(group)
        
        self.gemini3_api_key_edit = QLineEdit()
        self.gemini3_api_key_edit.setPlaceholderText("请输入 Gemini API Key")
        self.gemini3_api_key_edit.setEchoMode(QLineEdit.Password)
        ak_label = QLabel("API Key:")
        ak_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(ak_label, self.gemini3_api_key_edit)
        
        self.gemini3_show_keys_cb = QPushButton("显示密钥")
        self.gemini3_show_keys_cb.setCheckable(True)
        self.gemini3_show_keys_cb.toggled.connect(self._toggle_gemini3_keys_visibility)
        form_layout.addRow("", self.gemini3_show_keys_cb)
        
        layout.addWidget(group)
        
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_gemini3_connection)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        hint_label = QLabel(
            "提示：\n"
            "1. Gemini-3 Flash 用于文本视觉节点\n"
            "   支持图片理解和文本生成\n\n"
            "2. 特性：\n"
            "   • 支持多图片输入\n"
            "   • 支持中英文提示词\n"
            "   • 图片需压缩到 4.7MB 以下\n"
        )
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        return widget
    
    def _create_gpt52_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("🤖 GPT API 密钥")
        form_layout = QFormLayout(group)
        
        self.gpt52_api_key_edit = QLineEdit()
        self.gpt52_api_key_edit.setPlaceholderText("请输入 GPT API Key")
        self.gpt52_api_key_edit.setEchoMode(QLineEdit.Password)
        ak_label = QLabel("API Key:")
        ak_label.setStyleSheet("color: #e0e0e0;")
        form_layout.addRow(ak_label, self.gpt52_api_key_edit)
        
        self.gpt52_show_keys_cb = QPushButton("显示密钥")
        self.gpt52_show_keys_cb.setCheckable(True)
        self.gpt52_show_keys_cb.toggled.connect(self._toggle_gpt52_keys_visibility)
        form_layout.addRow("", self.gpt52_show_keys_cb)
        
        layout.addWidget(group)
        
        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_gpt52_connection)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        hint_label = QLabel(
            "提示：\n"
            "1. GPT-5.2 用于文本视觉节点\n"
            "   支持图片理解和文本生成\n\n"
            "2. 特性：\n"
            "   • 支持多图片输入\n"
            "   • 支持中英文提示词\n"
            "   • 高质量文本生成\n"
        )
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        return widget
    
    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("默认设置")
        form_layout = QFormLayout(group)
        
        self.default_disk_combo = QComboBox()
        from utils.file_utils import get_available_disks
        disks = get_available_disks()
        self.default_disk_combo.addItems([f"{d}:" for d in disks])
        form_layout.addRow("默认保存磁盘:", self.default_disk_combo)
        
        layout.addWidget(group)
        
        display_group = QGroupBox("界面设置")
        display_layout = QFormLayout(display_group)
        
        self.show_help_cb = QCheckBox()
        self.show_help_cb.setChecked(True)
        display_layout.addRow("显示使用说明:", self.show_help_cb)
        
        layout.addWidget(display_group)
        
        layout.addStretch()
        
        hint_label = QLabel("项目将保存在: {磁盘}:\\AIVIDEO\\{项目名}\\")
        hint_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint_label)
        
        return widget
    
    def _toggle_kling_keys_visibility(self, checked):
        if checked:
            self.kling_access_key_edit.setEchoMode(QLineEdit.Normal)
            self.kling_secret_key_edit.setEchoMode(QLineEdit.Normal)
            self.kling_show_keys_cb.setText("隐藏密钥")
        else:
            self.kling_access_key_edit.setEchoMode(QLineEdit.Password)
            self.kling_secret_key_edit.setEchoMode(QLineEdit.Password)
            self.kling_show_keys_cb.setText("显示密钥")
    
    def _toggle_jimeng_keys_visibility(self, checked):
        if checked:
            self.jimeng_access_key_edit.setEchoMode(QLineEdit.Normal)
            self.jimeng_secret_key_edit.setEchoMode(QLineEdit.Normal)
            self.jimeng_show_keys_cb.setText("隐藏密钥")
        else:
            self.jimeng_access_key_edit.setEchoMode(QLineEdit.Password)
            self.jimeng_secret_key_edit.setEchoMode(QLineEdit.Password)
            self.jimeng_show_keys_cb.setText("显示密钥")
    
    def _toggle_gemini_keys_visibility(self, checked):
        if checked:
            self.gemini_api_key_edit.setEchoMode(QLineEdit.Normal)
            self.gemini_show_keys_cb.setText("隐藏密钥")
        else:
            self.gemini_api_key_edit.setEchoMode(QLineEdit.Password)
            self.gemini_show_keys_cb.setText("显示密钥")
    
    def _toggle_veo3_keys_visibility(self, checked):
        if checked:
            self.veo3_api_key_edit.setEchoMode(QLineEdit.Normal)
            self.veo3_show_keys_cb.setText("隐藏密钥")
        else:
            self.veo3_api_key_edit.setEchoMode(QLineEdit.Password)
            self.veo3_show_keys_cb.setText("显示密钥")
    
    def _toggle_gemini3_keys_visibility(self, checked):
        if checked:
            self.gemini3_api_key_edit.setEchoMode(QLineEdit.Normal)
            self.gemini3_show_keys_cb.setText("隐藏密钥")
        else:
            self.gemini3_api_key_edit.setEchoMode(QLineEdit.Password)
            self.gemini3_show_keys_cb.setText("显示密钥")
    
    def _toggle_gpt52_keys_visibility(self, checked):
        if checked:
            self.gpt52_api_key_edit.setEchoMode(QLineEdit.Normal)
            self.gpt52_show_keys_cb.setText("隐藏密钥")
        else:
            self.gpt52_api_key_edit.setEchoMode(QLineEdit.Password)
            self.gpt52_show_keys_cb.setText("显示密钥")
    
    def _test_kling_connection(self):
        access_key = self.kling_access_key_edit.text()
        secret_key = self.kling_secret_key_edit.text()
        
        if not access_key or not secret_key:
            QMessageBox.warning(self, "警告", "请输入完整的 API 密钥")
            return
        
        api = KlingAPI()
        api.set_credentials(access_key, secret_key)
        
        self._show_testing_dialog()
        self.test_thread = TestConnectionThread(api, "可灵 AI")
        self.test_thread.finished_signal.connect(self._on_test_finished)
        self.test_thread.start()
    
    def _test_jimeng_connection(self):
        access_key = self.jimeng_access_key_edit.text()
        secret_key = self.jimeng_secret_key_edit.text()
        
        if not access_key or not secret_key:
            QMessageBox.warning(self, "警告", "请输入完整的 API 密钥")
            return
        
        api = JimengAPI()
        api.set_credentials(access_key, secret_key)
        
        self._show_testing_dialog()
        self.test_thread = TestConnectionThread(api, "即梦 AI")
        self.test_thread.finished_signal.connect(self._on_test_finished)
        self.test_thread.start()
    
    def _test_gemini_connection(self):
        api_key = self.gemini_api_key_edit.text()
        
        if not api_key:
            QMessageBox.warning(self, "警告", "请输入 Gemini API Key")
            return
        
        api = GeminiAPI()
        api.set_credentials(api_key)
        
        self._show_testing_dialog()
        self.test_thread = TestConnectionThread(api, "🍌 香蕉模型 (Gemini)")
        self.test_thread.finished_signal.connect(self._on_test_finished)
        self.test_thread.start()
    
    def _test_gemini3_connection(self):
        api_key = self.gemini3_api_key_edit.text()
        
        if not api_key:
            QMessageBox.warning(self, "警告", "请输入 Gemini-3 API Key")
            return
        
        api = TextVisionAPI()
        api.set_credentials(api_key)
        
        self._show_testing_dialog()
        self.test_thread = TestConnectionThread(api, "🔮 Gemini", model="gemini-3.1-flash-lite-preview")
        self.test_thread.finished_signal.connect(self._on_test_finished)
        self.test_thread.start()
    
    def _test_gpt52_connection(self):
        api_key = self.gpt52_api_key_edit.text()
        
        if not api_key:
            QMessageBox.warning(self, "警告", "请输入 GPT API Key")
            return
        
        api = TextVisionAPI()
        api.set_credentials(api_key)
        
        self._show_testing_dialog()
        self.test_thread = TestConnectionThread(api, "🤖 GPT", model="gpt-5.4")
        self.test_thread.finished_signal.connect(self._on_test_finished)
        self.test_thread.start()
    
    def _show_testing_dialog(self):
        self.testing_msg = QMessageBox(self)
        self.testing_msg.setWindowTitle("测试连接")
        self.testing_msg.setText("正在测试连接，请稍候...")
        self.testing_msg.setStandardButtons(QMessageBox.Cancel)
        self.testing_msg.buttonClicked.connect(self._on_testing_cancel)
        self.testing_msg.show()
    
    def _on_testing_cancel(self, button):
        if hasattr(self, 'test_thread') and self.test_thread.isRunning():
            self.test_thread.requestInterruption()
            self.test_thread.wait(3000)  # 等待最多3秒
        self.testing_msg.close()
    
    def _on_test_finished(self, success: bool, message: str):
        if hasattr(self, 'testing_msg') and self.testing_msg.isVisible():
            self.testing_msg.close()
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "失败", message)
    
    def _load_settings(self):
        kling_keys = self.config.get_api_keys("kling")
        self.kling_access_key_edit.setText(kling_keys.get("access_key", ""))
        self.kling_secret_key_edit.setText(kling_keys.get("secret_key", ""))
        
        jimeng_keys = self.config.get_api_keys("jimeng")
        self.jimeng_access_key_edit.setText(jimeng_keys.get("access_key", ""))
        self.jimeng_secret_key_edit.setText(jimeng_keys.get("secret_key", ""))
        
        gemini_keys = self.config.get_api_keys("gemini")
        self.gemini_api_key_edit.setText(gemini_keys.get("api_key", ""))
        
        veo3_keys = self.config.get_api_keys("veo3")
        self.veo3_api_key_edit.setText(veo3_keys.get("api_key", ""))
        
        gemini3_keys = self.config.get_api_keys("gemini3")
        self.gemini3_api_key_edit.setText(gemini3_keys.get("api_key", ""))
        
        gpt52_keys = self.config.get_api_keys("gpt52")
        self.gpt52_api_key_edit.setText(gpt52_keys.get("api_key", ""))
        
        default_disk = self.config.get_default_disk()
        index = self.default_disk_combo.findText(f"{default_disk}:")
        if index >= 0:
            self.default_disk_combo.setCurrentIndex(index)
        
        self.show_help_cb.setChecked(self.config.get_show_help())
    
    def _save_settings(self):
        self.config.set_api_keys("kling", {
            "access_key": self.kling_access_key_edit.text(),
            "secret_key": self.kling_secret_key_edit.text()
        })
        
        self.config.set_api_keys("jimeng", {
            "access_key": self.jimeng_access_key_edit.text(),
            "secret_key": self.jimeng_secret_key_edit.text()
        })
        
        self.config.set_api_keys("gemini", {
            "api_key": self.gemini_api_key_edit.text()
        })
        
        self.config.set_api_keys("veo3", {
            "api_key": self.veo3_api_key_edit.text()
        })
        
        self.config.set_api_keys("gemini3", {
            "api_key": self.gemini3_api_key_edit.text()
        })
        
        self.config.set_api_keys("gpt52", {
            "api_key": self.gpt52_api_key_edit.text()
        })
        
        disk_text = self.default_disk_combo.currentText()
        disk = disk_text.replace(":", "")
        self.config.set_default_disk(disk)
        
        self.config.set_show_help(self.show_help_cb.isChecked())
        
        if self.parent() and hasattr(self.parent(), '_update_help_panel'):
            self.parent()._update_help_panel()
        
        QMessageBox.information(self, "成功", "设置已保存")
        self.accept()
