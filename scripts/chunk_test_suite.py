"""
chunk_test_suite.py — 方案 B：多組參數比較測試套件

用法:
    python3 scripts/chunk_test_suite.py --suite test_suite.json

suite JSON 格式（全部寫在同一個檔案）：

    {
        "name": "視窗大小比較",
        "files": [0, 11],
        "configs": [
            {
                "label": "baseline",
                "chunking": {
                    "smart_merge_window_size": 5,
                    "smart_merge_strong_pct": 0.02,
                    "smart_merge_weak_pct": 0.05,
                    "smart_merge_min_sentences": 8,
                    "smart_merge_noise_drop_len": 2,
                    "smart_merge_noise_weak_len": 3
                },
                "models": ["oci-openai.gpt-oss-120b"]
            },
            {
                "label": "window_3",
                "chunking": { "smart_merge_window_size": 3 },
                "models": ["NV-deepseek-v4-flash"]
            }
        ]
    }

也可以混用外部檔案 + 內嵌覆蓋：
    {"label": "tight", "file": "scripts/config_2.json", "chunking": {"strong_pct": 0.01}}

比對報告會輸出到 output_dir/comparison_{timestamp}.txt
"""

import argparse
import json
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import get_env_or_config


def load_suite(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_chunk_params(config: dict) -> dict:
    c = config.get('chunking', {})
    return {
        "window_size": c.get('smart_merge_window_size', 5),
        "strong_pct": c.get('smart_merge_strong_pct', 0.02),
        "weak_pct": c.get('smart_merge_weak_pct', 0.05),
        "min_sentences": c.get('smart_merge_min_sentences', 8),
        "noise_drop_len": c.get('smart_merge_noise_drop_len', 2),
        "noise_weak_len": c.get('smart_merge_noise_weak_len', 3),
        "min_chunks": c.get('min_chunks', 2),
        "max_chunks": c.get('max_chunks', 200),
    }


def extract_models(config: dict) -> list:
    return config.get('summarization', {}).get('models', ["gpt-4.1-mini"])


def run_individual(script_dir: str, file_id: int, label: str,
                   chunk_params: dict, models: list,
                   output_dir: str) -> str:
    chunk_json = json.dumps(chunk_params, ensure_ascii=False)
    models_json = json.dumps(models, ensure_ascii=False)
    runner = os.path.join(script_dir, 'chunk_test_runner.py')

    cmd = [
        sys.executable, runner,
        '--file-id', str(file_id),
        '--chunk-params', chunk_json,
        '--models', models_json,
        '--output', output_dir,
    ]

    print(f"\n{'=' * 60}")
    print(f"  [{label}] file_id={file_id}")
    print(f"  參數: window={chunk_params['window_size']}, "
          f"strong={chunk_params['strong_pct']}, weak={chunk_params['weak_pct']}")
    print(f"  模型: {len(models)} 個")
    print(f"{'=' * 60}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"  ❌ 失敗 (exit {result.returncode})")
        print(f"  stderr: {result.stderr[:300]}")
        return None

    for line in result.stdout.strip().split('\n'):
        if '報告已寫入' in line or '結構化資料' in line or '全部完成' in line:
            print(f"  {line}")

    # 掃描 output_dir 中最新的 {file_id}_test_report_*.json
    import glob
    pat = os.path.join(output_dir, f"{file_id}_test_report_*.json")
    matches = sorted(glob.glob(pat), key=os.path.getmtime, reverse=True)
    return matches[0] if matches else None


def generate_comparison(suite: dict, results: dict, output_path: str):
    lines = []
    _sep = lambda: lines.append('')
    _hline = lambda: lines.append('=' * 80)

    _hline()
    lines.append(f"{'參數比較測試報告':^80}")
    _hline()
    lines.append(f"  測試名稱:    {suite.get('name', 'N/A')}")
    lines.append(f"  執行時間:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  測試檔案:    {', '.join(str(f) for f in suite['files'])}")
    _sep()

    labels = [c['label'] for c in suite['configs']]
    configs = {c['label']: c for c in suite['configs']}

    for fid in suite['files']:
        _hline()
        lines.append(f"{'檔案 ID: ' + str(fid):^80}")
        _hline()

        filename = None
        for label in labels:
            r = results.get(fid, {}).get(label)
            if r and r.get('filename'):
                filename = r['filename']
                break
        if filename:
            lines.append(f"  檔案: {filename}")
            _sep()

        # ── 參數對照表 ──
        lines.append("  --- 參數對照 ---")
        param_keys = ['window_size', 'strong_pct', 'weak_pct',
                      'min_sentences', 'noise_drop_len', 'noise_weak_len']
        header = "  {:<20}".format("參數")
        for label in labels:
            header += f"  {label:<20}"
        lines.append(header)
        lines.append("  " + "-" * len(header))
        for key in param_keys:
            row = f"  {key:<20}"
            for label in labels:
                r = results.get(fid, {}).get(label)
                val = r.get('params', {}).get(key, '-') if r else '-'
                row += f"  {str(val):<20}"
            lines.append(row)
        _sep()

        # ── 模型對照 ──
        lines.append("  --- 模型數量 ---")
        for label in labels:
            r = results.get(fid, {}).get(label)
            n = len(r.get('models', [])) if r else 0
            lines.append(f"    {label:<20}{n} 個")
        _sep()

        # ── 參與者 ──
        lines.append("  --- 參與者 ---")
        for label in labels:
            r = results.get(fid, {}).get(label)
            p = r.get('participants', []) if r else []
            lines.append(f"    {label:<20}{', '.join(p) if p else '(無)'}")
        _sep()

        # ── 量化統計 ──
        lines.append("  --- 量化統計 ---")
        stat_keys = [
            ("total_kept", "納入段數"),
            ("total_discarded", "排除段數"),
        ]
        stats_header = "  {:<20}".format("指標")
        for label in labels:
            stats_header += f"  {label:<20}"
        lines.append(stats_header)
        lines.append("  " + "-" * len(stats_header))
        for skey, sname in stat_keys:
            row = f"  {sname:<20}"
            for label in labels:
                r = results.get(fid, {}).get(label)
                val = r.get(skey, '-') if r else '-'
                row += f"  {str(val):<20}"
            lines.append(row)
        _sep()

        # ── 分段細節比對 ──
        lines.append("  --- 分段邊界比對 ---")
        all_entry_counts = set()
        for label in labels:
            r = results.get(fid, {}).get(label)
            if r and r.get('segments'):
                all_entry_counts.update(
                    f"{s['chunk_id']} ({s['entry_count']}行)"
                    for s in r['segments']
                )
        all_entry_counts = sorted(all_entry_counts, key=lambda x: int(x.split('_')[-1].split()[0]))
        _sep()

        # 列出每個 label 各 segment 的 entry_count
        for label in labels:
            r = results.get(fid, {}).get(label)
            if not r or not r.get('segments'):
                lines.append(f"    {label}: (無資料)")
                continue
            segs = r['segments']
            kept = sum(1 for s in segs if not s.get('dropped'))
            dropped = sum(1 for s in segs if s.get('dropped'))
            lines.append(f"    {label}: {len(segs)} 段 ({kept} 納入, {dropped} 排除)")
            for s in segs:
                def _bp_short(bp):
                    if not bp or bp.get('strength_pct') is None:
                        return bp.get('label', '-') if bp else '-'
                    return f"{bp['strength_pct']}%(cos{bp['cosine']})"
                lb = _bp_short(s.get('left_boundary'))
                rb = _bp_short(s.get('right_boundary'))
                tag = "❌" if s.get('dropped') else "✅"
                reason = f" [{s.get('drop_reason', '')}]" if s.get('dropped') else ""
                lines.append(f"      {tag} {s['chunk_id']}  "
                             f"{s['start_time']}→{s['end_time']}  "
                             f"({s['entry_count']}行)  "
                             f"起{lb} 終{rb}{reason}")
        _sep()

        # ── 差異分析 ──
        lines.append("  --- 差異分析 ---")
        first_label = labels[0]
        base_segs = results.get(fid, {}).get(first_label, {}).get('segments', [])
        base_kept_ids = {s['chunk_id'] for s in base_segs if not s.get('dropped')}
        base_dropped_ids = {s['chunk_id'] for s in base_segs if s.get('dropped')}

        for label in labels[1:]:
            r = results.get(fid, {}).get(label)
            if not r or not r.get('segments'):
                continue
            segs = r['segments']
            kept_ids = {s['chunk_id'] for s in segs if not s.get('dropped')}
            dropped_ids = {s['chunk_id'] for s in segs if s.get('dropped')}

            new_kept = kept_ids - base_kept_ids
            new_dropped = dropped_ids - base_dropped_ids
            changed_to_dropped = base_kept_ids & dropped_ids
            changed_to_kept = base_dropped_ids & kept_ids

            lines.append(f"    {label} vs {first_label}:")
            if new_kept:
                lines.append(f"      + 新納入: {', '.join(sorted(new_kept))}")
            if new_dropped:
                lines.append(f"      - 新排除: {', '.join(sorted(new_dropped))}")
            if changed_to_dropped:
                lines.append(f"      ↓ baseline納入→排除: {', '.join(sorted(changed_to_dropped))}")
            if changed_to_kept:
                lines.append(f"      ↑ baseline排除→納入: {', '.join(sorted(changed_to_kept))}")
            if not (new_kept or new_dropped or changed_to_dropped or changed_to_kept):
                lines.append(f"      (與 {first_label} 無差異)")
        _sep()
        _sep()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\n✅ 比對報告: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='TranscriptFlow 參數比較測試套件')
    parser.add_argument('--suite', required=True, help='test suite JSON 路徑')
    parser.add_argument('--output-dir', default=None,
                        help='輸出目錄（覆蓋 suite JSON 的 output_dir）')
    parser.add_argument('--skip-llm', action='store_true',
                        help='跳過 LLM 摘要階段（只比對 chunk 分段結果）')
    args = parser.parse_args()

    suite = load_suite(args.suite)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or suite.get('output_dir') or ''
    suite_output = output_dir if args.output_dir else os.path.join(
        get_env_or_config('SRT_OUTPUT_DIR', 'paths.output_dir', './output'), 'test_suite'
    )
    os.makedirs(suite_output, exist_ok=True)

    labels = []
    _fallback_models = None
    total_runs = len(suite['files']) * len(suite['configs'])
    run_count = 0
    json_paths = {}  # (file_id, label) -> json_path

    for cfg_entry in suite['configs']:
        label = cfg_entry['label']
        labels.append(label)

        # 載入基底設定（若有外部檔案）
        config = {}
        if cfg_entry.get('file'):
            file_path = cfg_entry['file']
            if not os.path.exists(file_path):
                print(f"❌ 設定檔不存在: {file_path}")
                sys.exit(1)
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

        # 內嵌 chunking 參數（覆蓋外部檔案對應欄位）
        inline_chunking = cfg_entry.get('chunking', {})
        if inline_chunking:
            config.setdefault('chunking', {}).update(inline_chunking)

        # 內嵌 models（完全取代外部檔案）
        if 'models' in cfg_entry:
            config.setdefault('summarization', {})['models'] = cfg_entry['models']

        chunk_params = extract_chunk_params(config)
        models = extract_models(config)

        # 若仍未指定 models，繼承第一個 config 的模型清單
        if models == ["gpt-4.1-mini"] and not cfg_entry.get('file') and 'models' not in cfg_entry:
            if _fallback_models is not None:
                models = _fallback_models
                config.setdefault('summarization', {})['models'] = models
        if _fallback_models is None:
            _fallback_models = models[:]

        for fid in suite['files']:
            run_count += 1
            print(f"\n[{run_count}/{total_runs}] 處理中...")
            result_path = run_individual(script_dir, fid, label, chunk_params, models, suite_output)
            json_paths[(fid, label)] = result_path

    # 收集結果並產生比對報告
    print(f"\n{'=' * 60}")
    print("  所有測試完成，產生比對報告...")
    print(f"{'=' * 60}")

    results = {}
    for fid in suite['files']:
        results[fid] = {}
        for label in labels:
            jp = json_paths.get((fid, label))
            if jp and os.path.exists(jp):
                with open(jp, 'r', encoding='utf-8') as f:
                    results[fid][label] = json.load(f)
            else:
                results[fid][label] = None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    comparison_path = os.path.join(suite_output, f"comparison_{timestamp}.txt")
    generate_comparison(suite, results, comparison_path)


if __name__ == '__main__':
    main()
