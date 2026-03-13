import requests
import base64
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TextVisionAPI:
    """文本视觉API封装 - 支持GPT-5.4和Gemini-3.1 Flash Lite Preview
    
    用于图片理解和文本生成，支持多图片输入。
    """
    
    def __init__(self):
        self.api_key = ""
        self._base_url = "https://api.vectorengine.ai"
        self._session = self._create_retry_session()
    
    def _create_retry_session(self):
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def set_credentials(self, api_key: str, **kwargs):
        self.api_key = api_key
    
    def test_connection(self, model: str = "gpt-5.4") -> bool:
        """测试API连接是否正常"""
        try:
            if model.startswith("gpt"):
                url = f"{self._base_url}/v1/models"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                resp = self._session.get(url, headers=headers, timeout=(10, 30))
            else:
                url = f"{self._base_url}/v1beta/models?key={self.api_key}"
                resp = self._session.get(url, timeout=(10, 30))
            
            if resp.status_code == 200:
                return True
            elif resp.status_code == 401:
                raise Exception("API密钥无效或无权限")
            else:
                raise Exception(f"API返回错误: HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到API，请检查网络")
        except requests.exceptions.Timeout:
            raise Exception("连接超时，请检查网络")
    
    def generate_text(
        self,
        prompt: str,
        image_paths: List[str] = None,
        model: str = "gpt-5.4",
        temperature: float = 0.8,
        is_stopped=None
    ) -> Optional[str]:
        """调用API生成文本
        
        Args:
            prompt: 文本提示词
            image_paths: 参考图片路径列表
            model: 模型名称 (gpt-5.4 或 gemini-3-flash-preview)
            is_stopped: 停止检查回调函数
        
        Returns:
            生成的文本，失败或被停止时返回None
        """
        if is_stopped and is_stopped():
            return None
        
        if model.startswith("gpt"):
            return self._call_gpt_api(prompt, image_paths, model, temperature, is_stopped)
        else:
            return self._call_gemini_api(prompt, image_paths, model, temperature, is_stopped)
    
    def _call_gpt_api(
        self,
        prompt: str,
        image_paths: List[str],
        model: str,
        temperature: float = 0.8,
        is_stopped=None
    ) -> Optional[str]:
        """调用GPT-5.4 API"""
        url = f"{self._base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        content = [{"type": "text", "text": prompt}]
        
        if image_paths:
            for img_path in image_paths:
                if not img_path or not Path(img_path).exists():
                    continue
                base64_data = self._encode_image(img_path)
                if base64_data:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}
                    })
        
        request_body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": content}
            ],
            "max_tokens": 4096,
            "temperature": temperature
        }
        
        try:
            resp = self._session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=(15, 120)
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return self._extract_gpt_text(data)
            else:
                error_msg = self._safe_get_error_message(resp)
                raise Exception(f"GPT API错误 (HTTP {resp.status_code}): {error_msg}")
        
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            raise Exception(f"网络错误: {e}")
    
    def _call_gemini_api(
        self,
        prompt: str,
        image_paths: List[str],
        model: str,
        temperature: float = 0.8,
        is_stopped=None
    ) -> Optional[str]:
        """调用Gemini-3 Flash API"""
        url = f"{self._base_url}/v1beta/models/{model}:generateContent?key={self.api_key}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        parts = [{"text": prompt}]
        
        if image_paths:
            for img_path in image_paths:
                if not img_path or not Path(img_path).exists():
                    continue
                base64_data = self._encode_image(img_path)
                if base64_data:
                    mime_type = self._get_mime_type(img_path)
                    parts.append({
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64_data
                        }
                    })
        
        request_body = {
            "contents": [{"role": "user", "parts": parts}]
        }
        
        try:
            resp = self._session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=(15, 120)
            )
            
            if resp.status_code == 200:
                data = resp.json()
                return self._extract_gemini_text(data)
            else:
                error_msg = self._safe_get_error_message(resp)
                raise Exception(f"Gemini API错误 (HTTP {resp.status_code}): {error_msg}")
        
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            raise Exception(f"网络错误: {e}")
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """将图片文件编码为base64字符串"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"读取图片失败 {image_path}: {e}")
            return None
    
    def _get_mime_type(self, image_path: str) -> str:
        """根据文件扩展名获取MIME类型"""
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
    
    def _extract_gpt_text(self, response_data: dict) -> str:
        """从GPT API响应中提取文本"""
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise Exception("API返回空结果")
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
                return "".join(text_parts)
            else:
                return str(content)
        
        except Exception as e:
            raise Exception(f"解析GPT响应失败: {e}")
    
    def _extract_gemini_text(self, response_data: dict) -> str:
        """从Gemini API响应中提取文本"""
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                feedback = response_data.get("promptFeedback", {})
                block_reason = feedback.get("blockReason", "")
                if block_reason:
                    raise Exception(f"请求被安全过滤拦截: {block_reason}")
                raise Exception("API返回空结果")
            
            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            
            if not parts:
                safety_ratings = candidate.get("safetyRatings", [])
                blocked_categories = [
                    r.get("category", "未知")
                    for r in safety_ratings
                    if r.get("blocked") or r.get("probability") in ("HIGH", "MEDIUM")
                ]
                if blocked_categories:
                    raise Exception(
                        f"请求被安全过滤拦截，原因: {', '.join(blocked_categories)}"
                    )
                raise Exception("API响应中未包含任何内容")
            
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            return "".join(text_parts)
        
        except Exception as e:
            raise Exception(f"解析Gemini响应失败: {e}")
    
    def _safe_get_error_message(self, resp) -> str:
        """安全地从错误响应中提取错误信息"""
        body = resp.text
        if not body or not body.strip():
            return "(空响应)"
        try:
            error_data = resp.json()
            if "error" in error_data:
                return error_data["error"].get("message", body[:300])
            return body[:300]
        except Exception:
            return body[:300]
    
    @staticmethod
    def estimate_tokens(text: str, image_paths: List[str] = None) -> int:
        """估算token数量
        
        Args:
            text: 文本内容
            image_paths: 图片路径列表
        
        Returns:
            估算的token数量
        """
        text_tokens = len(text) // 4
        
        image_tokens = 0
        if image_paths:
            for img_path in image_paths:
                if not img_path or not Path(img_path).exists():
                    continue
                try:
                    from PIL import Image
                    with Image.open(img_path) as img:
                        w, h = img.size
                        max_dim = max(w, h)
                        if max_dim < 512:
                            image_tokens += 85
                        elif max_dim < 1024:
                            image_tokens += 170
                        else:
                            image_tokens += 765
                except Exception:
                    image_tokens += 765
        
        return text_tokens + image_tokens
