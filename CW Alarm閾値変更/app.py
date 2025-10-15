import os, json, urllib.parse, time
import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
PARAM_NAME = os.environ.get("PARAM_NAME")  # 〈パラメータストア名〉
FORCE_ONE = os.environ.get("FORCE_ONE_DATAPOINT", "false").lower() == "true"

cw  = boto3.client("cloudwatch", region_name=REGION)
ssm = boto3.client("ssm",        region_name=REGION)

# ---- しきい値変換ロジック ----
def decide_new_threshold(a):
    # 単一メトリクス以外は対象外（Metrics フィールドを持つ＝メトリックマスは除外）
    if "MetricName" not in a or a.get("Metrics"):
        return None

    m = (a["MetricName"] or "").lower()
    comp = a["ComparisonOperator"]
    thr  = a["Threshold"]

    # 1 LogicalDisk % Free Space <=10 → <=99.5
    if "logicaldisk" in m and "% free space" in m and comp.endswith("LessThanOrEqualToThreshold") and float(thr) == 10.0:
        return {"ComparisonOperator": comp, "Threshold": 99.5}

    # 2 Memory Available Bytes <= 1717986918 → <= 1e12
    if "memory" in m and "available" in m and "bytes" in m and comp.endswith("LessThanOrEqualToThreshold") and int(thr) == 1717986918:
        return {"ComparisonOperator": comp, "Threshold": 1_000_000_000_000}

    # 3 Processor % Processor Time > 90 → > 1
    if "processor" in m and "% processor time" in m and comp.endswith("GreaterThanThreshold") and float(thr) == 90.0:
        return {"ComparisonOperator": comp, "Threshold": 1.0}

    # 4/5 StatusCheckFailed_* >= 1 → >= 0
    if a["MetricName"] in ("StatusCheckFailed", "StatusCheckFailed_Instance", "StatusCheckFailed_System") \
       and comp.endswith("GreaterThanOrEqualToThreshold") and float(thr) == 1.0:
        return {"ComparisonOperator": comp, "Threshold": 0.0}

    # 6 Windows_service_status < 1 → < 2
    if "windows" in m and "service" in m and "status" in m and comp.endswith("LessThanThreshold") and float(thr) == 1.0:
        return {"ComparisonOperator": comp, "Threshold": 2.0}

    return None

# ---- Parameter Store にアラーム単位で保存（サイズ対策のため分割） ----
def param_key_for_alarm(alarm_name):
    # 〈パラメータストア名〉/encodedAlarmName
    encoded = urllib.parse.quote(alarm_name, safe='')
    return f"{PARAM_NAME}/{encoded}"

def save_snapshot(alarm_name, payload):
    ssm.put_parameter(
        Name=param_key_for_alarm(alarm_name),
        Type="String",
        Overwrite=True,
        Value=json.dumps(payload, ensure_ascii=False)
    )

def load_snapshot(alarm_name):
    try:
        r = ssm.get_parameter(Name=param_key_for_alarm(alarm_name))
        return json.loads(r["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        return None

# ---- put_metric_alarm 用の引数を現在定義から構築 ----
def build_put_args_from(a):
    args = {
        "AlarmName": a["AlarmName"],
        "ComparisonOperator": a["ComparisonOperator"],
        "Threshold": a["Threshold"],
        "EvaluationPeriods": a.get("EvaluationPeriods"),
        "DatapointsToAlarm": a.get("DatapointsToAlarm"),
        "ActionsEnabled": a.get("ActionsEnabled", True),
        "AlarmActions": a.get("AlarmActions", []),
        "OKActions": a.get("OKActions", []),
        "InsufficientDataActions": a.get("InsufficientDataActions", []),
        "MetricName": a["MetricName"],
        "Namespace": a["Namespace"],
        "Statistic": a.get("Statistic"),
        "ExtendedStatistic": a.get("ExtendedStatistic"),
        "Period": a["Period"],
        "Unit": a.get("Unit"),
        "Dimensions": a.get("Dimensions", []),
        "TreatMissingData": a.get("TreatMissingData", "missing"),
        "Tags": a.get("Tags", [])
    }
    # None を除去（boto要件）
    return {k:v for k,v in args.items() if v is not None}

def update_one(a):
    rule = decide_new_threshold(a)
    if not rule:
        return None

    before = build_put_args_from(a)
    after  = dict(before)
    after["ComparisonOperator"] = rule["ComparisonOperator"]
    after["Threshold"] = rule["Threshold"]

    if FORCE_ONE:
        after["EvaluationPeriods"] = 1
        after["DatapointsToAlarm"] = 1

    # put
    cw.put_metric_alarm(**after)

    # 保存形式: before/after/rollback を保持（rollback=beforeと同）
    save_snapshot(a["AlarmName"], {
        "before": before,
        "after": after,
        "rollback": before
    })
    return {"name": a["AlarmName"], "change": {"from": before["Threshold"], "to": after["Threshold"]}}

def rollback_one(name):
    snap = load_snapshot(name)
    if not snap:
        return {"name": name, "status": "skip(no-snapshot)"}
    rb = snap["rollback"]
    cw.put_metric_alarm(**rb)
    return {"name": name, "status": "reverted"}

def describe_all_metric_alarms():
    paginator = cw.get_paginator("describe_alarms")
    for page in paginator.paginate():
        for a in page.get("MetricAlarms", []):
            # 複合アラーム除外
            if a.get("Metrics"): 
                continue
            yield a

def handler(event, context):
    action = (event or {}).get("action", "update")
    updated = []
    reverted = []

    if action == "update":
        for a in describe_all_metric_alarms():
            r = update_one(a)
            if r:
                updated.append(r)
            time.sleep(0.1)  # 軽いスロットリング対策
        return {"result": "updated", "count": len(updated), "items": updated}

    elif action == "rollback":
        # 直近スナップショット対象はパラメータ一覧が必要だが、キー列挙APIなしのため
        # 実在アラーム名に対し存在するスナップショットのみ復元
        names = [a["AlarmName"] for a in describe_all_metric_alarms()]
        for n in names:
            r = rollback_one(n)
            if r:
                reverted.append(r)
            time.sleep(0.05)
        return {"result": "rolled_back", "count": len(reverted), "items": reverted}

    else:
        return {"error": "unknown action"}
