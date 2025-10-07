# stop_handler.py
import os
import boto3

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")

# === 環境変数（差し替え） ===
AUTOMATION_DOC    = os.environ["AUTOMATION_DOC"]
PARAM_IID         = os.environ.get("PARAM_KEY_INSTANCE_ID", "InstanceId")
PARAM_RELALM_NAME = os.environ.get("PARAM_KEY_RELATED_ALARM_NAME", "RelatedAlarmName")
# EC2 側のタグキー（値が複合アラーム名）
INSTANCE_TAG_KEY  = os.environ.get("INSTANCE_TAG_KEY_RELATED_ALARM_NAME", "RelatedAlarmName")
CHANGE_CAL_ARN    = os.environ.get("CHANGE_CAL_ARN")

def is_calendar_open() -> bool:
    if not CHANGE_CAL_ARN:
        return True
    r = ssm.get_calendar_state(CalendarNames=[CHANGE_CAL_ARN])
    return r["State"] == "OPEN"

def get_related_alarm_name_from_instance(instance_id: str) -> str | None:
    """EC2 のタグから RelatedAlarmName の値を取得"""
    res = ec2.describe_tags(
        Filters=[
            {"Name": "resource-id", "Values": [instance_id]},
            {"Name": "key",         "Values": [INSTANCE_TAG_KEY]}
        ]
    )
    return res["Tags"][0]["Value"] if res.get("Tags") else None

def lambda_handler_stop(event, _context):
    # InputTransformer で {"instanceId": "<id>"} を渡すのが楽
    iid = (event.get("instanceId")
           or event.get("detail", {}).get("instance-id"))
    if not iid:
        raise ValueError("instanceId not found in event")

    # カレンダー CLOSED なら抑止
    if not is_calendar_open():
        return {"status": "suppressed_by_change_calendar", "instanceId": iid}

    related_alarm_name = get_related_alarm_name_from_instance(iid)
    if not related_alarm_name:
        return {"status": "skipped_no_related_alarm_name_tag", "instanceId": iid}

    params = {
        PARAM_IID:         [iid],
        PARAM_RELALM_NAME: [related_alarm_name],
    }
    resp = ssm.start_automation_execution(
        DocumentName=AUTOMATION_DOC,
        Parameters=params,
        ClientToken=event.get("id") or iid
    )
    return {
        "status": "started",
        "instanceId": iid,
        "relatedAlarmName": related_alarm_name,
        "executionId": resp["AutomationExecutionId"]
    }
