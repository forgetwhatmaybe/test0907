"""打开画布自动居中到所有节点中心

给 GraphicsView 挂 center_on_all_nodes 方法（计算场景内全部节点的包围盒中心并居中），
并包装 EditorWindow._load_workflow：每次加载工作流完成后，自动把视图居中到节点群中心，
不再依赖上次保存的视口位置。

用法（程序入口注入一次）::

    from ui.editor_window import EditorWindow
    from core.node_editor.view_center import install_center_on_open
    install_center_on_open(EditorWindow)
"""

from PyQt5.QtCore import QRectF, QTimer


def center_on_all_nodes(view):
    """将视图中心移动到场景内全部节点的包围盒中心（无节点时不动）"""
    scene = view.scene()
    if scene is None or not hasattr(scene, "nodes"):
        return False
    nodes = list(scene.nodes.values())
    if not nodes:
        return False

    rect = None
    for node in nodes:
        try:
            node_rect = node.mapToScene(node.boundingRect()).boundingRect()
        except Exception:
            continue
        rect = node_rect if rect is None else rect.united(node_rect)

    if rect is None or rect.isEmpty():
        return False

    center = rect.center()
    view.centerOn(center.x(), center.y())
    return True


def install_center_on_open(editor_window_cls):
    """包装 EditorWindow._load_workflow：加载完成后延时居中（两次兜底）"""
    if getattr(editor_window_cls, "_center_on_open_installed", False):
        return editor_window_cls

    original_load = editor_window_cls._load_workflow

    def _load_workflow(self, *args, **kwargs):
        result = original_load(self, *args, **kwargs)

        def do_center():
            view = getattr(self, "view", None)
            if view is not None and hasattr(view, "center_on_all_nodes"):
                center_on_all_nodes(view)

        # 两次延时兜底：第一次覆盖常规画布，第二次覆盖 336 节点级大画布的慢加载
        QTimer.singleShot(400, do_center)
        QTimer.singleShot(1200, do_center)
        return result

    editor_window_cls._load_workflow = _load_workflow
    editor_window_cls._center_on_open_installed = True
    return editor_window_cls
