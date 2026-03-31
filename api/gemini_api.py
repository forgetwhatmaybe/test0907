import time
import base64
import requests
from pathlib import Path
from typing import Optional, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GeminiAPI:
    """Gemini (Nano Banana / 香蕉模型) 图片生成 API
    
    使用 Google Gemini REST API 进行图片生成和编辑。
    支持文生图、图生图，最多 14 张参考图片输入。
    """
    
    BASE_URL = "https://api.vectorengine.ai/v1"
    REQUEST_RETRY_TOTAL = 10
    GENERATE_MAX_ATTEMPTS = 10
    
    def __init__(self):
        self.api_key = ""
        self._base_url = self.BASE_URL  # 实际使用的地址（可被中转地址覆盖）
        self._on_rate_limit = None  # callback(wait_seconds, message, attempt, max_attempts)
        self._session = self._create_retry_session()
    
    def _create_retry_session(self):
        session = requests.Session()
        retry = Retry(
            total=self.REQUEST_RETRY_TOTAL,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def set_credentials(self, api_key: str, base_url: str = "", **kwargs):
        """设置 API 密钥和可选的中转地址
        
        Args:
            api_key: API 密钥（SK 开头的令牌）
            base_url: 中转地址，为空则使用官方地址
        """
        self.api_key = api_key
        if base_url and base_url.strip():
            # 去掉末尾斜杠
            self._base_url = base_url.strip().rstrip("/")
        else:
            self._base_url = self.BASE_URL
    
    def test_connection(self) -> bool:
        """测试 API 连接是否正常"""
        try:
            url = f"{self._base_url}/models?key={self.api_key}"
            print(f"[Gemini] 测试连接: {self._base_url}/models?key=***")
            resp = self._session.get(url, timeout=(10, 30))
            if resp.status_code == 200:
                return True
            elif resp.status_code == 400:
                raise Exception("API 密钥格式错误")
            elif resp.status_code in (401, 403):
                raise Exception("API 密钥无效或无权限")
            elif resp.status_code == 429:
                raise Exception("请求过于频繁，请稍后重试")
            else:
                body_preview = resp.text[:300] if resp.text else "(空响应)"
                raise Exception(f"API 返回错误: HTTP {resp.status_code}\n{body_preview}")
        except requests.exceptions.ConnectionError:
            raise Exception(f"无法连接到 API ({self._base_url})，请检查网络或中转地址")
        except requests.exceptions.Timeout:
            raise Exception(f"连接超时 ({self._base_url})，请检查网络或中转地址")
    
    def generate_image(self, prompt: str, image_paths: List[str] = None,
                       model: str = "gemini-2.5-flash-preview-image-generation",
                       aspect_ratio: str = "1:1",
                       image_size: str = "",
                       save_path: str = "output.png",
                       is_stopped=None) -> Optional[str]:
        """调用 Gemini 生成图片
        
        Args:
            prompt: 文本提示词
            image_paths: 参考图片路径列表（最多 14 张）
            model: 模型名称
            aspect_ratio: 宽高比（1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9）
            image_size: 输出分辨率，仅 gemini-3-pro 支持（"1024", "2048", "4096"）
            save_path: 输出图片保存路径
            is_stopped: 停止检查回调函数，返回 True 时中断执行
        
        Returns:
            生成的图片保存路径，失败或被停止时返回 None
        """
        if is_stopped and is_stopped():
            return None
        
        # ---- 构建请求内容 ----
        contents_parts = []
        
        # 文本提示
        modified_prompt = f"生成图片{prompt}生成图片"
        contents_parts.append({"text": modified_prompt})
        
        # 参考图片（base64 内联）
        if image_paths:
            for img_path in image_paths:
                if not img_path or not Path(img_path).exists():
                    continue
                img_data = self._encode_image(img_path)
                if img_data:
                    mime_type = self._get_mime_type(img_path)
                    contents_parts.append({
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": img_data
                        }
                    })
        
        # ---- 构建请求体 ----
        generation_config = {
            "responseModalities": ["TEXT", "IMAGE"],
        }
        
        image_config = {}
        if aspect_ratio:
            image_config["aspectRatio"] = aspect_ratio
        # gemini-3-pro 和 gemini-3.1-flash 支持 imageSize 控制输出分辨率
        if image_size and ("pro" in model.lower() or "3.1-flash" in model.lower()):
            image_config["imageSize"] = image_size
        if image_config:
            generation_config["imageConfig"] = image_config
        
        request_body = {
            "contents": [{"parts": contents_parts}],
            "generationConfig": generation_config
        }
        
        url = f"{self._base_url}/models/{model}:generateContent?key={self.api_key}"
        print(f"[Gemini] 请求地址: {self._base_url}/models/{model}:generateContent?key=***")
        
        # ---- 发送请求（支持限流自动重试）----
        max_attempts = self.GENERATE_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
            if is_stopped and is_stopped():
                return None
            
            try:
                resp = self._session.post(
                    url, json=request_body,
                    timeout=(15, 900)  # 连接 15s，读取 900s（4K 图片生成可能较慢）
                )
                
                if resp.status_code == 429:
                    wait = 30 * attempt
                    msg = "请求过于频繁"
                    if self._on_rate_limit:
                        self._on_rate_limit(wait, msg, attempt, max_attempts)
                    if self._interruptible_sleep(wait, is_stopped):
                        return None
                    continue
                
                if resp.status_code == 200:
                    return self._safe_parse_and_extract(resp, save_path)
                else:
                    error_msg = self._safe_get_error_message(resp)
                    raise Exception(f"Gemini API 错误 (HTTP {resp.status_code}): {error_msg}")
            
            except (requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError) as e:
                if attempt < max_attempts:
                    wait = 5 * attempt
                    print(f"网络错误(第{attempt}次): {e}")
                    if self._interruptible_sleep(wait, is_stopped):
                        return None
                    continue
                raise Exception(f"网络错误: {e}")
        
        raise Exception("超过最大重试次数")
    
    def _safe_parse_and_extract(self, resp, save_path):
        """安全地解析响应并提取图片，处理空响应或非JSON情况"""
        body = resp.text
        if not body or not body.strip():
            raise Exception(
                f"API 返回空响应 (HTTP {resp.status_code})\n"
                f"请检查中转地址是否正确: {self._base_url}"
            )
        try:
            data = resp.json()
        except Exception:
            preview = body[:500]
            raise Exception(
                f"API 返回非JSON格式 (HTTP {resp.status_code})\n"
                f"响应内容: {preview}\n"
                f"请检查中转地址是否正确: {self._base_url}"
            )
        return self._extract_image(data, save_path)
    
    def _safe_get_error_message(self, resp):
        """安全地从错误响应中提取错误信息"""
        body = resp.text
        if not body or not body.strip():
            return f"(空响应) 请检查中转地址: {self._base_url}"
        try:
            error_data = resp.json()
            if "error" in error_data:
                return error_data["error"].get("message", body[:300])
            return body[:300]
        except Exception:
            return body[:300]
    
    # ---- 工具方法 ----
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """将图片文件编码为 base64 字符串"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"读取图片失败 {image_path}: {e}")
            return None
    
    def _get_mime_type(self, image_path: str) -> str:
        """根据文件扩展名获取 MIME 类型"""
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
    
    def _extract_image(self, response_data: dict, save_path: str) -> Optional[str]:
        """从 API 响应中提取第一张图片并保存到磁盘"""
        try:
            candidates = response_data.get("candidates") or []
            if not candidates:
                # 检查 promptFeedback 中是否有安全过滤信息
                feedback = response_data.get("promptFeedback") or {}
                block_reason = feedback.get("blockReason", "")
                if block_reason:
                    raise Exception(f"请求被安全过滤拦截: {block_reason}")
                raise Exception("API 返回空候选结果（candidates 为空）")
            
            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "")
            
            # 检查是否因安全原因被阻止（无 content）
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            
            if not parts:
                # 没有 parts：可能被安全过滤或模型拒绝生成
                safety_ratings = candidate.get("safetyRatings") or []
                blocked_categories = [
                    r.get("category", "未知")
                    for r in safety_ratings
                    if r.get("blocked") or r.get("probability") in ("HIGH", "MEDIUM")
                ]
                if blocked_categories:
                    raise Exception(
                        f"图片生成被安全过滤拦截，原因: {', '.join(blocked_categories)}\n"
                        f"finishReason={finish_reason}，请修改提示词后重试"
                    )
                if finish_reason and finish_reason not in ("STOP",):
                    raise Exception(
                        f"图片生成失败，finishReason={finish_reason}，请修改提示词后重试"
                    )
                raise Exception("API 响应中未包含任何内容 (parts 为空)")
            
            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    image_data = base64.b64decode(inline_data["data"])
                    
                    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(image_data)
                    return save_path
            
            # 没有图片数据，检查是否有文本说明（可能是安全过滤/模型只返回了文字）
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            if text_parts:
                text_info = " ".join(text_parts)[:200]
                raise Exception(f"未生成图片，模型返回文字: {text_info}")
            
            raise Exception(
                f"API 响应中未找到图片数据 (finishReason={finish_reason})"
            )
        except KeyError as e:
            raise Exception(f"解析 API 响应失败: {e}")
    
    @staticmethod
    def _interruptible_sleep(seconds, is_stopped=None):
        """可中断的 sleep，每秒检查一次停止信号"""
        for _ in range(int(seconds)):
            if is_stopped and is_stopped():
                return True
            time.sleep(1)
        remaining = seconds - int(seconds)
        if remaining > 0:
            time.sleep(remaining)
        return is_stopped() if is_stopped else False
