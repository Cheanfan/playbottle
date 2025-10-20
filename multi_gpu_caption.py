import json
import os
from datasets import load_dataset
from tqdm import tqdm
import multiprocessing as mp
from multiprocessing import Queue, Process
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
import qwen_vl_utils.vision_process
from PIL import Image
import time
from queue import Empty
import gc

# 设置视觉处理参数
qwen_vl_utils.vision_process.MIN_PIXELS = 28 * 28 * 8
qwen_vl_utils.vision_process.MAX_PIXELS = 28 * 28 * 64

class MultiGPUCaptionGenerator:
    def __init__(self, num_gpus=8, batch_size=8, model_name="HuggingFaceM4/idefics2-8b"):
        self.num_gpus = num_gpus
        self.batch_size = batch_size
        self.model_name = model_name
        
    def worker_process(self, gpu_id, task_queue, result_queue, progress_queue):
        """每个GPU上的工作进程"""
        try:
            # 设置CUDA设备
            torch.cuda.set_device(gpu_id)
            device = f"cuda:{gpu_id}"
            
            # 加载模型到指定GPU
            print(f"在GPU {gpu_id}上加载模型...")
            model = AutoModelForImageTextToText.from_pretrained(
                self.model_name,
                torch_dtype="auto",
                device_map={"": device},
                low_cpu_mem_usage=True
            )
            
            processor = AutoProcessor.from_pretrained(self.model_name)
            
            print(f"GPU {gpu_id} 模型加载完成，开始处理任务")
            
            while True:
                try:
                    # 从队列获取批次任务
                    batch_tasks = task_queue.get(timeout=10)
                    if batch_tasks is None:  # 结束信号
                        break
                    
                    # 批量处理图片
                    batch_results = self.process_batch(batch_tasks, model, processor, device)
                    
                    # 将结果放入结果队列
                    for result in batch_results:
                        result_queue.put(result)
                    
                    # 更新进度
                    progress_queue.put(len(batch_tasks))
                    
                    # 清理GPU内存
                    torch.cuda.empty_cache()
                    gc.collect()
                    
                except Empty:
                    print(f"GPU {gpu_id} 等待任务超时，继续等待...")
                    continue
                except Exception as e:
                    print(f"GPU {gpu_id} 处理出错: {e}")
                    continue
                    
        except Exception as e:
            print(f"GPU {gpu_id} 初始化失败: {e}")
        finally:
            print(f"GPU {gpu_id} 工作进程结束")
    
    def process_batch(self, batch_tasks, model, processor, device):
        """批量处理图片"""
        results = []
        
        try:
            # 准备批次数据
            images = []
            image_paths = []
            
            for task in batch_tasks:
                image_path = task['image_path']
                full_path = f"/root/dataset/raw/{image_path}"
                
                try:
                    image = Image.open(full_path).convert("RGB")
                    images.append(image)
                    image_paths.append(image_path)
                except Exception as e:
                    print(f"无法加载图片 {image_path}: {e}")
                    results.append({
                        'image_path': image_path,
                        'caption': f"ERROR: 无法加载图片 - {e}",
                        'success': False
                    })
            
            if not images:
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
            
            # 批量处理
            for i, (image, image_path) in enumerate(zip(images, image_paths)):
                try:
                    prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
                    inputs = processor(text=prompt, images=[image], return_tensors="pt")
                    
                    # 将输入移动到GPU
                    inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}
                    
                    with torch.no_grad():
                        generated_ids = model.generate(**inputs, max_new_tokens=500, do_sample=False)
                        generated_texts = processor.batch_decode(generated_ids, skip_special_tokens=True)
                    
                    caption = generated_texts[0].strip()
                    
                    results.append({
                        'image_path': image_path,
                        'caption': caption,
                        'success': True
                    })
                    
                except Exception as e:
                    print(f"处理图片 {image_path} 时出错: {e}")
                    results.append({
                        'image_path': image_path,
                        'caption': f"ERROR: 处理失败 - {e}",
                        'success': False
                    })
            
        except Exception as e:
            print(f"批量处理出错: {e}")
            for image_path in image_paths:
                results.append({
                    'image_path': image_path,
                    'caption': f"ERROR: 批量处理失败 - {e}",
                    'success': False
                })
        
        return results
    
    def prepare_tasks(self):
        """准备所有任务"""
        total_jsons = os.listdir("./jsons")
        all_tasks = []
        
        print("准备任务列表...")
        for _json in tqdm(total_jsons, desc="扫描JSON文件"):
            try:
                with open(f"./jsons/{_json}") as file:
                    name_index = _json.rfind(".")
                    name = _json[:name_index]
                    _data = json.load(file)
                
                with open(f"./json_detail/{_json}") as file:
                    detail_json = json.load(file)
                
                if len(detail_json["images"]) != len(_data["images"]):
                    print(f"图片数量不匹配: {name}")
                    continue
                
                types = detail_json["types"]
                _images = _data["images"]
                
                for img_idx, img in enumerate(detail_json["images"]):
                    if types[img_idx] not in ["TextElement", "ImageElement"]:
                        image_file = _images[img_idx]["file"]
                        
                        # 检查是否已经处理过
                        output_path = f"./shape_descriptions/{image_file}.txt"
                        if not os.path.exists(output_path):
                            all_tasks.append({
                                'image_path': image_file,
                                'output_path': output_path,
                                'json_name': name
                            })
                        
            except Exception as e:
                print(f"处理JSON文件 {_json} 时出错: {e}")
                continue
        
        print(f"总共需要处理 {len(all_tasks)} 张图片")
        return all_tasks
    
    def create_batches(self, tasks):
        """将任务分成批次"""
        batches = []
        for i in range(0, len(tasks), self.batch_size):
            batch = tasks[i:i + self.batch_size]
            batches.append(batch)
        return batches
    
    def run(self):
        """运行多GPU处理"""
        print("开始多GPU图片描述生成...")
        
        # 创建输出目录
        os.makedirs("./shape_descriptions", exist_ok=True)
        
        # 准备任务
        all_tasks = self.prepare_tasks()
        if not all_tasks:
            print("没有需要处理的任务")
            return
        
        # 创建批次
        batches = self.create_batches(all_tasks)
        print(f"分成 {len(batches)} 个批次，每个批次 {self.batch_size} 张图片")
        
        # 创建队列
        task_queue = Queue(maxsize=len(batches) + self.num_gpus)
        result_queue = Queue()
        progress_queue = Queue()
        
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
                args=(gpu_id, task_queue, result_queue, progress_queue)
            )
            p.start()
            processes.append(p)
        
        # 监控进度
        total_processed = 0
        total_images = len(all_tasks)
        
        with tqdm(total=total_images, desc="处理进度") as pbar:
            start_time = time.time()
            
            # 收集结果
            while total_processed < total_images:
                try:
                    # 获取结果
                    result = result_queue.get(timeout=1)
                    
                    # 保存结果
                    if result['success']:
                        with open(result['output_path'], "w", encoding='utf-8') as file:
                            file.write(result['caption'])
                    else:
                        print(f"处理失败: {result['image_path']} - {result['caption']}")
                    
                    total_processed += 1
                    pbar.update(1)
                    
                    # 显示速度信息
                    if total_processed % 100 == 0:
                        elapsed = time.time() - start_time
                        speed = total_processed / elapsed
                        pbar.set_postfix({
                            'speed': f'{speed:.2f} img/s',
                            'GPU利用率': f'{self.num_gpus}x'
                        })
                
                except Empty:
                    continue
                except Exception as e:
                    print(f"收集结果时出错: {e}")
                    break
        
        # 等待所有进程结束
        for p in processes:
            p.join()
        
        elapsed_time = time.time() - start_time
        print(f"\n处理完成!")
        print(f"总用时: {elapsed_time:.2f} 秒")
        print(f"平均速度: {total_processed / elapsed_time:.2f} 图片/秒")
        print(f"GPU加速比: {self.num_gpus}x")

def main():
    # 配置参数
    NUM_GPUS = 8  # GPU数量
    BATCH_SIZE = 8  # 每个GPU每次处理的图片数
    
    print(f"配置: {NUM_GPUS} 个GPU, 每个GPU批次大小: {BATCH_SIZE}")
    print(f"理论并行处理能力: {NUM_GPUS * BATCH_SIZE} 张图片/批次")
    
    # 创建并运行处理器
    generator = MultiGPUCaptionGenerator(
        num_gpus=NUM_GPUS,
        batch_size=BATCH_SIZE
    )
    
    generator.run()

if __name__ == "__main__":
    # 设置多进程启动方式
    mp.set_start_method('spawn', force=True)
    main() 