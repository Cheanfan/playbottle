# 多GPU图片描述生成器

这是一个高性能的多GPU并行图片描述生成系统，支持8张GPU同时处理，每张GPU批量处理8张图片。

## 主要特性

### 基础版本 (`multi_gpu_caption.py`)
- ✅ 8GPU并行处理
- ✅ 批量处理 (每GPU 8张图片/批次)
- ✅ 自动任务分配
- ✅ 实时进度监控
- ✅ GPU内存管理

### 高级版本 (`advanced_multi_gpu_caption.py`)
- ✅ 动态负载均衡
- ✅ 错误恢复与重试机制
- ✅ 检查点保存/恢复
- ✅ 系统资源监控
- ✅ GPU统计信息
- ✅ 内存优化
- ✅ 优雅中断处理

## 性能提升

### 理论性能
- **单GPU**: ~1-2 图片/秒
- **8GPU并行**: ~8-16 图片/秒 (8倍加速)
- **批量处理**: 每批次处理64张图片 (8GPU × 8图片)

### 实际优化
- 使用半精度浮点数 (FP16) 节省50%显存
- 动态图片尺寸调整减少内存占用
- 智能批次管理避免内存溢出
- 多进程并行避免GIL限制

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基础版本
```bash
python multi_gpu_caption.py
```

### 高级版本 (推荐)
```bash
python advanced_multi_gpu_caption.py
```

## 配置参数

在脚本中修改以下参数：

```python
NUM_GPUS = 8          # GPU数量
BATCH_SIZE = 8        # 每GPU批次大小
MAX_RETRIES = 3       # 最大重试次数
CHECKPOINT_INTERVAL = 1000  # 检查点间隔
```

## 目录结构

确保以下目录结构存在：
```
./
├── jsons/              # JSON配置文件目录
├── json_detail/        # 详细JSON文件目录
├── shape_descriptions/ # 输出目录（自动创建）
├── /root/dataset/raw/  # 原始图片目录
└── checkpoint.json     # 检查点文件（自动创建）
```

## 监控和调试

### 实时监控
- 进度条显示处理速度和GPU利用率
- 每50张图片更新统计信息
- GPU内存使用情况监控

### 日志信息
- 详细的错误日志和警告
- GPU加载和处理状态
- 系统资源使用情况

### 检查点机制
- 每1000张图片自动保存进度
- 意外中断后可恢复处理
- 跳过已处理的文件

## 故障排除

### 常见问题

1. **GPU内存不足**
   - 减少 `BATCH_SIZE` 参数
   - 检查其他程序是否占用GPU
   - 使用 `nvidia-smi` 监控GPU状态

2. **进程卡死**
   - 检查图片文件是否损坏
   - 查看日志中的错误信息
   - 使用 Ctrl+C 优雅中断

3. **处理速度慢**
   - 检查硬盘I/O性能
   - 确认网络连接稳定
   - 监控CPU使用率

### 性能调优

1. **内存优化**
   ```python
   # 减少批次大小
   BATCH_SIZE = 4
   
   # 启用更激进的内存清理
   torch.cuda.empty_cache()
   ```

2. **I/O优化**
   - 使用SSD存储图片
   - 预加载图片到内存
   - 异步文件读取

3. **模型优化**
   ```python
   # 使用更小的模型
   model_name = "HuggingFaceM4/idefics2-8b"  # 替换为更小的模型
   
   # 调整生成参数
   max_new_tokens = 50  # 减少生成长度
   num_beams = 1        # 使用贪婪搜索
   ```

## 扩展功能

### 支持更多GPU
```python
NUM_GPUS = 16  # 支持更多GPU
```

### 自定义提示词
```python
custom_prompt = "详细描述这张图片的内容，包括颜色、形状、位置等信息"
```

### 不同模型支持
```python
# 支持其他视觉语言模型
model_name = "Qwen/Qwen2.5-VL-7B-Instruct"
model_name = "microsoft/kosmos-2-patch14-224"
```

## 注意事项

1. **硬件要求**
   - 至少8张GPU，每张16GB显存以上
   - 充足的系统内存 (建议128GB+)
   - 高速存储 (NVMe SSD推荐)

2. **软件要求**
   - CUDA 11.8+
   - Python 3.8+
   - PyTorch 2.0+

3. **数据准备**
   - 确保图片路径正确
   - JSON文件格式正确
   - 足够的磁盘空间存储结果

## 许可证

本项目仅供学习和研究使用。 