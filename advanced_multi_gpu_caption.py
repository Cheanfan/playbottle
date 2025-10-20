import json
import os
from datasets import load_dataset
from tqdm import tqdm
import multiprocessing as mp
from multiprocessing import Queue, Process, Manager, Value
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
import qwen_vl_utils.vision_process
from PIL import Image
import time
from queue import Empty
import gc
import psutil
import threading
from contextlib import contextmanager
import logging
import signal
import sys

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置视觉处理参数
qwen_vl_utils.vision_process.MIN_PIXELS = 28 * 28 * 8
qwen_vl_utils.vision_process.MAX_PIXELS = 28 * 28 * 64

class AdvancedMultiGPUCaptionGenerator:
    def __init__(self, num_gpus=8, batch_size=8, model_name="HuggingFaceM4/idefics2-8b",
                 max_retries=3, checkpoint_interval=1000):
        self.num_gpus = num_gpus
        self.batch_size = batch_size
        self.model_name = model_name
        self.max_retries = max_retries
        self.checkpoint_interval = checkpoint_interval
        
        # 共享状态
        self.manager = Manager()
        self.processed_count = self.manager.Value('i', 0)
        self.failed_count = self.manager.Value('i', 0)
        self.gpu_stats = self.manager.dict()
        
        # 初始化GPU统计
        for i in range(num_gpus):
            self.gpu_stats[i] = {
                'processed': 0,
                'failed': 0,
                'avg_time': 0.0,
                'memory_usage': 0.0
            }
    
    @contextmanager
    def gpu_memory_monitor(self, gpu_id):
        """GPU内存监控上下文管理器"""
        try:
            torch.cuda.set_device(gpu_id)
            torch.cuda.empty_cache()
            yield
        finally:
            if torch.cuda.is_available():
                memory_used = torch.cuda.memory_allocated(gpu_id) / 1024**3  # GB
                self.gpu_stats[gpu_id]['memory_usage'] = memory_used
                torch.cuda.empty_cache()
                gc.collect()
    
    def worker_process(self, gpu_id, task_queue, result_queue, progress_queue, stop_event):
        """增强的工作进程，包含错误恢复和性能监控"""
        
        def signal_handler(signum, frame):
            logger.info(f"GPU {gpu_id} 收到停止信号")
            stop_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        model = None
        processor = None
        consecutive_failures = 0
        
        try:
            # 设置CUDA设备
            torch.cuda.set_device(gpu_id)
            device = f"cuda:{gpu_id}"
            
            logger.info(f"GPU {gpu_id} 开始加载模型...")
            
            # 加载模型到指定GPU
            model = AutoModelForImageTextToText.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16,  # 使用半精度节省内存
                device_map={"": device},
                low_cpu_mem_usage=True,
                use_cache=False  # 禁用缓存节省内存
            )
            
            processor = AutoProcessor.from_pretrained(self.model_name)
            
            # 设置模型为评估模式
            model.eval()
            
            logger.info(f"GPU {gpu_id} 模型加载完成")
            
            while not stop_event.is_set():
                try:
                    # 从队列获取批次任务
                    batch_tasks = task_queue.get(timeout=5)
                    if batch_tasks is None:  # 结束信号
                        break
                    
                    start_time = time.time()
                    
                    with self.gpu_memory_monitor(gpu_id):
                        # 批量处理图片
                        batch_results = self.process_batch_advanced(
                            batch_tasks, model, processor, device, gpu_id
                        )
                    
                    processing_time = time.time() - start_time
                    
                    # 更新统计信息
                    success_count = sum(1 for r in batch_results if r['success'])
                    fail_count = len(batch_results) - success_count
                    
                    stats = dict(self.gpu_stats[gpu_id])
                    stats['processed'] += success_count
                    stats['failed'] += fail_count
                    stats['avg_time'] = (stats['avg_time'] + processing_time) / 2
                    self.gpu_stats[gpu_id] = stats
                    
                    # 将结果放入结果队列
                    for result in batch_results:
                        result_queue.put(result)
                    
                    # 更新进度
                    progress_queue.put(len(batch_tasks))
                    
                    # 重置连续失败计数
                    consecutive_failures = 0
                    
                except Empty:
                    continue
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"GPU {gpu_id} 处理出错 (连续失败 {consecutive_failures}): {e}")
                    
                    if consecutive_failures >= 3:
                        logger.warning(f"GPU {gpu_id} 连续失败过多，重启模型")
                        try:
                            del model, processor
                            torch.cuda.empty_cache()
                            gc.collect()
                            time.sleep(2)
                            
                            # 重新加载模型
                            model = AutoModelForImageTextToText.from_pretrained(
                                self.model_name,
                                torch_dtype=torch.float16,
                                device_map={"": device},
                                low_cpu_mem_usage=True,
                                use_cache=False
                            )
                            processor = AutoProcessor.from_pretrained(self.model_name)
                            model.eval()
                            
                            consecutive_failures = 0
                            logger.info(f"GPU {gpu_id} 模型重启完成")
                            
                        except Exception as restart_error:
                            logger.error(f"GPU {gpu_id} 重启失败: {restart_error}")
                            break
                    
                    time.sleep(1)  # 短暂休息
                    
        except Exception as e:
            logger.error(f"GPU {gpu_id} 致命错误: {e}")
        finally:
            if model is not None:
                del model
            if processor is not None:
                del processor
            torch.cuda.empty_cache()
            gc.collect()
            logger.info(f"GPU {gpu_id} 工作进程结束")
    
    def process_batch_advanced(self, batch_tasks, model, processor, device, gpu_id):
        """高级批量处理，包含更多优化"""
        results = []
        
        try:
            # 准备批次数据
            valid_tasks = []
            
            for task in batch_tasks:
                image_path = task['image_path']
                full_path = f"/root/dataset/raw/{image_path}"
                
                # 预检查文件是否存在
                if not os.path.exists(full_path):
                    results.append({
                        'image_path': image_path,
                        'output_path': task['output_path'],
                        'caption': "ERROR: 文件不存在",
                        'success': False
                    })
                    continue
                
                try:
                    # 检查图片是否可以打开（快速检查）
                    with Image.open(full_path) as img:
                        if img.mode not in ['RGB', 'RGBA', 'L']:
                            results.append({
                                'image_path': image_path,
                                'output_path': task['output_path'],
                                'caption': f"ERROR: 不支持的图片格式 {img.mode}",
                                'success': False
                            })
                            continue
                    
                    valid_tasks.append(task)
                    
                except Exception as e:
                    results.append({
                        'image_path': image_path,
                        'output_path': task['output_path'],
                        'caption': f"ERROR: 图片格式错误 - {e}",
                        'success': False
                    })
            
            if not valid_tasks:
                return results
            
            # 准备消息模板
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": "describe the image briefly, within 30 words, output the description directly, do not start with 'the image is' or 'the photo is' or 'I can see' or anything that start with this image."},
                    ],
                }
            ]
            
            # 逐个处理（避免内存溢出）
            for task in valid_tasks:
                retries = 0
                success = False
                
                while retries < self.max_retries and not success:
                    try:
                        image_path = task['image_path']
                        full_path = f"/root/dataset/raw/{image_path}"
                        
                        # 加载并预处理图片
                        with Image.open(full_path) as img:
                            image = img.convert("RGB")
                            
                            # 可选：调整图片大小以节省内存
                            max_size = 1024
                            if max(image.size) > max_size:
                                ratio = max_size / max(image.size)
                                new_size = tuple(int(dim * ratio) for dim in image.size)
                                image = image.resize(new_size, Image.Resampling.LANCZOS)
                        
                        prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
                        
                        # 处理输入
                        with torch.no_grad():
                            inputs = processor(text=prompt, images=[image], return_tensors="pt")
                            
                            # 将输入移动到GPU
                            inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v 
                                    for k, v in inputs.items()}
                            
                            # 生成描述
                            generated_ids = model.generate(
                                **inputs,
                                max_new_tokens=100,  # 减少生成长度
                                do_sample=False,
                                pad_token_id=processor.tokenizer.eos_token_id,
                                num_beams=1  # 使用贪婪搜索节省内存
                            )
                            
                            generated_texts = processor.batch_decode(
                                generated_ids, 
                                skip_special_tokens=True
                            )
                        
                        caption = generated_texts[0].strip()
                        
                        # 清理生成的文本
                        if prompt in caption:
                            caption = caption.replace(prompt, "").strip()
                        
                        results.append({
                            'image_path': image_path,
                            'output_path': task['output_path'],
                            'caption': caption,
                            'success': True
                        })
                        
                        success = True
                        
                    except torch.cuda.OutOfMemoryError:
                        torch.cuda.empty_cache()
                        gc.collect()
                        retries += 1
                        logger.warning(f"GPU {gpu_id} 内存不足，重试 {retries}/{self.max_retries}")
                        time.sleep(1)
                        
                    except Exception as e:
                        retries += 1
                        logger.warning(f"GPU {gpu_id} 处理 {image_path} 失败 (尝试 {retries}): {e}")
                        time.sleep(0.5)
                
                if not success:
                    results.append({
                        'image_path': task['image_path'],
                        'output_path': task['output_path'],
                        'caption': f"ERROR: 处理失败，已重试 {self.max_retries} 次",
                        'success': False
                    })
            
        except Exception as e:
            logger.error(f"GPU {gpu_id} 批量处理严重错误: {e}")
            for task in batch_tasks:
                results.append({
                    'image_path': task['image_path'],
                    'output_path': task['output_path'],
                    'caption': f"ERROR: 批量处理失败 - {e}",
                    'success': False
                })
        
        return results
    
    def save_checkpoint(self, processed_files):
        """保存检查点"""
        checkpoint_data = {
            'processed_files': list(processed_files),
            'timestamp': time.time(),
            'stats': dict(self.gpu_stats)
        }
        
        with open('checkpoint.json', 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"检查点已保存，已处理 {len(processed_files)} 个文件")
    
    def load_checkpoint(self):
        """加载检查点"""
        if os.path.exists('checkpoint.json'):
            try:
                with open('checkpoint.json', 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                logger.info(f"加载检查点，跳过 {len(checkpoint_data['processed_files'])} 个已处理文件")
                return set(checkpoint_data['processed_files'])
            except Exception as e:
                logger.warning(f"加载检查点失败: {e}")
        return set()
    
    def monitor_system_resources(self, stop_event):
        """系统资源监控线程"""
        while not stop_event.is_set():
            try:
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # 内存使用率
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                
                # GPU内存使用情况
                gpu_memory_info = []
                for i in range(self.num_gpus):
                    if torch.cuda.is_available():
                        memory_used = torch.cuda.memory_allocated(i) / 1024**3
                        memory_total = torch.cuda.get_device_properties(i).total_memory / 1024**3
                        gpu_memory_info.append(f"GPU{i}: {memory_used:.1f}/{memory_total:.1f}GB")
                
                if cpu_percent > 90 or memory_percent > 90:
                    logger.warning(f"系统资源紧张 - CPU: {cpu_percent}%, 内存: {memory_percent}%")
                
                time.sleep(30)  # 每30秒检查一次
                
            except Exception as e:
                logger.error(f"资源监控错误: {e}")
                time.sleep(60)
    
    def run(self):
        """运行高级多GPU处理"""
        logger.info("开始高级多GPU图片描述生成...")
        
        # 创建输出目录
        os.makedirs("./shape_descriptions", exist_ok=True)
        
        # 加载检查点
        processed_files = self.load_checkpoint()
        
        # 准备任务
        all_tasks = self.prepare_tasks(processed_files)
        if not all_tasks:
            logger.info("没有需要处理的任务")
            return
        
        # 创建批次
        batches = self.create_batches(all_tasks)
        logger.info(f"分成 {len(batches)} 个批次，每个批次 {self.batch_size} 张图片")
        logger.info(f"总计需要处理 {len(all_tasks)} 张图片")
        
        # 创建队列和事件
        task_queue = Queue(maxsize=min(len(batches) + self.num_gpus, 1000))
        result_queue = Queue()
        progress_queue = Queue()
        stop_event = mp.Event()
        
        # 启动资源监控线程
        monitor_thread = threading.Thread(
            target=self.monitor_system_resources,
            args=(stop_event,)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        try:
            # 将批次任务放入队列
            for batch in batches:
                task_queue.put(batch)
            
            # 添加结束信号
            for _ in range(self.num_gpus):
                task_queue.put(None)
            
            # 启动工作进程
            processes = []
            for gpu_id in range(self.num_gpus):
                p = Process(
                    target=self.worker_process,
                    args=(gpu_id, task_queue, result_queue, progress_queue, stop_event)
                )
                p.start()
                processes.append(p)
            
            # 监控进度和收集结果
            total_processed = 0
            total_images = len(all_tasks)
            
            with tqdm(total=total_images, desc="处理进度") as pbar:
                start_time = time.time()
                last_checkpoint = 0
                
                while total_processed < total_images:
                    try:
                        result = result_queue.get(timeout=2)
                        
                        # 保存结果
                        if result['success']:
                            with open(result['output_path'], "w", encoding='utf-8') as file:
                                file.write(result['caption'])
                            processed_files.add(result['image_path'])
                        else:
                            logger.warning(f"处理失败: {result['image_path']} - {result['caption']}")
                        
                        total_processed += 1
                        pbar.update(1)
                        
                        # 定期保存检查点
                        if total_processed - last_checkpoint >= self.checkpoint_interval:
                            self.save_checkpoint(processed_files)
                            last_checkpoint = total_processed
                        
                        # 更新进度信息
                        if total_processed % 50 == 0:
                            elapsed = time.time() - start_time
                            speed = total_processed / elapsed
                            
                            # 计算GPU统计信息
                            gpu_info = []
                            for i in range(self.num_gpus):
                                stats = self.gpu_stats[i]
                                gpu_info.append(f"GPU{i}:{stats['processed']}✓/{stats['failed']}✗")
                            
                            pbar.set_postfix({
                                'speed': f'{speed:.2f} img/s',
                                'GPUs': ' '.join(gpu_info[:4])  # 显示前4个GPU的状态
                            })
                    
                    except Empty:
                        continue
                    except KeyboardInterrupt:
                        logger.info("收到中断信号，正在停止...")
                        stop_event.set()
                        break
                    except Exception as e:
                        logger.error(f"收集结果时出错: {e}")
                        continue
            
            # 保存最终检查点
            self.save_checkpoint(processed_files)
            
        except KeyboardInterrupt:
            logger.info("手动中断处理")
            stop_event.set()
        finally:
            # 等待所有进程结束
            for p in processes:
                p.join(timeout=10)
                if p.is_alive():
                    p.terminate()
                    p.join()
            
            stop_event.set()
            
            elapsed_time = time.time() - start_time
            logger.info(f"\n处理完成!")
            logger.info(f"总用时: {elapsed_time:.2f} 秒")
            logger.info(f"平均速度: {total_processed / elapsed_time:.2f} 图片/秒")
            logger.info(f"成功处理: {total_processed} 张图片")
            
            # 打印GPU统计信息
            for i in range(self.num_gpus):
                stats = self.gpu_stats[i]
                logger.info(f"GPU {i}: 成功 {stats['processed']}, 失败 {stats['failed']}, "
                          f"平均耗时 {stats['avg_time']:.2f}s")
    
    def prepare_tasks(self, skip_files=None):
        """准备任务列表，跳过已处理的文件"""
        if skip_files is None:
            skip_files = set()
        
        total_jsons = os.listdir("./jsons")
        all_tasks = []
        
        logger.info("准备任务列表...")
        for _json in tqdm(total_jsons, desc="扫描JSON文件"):
            try:
                with open(f"./jsons/{_json}") as file:
                    name_index = _json.rfind(".")
                    name = _json[:name_index]
                    _data = json.load(file)
                
                with open(f"./json_detail/{_json}") as file:
                    detail_json = json.load(file)
                
                if len(detail_json["images"]) != len(_data["images"]):
                    logger.warning(f"图片数量不匹配: {name}")
                    continue
                
                types = detail_json["types"]
                _images = _data["images"]
                
                for img_idx, img in enumerate(detail_json["images"]):
                    if types[img_idx] not in ["TextElement", "ImageElement"]:
                        image_file = _images[img_idx]["file"]
                        
                        # 跳过已处理的文件
                        if image_file in skip_files:
                            continue
                        
                        output_path = f"./shape_descriptions/{image_file}.txt"
                        if not os.path.exists(output_path):
                            all_tasks.append({
                                'image_path': image_file,
                                'output_path': output_path,
                                'json_name': name
                            })
                        
            except Exception as e:
                logger.error(f"处理JSON文件 {_json} 时出错: {e}")
                continue
        
        logger.info(f"总共需要处理 {len(all_tasks)} 张图片")
        return all_tasks
    
    def create_batches(self, tasks):
        """将任务分成批次"""
        batches = []
        for i in range(0, len(tasks), self.batch_size):
            batch = tasks[i:i + self.batch_size]
            batches.append(batch)
        return batches

def main():
    # 配置参数
    NUM_GPUS = 8  # GPU数量
    BATCH_SIZE = 8  # 每个GPU每次处理的图片数
    MAX_RETRIES = 3  # 最大重试次数
    CHECKPOINT_INTERVAL = 1000  # 检查点间隔
    
    logger.info(f"高级多GPU配置:")
    logger.info(f"- GPU数量: {NUM_GPUS}")
    logger.info(f"- 每GPU批次大小: {BATCH_SIZE}")
    logger.info(f"- 最大重试次数: {MAX_RETRIES}")
    logger.info(f"- 检查点间隔: {CHECKPOINT_INTERVAL}")
    logger.info(f"- 理论并行处理能力: {NUM_GPUS * BATCH_SIZE} 张图片/批次")
    
    # 创建并运行处理器
    generator = AdvancedMultiGPUCaptionGenerator(
        num_gpus=NUM_GPUS,
        batch_size=BATCH_SIZE,
        max_retries=MAX_RETRIES,
        checkpoint_interval=CHECKPOINT_INTERVAL
    )
    
    generator.run()

if __name__ == "__main__":
    # 设置多进程启动方式
    mp.set_start_method('spawn', force=True)
    main() 