# 代码重构说明

## 重构内容

### 1. 拆分 nodes.py 为模块化结构

原 `nodes.py` (~3000+ 行) 已拆分为以下文件：

```
core/nodes/
├── __init__.py          # 主入口，向后兼容
├── cache.py             # 缩略图缓存（修复 LRU 问题）
├── styles.py            # 统一样式定义
├── widgets.py           # 共享 UI 组件
├── mask_editor.py       # 蒙版编辑器
├── image_node.py        # 图片上传节点
├── video_node.py        # 视频上传节点
├── output_node.py       # 输出节点
├── image_edit_node.py   # 图片编辑节点
├── api_nodes/
│   ├── __init__.py
│   ├── kling_node.py    # 可灵 API
│   ├── jimeng_node.py   # 即梦 API
│   ├── gemini_node.py   # Gemini API
│   └── veo_node.py      # Veo API
└── nodes.py.backup      # 原文件备份
```

### 2. 修复 ThumbnailCache LRU 问题

**原代码问题：**
```python
# 原实现使用普通 dict，popitem() 是 FIFO 而非 LRU
if len(cls._cache) >= cls._max_cache_size:
    cls._cache.popitem()  # 错误：移除最先插入的，而非最久未使用的
```

**修复后：**
```python
# 使用 OrderedDict 实现真正的 LRU
_cache = OrderedDict()

@classmethod
def get(cls, image_path, width, height):
    if cache_key in cls._cache:
        cls._cache.move_to_end(cache_key)  # 标记为最近使用
        return cls._cache[cache_key]
    # ...
    if len(cls._cache) >= cls._max_cache_size:
        cls._cache.popitem(last=False)  # 移除最久未使用的
```

### 3. 提取公共样式

所有重复的内联 CSS 已提取到 `styles.py`：
- `COMBO_BOX` / `COMBO_BOX_SMALL` - 下拉框样式
- `TEXT_EDIT` - 文本编辑框样式
- `BUTTON` / `BUTTON_GREEN` / `BUTTON_RED` - 按钮样式
- `SLIDER_GREEN` / `SLIDER_BLUE` - 滑块样式
- `LABEL_HINT` / `LABEL_TITLE` / `LABEL_VALUE` - 标签样式
- `CONTEXT_MENU` - 右键菜单样式
- `IMAGE_PLACEHOLDER` / `IMAGE_LOADED` - 图片区域样式

## 向后兼容

原导入语句完全兼容：
```python
# 旧的导入方式仍然有效
from core.nodes import ImageNode, KlingAPINode

# 新的导入方式（推荐）
from core.nodes.image_node import ImageNode
from core.nodes.api_nodes import KlingAPINode
```

## 需要更新的导入

如果其他文件有以下导入，需要更新：

**文件：需要检查并更新导入的项目文件**
- `ui/editor_window.py` - 如果使用 NODE_REGISTRY
- `core/workflow/` - 如果有工作流相关代码

## 测试建议

1. 启动应用，检查所有节点是否正常加载
2. 测试图片/视频上传功能
3. 测试缩略图显示和缓存
4. 测试蒙版编辑器
5. 测试节点拖拽和连线

## 回滚方法

如果出现问题，可以回滚：
```bash
# 恢复备份
copy core\nodes\nodes.py.backup core\nodes\nodes.py
```

然后删除新创建的文件和目录即可。
