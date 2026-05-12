import os
import sys
import json
import argparse
import shutil
import tempfile
import fcntl
from datetime import datetime
from typing import List, Dict, Tuple
import pyarrow as pa
import pandas as pd
import time

# Local imports
from state_manager import update_state, set_status_file
import lancedb
from logger_config import get_logger
from config_loader import get_env_or_config, validate_config, check_required_env_vars, sanitize_api_url, ensure_secure_permissions, validate_path

logger = get_logger('finalize')

# 驗證必要環境變數
required_ok, missing = check_required_env_vars()
if not required_ok:
    raise RuntimeError(f'必要環境變數未設定:{missing}')

# 驗證配置參數
validation_errors = validate_config()
if validation_errors:
    raise ValueError('配置驗證失敗:\n' + '\n'.join(f' - {e}' for e in validation_errors))

# Environment / config
PROJECT_ROOT = os.getenv('SRT_PROJECT_ROOT', os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
OUTPUT_DIR = os.getenv('SRT_OUTPUT_DIR', './output')
DB_FINAL = get_env_or_config('SRT_DB_PATH', 'paths.db_path', os.path.join(OUTPUT_DIR, 'lance_test_db'))  # 最終寫入位置
TABLE_NAME = get_env_or_config('SRT_TABLE_NAME', 'tables.final_db', 'psychology_kb')
BACKUP_DIR = get_env_or_config('SRT_BACKUP_DIR', 'paths.backup_dir', './output/lance_backup')
EXPECTED_DIM = get_env_or_config('EMBEDDING_EXPECTED_DIM', 'embedding.expected_dim', 3072)


def deduplicate_records(records: List[Dict]) -> List[Dict]:
    """按語意去重:file_name + start_time 是 semantic chunk 的唯一主鍵。
    若同一 SRT 文件中同一時間點重複 chunk,則只保留第一次產生的那條記錄。
    """
    seen = set()
    deduped = []
    for rec in records:
        key = (rec['file_name'], rec['start_time'])
        if key not in seen:
            seen.add(key)
            deduped.append(rec)

    if len(deduped) != len(records):
        logger.warning(f"Deduplicated: {len(records)} → {len(deduped)} records (removed {len(records)-len(deduped)} duplicates)")

    return deduped


def write_to_db(records: List[Dict]) -> Tuple[bool, str]:
    records = deduplicate_records(records)
    if not records:
        return True, "No records to write"

    os.makedirs(DB_FINAL, exist_ok=True)
    try:
        db = lancedb.connect(DB_FINAL)
        raw = db.list_tables()
        table_names = raw.tables

        if TABLE_NAME not in table_names:
            schema = pa.schema([
                ("file_name", pa.string()),
                ("start_time", pa.string()),
                ("end_time", pa.string()),
                ("summary", pa.string()),
                ("text_content", pa.string()),
                ("tags", pa.list_(pa.string())),
                ("participants", pa.list_(pa.string())),
                ("vector", pa.list_(pa.float32(), EXPECTED_DIM)),
                ("boundary_type", pa.string())
            ])
            db.create_table(TABLE_NAME, schema=schema)

        dims = set(len(r['vector']) for r in records)
        if dims != {EXPECTED_DIM}:
            return False, f"Vector dimension mismatch: found {dims}, expected {{{EXPECTED_DIM}}}."

        table = db.open_table(TABLE_NAME)
        table.add(records)
        logger.info(f"LanceDB append: {len(records)} records")
        return True, f"Written {len(records)} records to {TABLE_NAME}"
    except Exception as e:
        return False, str(e)

if __name__ == '__main__':
    logger.error("finalize.py is no longer a standalone entry point. Use summarize.py --phase db_inserting instead.")
    sys.exit(1)
