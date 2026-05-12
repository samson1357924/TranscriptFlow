#!/usr/bin/env python3
"""
summarize_retry.py - 片段級別重試處理
功能：
1. 讀取失敗片段列表 (failed_chunks_*.json)。
2. 只處理這些失敗片段。
3. 若重試 3 次仍失敗，標記為永久失敗並喚醒。
"""

import os
import sys
import json
import argparse
import subprocess
import tempfile
import time
import glob
from datetime import datetime
from logger_config import get_logger
from state_manager import update_state, set_status_file, load_status
from config_loader import get_env_or_config

logger = get_logger('summarize_retry')
OUTPUT_DIR = os.getenv('SRT_OUTPUT_DIR', './output')

def process_failed_chunks(file_id, batch_file, chunk_indices, chunk_type='embedding'):
    """處理指定的失敗片段 - Branch B 修復策略。
    
    策略：
    1. 讀取原始 chunks input 檔案
    2. 根據 chunk_indices 過濾出需要重試的 chunks
    3. 將過濾後的 chunks 寫入暫時 input 檔案 (_chunks_retry_input.json)
    4. 呼叫 summarize_pipeline.py --input <temp_input> --output <temp_output>
    5. 將結果合併回原始 output 檔案
    """
    logger.info(f"🔄 開始處理檔案 {file_id} 的失敗片段 (類型：{chunk_type}, 數量：{len(chunk_indices)})...")
    
    # 尋找原始 input 和 output 檔案
    # 假設 input 檔案命名為: {file_id}_chunks_input.json
    # 假設 output 檔案命名為: {file_id}_chunks_output.json
    input_file = os.path.join(OUTPUT_DIR, f'{file_id}_chunks_input.json')
    output_file = os.path.join(OUTPUT_DIR, f'{file_id}_chunks_output.json')
    
    # 落實的路徑：也可能在 working directory
    if not os.path.exists(input_file):
        work_dir = os.getenv('SRT_WORK_DIR', os.path.join(os.path.dirname(__file__), '../../../structured_yt_data'))
        input_file = os.path.join(work_dir, f'{file_id}_chunks_input.json')
        output_file = os.path.join(work_dir, f'{file_id}_chunks_output.json')
    
    # 驗證 input 檔案存在
    if not os.path.exists(input_file):
        logger.error(f"❌ Input 檔案不存在：{input_file}")
        return False
    
    # 讀取原始 chunks
    with open(input_file, 'r', encoding='utf-8') as f:
        all_chunks = json.load(f)
    
    # 根據 chunk_indices 過濾出需要重試的 chunks
    # chunk_indices 可能是 chunk_id 列表或索引列表
    # 先嘗試作為 chunk_id 列表處理
    retry_chunks = []
    for chunk in all_chunks:
        chunk_id = chunk.get('chunk_id', '')
        # 如果 chunk_indices 包含 chunk_id
        if str(chunk_id) in [str(idx) for idx in chunk_indices]:
            retry_chunks.append(chunk)
    
    # 如果沒有找到匹配的 chunk_id，嘗試作為索引處理
    if not retry_chunks and chunk_indices:
        for idx in chunk_indices:
            if 0 <= idx < len(all_chunks):
                retry_chunks.append(all_chunks[idx])
    
    if not retry_chunks:
        logger.error(f"❌ 找不到需要重試的 chunks，chunk_indices: {chunk_indices}")
        return False
    
    logger.info(f"📋 找到 {len(retry_chunks)} 個需要重試的 chunks")
    
    # 創建暫時檔案
    temp_input_path = os.path.join(OUTPUT_DIR, f'{file_id}_chunks_retry_input.json')
    temp_output_path = os.path.join(OUTPUT_DIR, f'{file_id}_chunks_retry_output.json')
    
    try:
        # 寫入暫時 input 檔案
        with open(temp_input_path, 'w', encoding='utf-8') as f:
            json.dump(retry_chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"📝 寫入暫時 input 檔案：{temp_input_path}")
        
        # 呼叫 summarize_pipeline.py 處理暫時 input
        # 只傳入 --input 和 --output 參數
        cmd = [
            'python3',
            os.path.join(os.path.dirname(__file__), 'summarize_pipeline.py'),
            '--input', temp_input_path,
            '--output', temp_output_path
        ]
        
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            retry_count += 1
            logger.info(f" [重試 {retry_count}/{max_retries}] 呼叫 summarize_pipeline.py...")
            
            try:
                result = subprocess.run(
                    cmd,
                    check=False,
                    timeout=1800,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    logger.info(f"✅ summarize_pipeline.py 執行成功")
                    success = True
                    break
                else:
                    logger.error(f"❌ summarize_pipeline.py 執行失敗 (return code: {result.returncode}): {result.stderr[:200]}")
                    if retry_count < max_retries:
                        time.sleep(5)
            except subprocess.TimeoutExpired:
                logger.error(f"❌ summarize_pipeline.py 執行超時")
                if retry_count < max_retries:
                    time.sleep(5)
            except Exception as e:
                logger.error(f"❌ 呼叫 summarize_pipeline.py 時發生異常：{e}")
                if retry_count < max_retries:
                    time.sleep(5)
        
        if not success:
            logger.error(f"❌ 檔案 {file_id} 的失敗片段已重試 {max_retries} 次仍失敗，標記為永久失敗。")
            # 觸發喚醒
            alert_file = os.path.join(OUTPUT_DIR, 'CRITICAL_ALERT.signal')
            with open(alert_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "error": f"Chunk-level retry failed for file {file_id} after {max_retries} attempts",
                    "failed_chunks": chunk_indices,
                    "status": "AWAITING_DEBUG"
                }, f, ensure_ascii=False, indent=2)
            return False
        
        # 讀取重試後的結果
        if not os.path.exists(temp_output_path):
            logger.error(f"❌ 暫時 output 檔案不存在：{temp_output_path}")
            return False
            
        with open(temp_output_path, 'r', encoding='utf-8') as f:
            retry_results = json.load(f)
        
        # 合併結果回原始 output 檔案
        # 如果 output 檔案存在，讀取並更新；否則創建新的
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
        else:
            existing_results = []
        
        # 創建 chunk_id 到 result 的映射
        existing_map = {}
        for chunk in existing_results:
            chunk_id = chunk.get('chunk_id', '')
            if chunk_id:
                existing_map[chunk_id] = chunk
        
        # 更新失敗 chunks 的結果
        updated_count = 0
        for retry_result in retry_results:
            chunk_id = retry_result.get('chunk_id', '')
            if chunk_id in existing_map:
                # 更新現有結果
                existing_map[chunk_id].update(retry_result)
                updated_count += 1
            else:
                # 新增新結果
                existing_results.append(retry_result)
                updated_count += 1
        
        # 寫回 output 檔案
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(existing_results, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 成功更新 {updated_count} 個 chunks 的結果到 {output_file}")
        return True
        
    finally:
        # 清理暫時檔案
        for temp_path in [temp_input_path, temp_output_path]:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    logger.debug(f"🧹 清理暫時檔案：{temp_path}")
                except Exception as e:
                    logger.warning(f"⚠️ 無法清理暫時檔案 {temp_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description='處理失敗片段')
    parser.add_argument('--file-id', type=int, required=True, help='檔案 ID')
    parser.add_argument('--batch', type=str, required=False, help='批次檔案路徑 (若未提供則自動搜尋)')
    parser.add_argument('--chunk-type', type=str, default='embedding', help='失敗類型 (embedding/summary)')
    args = parser.parse_args()
    
    # 若未提供 batch 檔案，自動搜尋 OUTPUT_DIR 中的 batch_status_*.json
    if args.batch is None:
        batch_pattern = os.path.join(OUTPUT_DIR, 'batch_status_*.json')
        batch_files = glob.glob(batch_pattern)
        if batch_files:
            batch_file = batch_files[0]  # 取第一個匹配的檔案
            logger.info(f'🔍 自動偵測到 batch 檔案：{batch_file}')
        else:
            logger.error(f'❌ 在 {OUTPUT_DIR} 中找不到 batch_status_*.json 檔案')
            return
    else:
        batch_file = args.batch
    
    # 讀取失敗片段列表
    failed_file = os.path.join(OUTPUT_DIR, f'failed_chunks_{args.file_id}.json')
    if not os.path.exists(failed_file):
        logger.error(f"❌ 失敗片段檔案不存在：{failed_file}")
        return
    
    with open(failed_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunk_indices = data.get('failed_indices', [])
    chunk_type = data.get('type', args.chunk_type)
    
    if not chunk_indices:
        logger.info("ℹ️ 無失敗片段，跳過。")
        return
    
    # 設定狀態檔案
    set_status_file(batch_file)
    update_state(args.file_id, 'summarizing')
    
    # 執行處理
    success = process_failed_chunks(args.file_id, batch_file, chunk_indices, chunk_type)
    
    if success:
        update_state(args.file_id, 'done')
        # 清理失敗檔案
        if os.path.exists(failed_file):
            os.remove(failed_file)
    else:
        # 標記為 failed_permanent 或等待人工介入
        update_state(args.file_id, 'failed_permanent')

if __name__ == '__main__':
    main()
