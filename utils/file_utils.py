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
    """检查图片大小，如果超过限制则压缩，返回处理后的图片路径（优化版）
    
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
    
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"[图片压缩] 无法打开图片: {e}")
        return image_path
    
    temp_dir = tempfile.gettempdir()
    base_name = os.path.basename(image_path)
    name, ext = os.path.splitext(base_name)
    
    unique_id = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    temp_path = os.path.join(temp_dir, f"{name}_{unique_id}.jpg")
    
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # 优化：使用二分查找算法快速找到合适的质量值
    low, high = 10, 95
    best_quality = 10
    best_size = float('inf')
    
    while low <= high:
        quality = (low + high) // 2
        img.save(temp_path, 'JPEG', quality=quality, optimize=True)
        
        compressed_size = get_file_size_mb(temp_path)
        
        if compressed_size <= max_size_mb:
            # 当前质量满足要求，尝试更高质量
            best_quality = quality
            best_size = compressed_size
            low = quality + 1
        else:
            # 当前质量太大，降低质量
            high = quality - 1
    
    # 使用找到的最佳质量重新保存
    img.save(temp_path, 'JPEG', quality=best_quality, optimize=True)
    final_size = get_file_size_mb(temp_path)
    
    print(f"[图片压缩] 完成: {file_size:.2f}MB -> {final_size:.2f}MB (quality={best_quality})")
    return temp_path


def convert_video_to_mp4(video_path: str, max_size_mb: float = 50) -> str:
    """将视频转换为 MP4 格式并压缩到指定大小
    
    Args:
        video_path: 原视频路径
        max_size_mb: 最大允许大小（MB），默认50MB
    
    Returns:
        处理后的视频路径
    """
    import subprocess
    import tempfile
    
    file_size = get_file_size_mb(video_path)
    ext = os.path.splitext(video_path)[1].lower()
    
    # 如果已经是 mp4 且大小符合要求，直接返回
    if ext == '.mp4' and file_size <= max_size_mb:
        return video_path
    
    print(f"[视频处理] 开始处理: {os.path.basename(video_path)} ({file_size:.2f}MB)")
    
    temp_dir = tempfile.gettempdir()
    base_name = os.path.basename(video_path)
    name = os.path.splitext(base_name)[0]
    temp_path = os.path.join(temp_dir, f"{name}_converted.mp4")
    
    try:
        # 先尝试直接转换格式（不重新编码）
        if ext != '.mp4':
            cmd = [
                'ffmpeg', '-i', video_path,
                '-c', 'copy',  # 不重新编码
                '-y',  # 覆盖输出
                temp_path
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)
            
            if os.path.exists(temp_path) and get_file_size_mb(temp_path) <= max_size_mb:
                print(f"[视频处理] 格式转换完成: {file_size:.2f}MB -> {get_file_size_mb(temp_path):.2f}MB")
                return temp_path
        
        # 如果文件太大或格式转换失败，重新编码压缩
        # 计算目标比特率 (bits per second)
        # 假设视频时长，使用 ffprobe 获取实际时长
        try:
            probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            duration = float(result.stdout.strip())
        except:
            duration = 30  # 默认30秒
        
        # 目标比特率 = (目标大小 MB * 8 * 1024 * 1024) / 时长秒
        target_bitrate = int((max_size_mb * 8 * 1024 * 1024) / duration)
        
        cmd = [
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264',  # H.264 编码
            '-b:v', f'{target_bitrate}',  # 视频比特率
            '-c:a', 'aac',  # 音频编码
            '-b:a', '128k',  # 音频比特率
            '-y',  # 覆盖输出
            temp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=300)
        
        if os.path.exists(temp_path):
            final_size = get_file_size_mb(temp_path)
            print(f"[视频处理] 压缩完成: {file_size:.2f}MB -> {final_size:.2f}MB")
            return temp_path
        else:
            print(f"[视频处理] 压缩失败，返回原文件")
            return video_path
            
    except FileNotFoundError:
        print(f"[视频处理] ffmpeg 未安装，返回原文件")
        return video_path
    except Exception as e:
        print(f"[视频处理] 错误: {e}，返回原文件")
        return video_path


def convert_audio_to_mp3(audio_path: str, max_size_mb: float = 15) -> str:
    """将音频转换为 MP3 格式并压缩到指定大小
    
    Args:
        audio_path: 原音频路径
        max_size_mb: 最大允许大小（MB），默认15MB
    
    Returns:
        处理后的音频路径
    """
    import subprocess
    import tempfile
    
    file_size = get_file_size_mb(audio_path)
    ext = os.path.splitext(audio_path)[1].lower()
    
    # 如果已经是 mp3 且大小符合要求，直接返回
    if ext == '.mp3' and file_size <= max_size_mb:
        return audio_path
    
    print(f"[音频处理] 开始处理: {os.path.basename(audio_path)} ({file_size:.2f}MB)")
    
    temp_dir = tempfile.gettempdir()
    base_name = os.path.basename(audio_path)
    name = os.path.splitext(base_name)[0]
    temp_path = os.path.join(temp_dir, f"{name}_converted.mp3")
    
    try:
        # 获取音频时长
        try:
            probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            duration = float(result.stdout.strip())
        except:
            duration = 180  # 默认3分钟
        
        # 目标比特率
        target_bitrate = int((max_size_mb * 8 * 1024 * 1024) / duration)
        # 限制比特率范围
        target_bitrate = max(64000, min(target_bitrate, 320000))
        
        cmd = [
            'ffmpeg', '-i', audio_path,
            '-c:a', 'libmp3lame',  # MP3 编码
            '-b:a', f'{target_bitrate}',  # 音频比特率
            '-y',  # 覆盖输出
            temp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
        
        if os.path.exists(temp_path):
            final_size = get_file_size_mb(temp_path)
            print(f"[音频处理] 转换完成: {file_size:.2f}MB -> {final_size:.2f}MB")
            return temp_path
        else:
            print(f"[音频处理] 转换失败，返回原文件")
            return audio_path
            
    except FileNotFoundError:
        print(f"[音频处理] ffmpeg 未安装，返回原文件")
        return audio_path
    except Exception as e:
        print(f"[音频处理] 错误: {e}，返回原文件")
        return audio_path
