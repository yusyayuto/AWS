# ベースイメージ
FROM python:3.12-slim

# 作業ディレクトリ
WORKDIR /app

# スクリプトをコピー
COPY batch_job.py .

# 実行
CMD ["python", "-u", "batch_job.py"]
