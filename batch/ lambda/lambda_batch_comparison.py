# lambda_batch_comparison.py
import json
import random
import time
from datetime import datetime

def lambda_handler(event, context):
    """
    AWS Batchと同じ処理をLambdaで実行
    """
    job_id = f"lambda-job-{int(time.time())}-{random.randint(1000, 9999)}"
    start_time = time.time()
    
    # AWS Batchと同じダミー処理
    time.sleep(random.uniform(0.1, 2.0))
    
    duration = time.time() - start_time
    is_success = random.random() > 0.005
    
    # AWS Batchと同じログ形式
    log_data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "job_id": job_id,
        "execution_env": "lambda",  # ← 識別用
        "status": "SUCCEEDED" if is_success else "FAILED",
        "duration": round(duration, 3),
        "message": "Job completed successfully" if is_success else "Job failed"
    }
    
    print(json.dumps(log_data))
    
    return {
        'statusCode': 200 if is_success else 500,
        'body': json.dumps(log_data)
    }
