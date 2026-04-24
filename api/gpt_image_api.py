import base64
import mimetypes
from pathlib import Path
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GPTImageAPI:
    """GPT 图片生成 API，支持文生图与图生图。"""

    BASE_URL = "https://api.vectorengine.ai"
    DEFAULT_MODEL = "gpt-image-2-all"

    def __init__(self):
        self.api_key = ""
        self._base_url = self.BASE_URL
        self._session = self._create_retry_session()

    def _create_retry_session(self):
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def set_credentials(self, api_key: str, base_url: str = "", **kwargs):
        self.api_key = api_key
        if base_url and base_url.strip():
            self._base_url = base_url.strip().rstrip("/")

    def test_connection(self) -> bool:
        try:
            url = f"{self._base_url}/v1/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = self._session.get(url, headers=headers, timeout=(10, 30))
            if resp.status_code == 200:
                return True
            if resp.status_code in (401, 403):
                raise Exception("API 密钥无效或无权限")
            raise Exception(f"API 返回错误: HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到 API，请检查网络")
        except requests.exceptions.Timeout:
            raise Exception("连接超时，请检查网络")

    def generate_image(
        self,
        prompt: str,
        image_paths: List[str] = None,
        model: str = "gpt-image-2",
        aspect_ratio: str = "1:1",
        image_size: str = "2K",
        save_path: str = "output.png",
        is_stopped=None,
    ) -> Optional[str]:
        if is_stopped and is_stopped():
            return None

        payload = {
            "size": self._build_size(aspect_ratio, image_size),
            "prompt": self._build_prompt(prompt),
            "model": self._normalize_model(model),
            "n": 1,
        }

        if image_paths:
            return self._edit_image(payload, image_paths, save_path, is_stopped)
        return self._generate_image(payload, save_path, is_stopped)

    def _generate_image(self, payload: dict, save_path: str, is_stopped=None) -> Optional[str]:
        url = f"{self._base_url}/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        resp = self._session.post(url, json=payload, headers=headers, timeout=(15, 180))
        if is_stopped and is_stopped():
            return None
        if resp.status_code != 200:
            raise Exception(f"GPT 生图失败 (HTTP {resp.status_code}): {self._safe_get_error_message(resp)}")
        return self._extract_and_save_image(resp.json(), save_path)

    def _edit_image(self, payload: dict, image_paths: List[str], save_path: str, is_stopped=None) -> Optional[str]:
        valid_image_paths = [p for p in (image_paths or []) if p and Path(p).exists()]
        if not valid_image_paths:
            return self._generate_image(payload, save_path, is_stopped)

        url = f"{self._base_url}/v1/images/edits"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        files = []
        file_handles = []
        try:
            for image_path in valid_image_paths:
                handle = open(image_path, "rb")
                file_handles.append(handle)
                files.append((
                    "image",
                    (
                        str(Path(image_path).resolve()),
                        handle,
                        mimetypes.guess_type(str(Path(image_path).resolve()))[0] or "application/octet-stream",
                    ),
                ))

            response = requests.request(
                "POST",
                url,
                headers=headers,
                data=payload,
                files=files,
                timeout=(15, 300),
            )
            if is_stopped and is_stopped():
                return None

            if response.status_code != 200:
                raise Exception(f"GPT 图生图失败 (HTTP {response.status_code}): {self._safe_get_error_message(response)}")

            return self._extract_and_save_image(response.json(), save_path)
        finally:
            for handle in file_handles:
                handle.close()

    def _extract_and_save_image(self, response_data: dict, save_path: str) -> Optional[str]:
        data = response_data.get("data") or []
        if not data:
            raise Exception("API 返回空结果")

        first = data[0] or {}
        b64_data = first.get("b64_json") or first.get("b64") or first.get("image_base64")
        image_url = first.get("url") or first.get("image_url")

        if b64_data:
            image_bytes = base64.b64decode(b64_data)
        elif image_url:
            image_resp = self._session.get(image_url, timeout=(15, 120))
            if image_resp.status_code != 200:
                raise Exception(f"下载生成图片失败: HTTP {image_resp.status_code}")
            image_bytes = image_resp.content
        else:
            raise Exception("API 响应中未找到图片数据")

        save_path_obj = Path(save_path)
        save_path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path_obj, "wb") as file:
            file.write(image_bytes)
        return str(save_path_obj)

    def _build_prompt(self, prompt: str) -> str:
        prompt = (prompt or "").strip()
        return f"生成图片{prompt}生成图片"

    def _normalize_model(self, model: str) -> str:
        model = (model or "").strip()
        if not model:
            return self.DEFAULT_MODEL
        if model in ("gpt-image-2", "gpt-image-2-all"):
            return self.DEFAULT_MODEL
        return model

    def _build_size(self, aspect_ratio: str, image_size: str) -> str:
        longest_edge = 1024 if str(image_size).upper() == "1K" else 2048
        ratio_text = (aspect_ratio or "1:1").strip()
        try:
            width_ratio, height_ratio = ratio_text.split(":", 1)
            width_ratio = max(int(width_ratio), 1)
            height_ratio = max(int(height_ratio), 1)
        except Exception:
            width_ratio, height_ratio = 1, 1

        scale = longest_edge / max(width_ratio, height_ratio)
        width = max(int(round(width_ratio * scale)), 1)
        height = max(int(round(height_ratio * scale)), 1)
        return f"{width}x{height}"

    def _get_mime_type(self, image_path: str) -> str:
        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }
        return mime_map.get(ext, "image/png")

    def _safe_get_error_message(self, resp) -> str:
        body = resp.text
        if not body or not body.strip():
            return "(空响应)"
        try:
            error_data = resp.json()
            if "error" in error_data:
                error = error_data["error"]
                if isinstance(error, dict):
                    return error.get("message", body[:300])
                return str(error)
            return body[:300]
        except Exception:
            return body[:300]

