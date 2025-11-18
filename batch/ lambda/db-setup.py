import json
import boto3

def lambda_handler(event, context):
    client = boto3.client('secretsmanager')
    secret_arn = 'arn:aws:secretsmanager:ap-northeast-1:832362088330:secret:rds!db-xxxxxxxx'
    
    response = client.get_secret_value(SecretId=secret_arn)
    creds = json.loads(response['SecretString'])
    
    import pg8000
    
    # postgres データベースに接続
    conn = pg8000.connect(
        host=creds['host'],
        database=creds.get('dbname', 'postgres'),
        user=creds['username'],
        password=creds['password'],
        port=int(creds['port'])
    )
    
    cursor = conn.cursor()
    
    # batch_etl データベース作成
    cursor.execute("SELECT 1 FROM pg_database WHERE datname='batch_etl'")
    if not cursor.fetchone():
        conn.autocommit = True
        cursor.execute("CREATE DATABASE batch_etl")
        conn.autocommit = False
    
    cursor.close()
    conn.close()
    
    # batch_etl に接続し直す
    conn = pg8000.connect(
        host=creds['host'],
        database='batch_etl',
        user=creds['username'],
        password=creds['password'],
        port=int(creds['port'])
    )
    
    cursor = conn.cursor()
    
    # orders テーブル
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
    
    # daily_summary テーブル
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
    
    # etl_job_history テーブル
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
            'database': 'batch_etl',
            'tables_created': ['orders', 'daily_summary', 'etl_job_history'],
            'sample_data_inserted': inserted
        })
    }
