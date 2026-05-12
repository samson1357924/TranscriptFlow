#!/usr/bin/env python3
"""
健康檢查工具

檢查以下服務的可用性：
1. Embedding 服務（呼叫 /v1/models 端點）
2. 確認 configured embedding 模型存在
3. OpenAI-compatible API 連接
4. LanceDB 目錄存在性

用法：
    python3 health_check.py

退出碼：
    0 = 所有檢查通過
    1 = 至少一項檢查失敗
"""

import os
import sys
import json
import urllib.request
from pathlib import Path

# 加入 scripts 目錄到 path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from logger_config import get_logger
from config_loader import get_env_or_config, sanitize_api_url, ensure_secure_permissions, get_api_config

logger = get_logger('health_check')


def check_embedding_service() -> tuple[bool, str]:
    """
    檢查 Embedding 服務可用性
    
    Returns:
        (是否成功, 訊息)
    """
    _api_cfg = get_api_config()
    base_url = _api_cfg['base_url']
    
    # 驗證 URL 安全性
    valid, msg = sanitize_api_url(base_url)
    if not valid:
        return False, msg
    
    url = f"{base_url.rstrip('/')}{_api_cfg['models_path']}"
    api_key = _api_cfg['api_key']
    
    try:
        req = urllib.request.Request(url)
        if api_key:
            req.add_header('Authorization', f'Bearer {api_key}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
            models = [m['id'] for m in data.get('data', [])]
            
            embedding_model = get_env_or_config('EMBEDDING_MODEL', 'embedding.model', 'text-embedding-3-large')
            
            if embedding_model in models:
                return True, f"✅ Embedding 服務正常 (模型 '{embedding_model}' 可用)"
            else:
                available = ', '.join(models[:5])
                return False, f"❌ 模型 '{embedding_model}' 未找到。可用模型: {available}"
    except urllib.error.URLError as e:
        return False, f"❌ Embedding 服務無法連接 ({base_url}): {e}"
    except Exception as e:
        return False, f"❌ Embedding 服務檢查失敗: {e}"


def check_openai_compatible_api() -> tuple[bool, str]:
    """
    檢查 OpenAI-compatible API 連接（與 Embedding 服務同一端點）
    
    Returns:
        (是否成功, 訊息)
    """
    _api_cfg = get_api_config()
    base_url = _api_cfg['base_url']
    
    # 驗證 URL 安全性
    valid, msg = sanitize_api_url(base_url)
    if not valid:
        return False, msg
    
    api_key = _api_cfg['api_key']
    if not api_key:
        return False, "❌ API key 未設定（config.json api.api_key）"
    
    # 呼叫 /v1/models 端點
    url = f"{base_url.rstrip('/')}{_api_cfg['models_path']}"
    
    try:
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {api_key}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, f"✅ OpenAI-compatible API 連接正常 ({base_url})"
            else:
                return False, f"❌ OpenAI-compatible API 返回錯誤狀態碼: {resp.status}"
    except Exception as e:
        return False, f"❌ OpenAI-compatible API 檢查失敗: {e}"


# Backward-compatible import name for older scripts.
check_llm_proxy = check_openai_compatible_api


def check_lancedb_dir() -> tuple[bool, str]:
    """
    檢查 LanceDB 目錄是否存在並設置安全權限
    
    Returns:
        (是否成功, 訊息)
    """
    db_path = get_env_or_config('SRT_DB_PATH', 'paths.db_path', 
                                 './output/lance_test_db')
    
    if os.path.exists(db_path):
        # 設置安全權限
        success, msg = ensure_secure_permissions(db_path)
        if success:
            return True, f"✅ LanceDB 目錄存在且權限已設置: {db_path}"
        else:
            return True, f"⚠️ LanceDB 目錄存在但權限設置失敗: {msg}"
    else:
        # 嘗試建立目錄
        try:
            os.makedirs(db_path, exist_ok=True)
            # 設置安全權限
            ensure_secure_permissions(db_path)
            return True, f"✅ LanceDB 目錄已建立且權限已設置: {db_path}"
        except Exception as e:
            return False, f"❌ LanceDB 目錄不存在且無法建立: {e}"


def main():
    """主函數：執行所有健康檢查"""
    logger.info("開始執行健康檢查...")
    
    # 使用 logger 而非 print
    logger.info("=" * 60)
    logger.info("SRT Semantic Chunk 健康檢查")
    logger.info("=" * 60)
    
    checks = [
        ("OpenAI-compatible API 連接", check_openai_compatible_api),
        ("Embedding 服務", check_embedding_service),
        ("LanceDB 目錄", check_lancedb_dir),
    ]
    
    results = []
    all_passed = True
    
    for name, check_func in checks:
        logger.info(f"\n檢查: {name}...")
        success, message = check_func()
        results.append((name, success, message))
        
        if success:
            logger.info(f"  {message}")
        else:
            logger.warning(f"  {message}")
            all_passed = False
    
    logger.info("\n" + "=" * 60)
    logger.info("檢查結果摘要:")
    logger.info("=" * 60)
    
    passed_count = sum(1 for _, success, _ in results if success)
    total_count = len(results)
    
    for name, success, message in results:
        status = "✅ 通過" if success else "❌ 失敗"
        logger.info(f"  {status} - {name}")
    
    logger.info(f"\n總計: {passed_count}/{total_count} 檢查通過")
    
    if all_passed:
        logger.info("\n🎉 所有健康檢查通過！")
        sys.exit(0)
    else:
        logger.warning("\n⚠️ 部分檢查失敗，請檢查上述錯誤訊息。")
        sys.exit(1)


if __name__ == '__main__':
    main()
