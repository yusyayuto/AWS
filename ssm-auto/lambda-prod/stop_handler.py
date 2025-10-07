import os, json, boto3

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")

AUTOMATION_DOC = os.environ["AUTOMATION_DOC"]
PARAM_IID      = os.environ.get("PARAM_KEY_INSTANCE_ID", "UnhealthyInstanceId")
PARAM_RELALM   = os.environ.get("PARAM_KEY_RELATED_ALARM", "RelatedAlarm")
TAG_KEY        = os.environ.get("TAG_KEY_RELATED_ALARM", "RelatedAlarm")
CHANGE_CAL_ARN = os.environ.get("CHANGE_CAL_ARN")   # ← Change Calendar ARN

def get_related_alarm_value(instance_id: str) -> str | None:
    res = ec2.describe_tags(
        Filters=[
            {"Name":"resource-id","Values":[instance_id]},
            {"Name":"key","Values":[TAG_KEY]}
        ]
    )
    return res["Tags"][0]["Value"] if res.get("Tags") else None

def is_calendar_open() -> bool:
    """Change Calendarのステータスを確認（OPENならTrue）"""
    if not CHANGE_CAL_ARN:
        return True  # カレンダー指定なしなら常に許可
    r = ssm.get_calendar_state(CalendarNames=[CHANGE_CAL_ARN])
    return r["State"] == "OPEN"

def lambda_handler_stop(event, _):
    iid = (event.get("instanceId")
           or event.get("detail", {}).get("instance-id"))
    if not iid:
        raise ValueError("instanceId not found in event")

    if not is_calendar_open():
        return {"status":"suppressed_by_change_calendar", "instanceId": iid}

    related = get_related_alarm_value(iid)
    if not related:
        return {"status":"skipped_no_related_alarm_tag", "instanceId": iid}

    params = {
        PARAM_IID:   [iid],
        PARAM_RELALM:[related]
    }

    resp = ssm.start_automation_execution(
        DocumentName=AUTOMATION_DOC,
        Parameters=params,
        ClientToken=event.get("id") or iid
    )

    return {
        "status": "started",
        "instanceId": iid,
        "relatedAlarm": related,
        "executionId": resp["AutomationExecutionId"]
    }
