"""节点模块 - AI 视频创作工具的节点定义

重构后的模块结构：
- cache.py: 缩略图缓存（LRU 策略）
- styles.py: 统一样式定义
- widgets.py: 共享 UI 组件
- mask_editor.py: 蒙版编辑器对话框
- image_node.py: 图片上传节点
- video_node.py: 视频上传节点
- output_node.py: 输出节点
- image_edit_node.py: 图片编辑节点
- text_vision_node.py: 文本视觉节点
- text_display_node.py: 文本显示节点
- api_nodes/: API 服务节点
    - kling_node.py: 可灵生视频
    - jimeng_node.py: 即梦生视频
    - gemini_node.py: 香蕉生图
    - veo_node.py: Veo 生视频

向后兼容：原 nodes.py 中的所有类仍可从此模块导入
"""

# 基础组件
from .cache import ThumbnailCache
from .styles import *
from .widgets import DoubleClickButton, DraggableThumbnail, ImageThumbnailStrip
from .mask_editor import MaskEditorDialog

# UI 节点
from .image_node import ImageNode
from .video_node import VideoNode
from .output_node import OutputNode
from .image_edit_node import ImageEditNode
from .text_vision_node import TextVisionNode
from .text_display_node import TextDisplayNode

# API 节点
from .api_nodes import KlingAPINode, JimengAPINode, GeminiAPINode, VeoAPINode

# 节点注册表（用于动态创建节点）
NODE_REGISTRY = {
    "image": ImageNode,
    "video": VideoNode,
    "output": OutputNode,
    "kling_api": KlingAPINode,
    "jimeng_api": JimengAPINode,
    "gemini_api": GeminiAPINode,
    "veo_api": VeoAPINode,
    "image_edit": ImageEditNode,
    "text_vision": TextVisionNode,
    "text_display": TextDisplayNode,
}

def get_node_class(node_type: str):
    """根据类型名称获取节点类"""
    return NODE_REGISTRY.get(node_type)

def register_node(node_type: str, node_class):
    """注册新的节点类型"""
    NODE_REGISTRY[node_type] = node_class

__all__ = [
    # 缓存和工具
    'ThumbnailCache',
    # 组件
    'DoubleClickButton', 'DraggableThumbnail', 'ImageThumbnailStrip',
    'MaskEditorDialog',
    # 节点
    'ImageNode', 'VideoNode', 'OutputNode', 'ImageEditNode',
    'KlingAPINode', 'JimengAPINode', 'GeminiAPINode', 'VeoAPINode',
    'TextVisionNode', 'TextDisplayNode',
    # 注册表
    'NODE_REGISTRY', 'get_node_class', 'register_node',
]
