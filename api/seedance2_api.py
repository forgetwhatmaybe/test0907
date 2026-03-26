"""Seedance 2.0 API - 通过 EvoLink 中转调用 Seedance 2.0 视频生成"""

import requests
import time
from typing import Optional, List
from .base_api import BaseAPI, TaskStatus


class Seedance2API(BaseAPI):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api.evolink.ai"
        self._session = self._create_retry_session()

    @staticmethod
    def _create_retry_session():
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def set_credentials(self, api_key: str, secret_key: str = ""):
        self.api_key = api_key
        # secret_key 不需要，Seedance2 使用 Bearer Token

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def test_connection(self) -> bool:
        try:
            if not self.api_key:
                return False
            # 尝试提交一个最小请求来测试连接
            payload = {
                "model": "seedance-2.0",
                "prompt": "test"
            }
            response = self._session.post(
                f"{self.base_url}/v1/videos/generations",
                headers=self._get_headers(),
                json=payload,
                timeout=(10, 15)
            )
            if response.status_code in [200, 201]:
                return True
            if response.status_code == 401:
                print(f"Seedance2API test_connection: 401 Unauthorized")
                return False
            if response.status_code == 429:
                return True  # 限流但 key 有效
            # 其他状态码，尝试解析
            try:
                result = response.json()
                if "id" in result:
                    return True
                error = result.get("error", {})
                if isinstance(error, dict) and error.get("code") in ["invalid_api_key", "authentication_error"]:
                    return False
            except Exception:
                pass
            return response.status_code < 500
        except requests.exceptions.Timeout:
            raise Exception("连接超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise Exception("网络连接失败，请检查网络设置")
        except Exception:
            raise

    def submit_video_task(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        video_urls: Optional[List[str]] = None,
        audio_urls: Optional[List[str]] = None,
        duration: int = 5,
        quality: str = "720p",
        aspect_ratio: str = "16:9",
        generate_audio: bool = True,
        **kwargs
    ) -> str:
        """提交视频生成任务

        Args:
            prompt: 文本描述（最多2000 tokens），支持 @tag 引用
            image_urls: 参考图片 URL 列表（最多9张）
            video_urls: 参考视频 URL 列表（最多3个）
            audio_urls: 参考音频 URL 列表（最多3个）
            duration: 视频时长（4-15秒）
            quality: 分辨率（480p/720p/1080p）
            aspect_ratio: 画面比例
            generate_audio: 是否生成同步音频
        """
        payload = {
            "model": "seedance-2.0",
            "prompt": prompt,
            "duration": duration,
            "quality": quality,
            "aspect_ratio": aspect_ratio,
            "generate_audio": generate_audio,
        }
        if image_urls:
            payload["image_urls"] = image_urls[:9]
        if video_urls:
            payload["video_urls"] = video_urls[:3]
        if audio_urls:
            payload["audio_urls"] = audio_urls[:3]

        response = self._session.post(
            f"{self.base_url}/v1/videos/generations",
            headers=self._get_headers(),
            json=payload,
            timeout=(15, 60)
        )

        # 处理限流
        if response.status_code == 429:
            max_retries = 6
            for attempt in range(max_retries):
                wait = 30 * (attempt + 1)
                print(f"Seedance 2.0 限流(HTTP 429), {wait}秒后重试({attempt+1}/{max_retries})")
                if hasattr(self, '_on_rate_limit'):
                    self._on_rate_limit(wait, "请求过快，超出并发限制", attempt + 1, max_retries)
                time.sleep(wait)
                response = self._session.post(
                    f"{self.base_url}/v1/videos/generations",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=(15, 60)
                )
                if response.status_code in [200, 201]:
                    break
                elif response.status_code != 429:
                    break
            if response.status_code == 429:
                raise Exception("Seedance 2.0 提交任务失败: 并发数不足，多次等待后仍无法提交")

        if response.status_code in [200, 201]:
            result = response.json()
            task_id = result.get("id", "")
            if task_id:
                return task_id
            raise Exception(f"Seedance 2.0 返回结果缺少任务ID: {result}")
        else:
            try:
                result = response.json()
                error_msg = result.get("error", {}).get("message", response.text[:500])
            except Exception:
                error_msg = response.text[:500]
            raise Exception(f"Seedance 2.0 提交任务失败: HTTP {response.status_code} - {error_msg}")

    def get_task_status(self, task_id: str) -> TaskStatus:
        response = self._session.get(
            f"{self.base_url}/v1/tasks/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        if response.status_code == 200:
            result = response.json()
            status = result.get("status", "")
            status_map = {
                "pending": TaskStatus.PENDING,
                "processing": TaskStatus.RUNNING,
                "completed": TaskStatus.SUCCESS,
                "failed": TaskStatus.FAILED,
            }
            return status_map.get(status, TaskStatus.PENDING)
        return TaskStatus.FAILED

    def get_task_result(self, task_id: str) -> Optional[str]:
        response = self._session.get(
            f"{self.base_url}/v1/tasks/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        if response.status_code == 200:
            result = response.json()
            data = result.get("results")
            if data and isinstance(data, list) and data:
                return data[0]  # 第一个结果 URL
        return None