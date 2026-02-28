import time
import base64
import requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class VeoAPI:
    """Google Veo 视频生成 API

    通过 Gemini API 密钥（与香蕉生图共用）调用 Veo 视频生成服务。
    支持图生视频（image_to_video）和首尾帧（first_last_frame）两种模式。

    API 端点（Google AI / Gemini 系）：
      提交: POST {BASE_URL}/models/{model}:predictLongRunning?key={api_key}
      轮询: GET  {BASE_URL}/{operation_name}?key={api_key}
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self):
        self.api_key = ""
        self._base_url = self.BASE_URL
        self._session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def set_credentials(self, api_key: str, base_url: str = "", **kwargs):
        """设置 API 密钥（与香蕉模型共用）
        
        注意：Veo API 不支持中转服务，始终使用官方 Google API 地址。
        如果配置了中转地址，会提示用户 Veo 需要直连官方 API。
        """
        self.api_key = api_key
        # Veo API 不支持中转，始终使用官方地址
        self._using_proxy = False
        if base_url and base_url.strip() and base_url.strip() != self.BASE_URL:
            self._using_proxy = True
            print(f"[Veo] 警告: Veo API 不支持中转服务，将使用官方地址 {self.BASE_URL}")
        self._base_url = self.BASE_URL

    # ------------------------------------------------------------------ #
    #  图片编码
    # ------------------------------------------------------------------ #

    def _encode_image(self, image_path: str):
        """读取图片文件，返回 (base64_str, mime_type)"""
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
        return b64, mime_type

    # ------------------------------------------------------------------ #
    #  提交任务
    # ------------------------------------------------------------------ #

    def submit_video_task(
        self,
        prompt: str = "",
        image_path: str = None,
        last_frame_path: str = None,
        model: str = "veo-3.1-generate-001",
        # model: str = "veo_3.1",
        duration_seconds: int = 8,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        generate_audio: bool = False,
        sample_count: int = 1,
    ) -> str:
        """提交 Veo 视频生成任务，返回 operation_name（字符串）

        支持：
          - 仅提示词（文生视频）
          - 图片 + 提示词（图生视频）
          - 图片 + 尾帧图片 + 提示词（首尾帧）

        Returns:
            operation_name: 如 "models/veo-3.1-generate-001/operations/xxxxxx"
        """
        instance: dict = {}
        if prompt:
            instance["prompt"] = prompt

        if image_path and Path(image_path).exists():
            b64, mime = self._encode_image(image_path)
            instance["image"] = {"bytesBase64Encoded": b64, "mimeType": mime}

        if last_frame_path and Path(last_frame_path).exists():
            b64, mime = self._encode_image(last_frame_path)
            instance["lastFrame"] = {"bytesBase64Encoded": b64, "mimeType": mime}

        parameters: dict = {
            "durationSeconds": duration_seconds,
            "aspectRatio": aspect_ratio,
            "sampleCount": sample_count,
        }
        # resolution 仅 Veo 3 支持
        if "veo-3" in model or "veo-2.0" not in model:
            parameters["resolution"] = resolution
        # generateAudio: Veo 3 必填，Veo 2 不支持
        if "veo-2" not in model:
            parameters["generateAudio"] = generate_audio

        body = {
            "instances": [instance],
            "parameters": parameters,
        }

        url = f"{self._base_url}/models/{model}:predictLongRunning?key={self.api_key}"
        print(f"[Veo] 提交任务: {self._base_url}/models/{model}:predictLongRunning?key=***")

        resp = self._session.post(url, json=body, timeout=(20, 120))
        if resp.status_code != 200:
            try:
                err = resp.json()
                msg = err.get("error", {}).get("message", resp.text[:400])
            except Exception:
                msg = resp.text[:400]
            raise Exception(f"Veo API 错误 (HTTP {resp.status_code}): {msg}")

        try:
            data = resp.json()
        except Exception:
            raise Exception(f"Veo API 返回非 JSON 格式: {resp.text[:400]}")

        operation_name = data.get("name", "")
        if not operation_name:
            raise Exception(f"Veo API 未返回操作名称，响应: {str(data)[:400]}")

        print(f"[Veo] 操作名称: {operation_name}")
        return operation_name

    # ------------------------------------------------------------------ #
    #  轮询操作
    # ------------------------------------------------------------------ #

    def _poll_operation(self, operation_name: str):
        """轮询一次操作状态

        Returns:
            (done: bool, video_base64: str)
            done=True 且 video_base64 非空表示成功完成
            done=True 且 video_base64 为空表示完成但无视频（可能被 RAI 过滤）
        """
        # operation_name 格式: "models/{model}/operations/{op_id}"
        # 拼出完整 URL: {base_url}/{operation_name}?key={api_key}
        url = f"{self._base_url}/{operation_name}?key={self.api_key}"

        resp = self._session.get(url, timeout=(15, 60))
        if resp.status_code != 200:
            print(f"[Veo] 轮询返回 HTTP {resp.status_code}: {resp.text[:200]}")
            return False, ""

        try:
            data = resp.json()
        except Exception:
            return False, ""

        done = data.get("done", False)
        if not done:
            return False, ""

        # 操作已完成，提取视频数据
        error = data.get("error")
        if error:
            raise Exception(f"Veo 操作失败: {error.get('message', str(error))}")

        response = data.get("response", {})
        rai_count = response.get("raiMediaFilteredCount", 0)
        if rai_count and rai_count > 0:
            raise Exception(
                f"视频被 Responsible AI 内容政策过滤（{rai_count} 个）。"
                "请修改提示词或图片后重试。"
            )

        videos = response.get("videos", [])
        if videos:
            video_b64 = videos[0].get("bytesBase64Encoded", "")
            if video_b64:
                return True, video_b64

        # 完成但无 base64（可能已写入 GCS，但我们没有提供 storageUri）
        return True, ""

    # ------------------------------------------------------------------ #
    #  等待完成
    # ------------------------------------------------------------------ #

    def wait_for_completion(
        self,
        operation_name: str,
        timeout: int = 600,
        is_stopped=None,
    ) -> str:
        """持续轮询直到视频生成完成

        Returns:
            base64 编码的 MP4 视频数据字符串；失败或被停止时返回 ""
        """
        start = time.time()
        poll_interval = 6  # 初始轮询间隔（秒）

        while True:
            if is_stopped and is_stopped():
                return ""
            if time.time() - start > timeout:
                raise Exception(f"Veo 视频生成超时（已等待 {timeout}s）")

            try:
                done, video_b64 = self._poll_operation(operation_name)
                if done:
                    return video_b64
            except Exception as e:
                raise Exception(f"轮询 Veo 操作状态失败: {e}")

            # 可中断地等待
            for _ in range(poll_interval):
                if is_stopped and is_stopped():
                    return ""
                time.sleep(1)

            # 渐进增加轮询间隔（最多 30s）
            poll_interval = min(poll_interval + 3, 30)
