import os
import base64
from pathlib import Path
from typing import Optional
import requests


def encode_image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def download_file(url: str, save_path: str, max_retries: int = 3) -> bool:
    """下载文件，带重试机制和 SSL 容错"""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=2,              # 2s, 4s, 8s 递增等待
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = session.get(url, stream=True, timeout=(15, 120))
            response.raise_for_status()
            
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except (requests.exceptions.SSLError, 
                requests.exceptions.ConnectionError) as e:
            last_error = e
            import time
            wait = 3 * (attempt + 1)
            print(f"下载失败(第{attempt+1}次): {e}, {wait}秒后重试...")
            time.sleep(wait)
        except Exception as e:
            last_error = e
            print(f"Download error: {e}")
            break
    
    print(f"下载最终失败: {last_error}")
    return False


def get_available_disks() -> list:
    if os.name == 'nt':
        import string
        disks = []
        for letter in string.ascii_uppercase:
            if os.path.exists(f"{letter}:\\"):
                disks.append(letter)
        return disks
    else:
        return ["/"]


def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


def get_file_size_mb(file_path: str) -> float:
    if os.path.exists(file_path):
        return os.path.getsize(file_path) / (1024 * 1024)
    return 0


def compress_image_if_needed(image_path: str, max_size_mb: float = 4.7) -> str:
    """检查图片大小，如果超过限制则压缩，返回处理后的图片路径
    
    Args:
        image_path: 原图片路径
        max_size_mb: 最大允许大小（MB），默认4.7MB
    
    Returns:
        处理后的图片路径（如果压缩则返回临时文件路径，否则返回原路径）
    """
    from PIL import Image
    import tempfile
    import time
    import random
    
    file_size = get_file_size_mb(image_path)
    
    if file_size <= max_size_mb:
        return image_path
    
    print(f"[图片压缩] 开始压缩: {os.path.basename(image_path)} ({file_size:.2f}MB)")
    
    img = Image.open(image_path)
    
    temp_dir = tempfile.gettempdir()
    base_name = os.path.basename(image_path)
    name, ext = os.path.splitext(base_name)
    
    unique_id = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    temp_path = os.path.join(temp_dir, f"{name}_{unique_id}.jpg")
    
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    quality = 95
    while quality >= 10:
        img.save(temp_path, 'JPEG', quality=quality, optimize=True)
        
        compressed_size = get_file_size_mb(temp_path)
        if compressed_size <= max_size_mb:
            print(f"[图片压缩] 完成: {file_size:.2f}MB -> {compressed_size:.2f}MB (quality={quality})")
            return temp_path
        
        quality -= 5
    
    print(f"[图片压缩] 完成(最低质量): {file_size:.2f}MB -> {get_file_size_mb(temp_path):.2f}MB")
    return temp_path
