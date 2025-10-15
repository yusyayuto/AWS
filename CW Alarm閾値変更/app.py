import os, json, urllib.parse, time
import boto3

REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
PARAM_NAME = os.environ.get("PARAM_NAME")  # 〈パラメータストア名〉
FORCE_ONE = os.environ.get("FORCE_ONE_DATAPOINT", "false").lower() == "true"

cw  = boto3.client("cloudwatch", region_name=REGION)
ssm = boto3.client("ssm",        region_name=REGION)

# ---------- しきい値変換ロジック ----------
def decide_new_threshold(a):
    # 単一メトリクス以外は対象外（Metricsがある＝メトリックマス/複合想定）
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

# ---------- Parameter Store（アラーム単位で保存） ----------
def param_key_for_alarm(alarm_name):
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

# ---------- put_metric_alarm 用引数構築（全ディメンション含む） ----------
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
    return {k:v for k,v in args.items() if v is not None}

def describe_all_metric_alarms():
    paginator = cw.get_paginator("describe_alarms")
    for page in paginator.paginate():
        for a in page.get("MetricAlarms", []):
            if a.get("Metrics"):
                continue
            yield a

def update_one(a, dry_run=False):
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

    if not dry_run:
        cw.put_metric_alarm(**after)
        save_snapshot(a["AlarmName"], {"before": before, "after": after, "rollback": before})

    return {"name": a["AlarmName"], "from": before["Threshold"], "to": after["Threshold"], "dry_run": dry_run}

def rollback_one(name, dry_run=False):
    snap = load_snapshot(name)
    if not snap:
        return {"name": name, "status": "skip(no-snapshot)", "dry_run": dry_run}
    rb = snap["rollback"]
    if not dry_run:
        cw.put_metric_alarm(**rb)
    return {"name": name, "status": "reverted", "dry_run": dry_run}

def handler(event, context):
    action = (event or {}).get("action", "update")
    name_prefix = (event or {}).get("name_prefix")
    dry_run = bool((event or {}).get("dry_run", False))

    def name_ok(n): return (not name_prefix) or n.startswith(name_prefix)

    results = []
    if action == "update":
        for a in describe_all_metric_alarms():
            if not name_ok(a["AlarmName"]):
                continue
            r = update_one(a, dry_run=dry_run)
            if r:
                results.append(r)
            time.sleep(0.1)
        return {"result": "updated", "count": len(results), "items": results}

    if action == "rollback":
        names = [a["AlarmName"] for a in describe_all_metric_alarms() if name_ok(a["AlarmName"])]
        for n in names:
            r = rollback_one(n, dry_run=dry_run)
            results.append(r)
            time.sleep(0.05)
        return {"result": "rolled_back", "count": len(results), "items": results}

    return {"error": "unknown action"}
