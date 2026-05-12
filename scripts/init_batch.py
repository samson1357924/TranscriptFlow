import os
import sys
import argparse
from state_manager import init_batch
from logger_config import get_logger

logger = get_logger('init_batch')


def check_health():
    """執行健康檢查"""
    try:
        # 加入 scripts 目錄到 path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        
        from health_check import check_openai_compatible_api, check_embedding_service, check_lancedb_dir
        
        print("\n執行健康檢查...")
        print("=" * 50)
        
        checks = [
            ("OpenAI-compatible API", check_openai_compatible_api),
            ("Embedding 服務", check_embedding_service),
            ("LanceDB 目錄", check_lancedb_dir),
        ]
        
        all_passed = True
        for name, check_func in checks:
            success, msg = check_func()
            status = "✅" if success else "❌"
            print(f"{status} {name}: {msg}")
            if not success:
                all_passed = False
        
        print("=" * 50)
        
        if all_passed:
            print("✅ 健康檢查通過")
            return True
        else:
            print("⚠️ 部分健康檢查失敗，建議檢查配置")
            return False
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        print(f"⚠️ 健康檢查執行失敗: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Initialize a semantic-chunk batch.')
    parser.add_argument('--start', type=int, required=True, help='Start index (inclusive)')
    parser.add_argument('--end', type=int, required=True, help='End index (inclusive)')
    parser.add_argument('--check-health', action='store_true', 
                        help='執行健康檢查後再初始化批次')
    parser.add_argument('--no-health-check', action='store_true',
                        help='明確跳過健康檢查（預設行為）')
    
    args = parser.parse_args()
    
    # 如果指定 --check-health，執行健康檢查
    if args.check_health:
        if not check_health():
            logger.warning("健康檢查未完全通過，但繼續執行...")
            # 不阻斷執行，僅記錄警告
    
    logger.info(f"Initializing batch from {args.start} to {args.end}")
    init_batch(args.start, args.end)
    
    print(f"✅ 批次初始化完成: {args.start} - {args.end}")


if __name__ == '__main__':
    main()
