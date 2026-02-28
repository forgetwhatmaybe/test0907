import requests
import json
import time
import base64
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, Any
from .base_api import BaseAPI, TaskStatus


class JimengAPI(BaseAPI):
    def __init__(self):
        super().__init__()
        self.base_url = "https://visual.volcengineapi.com"
        self.access_key = ""
        self.region = "cn-north-1"
        self.service = "cv"
        self._session = self._create_retry_session()
    
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
        self.access_key = access_key
        self.secret_key = secret_key
    
    def _generate_signature(self, method: str, path: str, query: str, body: str, timestamp: str) -> dict:
        algorithm = "HMAC-SHA256"
        short_date = timestamp[:8]
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        host = self.base_url.replace("https://", "")
        
        # 计算请求体的 SHA256 哈希
        hashed_body = hashlib.sha256(body.encode('utf-8')).hexdigest()
        
        # 构建规范请求 (CanonicalRequest)
        # 按照火山引擎签名规范，canonical headers 必须包含 host 和 x-date
        # headers 按字母顺序排列，每个 header 以 \n 结尾
        canonical_headers = f"content-type:application/json\nhost:{host}\nx-date:{timestamp}\n"
        signed_headers = "content-type;host;x-date"
        
        canonical_request = f"{method}\n{path}\n{query}\n{canonical_headers}\n{signed_headers}\n{hashed_body}"
        
        # 构建待签名字符串 (StringToSign)
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"
        
        # 派生签名密钥
        k_date = hmac.new(self.secret_key.encode('utf-8'), short_date.encode('utf-8'), hashlib.sha256).digest()
        k_region = hmac.new(k_date, self.region.encode('utf-8'), hashlib.sha256).digest()
        k_service = hmac.new(k_region, self.service.encode('utf-8'), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, "request".encode('utf-8'), hashlib.sha256).digest()
        
        # 计算签名
        signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        authorization = f"{algorithm} Credential={self.access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        
        return {
            "Content-Type": "application/json",
            "Host": host,
            "X-Date": timestamp,
            "Authorization": authorization
        }
    
    def _get_headers(self, method: str, path: str, query: str, body: str) -> dict:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return self._generate_signature(method, path, query, body, timestamp)
    
    def test_connection(self) -> bool:
        try:
            if not self.access_key or not self.secret_key:
                return False
            # 使用提交任务接口测试连接，发送一个最小请求
            # 注意：由于没有发送图片，API 会返回参数错误，但只要鉴权通过就说明连接成功
            payload = {
                "req_key": "jimeng_i2v_first_v30",
                "prompt": "test"
            }
            body = json.dumps(payload)
            query = "Action=CVSync2AsyncSubmitTask&Version=2022-08-31"
            headers = self._get_headers("POST", "/", query, body)
            
            response = self._session.post(
                f"{self.base_url}/?{query}",
                headers=headers,
                data=body.encode('utf-8'),
                timeout=(10, 15)
            )
            
            # 尝试解析 JSON 响应
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError):
                result = {}
            
            # 有 code 字段说明已经到达业务层
            if "code" in result:
                code = result.get("code")
                message = result.get("message", "")
                
                # code 50400 = Access Denied，服务未开通或权限不足
                if code == 50400 or "Access Denied" in message:
                    raise Exception(
                        "即梦AI服务未开通或权限不足。\n"
                        "请前往火山引擎控制台完成以下步骤：\n"
                        "1. 开通即梦AI服务: https://console.volcengine.com/jimeng\n"
                        "2. 确保账号已完成实名认证\n"
                        "3. 前往 IAM -> 权限策略，为API密钥用户添加:\n"
                        "   系统策略 CVImageProcessFullAccess"
                    )
                
                # 其他 code 值（如参数错误），说明鉴权已通过
                return True
            
            # 解析 ResponseMetadata 中的错误信息
            if "ResponseMetadata" in result:
                metadata = result["ResponseMetadata"]
                error = metadata.get("Error", {})
                error_code = error.get("Code", "")
                
                # 签名/密钥本身无效
                if error_code in ["SignatureDoesNotMatch", "InvalidAccessKeyId",
                                  "AuthFailure", "IncompleteSignature"]:
                    print(f"JimengAPI test_connection: Auth error - {error_code}")
                    return False
                
                # AccessDenied 说明密钥有效但 IAM 权限不足
                # 需要在火山引擎控制台授权 cv 服务权限
                if error_code == "AccessDenied":
                    error_msg = error.get("Message", "")
                    print(f"JimengAPI test_connection: AccessDenied - {error_msg}")
                    raise Exception(
                        "密钥有效，但 IAM 权限不足。\n"
                        "请前往火山引擎控制台 -> 访问控制(IAM) -> 权限策略，\n"
                        "为当前密钥的用户/角色添加「智能视觉(cv)」的访问权限。\n"
                        "推荐添加系统策略：CVImageProcessFullAccess"
                    )
                
                # 其他业务错误（如参数不全），说明鉴权已通过
                return True
            
            # 非 403 的其他 HTTP 状态码通常意味着鉴权已通过
            if response.status_code in [200, 400]:
                return True
            
            if response.status_code == 403:
                print(f"JimengAPI test_connection: 403 Forbidden - {response.text[:300]}")
                return False
            
            print(f"JimengAPI test_connection: HTTP {response.status_code} - {response.text[:200]}")
            return False
        except requests.exceptions.Timeout:
            raise Exception("连接超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            raise Exception("网络连接失败，请检查网络设置")
        except Exception:
            raise
    
    def submit_image_to_video_task(self, image_path: str, prompt: str, **kwargs) -> str:
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()
        
        model = kwargs.get("model", "jimeng_v1")
        video_duration = kwargs.get("video_duration", 5)
        seed = kwargs.get("seed", -1)
        tail_image = kwargs.get("tail_image")
        resolution = kwargs.get("resolution", "720P")
        
        if model == "jimeng_v30_pro":
            req_key = "jimeng_ti2v_v30_pro"
            frames = 24 * video_duration + 1
            payload = {
                "req_key": req_key,
                "binary_data_base64": [image_base64],
                "prompt": prompt,
                "frames": frames
            }
            if seed >= 0:
                payload["seed"] = seed
        elif model == "jimeng_v30":
            frames = 24 * video_duration + 1
            is_1080p = resolution == "1080P"
            
            if tail_image:
                req_key = "jimeng_i2v_first_tail_v30_1080" if is_1080p else "jimeng_i2v_first_tail_v30"
                with open(tail_image, "rb") as f:
                    tail_base64 = base64.b64encode(f.read()).decode()
                payload = {
                    "req_key": req_key,
                    "binary_data_base64": [image_base64, tail_base64],
                    "prompt": prompt,
                    "frames": frames
                }
            else:
                req_key = "jimeng_i2v_first_v30_1080" if is_1080p else "jimeng_i2v_first_v30"
                payload = {
                    "req_key": req_key,
                    "binary_data_base64": [image_base64],
                    "prompt": prompt,
                    "frames": frames
                }
            if seed >= 0:
                payload["seed"] = seed
        else:
            if model == "jimeng_v2":
                req_key = "jimeng_image2video_v2"
            else:
                req_key = "jimeng_image2video_v1"
            
            payload = {
                "req_key": req_key,
                "binary_data_base64": [image_base64],
                "prompt": prompt,
                "video_duration": video_duration,
                "fps": kwargs.get("fps", 24)
            }
            if seed >= 0:
                payload["seed"] = seed
            if tail_image:
                with open(tail_image, "rb") as f:
                    tail_base64 = base64.b64encode(f.read()).decode()
                payload["tail_image"] = tail_base64
        
        body = json.dumps(payload)
        
        if model in ["jimeng_v30_pro", "jimeng_v30"]:
            query = "Action=CVSync2AsyncSubmitTask&Version=2022-08-31"
        else:
            query = "Action=CVSync2AsyncSubmitTask&Version=2022-08-31"
        
        headers = self._get_headers("POST", "/", query, body)
        
        response = self._session.post(
            f"{self.base_url}/?{query}",
            headers=headers,
            data=body.encode('utf-8'),
            timeout=(15, 60)
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 10000:
                task_id = result.get("data", {}).get("task_id", "")
                if not hasattr(self, '_task_req_keys'):
                    self._task_req_keys = {}
                self._task_req_keys[task_id] = req_key
                return task_id
            else:
                code = result.get('code')
                message = result.get('message', '')
                
                # 并发/限流检测: 常见限流码
                if code in [50429, 50503, 10002] or 'rate limit' in message.lower() or 'too many' in message.lower() or '并发' in message:
                    max_retries = 6
                    for attempt in range(max_retries):
                        wait = 30 * (attempt + 1)
                        print(f"即梦AI 并发限制(code={code}): {message}, {wait}秒后重试({attempt+1}/{max_retries})")
                        if hasattr(self, '_on_rate_limit'):
                            self._on_rate_limit(wait, message, attempt + 1, max_retries)
                        time.sleep(wait)
                        # 重新签名（时间戳变了）
                        headers = self._get_headers("POST", "/", query, body)
                        response = self._session.post(
                            f"{self.base_url}/?{query}",
                            headers=headers,
                            data=body.encode('utf-8'),
                            timeout=(15, 60)
                        )
                        if response.status_code == 200:
                            result = response.json()
                            if result.get("code") == 10000:
                                task_id = result.get("data", {}).get("task_id", "")
                                if not hasattr(self, '_task_req_keys'):
                                    self._task_req_keys = {}
                                self._task_req_keys[task_id] = req_key
                                return task_id
                            # 如果仍然是限流码，继续循环
                            new_code = result.get('code')
                            if new_code not in [50429, 50503, 10002]:
                                new_msg = result.get('message', '')
                                if '并发' not in new_msg and 'rate limit' not in new_msg.lower():
                                    break  # 不是限流了，跳出
                    raise Exception(f"即梦AI 提交任务失败: 并发数不足，多次等待后仍无法提交")
                
                if code == 50400 or 'Access Denied' in message:
                    raise Exception(
                        "即梦AI服务访问被拒绝(50400)。\n"
                        "请前往火山引擎控制台完成以下步骤：\n"
                        "1. 开通即梦AI服务: https://console.volcengine.com/jimeng\n"
                        "2. 确保账号已完成实名认证\n"
                        "3. 前往 IAM -> 权限策略，为API密钥用户添加:\n"
                        "   系统策略 CVImageProcessFullAccess"
                    )
                raise Exception(f"API Error: code={code}, message={message}")
        elif response.status_code == 429:
            # HTTP 429: 并发/QPS限制
            max_retries = 6
            for attempt in range(max_retries):
                wait = 30 * (attempt + 1)
                print(f"即梦AI 限流(HTTP 429), {wait}秒后重试({attempt+1}/{max_retries})")
                if hasattr(self, '_on_rate_limit'):
                    self._on_rate_limit(wait, "请求过快，超出并发限制", attempt + 1, max_retries)
                time.sleep(wait)
                headers = self._get_headers("POST", "/", query, body)
                response = self._session.post(
                    f"{self.base_url}/?{query}",
                    headers=headers,
                    data=body.encode('utf-8'),
                    timeout=(15, 60)
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 10000:
                        task_id = result.get("data", {}).get("task_id", "")
                        if not hasattr(self, '_task_req_keys'):
                            self._task_req_keys = {}
                        self._task_req_keys[task_id] = req_key
                        return task_id
                elif response.status_code != 429:
                    break
            raise Exception("即梦AI 提交任务失败: 并发数不足，多次等待后仍无法提交")
        else:
            try:
                result = response.json()
                code = result.get('code', '')
                message = result.get('message', '')
                if code == 50400 or 'Access Denied' in message:
                    raise Exception(
                        "即梦AI服务访问被拒绝(50400)。\n"
                        "请前往火山引擎控制台完成以下步骤：\n"
                        "1. 开通即梦AI服务: https://console.volcengine.com/jimeng\n"
                        "2. 确保账号已完成实名认证\n"
                        "3. 前往 IAM -> 权限策略，为API密钥用户添加:\n"
                        "   系统策略 CVImageProcessFullAccess"
                    )
                raise Exception(f"API Error: HTTP {response.status_code} - code={code}, message={message}")
            except (json.JSONDecodeError, ValueError):
                raise Exception(f"API Error: HTTP {response.status_code} - {response.text[:500]}")
    
    def get_task_status(self, task_id: str) -> TaskStatus:
        # 获取任务对应的 req_key
        req_key = self._task_req_keys.get(task_id, "jimeng_i2v_first_v30") if hasattr(self, '_task_req_keys') else "jimeng_i2v_first_v30"
        
        payload = {
            "req_key": req_key,
            "task_id": task_id
        }
        body = json.dumps(payload)
        query = "Action=CVSync2AsyncGetResult&Version=2022-08-31"
        headers = self._get_headers("POST", "/", query, body)
        
        response = self._session.post(
            f"{self.base_url}/?{query}",
            headers=headers,
            data=body.encode('utf-8'),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 10000:
                status = result.get("data", {}).get("status", "")
                status_map = {
                    "in_queue": TaskStatus.PENDING,
                    "submitted": TaskStatus.PENDING,
                    "generating": TaskStatus.RUNNING,
                    "running": TaskStatus.RUNNING,
                    "done": TaskStatus.SUCCESS,
                    "success": TaskStatus.SUCCESS,
                    "failed": TaskStatus.FAILED,
                    "not_found": TaskStatus.FAILED,
                    "expired": TaskStatus.FAILED
                }
                return status_map.get(status, TaskStatus.PENDING)
        return TaskStatus.FAILED
    
    def get_task_result(self, task_id: str) -> Optional[str]:
        # 获取任务对应的 req_key
        req_key = self._task_req_keys.get(task_id, "jimeng_i2v_first_v30") if hasattr(self, '_task_req_keys') else "jimeng_i2v_first_v30"
        
        payload = {
            "req_key": req_key,
            "task_id": task_id,
            "req_json": json.dumps({"return_url": True})
        }
        body = json.dumps(payload)
        query = "Action=CVSync2AsyncGetResult&Version=2022-08-31"
        headers = self._get_headers("POST", "/", query, body)
        
        response = self._session.post(
            f"{self.base_url}/?{query}",
            headers=headers,
            data=body.encode('utf-8'),
            timeout=(10, 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            data = result.get("data")
            if data and isinstance(data, dict):
                # 优先返回视频URL，其次图片URL
                video_url = data.get("video_url")
                if video_url:
                    return video_url
                image_urls = data.get("image_urls")
                if image_urls and isinstance(image_urls, list) and image_urls:
                    return image_urls[0]
                # base64 fallback
                b64_list = data.get("binary_data_base64")
                if b64_list and isinstance(b64_list, list) and b64_list:
                    return "base64:" + b64_list[0]
        return None

    # ========== 即梦超清 (Super Resolution) ==========
    def submit_super_resolution_task(self, image_path: str, **kwargs) -> str:
        """提交即梦超清任务
        Args:
            image_path: 原图路径
            resolution: "4k" 或 "8k"，默认 "4k"
            scale: 0-100，默认 50
        """
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()

        payload = {
            "req_key": "jimeng_i2i_seed3_tilesr_cvtob",
            "binary_data_base64": [image_base64],
            "scale": int(kwargs.get("scale", 50)),
        }
        resolution = kwargs.get("resolution", "4k")
        if resolution:
            payload["resolution"] = resolution

        body = json.dumps(payload)
        query = "Action=CVSync2AsyncSubmitTask&Version=2022-08-31"
        headers = self._get_headers("POST", "/", query, body)

        response = self._session.post(
            f"{self.base_url}/?{query}",
            headers=headers,
            data=body.encode('utf-8'),
            timeout=(15, 60)
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 10000:
                task_id = result.get("data", {}).get("task_id", "")
                if not hasattr(self, '_task_req_keys'):
                    self._task_req_keys = {}
                self._task_req_keys[task_id] = "jimeng_i2i_seed3_tilesr_cvtob"
                return task_id
            else:
                raise Exception(f"即梦超清错误: code={result.get('code')}, {result.get('message', '')}")
        raise Exception(f"即梦超清 API Error: HTTP {response.status_code}")

    # ========== 即梦局部重绘 (Inpaint) ==========
    def submit_inpaint_task(self, image_path: str, mask_path: str, prompt: str, **kwargs) -> str:
        """提交即梦局部重绘任务
        Args:
            image_path: 原图路径
            mask_path: 遮罩路径（单通道灰度，0=保留, 255=重绘）
            prompt: 重绘提示词（必填，≤120字符，"删除"表示擦除）
            seed: 可选种子，默认 101
        """
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()
        with open(mask_path, "rb") as f:
            mask_base64 = base64.b64encode(f.read()).decode()

        payload = {
            "req_key": "jimeng_image2image_dream_inpaint",
            "binary_data_base64": [image_base64, mask_base64],
            "prompt": prompt,
        }
        seed = kwargs.get("seed", 101)
        if seed is not None:
            payload["seed"] = int(seed)

        body = json.dumps(payload)
        query = "Action=CVSync2AsyncSubmitTask&Version=2022-08-31"
        headers = self._get_headers("POST", "/", query, body)

        response = self._session.post(
            f"{self.base_url}/?{query}",
            headers=headers,
            data=body.encode('utf-8'),
            timeout=(15, 60)
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 10000:
                task_id = result.get("data", {}).get("task_id", "")
                if not hasattr(self, '_task_req_keys'):
                    self._task_req_keys = {}
                self._task_req_keys[task_id] = "jimeng_image2image_dream_inpaint"
                return task_id
            else:
                raise Exception(f"即梦局部重绘错误: code={result.get('code')}, {result.get('message', '')}")
        raise Exception(f"即梦局部重绘 API Error: HTTP {response.status_code}")
