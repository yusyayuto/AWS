import json
import boto3
import os
from boto3.dynamodb.conditions import Attr
from decimal import Decimal

TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MonitoringAlerts')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# DynamoDBのDecimal型をJSON化するためのヘルパー
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    try:
        # クエリパラメータからフィルタを取得（オプション）
        query_params = event.get('queryStringParameters', {}) or {}
        status_filter = query_params.get('status')
        
        # DynamoDBからデータを取得
        if status_filter:
            response = table.scan(
                FilterExpression=Attr('status').eq(status_filter)
            )
        else:
            response = table.scan()
        
        items = response.get('Items', [])
        
        # timestampで降順ソート（新しい順）
        items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': json.dumps({
                'alerts': items,
                'count': len(items)
            }, cls=DecimalEncoder)
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
