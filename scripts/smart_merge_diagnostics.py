#!/usr/bin/env python3
"""
smart_merge_diagnostics.py - 診斷 Smart Merge 為何產出 0 chunks

此腳本模擬完整的 Smart Merge 3.0 流程，並產生詳細的診斷報告。
"""

import json
import sys
import os
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

# 模擬 parse_srt 模組
@dataclass
class SubtitleEntry:
    start_time: str
    end_time: str
    text: str

def parse_srt_mock(content: str) -> List[SubtitleEntry]:
    """模擬解析 SRT 內容"""
    import re
    entries = []
    blocks = re.split(r'\r?\n\r?\n+', content.strip())
    for blk in blocks:
        lines = blk.splitlines()
        if len(lines) < 2:
            continue
        time_line = lines[1] if re.match(r'\d+$', lines[0].strip()) else lines[0]
        m = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', time_line)
        if not m:
            continue
        start, end = m.group(1), m.group(2)
        text = ' '.join(l.strip() for l in lines[2:] if l.strip())
        entries.append(SubtitleEntry(start, end, text))
    return entries

# Smart Merge 3.0 參數 (從 config.json)
SMART_MERGE_WINDOW_SIZE = 5
SMART_MERGE_MIN_SENTENCES = 6
SMART_MERGE_STRONG_PCT = 0.03  # 2-3% 為強斷點
SMART_MERGE_WEAK_PCT = 0.05   # 5% 為弱斷點
SMART_MERGE_NOISE_DROP_LEN = 2
SMART_MERGE_NOISE_WEAK_LEN = 3

def mock_generate_embedding(text: str) -> np.ndarray:
    """
    模擬產生嵌入向量。
    在真實環境中，這會呼叫 OpenAI-compatible Embedding API。
    """
    # 使用簡單的 hash 模擬向量，確保相同文字有相同向量
    np.random.seed(hash(text) % (2**32))
    return np.random.randn(3072)

def calculate_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """計算 Cosine 相似度"""
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def smart_merge_3_0_diagnostics(
    entries: List[SubtitleEntry],
    file_id: int
) -> Dict:
    """
    執行 Smart Merge 3.0 並返回詳細診斷數據。
    """
    total_entries = len(entries)
    diagnostics = {
        "file_id": file_id,
        "total_entries": total_entries,
        "window_size": SMART_MERGE_WINDOW_SIZE,
        "min_sentences": SMART_MERGE_MIN_SENTENCES,
        "strong_pct_threshold": SMART_MERGE_STRONG_PCT,
        "weak_pct_threshold": SMART_MERGE_WEAK_PCT,
        "windows_generated": 0,
        "embeddings_success": 0,
        "embeddings_failed": 0,
        "similarities_computed": 0,
        "strong_breakpoints": [],
        "weak_breakpoints": [],
        "pending_breakpoints": [],
        "active_breaks": [],
        "filtered_chunks": [],
        "noise_filtered": [],
        "final_chunk_count": 0,
        "chunk_sizes": [],
        "detailed_similarity_list": [],
        "analysis": {}
    }
    
    if total_entries < SMART_MERGE_WINDOW_SIZE:
        diagnostics["analysis"]["reason"] = f"總條目數 ({total_entries}) 小於視窗大小 ({SMART_MERGE_WINDOW_SIZE})，無法執行 Smart Merge"
        return diagnostics
    
    # 1. 產生重疊窗口
    windows = []
    for i in range(total_entries - SMART_MERGE_WINDOW_SIZE + 1):
        seg = entries[i : i + SMART_MERGE_WINDOW_SIZE]
        window_text = ' '.join(e.text for e in seg)
        windows.append(window_text)
    
    diagnostics["windows_generated"] = len(windows)
    
    # 2. 向量化 (模擬)
    vectors = []
    for idx, txt in enumerate(windows):
        try:
            vec = mock_generate_embedding(txt)
            vectors.append(vec)
            diagnostics["embeddings_success"] += 1
        except Exception as e:
            diagnostics["embeddings_failed"] += 1
            vectors.append(None)
    
    # 3. 計算相似度 (無重疊、相鄰窗口)
    sims = []
    sim_to_break_idx = []
    for i in range(len(vectors) - SMART_MERGE_WINDOW_SIZE):
        v1 = vectors[i]
        v2 = vectors[i + SMART_MERGE_WINDOW_SIZE]
        if v1 is not None and v2 is not None:
            sim = calculate_similarity(v1, v2)
            sims.append(sim)
            sim_to_break_idx.append(i + SMART_MERGE_WINDOW_SIZE)
            diagnostics["similarities_computed"] += 1
            diagnostics["detailed_similarity_list"].append({
                "similarity_index": i,
                "window1_start": i,
                "window2_start": i + SMART_MERGE_WINDOW_SIZE,
                "similarity": float(sim),
                "breakpoint_position": i + SMART_MERGE_WINDOW_SIZE
            })
        else:
            sims.append(1.0)
            sim_to_break_idx.append(i + SMART_MERGE_WINDOW_SIZE)
    
    if not sims:
        diagnostics["analysis"]["reason"] = "相似度計算結果為空，無法產生斷點"
        return diagnostics
    
    # 4. 斷點強度排序
    n_sims = len(sims)
    strengths = [1.0 - s for s in sims]  # 相似度越低，強度越高
    
    sorted_idx = sorted(range(n_sims), key=lambda x: strengths[x], reverse=True)
    
    high_cut = max(1, int(n_sims * SMART_MERGE_WEAK_PCT))  # 前 5% 弱斷點
    low_cut = max(1, int(n_sims * SMART_MERGE_STRONG_PCT))  # 前 2-3% 強斷點
    
    # 記錄強弱斷點
    for i in range(low_cut):
        bp_pos = sim_to_break_idx[sorted_idx[i]]
        diagnostics["strong_breakpoints"].append({
            "position": bp_pos,
            "strength": strengths[sorted_idx[i]],
            "similarity": sims[sorted_idx[i]]
        })
    
    for i in range(low_cut, high_cut):
        bp_pos = sim_to_break_idx[sorted_idx[i]]
        diagnostics["pending_breakpoints"].append({
            "position": bp_pos,
            "strength": strengths[sorted_idx[i]],
            "similarity": sims[sorted_idx[i]]
        })
    
    # 5. 斷點驗證與合併
    active_breaks = [0, total_entries] + [sim_to_break_idx[i] for i in range(low_cut)]
    active_breaks.sort()
    diagnostics["active_breaks_initial"] = active_breaks.copy()
    
    # 依強度從弱到強檢查待定斷點
    for sim_idx in reversed(range(low_cut, high_cut)):
        bp_line = sim_to_break_idx[sim_idx]
        
        # 尋找左右邊界
        left_bound = 0
        right_bound = total_entries
        for b in active_breaks:
            if b <= bp_line:
                left_bound = b
            if b > bp_line and right_bound == total_entries:
                right_bound = b
                break
        
        left_sentences = bp_line - left_bound
        right_sentences = right_bound - bp_line
        
        diagnostics["pending_verification"] = {
            "position": bp_line,
            "left_boundary": left_bound,
            "right_boundary": right_bound,
            "left_sentences": left_sentences,
            "right_sentences": right_sentences,
            "min_required": SMART_MERGE_MIN_SENTENCES,
            "passed": left_sentences >= SMART_MERGE_MIN_SENTENCES and right_sentences >= SMART_MERGE_MIN_SENTENCES
        }
        
        if left_sentences >= SMART_MERGE_MIN_SENTENCES and right_sentences >= SMART_MERGE_MIN_SENTENCES:
            active_breaks.append(bp_line)
            active_breaks.sort()
        else:
            diagnostics["filtered_pending_breakpoints"] = {
                "position": bp_line,
                "reason": f"左側 ({left_sentences}) 或右側 ({right_sentences}) 小於最小句子數 ({SMART_MERGE_MIN_SENTENCES})"
            }
    
    diagnostics["active_breaks_final"] = active_breaks
    
    # 6. 雜訊過濾與產生最終段落
    final_chunks = []
    for i in range(len(active_breaks) - 1):
        start_idx = active_breaks[i]
        end_idx = active_breaks[i+1] - 1
        chunk_len = end_idx - start_idx + 1
        
        if chunk_len <= SMART_MERGE_NOISE_DROP_LEN:
            diagnostics["noise_filtered"].append({
                "start": start_idx,
                "end": end_idx,
                "length": chunk_len,
                "reason": f"長度 {chunk_len} <= {SMART_MERGE_NOISE_DROP_LEN}，直接拋棄"
            })
            continue
        
        if chunk_len == SMART_MERGE_NOISE_WEAK_LEN:
            # 檢查兩端強度
            left_strength = 0.0
            right_strength = 0.0
            try:
                l_idx = sim_to_break_idx.index(start_idx)
                left_strength = strengths[l_idx]
            except ValueError:
                pass
            try:
                r_idx = sim_to_break_idx.index(end_idx + 1)
                right_strength = strengths[r_idx]
            except ValueError:
                pass
            
            # 如果兩端皆為極弱連結（>= 強斷點閾值），拋棄
            low_pct_strength_threshold = strengths[sorted_idx[min(low_cut, n_sims-1)]]
            if left_strength >= low_pct_strength_threshold and right_strength >= low_pct_strength_threshold:
                diagnostics["noise_filtered"].append({
                    "start": start_idx,
                    "end": end_idx,
                    "length": chunk_len,
                    "left_strength": left_strength,
                    "right_strength": right_strength,
                    "threshold": low_pct_strength_threshold,
                    "reason": "長度為 3 且兩端皆為極弱連結"
                })
                continue
        
        seg = entries[start_idx : end_idx + 1]
        chunk = {
            "start_idx": start_idx,
            "end_idx": end_idx,
            "length": chunk_len,
            "text_preview": ' '.join(e.text for e in seg[:3]) + "..." if len(seg) > 3 else ' '.join(e.text for e in seg)
        }
        final_chunks.append(chunk)
        diagnostics["chunk_sizes"].append(chunk_len)
    
    diagnostics["filtered_chunks"] = final_chunks
    diagnostics["final_chunk_count"] = len(final_chunks)
    
    # 7. 分析產出 0 chunks 的可能原因
    if len(final_chunks) == 0:
        reasons = []
        
        if diagnostics["active_breaks_final"] == [0, total_entries]:
            reasons.append("沒有產生任何斷點（除了頭尾），可能原因：")
            reasons.append(f"  - 相似度分佈均勻，沒有明顯的斷點（強斷點數量：{len(diagnostics['strong_breakpoints'])}")
            reasons.append(f"  - 總相似度值：min={min(sims):.4f}, max={max(sims):.4f}, avg={np.mean(sims):.4f}")
        
        if diagnostics["noise_filtered"]:
            reasons.append(f"所有候選段落都被雜訊過濾：")
            for nf in diagnostics["noise_filtered"]:
                reasons.append(f"  - [{nf['start']}~{nf['end']}] {nf['reason']}")
        
        if "pending_verification" in diagnostics and not diagnostics.get("filtered_pending_breakpoints"):
            reasons.append("待定斷點未通過驗證：")
            reasons.append(f"  - 候斷點位置：{diagnostics.get('pending_verification', {}).get('position')}")
            reasons.append(f"  - 左側句子數：{diagnostics.get('pending_verification', {}).get('left_sentences')} < {SMART_MERGE_MIN_SENTENCES}")
            reasons.append(f"  - 右側句子數：{diagnostics.get('pending_verification', {}).get('right_sentences')} < {SMART_MERGE_MIN_SENTENCES}")
        
        diagnostics["analysis"]["reasons_zero_chunks"] = reasons
    
    # 統計資訊
    if diagnostics["chunk_sizes"]:
        diagnostics["analysis"]["chunk_size_stats"] = {
            "min": min(diagnostics["chunk_sizes"]),
            "max": max(diagnostics["chunk_sizes"]),
            "avg": np.mean(diagnostics["chunk_sizes"]),
            "median": np.median(diagnostics["chunk_sizes"])
        }
    
    return diagnostics

def main():
    """主函式：執行診斷並輸出報告"""
    
    # 範例 SRT 內容（模擬一個小型 SRT 檔案）
    sample_srt_content = """
1
00:00:01,000 --> 00:00:04,000
歡迎來到我們的節目

2
00:00:05,000 --> 00:00:07,000
今天我們要討論代溝的問題

3
00:00:08,500 --> 00:00:12,000
這是一個很重要的話題

4
00:00:13,000 --> 00:00:16,000
讓我們開始吧

5
00:00:17,000 --> 00:00:20,000
首先請教我們的來賓

6
00:00:21,000 --> 00:00:24,000
您認為代溝的主要責任在哪邊

7
00:00:25,000 --> 00:00:28,000
我覺得兩邊都有責任

8
00:00:29,000 --> 00:00:32,000
長輩需要理解年輕人

9
00:00:33,000 --> 00:00:36,000
年輕人也需要尊重長輩

10
00:00:37,000 --> 00:00:40,000
這就是我們今天的討論
"""
    
    print("=" * 80)
    print("Smart Merge 3.0 診斷報告")
    print("=" * 80)
    print()
    
    # 解析 SRT
    entries = parse_srt_mock(sample_srt_content)
    print(f"📄 SRT 解析結果：{len(entries)} 筆條目")
    print()
    
    # 執行診斷
    diagnostics = smart_merge_3_0_diagnostics(entries, file_id=1)
    
    # 輸出報告
    print("📊 基本參數:")
    print(f"  - 視窗大小: {diagnostics['window_size']}")
    print(f"  - 最小句子數: {diagnostics['min_sentences']}")
    print(f"  - 強斷點百分比: {diagnostics['strong_pct_threshold']*100:.1f}%")
    print(f"  - 弱斷點百分比: {diagnostics['weak_pct_threshold']*100:.1f}%")
    print()
    
    print("🔢 處理統計:")
    print(f"  - 產生窗口數: {diagnostics['windows_generated']}")
    print(f"  - 嵌入成功: {diagnostics['embeddings_success']}")
    print(f"  - 相似度計算: {diagnostics['similarities_computed']}")
    print()
    
    print("📍 斷點分析:")
    print(f"  - 強斷點數量: {len(diagnostics['strong_breakpoints'])}")
    print(f"  - 待定斷點數量: {len(diagnostics['pending_breakpoints'])}")
    print(f"  - 初始斷點: {diagnostics.get('active_breaks_initial', [])}")
    print(f"  - 最終斷點: {diagnostics['active_breaks_final']}")
    print()
    
    if diagnostics['detailed_similarity_list']:
        print("📈 相似度分佈:")
        sims = [d['similarity'] for d in diagnostics['detailed_similarity_list']]
        print(f"  - 最小相似度: {min(sims):.4f}")
        print(f"  - 最大相似度: {max(sims):.4f}")
        print(f"  - 平均相似度: {np.mean(sims):.4f}")
        print(f"  - 標準差: {np.std(sims):.4f}")
        print()
    
    print("🧹 雜訊過濾:")
    if diagnostics['noise_filtered']:
        for nf in diagnostics['noise_filtered']:
            print(f"  - 過濾：[{nf['start']}~{nf['end']}] - {nf['reason']}")
    else:
        print("  無雜訊過濾")
    print()
    
    print("📦 候選 Chunk:")
    if diagnostics['filtered_chunks']:
        for i, chunk in enumerate(diagnostics['filtered_chunks']):
            print(f"  Chunk {i+1}: [{chunk['start_idx']}~{chunk['end_idx']}] 長度={chunk['length']}")
            print(f"    預覽：{chunk['text_preview'][:50]}...")
    else:
        print("  ❌ 無有效 Chunk（產出 0 chunks）")
    print()
    
    print("🔍 最終結果:")
    print(f"  - 最終 Chunk 數量: {diagnostics['final_chunk_count']}")
    print()
    
    if diagnostics['final_chunk_count'] == 0:
        print("❌ 產出 0 chunks 的原因分析:")
        if 'reasons_zero_chunks' in diagnostics['analysis']:
            for reason in diagnostics['analysis']['reasons_zero_chunks']:
                print(f"  {reason}")
        else:
            print("  未明確分析原因")
    elif diagnostics['analysis'].get('chunk_size_stats'):
        stats = diagnostics['analysis']['chunk_size_stats']
        print("✅ Chunk 大小統計:")
        print(f"  - 最小: {stats['min']} 行")
        print(f"  - 最大: {stats['max']} 行")
        print(f"  - 平均: {stats['avg']:.2f} 行")
        print(f"  - 中位數: {stats['median']:.2f} 行")
    
    print()
    print("=" * 80)
    print("診斷完成")
    print("=" * 80)
    
    # 輸出完整診斷數據為 JSON
    output_file = "./output/smart_merge_diagnostics.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(diagnostics, f, ensure_ascii=False, indent=2)
    print(f"\n完整診斷數據已寫入：{output_file}")

if __name__ == '__main__':
    main()
