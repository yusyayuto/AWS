"""
ETL メイン処理
昨日の注文データを集計して daily_summary テーブルに保存
"""
import json
import time
import os
from datetime import datetime, timedelta
from db_connector import DBConnector


def main():
    """ETL メイン処理"""
    
    # 環境変数から設定取得
    job_type = os.environ.get('JOB_TYPE', 'daily-summary')
    job_category = os.environ.get('JOB_CATEGORY', 'normal')
    execution_env = "batch"
    
    start_time = time.time()
    job_id = f"etl-{int(start_time)}"
    
    try:
        # DB接続
        db = DBConnector()
        
        # ETL処理実行
        records_processed = process_daily_summary(db)
        
        duration = time.time() - start_time
        
        # 成功ログ (JSON形式)
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_id": job_id,
            "job_type": job_type,
            "job_category": job_category,
            "execution_env": execution_env,
            "status": "SUCCEEDED",
            "duration": round(duration, 3),
            "records_processed": records_processed,
            "message": f"ETL job completed successfully. Processed {records_processed} records."
        }
        
        print(json.dumps(log_data))
        
        # ジョブ履歴記録
        record_job_history(db, job_type, "SUCCEEDED", records_processed, duration, None)
        
        return 0
        
    except Exception as e:
        duration = time.time() - start_time
        
        # エラーログ (JSON形式)
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "job_id": job_id,
            "job_type": job_type,
            "job_category": job_category,
            "execution_env": execution_env,
            "status": "FAILED",
            "duration": round(duration, 3),
            "error": str(e),
            "message": f"ETL job failed: {str(e)}"
        }
        
        print(json.dumps(log_data))
        
        # エラー履歴記録
        try:
            record_job_history(db, job_type, "FAILED", 0, duration, str(e))
        except:
            pass
        
        return 1


def process_daily_summary(db):
    """
    日次集計処理
    昨日の注文データを地域・商品別に集計
    """
    
    # 集計対象日 (昨日)
    target_date = (datetime.now() - timedelta(days=1)).date()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Extract & Transform
        # 昨日の注文データを地域・商品別に集計
        query = """
            SELECT
                order_date,
                region,
                product_id,
                COUNT(*) as total_orders,
                SUM(quantity) as total_quantity,
                SUM(total_amount) as total_amount
            FROM orders
            WHERE order_date = %s
            GROUP BY order_date, region, product_id
            ORDER BY region, product_id
        """
        
        cursor.execute(query, (target_date,))
        results = cursor.fetchall()
        
        # Load
        # daily_summary テーブルに保存 (既存データは更新)
        insert_query = """
            INSERT INTO daily_summary 
            (summary_date, region, product_id, total_orders, total_quantity, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (summary_date, region, product_id)
            DO UPDATE SET
                total_orders = EXCLUDED.total_orders,
                total_quantity = EXCLUDED.total_quantity,
                total_amount = EXCLUDED.total_amount,
                created_at = CURRENT_TIMESTAMP
        """
        
        for row in results:
            cursor.execute(insert_query, row)
        
        conn.commit()
        cursor.close()
        
        return len(results)


def record_job_history(db, job_name, status, records_processed, duration, error_message):
    """ジョブ実行履歴をDBに記録"""
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        query = """
            INSERT INTO etl_job_history
            (job_name, execution_date, start_time, end_time, status, records_processed, error_message)
            VALUES (%s, CURRENT_DATE, CURRENT_TIMESTAMP - INTERVAL '%s seconds', CURRENT_TIMESTAMP, %s, %s, %s)
        """
        
        cursor.execute(query, (job_name, duration, status, records_processed, error_message))
        conn.commit()
        cursor.close()


if __name__ == "__main__":
    exit(main())
