"""缩略图缓存管理器 - 使用 LRU 缓存策略"""

from collections import OrderedDict
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
import logging

logger = logging.getLogger(__name__)


class ThumbnailCache:
    """缩略图缓存管理器，避免重复加载和缩放大图片
    
    使用 LRU (Least Recently Used) 策略，当缓存满时移除最久未使用的项。
    最大缓存条目数可通过环境变量 THUMBNAIL_CACHE_SIZE 调整，默认 200。
    """
    _cache = OrderedDict()  # {cache_key: QPixmap}
    _max_cache_size = 200
    _initialized = False
    
    @classmethod
    def _init(cls):
        """延迟初始化，读取环境变量配置"""
        if cls._initialized:
            return
        import os
        try:
            env_size = os.environ.get('THUMBNAIL_CACHE_SIZE', '200')
            cls._max_cache_size = max(50, int(env_size))
        except (ValueError, TypeError):
            cls._max_cache_size = 200
        cls._initialized = True
    
    @classmethod
    def get(cls, image_path, width, height):
        """获取缩略图，如果缓存中没有则创建并缓存
        
        Args:
            image_path: 图片文件路径
            width: 目标宽度
            height: 目标高度
            
        Returns:
            QPixmap 或 None
        """
        cls._init()
        cache_key = f"{image_path}_{width}x{height}"
        
        if cache_key in cls._cache:
            # 移动到末尾（标记为最近使用）
            cls._cache.move_to_end(cache_key)
            return cls._cache[cache_key]
        
        pixmap = cls._load_and_scale(image_path, width, height)
        if pixmap and not pixmap.isNull():
            if len(cls._cache) >= cls._max_cache_size:
                # 移除最久未使用的项（OrderedDict 的第一个）
                cls._cache.popitem(last=False)
            cls._cache[cache_key] = pixmap
        return pixmap
    
    @classmethod
    def _load_and_scale(cls, image_path, width, height):
        """加载图片并缩放，优先使用 cv2 提高速度
        
        尝试多种方法加载图片，确保兼容性：
        1. OpenCV（支持中文路径，速度快）
        2. PIL（备用方案）
        3. QPixmap（最后手段）
        """
        if not image_path:
            return None
            
        # 方法1: 使用 cv2（支持中文路径）
        try:
            import cv2
            import numpy as np
            img_array = np.fromfile(str(image_path), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                scale = min(width / w, height / h)
                new_w, new_h = int(w * scale), int(h * scale)
                img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                q_img = QImage(img_rgb.tobytes(), new_w, new_h, new_w * 3, QImage.Format_RGB888).copy()
                return QPixmap.fromImage(q_img)
        except ImportError:
            logger.debug("OpenCV 不可用，跳过 cv2 加载方式")
        except Exception as e:
            logger.debug(f"cv2 加载失败: {e}")
        
        # 方法2: 使用 PIL
        try:
            from PIL import Image
            pil_img = Image.open(image_path)
            if pil_img.mode in ('RGBA', 'P'):
                pil_img = pil_img.convert('RGB')
            pil_img.thumbnail((width, height))
            data = pil_img.tobytes('raw', 'RGB')
            q_img = QImage(data, pil_img.width, pil_img.height, pil_img.width * 3, QImage.Format_RGB888).copy()
            return QPixmap.fromImage(q_img)
        except ImportError:
            logger.debug("PIL 不可用，跳过 PIL 加载方式")
        except Exception as e:
            logger.debug(f"PIL 加载失败: {e}")
        
        # 方法3: 使用 QPixmap（可能不支持中文路径）
        try:
            return QPixmap(image_path).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception as e:
            logger.warning(f"所有图片加载方式均失败: {e}")
            return None
    
    @classmethod
    def clear(cls):
        """清空缓存"""
        cls._cache.clear()
    
    @classmethod
    def invalidate(cls, image_path):
        """清除指定图片路径的所有缓存（所有尺寸）"""
        if not image_path:
            return
        prefix = f"{image_path}_"
        keys_to_remove = [k for k in cls._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del cls._cache[k]
    
    @classmethod
    def get_stats(cls):
        """获取缓存统计信息"""
        return {
            'size': len(cls._cache),
            'max_size': cls._max_cache_size,
            'usage_percent': len(cls._cache) / cls._max_cache_size * 100
        }
