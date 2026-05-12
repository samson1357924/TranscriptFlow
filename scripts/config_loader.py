#!/usr/bin/env python3
"""
統一配置加載模組

從 config.json 讀取預設值，環境變數具有最高優先級。
提供統一的參數存取接口，並包含基本驗證與安全檢查。
"""

import os
import json
import re
from pathlib import Path
from typing import Any, Optional, List

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = Path(os.getenv('TRANSCRIPTFLOW_CONFIG', SCRIPT_DIR / 'config.json'))
EXAMPLE_CONFIG_PATH = SCRIPT_DIR / 'config.example.json'

_config = None


def get_config() -> dict:
    """
    載入並返回配置字典（單例模式）
    """
    global _config
    if _config is None:
        path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
        if not path.exists():
            raise FileNotFoundError(f"配置檔案不存在：{CONFIG_PATH} 或 {EXAMPLE_CONFIG_PATH}")

        with open(path, 'r', encoding='utf-8') as f:
            _config = json.load(f)
    
    return _config


def get_env_or_config(env_var: str, config_path: str, default: Any = None) -> Any:
    """
    優先讀取環境變數，其次從 config.json 讀取，最後使用預設值
    
    Args:
        env_var: 環境變數名稱
        config_path: config.json 中的路徑（使用點號分隔，如 'chunking.window_size'）
        default: 預設值
    
    Returns:
        對應的值
    """
    # 優先檢查環境變數
    env_val = os.getenv(env_var)
    if env_val is not None:
        # 嘗試自動轉換類型
        return _convert_value(env_val, default)
    
    # 從 config.json 讀取
    config = get_config()
    parts = config_path.split('.')
    val = config
    
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return default
    
    return val if val is not None else default


def _convert_value(str_val: str, default: Any) -> Any:
    """
    嘗試將字串轉換為合適的類型
    """
    if default is None:
        return str_val
    
    if isinstance(default, bool):
        return str_val.lower() in ('true', '1', 'yes', 'on')
    elif isinstance(default, int):
        try:
            return int(str_val)
        except ValueError:
            return default
    elif isinstance(default, float):
        try:
            return float(str_val)
        except ValueError:
            return default
    elif isinstance(default, list):
        # 對於列表，嘗試解析 JSON
        try:
            parsed = json.loads(str_val)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return default
    else:
        return str_val


def get_nested_config(path: str, default: Any = None) -> Any:
    """
    直接從 config.json 讀取巢狀值
    
    Args:
        path: config.json 中的路徑（使用點號分隔）
        default: 預設值
    
    Returns:
        對應的值
    """
    config = get_config()
    parts = path.split('.')
    val = config
    
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return default
    
    return val if val is not None else default


def validate_config() -> list:
    """
    驗證配置參數的合理性
    
    Returns:
        錯誤訊息清單（無錯誤時為空清單）
    """
    errors = []
    config = get_config()
    
    # 驗證 chunking 參數
    cw = config.get('chunking', {}).get('smart_merge_window_size', 5)
    if not (1 <= cw <= 20):
        errors.append(f"smart_merge_window_size 必須介於 1~20，當前值：{cw}")
    
    mcd = config.get('chunking', {}).get('max_chunk_duration_sec', 300)
    if mcd < 30:
        errors.append(f"max_chunk_duration_sec 必須 >= 30，當前值：{mcd}")
    
    mc = config.get('chunking', {}).get('min_chunks', 2)
    if mc < 1:
        errors.append(f"min_chunks 必須 >= 1，當前值：{mc}")
    
    mxc = config.get('chunking', {}).get('max_chunks', 200)
    if mxc < mc:
        errors.append(f"max_chunks ({mxc}) 必須 >= min_chunks ({mc})")
    
    # 驗證 embedding 參數
    edim = config.get('embedding', {}).get('expected_dim', 3072)
    if edim <= 0:
        errors.append(f"expected_dim 必須 > 0，當前值：{edim}")
    
    # 驗證 summarization 參數
    pc = config.get('summarization', {}).get('participant_chunks', 3)
    if pc < 1:
        errors.append(f"participant_chunks 必須 >= 1，當前值：{pc}")
    
    mr = config.get('summarization', {}).get('max_retries', 3)
    if mr < 0:
        errors.append(f"max_retries 必須 >= 0，當前值：{mr}")
    
    # 驗證路徑參數
    return errors


def validate_path(path: str, allowed_base: str = None) -> tuple[bool, str]:
    """
    驗證路徑是否合法，防止路徑穿越攻擊
    
    Args:
        path: 要驗證的路徑
        allowed_base: 允許的基础目录（可选）
    
    Returns:
        (是否合法, 訊息)
    """
    if not path:
        return False, "路徑為空"
    
    try:
        real_path = os.path.realpath(path)
        
        # 檢查是否包含 .. 等危險路徑元件
        if '..' in path.split(os.sep):
            # 允許 .. 但需要檢查解析後的實際位置
            if allowed_base:
                real_base = os.path.realpath(allowed_base)
                if not real_path.startswith(real_base + os.sep) and real_path != real_base:
                    return False, f"路徑 {path} 超出允許範圍 {allowed_base}"
        
        return True, "路徑合法"
    except Exception as e:
        return False, f"路徑驗證失敗: {e}"


def sanitize_api_url(url: str) -> tuple[bool, str]:
    """
    驗證 API URL 的安全性
    
    策略：
    1. 允許 HTTPS 連接（最安全）
    2. 允許 HTTP 連接，但僅限於受信任的內部網路（Localhost, Private IP）
    3. 阻止 HTTP 連接至公网 IP（防止數據洩漏到未加密的外部網路）
    
    Args:
        url: API URL
    
    Returns:
        (是否合法, 訊息)
    """
    if not url:
        return False, "URL 為空"
    
    # 允許 HTTPS，無需檢查
    if url.startswith('https://'):
        return True, "URL 合法 (HTTPS)"
    
    # 僅處理 HTTP 連接
    if url.startswith('http://'):
        # 檢查是否強制允許 HTTP（開發模式）
        allow_insecure = os.getenv('ALLOW_INSECURE_HTTP', '').lower() in ('1', 'true', 'yes')
        
        if allow_insecure:
            logger.warning("⚠️ 注意：ALLOW_INSECURE_HTTP 已啟用，允許所有 HTTP 連接（僅限開發測試）")
            return True, "URL 合法 (強制允許 HTTP)"
        
        # 解析主機名/IP
        try:
            # 提取主機部分 (去掉 port)
            host_part = url.split('http://')[1].split('/')[0].split(':')[0]
            
            # 檢查是否為內部網路 IP 或 localhost
            is_internal = (
                host_part == 'localhost' or
                host_part == '127.0.0.1' or
                host_part.startswith('10.') or                  # Class A Private
                host_part.startswith('172.16.') or              # Class B Private (172.16-31)
                host_part.startswith('172.17.') or
                host_part.startswith('172.18.') or
                host_part.startswith('172.19.') or
                host_part.startswith('172.20.') or
                host_part.startswith('172.21.') or
                host_part.startswith('172.22.') or
                host_part.startswith('172.23.') or
                host_part.startswith('172.24.') or
                host_part.startswith('172.25.') or
                host_part.startswith('172.26.') or
                host_part.startswith('172.27.') or
                host_part.startswith('172.28.') or
                host_part.startswith('172.29.') or
                host_part.startswith('172.30.') or
                host_part.startswith('172.31.') or
                host_part.startswith('192.168.') or             # Class C Private
                host_part.startswith('169.254.') or             # Link-local
                host_part.startswith('100.64.')                 # Carrier-grade NAT (通常也是內部)
            )
            
            if is_internal:
                return True, f"URL 合法 (內部網路 HTTP: {host_part})"
            else:
                # 嘗試解析 DNS 以確認是否為內部 IP（防偽裝）
                import socket
                try:
                    ip = socket.gethostbyname(host_part)
                    # 再次檢查解析後的 IP 是否為內部
                    if (ip.startswith('10.') or ip.startswith('172.') or 
                        ip.startswith('192.168.') or ip.startswith('127.')):
                        return True, f"URL 合法 (DNS 解析為內部 IP: {ip})"
                except:
                    pass  # DNS 解析失敗，繼續檢查原始 host_part
                
                return False, f"❌ 安全阻止：HTTP 連接至外部網路 ({host_part}) 不被允許。請使用 HTTPS 或確認這是內部 IP。"
        except Exception as e:
            return False, f"URL 解析失敗: {e}"
    
    return False, f"不支持的協議: {url.split(':')[0]}"

# 增加一個日誌 helper，避免循環引用
import logging
logger = logging.getLogger(__name__)


def get_api_config() -> dict:
    """
    取得 OpenAI-compatible API 配置（優先環境變數，fallback 到 config.json）
    
    優先級：
    1. OPENAI_BASE_URL / OPENAI_API_KEY
    2. Legacy LITELLM_PROXY_URL / LITELLM_PROXY_KEY
    3. config.json api.base_url / api.api_key
    4. Legacy config.json api.primary.proxy_url
    
    Returns:
        {
            'base_url': str,
            'proxy_url': str,
            'embedding_url': str,
            'api_key': str,
            'api_timeout': int,
            'chat_completions_path': str,
            'embeddings_path': str,
            'models_path': str
        }
    """
    config = get_config()
    api_cfg = config.get('api', {})
    
    # 環境變數優先
    base_url = (
        os.getenv('OPENAI_BASE_URL')
        or os.getenv('LITELLM_PROXY_URL')
        or os.getenv('EMBEDDING_API_BASE')
    )
    embedding_url = os.getenv('EMBEDDING_API_BASE')
    api_key = os.getenv('OPENAI_API_KEY') or os.getenv('LITELLM_PROXY_KEY')
    
    if not base_url:
        base_url = api_cfg.get('base_url', '')

    if not base_url:
        primary = api_cfg.get('primary', {})
        base_url = primary.get('proxy_url', '')

    # OpenAI-compatible endpoints normally share one base URL.
    embedding_url = embedding_url or base_url

    if not api_key:
        api_key = api_cfg.get('api_key', '')
    
    api_timeout = api_cfg.get('api_timeout', 60)
    chat_completions_path = api_cfg.get('chat_completions_path', '/v1/chat/completions')
    embeddings_path = api_cfg.get('embeddings_path', '/v1/embeddings')
    models_path = api_cfg.get('models_path', '/v1/models')
    
    return {
        'base_url': base_url,
        # Backward-compatible alias for older call sites.
        'proxy_url': base_url,
        'embedding_url': embedding_url,
        'api_key': api_key,
        'api_timeout': api_timeout,
        'chat_completions_path': chat_completions_path,
        'embeddings_path': embeddings_path,
        'models_path': models_path
    }


def get_fallback_api_config() -> dict:
    """
    取得備援 API 配置
    """
    config = get_config()
    api_cfg = config.get('api', {})
    fallback = api_cfg.get('fallback', {})
    
    return {
        'proxy_url': fallback.get('proxy_url', ''),
        'embedding_url': fallback.get('embedding_url', ''),
        'api_key': api_cfg.get('api_key', ''),
        'api_timeout': api_cfg.get('api_timeout', 60)
    }


def get_required_env_vars() -> list:
    """
    返回必須設定的環境變數清單（v1.1起 API key 已移至 config.json，環境變數為可選）
    
    Returns:
        環境變數名稱清單
    """
    return []


def check_required_env_vars() -> tuple[bool, list]:
    """
    檢查必要的配置是否已設定（環境變數 或 config.json）
    
    Returns:
        (是否全部設定, 未設定的項目清單)
    """
    missing = []
    
    # 檢查 API key（環境變數 或 config.json）
    api_key = os.getenv('OPENAI_API_KEY') or os.getenv('LITELLM_PROXY_KEY') or get_nested_config('api.api_key')
    if not api_key:
        missing.append('api.api_key (config.json) 或 OPENAI_API_KEY (env)')
    
    return len(missing) == 0, missing


def ensure_secure_permissions(path: str, mode: int = 0o700) -> tuple[bool, str]:
    """
    確保目錄或檔案具有安全的權限
    
    Args:
        path: 路徑
        mode: 權限模式（預設 0o700，僅所有者可訪問）
    
    Returns:
        (是否成功, 訊息)
    """
    try:
        if os.path.exists(path):
            os.chmod(path, mode)
            return True, f"已設置權限 {oct(mode)} 於 {path}"
        else:
            return False, f"路徑不存在：{path}"
    except Exception as e:
        return False, f"設置權限失敗: {e}"
