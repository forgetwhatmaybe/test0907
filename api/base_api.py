import requests
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BaseAPI(ABC):
    def __init__(self):
        self.api_key = ""
        self.secret_key = ""
        self.base_url = ""
    
    def set_credentials(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
    
    @abstractmethod
    def test_connection(self) -> bool:
        pass
    
    @abstractmethod
    def submit_image_to_video_task(self, image_path: str, prompt: str, **kwargs) -> str:
        pass
    
    @abstractmethod
    def get_task_status(self, task_id: str) -> TaskStatus:
        pass
    
    @abstractmethod
    def get_task_result(self, task_id: str) -> Optional[str]:
        pass
    
    def wait_for_completion(self, task_id: str, timeout: int = 600, interval: int = 5,
                            is_stopped=None) -> Optional[str]:
        """轮询等待任务完成
        Args:
            is_stopped: 可选的回调函数，返回 True 表示应该停止等待
        """
        import requests as _requests
        start_time = time.time()
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        def _interruptible_sleep(seconds):
            """可中断的 sleep，每秒检查一次停止信号"""
            for _ in range(int(seconds)):
                if is_stopped and is_stopped():
                    return True  # 被中断
                time.sleep(1)
            remaining = seconds - int(seconds)
            if remaining > 0:
                time.sleep(remaining)
            return is_stopped() if is_stopped else False
        
        while time.time() - start_time < timeout:
            # 检查停止信号
            if is_stopped and is_stopped():
                return None
            
            try:
                status = self.get_task_status(task_id)
                consecutive_errors = 0
                
                if status == TaskStatus.SUCCESS:
                    for attempt in range(3):
                        try:
                            result = self.get_task_result(task_id)
                            if result:
                                return result
                        except (_requests.exceptions.SSLError,
                                _requests.exceptions.ConnectionError) as e:
                            print(f"获取结果失败(第{attempt+1}次): {e}")
                            if _interruptible_sleep(3 * (attempt + 1)):
                                return None
                    return self.get_task_result(task_id)
                elif status == TaskStatus.FAILED:
                    return None
            except (_requests.exceptions.SSLError,
                    _requests.exceptions.ConnectionError,
                    _requests.exceptions.Timeout) as e:
                consecutive_errors += 1
                print(f"轮询状态网络错误(连续第{consecutive_errors}次): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    print(f"连续{max_consecutive_errors}次网络错误，放弃轮询")
                    return None
                if _interruptible_sleep(interval * 2):
                    return None
                continue
            except Exception:
                raise
            
            if _interruptible_sleep(interval):
                return None
        return None
