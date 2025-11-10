import json
import random
import time
import sys
from datetime import datetime

def main():
    """
    バッチジョブシミュレーター (AWS Batch版)
    終了コードで成功/失敗を判定
    """
    
    # ジョブIDの生成
    job_id = f"job-{int(time.time())}-{random.randint(1000, 9999)}"
    
    # 処理開始時刻
    start_time = time.time()
    
    print(f"[INFO] Job started: {job_id}")
    
    # ダミー処理
    try:
        simulate_job_execution()
        
        # 処理時間の計算
        duration = time.time() - start_time
        
        # 成功/失敗の判定 (99.5%の確率で成功)
        is_success = random.random() > 0.005
        
        # ログ出力
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_id": job_id,
            "status": "SUCCEEDED" if is_success else "FAILED",
            "duration": round(duration, 3),
            "message": "Job completed successfully" if is_success else "Job failed due to simulated error"
        }
        
        print(json.dumps(log_data))
        
        # 終了コードで成功/失敗を判定
        if is_success:
            print(f"[INFO] Job succeeded: {job_id}")
            sys.exit(0)  # 成功
        else:
            print(f"[ERROR] Job failed: {job_id}")
            sys.exit(1)  # 失敗
            
    except Exception as e:
        # 予期しないエラー
        print(f"[ERROR] Unexpected error: {str(e)}")
        sys.exit(1)


def simulate_job_execution():
    """
    ダミーのジョブ処理
    実際の処理時間をシミュレート
    """
    processing_time = random.uniform(0.1, 2.0)
    time.sleep(processing_time)
    
    # 実際のバッチ処理なら:
    # - RDS接続
    # - データ処理
    # など


if __name__ == "__main__":
    main()
