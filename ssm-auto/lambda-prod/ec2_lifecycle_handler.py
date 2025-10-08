# ec2_lifecycle_handler.py（最小）
import json, boto3, os
ssm=boto3.client("ssm"); ec2=boto3.client("ec2")

DOC=os.environ["AUTOMATION_DOC"]
P_IID=os.environ["PARAM_KEY_INSTANCE_ID"]
P_ALM=os.environ["PARAM_KEY_ALARM_NAME"]
TAG_KEY=os.environ.get("TAG_KEY","RelatedAlarm")

def lambda_handler_lifecycle(event, context):
    iid = event.get("instanceId")
    if not iid:
        return {"status":"error","reason":"missing instanceId"}

    r = ec2.describe_tags(Filters=[
        {"Name":"resource-id","Values":[iid]},
        {"Name":"key","Values":[TAG_KEY]}
    ])
    tags = r.get("Tags",[])
    if not tags:
        return {"status":"skipped","reason":f"tag '{TAG_KEY}' not found","instanceId":iid}

    alarm = tags[0]["Value"]
    token = f"{str(event.get('id') or context.aws_request_id)}-{iid}"[:64]

    resp = ssm.start_automation_execution(
        DocumentName=DOC,
        Parameters={P_IID:[iid], P_ALM:[alarm]},
        ClientToken=token
    )
    return {"status":"started","iid":iid,"alarmName":alarm,"execId":resp.get("AutomationExecutionId")}
