"""节点样式定义 - 统一管理和复用样式常量"""

# 通用下拉框样式
COMBO_BOX = """
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

# 小号下拉框样式
COMBO_BOX_SMALL = """
    QComboBox {
        background-color: #2a2a2a; color: white;
        border: 1px solid #444; border-radius: 3px; padding: 2px;
    }
    QComboBox QAbstractItemView {
        background-color: #2a2a2a; color: white;
        selection-background-color: #4a4a4a; border: 1px solid #444;
    }
    QComboBox::drop-down { border: none; }
    QComboBox::down-arrow {
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent; border-top: 6px solid white;
        margin-right: 3px;
    }
"""

# 文本编辑框样式
TEXT_EDIT = """
    QTextEdit {
        background-color: #2a2a2a; color: white;
        border: 1px solid #444; border-radius: 3px;
        padding: 3px; min-height: 40px;
    }
"""

# 按钮样式
BUTTON = """
    QPushButton {
        background-color: #4a4a4a; color: white;
        border: none; padding: 5px; border-radius: 3px;
    }
    QPushButton:hover { background-color: #5a5a5a; }
"""

# 绿色按钮
BUTTON_GREEN = """
    QPushButton {
        background-color: #4CAF50; color: white; border: none;
        padding: 8px 24px; border-radius: 4px; font-size: 13px;
    }
    QPushButton:hover { background-color: #43a047; }
"""

# 红色按钮
BUTTON_RED = """
    QPushButton {
        background-color: #f44336; color: white; border: none;
        padding: 8px 24px; border-radius: 4px; font-size: 13px;
    }
    QPushButton:hover { background-color: #e53935; }
"""

# 标签样式
LABEL_HINT = "color: #888; font-size: 11px;"
LABEL_TITLE = "color: #aaa; font-size: 11px;"
LABEL_VALUE = "color: #4CAF50; font-size: 11px; min-width: 30px;"

# 上下文菜单样式
CONTEXT_MENU = """
    QMenu {
        background-color: #2d2d2d; color: #e0e0e0;
        border: 1px solid #444; border-radius: 5px; padding: 5px;
    }
    QMenu::item { padding: 8px 25px; border-radius: 3px; }
    QMenu::item:selected { background-color: #3d3d3d; }
"""

# 图片占位符样式
IMAGE_PLACEHOLDER = """
    QLabel {
        background-color: #2a2a2a; border: 2px dashed #555;
        border-radius: 5px; color: #888;
    }
"""

# 图片已加载样式
IMAGE_LOADED = """
    QLabel {
        background-color: #2a2a2a; border: 2px solid #4CAF50;
        border-radius: 5px;
    }
"""
