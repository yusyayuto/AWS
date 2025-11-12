import json
import boto3
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('MonitoringAlerts')

def lambda_handler(event, context):
    # SNSメッセージを取得
    sns_message = json.loads(event['Records'][0]['Sns']['Message'])
    
    # アラーム情報を抽出
    alarm_name = sns_message.get('AlarmName', 'Unknown')
    new_state = sns_message.get('NewStateValue', 'ALARM')
    timestamp = sns_message.get('StateChangeTime', datetime.utcnow().isoformat())
    
    # Trigger情報からメトリクス詳細を取得
    trigger = sns_message.get('Trigger', {})
    metric_name = trigger.get('MetricName', 'Unknown')
    
    # alert_idを生成
    alert_id = f"alert-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:8]}"
    
    # DynamoDBに保存
    item = {
        'alert_id': alert_id,
        'timestamp': timestamp,
        'alarm_name': alarm_name,
        'alert_type': metric_name,
        'status': 'pending',
        'new_state': new_state,
        'notification_time': datetime.utcnow().isoformat(),
        'raw_message': json.dumps(sns_message)
    }
    
    try:
        table.put_item(Item=item)
        print(f"Alert recorded: {alert_id}")
        return {
            'statusCode': 200,
            'body': json.dumps(f'Alert {alert_id} recorded successfully')
        }
    except Exception as e:
        print(f"Error recording alert: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
