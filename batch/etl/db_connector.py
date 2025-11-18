"""
RDS PostgreSQL 接続管理モジュール
"""
import os
import json
import boto3
import psycopg2
from contextlib import contextmanager


class DBConnector:
    """RDS接続管理クラス"""
    
    def __init__(self):
        """Secrets Manager から認証情報を取得して初期化"""
        self.credentials = self._get_credentials_from_secrets_manager()
        
        self.host = self.credentials['host']
        self.database = self.credentials.get('dbname', 'batch_etl')
        self.user = self.credentials['username']
        self.password = self.credentials['password']
        self.port = int(self.credentials.get('port', 5432))
    
    def _get_credentials_from_secrets_manager(self):
        """Secrets Manager から認証情報を取得"""
        secret_arn = os.environ.get('DB_SECRET_ARN')
        
        if not secret_arn:
            raise ValueError("環境変数 DB_SECRET_ARN が設定されていません")
        
        try:
            client = boto3.client('secretsmanager', region_name='ap-northeast-1')
            response = client.get_secret_value(SecretId=secret_arn)
            return json.loads(response['SecretString'])
        except Exception as e:
            raise Exception(f"Secrets Manager からの認証情報取得に失敗: {str(e)}")
    
    @contextmanager
    def get_connection(self):
        """
        DB コネクションを取得 (with文で使用)
        
        使用例:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM orders")
        """
        conn = None
        try:
            conn = psycopg2.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password,
                port=self.port,
                connect_timeout=10
            )
            yield conn
        except psycopg2.OperationalError as e:
            if conn:
                conn.rollback()
            raise Exception(f"DB接続エラー: {str(e)}")
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
