import requests
import json
import time
import base64
import jwt
from typing import Optional, Dict, Any
from .base_api import BaseAPI, TaskStatus


class KlingAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        self.base_url = "https://api-beijing.klingai.com"
        self.access_key = ""
        self._omni_task_id = None  # 用于 Omni-Video 任务
        self._session = self._create_retry_session()
        # 优化：缓存JWT token，避免频繁生成
        self._cached_token = None
        self._token_expiry = 0
        self._token_buffer_time = 300  # token过期前5分钟刷新
    
    @staticmethod
    def _create_retry_session():
        """创建带重试机制的 requests Session"""
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
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
    
    def set_credentials(self, access_key: str, secret_key: str):
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
    
    def _generate_jwt_token(self) -> str:
        """生成JWT鉴权token (官方文档: HS256签名)"""
        now = int(time.time())
        headers = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "iss": self.access_key,
            "exp": now + 1800,  # 30分钟后过期
            "nbf": now - 5      # 5秒前开始生效
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256", headers=headers)
    
    def _get_cached_token(self) -> str:
        """获取缓存的JWT token，如果过期则重新生成"""
        current_time = int(time.time())
        
        # 检查缓存的token是否有效
        if (self._cached_token and 
            self._token_expiry > current_time + self._token_buffer_time):
            return self._cached_token
        
        # 生成新token
        self._cached_token = self._generate_jwt_token()
        self._token_expiry = current_time + 1800  # 30分钟后过期
        
        return self._cached_token
    
    def _get_headers(self) -> dict:
        """获取请求头（优化：使用缓存的token）"""
        token = self._get_cached_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    
    def test_connection(self) -> bool:
        try:
            if not self.access_key or not self.secret_key:
                return False
            
            response = requests.get(
                f"{self.base_url}/v1/videos/image2video",
                headers=self._get_headers(),
                timeout=30
            )
            
            # 尝试解析 JSON 响应
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError):
                result = {}
            
            code = result.get("code", -1)
            message = result.get("message", "")
            
            # HTTP 200 且 code=0 → 请求成功（理论上不会出现，因为没传参数）
            if response.status_code == 200 and code == 0:
                return True
            
            # 401: 身份验证失败 (code 1000-1004)
            if response.status_code == 401:
                error_map = {
                    1000: "身份验证失败，请检查 Authorization 是否正确",
                    1001: "Authorization 为空",
                    1002: "Authorization 值非法，请检查密钥是否正确",
                    1003: "Token 未到有效时间，请检查系统时间是否正确",
                    1004: "Token 已过期，请重新签发",
                }
                detail = error_map.get(code, message or "身份验证失败")
                raise Exception(
                    f"可灵AI 密钥验证失败 (code={code})\n"
                    f"{detail}\n"
                    "请前往可灵AI开发者中心检查密钥：\n"
                    "https://app.klingai.com/cn/dev"
                )
            
            # 403: 无权限 (code 1103)
            if response.status_code == 403:
                raise Exception(
                    "可灵AI 账户无权限 (code=1103)\n"
                    "请求的资源无权限，请检查账户是否已开通对应的API服务。\n"
                    "前往可灵AI开发者中心确认：\n"
                    "https://app.klingai.com/cn/dev"
                )
            
            # 429: 账户异常 (code 1100-1102, 1302-1304)
            if response.status_code == 429:
                error_map = {
                    1100: "账户异常，请检查账户配置信息",
                    1101: "账户欠费（后付费场景），请充值确保余额充足",
                    1102: "资源包已用完或已过期（预付费场景），请购买资源包或开通后付费",
                    1302: "API请求过快，超过速率限制，请稍后重试",
                    1303: "并发或QPS超出预付费资源包限制，请降低频率后重试",
                    1304: "触发IP白名单策略，请联系客服",
                }
                detail = error_map.get(code, message or "账户异常")
                raise Exception(
                    f"可灵AI 账户异常 (code={code})\n"
                    f"{detail}"
                )
            
            # 400: 请求参数非法 → 说明鉴权已通过，密钥有效
            if response.status_code == 400:
                return True
            
            # 500/503/504: 服务器内部错误
            if response.status_code in [500, 503, 504]:
                raise Exception(
                    f"可灵AI 服务器错误 (HTTP {response.status_code})\n"
                    f"{message or '服务暂时不可用，请稍后重试'}"
                )
            
            # 404: 可能是端点问题，但如果返回了业务code说明鉴权通过
            if response.status_code == 404 and code in [1202, 1203]:
                return True
            
            # 其他情况
            if code > 0:
                raise Exception(f"可灵AI 错误 (HTTP {response.status_code}, code={code}): {message}")
            
            # 无法解析时根据 HTTP 状态码判断
            raise Exception(f"可灵AI 连接失败 (HTTP {response.status_code}): {response.text[:200]}")
            
        except requests.exceptions.Timeout:
            raise Exception("连接超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise Exception("网络连接失败，请检查网络设置")
        except Exception:
            raise
    
    def _is_omni_model(self, model: str) -> bool:
        """判断是否为 Omni-Video 模型"""
        return model == "kling-video-o1"
    
    def submit_image_to_video_task(self, image_path: str, prompt: str, **kwargs) -> str:
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()
        
        model = kwargs.get("model", "kling-v1")
        duration = int(kwargs.get("duration", "5"))
        mode = kwargs.get("mode", "std")
        cfg_scale = kwargs.get("cfg_scale", 0.5)
        
        if self._is_omni_model(model):
            # Omni-Video API
            return self._submit_omni_task(image_base64, prompt, model, duration, mode, kwargs)
        else:
            # 图生视频 API
            return self._submit_image2video_task(image_base64, prompt, model, duration, mode, cfg_scale, kwargs)
    
    def _submit_image2video_task(self, image_base64: str, prompt: str, model: str, 
                                  duration: int, mode: str, cfg_scale: float, kwargs: dict) -> str:
        """提交图生视频任务（含并发限流自动等待重试）"""
        payload = {
            "model_name": model,
            "image": image_base64,
            "prompt": prompt,
            "duration": duration,
            "cfg_scale": cfg_scale,
            "mode": mode
        }
        
        # 处理首尾帧模式
        tail_image = kwargs.get("tail_image")
        if tail_image:
            with open(tail_image, "rb") as f:
                tail_base64 = base64.b64encode(f.read()).decode()
            payload["image_tail"] = tail_base64
        
        max_retries = 6
        for attempt in range(max_retries):
            response = self._session.post(
                f"{self.base_url}/v1/videos/image2video",
                headers=self._get_headers(),
                json=payload,
                timeout=(15, 60)
            )
            
            if response.status_code == 200:
                result = response.json()
                code = result.get("code", 0)
                if code == 0:
                    return result.get("data", {}).get("task_id", "")
                # 业务层限流码
                if code in [1302, 1303]:
                    wait = 30 * (attempt + 1)
                    msg = result.get("message", "并发限制")
                    print(f"可灵AI 并发限制(code={code}): {msg}, {wait}秒后重试({attempt+1}/{max_retries})")
                    if hasattr(self, '_on_rate_limit'):
                        self._on_rate_limit(wait, msg, attempt + 1, max_retries)
                    time.sleep(wait)
                    continue
                return result.get("data", {}).get("task_id", "")
            elif response.status_code == 429:
                # HTTP 429: 请求过快 / 并发不足
                try:
                    result = response.json()
                    code = result.get("code", 0)
                    msg = result.get("message", "请求过快")
                except (json.JSONDecodeError, ValueError):
                    code = 429
                    msg = "请求过快，超出并发限制"
                wait = 30 * (attempt + 1)
                print(f"可灵AI 限流(HTTP 429, code={code}): {msg}, {wait}秒后重试({attempt+1}/{max_retries})")
                if hasattr(self, '_on_rate_limit'):
                    self._on_rate_limit(wait, msg, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            else:
                raise Exception(f"API Error: {response.text}")
        
        raise Exception("可灵AI 提交任务失败: 并发数不足，多次等待后仍无法提交，请稍后再试")
    
    def _submit_omni_task(self, image_base64: str, prompt: str, model: str,
                          duration: int, mode: str, kwargs: dict) -> str:
        """提交 Omni-Video 任务"""
        payload = {
            "model_name": model,
            "prompt": prompt,
            "duration": duration,
            "mode": mode,
            "image_list": [
                {
                    "image_url": image_base64,
                    "type": "first_frame"
                }
            ]
        }
        
        # 处理首尾帧模式
        tail_image = kwargs.get("tail_image")
        if tail_image:
            with open(tail_image, "rb") as f:
                tail_base64 = base64.b64encode(f.read()).decode()
            payload["image_list"].append({
                "image_url": tail_base64,
                "type": "end_frame"
            })
        
        response = self._session.post(
            f"{self.base_url}/v1/videos/omni-video",
            headers=self._get_headers(),
            json=payload,
            timeout=(15, 60)
        )
        
        if response.status_code == 200:
            result = response.json()
            code = result.get("code", 0)
            if code in [1302, 1303]:
                # 并发限制，自动等待重试
                for attempt in range(5):
                    wait = 30 * (attempt + 1)
                    msg = result.get("message", "并发限制")
                    print(f"可灵AI Omni 并发限制: {msg}, {wait}秒后重试")
                    if hasattr(self, '_on_rate_limit'):
                        self._on_rate_limit(wait, msg, attempt + 1, 5)
                    time.sleep(wait)
                    response = self._session.post(
                        f"{self.base_url}/v1/videos/omni-video",
                        headers=self._get_headers(),
                        json=payload,
                        timeout=(15, 60)
                    )
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("code", 0) not in [1302, 1303]:
                            break
                    elif response.status_code != 429:
                        break
            task_id = result.get("data", {}).get("task_id", "")
            self._omni_task_id = task_id
            return task_id
        elif response.status_code == 429:
            raise Exception("可灵AI 并发数不足，请稍后再试")
        else:
            raise Exception(f"API Error: {response.text}")
    
    # ========== 可灵扩图 (Image Expand) ==========
    def submit_expand_image_task(self, image_path: str, **kwargs) -> str:
        """提交可灵扩图任务"""
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()

        payload = {
            "image": image_base64,
            "up_expansion_ratio": float(kwargs.get("up_expansion_ratio", 0.0)),
            "down_expansion_ratio": float(kwargs.get("down_expansion_ratio", 0.0)),
            "left_expansion_ratio": float(kwargs.get("left_expansion_ratio", 0.0)),
            "right_expansion_ratio": float(kwargs.get("right_expansion_ratio", 0.0)),
            "n": int(kwargs.get("n", 1)),
        }
        prompt = kwargs.get("prompt", "")
        if prompt:
            payload["prompt"] = prompt

        max_retries = 6
        for attempt in range(max_retries):
            response = self._session.post(
                f"{self.base_url}/v1/images/editing/expand",
                headers=self._get_headers(),
                json=payload,
                timeout=(15, 60)
            )
            if response.status_code == 200:
                result = response.json()
                code = result.get("code", 0)
                if code == 0:
                    return result.get("data", {}).get("task_id", "")
                if code in [1302, 1303]:
                    wait = 30 * (attempt + 1)
                    msg = result.get("message", "并发限制")
                    if hasattr(self, '_on_rate_limit'):
                        self._on_rate_limit(wait, msg, attempt + 1, max_retries)
                    time.sleep(wait)
                    continue
                raise Exception(f"可灵扩图错误: code={code}, {result.get('message', '')}")
            elif response.status_code == 429:
                wait = 30 * (attempt + 1)
                if hasattr(self, '_on_rate_limit'):
                    self._on_rate_limit(wait, "请求过快", attempt + 1, max_retries)
                time.sleep(wait)
                continue
            else:
                raise Exception(f"可灵扩图 API Error: {response.text}")
        raise Exception("可灵扩图 提交失败: 多次重试后仍无法提交")

    def get_expand_task_status(self, task_id: str) -> TaskStatus:
        response = self._session.get(
            f"{self.base_url}/v1/images/editing/expand/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        if response.status_code == 200:
            result = response.json()
            status = result.get("data", {}).get("task_status", "")
            status_map = {
                "submitted": TaskStatus.PENDING,
                "processing": TaskStatus.RUNNING,
                "succeed": TaskStatus.SUCCESS,
                "failed": TaskStatus.FAILED
            }
            return status_map.get(status, TaskStatus.PENDING)
        return TaskStatus.FAILED

    def get_expand_task_result(self, task_id: str) -> Optional[str]:
        response = self._session.get(
            f"{self.base_url}/v1/images/editing/expand/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        if response.status_code == 200:
            result = response.json()
            images = result.get("data", {}).get("task_result", {}).get("images", [])
            if images:
                return images[0].get("url")
        return None

    def wait_for_expand_completion(self, task_id: str, timeout: int = 300,
                                    is_stopped=None) -> Optional[str]:
        """轮询等待扩图任务完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if is_stopped and is_stopped():
                return None
            status = self.get_expand_task_status(task_id)
            if status == TaskStatus.SUCCESS:
                return self.get_expand_task_result(task_id)
            elif status == TaskStatus.FAILED:
                raise Exception("可灵扩图任务失败")
            time.sleep(5)
        raise Exception("可灵扩图超时")

    def get_task_status(self, task_id: str) -> TaskStatus:
        # 尝试图生视频端点
        response = self._session.get(
            f"{self.base_url}/v1/videos/image2video/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            status = result.get("data", {}).get("task_status", "")
            status_map = {
                "submitted": TaskStatus.PENDING,
                "processing": TaskStatus.RUNNING,
                "succeed": TaskStatus.SUCCESS,
                "failed": TaskStatus.FAILED
            }
            return status_map.get(status, TaskStatus.PENDING)
        
        # 尝试 Omni-Video 端点
        response = self._session.get(
            f"{self.base_url}/v1/videos/omni-video/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            status = result.get("data", {}).get("task_status", "")
            status_map = {
                "submitted": TaskStatus.PENDING,
                "processing": TaskStatus.RUNNING,
                "succeed": TaskStatus.SUCCESS,
                "failed": TaskStatus.FAILED
            }
            return status_map.get(status, TaskStatus.PENDING)
        
        return TaskStatus.FAILED
    
    def get_task_result(self, task_id: str) -> Optional[str]:
        # 尝试图生视频端点
        response = self._session.get(
            f"{self.base_url}/v1/videos/image2video/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            video_url = result.get("data", {}).get("task_result", {}).get("videos", [{}])[0].get("url")
            if video_url:
                return video_url
        
        # 尝试 Omni-Video 端点
        response = self._session.get(
            f"{self.base_url}/v1/videos/omni-video/{task_id}",
            headers=self._get_headers(),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("data", {}).get("task_result", {}).get("videos", [{}])[0].get("url")
        
        return None
