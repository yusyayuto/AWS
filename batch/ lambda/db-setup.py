import json
import boto3

def lambda_handler(event, context):
    # Secrets Manager から認証情報取得
    client = boto3.client('secretsmanager')
    
    # 実際のシークレット ARN に置き換えてください
    secret_arn = 'arn:aws:secretsmanager:ap-northeast-1:832362088330:secret:rds!db-xxxxxxxx'
    
    response = client.get_secret_value(SecretId=secret_arn)
    creds = json.loads(response['SecretString'])
    
    # psycopg2 が使えない場合は pg8000 を使用
    import pg8000
    
    conn = pg8000.connect(
        host=creds['host'],
        database='batch_etl',
        user=creds['username'],
        password=creds['password'],
        port=int(creds['port'])
    )
    
    cursor = conn.cursor()
    
    # テーブル作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            order_date DATE NOT NULL,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price DECIMAL(10, 2) NOT NULL,
            total_amount DECIMAL(10, 2) NOT NULL,
            region VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            summary_id SERIAL PRIMARY KEY,
            summary_date DATE NOT NULL,
            region VARCHAR(50) NOT NULL,
            product_id INTEGER NOT NULL,
            total_orders INTEGER NOT NULL,
            total_quantity INTEGER NOT NULL,
            total_amount DECIMAL(12, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(summary_date, region, product_id)
        )
    """)
    
    # サンプルデータ投入
    cursor.execute("SELECT COUNT(*) FROM orders")
    count = cursor.fetchone()[0]
    
    if count == 0:
        cursor.execute("""
            INSERT INTO orders (order_date, customer_id, product_id, quantity, unit_price, total_amount, region)
            SELECT
                CURRENT_DATE - (random() * 30)::integer,
                (random() * 100)::integer + 1,
                (random() * 10)::integer + 1,
                (random() * 5)::integer + 1,
                (random() * 100 + 10)::numeric(10,2),
                ((random() * 5)::integer + 1) * (random() * 100 + 10)::numeric(10,2),
                CASE (random() * 4)::integer
                    WHEN 0 THEN 'North'
                    WHEN 1 THEN 'South'
                    WHEN 2 THEN 'East'
                    ELSE 'West'
                END
            FROM generate_series(1, 100)
        """)
        inserted = 100
    else:
        inserted = 0
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Database setup completed',
            'tables_created': ['orders', 'daily_summary'],
            'sample_data_inserted': inserted
        })
    }
