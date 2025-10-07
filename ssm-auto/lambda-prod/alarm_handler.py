# alarm_handler.py
import os
import json
import boto3

cw  = boto3.client("cloudwatch")
ssm = boto3.client("ssm")

# === 環境変数（差し替え） ===
AUTOMATION_DOC    = os.environ["AUTOMATION_DOC"]                  # 例: Failover-Automation-Doc
PARAM_IID         = os.environ.get("PARAM_KEY_INSTANCE_ID", "InstanceId")
PARAM_RELALM_NAME = os.environ.get("PARAM_KEY_RELATED_ALARM_NAME", "RelatedAlarmName")
CHANGE_CAL_ARN    = os.environ.get("CHANGE_CAL_ARN")              # 例: arn:aws:ssm:ap-northeast-1:123...:document/BusinessHours

def is_calendar_open() -> bool:
    """SSM Change Calendar が OPEN なら True"""
    if not CHANGE_CAL_ARN:
        return True
    r = ssm.get_calendar_state(CalendarNames=[CHANGE_CAL_ARN])
    return r["State"] == "OPEN"

def get_child_alarm_and_instance_id_from_composite(event) -> tuple[str, str]:
    """複合アラームイベントから子アラーム名と InstanceId を1つ取得"""
    reason = json.loads(event["detail"]["state"]["reasonData"])
    if not reason.get("triggeringAlarms"):
        raise RuntimeError("No triggeringAlarms in reasonData")
    child_arn  = reason["triggeringAlarms"][0]["arn"]
    child_name = child_arn.split(":alarm:", 1)[1]

    r = cw.describe_alarms(AlarmNames=[child_name])
    if not r.get("MetricAlarms"):
        raise RuntimeError(f"No MetricAlarms found for child alarm: {child_name}")

    dims = r["MetricAlarms"][0].get("Dimensions", [])
    iid  = next((d["Value"] for d in dims if d.get("Name") == "InstanceId"), None)
    if not iid:
        raise RuntimeError(f"No InstanceId dimension in child alarm: {child_name}")
    return child_name, iid

def lambda_handler_alarm(event, _context):
    # ALARM 遷移以外は無視
    cur  = event["detail"]["state"]["value"]
    prev = event["detail"].get("previousState", {}).get("value")
    if not (cur == "ALARM" and prev != "ALARM"):
        return {"status": "ignored", "current": cur, "previous": prev}

    # カレンダー CLOSED なら抑止
    if not is_calendar_open():
        return {"status": "suppressed_by_change_calendar",
                "composite": event["detail"]["alarmName"]}

    # 子アラーム・InstanceId 抽出
    child_name, iid = get_child_alarm_and_instance_id_from_composite(event)

    # RelatedAlarmName は「複合アラーム名」をそのまま渡す
    composite_name = event["detail"]["alarmName"]

    # SSM 起動
    params = {
        PARAM_IID:         [iid],
        PARAM_RELALM_NAME: [composite_name],
    }
    resp = ssm.start_automation_execution(
        DocumentName=AUTOMATION_DOC,
        Parameters=params,
        ClientToken=event.get("id")  # 冪等性
    )
    return {
        "status": "started",
        "instanceId": iid,
        "childAlarm": child_name,
        "composite": composite_name,
        "executionId": resp.get("AutomationExecutionId")
    }
