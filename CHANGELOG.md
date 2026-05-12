# 📜 CHANGELOG - srt-semantic-chunk

## v2.0 (2026-05-12): Comprehensive Audit, Model Diagnostics & Parallelism Fixes

### 🚀 New Features

- **`batch_audit.py`** — 全面稽核工具：6 維度檢查 batch_status（Schema, Timeliness, Error Visibility, Data Integrity, Model Performance, Cross-File），產出 JSON 報告 + 終端機摘要
- **`model_diagnostics_{file_id}.json`** — 獨立 model 診斷檔案，寫入 per-model 真實成功率（含 retry 失敗），無需從 batch_status 手動解析
- **Embedding 進度即時寫入** — `phase_embedding()` 每嵌入一筆即更新 `diagnostics.phase3_progress` 至 batch_status

### 🔧 Improvements

- **Error 歸屬修正** — `phase_db_inserting()` 中的 `top_errors` 現在按 `errors[].model`（實際出錯的 model）歸屬，而非 `model_used`（最終成功的 model）。`diagnostics.models[].fail` 改為包含所有失敗（含 retry 過程中被其他 model 取代的失敗），`success_rate` 反映真實表現
- **Prompt 改良** — 移除「精準」要求、明確禁止引導詞（避免 framing 干擾 embedding）、指定繁體中文、排除 markdown code block。新 prompt 摘要直接從內容開始，減少 JSON parse 錯誤
- **`acquire_phase_slot()` 修復** — `open(path, 'w+')` 改為 `r+`，避免每次 truncate 後讀到空值導致 slot 計數永久歸零（並行控制形同虛設的 bug）
- **`run_batch_processor()` 多檔案處理** — 不再 `return` 第一個處理的檔案，改為在同一輪迴圈內掃描所有檔案並啟動所有可推進的任務。前一檔案進入 summarizing 後下一檔案立即開始 chunking，不需等待 30 秒間隔
- **Watchdog 主迴圈** — 移除 `break`，允許同一輪處理多個 batch 檔案
- **`finalize.py` list_tables API 相容** — 新版 lancedb 回傳 `ListTablesResponse` object（`.tables` 為字串列表），原始 `[t.name for t in raw.tables]` 將字串誤當物件
- **`run_wrapper.sh` 動態讀取 db_path** — `SRT_DB_PATH` 改從 `config_loader.get_nested_config('paths.db_path')` 讀取，不再硬編碼
- **`elapsed_sec` 追蹤** — `process_chunk()` 記錄每次 LLM call 的實際耗時，寫入 batch_status chunks，供 `chars_per_sec_actual` 精確計算
- **`chars_per_sec` 雙軌制** — diagnostics 同時輸出 `chars_per_sec_overall`（wall-clock）與 `chars_per_sec_actual`（實際處理時間）
- **`top_failed_models` 排序改進** — 現在依總失敗數排序，而非僅算 final fail

### 🔻 Removed

- **`NV-qwen3.5-122b`** — 從 `config.json` model list、`summarize_pipeline.py`/`summarize.py` fallback list、`state_manager.py` validator model 清單移除（100% 失敗率 6/6）

### ✅ Verified

- Batch 0~2 全部成功（3/3，共 117 chunks，全部寫入 LanceDB）
- 測試完成 3 次完整運行驗證

### 📋 Config Audit

經 subagent 全面清查 `config.json` 32 個 leaf keys：
- 30 個正確被程式碼使用
- 2 個 structural（`_comment`）
- `api.fallback.proxy_url` 為 orphaned key（`get_fallback_api_config()` 為 dead code）

---

## v1.3 (2026-05-12): 11-State Machine with Queueing & Chunk-Level Tracking

### ✅ Fixed (Phase 1 — Staunch Bleeding)
- **P0-1 `run_wrapper.sh` 補 `--batch` 參數**: 自動偵測 batch 檔案路徑
- **P0-2 `process_file()` 補 `update_state`**: 成功/失敗路徑皆呼叫 `update_state`
- **P0-3 model 重試輪換**: `(attempt-1) % len(MODELS)` 輪換

### 🚀 New Features (Phase 2 — Core Refactoring)
- **P0-5 11 狀態機 + 相位並發控制**
- **P0-8 batch_status 雙層 schema**: `chunks[]` 子陣列
- **P0-6 chunk 層級 `retry_count`**
- **P0-4 chunk 失敗追蹤與重試**: `run_failed_chunk_retry()`
- **P0-7 `failed_permanent` 通知與報告**

### 🧹 Cleanup (Phase 3)
- **P1-9 清理雙重 `write_to_db`**
- **P1-10 config.json 孤兒 key 移除**
- **P1-11 `embedding_url` → `proxy_url` 統一**
- **P1-12 非阻塞 fcntl flock**
- **P1-13 SKILL.md 更新**
- **P1-14 刪除廢棄 `watchdog.py`**

### 🎯 Finalization (Phase 4)
- **P2-15 `load_status()` 死碼清理**
- **P2-16 models 清單去重（後續已 revert，重複為刻意設計）**
- **P2-17 watchdog 超時統一**

### 🐛 Bug Fixes (Phase 5)
- `_VALID_TRANSITIONS` 補 `'undone'`
- `run_failed_chunk_retry()` 順序修正
- `retry_count` 追蹤修正
- `_write_failed_report()` 條件修正
- 向後相容舊格式 batch_status
- 相位 slot 啟動清理

### 🔧 Post-v1.3 Refinements
- `process_file` 拆分 4 階段（`--phase` 參數）
- 狀態機強化（`failed` → `undone` 自動排程）
- LanceDB 寫入 O(1) 優化
- 跨 Worker 模型輪詢（`_get_next_model()`）
- 錯誤追蹤強化（跨 retry 錯誤記錄）

### ✅ Verified
- Batch ID 10~14 全部通過（5/5，共 158 semantic chunks）

---

## v1.0 (2026-05-04): Stability & Resilience Baseline

### ✅ Fixed
- **Resolved "0-Chunk" Death Loop**: Multi-layer fallbacks (Time-based → Forced → Emergency)
- **Model Naming Consistency**: `openai.gpt-oss-120b` → `oci-openai.gpt-oss-120b`
- **Hybrid Error Handling**: Infrastructure checks, `ZeroChunksError`

### 🛠️ Improvements
- **Atomic Writing**: `CheckpointManager` with `fcntl` locking
- **Detailed Diagnostics**: `SRT-Pipeline-Diagnostics-Report.md`
- **Documentation**: `SKILL.md`, `README.md`

### ⚠️ Known Issues
- **Performance Bottleneck**: Embedding process single-request based

---

## 2026-05-03: Core Pipeline Implementation
- Initial implementation of Smart Merge 3.0
- Integration with LiteLLM Proxy and LanceDB
- Basic Watchdog heartbeat implementation
- Checkpoint-based resume functionality
