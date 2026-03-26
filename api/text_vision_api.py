import requests
import base64
import time
import json
import pprint
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
    
    def set_credentials(self, api_key: str, base_url: str = "", **kwargs):
        self.api_key = api_key
        if base_url and base_url.strip():
            self._base_url = base_url.strip().rstrip("/")
    
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
        format_mode: str = "无",
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
            return self._call_gpt_api(prompt, image_paths, model, temperature, format_mode, is_stopped)
        else:
            return self._call_gemini_api(prompt, image_paths, model, temperature, format_mode, is_stopped)
    
    def _call_gpt_api(
        self,
        prompt: str,
        image_paths: List[str],
        model: str,
        temperature: float = 0.8,
        format_mode: str = "无",
        is_stopped=None
    ) -> Optional[str]:
        """调用GPT-5.4 API"""
        url = f"{self._base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        system_prompt = self._build_system_prompt(format_mode)
        user_prompt = self._build_user_prompt(prompt, format_mode)
        content = [{"type": "text", "text": user_prompt}]
        
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
                {"role": "system", "content": system_prompt},
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
                return self._format_response_text(self._extract_gpt_text(data), format_mode)
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
        format_mode: str = "无",
        is_stopped=None
    ) -> Optional[str]:
        """调用Gemini-3 Flash API"""
        url = f"{self._base_url}/v1beta/models/{model}:generateContent?key={self.api_key}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        system_prompt = self._build_system_prompt(format_mode)
        user_prompt = self._build_user_prompt(prompt, format_mode)
        parts = [{"text": f"{system_prompt}\n\n{user_prompt}"}]
        
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
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096,
            }
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
                return self._format_response_text(self._extract_gemini_text(data), format_mode)
            else:
                error_msg = self._safe_get_error_message(resp)
                raise Exception(f"Gemini API错误 (HTTP {resp.status_code}): {error_msg}")
        
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            raise Exception(f"网络错误: {e}")

    def _build_system_prompt(self, format_mode: str) -> str:
        if format_mode == "图片反推json":
            return (
                "你是专业的图片分析与结构化输出助手。"
                "你必须严格返回一个合法 JSON 对象，且只输出 JSON，"
                "不要输出 Markdown、代码块、解释或额外前后缀。"
                "JSON 必须严格包含以下 8 个键，并尽量按这个顺序输出："
                "\"主体 + 动作\"、\"场景 + 环境\"、\"视角\"、\"镜头 & 景深\"、"
                "\"光影\"、\"色彩风格\"、\"画质\"、\"特效\"。"
                "每个键的值都使用中文字符串；没有明确内容时返回空字符串。"
            )
        if format_mode == "json格式":
            return (
                "你是结构化输出助手。"
                "请严格返回合法 JSON，且只输出 JSON，不要输出 Markdown、代码块、说明或额外文本。"
                "如果用户没有明确指定 JSON 字段结构，请返回一个对象，优先包含："
                "\"总结\"、\"分析\"、\"细节\" 这三个顶层字段。"
                "其中 \"分析\" 建议为字符串数组，\"细节\" 建议为对象。"
            )
        return "你是专业的图片理解与文本生成助手，请基于图片和提示词直接回答。"

    def _build_user_prompt(self, prompt: str, format_mode: str) -> str:
        prompt = (prompt or "").strip()
        if format_mode == "图片反推json":
            return (
                "请结合输入图片完成图像反推，并输出结构化结果。\n"
                "输出要求：\n"
                "1. 只返回一个合法 JSON 对象。\n"
                "2. 不要使用 Markdown 或代码块。\n"
                "3. 8 个字段必须全部存在。\n"
                f"4. 额外要求：{prompt or '请尽量准确、精炼地概括图片的核心视觉信息。'}"
            )
        if format_mode == "json格式":
            return (
                "请根据输入图片与用户需求，以 JSON 格式回答。\n"
                "输出要求：\n"
                "1. 只返回合法 JSON。\n"
                "2. 不要使用 Markdown 或代码块。\n"
                "3. 如果用户指定了字段或结构，优先遵循用户要求。\n"
                f"用户需求：{prompt or '请对图片内容进行结构化总结。'}"
            )
        return prompt

    def _format_response_text(self, text: str, format_mode: str) -> str:
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            return ""
        if format_mode == "无":
            return cleaned_text

        parsed_json = self._try_parse_json(cleaned_text)
        if parsed_json is None:
            return cleaned_text

        return pprint.pformat(
            parsed_json,
            width=100,
            compact=False,
            sort_dicts=False,
        )

    def _try_parse_json(self, text: str):
        candidate = (text or "").strip()
        if not candidate:
            return None

        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) >= 3:
                candidate = "\n".join(lines[1:-1]).strip()

        try:
            return json.loads(candidate)
        except Exception:
            pass

        decoder = json.JSONDecoder()
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            snippet = candidate[index:]
            try:
                parsed, _ = decoder.raw_decode(snippet)
                return parsed
            except Exception:
                continue
        return None
    
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
