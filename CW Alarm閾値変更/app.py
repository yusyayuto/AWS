import os, json, urllib.parse, time
import boto3

# === 環境変数 ===
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
FORCE_ONE = os.environ.get("FORCE_ONE_DATAPOINT", "false").lower() == "true"
S3_BUCKET = os.environ.get("SNAPSHOT_S3_BUCKET")

cw = boto3.client("cloudwatch", region_name=REGION)
s3 = boto3.client("s3")

# === 保存先キー ===
def _s3_key(alarm_name: str) -> str:
    enc = urllib.parse.quote(alarm_name, safe="")
    return f"cw-alarm-backup/{REGION}/{enc}.json"

def snapshot_merge_write(alarm_name: str, label: str, alarm_obj: dict):
    key = _s3_key(alarm_name)
    try:
        cur = s3.get_object(Bucket=S3_BUCKET, Key=key)
        data = json.loads(cur["Body"].read().decode("utf-8"))
    except Exception:
        data = {}
    data[label] = alarm_obj
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=body, ContentType="application/json")

# === 引数生成（説明を含む完全形） ===
def build_put_args_from(a: dict) -> dict:
    stat, estat = a.get("Statistic"), a.get("ExtendedStatistic")
    if stat and estat:
        estat = None
    args = {
        "AlarmName": a["AlarmName"],
        "AlarmDescription": a.get("AlarmDescription"),
        "ActionsEnabled": a.get("ActionsEnabled", True),
        "OKActions": a.get("OKActions", []),
        "AlarmActions": a.get("AlarmActions", []),
        "InsufficientDataActions": a.get("InsufficientDataActions", []),
        "MetricName": a["MetricName"],
        "Namespace": a["Namespace"],
        "Statistic": stat,
        "ExtendedStatistic": estat,
        "Dimensions": a.get("Dimensions", []),
        "Period": a["Period"],
        "Unit": a.get("Unit"),
        "EvaluationPeriods": a.get("EvaluationPeriods"),
        "DatapointsToAlarm": a.get("DatapointsToAlarm"),
        "Threshold": a["Threshold"],
        "ComparisonOperator": a["ComparisonOperator"],
        "TreatMissingData": a.get("TreatMissingData", "missing"),
    }
    return {k: v for k, v in args.items() if v is not None and (not isinstance(v, str) or v.strip() != "")}

# === ルール定義 ===
UPDATE_RULES = [
    {"match": ("LessThanOrEqualToThreshold", 10.0), "set": ("LessThanOrEqualToThreshold", 99.5),
     "contains": ["logicaldisk", "% free space"]},
    {"match": ("LessThanOrEqualToThreshold", 1717986918.0), "set": ("LessThanOrEqualToThreshold", 1_000_000_000_000.0),
     "contains": ["memory", "available", "bytes"]},
    {"match": ("GreaterThanThreshold", 90.0), "set": ("GreaterThanThreshold", 1.0),
     "contains": ["processor", "% processor time"]},
    {"match": ("GreaterThanOrEqualToThreshold", 1.0), "set": ("GreaterThanOrEqualToThreshold", 0.0),
     "exact": "StatusCheckFailed_Instance"},
    {"match": ("GreaterThanOrEqualToThreshold", 1.0), "set": ("GreaterThanOrEqualToThreshold", 0.0),
     "exact": "StatusCheckFailed_System"},
    {"match": ("LessThanThreshold", 1.0), "set": ("LessThanThreshold", 2.0),
     "contains": ["windows", "service", "status"]},
]

INVERT_RULES = [
    {"match": ("LessThanOrEqualToThreshold", 99.5), "set": ("LessThanOrEqualToThreshold", 10.0),
     "contains": ["logicaldisk", "% free space"]},
    {"match": ("LessThanOrEqualToThreshold", 1_000_000_000_000.0), "set": ("LessThanOrEqualToThreshold", 1717986918.0),
     "contains": ["memory", "available", "bytes"]},
    {"match": ("GreaterThanThreshold", 1.0), "set": ("GreaterThanThreshold", 90.0),
     "contains": ["processor", "% processor time"]},
    {"match": ("GreaterThanOrEqualToThreshold", 0.0), "set": ("GreaterThanOrEqualToThreshold", 1.0),
     "exact": "StatusCheckFailed_Instance"},
    {"match": ("GreaterThanOrEqualToThreshold", 0.0), "set": ("GreaterThanOrEqualToThreshold", 1.0),
     "exact": "StatusCheckFailed_System"},
    {"match": ("LessThanThreshold", 2.0), "set": ("LessThanThreshold", 1.0),
     "contains": ["windows", "service", "status"]},
]

# === 共通関数 ===
def describe_all_metric_alarms():
    p = cw.get_paginator("describe_alarms")
    for page in p.paginate():
        for a in page.get("MetricAlarms", []):
            if a.get("Metrics"):  # MetricMath/Composite除外
                continue
            yield a

def describe_alarm_by_name(name: str):
    r = cw.describe_alarms(AlarmNames=[name])
    lst = r.get("MetricAlarms", [])
    return lst[0] if lst else None

def _matches(a, rule):
    metric = a["MetricName"]
    if "exact" in rule and metric != rule["exact"]:
        return False
    if "contains" in rule:
        m = (metric or "").lower()
        if not all(t in m for t in rule["contains"]):
            return False
    return True

def _apply(a, rule):
    op, thr = a["ComparisonOperator"], float(a["Threshold"])
    mop, mthr = rule["match"]
    if op != mop or thr != float(mthr):
        return None
    put = build_put_args_from(a)
    sop, sthr = rule["set"]
    put["ComparisonOperator"] = sop
    put["Threshold"] = float(sthr)
    if FORCE_ONE:
        put["EvaluationPeriods"] = 1
        put["DatapointsToAlarm"] = 1
    return put

# === アクション ===
def do_update(prefix, dry_run):
    res = []
    for a in describe_all_metric_alarms():
        if prefix and not a["AlarmName"].startswith(prefix):
            continue
        before = build_put_args_from(a)
        snapshot_merge_write(a["AlarmName"], "before", before)
        updated = None
        for r in UPDATE_RULES:
            if not _matches(a, r):
                continue
            u = _apply(a, r)
            if u:
                updated = u
                break
        if not updated:
            res.append({"name": a["AlarmName"], "status": "skip"})
            continue
        if not dry_run:
            cw.put_metric_alarm(**updated)
        after_live = describe_alarm_by_name(a["AlarmName"]) if not dry_run else updated
        snapshot_merge_write(a["AlarmName"], "after", build_put_args_from(after_live))
        res.append({"name": a["AlarmName"], "from": before["Threshold"], "to": updated["Threshold"], "dry_run": dry_run})
        time.sleep(0.05)
    return {"result": "updated", "count": len(res), "items": res}

def do_rollback(prefix, dry_run):
    res = []
    for a in describe_all_metric_alarms():
        if prefix and not a["AlarmName"].startswith(prefix):
            continue
        restored = None
        for r in INVERT_RULES:
            if not _matches(a, r):
                continue
            rb = _apply(a, r)
            if rb:
                restored = rb
                break
        if not restored:
            res.append({"name": a["AlarmName"], "status": "skip"})
            continue
        if not dry_run:
            cw.put_metric_alarm(**restored)
        after_live = describe_alarm_by_name(a["AlarmName"]) if not dry_run else restored
        snapshot_merge_write(a["AlarmName"], "rollback", build_put_args_from(after_live))
        res.append({"name": a["AlarmName"], "restored_to": restored["Threshold"], "dry_run": dry_run})
        time.sleep(0.05)
    return {"result": "rolled_back", "count": len(res), "items": res}

# === Lambda Handler ===
def handler(event, context):
    action = (event or {}).get("action", "update")
    prefix = (event or {}).get("name_prefix")
    dry_run = bool((event or {}).get("dry_run", False))
    if not S3_BUCKET:
        return {"error": "SNAPSHOT_S3_BUCKET is required"}
    if action == "update":
        return do_update(prefix, dry_run)
    elif action == "rollback":
        return do_rollback(prefix, dry_run)
    else:
        return {"error": "unknown action"}
