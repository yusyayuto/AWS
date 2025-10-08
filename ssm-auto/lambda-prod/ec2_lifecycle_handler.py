# ec2_lifecycle_handler.py
# 停止・再起動・終了（CloudTrail経由）を1本で処理して
# SSM Automation を起動する最小コード
#
# 事前前提：
# - EventBridge ルールは CloudTrail 管理イベント（Stop/Reboot/Terminate）
# - Input Transformer で { "instanceId": "<iid>", "id": "<eid>" } を渡す
# - EC2 インスタンスに Key=RelatedAlarm（可変）で複合アラーム名のタグを付与
#
# 必要な環境変数（Lambdaの設定で指定）:
#   AUTOMATION_DOC              例: stg-sgn-pf-az-failure-recovery
#   PARAM_KEY_INSTANCE_ID       例: UnhealthyInstanceId
#   PARAM_KEY_ALARM_NAME        例: AlarmName
#   TAG_KEY                     例: RelatedAlarm  （省略時は RelatedAlarm）

import json
import os
import boto3

ssm = boto3.client("ssm")
ec2 = boto3.client("ec2")

DOC     = os.environ["AUTOMATION_DOC"]
P_IID   = os.environ["PARAM_KEY_INSTANCE_ID"]      # e.g., UnhealthyInstanceId
P_ALM   = os.environ["PARAM_KEY_ALARM_NAME"]       # e.g., AlarmName
TAG_KEY = os.environ.get("TAG_KEY", "RelatedAlarm")

def _get_alarm_name_from_instance_tag(instance_id: str) -> str | None:
    """EC2タグから複合アラーム名（TAG_KEYの値）を取り出す。"""
    resp = ec2.describe_tags(
        Filters=[
            {"Name": "resource-id", "Values": [instance_id]},
            {"Name": "key", "Values": [TAG_KEY]},
        ]
    )
    tags = resp.get("Tags", [])
    return tags[0]["Value"] if tags else None

def lambda_handler_lifecycle(event, context):
    # EventBridge(CloudTrail) の Input Transformer で渡された値を前提に最小化
    # 例: {"instanceId":"i-0123456789abcdef0","id":"abcd-1234-..."}
    print("### Raw Event ###")
    print(json.dumps(event, ensure_ascii=False))

    iid = event.get("instanceId")
    if not iid:
        # フォールバック（Input Transformer未設定時の保険：CloudTrailの素JSONを直読）
        iid = (
            event.get("detail", {})
                 .get("requestParameters", {})
                 .get("instancesSet", {})
                 .get("items", [{}])[0].get("instanceId")
        )

    if not iid:
        return {"status": "error", "reason": "missing instanceId in event"}

    alarm_name = _get_alarm_name_from_instance_tag(iid)
    if not alarm_name:
        return {"status": "skipped", "instanceId": iid, "reason": f"tag '{TAG_KEY}' not found"}

    # 冪等性：イベントID + インスタンスID（64文字上限に切り詰め）
    token_src = str(event.get("id") or context.aws_request_id)
    client_token = (f"{token_src}-{iid}")[:64]

    resp = ssm.start_automation_execution(
        DocumentName=DOC,
        Parameters={P_IID: [iid], P_ALM: [alarm_name]},
        ClientToken=client_token
    )
    return {
        "status": "started",
        "instanceId": iid,
        "alarmName": alarm_name,
        "executionId": resp.get("AutomationExecutionId")
    }

# —— 参考：Failover実行中の二重起動を避けたい場合は、以下を追加（任意）——
# 1) SSM Automation の最初/最後で EC2 に Key=FailoverInProgress,Value=true を付与/削除
# 2) この関数の冒頭で該当タグを検査し、付いていたら即 return する
#
# def _in_progress(instance_id: str) -> bool:
#     r = ec2.describe_tags(Filters=[
#         {"Name": "resource-id", "Values": [instance_id]},
#         {"Name": "key", "Values": ["FailoverInProgress"]},
#         {"Name": "value", "Values": ["true"]},
#     ])
#     return bool(r.get("Tags"))
#
# if _in_progress(iid): return {"status":"skipped","reason":"failover in progress","instanceId":iid}
