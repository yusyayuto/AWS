import json
import os
import boto3

def lambda_handler(event, context):
    secret_arn = os.environ.get('DB_SECRET_ARN')
    
    if not secret_arn:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': '環境変数 DB_SECRET_ARN が設定されていません'})
        }
    
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_arn)
    creds = json.loads(response['SecretString'])
    
    import pg8000
    
    # batch_etl データベースに接続
    conn = pg8000.connect(
        host=creds['host'],
        database='batch_etl',
        user=creds['username'],
        password=creds['password'],
        port=int(creds['port'])
    )
    
    cursor = conn.cursor()
    
    # etl_job_history テーブルを作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS etl_job_history (
            job_id SERIAL PRIMARY KEY,
            job_name VARCHAR(100) NOT NULL,
            execution_date DATE NOT NULL,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            status VARCHAR(20) NOT NULL,
            records_processed INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'etl_job_history table created successfully'
        })
    }
