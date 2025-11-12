import json
import boto3
import os

TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MonitoringAlerts')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    try:
        # パスパラメータからalert_idを取得
        alert_id = event['pathParameters']['alert_id']
        
        # リクエストボディからstatusを取得
        body = json.loads(event['body'])
        new_status = body.get('status')
        
        # バリデーション
        valid_statuses = ['pending', 'true_positive', 'false_positive']
        if new_status not in valid_statuses:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': f'Invalid status. Must be one of: {valid_statuses}'
                })
            }
        
        # DynamoDBのステータスを更新
        response = table.update_item(
            Key={'alert_id': alert_id},
            UpdateExpression='SET #status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': new_status},
            ReturnValues='ALL_NEW'
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'PUT,OPTIONS'
            },
            'body': json.dumps({
                'message': 'Status updated successfully',
                'alert_id': alert_id,
                'new_status': new_status,
                'updated_item': response.get('Attributes', {})
            })
        }
    except KeyError as e:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Missing required field: {str(e)}'})
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
