import json
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """
    AWS Batchのジョブステータスイベントからメトリクスを収集
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    # イベントから情報を取得
    detail = event.get('detail', {})
    status = detail.get('status')
    job_name = detail.get('jobName')
    job_id = detail.get('jobId')
    
    # タイムスタンプ
    created_at = detail.get('createdAt')  # ジョブ投入時刻
    started_at = detail.get('startedAt')  # ジョブ開始時刻
    stopped_at = detail.get('stoppedAt')  # ジョブ終了時刻
    
    print(f"Job: {job_name}, Status: {status}")
    
    # ジョブが開始された時 (RUNNING状態になった時)
    if status == 'RUNNING' and created_at and started_at:
        # 待機時間を計算 (ミリ秒 → 秒)
        wait_time = (started_at - created_at) / 1000.0
        
        print(f"Wait time: {wait_time} seconds")
        
        # CloudWatch Metricsに送信
        try:
            cloudwatch.put_metric_data(
                Namespace='BatchSimulation',
                MetricData=[
                    {
                        'MetricName': 'JobWaitTime',
                        'Value': wait_time,
                        'Unit': 'Seconds',
                        'Timestamp': datetime.now()
                    }
                ]
            )
            print("Metric sent successfully")
        except Exception as e:
            print(f"Error sending metric: {e}")
    
    # ジョブが完了した時 (SUCCEEDED/FAILED)
    elif status in ['SUCCEEDED', 'FAILED']:
        # Retry情報を取得
        attempts = detail.get('attempts', [])
        attempt_count = len(attempts)
        
        print(f"Job finished. Attempts: {attempt_count}")
        
        # Retry発生をメトリクス化
        is_retry = 1 if attempt_count > 1 else 0
        
        try:
            cloudwatch.put_metric_data(
                Namespace='BatchSimulation',
                MetricData=[
                    {
                        'MetricName': 'JobRetried',
                        'Value': is_retry,
                        'Unit': 'Count',
                        'Timestamp': datetime.now()
                    },
                    {
                        'MetricName': 'JobCompleted',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': datetime.now()
                    }
                ]
            )
            print("Retry metrics sent successfully")
        except Exception as e:
            print(f"Error sending retry metrics: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Metrics processed')
    }
