# 项目性能优化方案

## 问题分析

经过代码审查，发现以下主要性能瓶颈：

1. **缩略图加载和渲染问题**
2. **缩略图条重建开销**
3. **场景渲染优化不足**
4. **节点和连线更新过于频繁**
5. **内存使用优化不足**

---

## 优化方案

### [x] 任务 1：优化缩略图缓存
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 增加缓存大小
  - 优化缓存策略
  - 添加内存使用监控
- **Success Criteria**:
  - 缓存命中率提高
  - 内存使用更加合理
- **Test Requirements**:
  - `programmatic` TR-1.1: 缓存大小可配置，默认从 200 增加到 500
  - `human-judgement` TR-1.2: 大量图片加载时不会明显卡顿

---

### [x] 任务 2：实现缩略图延迟加载
- **Priority**: P0
- **Depends On**: 任务 1
- **Description**: 
  - DraggableThumbnail 只在可见时加载缩略图
  - 使用 QTimer 延迟加载
  - 视口外的缩略图不加载
- **Success Criteria**:
  - 初始加载速度显著提升
  - 滚动时才加载新缩略图
- **Test Requirements**:
  - `programmatic` TR-2.1: 缩略图只在进入视口时加载
  - `human-judgement` TR-2.2: 添加多个图片节点时界面响应流畅

---

### [x] 任务 3：优化缩略图条更新
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 增量更新缩略图条，而非完全重建
  - 只更新变化的部分
  - 复用现有控件
- **Success Criteria**:
  - 添加/移除图片时只更新必要的控件
  - 减少控件创建/销毁开销
- **Test Requirements**:
  - `programmatic` TR-3.1: update_thumbnails 只重建变化的缩略图
  - `human-judgement` TR-3.2: 连接/断开图片时界面响应更快

---

### [x] 任务 4：优化场景渲染
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 使用 ItemCacheMode 缓存节点渲染
  - 优化场景初始大小
  - 添加视口裁剪优化
- **Success Criteria**:
  - 场景渲染帧率提升
  - 拖动和缩放更流畅
- **Test Requirements**:
  - `programmatic` TR-4.1: 节点启用 DeviceCoordinateCache
  - `human-judgement` TR-4.2: 大量节点时拖动仍保持流畅

---

### [x] 任务 5：优化连线更新
- **Priority**: P2
- **Depends On**: None
- **Description**: 
  - 减少不必要的连线更新
  - 使用节流器限制更新频率
  - 批量更新连线
- **Success Criteria**:
  - 节点拖动时连线更新更高效
  - 减少 CPU 使用率
- **Test Requirements**:
  - `programmatic` TR-5.1: 连线更新使用节流器
  - `human-judgement` TR-5.2: 拖动节点时 CPU 使用率降低

---

### [x] 任务 6：添加内存优化
- **Priority**: P2
- **Depends On**: 任务 1
- **Description**: 
  - 监控内存使用
  - 自动清理不常用的缓存
  - 限制最大缩略图尺寸
- **Success Criteria**:
  - 内存使用更加稳定
  - 长时间运行不会内存泄漏
- **Test Requirements**:
  - `programmatic` TR-6.1: 添加内存使用监控
  - `human-judgement` TR-6.2: 长时间运行内存不会持续增长

---

## 实施顺序

1. 先实施 **任务 1** 和 **任务 2**（最关键的性能优化）
2. 然后实施 **任务 3** 和 **任务 4**
3. 最后实施 **任务 5** 和 **任务 6**

---

### [ ] 任务 7：缩小缩略图尺寸以减少内存使用
- **Priority**: P1
- **Depends On**: 任务 1
- **Description**: 
  - 将缩略图尺寸从 512x512 减小到 256x256
  - 显著减少内存使用
  - 保持显示质量
- **Success Criteria**:
  - 缩略图内存使用减少 75%
  - 显示质量仍然足够好
- **Test Requirements**:
  - `programmatic` TR-7.1: 缩略图尺寸改为 256x256
  - `human-judgement` TR-7.2: 缩略图显示质量仍然可接受

---

## 实施顺序

1. 先实施 **任务 1** 和 **任务 2**（最关键的性能优化）
2. 然后实施 **任务 3** 和 **任务 4**
3. 最后实施 **任务 5**、**任务 6** 和 **任务 7**

## 预期效果

- 初始加载速度提升 50%+
- 大量图片节点时界面响应流畅
- 内存使用更加稳定
- 整体用户体验显著改善
