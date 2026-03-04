import time
import base64
import requests
from pathlib import Path
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Veo3API:
    """Veo3 视频生成 API
    
    支持多种 Veo 模型：
      - veo2, veo2-fast, veo2-fast-frames, veo2-fast-components, veo2-pro
      - veo3, veo3-fast, veo3-pro, veo3-pro-frames, veo3-fast-frames, veo3-frames
    
    特性：
      - 支持中文提示词自动转英文（enhance_prompt）
      - 支持图片输入（图生视频、首尾帧）
      - 支持超分（enable_upsample）
    """

    BASE_URL = "https://api.vectorengine.ai"

    def __init__(self):
        self.api_key = ""
        self._session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def set_credentials(self, api_key: str, **kwargs):
        """设置 API 密钥"""
        self.api_key = api_key

    def _encode_image_to_base64(self, image_path: str) -> str:
        """将本地图片编码为 base64 data URL"""
        path = Path(image_path)
        suffix = path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")
        with open(str(image_path), "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"

    def submit_video_task(
        self,
        prompt: str = "",
        model: str = "veo_3_1",
        images: list = None,
        enhance_prompt: bool = True,
        enable_upsample: bool = True,
        aspect_ratio: str = "16:9",
    ) -> str:
        """提交 Veo3 视频生成任务，返回任务 ID
        
        Args:
            prompt: 提示词（支持中文，会自动转英文）
            model: 模型名称
            images: 图片路径列表
            enhance_prompt: 是否增强提示词（中文转英文）
            enable_upsample: 是否启用超分
            aspect_ratio: 宽高比，"16:9" 或 "9:16"
        
        Returns:
            task_id: 任务 ID，用于轮询结果
        """
        body = {
            "prompt": prompt,
            "model": model,
            "enhance_prompt": enhance_prompt,
            "enable_upsample": enable_upsample,
        }

        # veo3 系列和 veo_3_1 支持 aspect_ratio
        if "veo3" in model or model == "veo_3_1":
            body["aspect_ratio"] = aspect_ratio

        # 处理图片输入
        if images:
            image_urls = []
            for img_path in images:
                if img_path and Path(img_path).exists():
                    data_url = self._encode_image_to_base64(img_path)
                    image_urls.append(data_url)
                elif img_path.startswith("http"):
                    image_urls.append(img_path)
            if image_urls:
                body["images"] = image_urls

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.BASE_URL}/v1/video/create"
        print(f"[Veo3] 提交任务: {url} model={model}")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._session.post(url, headers=headers, json=body, timeout=(30, 180))
                
                if resp.status_code != 200:
                    try:
                        err = resp.json()
                        msg = err.get("error") or err.get("message") or ""
                        if isinstance(msg, dict):
                            msg = msg.get("message", str(msg))
                        if not msg:
                            msg = resp.text[:400]
                    except Exception:
                        msg = resp.text[:400]
                    raise Exception(f"Veo3 API 错误 (HTTP {resp.status_code}): {msg}")

                try:
                    data = resp.json()
                except Exception:
                    raise Exception(f"Veo3 API 返回非 JSON 格式: {resp.text[:400]}")

                task_id = data.get("id", "")
                if not task_id:
                    raise Exception(f"Veo3 API 未返回任务 ID，响应: {str(data)[:400]}")

                print(f"[Veo3] 任务 ID: {task_id}")
                return task_id

            except (requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError) as e:
                if attempt < max_attempts:
                    wait = 5 * attempt
                    print(f"[Veo3] 网络错误(第{attempt}次): {e}，{wait}秒后重试")
                    time.sleep(wait)
                    continue
                raise Exception(f"Veo3 API 网络错误，重试{max_attempts}次后失败: {e}")

        raise Exception("Veo3 API 超过最大重试次数")

    def get_task_status(self, task_id: str) -> dict:
        """查询任务状态
        
        Returns:
            {
                "status": "pending" | "processing" | "completed" | "failed",
                "video_url": str | None,  # 完成时的视频 URL
                "error": str | None       # 失败时的错误信息
            }
        """
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # 查询结果 URL（使用 query 参数）
        url = f"{self.BASE_URL}/v1/video/query?id={task_id}"
        print(f"[Veo3] 查询任务状态: {url}")
        print(f"[Veo3] 原始 task_id: {task_id}")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._session.get(url, headers=headers, timeout=(30, 120))

                if resp.status_code != 200:
                    try:
                        err = resp.json()
                        msg = err.get("error", {}).get("message", resp.text[:400])
                    except Exception:
                        msg = resp.text[:400]
                    return {"status": "failed", "error": f"HTTP {resp.status_code}: {msg}"}

                try:
                    data = resp.json()
                except Exception:
                    return {"status": "failed", "error": "非 JSON 响应"}

                status = data.get("status", "pending")
                result = {"status": status}

                if status == "completed":
                    # 尝试从响应中获取视频 URL
                    # 1. 根级别 video_url
                    video_url = data.get("video_url")
                    # 2. detail.video_url 或 detail.upsample_video_url
                    if not video_url and "detail" in data:
                        detail = data.get("detail", {})
                        video_url = detail.get("upsample_video_url") or detail.get("video_url")
                    # 3. 其他可能的字段
                    if not video_url:
                        video_url = data.get("output_url") or data.get("url")
                    # 4. choices 数组
                    if not video_url and "choices" in data:
                        choices = data.get("choices", [])
                        if choices:
                            video_url = choices[0].get("video_url") or choices[0].get("url")
                    result["video_url"] = video_url
                elif status == "failed":
                    # 尝试获取错误信息
                    error_msg = data.get("error") or data.get("error_message")
                    if not error_msg and "detail" in data:
                        detail = data.get("detail", {})
                        error_msg = detail.get("error_message") or detail.get("video_generation_error")
                    # 如果 error_msg 是字典，提取 message
                    if isinstance(error_msg, dict):
                        error_msg = error_msg.get("message") or str(error_msg)
                    # 尝试从 message 字段获取
                    if not error_msg:
                        error_msg = data.get("message")
                    result["error"] = error_msg or "未知错误"

                return result

            except (requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError) as e:
                if attempt < max_attempts:
                    wait = 3 * attempt
                    print(f"[Veo3] 查询网络错误(第{attempt}次): {e}，{wait}秒后重试")
                    time.sleep(wait)
                    continue
                return {"status": "failed", "error": f"网络错误: {e}"}

        return {"status": "failed", "error": "超过最大重试次数"}

    def wait_for_completion(
        self,
        task_id: str,
        timeout: int = 600,
        is_stopped=None,
    ) -> str:
        """持续轮询直到视频生成完成
        
        Returns:
            视频 URL 字符串；失败或被停止时返回 ""
        """
        start = time.time()
        poll_interval = 6

        while True:
            if is_stopped and is_stopped():
                return ""
            if time.time() - start > timeout:
                raise Exception(f"Veo3 视频生成超时（已等待 {timeout}s）")

            try:
                result = self.get_task_status(task_id)
                status = result.get("status")

                if status == "completed":
                    video_url = result.get("video_url")
                    if video_url:
                        return video_url
                    else:
                        raise Exception("任务完成但未返回视频 URL")
                elif status == "failed":
                    raise Exception(f"视频生成失败: {result.get('error', '未知错误')}")

            except Exception as e:
                if "超时" in str(e) or "失败" in str(e):
                    raise
                print(f"[Veo3] 轮询错误: {e}")

            # 可中断地等待
            for _ in range(poll_interval):
                if is_stopped and is_stopped():
                    return ""
                time.sleep(1)

            # 渐进增加轮询间隔（最多 30s）
            poll_interval = min(poll_interval + 3, 30)
