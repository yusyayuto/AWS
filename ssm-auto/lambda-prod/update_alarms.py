# update_alarms.py
import os
import boto3

cw = boto3.client("cloudwatch")

# === 受け取りは SSM から（Payload で飛んでくる想定） ===
# {
#   "RelatedAlarmName": "Composite-xxx",
#   "OldInstanceId":    "i-old",
#   "NewInstanceId":    "i-new"
# }

TAG_KEY_FOR_ALARM = os.environ.get("ALARM_TAG_KEY", "RelatedAlarmName")

def list_alarms_by_tag_value(tag_value: str) -> list[str]:
    """タグ Key=RelatedAlarmName, Value=tag_value を持つアラーム名を列挙"""
    # CloudWatch リソースタグは ListTagsForResource で個別に引く必要があるため、
    # ここでは DescribeAlarms で全部一覧→フィルタ、が簡単（数が多いなら工夫）
    names = []
    paginator = cw.get_paginator("describe_alarms")
    for page in paginator.paginate():
        for a in page.get("MetricAlarms", []):
            arn = a.get("AlarmArn")
            if not arn:
                continue
            tags = cw.list_tags_for_resource(ResourceARN=arn).get("Tags", [])
            if any(t["Key"] == TAG_KEY_FOR_ALARM and t["Value"] == tag_value for t in tags):
                names.append(a["AlarmName"])
    return names

def update_alarm_instance_dimension(alarm_name: str, old_iid: str, new_iid: str) -> bool:
    """該当アラームの Dimensions.InstanceId = old → new に置換し PutMetricAlarm"""
    r = cw.describe_alarms(AlarmNames=[alarm_name])
    if not r.get("MetricAlarms"):
        return False
    alarm = r["MetricAlarms"][0]

    dims = alarm.get("Dimensions", [])
    changed = False
    for d in dims:
        if d.get("Name") == "InstanceId" and d.get("Value") == old_iid:
            d["Value"] = new_iid
            changed = True

    if not changed:
        return False  # 変更なし

    # PutMetricAlarm 用に必要フィールドを再構築
    put_args = {
        "AlarmName": alarm["AlarmName"],
        "ComparisonOperator": alarm["ComparisonOperator"],
        "EvaluationPeriods": alarm["EvaluationPeriods"],
        "MetricName": alarm["MetricName"],
        "Namespace": alarm["Namespace"],
        "Period": alarm["Period"],
        "Statistic": alarm.get("Statistic"),
        "ExtendedStatistic": alarm.get("ExtendedStatistic"),
        "Threshold": alarm.get("Threshold"),
        "TreatMissingData": alarm.get("TreatMissingData", "missing"),
        "ActionsEnabled": alarm.get("ActionsEnabled", True),
        "AlarmActions": alarm.get("AlarmActions", []),
        "OKActions": alarm.get("OKActions", []),
        "InsufficientDataActions": alarm.get("InsufficientDataActions", []),
        "Dimensions": dims
    }
    # optional の None を削る
    put_args = {k:v for k,v in put_args.items() if v is not None}
    cw.put_metric_alarm(**put_args)
    return True

def lambda_handler_update_alarms(event, _context):
    related = event["RelatedAlarmName"]
    old_iid  = event["OldInstanceId"]
    new_iid  = event["NewInstanceId"]

    names = list_alarms_by_tag_value(related)
    updated = []
    skipped = []

    for name in names:
        if update_alarm_instance_dimension(name, old_iid, new_iid):
            updated.append(name)
        else:
            skipped.append(name)

    return {
        "status": "done",
        "relatedAlarmName": related,
        "updated": updated,
        "skipped": skipped
    }
