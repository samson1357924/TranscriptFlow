#!/usr/bin/env python3
"""db_writer.py — 直接讀取 summarize 結果寫入 LanceDB（避免重跑 pipeline）"""
import os, sys, json, argparse

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))
from logger_config import get_logger
from config_loader import get_env_or_config
from state_manager import update_state, set_status_file, load_status

logger = get_logger('db_writer')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=int, required=True)
    parser.add_argument('--batch', type=str, default='')
    args = parser.parse_args()
    
    if args.batch:
        set_status_file(args.batch)
    
    output_dir = get_env_or_config('SRT_OUTPUT_DIR', 'paths.output_dir', './output')
    
    # Read the chunks_output.json (records with summary)
    output_file = os.path.join(output_dir, f'{args.id}_chunks_output.json')
    if not os.path.exists(output_file):
        logger.error(f"Chunks output not found: {output_file}")
        sys.exit(1)
    
    with open(output_file, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    # Build records
    records = []
    expected_dim = get_env_or_config('EMBEDDING_EXPECTED_DIM', 'embedding.expected_dim', 3072)
    for ch in chunks:
        if ch.get('status') != 'done':
            continue
        summary = ch.get('summary', '')
        if not summary or not summary.strip():
            continue
        records.append({
            "chunk_id": ch.get("chunk_id", f"{args.id}_{len(records)}"),
            "file_id": args.id,
            "file_name": f"file_{args.id}",
            "start_time": ch.get('start_time', ''),
            "end_time": ch.get('end_time', ''),
            "summary": summary,
            "text_content": ch.get('text_content', ''),
            "tags": ch.get('tags', []),
            "participants": [],
            "vector": [0.0] * expected_dim,  # placeholder; regenerate embeddings before production search
            "boundary_type": ch.get('boundary_type', 'summary'),
        })
    
    if not records:
        logger.warning("No valid records to write to DB")
        sys.exit(0)
    
    # Write to LanceDB via finalize's write_to_db
    from finalize import write_to_db
    success, msg = write_to_db(records)
    
    if success:
        update_state(args.id, 'done')
        logger.info(f"✅ ID {args.id}: {len(records)} records written to DB")
        # Cleanup
        for suffix in ['_chunks_input.json', '_chunks_output.json']:
            p = os.path.join(output_dir, f"{args.id}{suffix}")
            if os.path.exists(p):
                os.remove(p)
    else:
        update_state(args.id, 'failed', msg)
        logger.error(f"❌ DB write failed: {msg}")
        sys.exit(1)

if __name__ == '__main__':
    main()
