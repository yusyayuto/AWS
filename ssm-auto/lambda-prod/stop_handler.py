import boto3, os

ssm = boto3.client("ssm")
ec2 = boto3.client("ec2")

DOC   = os.environ["AUTOMATION_DOC"]          # SSMドキュメント名
P_IID = os.environ["PARAM_KEY_INSTANCE_ID"]   # 例: UnhealthyInstanceId
P_ALM = os.environ["PARAM_KEY_ALARM_NAME"]    # 例: AlarmName
TAG_KEY = "RelatedAlarmName"

def lambda_handler(event, _):
    iid = event.get("instanceId") or event.get("detail", {}).get("instance-id")
    if not iid:
        return {"status": "error", "reason": "no instance id"}

    # タグから複合アラーム名取得
    r = ec2.describe_tags(
        Filters=[
            {"Name": "resource-id", "Values": [iid]},
            {"Name": "key", "Values": [TAG_KEY]}
        ]
    )
    if not r["Tags"]:
        return {"status": "skip", "reason": "no tag", "instanceId": iid}

    alarm_name = r["Tags"][0]["Value"]

    # SSMオートメーション起動
    resp = ssm.start_automation_execution(
        DocumentName=DOC,
        Parameters={P_IID: [iid], P_ALM: [alarm_name]},
        ClientToken=event.get("id", iid)
    )

    return {"status": "started", "instanceId": iid, "alarmName": alarm_name}
