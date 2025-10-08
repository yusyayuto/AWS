# stop_handler.py（最小修正）
import json, boto3, os

ssm = boto3.client("ssm")
ec2 = boto3.client("ec2")

DOC   = os.environ["AUTOMATION_DOC"]
P_IID = os.environ["PARAM_KEY_INSTANCE_ID"]     # 例: UnhealthyInstanceId
P_ALM = os.environ["PARAM_KEY_ALARM_NAME"]      # 例: AlarmName
TAG_KEY = os.environ.get("TAG_KEY", "RelatedAlarm")  # ←あなたの運用に合わせて修正

def lambda_handler_stop(event, context):
    print("### Raw Event ###"); print(json.dumps(event, ensure_ascii=False))

    # 1) instanceId を複数の経路で探す（両対応）
    iid = (
        event.get("instanceId") or                                  # 入力トランスフォーマで整形済みのとき
        event.get("detail", {}).get("instance-id") or               # EC2 state-change 通知
        (event.get("detail", {})
              .get("requestParameters", {})
              .get("instancesSet", {})
              .get("items", [{}])[0].get("instanceId"))            # CloudTrail: RebootInstances
    )
    if not iid:
        return {"status": "error", "reason": "missing instance-id"}

    # 2) タグから複合アラーム名を取得
    res = ec2.describe_tags(
        Filters=[
            {"Name": "resource-id", "Values": [iid]},
            {"Name": "key", "Values": [TAG_KEY]},
        ]
    )
    tags = res.get("Tags", [])
    if not tags:
        return {"status": "skipped", "reason": f"tag '{TAG_KEY}' not found", "instanceId": iid}
    alarm_name = tags[0]["Value"]

    # 3) SSM Automation 起動（冪等性: event.id があれば使う）
    resp = ssm.start_automation_execution(
        DocumentName=DOC,
        Parameters={P_IID: [iid], P_ALM: [alarm_name]},
        ClientToken=str(event.get("id") or context.aws_request_id)[:64]
    )
    return {"status": "started", "instanceId": iid, "alarmName": alarm_name,
            "executionId": resp.get("AutomationExecutionId")}
