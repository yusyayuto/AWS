import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal

TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MonitoringAlerts')
CLOUDWATCH_NAMESPACE = os.environ.get('CLOUDWATCH_NAMESPACE', 'MonitoringSystem')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
cloudwatch = boto3.client('cloudwatch')

def lambda_handler(event, context):
    try:
        # DynamoDBから全アラートデータを取得
        response = table.scan()
        items = response.get('Items', [])
        
        print(f"Total alerts found: {len(items)}")
        
        # 誤検知率を計算
        false_positive_rate = calculate_false_positive_rate(items)
        
        # 遅延時間を計算
        avg_delay_time = calculate_average_delay_time(items)
        
        # CloudWatch Metricsに送信
        send_metrics(false_positive_rate, avg_delay_time, len(items))
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Metrics calculated and sent successfully',
                'total_alerts': len(items),
                'false_positive_rate': float(false_positive_rate) if false_positive_rate is not None else None,
                'average_delay_time': float(avg_delay_time) if avg_delay_time is not None else None
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def calculate_false_positive_rate(items):
    """誤検知率を計算"""
    if not items:
        return None
    
    # 判定済みのアラートのみを対象
    judged_items = [item for item in items if item.get('status') in ['true_positive', 'false_positive']]
    
    if not judged_items:
        print("No judged alerts found")
        return None
    
    false_positive_count = len([item for item in judged_items if item.get('status') == 'false_positive'])
    total_judged = len(judged_items)
    
    rate = (false_positive_count / total_judged) * 100
    
    print(f"False positive rate: {rate}% ({false_positive_count}/{total_judged})")
    
    return rate

def calculate_average_delay_time(items):
    """平均遅延時間を計算（秒）"""
    delay_times = []
    
    for item in items:
        timestamp = item.get('timestamp')
        notification_time = item.get('notification_time')
        
        if timestamp and notification_time:
            try:
                # ISO形式の日時文字列をパース
                alert_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                notif_time = datetime.fromisoformat(notification_time.replace('Z', '+00:00'))
                
                # 遅延時間を秒で計算
                delay = (notif_time - alert_time).total_seconds()
                
                # 負の値やあまりに大きな値は除外
                if 0 <= delay <= 3600:  # 1時間以内
                    delay_times.append(delay)
                    
            except Exception as e:
                print(f"Error parsing timestamps: {e}")
                continue
    
    if not delay_times:
        print("No valid delay times found")
        return None
    
    avg_delay = sum(delay_times) / len(delay_times)
    
    print(f"Average delay time: {avg_delay} seconds (from {len(delay_times)} alerts)")
    
    return avg_delay

def send_metrics(false_positive_rate, avg_delay_time, total_alerts):
    """CloudWatch Metricsにカスタムメトリクスを送信"""
    metric_data = []
    
    timestamp = datetime.utcnow()
    
    # 誤検知率のメトリクス
    if false_positive_rate is not None:
        metric_data.append({
            'MetricName': 'FalsePositiveRate',
            'Value': float(false_positive_rate),
            'Unit': 'Percent',
            'Timestamp': timestamp
        })
    
    # 平均遅延時間のメトリクス
    if avg_delay_time is not None:
        metric_data.append({
            'MetricName': 'AverageDelayTime',
            'Value': float(avg_delay_time),
            'Unit': 'Seconds',
            'Timestamp': timestamp
        })
    
    # 全アラート数のメトリクス
    metric_data.append({
        'MetricName': 'TotalAlerts',
        'Value': total_alerts,
        'Unit': 'Count',
        'Timestamp': timestamp
    })
    
    if metric_data:
        cloudwatch.put_metric_data(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricData=metric_data
        )
        print(f"Sent {len(metric_data)} metrics to CloudWatch")
