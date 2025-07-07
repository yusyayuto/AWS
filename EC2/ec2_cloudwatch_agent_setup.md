構成概要
EC2 OS: Amazon Linux 2 / Amazon Linux 2023

ログファイル例: /var/log/secure

ロググループ: aaaaa

IAM ロール: CloudWatchAgentServerPolicy をアタッチ

エージェント: CloudWatch Agent

前提条件
・EC2 に CloudWatchAgentServerPolicy がアタッチされた IAM ロールが設定されている
・CloudWatch Logs 側でロググループが作成されている（自動作成でも可）

手順
・CloudWatch Agent インストール
sudo yum install -y amazon-cloudwatch-agent

確認
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status

正常なら stopped が出ます。

ログファイルの存在確認

sudo ls -l /var/log/secure
実在するログファイルを対象に選びます。

3設定ファイル作成
bash
コピーする
編集する
sudo vi /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
例：

json
コピーする
編集する
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/secure",
            "log_group_name": "tkkk-pj-loggroup-sasaki",
            "log_stream_name": "{instance_id}/secure",
            "timestamp_format": "%b %d %H:%M:%S"
          }
        ]
      }
    }
  }
}
💡 vi の保存: Esc → :wq → Enter

4️⃣ エージェントの起動
bash
コピーする
編集する
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
-m ec2 \
-a fetch-config \
-c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
-s
5️⃣ 動作確認
CloudWatch Logs の該当ロググループでストリームが生成され、ログが流れていることを確認します。
