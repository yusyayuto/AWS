# stop_handler.py
import json, boto3, os

ssm = boto3.client("ssm")
ec2 = boto3.client("ec2")

DOC  = os.environ["AUTOMATION_DOC"]            # SSM Automation ドキュメント名
P_IID = os.environ["PARAM_KEY_INSTANCE_ID"]    # 例: UnhealthyInstanceId
P_ALM = os.environ["PARAM_KEY_ALARM_NAME"]     # 例: AlarmName
TAG_KEY = os.environ.get("TAG_KEY", "RelatedAlarmName")  # デフォルトキー

def lambda_handler_stop(event, context):
    print("### Raw Event ###")
    print(json.dumps(event, ensure_ascii=False))

    # --- EC2 停止イベントから instance-id を取得 ---
    iid = event.get("detail", {}).get("instance-id")
    if not iid:
        print("Error: instance-id not found in event")
        return {"status": "error", "reason": "missing instance-id"}

    # --- EC2インスタンスのタグを取得 ---
    try:
        res = ec2.describe_tags(
            Filters=[
                {"Name": "resource-id", "Values": [iid]},
                {"Name": "key", "Values": [TAG_KEY]},
            ]
        )
        tags = res.get("Tags", [])
        if not tags:
            print(f"No tag '{TAG_KEY}' found for instance {iid}")
            return {"status": "skipped", "reason": f"tag '{TAG_KEY}' not found"}

        alarm_name = tags[0]["Value"]
        print(f"Found alarm tag: {TAG_KEY} = {alarm_name}")

    except Exception as e:
        print(f"Tag retrieval error: {e}")
        return {"status": "error", "reason": str(e)}

    # --- SSM Automation 実行 ---
    try:
        resp = ssm.start_automation_execution(
            DocumentName=DOC,
            Parameters={
                P_IID: [iid],
                P_ALM: [alarm_name]
            },
            ClientToken=event.get("id", iid)
        )

        execution_id = resp.get("AutomationExecutionId")
        print(f"Started AutomationExecution: {execution_id}")

        return {
            "status": "started",
            "instanceId": iid,
            "alarmName": alarm_name,
            "executionId": execution_id
        }

    except Exception as e:
        print(f"SSM execution error: {e}")
        return {"status": "error", "reason": str(e)}
