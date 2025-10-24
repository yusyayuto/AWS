追加分はこれだけで足りる。差分→そのままコピペ可。

1) 追記する環境変数
	•	TAG_KEY = FailoverGroup（グループ化タグのキー）
	•	DEDUP_TABLE = ec2-events-dedup
	•	DEDUP_TTL_SEC = 900

2) 追記するIAM
	•	dynamodb:PutItem を ec2-events-dedup テーブルに許可
（既存のCW/SSM/Logs許可は流用）

3) 追記するコード（alarm_handler.py）

以下を既存にマージ。関数名は衝突しない。

# === 追加 import ===
import time
from botocore.exceptions import ClientError

# === 追加 クライアント/テーブル ===
ddb = boto3.resource("dynamodb").Table(os.environ["DEDUP_TABLE"])

# === 追加 環境変数 ===
TAG_KEY        = os.environ["TAG_KEY"]                 # 例: FailoverGroup
DEDUP_TTL_SEC  = int(os.environ.get("DEDUP_TTL_SEC","900"))

# === 追加: グループタグ取得 ===
def get_group_from_instance(iid: str) -> str | None:
    r = ec2.describe_instances(InstanceIds=[iid])
    inst = r["Reservations"][0]["Instances"][0]
    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
    return tags.get(TAG_KEY)

# === 追加: DynamoDBロック ===
def acquire_lock(key: str) -> bool:
    now = int(time.time())
    try:
        ddb.put_item(
            Item={"k": key, "ttl": now + DEDUP_TTL_SEC, "ts": now},
            ConditionExpression="attribute_not_exists(k)"
        )
        return True
    except ClientError:
        return False

4) 既存ハンドラへの組み込みポイント

lambda_handler_alarm の「SSM 起動」の直前で以下を挿入。
また、インスタンスID取得後にグループタグを取得する。

def lambda_handler_alarm(event, _context):
    # ...（既存のALARM判定や子アラーム解析はそのまま）

    child_name, iid = get_child_alarm_and_instance_id_from_composite(event)
    composite_name  = event["detail"]["alarmName"]

    # === 追加: グループタグ取得 ===
    group = get_group_from_instance(iid)
    if not group:
        return {"status": "ignored_no_group", "instanceId": iid, "alarm": composite_name}

    # === 追加: DynamoDBで排他（グループ単位の一回のみ）===
    if not acquire_lock(group):
        return {"status": "skipped_dedup", "group": group, "instanceId": iid, "alarm": composite_name}

    # === 既存: SSM 起動（必要ならGroupも渡す）===
    params = {
        PARAM_IID:         [iid],
        PARAM_RELALM_NAME: [composite_name],
        # 任意: ランブックで使うならグループも渡す
        "Group":           [group]
    }
    resp = ssm.start_automation_execution(
        DocumentName=AUTOMATION_DOC,
        Parameters=params,
        ClientToken=event.get("id")  # 既存の冪等トークン
    )
    return {
        "status": "started",
        "instanceId": iid,
        "group": group,
        "childAlarm": child_name,
        "composite": composite_name,
        "executionId": resp.get("AutomationExecutionId")
    }

5) 注意点
	•	TTLはオートメーション想定時間+余裕に合わせる。短すぎると再実行、長すぎると必要な再起動もブロック。初期値900秒で開始、実測で調整。
	•	キーはタグ値。同じグループの別EC2でも一度きりにしたい要件を満たす。インスタンス単位にしたい場合は key = f"{group}:{iid}" に変更。
	•	タグ未設定は即スキップしログへ。運用でタグの付与を徹底。
	•	例外処理は最小化。ConditionalCheckFailed は exceptでまとめてFalse返しで十分（詳細な内訳が要るならコードで分岐）。

これでLambdaBにも重複防止が入る。
