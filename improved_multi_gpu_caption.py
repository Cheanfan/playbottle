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

class ImprovedMultiGPUCaptionGenerator:
    def __init__(self, num_gpus=8, model_name="HuggingFaceM4/idefics2-8b"):
        self.num_gpus = num_gpus
        self.model_name = model_name
        
    def get_caption(self, image_path, model, processor, device):
        """单张图片描述生成函数 - 基于原始代码"""
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                        },
                        {"type": "text", "text": "describe the image briefly, within 30 words, output the description directly, do not start with 'the image is' or 'the photo is' or 'I can see' or anything that start with this image."},
                    ],
                }
            ]
            
            images = [Image.open(f"/root/dataset/raw/{image_path}").convert("RGB")]
            
            prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = processor(text=prompt, images=images, return_tensors="pt").to(device)

            with torch.no_grad():
                generated_ids = model.generate(**inputs, max_new_tokens=500)
                generated_texts = processor.batch_decode(generated_ids, skip_special_tokens=True)
                res = generated_texts[0]
            
            key = "Assistant: "
            _index = res.rfind(key)
            if _index != -1:
                res = res[_index+len(key):]
            
            return res.strip()
            
        except Exception as e:
            print(f"处理图片 {image_path} 时出错: {e}")
            return f"ERROR: {str(e)}"

    def worker_process(self, gpu_id, tasks_chunk, result_queue, progress_queue):
        """每个GPU上的工作进程"""
        try:
            # 设置CUDA设备
            device = f"cuda:{gpu_id}"
            torch.cuda.set_device(gpu_id)
            
            print(f"GPU {gpu_id}: 开始加载模型...")
            
            # 加载模型到指定GPU
            model = AutoModelForImageTextToText.from_pretrained(
                self.model_name,
                torch_dtype="auto", 
                device_map=device
            ).to(device)
            
            processor = AutoProcessor.from_pretrained(self.model_name)
            
            print(f"GPU {gpu_id}: 模型加载完成，开始处理 {len(tasks_chunk)} 个任务")
            
            # 处理分配给这个GPU的所有任务
            for task in tqdm(tasks_chunk, desc=f"GPU {gpu_id} 进度"):
                try:
                    image_path = task['image_path']
                    output_path = task['output_path']
                    
                    # 检查文件是否已经存在
                    if os.path.exists(output_path):
                        print(f"GPU {gpu_id}: 跳过已存在的文件 {image_path}")
                        progress_queue.put(1)
                        continue
                    
                    # 生成描述
                    caption = self.get_caption(image_path, model, processor, device)
                    
                    # 保存结果
                    result_queue.put({
                        'image_path': image_path,
                        'output_path': output_path,
                        'caption': caption,
                        'success': not caption.startswith('ERROR:')
                    })
                    
                    # 更新进度
                    progress_queue.put(1)
                    
                    # 定期清理GPU内存
                    if len(tasks_chunk) % 10 == 0:
                        torch.cuda.empty_cache()
                        gc.collect()
                    
                except Exception as e:
                    print(f"GPU {gpu_id}: 处理任务时出错 {task['image_path']}: {e}")
                    result_queue.put({
                        'image_path': task['image_path'],
                        'output_path': task['output_path'],
                        'caption': f"ERROR: {str(e)}",
                        'success': False
                    })
                    progress_queue.put(1)
                    
        except Exception as e:
            print(f"GPU {gpu_id}: 初始化失败: {e}")
        finally:
            # 清理GPU内存
            if 'model' in locals():
                del model
            torch.cuda.empty_cache()
            gc.collect()
            print(f"GPU {gpu_id}: 工作进程结束")
    
    def prepare_tasks(self):
        """准备所有需要处理的任务 - 基于原始代码逻辑"""
        total_jsons = os.listdir("./jsons")
        all_tasks = []
        
        print("准备任务列表...")
        progress_bar = tqdm(total=len(total_jsons), desc="扫描JSON文件")
        
        for _json in total_jsons:
            try:
                with open(f"./jsons/{_json}") as file:
                    name_index = _json.rfind(".")
                    name = _json[:name_index]
                    _data = json.load(file)
                
                with open(f"./json_detail/{_json}") as file:
                    detail_json = json.load(file)
                
                _descriptions = _data["descriptions"]
                _id = name
                
                if len(detail_json["images"]) != len(_data["images"]):
                    print(f"发现图片数量不匹配: {_id}")
                    progress_bar.update(1)
                    continue
                
                # 获取详细信息
                fonts = detail_json["fonts"]
                types = detail_json["types"]
                category = detail_json["category"]
                texts = detail_json["text"]
                text_color = detail_json["text_color"]
                title = detail_json["title"]
                keywords = detail_json["keywords"]
                keyword_results = ','.join(keywords)
                
                canvas_description = f"category: {category}; title: {title}; keywords: {keyword_results}"
                
                detail_imgs = detail_json["images"]
                _images = _data["images"]
                _width = _data["width"]
                _height = _data["height"]
                
                # 处理每张图片
                for img_idx, img in enumerate(detail_imgs):
                    if types[img_idx] != "TextElement" and types[img_idx] != "ImageElement":
                        image_file = _images[img_idx]["file"]
                        output_path = f"./shape_descriptions/{image_file}.txt"
                        
                        # 只添加未处理的任务
                        if not os.path.exists(output_path):
                            all_tasks.append({
                                'image_path': image_file,
                                'output_path': output_path,
                                'json_name': name,
                                'canvas_description': canvas_description,
                                'type': types[img_idx]
                            })
                
                progress_bar.update(1)
                
            except Exception as e:
                print(f"处理JSON文件 {_json} 时出错: {e}")
                progress_bar.update(1)
                continue
        
        progress_bar.close()
        print(f"总共需要处理 {len(all_tasks)} 张图片")
        return all_tasks
    
    def split_tasks(self, all_tasks):
        """将任务平均分成8份"""
        chunk_size = len(all_tasks) // self.num_gpus
        remainder = len(all_tasks) % self.num_gpus
        
        chunks = []
        start_idx = 0
        
        for i in range(self.num_gpus):
            # 如果有余数，前几个进程多分配一个任务
            current_chunk_size = chunk_size + (1 if i < remainder else 0)
            end_idx = start_idx + current_chunk_size
            
            chunk = all_tasks[start_idx:end_idx]
            chunks.append(chunk)
            
            print(f"GPU {i}: 分配 {len(chunk)} 个任务 (索引 {start_idx}-{end_idx-1})")
            start_idx = end_idx
        
        return chunks
    
    def run(self):
        """运行多GPU处理"""
        print("开始多GPU图片描述生成...")
        print(f"使用 {self.num_gpus} 张GPU并行处理")
        
        # 创建输出目录
        os.makedirs("./shape_descriptions", exist_ok=True)
        
        # 准备任务
        all_tasks = self.prepare_tasks()
        if not all_tasks:
            print("没有需要处理的任务")
            return
        
        # 将任务分成8份
        task_chunks = self.split_tasks(all_tasks)
        
        # 创建队列
        result_queue = Queue()
        progress_queue = Queue()
        
        # 启动8个工作进程
        processes = []
        for gpu_id in range(self.num_gpus):
            if gpu_id < len(task_chunks) and len(task_chunks[gpu_id]) > 0:
                p = Process(
                    target=self.worker_process,
                    args=(gpu_id, task_chunks[gpu_id], result_queue, progress_queue)
                )
                p.start()
                processes.append(p)
                print(f"启动GPU {gpu_id} 进程，处理 {len(task_chunks[gpu_id])} 个任务")
        
        # 监控进度和收集结果
        total_processed = 0
        total_images = len(all_tasks)
        successful_count = 0
        failed_count = 0
        
        print(f"\n开始处理 {total_images} 张图片...")
        start_time = time.time()
        
        with tqdm(total=total_images, desc="总体进度") as pbar:
            # 收集结果
            while total_processed < total_images:
                try:
                    # 获取进度更新
                    if not progress_queue.empty():
                        progress_update = progress_queue.get_nowait()
                        total_processed += progress_update
                        pbar.update(progress_update)
                        
                        # 更新速度信息
                        if total_processed > 0:
                            elapsed = time.time() - start_time
                            speed = total_processed / elapsed
                            pbar.set_postfix({
                                'speed': f'{speed:.2f} img/s',
                                'GPUs': self.num_gpus
                            })
                    
                    # 获取结果并保存
                    if not result_queue.empty():
                        result = result_queue.get_nowait()
                        
                        if result['success']:
                            with open(result['output_path'], "w", encoding='utf-8') as file:
                                file.write(result['caption'])
                            successful_count += 1
                        else:
                            print(f"\n处理失败: {result['image_path']} - {result['caption']}")
                            failed_count += 1
                    
                    time.sleep(0.1)  # 避免过度占用CPU
                    
                except Exception as e:
                    print(f"监控进度时出错: {e}")
                    time.sleep(1)
        
        # 等待所有进程结束
        for p in processes:
            p.join()
        
        # 处理剩余的结果
        while not result_queue.empty():
            try:
                result = result_queue.get_nowait()
                if result['success']:
                    with open(result['output_path'], "w", encoding='utf-8') as file:
                        file.write(result['caption'])
                    successful_count += 1
                else:
                    failed_count += 1
            except:
                break
        
        elapsed_time = time.time() - start_time
        print(f"\n处理完成!")
        print(f"总用时: {elapsed_time:.2f} 秒")
        print(f"成功处理: {successful_count} 张图片")
        print(f"处理失败: {failed_count} 张图片")
        print(f"平均速度: {total_processed / elapsed_time:.2f} 图片/秒")
        print(f"GPU并行加速: {self.num_gpus}x")

def main():
    # 配置参数
    NUM_GPUS = 8  # 使用8张GPU
    MODEL_NAME = "HuggingFaceM4/idefics2-8b"
    
    print(f"配置信息:")
    print(f"- GPU数量: {NUM_GPUS}")
    print(f"- 模型: {MODEL_NAME}")
    print(f"- 数据将平均分配到各个GPU上并行处理")
    
    # 创建并运行处理器
    generator = ImprovedMultiGPUCaptionGenerator(
        num_gpus=NUM_GPUS,
        model_name=MODEL_NAME
    )
    
    generator.run()

if __name__ == "__main__":
    # 设置多进程启动方式
    mp.set_start_method('spawn', force=True)
    main() 