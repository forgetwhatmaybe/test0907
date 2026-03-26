from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QAction, QMessageBox, QProgressBar, QLabel, QFileDialog, QScrollArea, QMenu
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF
from PyQt5.QtGui import QKeySequence
from pathlib import Path
import sys
import os
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.node_editor.scene import NodeScene
from core.node_editor.graphics_view import GraphicsView
from core.node_editor.edge import Edge
from core.nodes.nodes import (
    ImageNode, KlingAPINode, JimengAPINode, GeminiAPINode, 
    OutputNode, ImageEditNode, VideoNode, VeoAPINode
)
from core.nodes.text_vision_node import TextVisionNode
from core.nodes.text_display_node import TextDisplayNode
from core.nodes.audio_node import AudioNode
from core.nodes.api_nodes.seedance2_node import Seedance2APINode
from ui.node_panel import NodePanel
from ui.api_settings_dialog import APISettingsDialog
from ui.video_player import VideoPlayerDialog
from ui.task_queue import TaskQueueManager, QueueDialog
from utils.config import Config
from utils.project_manager import ProjectManager
from utils.file_utils import download_file, compress_image_if_needed, convert_video_to_mp4, convert_audio_to_mp3
from api.kling_api import KlingAPI
from api.jimeng_api import JimengAPI
from api.gemini_api import GeminiAPI
from api.veo3_api import Veo3API
from resources.templates import get_template_list, get_template


NODE_REGISTRY = {
    "image": ImageNode,
    "kling_api": KlingAPINode,
    "jimeng_api": JimengAPINode,
    "gemini_api": GeminiAPINode,
    "veo_api": VeoAPINode,
    "seedance2_api": Seedance2APINode,
    "image_edit": ImageEditNode,
    "video": VideoNode,
    "audio": AudioNode,
    "output": OutputNode,
    "text_vision": TextVisionNode,
    "text_display": TextDisplayNode,
}


def _make_image_thumbnail(image_path, thumb_path):
    """将任意图片压缩为小 JPEG 缩略图（最大 320px 宽，质量 85）"""
    try:
        import cv2
        import numpy as np
        # 使用 np.fromfile 读取文件，支持中文路径
        img_array = np.fromfile(image_path, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return False
        h, w = img.shape[:2]
        if w > 320:
            scale = 320 / w
            img = cv2.resize(img, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
        # 使用 imencode + tofile 保存，支持中文路径
        cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(thumb_path)
        return True
    except Exception:
        return False


class _StoppedException(Exception):
    """执行被用户停止"""
    pass


class ExecuteThread(QThread):
    progress = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    video_generated = pyqtSignal(str, str)
    node_status_changed = pyqtSignal(str, str)  # (node_id, status: 'executing'/'success'/'error')
    text_display_updated = pyqtSignal(str, str, int)  # (node_id, text, tokens)
    
    def __init__(self, scene, config, project_manager, output_node=None, output_nodes=None, direct_node=None):
        super().__init__()
        self.scene = scene
        self.config = config
        self.project_manager = project_manager
        self.direct_node = direct_node
        # output_nodes 优先，如果传入列表则使用列表；否则封装单个节点
        if output_nodes is not None:
            self.target_output_nodes = output_nodes
        elif output_node is not None:
            self.target_output_nodes = [output_node]
        else:
            self.target_output_nodes = []  # 空列表表示执行全部
        # 展层兼容旧属性
        self.target_output_node = output_node
    
    def _set_output_nodes_status(self, api_node, status):
        """设置API节点连接的输出节点或文本显示节点的执行状态（仅目标节点）"""
        output_nodes = self._get_status_output_nodes(api_node)
        for output_node in output_nodes:
            self.node_status_changed.emit(output_node.id, status)
    
    def _get_status_output_nodes(self, api_node):
        """获取需要显示执行状态的输出节点列表。
        如果有 direct_node，并且 api_node 就是 direct_node，则只更新发起执行的目标输出节点。
        """
        all_output_nodes = self._find_output_nodes(api_node)
        
        # 如果是直接执行模式，并且当前节点就是 direct_node，则只返回发起执行的目标输出节点
        if self.direct_node and api_node.id == self.direct_node.id:
            # 只返回 target_output_nodes 中存在的节点
            if self.target_output_nodes:
                target_ids = {n.id for n in self.target_output_nodes}
                filtered = [n for n in all_output_nodes if n.id in target_ids]
                if filtered:
                    return filtered
            return all_output_nodes
        
        # 否则按原来的逻辑处理
        if not self.target_output_nodes:
            return all_output_nodes
        target_ids = {n.id for n in self.target_output_nodes}
        filtered = [n for n in all_output_nodes if n.id in target_ids]
        if filtered:
            return filtered
        # filtered 为空：直连 OutputNode 都不在最终目标中
        # 这是链式执行的中间步骤，必须写入中间 OutputNode 才能继续传递结果
        return all_output_nodes
    
    def _get_target_output_nodes(self, api_node):
        """获取需要保存结果的输出节点列表。
        如果是 direct_node 模式，只返回发起执行的目标输出节点。
        否则返回所有连接的输出节点。
        """
        all_output_nodes = self._find_output_nodes(api_node)
        
        # 如果是直接执行模式，只返回目标输出节点
        if self.direct_node and api_node.id == self.direct_node.id:
            if self.target_output_nodes:
                target_ids = {n.id for n in self.target_output_nodes}
                filtered = [n for n in all_output_nodes if n.id in target_ids]
                if filtered:
                    return filtered
            return all_output_nodes
        
        # 否则返回所有输出节点
        return all_output_nodes
    
    def run(self):
        try:
            self.progress.emit("正在分析工作流...")
            
            execution_order = self._get_execution_order()
            
            for node in execution_order:
                if self.isInterruptionRequested():
                    self.progress.emit("执行已停止")
                    self.finished_signal.emit(False, "⬛ 执行已停止")
                    return
                
                api_types = {"kling_api", "jimeng_api", "gemini_api", "veo_api", "seedance2_api", "image_edit", "text_vision"}
                if node.node_type not in api_types:
                    continue
                
                self._set_output_nodes_status(node, "executing")
                try:
                    if node.node_type == "kling_api":
                        self._execute_kling_node(node)
                    elif node.node_type == "jimeng_api":
                        self._execute_jimeng_node(node)
                    elif node.node_type == "gemini_api":
                        self._execute_gemini_node(node)
                    elif node.node_type == "veo_api":
                        self._execute_veo_node(node)
                    elif node.node_type == "seedance2_api":
                        self._execute_seedance2_node(node)
                    elif node.node_type == "image_edit":
                        self._execute_image_edit_node(node)
                    elif node.node_type == "text_vision":
                        self._execute_text_vision_node(node)
                    
                    if self.isInterruptionRequested():
                        self._set_output_nodes_status(node, "cancelled")
                        self.finished_signal.emit(False, "⬛ 执行已停止")
                        return
                    self._set_output_nodes_status(node, "success")
                except _StoppedException:
                    self._set_output_nodes_status(node, "cancelled")
                    self.finished_signal.emit(False, "⬛ 执行已停止")
                    return
                except Exception as e:
                    self._set_output_nodes_status(node, "error")
                    raise
            
            self.finished_signal.emit(True, "工作流执行完成")
        except Exception as e:
            self.finished_signal.emit(False, f"执行错误: {str(e)}")
    
    def _get_execution_order(self):
        """获取执行顺序，支持链式执行（OutputNode 输出端口连到下游节点）"""
        if self.direct_node:
            # 如果指定了直接节点，只执行该节点本身
            return [self.direct_node]
        elif self.target_output_nodes:
            # 从目标输出节点出发，同时沿输出端口向下游追踪整条链
            nodes = []
            chain_visited = set()
            def collect_chain(out_node):
                if out_node.id in chain_visited:
                    return
                chain_visited.add(out_node.id)
                nodes.append(out_node)
                # OutputNode 有输出端口时，沿下游继续
                for socket in out_node.outputs:
                    for edge in socket.edges:
                        if edge.end_socket:
                            downstream = edge.end_socket.node
                            # 沿下游找到下一个 OutputNode
                            self._collect_downstream_outputs(downstream, nodes, chain_visited)
            for t in self.target_output_nodes:
                collect_chain(t)
            # 更新 target_output_nodes，包含链中发现的所有 OutputNode
            # 这样下游的 OutputNode 也能正确接收结果
            self.target_output_nodes = [n for n in nodes if n.node_type == "output"]
        else:
            nodes = list(self.scene.nodes.values())
        
        order = []
        visited = set()
        
        def visit(node):
            if node.id in visited:
                return
            visited.add(node.id)
            
            for socket in node.inputs:
                for edge in socket.edges:
                    if edge.start_socket:
                        visit(edge.start_socket.node)
            
            order.append(node)
        
        for node in nodes:
            visit(node)
        
        return order
    
    def _collect_downstream_outputs(self, node, nodes_list, visited):
        """迭代收集下游的 OutputNode（优化：使用迭代替代递归）"""
        stack = [node]
        
        while stack:
            current_node = stack.pop()
            if current_node.id in visited:
                continue
            visited.add(current_node.id)
            
            if current_node.node_type == "output":
                nodes_list.append(current_node)
            
            # 将所有下游节点加入栈
            for socket in current_node.outputs:
                for edge in socket.edges:
                    if edge.end_socket:
                        stack.append(edge.end_socket.node)
    
    def _get_input_images(self, node):
        images = {"first": None, "last": None}
        
        for i, socket in enumerate(node.inputs):
            for edge in socket.edges:
                if edge.start_socket:
                    src_node = edge.start_socket.node
                    img_path = None
                    if src_node.node_type == "image":
                        # 检查连接来自哪个输出口：index=0 → 图片，index=1 → 蒙版
                        if edge.start_socket.index == 1 and getattr(src_node, 'mask_path', ''):
                            img_path = src_node.mask_path
                        else:
                            img_path = src_node.image_path
                    elif src_node.node_type == "gemini_api":
                        img_path = getattr(src_node, 'generated_image_path', '')
                    elif src_node.node_type == "output":
                        # 链式执行：从上游 OutputNode 获取结果
                        out_path = getattr(src_node, 'video_path', '')
                        if out_path and Path(out_path).exists():
                            img_path = out_path
                    elif src_node.node_type == "image_edit":
                        img_path = getattr(src_node, '_result_path', '')
                    
                    if img_path:
                        if i == 0:
                            images["first"] = img_path
                        elif i == 1:
                            images["last"] = img_path
        
        return images
    
    def _get_gemini_input_images(self, node):
        """收集 Gemini 节点的输入图片（按用户排序顺序）"""
        # 获取用户排序后的节点ID顺序
        ordered_ids = node.get_ordered_node_ids()
        
        # 从连线中收集所有图片，构建 node_id -> path 映射
        id_to_path = {}
        for socket in node.inputs:
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
                        id_to_path[src_node.id] = img_path
        
        if not id_to_path:
            return []
        
        # 按用户排序顺序返回图片路径
        result = []
        for nid in ordered_ids:
            if nid in id_to_path:
                result.append(id_to_path[nid])
        
        # 追加未在排序列表中的新图片
        for nid, path in id_to_path.items():
            if nid not in ordered_ids:
                result.append(path)
        
        return result[:14]
    
    def _execute_kling_node(self, node):
        """执行可灵生视频节点，失败后持续重试，20分钟超时（优化版）"""
        self.progress.emit(f"正在执行: {node.title}")
        
        images = self._get_input_images(node)
        image_path = images["first"]
        
        if not image_path:
            raise Exception(f"节点 '{node.title}' 没有输入图片")
        
        # 优化：只在需要时压缩图片
        if get_file_size_mb(image_path) > 4.7:
            image_path = compress_image_if_needed(image_path, 4.7)
        
        keys = self.config.get_api_keys("kling")
        if not keys.get("access_key") or not keys.get("secret_key"):
            raise Exception("请先配置可灵AI的API密钥")
        
        api = KlingAPI()
        api.set_credentials(keys["access_key"], keys["secret_key"])
        api._on_rate_limit = lambda wait, msg, attempt, total: \
            self.progress.emit(f"⏳ 并发限制，等待{wait}秒...")
        
        params = node.get_params().copy()
        if images["last"]:
            # 优化：只在需要时压缩尾帧图片
            if get_file_size_mb(images["last"]) > 4.7:
                params["tail_image"] = compress_image_if_needed(images["last"], 4.7)
            else:
                params["tail_image"] = images["last"]
        
        import time as _time
        start_time = _time.time()
        timeout = 1200
        attempt = 0
        max_retries = 6  # 最大重试次数
        
        while _time.time() - start_time < timeout and attempt < max_retries:
            if self.isInterruptionRequested():
                raise _StoppedException()
            
            attempt += 1
            self.progress.emit(f"等待视频生成... (尝试 {attempt}/{max_retries})")
            
            try:
                prompt = params.get("prompt", "")
                task_params = params.copy()
                task_params.pop("prompt", None)
                task_id = api.submit_image_to_video_task(image_path, prompt, **task_params)
                
                video_url = api.wait_for_completion(task_id, timeout=600,
                                                    is_stopped=self.isInterruptionRequested)
                
                if self.isInterruptionRequested():
                    raise _StoppedException()
                
                if video_url:
                    output_nodes = self._get_target_output_nodes(node)
                    for output_node in output_nodes:
                        output_name = output_node.get_output_name()
                        save_path = self.project_manager.get_output_path(output_name)
                        
                        download_file(video_url, str(save_path))
                        
                        thumb_path = str(save_path).replace(".mp4", "_thumb.jpg")
                        self._extract_thumbnail(str(save_path), thumb_path)
                        
                        output_node.video_path = str(save_path)
                        self.video_generated.emit(str(save_path), output_node.id)
                    
                    self.progress.emit(f"✅ 视频生成完成")
                    return
                    
            except _StoppedException:
                raise
            except Exception as e:
                elapsed = int(_time.time() - start_time)
                if elapsed < timeout and attempt < max_retries:
                    # 优化：使用指数退避策略
                    wait_time = min(5 * (2 ** (attempt - 1)), 30)  # 最大等待30秒
                    self.progress.emit(f"⏳ 重试中，等待{wait_time}秒...")
                    _time.sleep(wait_time)
                else:
                    break
        
        raise Exception(f"视频生成失败(已重试{attempt}次或超时20分钟)")
    
    def _execute_jimeng_node(self, node):
        """执行即梦生视频节点，失败后持续重试，20分钟超时"""
        self.progress.emit(f"正在执行: {node.title}")
        
        images = self._get_input_images(node)
        image_path = images["first"]
        
        if not image_path:
            raise Exception(f"节点 '{node.title}' 没有输入图片")
        
        image_path = compress_image_if_needed(image_path, 4.7)
        
        keys = self.config.get_api_keys("jimeng")
        if not keys.get("access_key") or not keys.get("secret_key"):
            raise Exception("请先配置即梦AI的API密钥")
        
        api = JimengAPI()
        api.set_credentials(keys["access_key"], keys["secret_key"])
        api._on_rate_limit = lambda wait, msg, attempt, total: \
            self.progress.emit(f"⏳ 并发限制，等待中...")
        
        params = node.get_params()
        
        if images["last"]:
            params["tail_image"] = compress_image_if_needed(images["last"], 4.7)
        
        import time as _time
        start_time = _time.time()
        timeout = 1200
        attempt = 0
        
        while _time.time() - start_time < timeout:
            if self.isInterruptionRequested():
                raise _StoppedException()
            
            attempt += 1
            self.progress.emit(f"等待视频生成...")
            
            try:
                task_params = params.copy()
                prompt = task_params.pop("prompt", "")
                task_id = api.submit_image_to_video_task(image_path, prompt, **task_params)
                
                video_url = api.wait_for_completion(task_id, timeout=600,
                                                    is_stopped=self.isInterruptionRequested)
                
                if self.isInterruptionRequested():
                    raise _StoppedException()
                
                if video_url:
                    output_nodes = self._get_target_output_nodes(node)
                    for output_node in output_nodes:
                        output_name = output_node.get_output_name()
                        save_path = self.project_manager.get_output_path(output_name)
                        
                        download_file(video_url, str(save_path))
                        
                        thumb_path = str(save_path).replace(".mp4", "_thumb.jpg")
                        self._extract_thumbnail(str(save_path), thumb_path)
                        
                        output_node.video_path = str(save_path)
                        self.video_generated.emit(str(save_path), output_node.id)
                    
                    self.progress.emit(f"✅ 视频生成完成")
                    return
                    
            except _StoppedException:
                raise
            except Exception as e:
                elapsed = int(_time.time() - start_time)
                if elapsed < timeout:
                    _time.sleep(5)
                else:
                    break
        
        raise Exception(f"视频生成失败(已超时20分钟)")
    
    def _execute_gemini_node(self, node):
        """执行香蕉生图（Gemini）节点，失败后最多重试3次"""
        self.progress.emit(f"正在执行: {node.title}")
        
        image_paths = self._get_gemini_input_images(node)
        
        image_paths = [compress_image_if_needed(p, 4.7) for p in image_paths] if image_paths else None
        
        keys = self.config.get_api_keys("gemini")
        if not keys.get("api_key"):
            raise Exception("请先配置 Gemini (香蕉模型) 的 API 密钥")
        
        api = GeminiAPI()
        api.set_credentials(keys["api_key"], base_url=keys.get("base_url", ""))
        api._on_rate_limit = lambda wait, msg, attempt, total: \
            self.progress.emit(f"⏳ 并发限制，等待中...")
        
        params = node.get_params()
        prompt = node.get_upper_text()
        if not prompt:
            prompt = params.get("prompt", "")
        if not prompt:
            raise Exception(f"节点 '{node.title}' 没有设置提示词")
        
        import time as _time
        timestamp = int(_time.time() * 1000)
        save_dir = self.project_manager.current_project_path / "素材库"
        save_dir.mkdir(exist_ok=True)
        save_path = str(save_dir / f"gemini_{timestamp}.png")
        
        max_retries = 3
        last_error = None
        for attempt in range(1, max_retries + 1):
            if self.isInterruptionRequested():
                raise _StoppedException()
            
            self.progress.emit(f"等待图片生成...")
            
            try:
                result_path = api.generate_image(
                    prompt=prompt,
                    image_paths=image_paths if image_paths else None,
                    model=params.get("model", "gemini-2.5-flash-preview-image-generation"),
                    aspect_ratio=params.get("aspect_ratio", "1:1"),
                    image_size=params.get("image_size", ""),
                    save_path=save_path,
                    is_stopped=self.isInterruptionRequested
                )
                
                if self.isInterruptionRequested():
                    raise _StoppedException()
                
                if result_path:
                    node.generated_image_path = result_path
                    self.progress.emit(f"✅ 图片生成完成")
                    self.node_status_changed.emit(node.id, "gemini_done:" + result_path)
                    
                    output_nodes = self._get_target_output_nodes(node)
                    for output_node in output_nodes:
                        output_name = output_node.get_output_name()
                        output_path = str(self.project_manager.current_project_path / f"{output_name}.png")
                        import shutil as _shutil
                        _shutil.copy2(result_path, output_path)
                        output_node.video_path = output_path
                        self.video_generated.emit(output_path, output_node.id)
                    return
                    
            except _StoppedException:
                raise
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    _time.sleep(2)
        
        raise Exception(f"图片生成失败(已重试{max_retries}次)")
    
    def _execute_veo_node(self, node):
        """执行 Veo3 生视频节点，失败后持续重试，20分钟超时"""
        self.progress.emit(f"正在执行: {node.title}")
        
        images = self._get_input_images(node)
        image_path = images["first"]
        
        if not image_path:
            raise Exception(f"节点 '{node.title}' 没有输入图片")
        
        image_path = compress_image_if_needed(image_path, 4.7)
        
        keys = self.config.get_api_keys("veo3")
        if not keys.get("api_key"):
            raise Exception("请先配置 Veo3 的 API 密钥（在设置 → Veo3视频）")
        
        api = Veo3API()
        api.set_credentials(keys["api_key"])
        
        params = node.get_params()
        prompt = node.get_upper_text()
        if not prompt:
            prompt = params.get("prompt", "").strip()
        if not prompt:
            prompt = "Generate videos based on images."
        model = params.get("model", "veo_3_1")
        aspect_ratio = params.get("aspect_ratio", "16:9")
        enhance_prompt = params.get("enhance_prompt", True)
        enable_upsample = params.get("enable_upsample", True)
        mode = params.get("mode", "image_to_video")
        
        image_list = [image_path]
        if mode == "first_last_frame" and images["last"]:
            image_list.append(compress_image_if_needed(images["last"], 4.7))
        
        import time as _time
        start_time = _time.time()
        timeout = 1200
        attempt = 0
        
        while _time.time() - start_time < timeout:
            if self.isInterruptionRequested():
                raise _StoppedException()
            
            attempt += 1
            self.progress.emit(f"等待视频生成...")
            
            try:
                task_id = api.submit_video_task(
                    prompt=prompt,
                    model=model,
                    images=image_list,
                    enhance_prompt=enhance_prompt,
                    enable_upsample=enable_upsample,
                    aspect_ratio=aspect_ratio,
                )
                
                video_url = api.wait_for_completion(
                    task_id,
                    timeout=600,
                    is_stopped=self.isInterruptionRequested
                )
                
                if self.isInterruptionRequested():
                    raise _StoppedException()
                
                if video_url:
                    output_nodes = self._get_target_output_nodes(node)
                    for output_node in output_nodes:
                        output_name = output_node.get_output_name()
                        save_path = self.project_manager.get_output_path(output_name)
                        
                        import requests
                        resp = requests.get(video_url, timeout=120)
                        if resp.status_code == 200:
                            with open(str(save_path), 'wb') as f:
                                f.write(resp.content)
                        else:
                            raise Exception(f"视频下载失败: HTTP {resp.status_code}")
                        
                        thumb_path = str(save_path).replace(".mp4", "_thumb.jpg")
                        self._extract_thumbnail(str(save_path), thumb_path)
                        
                        output_node.video_path = str(save_path)
                        self.video_generated.emit(str(save_path), output_node.id)
                    
                    self.progress.emit(f"✅ 视频生成完成")
                    return
                    
            except _StoppedException:
                raise
            except Exception as e:
                elapsed = int(_time.time() - start_time)
                if elapsed < timeout:
                    _time.sleep(5)
                else:
                    break
        
        raise Exception(f"视频生成失败(已超时20分钟)")

    def _execute_seedance2_node(self, node):
        """执行 Seedance 2.0 生视频节点，支持三种模式"""
        self.progress.emit(f"正在执行: {node.title}")

        # 获取生成模式
        mode = getattr(node, 'generation_mode', 'multimodal')

        # 获取 API Key
        keys = self.config.get_api_keys("seedance2")
        if not keys.get("api_key"):
            raise Exception("请先配置 Seedance 2.0 的 API 密钥（在设置 → Seedance 2.0）")

        from api.seedance2_api import Seedance2API
        api = Seedance2API()
        api.set_credentials(keys["api_key"])

        params = node.get_params()
        prompt = params.get("prompt", "")
        if not prompt:
            raise Exception(f"节点 '{node.title}' 没有设置提示词")

        # 根据模式收集输入
        image_urls = None
        video_urls = None
        audio_urls = None

        import base64 as _b64

        def _file_to_data_url(file_path):
            """将文件转换为 data URL"""
            from pathlib import Path as _Path
            suffix = _Path(file_path).suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".bmp": "image/bmp", ".gif": "image/gif", ".tiff": "image/tiff",
                ".mp4": "video/mp4", ".mov": "video/quicktime",
                ".mp3": "audio/mpeg", ".wav": "audio/wav",
            }
            mime = mime_map.get(suffix, "application/octet-stream")
            with open(file_path, "rb") as f:
                data = _b64.b64encode(f.read()).decode()
            return f"data:{mime};base64,{data}"

        if mode == "multimodal":
            # 参考生视频模式：收集所有图片、视频、音频
            image_paths = node.get_ordered_image_paths()
            video_paths = node.get_ordered_video_paths()
            audio_paths = node.get_ordered_audio_paths()
            
            # 预处理文件
            self.progress.emit("正在预处理文件...")
            image_paths = [compress_image_if_needed(p, 4.7) for p in image_paths] if image_paths else None
            video_paths = [convert_video_to_mp4(p, 50) for p in video_paths] if video_paths else None
            audio_paths = [convert_audio_to_mp3(p, 15) for p in audio_paths] if audio_paths else None
            
            image_urls = [_file_to_data_url(p) for p in image_paths] if image_paths else None
            video_urls = [_file_to_data_url(p) for p in video_paths] if video_paths else None
            audio_urls = [_file_to_data_url(p) for p in audio_paths] if audio_paths else None
        elif mode == "image_to_video":
            # 图生视频模式：只收集图片
            image_paths = node.get_ordered_image_paths()
            
            # 预处理图片
            self.progress.emit("正在预处理图片...")
            image_paths = [compress_image_if_needed(p, 4.7) for p in image_paths] if image_paths else None
            
            image_urls = [_file_to_data_url(p) for p in image_paths] if image_paths else None
        elif mode == "first_last_frame":
            # 首尾帧模式：收集首帧和尾帧图片
            image_paths = node.get_ordered_image_paths()
            if len(image_paths) < 2:
                raise Exception(f"节点 '{node.title}' 首尾帧模式需要至少2张图片（首帧和尾帧）")
            
            # 预处理图片
            self.progress.emit("正在预处理图片...")
            image_paths = [compress_image_if_needed(p, 4.7) for p in image_paths[:2]]
            
            image_urls = [_file_to_data_url(p) for p in image_paths]

        import time as _time
        start_time = _time.time()
        timeout = 1200
        attempt = 0

        while _time.time() - start_time < timeout:
            if self.isInterruptionRequested():
                raise _StoppedException()

            attempt += 1
            self.progress.emit(f"等待视频生成...")

            try:
                task_id = api.submit_video_task(
                    prompt=prompt,
                    image_urls=image_urls,
                    video_urls=video_urls,
                    audio_urls=audio_urls,
                    duration=params.get("duration", 5),
                    quality=params.get("quality", "720p"),
                    aspect_ratio=params.get("aspect_ratio", "16:9"),
                    generate_audio=params.get("generate_audio", True),
                )

                video_url = api.wait_for_completion(
                    task_id,
                    timeout=600,
                    is_stopped=self.isInterruptionRequested
                )

                if self.isInterruptionRequested():
                    raise _StoppedException()

                if video_url:
                    output_nodes = self._get_target_output_nodes(node)
                    for output_node in output_nodes:
                        output_name = output_node.get_output_name()
                        save_path = self.project_manager.get_output_path(output_name)

                        import requests
                        resp = requests.get(video_url, timeout=120)
                        if resp.status_code == 200:
                            with open(str(save_path), 'wb') as f:
                                f.write(resp.content)
                        else:
                            raise Exception(f"视频下载失败: HTTP {resp.status_code}")

                        thumb_path = str(save_path).replace(".mp4", "_thumb.jpg")
                        self._extract_thumbnail(str(save_path), thumb_path)

                        output_node.video_path = str(save_path)
                        self.video_generated.emit(str(save_path), output_node.id)

                    self.progress.emit(f"✅ 视频生成完成")
                    return

            except _StoppedException:
                raise
            except Exception as e:
                elapsed = int(_time.time() - start_time)
                if elapsed < timeout:
                    _time.sleep(5)
                else:
                    break

        raise Exception(f"视频生成失败(已超时20分钟)")
      
    def _execute_image_edit_node(self, node):
        """执行图片修改节点：可灵扩图 / 即梦超清 / 即梦局部重绘"""
        self.progress.emit(f"正在执行: {node.title}")
        params = node.get_params()
        mode = params["mode"]
        
        images = self._get_input_images(node)
        image_path = images["first"]
        if not image_path:
            raise Exception(f"节点 '{node.title}' 没有输入图片")
        
        import time as _time
        timestamp = int(_time.time() * 1000)
        save_dir = self.project_manager.current_project_path / "素材库"
        save_dir.mkdir(exist_ok=True)
        
        if mode == "可灵扩图":
            keys = self.config.get_api_keys("kling")
            if not keys.get("access_key") or not keys.get("secret_key"):
                raise Exception("请先配置可灵AI的API密钥")
            api = KlingAPI()
            api.set_credentials(keys["access_key"], keys["secret_key"])
            api._on_rate_limit = lambda wait, msg, attempt, total: \
                self.progress.emit(f"⏳ 并发限制: {msg}，等待{wait}秒后重试 ({attempt}/{total})")
            
            # 可灵扩图限制：最终面积不超过原图 3 倍
            # (1 + up + down) * (1 + left + right) <= 3
            # 如果超出，等比缩小四个方向的比例
            up    = params.get("up_expansion_ratio", 0.0)
            down  = params.get("down_expansion_ratio", 0.0)
            left  = params.get("left_expansion_ratio", 0.0)
            right = params.get("right_expansion_ratio", 0.0)
            area_mult = (1 + up + down) * (1 + left + right)
            if area_mult > 3.0:
                # 等比缩小：scale_factor = sqrt(3 / area_mult)
                import math as _math
                scale = _math.sqrt(3.0 / area_mult)
                up    = round(up    * scale, 4)
                down  = round(down  * scale, 4)
                left  = round(left  * scale, 4)
                right = round(right * scale, 4)
                params["up_expansion_ratio"]    = up
                params["down_expansion_ratio"]  = down
                params["left_expansion_ratio"]  = left
                params["right_expansion_ratio"] = right
                self.progress.emit(
                    f"⚠ 扩图面积超过 3 倍限制，已自动缩放至 "
                    f"上{up:.2f}/下{down:.2f}/左{left:.2f}/右{right:.2f}"
                )
            
            self.progress.emit("提交可灵扩图任务...")
            task_id = api.submit_expand_image_task(image_path, **params)
            self.progress.emit(f"等待扩图完成... (任务ID: {task_id[:8]}...)")
            result_url = api.wait_for_expand_completion(task_id, timeout=300,
                                                         is_stopped=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                raise _StoppedException()
            if not result_url:
                raise Exception("可灵扩图失败")
            
            save_path = str(save_dir / f"expand_{timestamp}.png")
            self.progress.emit(f"下载扩图结果...")
            download_file(result_url, save_path)
        
        elif mode == "即梦超清":
            keys = self.config.get_api_keys("jimeng")
            if not keys.get("access_key") or not keys.get("secret_key"):
                raise Exception("请先配置即梦AI的API密钥")
            api = JimengAPI()
            api.set_credentials(keys["access_key"], keys["secret_key"])
            
            self.progress.emit("提交即梦超清任务...")
            task_id = api.submit_super_resolution_task(image_path, **params)
            self.progress.emit(f"等待超清处理... (任务ID: {task_id[:8]}...)")
            result_url = api.wait_for_completion(task_id, timeout=300,
                                                  is_stopped=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                raise _StoppedException()
            if not result_url:
                raise Exception("即梦超清失败")
            
            save_path = str(save_dir / f"sr_{timestamp}.png")
            self.progress.emit(f"下载超清结果...")
            if result_url.startswith("base64:"):
                import base64 as _b64
                img_data = _b64.b64decode(result_url[7:])
                with open(save_path, 'wb') as f:
                    f.write(img_data)
            else:
                download_file(result_url, save_path)
        
        elif mode == "即梦局部重绘":
            keys = self.config.get_api_keys("jimeng")
            if not keys.get("access_key") or not keys.get("secret_key"):
                raise Exception("请先配置即梦AI的API密钥")
            api = JimengAPI()
            api.set_credentials(keys["access_key"], keys["secret_key"])
            
            mask_path = images.get("last")
            if not mask_path:
                raise Exception(f"节点 '{node.title}' 没有输入遮罩图（第二个输入口）")
            
            prompt = params.get("prompt", "")
            if not prompt:
                raise Exception(f"节点 '{node.title}' 局部重绘需要提示词")
            
            self.progress.emit("提交即梦局部重绘任务...")
            task_id = api.submit_inpaint_task(image_path, mask_path, prompt,
                                               seed=params.get("seed", 101))
            self.progress.emit(f"等待重绘完成... (任务ID: {task_id[:8]}...)")
            result_url = api.wait_for_completion(task_id, timeout=300,
                                                  is_stopped=self.isInterruptionRequested)
            if self.isInterruptionRequested():
                raise _StoppedException()
            if not result_url:
                raise Exception("即梦局部重绘失败")
            
            save_path = str(save_dir / f"inpaint_{timestamp}.png")
            self.progress.emit(f"下载重绘结果...")
            if result_url.startswith("base64:"):
                import base64 as _b64
                img_data = _b64.b64decode(result_url[7:])
                with open(save_path, 'wb') as f:
                    f.write(img_data)
            else:
                download_file(result_url, save_path)
        else:
            raise Exception(f"未知的图片修改模式: {mode}")
        
        # 存储结果路径，供下游节点读取
        node._result_path = save_path
        self.progress.emit(f"✅ 图片修改完成: {Path(save_path).name}")
        
        # 如果直接连接到 OutputNode，复制到输出位置
        output_nodes = self._get_target_output_nodes(node)
        for output_node in output_nodes:
            output_name = output_node.get_output_name()
            output_path = str(self.project_manager.current_project_path / f"{output_name}.png")
            import shutil as _shutil
            _shutil.copy2(save_path, output_path)
            # 直接设置 video_path，供链式执行下游节点读取
            output_node.video_path = output_path
            self.video_generated.emit(output_path, output_node.id)
    
    def _execute_text_vision_node(self, node):
        """执行文本视觉节点：调用 GPT-5.2 或 Gemini-3 进行图片理解"""
        self.progress.emit(f"正在执行: {node.title}")
        
        params = node.get_params()
        prompt = params.get("prompt", "")
        if not prompt:
            raise Exception(f"节点 '{node.title}' 没有设置提示词")
        
        image_paths = node.get_ordered_image_paths()
        if image_paths:
            image_paths = [compress_image_if_needed(p, 4.7) for p in image_paths]
        
        model = params.get("model", "gpt-5.2")
        temperature = params.get("temperature", 0.8)
        
        if model.startswith("gpt"):
            keys = self.config.get_api_keys("gpt52")
            if not keys.get("api_key"):
                raise Exception("请先配置 GPT-5.2 的 API 密钥（在设置 → GPT-5.2）")
        else:
            keys = self.config.get_api_keys("gemini3")
            if not keys.get("api_key"):
                raise Exception("请先配置 Gemini-3 的 API 密钥（在设置 → Gemini-3）")
        
        from api.text_vision_api import TextVisionAPI
        api = TextVisionAPI()
        api.set_credentials(keys["api_key"])
        
        self.progress.emit(f"正在调用 {model} 生成文本...")
        
        try:
            result_text = api.generate_text(
                prompt=prompt,
                image_paths=image_paths,
                model=model,
                temperature=temperature,
                is_stopped=self.isInterruptionRequested
            )
            
            if self.isInterruptionRequested():
                raise _StoppedException()
            
            if result_text:
                node.generated_text = result_text
                estimated_tokens = TextVisionAPI.estimate_tokens(prompt, image_paths)
                self.progress.emit(f"✅ 文本生成完成 (预估 {estimated_tokens} tokens)")
                
                # 使用信号更新文本显示节点（跨线程安全）
                # 获取目标输出节点列表
                text_display_nodes = self._get_target_output_nodes(node)
                # 过滤只保留 text_display 类型
                text_display_nodes = [n for n in text_display_nodes if n.node_type == "text_display"]
                for text_node in text_display_nodes:
                    self.text_display_updated.emit(text_node.id, result_text, estimated_tokens)
            else:
                raise Exception("API 返回空结果")
                
        except _StoppedException:
            raise
        except Exception as e:
            raise Exception(f"文本生成失败: {str(e)}")
    
    def _find_output_nodes(self, api_node):
        output_nodes = []
        for socket in api_node.outputs:
            for edge in socket.edges:
                if edge.end_socket and edge.end_socket.node.node_type in ("output", "text_display"):
                    output_nodes.append(edge.end_socket.node)
        return output_nodes
    
    def _find_text_display_nodes(self, text_vision_node):
        """查找连接到文本视觉节点的文本显示节点"""
        text_display_nodes = []
        for socket in text_vision_node.outputs:
            for edge in socket.edges:
                if edge.end_socket and edge.end_socket.node.node_type == "text_display":
                    text_display_nodes.append(edge.end_socket.node)
        return text_display_nodes
    
    def _extract_thumbnail(self, video_path, thumb_path):
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            ret, frame = cap.read()
            if ret:
                # 缩放到最大 320px 宽，保持比例
                h, w = frame.shape[:2]
                if w > 320:
                    scale = 320 / w
                    frame = cv2.resize(frame, (320, int(h * scale)), interpolation=cv2.INTER_AREA)
                # 使用 imencode + tofile 保存，支持中文路径
                cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(thumb_path)
            cap.release()
        except:
            pass


class EditorWindow(QMainWindow):
    def __init__(self, project_path: str, parent=None):
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.config = Config()
        self.project_manager = ProjectManager(self.config)
        self.project_manager.open_project(project_path)
        
        self.clipboard_nodes = []
        self.undo_stack = []
        self.redo_stack = []
        
        # 任务队列管理器
        self.task_queue = TaskQueueManager(self)
        self.task_queue.active_count_changed.connect(self._on_active_count_changed)
        self.task_queue.queue_empty.connect(self._on_queue_empty)
        self.task_queue.task_stopped.connect(self._on_task_stopped)
        self._queue_dialog = None
        
        # 防抖自动保存定时器（内容变化后2秒无操作才保存）
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(2000)
        self._auto_save_timer.timeout.connect(self._auto_save)
        
        self.setWindowTitle(f"{self.project_path.name}")
        self.setMinimumSize(1200, 800)
        self.setCursor(Qt.ArrowCursor)
        
        self._init_ui()
        self._init_toolbar()
        self._init_shortcuts()
        
        QTimer.singleShot(10, self._load_workflow)
    
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        
        self.node_panel = NodePanel()
        self.node_panel.setFixedWidth(200)
        
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scene = NodeScene()
        self.view = GraphicsView(self.scene)
        self.view.setCursor(Qt.ArrowCursor)
        self.view.viewport().setCursor(Qt.ArrowCursor)
        self.view.on_node_drop = self._on_node_drop
        self.view.on_edge_created = self._auto_save
        self.view.on_template_place = self._place_template_at
        self.view.on_image_file_drop = self._on_image_file_drop
        self.view.on_video_file_drop = self._on_video_file_drop
        self.view.on_edge_drop_create = self._on_edge_drop_create
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        
        center_layout.addWidget(self.view)
        
        self.help_panel = self._create_help_panel()
        center_layout.addWidget(self.help_panel)
        
        splitter.addWidget(self.node_panel)
        splitter.addWidget(center_widget)
        splitter.setSizes([200, 1000])
        
        layout.addWidget(splitter)
        
        self._apply_style()
        self._load_help_setting()
        
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 4px 10px;
                font-size: 13px;
            }
        """)
        self.statusBar().showMessage(f"项目: {self.project_path.name}")
    
    def _load_help_setting(self):
        show_help = self.config.get_show_help()
        self.help_panel.setVisible(show_help)
    
    def _update_help_panel(self):
        show_help = self.config.get_show_help()
        self.help_panel.setVisible(show_help)
    
    def _create_help_panel(self):
        panel = QWidget()
        panel.setFixedWidth(200)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2a2a2a;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a4a;
                border-radius: 3px;
            }
        """)
        
        content = QLabel()
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        content.setStyleSheet("color: #888; font-size: 11px;")
        
        try:
            from pathlib import Path
            import sys
            if hasattr(sys, '_MEIPASS'):
                help_file = Path(sys._MEIPASS) / "resources" / "sm.txt"
            else:
                help_file = Path(__file__).parent.parent / "resources" / "sm.txt"
            if help_file.exists():
                with open(help_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    numbered_lines = [f"{i+1}. {line}" for i, line in enumerate(lines)]
                    content.setText("\n".join(numbered_lines))
        except:
            content.setText("1. Delete键删除选中的节点或连线\n2. Ctrl+C复制选中的节点\n3. Ctrl+V粘贴节点")
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return panel
    
    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QToolBar {
                background-color: #1a1a1a;
                border: none;
                spacing: 5px;
                padding: 5px;
            }
            QToolBar QToolButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QToolBar QToolButton:hover {
                background-color: #3d3d3d;
            }
            QToolBar QToolButton:pressed {
                background-color: #4d4d4d;
            }
            QStatusBar {
                background-color: #1a1a1a;
                color: #888;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QSplitter::handle {
                background-color: #2d2d2d;
            }
        """)
    
    def _init_toolbar(self):
        toolbar = self.addToolBar("工具栏")
        toolbar.setMovable(False)
        
        back_action = QAction("← 返回", self)
        back_action.triggered.connect(self._go_back)
        toolbar.addAction(back_action)
        
        toolbar.addSeparator()
        
        save_action = QAction("💾 保存", self)
        save_action.triggered.connect(self._save_workflow)
        toolbar.addAction(save_action)
        
        toolbar.addSeparator()
        
        undo_action = QAction("↩ 撤销", self)
        undo_action.triggered.connect(self._undo)
        toolbar.addAction(undo_action)
        
        redo_action = QAction("↪ 重做", self)
        redo_action.triggered.connect(self._redo)
        toolbar.addAction(redo_action)
        
        toolbar.addSeparator()
        
        template_menu = QMenu("📋 模板", self)
        template_menu.setStyleSheet("""
            QMenu {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
            }
            QMenu::item:selected {
                background-color: #4a4a4a;
            }
        """)
        
        for template_info in get_template_list():
            template_action = QAction(template_info["name"], self)
            template_action.setToolTip(template_info["description"])
            template_action.triggered.connect(lambda checked, tid=template_info["id"]: self._load_template(tid))
            template_menu.addAction(template_action)
        
        template_btn = QAction("📋 模板", self)
        template_btn.setMenu(template_menu)
        toolbar.addAction(template_btn)
        
        toolbar.addSeparator()
        
        execute_action = QAction("▶ 执行", self)
        execute_action.triggered.connect(self._execute_selected_or_all)
        toolbar.addAction(execute_action)
        
        self.stop_action = QAction("⏹ 停止全部", self)
        self.stop_action.triggered.connect(self._stop_all_tasks)
        self.stop_action.setEnabled(False)
        toolbar.addAction(self.stop_action)
        
        self.queue_action = QAction("📋 队列", self)
        self.queue_action.triggered.connect(self._open_queue_dialog)
        toolbar.addAction(self.queue_action)
        
        toolbar.addSeparator()
        
        settings_action = QAction("⚙ API设置", self)
        settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(settings_action)
        
        self.statusBar().showMessage(f"项目: {self.project_path.name}")
    
    def _init_shortcuts(self):
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self._undo)
        
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self._redo)
        
        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        copy_shortcut.activated.connect(self._copy_nodes)
        
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_shortcut.activated.connect(self._paste_nodes)
        
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._save_workflow)
    
    def _on_image_file_drop(self, file_paths, pos):
        """图片文件被拖入画布时：单张就近加载到已有ImageNode，多张创建多个新节点"""
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        if len(file_paths) == 1:
            # 单张图片：就近加载到已有ImageNode，否则创建新节点
            file_path = file_paths[0]
            closest_node = None
            closest_dist = float('inf')
            for node in self.scene.nodes.values():
                if isinstance(node, ImageNode):
                    node_center = node.pos() + QPointF(node.width / 2, node.height / 2)
                    dist = ((pos.x() - node_center.x()) ** 2 + (pos.y() - node_center.y()) ** 2) ** 0.5
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_node = node
            if closest_node and closest_dist < 220:
                closest_node.load_image_file(file_path)
                self._auto_save()
                return
            self._save_undo_state()
            node = ImageNode()
            node.setPos(pos)
            if hasattr(node, 'set_project_path'):
                node.set_project_path(str(self.project_path))
            node.load_image_file(file_path)
            self.scene.add_node(node)
            self._auto_save()
        else:
            # 多张图片：每张创建一个新节点，纵向排列
            self._save_undo_state()
            spacing_y = 200  # 节点间纵向间距
            for i, file_path in enumerate(file_paths):
                node = ImageNode()
                node.setPos(QPointF(pos.x(), pos.y() + i * spacing_y))
                if hasattr(node, 'set_project_path'):
                    node.set_project_path(str(self.project_path))
                node.load_image_file(file_path)
                self.scene.add_node(node)
            self._auto_save()

    def _on_video_file_drop(self, file_paths, pos):
        """视频文件被拖入画布时：每个视频创建一个 VideoNode"""
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        self._save_undo_state()
        spacing_y = 200
        for i, file_path in enumerate(file_paths):
            node = VideoNode()
            node.setPos(QPointF(pos.x(), pos.y() + i * spacing_y))
            if hasattr(node, 'set_project_path'):
                node.set_project_path(str(self.project_path))
            node.load_video_file(file_path)
            self.scene.add_node(node)
        self._auto_save()

    def _on_node_drop(self, node_type, pos):
        node_class = NODE_REGISTRY.get(node_type)
        if node_class:
            self._save_undo_state()
            node = node_class()
            node.setPos(pos)
            if hasattr(node, 'set_project_path'):
                node.set_project_path(str(self.project_path))
            if hasattr(node, 'set_unique_name'):
                existing_names = set()
                for n in self.scene.nodes.values():
                    if hasattr(n, 'get_output_name'):
                        existing_names.add(n.get_output_name())
                if hasattr(node, 'name_edit'):
                    existing_names.add(node.name_edit.text())
                node.set_unique_name(existing_names)
            if hasattr(node, 'on_execute_requested'):
                node.on_execute_requested = self._on_node_execute
            if hasattr(node, 'on_execute_current_requested'):
                node.on_execute_current_requested = self._on_node_execute_current
            self._connect_node_signals(node)
            self.scene.add_node(node)
            self._auto_save()
    
    def _on_edge_drop_create(self, node_type, scene_pos, source_socket, source_type):
        """拖线到空白处松开后，创建新节点并自动与来源 socket 连线"""
        from core.node_editor.edge import Edge

        node_class = NODE_REGISTRY.get(node_type)
        if not node_class:
            return

        self._save_undo_state()
        node = node_class()
        # 根据拖线方向偏移节点位置，使 socket 对准鼠标释放点
        if source_type == 'output':
            # 新节点在右侧，输入 socket 在左侧，向右偏移一点
            node.setPos(scene_pos.x() + 20, scene_pos.y() - node.height / 2)
        else:
            # 新节点在左侧，输出 socket 在右侧
            node.setPos(scene_pos.x() - node.width - 20, scene_pos.y() - node.height / 2)

        if hasattr(node, 'set_project_path'):
            node.set_project_path(str(self.project_path))
        if hasattr(node, 'set_unique_name'):
            existing_names = set()
            for n in self.scene.nodes.values():
                if hasattr(n, 'get_output_name'):
                    existing_names.add(n.get_output_name())
            node.set_unique_name(existing_names)
        if hasattr(node, 'on_execute_requested'):
            node.on_execute_requested = self._on_node_execute
        if hasattr(node, 'on_execute_current_requested'):
            node.on_execute_current_requested = self._on_node_execute_current
        self._connect_node_signals(node)
        self.scene.add_node(node)

        # 自动连线
        if source_type == 'output' and node.inputs:
            # 检查是否是从文本显示节点拉线到 Veo 或香蕉生图节点
            source_node = source_socket.node
            is_text_display_source = (hasattr(source_node, 'node_type') and 
                                      source_node.node_type in ('text_display', 'text_vision'))
            is_target_gemini_or_veo = node_type in ('gemini_api', 'veo_api')
            
            in_socket = None
            
            if is_text_display_source and is_target_gemini_or_veo:
                # 自动显示红色文本输入口
                if hasattr(node, '_toggle_text_input') and not node._show_text_input:
                    node._toggle_text_input()
                
                # 连接到红色文本输入口
                if hasattr(node, '_text_input_socket') and node._text_input_socket:
                    in_socket = node._text_input_socket
            
            # 如果没有特殊处理，使用默认第一个输入口
            if in_socket is None:
                in_socket = node.inputs[0]
            
            if not getattr(in_socket, 'multi_input', False):
                for edge in in_socket.edges[:]:
                    edge.remove()
            new_edge = Edge(source_socket, in_socket)
            self.scene.add_edge(new_edge)
        elif source_type == 'input' and node.outputs:
            # 来源是输入口 → 连到新节点的第一个输出口
            out_socket = node.outputs[0]
            in_socket = source_socket
            if not getattr(in_socket, 'multi_input', False):
                for edge in in_socket.edges[:]:
                    edge.remove()
            new_edge = Edge(out_socket, in_socket)
            self.scene.add_edge(new_edge)

        self._auto_save()

    def _on_node_execute(self, output_node):
        """右键执行/点击节点执行按钮：如果有多个输出/文本显示节点被选中，则并行执行所有选中的节点"""
        # 检查是 output 节点还是 text_display 节点
        is_text_display = hasattr(output_node, 'node_type') and output_node.node_type == 'text_display'
        
        # 找到当前选中的 output 或 text_display 节点
        selected = [item for item in self.scene.selectedItems()
                    if hasattr(item, 'node_type') and item.node_type in ('output', 'text_display')]
        
        # 如果没有选中，或者只有一个被点击的节点，则只执行该节点
        if len(selected) == 0 or (len(selected) == 1 and selected[0] == output_node):
            # 对于文本显示节点，使用"执行当前节点"的逻辑
            if is_text_display:
                self._on_node_execute_current(output_node)
            else:
                self._execute_workflow(output_node=output_node)
        else:
            # 多个选中，执行所有选中的节点
            for node in selected:
                is_text_node = hasattr(node, 'node_type') and node.node_type == 'text_display'
                if is_text_node:
                    self._on_node_execute_current(node)
                else:
                    self._execute_workflow(output_node=node)
    
    def _on_node_execute_current(self, node):
        """执行当前节点连接的上游节点：如果有多个输出/文本显示节点被选中，则并行执行所有选中的节点"""
        selected = [item for item in self.scene.selectedItems()
                    if hasattr(item, 'node_type') and item.node_type in ('output', 'text_display')]
        
        # 确保当前节点在选中列表中
        if node not in selected:
            selected.append(node)
        
        if len(selected) > 1:
            for selected_node in selected:
                self._execute_current_node(selected_node)
        else:
            self._execute_current_node(node)
    
    def _execute_current_node(self, node):
        """执行直接连接到该输出节点或文本显示节点的上游节点"""
        if not self.scene.nodes:
            QMessageBox.warning(self, "警告", "工作流中没有节点")
            return
        
        # 找到直接连接的上游API节点
        direct_api_node = None
        for socket in node.inputs:
            for edge in socket.edges:
                if edge.start_socket:
                    src_node = edge.start_socket.node
                    api_types = {"kling_api", "jimeng_api", "gemini_api", "veo_api", "seedance2_api", "image_edit", "text_vision"}
                    if src_node.node_type in api_types:
                        direct_api_node = src_node
                        break
            if direct_api_node:
                break
        
        if not direct_api_node:
            QMessageBox.warning(self, "警告", "该节点没有直接连接到API节点")
            return
        
        # 创建并提交任务，只执行该直接连接的API节点
        task_id = node.id
        existing = self.task_queue.tasks.get(task_id)
        if existing:
            from ui.task_queue import TaskState
            if existing["state"] == TaskState.RUNNING:
                node_name = node.get_output_name() if hasattr(node, 'get_output_name') else (node.title if hasattr(node, 'title') else '节点')
                self.statusBar().showMessage(f"⏳ {node_name} 正在执行中")
                return
            # 如果任务已经完成或失败,先清除它
            if existing["state"] in (TaskState.SUCCESS, TaskState.FAILED, TaskState.CANCELLED):
                self.task_queue.remove_finished()
        
        # 获取输出名称
        if hasattr(node, 'get_output_name'):
            output_name = node.get_output_name()
        elif hasattr(node, 'name_edit'):
            output_name = node.name_edit.text()
        else:
            output_name = 'text_output'
        
        # 检测任务类型
        type_label = "当前节点"
        if hasattr(self, '_detect_task_type') and hasattr(node, 'inputs'):
            try:
                type_label = self._detect_task_type(node)
            except:
                pass
        
        thread = ExecuteThread(
            self.scene, self.config, self.project_manager,
            output_node=node,
            direct_node=direct_api_node
        )
        thread.video_generated.connect(self._on_video_generated)
        thread.node_status_changed.connect(self._on_node_status_changed)
        thread.text_display_updated.connect(self._on_text_display_updated)
        
        self.task_queue.add_task(task_id, output_name, type_label, thread)
        self.stop_action.setEnabled(True)
        active = self.task_queue.active_count()
        self.statusBar().showMessage(f"🔄 {active} 个任务正在执行")
    
    def _go_back(self):
        self._save_workflow()
        if self.parent():
            self.parent().showNormal()  # 恢复主窗口
            self.parent()._load_projects()
        self.close()
    
    def _save_undo_state(self):
        state = self.scene.save_to_dict()
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
    
    def _undo(self):
        if self.undo_stack:
            current_state = self.scene.save_to_dict()
            self.redo_stack.append(current_state)
            
            state = self.undo_stack.pop()
            self.scene.load_from_dict(state, NODE_REGISTRY)
            self.statusBar().showMessage("已撤销")
    
    def _redo(self):
        if self.redo_stack:
            current_state = self.scene.save_to_dict()
            self.undo_stack.append(current_state)
            
            state = self.redo_stack.pop()
            self.scene.load_from_dict(state, NODE_REGISTRY)
            self.statusBar().showMessage("已重做")
    
    def _copy_nodes(self):
        selected_nodes = [item for item in self.scene.selectedItems() if hasattr(item, 'node_type')]
        if selected_nodes:
            selected_ids = {node.id for node in selected_nodes}
            
            nodes_data = []
            for node in selected_nodes:
                node_data = node.serialize()
                nodes_data.append(node_data)
            
            edges_data = []
            for edge in self.scene.edges:
                if edge.start_socket.node.id in selected_ids and edge.end_socket.node.id in selected_ids:
                    edges_data.append({
                        "start_node_id": edge.start_socket.node.id,
                        "start_socket_index": edge.start_socket.node.outputs.index(edge.start_socket),
                        "end_node_id": edge.end_socket.node.id,
                        "end_socket_index": edge.end_socket.node.inputs.index(edge.end_socket)
                    })
            
            self.clipboard_nodes = nodes_data
            self.clipboard_edges = edges_data
            # 清除系统剪贴板里可能残留的 TAPNOW_IMG:/TAPNOW_VID: 文本
            # 避免 Ctrl+V 时优先触发"从输出创建节点"逻辑
            from PyQt5.QtWidgets import QApplication
            _cb = QApplication.clipboard()
            if _cb.text().startswith("TAPNOW_IMG:") or _cb.text().startswith("TAPNOW_VID:"):
                _cb.clear()
            self.statusBar().showMessage(f"已复制 {len(selected_nodes)} 个节点和 {len(edges_data)} 条连线")
    
    def _paste_nodes(self):
        # 先检查是否有 TAPNOW 剪贴板内容（来自 OutputNode 的 "复制输出文件路径"）
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clip_text = clipboard.text()
        if clip_text.startswith("TAPNOW_IMG:") or clip_text.startswith("TAPNOW_VID:"):
            is_image = clip_text.startswith("TAPNOW_IMG:")
            file_path = clip_text[len("TAPNOW_IMG:"):] if is_image else clip_text[len("TAPNOW_VID:"):]
            if Path(file_path).exists():
                self._save_undo_state()
                cursor_pos = self.view.mapToScene(self.view.mapFromGlobal(self.cursor().pos()))
                if is_image:
                    node = ImageNode()
                    node.setPos(cursor_pos)
                    if hasattr(node, 'set_project_path'):
                        node.set_project_path(str(self.project_path))
                    node.load_image_file(file_path)
                else:
                    node = VideoNode()
                    node.setPos(cursor_pos)
                    if hasattr(node, 'set_project_path'):
                        node.set_project_path(str(self.project_path))
                    node.load_video_file(file_path)
                self._connect_node_signals(node)
                self.scene.add_node(node)
                self.statusBar().showMessage(f"已从输出粘贴为{'图片' if is_image else '视频'}上传节点")
                self._auto_save()
                return
        
        if self.clipboard_nodes:
            self._save_undo_state()
            
            cursor_pos = self.view.mapToScene(self.view.mapFromGlobal(self.cursor().pos()))
            
            min_x = min(node_data["pos"]["x"] for node_data in self.clipboard_nodes)
            min_y = min(node_data["pos"]["y"] for node_data in self.clipboard_nodes)
            
            id_map = {}
            import uuid
            import copy
            for node_data in self.clipboard_nodes:
                old_id = node_data["id"]
                new_id = str(uuid.uuid4())
                id_map[old_id] = new_id
                
                new_node_data = copy.deepcopy(node_data)
                new_node_data["id"] = new_id
                new_node_data["pos"]["x"] = cursor_pos.x() + (node_data["pos"]["x"] - min_x)
                new_node_data["pos"]["y"] = cursor_pos.y() + (node_data["pos"]["y"] - min_y)
                
                node_class = NODE_REGISTRY.get(new_node_data["type"])
                if node_class:
                    node = node_class()
                    node.deserialize(new_node_data)
                    if hasattr(node, 'set_project_path'):
                        node.set_project_path(str(self.project_path))
                    if hasattr(node, 'set_unique_name'):
                        existing_names = set()
                        for n in self.scene.nodes.values():
                            if hasattr(n, 'get_output_name'):
                                existing_names.add(n.get_output_name())
                        if hasattr(node, 'name_edit'):
                            existing_names.add(node.name_edit.text())
                        node.set_unique_name(existing_names)
                    if hasattr(node, 'on_execute_requested'):
                        node.on_execute_requested = self._on_node_execute
                    self._connect_node_signals(node)
                    self.scene.add_node(node)
                    id_map[old_id + "_node"] = node
            
            if hasattr(self, 'clipboard_edges') and self.clipboard_edges:
                for edge_data in self.clipboard_edges:
                    start_node = id_map.get(edge_data["start_node_id"] + "_node")
                    end_node = id_map.get(edge_data["end_node_id"] + "_node")
                    
                    if start_node and end_node:
                        from core.node_editor.edge import Edge
                        start_socket = start_node.outputs[edge_data["start_socket_index"]]
                        end_socket = end_node.inputs[edge_data["end_socket_index"]]
                        edge = Edge(start_socket, end_socket)
                        self.scene.add_edge(edge)
            
            self.statusBar().showMessage(f"已粘贴 {len(self.clipboard_nodes)} 个节点")
            self._auto_save()
    
    def _save_workflow(self):
        try:
            data = self.scene.save_to_dict()
            # 保存视口状态
            data["view_state"] = {
                "center_x": self.view.mapToScene(self.view.viewport().rect().center()).x(),
                "center_y": self.view.mapToScene(self.view.viewport().rect().center()).y(),
                "zoom": self.view._zoom
            }
            self.project_manager.save_workflow(data)
            self.statusBar().showMessage("工作流已保存")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败: {str(e)}")
    
    def _auto_save(self):
        """立即保存（由定时器触发或直接调用）"""
        try:
            data = self.scene.save_to_dict()
            # 保存视口状态
            data["view_state"] = {
                "center_x": self.view.mapToScene(self.view.viewport().rect().center()).x(),
                "center_y": self.view.mapToScene(self.view.viewport().rect().center()).y(),
                "zoom": self.view._zoom
            }
            self.project_manager.save_workflow(data)
        except Exception as e:
            print(f"自动保存失败: {e}")
    
    def _schedule_auto_save(self):
        """防抖：节点内容变化时重启定时器，2秒后才真正保存"""
        self._auto_save_timer.start()
    
    def _connect_node_signals(self, node):
        """连接节点内容变化信号到防抖自动保存"""
        if hasattr(node, 'prompt_edit'):
            node.prompt_edit.textChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'model_combo'):
            node.model_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'mode_combo'):
            node.mode_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'resolution_combo'):
            node.resolution_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'duration_combo'):
            node.duration_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'aspect_ratio_combo'):
            node.aspect_ratio_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'cfg_slider'):
            node.cfg_slider.valueChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'name_edit'):
            node.name_edit.editingFinished.connect(self._schedule_auto_save)
        if hasattr(node, 'seed_spin'):
            node.seed_spin.valueChanged.connect(self._schedule_auto_save)
        # ImageEditNode 专有控件
        if hasattr(node, 'sr_resolution_combo'):
            node.sr_resolution_combo.currentIndexChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'sr_scale_slider'):
            node.sr_scale_slider.valueChanged.connect(self._schedule_auto_save)
        if hasattr(node, 'inpaint_seed_spin'):
            node.inpaint_seed_spin.valueChanged.connect(self._schedule_auto_save)
        if hasattr(node, '_expand_sliders'):
            for slider in node._expand_sliders.values():
                slider.valueChanged.connect(self._schedule_auto_save)
    
    def _load_workflow(self):
        self._loading_step = 0
        self._loading_data = None
        self._do_load_step_1()
    
    def _do_load_step_1(self):
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #1e3a5f;
                color: #90CAF9;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self.statusBar().showMessage("⏳ 正在加载工作流...")
        QTimer.singleShot(50, self._do_load_step_2)
    
    def _do_load_step_2(self):
        try:
            self._loading_data = self.project_manager.load_workflow()
            QTimer.singleShot(10, self._do_load_step_3)
        except Exception as e:
            print(f"加载工作流失败: {str(e)}")
            self.statusBar().setStyleSheet("""
                QStatusBar {
                    background-color: #5f1e1e;
                    color: #EF9A9A;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                    padding: 4px 10px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            self.statusBar().showMessage(f"❌ 加载工作流失败: {str(e)}")
    
    def _do_load_step_3(self):
        if self._loading_data:
            self.scene.load_from_dict(self._loading_data, NODE_REGISTRY)
            QTimer.singleShot(10, self._do_load_step_4)
        else:
            self._finish_loading()
    
    def _do_load_step_4(self):
        for node in self.scene.nodes.values():
            if hasattr(node, 'set_project_path'):
                node.set_project_path(str(self.project_path))
            if hasattr(node, 'on_execute_requested'):
                node.on_execute_requested = self._on_node_execute
            if hasattr(node, 'on_execute_current_requested'):
                node.on_execute_current_requested = self._on_node_execute_current
            self._connect_node_signals(node)
        QTimer.singleShot(10, self._do_load_step_5)
    
    def _do_load_step_5(self):
        if "view_state" in self._loading_data:
            view_state = self._loading_data["view_state"]
            if "center_x" in view_state and "center_y" in view_state:
                self.view.centerOn(view_state["center_x"], view_state["center_y"])
            if "zoom" in view_state:
                zoom = view_state["zoom"]
                self.view._zoom = zoom
                self.view.resetTransform()
                self.view.scale(zoom, zoom)
        QTimer.singleShot(10, self._finish_loading)
    
    def _finish_loading(self):
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #1a3d1a;
                color: #81C784;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: bold;
            }
        """)
        self.statusBar().showMessage("✅ 工作流已加载")
        QTimer.singleShot(2000, lambda: self._restore_status_bar())
    
    def _restore_status_bar(self):
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 4px 10px;
                font-size: 13px;
            }
        """)
        self.statusBar().showMessage(f"项目: {self.project_path.name}")
    
    def _get_root_output_nodes(self, all_outputs):
        """从所有 OutputNode 中找出链的根节点（不被其他 OutputNode 的输出链覆盖的节点）。
        例如：OutputNode1 → ImageEdit → OutputNode2，OutputNode2 是下游，
        执行全部时只需为 OutputNode1 创建线程，它会自动覆盖整条链。
        """
        # 收集所有被其他 OutputNode 通过输出链可达的 OutputNode id
        downstream_ids = set()
        def dfs_downstream(node, origin_id, visited):
            if node.id in visited:
                return
            visited.add(node.id)
            for socket in node.outputs:
                for edge in socket.edges:
                    if edge.end_socket:
                        nxt = edge.end_socket.node
                        if nxt.node_type == "output" and nxt.id != origin_id:
                            downstream_ids.add(nxt.id)
                        dfs_downstream(nxt, origin_id, visited)
        for out_node in all_outputs:
            dfs_downstream(out_node, out_node.id, set())
        return [n for n in all_outputs if n.id not in downstream_ids]

    def _execute_selected_or_all(self):
        """工具栏执行：选中节点中有OutputNode则依次执行它们，否则执行全部"""
        selected = [item for item in self.scene.selectedItems() if hasattr(item, 'node_type')]
        selected_output_nodes = [n for n in selected if n.node_type == 'output']
        if selected_output_nodes:
            # 选中节点中也只执行根节点，避免链的下游被单独重复执行
            root_selected = self._get_root_output_nodes(selected_output_nodes)
            for out_node in root_selected:
                self._execute_workflow(output_node=out_node)
        else:
            # 收集所有 OutputNode，只对链的根节点创建线程
            # 下游 OutputNode 由根节点的链式执行自动覆盖，避免重复 API 调用和竞争
            all_outputs = [n for n in self.scene.nodes.values() if n.node_type == 'output']
            if not all_outputs:
                QMessageBox.warning(self, "警告", "工作流中没有输出节点")
                return
            root_outputs = self._get_root_output_nodes(all_outputs)
            for out_node in root_outputs:
                self._execute_workflow(output_node=out_node)

    def _execute_workflow(self, output_node=None, output_nodes=None):
        """为每个输出节点创建独立任务并提交到队列"""
        if not self.scene.nodes:
            QMessageBox.warning(self, "警告", "工作流中没有节点")
            return
        
        # 收集要执行的输出节点列表
        if output_nodes:
            targets = output_nodes
        elif output_node:
            targets = [output_node]
        else:
            targets = [n for n in self.scene.nodes.values() if n.node_type == 'output']
        
        for out_node in targets:
            task_id = out_node.id
            # 如果同一输出节点已在运行中，跳过
            existing = self.task_queue.tasks.get(task_id)
            if existing and existing["state"].name == "RUNNING":
                self.statusBar().showMessage(f"⏳ {out_node.get_output_name()} 正在执行中")
                continue
            
            output_name = out_node.get_output_name()
            type_label = self._detect_task_type(out_node)
            
            thread = ExecuteThread(
                self.scene, self.config, self.project_manager,
                output_node=out_node
            )
            thread.video_generated.connect(self._on_video_generated)
            thread.node_status_changed.connect(self._on_node_status_changed)
            thread.text_display_updated.connect(self._on_text_display_updated)
            
            self.task_queue.add_task(task_id, output_name, type_label, thread)
        
        self.stop_action.setEnabled(True)
        active = self.task_queue.active_count()
        self.statusBar().showMessage(f"🔄 {active} 个任务正在执行")
    
    def _detect_task_type(self, output_node):
        """检测输出节点或文本显示节点的上游API类型，用于队列显示"""
        for socket in output_node.inputs:
            for edge in socket.edges:
                if edge.start_socket:
                    src = edge.start_socket.node
                    if src.node_type == "kling_api":
                        return "可灵生视频"
                    elif src.node_type == "jimeng_api":
                        return "即梦生视频"
                    elif src.node_type == "gemini_api":
                        return "香蕉生图"
                    elif src.node_type == "veo_api":
                        return "Veo生视频"
                    elif src.node_type == "seedance2_api":
                        return "Seedance 2.0"
                    elif src.node_type == "image_edit":
                        mode = getattr(src, 'edit_mode', '图片修改')
                        return mode
                    elif src.node_type == "text_vision":
                        return "文本识图"
        return "工作流"
    
    def _on_active_count_changed(self, count):
        """队列中运行任务数变化"""
        self.stop_action.setEnabled(count > 0)
        if count > 0:
            self.statusBar().showMessage(f"🔄 {count} 个任务正在执行")
        # 更新队列按钮文字
        self.queue_action.setText(f"📋 队列({count})" if count > 0 else "📋 队列")
    
    def _on_queue_empty(self):
        """所有任务完成"""
        self.statusBar().showMessage("✅ 所有任务已完成")
        self.stop_action.setEnabled(False)

    def _on_task_stopped(self, task_id):
        """任务被用户停止，更新输出节点状态为 cancelled"""
        node = self.scene.get_node_by_id(task_id)
        if node and hasattr(node, 'set_execution_status'):
            node.set_execution_status('cancelled')

    def _on_node_status_changed(self, node_id, status):
        """更新节点的执行状态颜色"""
        node = self.scene.get_node_by_id(node_id)
        if not node:
            return
        # Gemini 节点生成完成，更新预览
        if status.startswith("gemini_done:"):
            image_path = status[len("gemini_done:"):]
            if hasattr(node, 'set_generated_image'):
                node.set_generated_image(image_path)
            return
        if hasattr(node, 'set_execution_status'):
            node.set_execution_status(status)
    
    def _on_text_display_updated(self, node_id, text, tokens):
        """更新文本显示节点的内容（跨线程安全）"""
        node = self.scene.get_node_by_id(node_id)
        if not node:
            return
        if hasattr(node, 'set_display_text'):
            node.set_display_text(text, tokens)
    
    def _on_video_generated(self, video_path, node_id):
        node = self.scene.get_node_by_id(node_id)
        if not node or not hasattr(node, 'set_video_thumbnail'):
            return
        if video_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp')):
            # 图片输出：生成小 JPEG 缩略图，避免加载全尺寸大图很卡
            thumb_path = str(Path(video_path).with_suffix('')) + "_thumb.jpg"
            ok = _make_image_thumbnail(video_path, thumb_path)
            if ok and Path(thumb_path).exists():
                node.set_video_thumbnail(thumb_path, video_path)
            else:
                # 回退：直接加载原图
                node.set_video_thumbnail(video_path, video_path)
        else:
            thumb_path = video_path.replace(".mp4", "_thumb.jpg")
            node.set_video_thumbnail(thumb_path, video_path)
    
    def _open_settings(self):
        dialog = APISettingsDialog(self)
        dialog.exec_()
    
    def _stop_all_tasks(self):
        """停止所有正在执行的任务"""
        self.task_queue.stop_all()
        self.statusBar().showMessage("正在停止所有任务...")
        self.stop_action.setEnabled(False)
    
    def _open_queue_dialog(self):
        """打开任务队列查看器"""
        if self._queue_dialog is None or not self._queue_dialog.isVisible():
            self._queue_dialog = QueueDialog(self.task_queue, self)
            self._queue_dialog.locate_node_requested.connect(self._locate_node_by_task_id)
        self._queue_dialog.show()
        self._queue_dialog.raise_()
        self._queue_dialog.activateWindow()
    
    def _locate_node_by_task_id(self, task_id):
        """根据任务ID定位到对应节点"""
        node = self.scene.nodes.get(task_id)
        if node:
            # 计算节点中心位置
            center_x = node.pos().x() + node.width / 2
            center_y = node.pos().y() + node.height / 2
            
            # 将视口中心移动到节点
            self.view.centerOn(center_x, center_y)
            
            # 选中该节点
            self.scene.clearSelection()
            node.setSelected(True)
    
    def closeEvent(self, event):
        # 关闭前保存工作流
        self._auto_save_timer.stop()
        self._auto_save()
        
        self.task_queue.stop_all()
        # 等待所有线程结束
        for t in self.task_queue.tasks.values():
            thread = t.get("thread")
            if thread and thread.isRunning():
                thread.wait(3000)
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self._delete_selected()
        super().keyPressEvent(event)
    
    def _delete_selected(self):
        selected = self.scene.selectedItems()
        if selected:
            self._save_undo_state()
            for item in selected:
                if hasattr(item, 'node_type'):
                    self.scene.remove_node(item)
                elif hasattr(item, 'edge_type'):
                    item.remove()
            self._auto_save()
    
    def _load_template(self, template_id):
        template = get_template(template_id)
        if template:
            self._pending_template = template
            self._pending_template_id = template_id
            self.statusBar().showMessage(f"已选择模板 '{template['name']}'，请点击画布放置")
            self.view.setCursor(Qt.CrossCursor)
            self.view.viewport().setCursor(Qt.CrossCursor)
    
    def _place_template_at(self, pos):
        if hasattr(self, '_pending_template') and self._pending_template:
            template = self._pending_template
            self._save_undo_state()
            
            data = template["data"]
            node_id_map = {}  # 旧ID -> 新节点
            
            nodes_data = data.get("nodes", [])
            if nodes_data:
                min_x = min(node_data["pos"]["x"] for node_data in nodes_data)
                min_y = min(node_data["pos"]["y"] for node_data in nodes_data)
            else:
                min_x, min_y = 0, 0
            
            import uuid
            for node_data in nodes_data:
                node_type = node_data.get("type")
                node_class = NODE_REGISTRY.get(node_type)
                if node_class:
                    node = node_class()
                    # 生成新的唯一ID，避免重复
                    old_id = node_data["id"]
                    new_id = str(uuid.uuid4())
                    
                    node_data_copy = node_data.copy()
                    node_data_copy["id"] = new_id
                    node_data_copy["pos"]["x"] = pos.x() + (node_data["pos"]["x"] - min_x)
                    node_data_copy["pos"]["y"] = pos.y() + (node_data["pos"]["y"] - min_y)
                    node.deserialize(node_data_copy)
                    if hasattr(node, 'set_project_path'):
                        node.set_project_path(str(self.project_path))
                    if hasattr(node, 'set_unique_name'):
                        existing_names = set()
                        for n in self.scene.nodes.values():
                            if hasattr(n, 'get_output_name'):
                                existing_names.add(n.get_output_name())
                        if hasattr(node, 'name_edit'):
                            existing_names.add(node.name_edit.text())
                        node.set_unique_name(existing_names)
                    if hasattr(node, 'on_execute_requested'):
                        node.on_execute_requested = self._on_node_execute
                    self._connect_node_signals(node)
                    node_id_map[old_id] = node  # 使用旧ID作为key，映射到新节点
                    self.scene.add_node(node)
            
            for edge_data in data.get("edges", []):
                start_node_id = edge_data.get("start_node")
                end_node_id = edge_data.get("end_node")
                start_socket_index = edge_data.get("start_socket")
                end_socket_index = edge_data.get("end_socket")
                
                start_node = node_id_map.get(start_node_id)
                end_node = node_id_map.get(end_node_id)
                
                if start_node and end_node:
                    from core.node_editor.edge import Edge
                    start_socket = start_node.outputs[start_socket_index]
                    end_socket = end_node.inputs[end_socket_index]
                    edge = Edge(start_socket, end_socket)
                    self.scene.add_edge(edge)
            
            self.statusBar().showMessage(f"已放置模板: {template['name']}")
            self._pending_template = None
            self._pending_template_id = None
            self.view.setCursor(Qt.ArrowCursor)
            self.view.viewport().setCursor(Qt.ArrowCursor)
            self._auto_save()
