import json
import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    """
    AWS Batch のジョブステータスイベントからメトリクスを収集
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    # イベントから情報を取得
    detail = event.get('detail', {})
    status = detail.get('status')
    job_name = detail.get('jobName')
    job_id = detail.get('jobId')
    
    # job_category を抽出
    job_category = extract_job_category(job_name)
    
    # タイムスタンプ
    created_at = detail.get('createdAt')
    started_at = detail.get('startedAt')
    stopped_at = detail.get('stoppedAt')
    
    print(f"Job: {job_name}, Status: {status}, Category: {job_category}")
    
    # ===== 1. 待機時間の測定 (RUNNING 時) =====
    if status == 'RUNNING' and created_at and started_at:
        wait_time = (started_at - created_at) / 1000.0
        
        print(f"Wait time: {wait_time} seconds")
        
        try:
            cloudwatch.put_metric_data(
                Namespace='sasaki-Batchtest',
                MetricData=[
                    {
                        'MetricName': f'JobWaitTime-batch-{job_category}',
                        'Value': wait_time,
                        'Unit': 'Seconds',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
            print(f"Wait time metric sent: {wait_time}s for {job_category}")
        except Exception as e:
            print(f"Error sending wait time metric: {e}")
    
    # ===== 2. リトライ & 完了の測定 (SUCCEEDED/FAILED 時) =====
    elif status in ['SUCCEEDED', 'FAILED']:
        attempts = detail.get('attempts', [])
        attempt_count = len(attempts)
        
        print(f"Job finished. Status: {status}, Attempts: {attempt_count}")
        
        # リトライ発生 (2回以上の試行 = リトライあり)
        is_retry = 1 if attempt_count > 1 else 0
        
        try:
            cloudwatch.put_metric_data(
                Namespace='sasaki-Batchtest',
                MetricData=[
                    {
                        'MetricName': f'JobRetried-batch-{job_category}',
                        'Value': is_retry,
                        'Unit': 'Count',
                        'Timestamp': datetime.utcnow()
                    },
                    {
                        'MetricName': f'JobCompleted-batch-{job_category}',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': datetime.utcnow()
                    }
                ]
            )
            print(f"Retry & Completion metrics sent for {job_category}")
        except Exception as e:
            print(f"Error sending retry metrics: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Metrics processed')
    }


def extract_job_category(job_name):
    """job_name から job_category を抽出"""
    if not job_name:
        return 'unknown'
    
    job_name_lower = job_name.lower()
    
    if 'critical' in job_name_lower:
        return 'critical'
    elif 'normal' in job_name_lower:
        return 'normal'
    elif 'low' in job_name_lower:
        return 'low'
    else:
        return 'unknown'
