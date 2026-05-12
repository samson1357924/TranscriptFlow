#!/bin/bash
# TranscriptFlow 統一啟動腳本
# 使用方式: ./run_wrapper.sh --id <檔案 ID> [--batch <批次檔案路徑>]
# v1.1: API 配置統一從 config.json 讀取，環境變數可覆蓋

set -e

# --- API 配置（優先環境變數，fallback 到 config_loader） ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 從 config_loader 讀取 API 配置
OPENAI_BASE_URL="${OPENAI_BASE_URL:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_api_config; print(get_api_config().get('base_url', ''))" 2>/dev/null || echo "")}"
OPENAI_API_KEY="${OPENAI_API_KEY:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_api_config; print(get_api_config().get('api_key', ''))" 2>/dev/null || echo "")}"
EMBEDDING_API_BASE="${EMBEDDING_API_BASE:-$OPENAI_BASE_URL}"

# 如果 config_loader 也讀不到，使用預設值
OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com}"
EMBEDDING_API_BASE="${EMBEDDING_API_BASE:-$OPENAI_BASE_URL}"

export OPENAI_BASE_URL
export EMBEDDING_API_BASE
export OPENAI_API_KEY

# --- 路徑配置 ---
export SRT_OUTPUT_DIR="${SRT_OUTPUT_DIR:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_nested_config; print(get_nested_config('paths.output_dir'))" 2>/dev/null || echo "./output")}"
export SRT_DB_PATH="${SRT_DB_PATH:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_nested_config; print(get_nested_config('paths.db_path'))" 2>/dev/null || echo "$SRT_OUTPUT_DIR/lance_test_db")}"
export SRT_TABLE_NAME="${SRT_TABLE_NAME:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_nested_config; print(get_nested_config('tables.final_db'))" 2>/dev/null || echo "psychology_kb")}"
export SRT_WORK_DIR="${SRT_WORK_DIR:-$(cd "$SCRIPT_DIR/../../../" && pwd)/structured_yt_data}"
export SRT_MASTER_FILE="${SRT_MASTER_FILE:-$(PYTHONPATH="$SCRIPT_DIR" python3 -c "from config_loader import get_nested_config; print(get_nested_config('paths.master_file'))" 2>/dev/null || echo "./examples/master_file_manifest.example.json")}"
export SRT_PROJECT_ROOT="${SRT_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../../" && pwd)}"

export SRT_OUTPUT_DIR SRT_DB_PATH SRT_TABLE_NAME SRT_WORK_DIR SRT_MASTER_FILE SRT_PROJECT_ROOT

# 確認 API key 已設定
if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ 錯誤: OPENAI_API_KEY 未設定（請在 config.json api.api_key 或環境變數中設定）"
  exit 1
fi

# 解析參數
ID=""
BATCH=""
PHASE=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --id)
      if ! [[ "$2" =~ ^[0-9]+$ ]]; then
        echo "❌ 錯誤：--id 必須為正整數"
        exit 1
      fi
      ID="$2"
      shift 2
      ;;
    --batch)
      BATCH="$2"
      shift 2
      ;;
    --phase)
      PHASE="$2"
      shift 2
      ;;
    *)
      echo "❌ 未知參數: $1"
      echo "使用方式: $0 --id <檔案 ID> [--batch <批次檔案路徑>]"
      exit 1
      ;;
  esac
done

if [ -z "$ID" ]; then
  echo "❌ 錯誤: 必須指定 --id 參數"
  echo "使用方式: $0 --id <檔案 ID> [--batch <批次檔案路徑>]"
  exit 1
fi

echo "=== 開始處理檔案 ID: $ID ==="
echo "API Base URL: $OPENAI_BASE_URL"
echo "Embedding: $EMBEDDING_API_BASE"
echo "批次檔案: ${BATCH:-自動偵測}"
echo "輸出目錄: $SRT_OUTPUT_DIR"
echo "=================================="

# 執行處理
cd "$SCRIPT_DIR"
if [ -z "$BATCH" ]; then
  BATCH="${SRT_OUTPUT_DIR}/batch_status_0_2.json"
fi

python3 summarize.py --id "$ID" --batch "$BATCH" --phase "$PHASE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ 檔案 $ID 處理成功"
else
  echo "❌ 檔案 $ID 處理失敗 (退出碼: $EXIT_CODE)"
  exit $EXIT_CODE
fi
