FROM python:3.12-slim

# メタデータ
LABEL maintainer="ssk"
LABEL description="ETL Pipeline for AWS Batch - PostgreSQL version"

# 作業ディレクトリ
WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY etl_job.py .
COPY db_connector.py .

# 実行
CMD ["python", "-u", "etl_job.py"]
