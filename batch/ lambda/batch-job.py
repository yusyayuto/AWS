import json
import random
import time
from datetime import datetime

def lambda_handler(event, context):
    """
    バッチジョブシミュレーター
    - 成功率: 約99.5% (失敗率0.5%)
    - ログをJSON形式で出力
    """
    
    # ジョブIDの生成
    job_id = f"job-{int(time.time())}-{random.randint(1000, 9999)}"
    
    # 処理開始時刻
    start_time = time.time()
    
    # ダミー処理（実際の処理をここに書く）
    # 例: RDSへのクエリ、データ加工など
    simulate_job_execution()
    
    # 処理時間の計算
    duration = time.time() - start_time
    
    # 成功/失敗の判定 (99.5%の確率で成功)
    # random.random()は0.0-1.0の乱数を返す
    is_success = random.random() > 0.005  # 0.5%の確率で失敗
    
    # ログ出力用のデータ構造
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "job_id": job_id,
        "status": "SUCCEEDED" if is_success else "FAILED",
        "duration": round(duration, 3),  # 秒単位、小数点3桁
        "message": "Job completed successfully" if is_success else "Job failed due to simulated error"
    }
    
    # JSON形式でログ出力（CloudWatch Logsに記録される）
    print(json.dumps(log_data))
    
    # Lambda関数の戻り値
    return {
        'statusCode': 200 if is_success else 500,
        'body': json.dumps(log_data)
    }


def simulate_job_execution():
    """
    ダミーのジョブ処理
    実際の処理時間をシミュレート (0.1-2.0秒)
    """
    # ランダムな処理時間をシミュレート
    processing_time = random.uniform(0.1, 2.0)
    time.sleep(processing_time)
    
    # 実際のバッチ処理ならここで:
    # - RDSへの接続とクエリ実行
    # - データの加工
    # - 外部APIの呼び出し
    # など
