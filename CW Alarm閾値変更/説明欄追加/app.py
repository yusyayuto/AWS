import os, json, time

import boto3

REGION = os.environ.get("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1"))
cw = boto3.client("cloudwatch", region_name=REGION)

# ---- 対象は「説明が空」かつ「テスト用しきい値」に一致するアラームのみ ----
def is_windows_service(metric_name: str) -> bool:
    m = metric_name.lower()
    return ("windows" in m) and ("service" in m) and ("status" in m)

def pick_description(a):
    """各テスト閾値に対応する説明文を環境変数から取得。合致しなければ None。"""
    metric = a["MetricName"]
    op = a["ComparisonOperator"]
    thr = float(a["Threshold"])

    # Windowsサービス系は完全スキップ
    if is_windows_service(metric):
        return None

    # Disk: LogicalDisk % Free Space <= 99.5
    if "% Free Space" in metric and op == "LessThanOrEqualToThreshold" and thr == 99.5:
        return os.environ.get("DESC_DISK")

    # Memory: Memory Available Bytes <= 1,000,000,000,000
    if metric == "Memory Available Bytes" and op == "LessThanOrEqualToThreshold" and thr == 1_000_000_000_000:
        return os.environ.get("DESC_MEMORY")

    # CPU: Processor % Processor Time > 1
    if "% Processor Time" in metric and op == "GreaterThanThreshold" and thr == 1.0:
        return os.environ.get("DESC_CPU")

    # Status: Instance >= 0
    if metric == "StatusCheckFailed_Instance" and op == "GreaterThanOrEqualToThreshold" and thr == 0.0:
        return os.environ.get("DESC_STATUS_INSTANCE")

    # Status: System >= 0
    if metric == "StatusCheckFailed_System" and op == "GreaterThanOrEqualToThreshold" and thr == 0.0:
        return os.environ.get("DESC_STATUS_SYSTEM")

    return None

def build_put_args_from(a: dict) -> dict:
    """現定義を踏襲して説明だけ差し込む。"""
    args = {
        "AlarmName": a["AlarmName"],
        "AlarmDescription": a.get("AlarmDescription"),  # 後で上書き
        "ActionsEnabled": a.get("ActionsEnabled", True),
        "OKActions": a.get("OKActions", []),
        "AlarmActions": a.get("AlarmActions", []),
        "InsufficientDataActions": a.get("InsufficientDataActions", []),
        "MetricName": a["MetricName"],
        "Namespace": a["Namespace"],
        "Statistic": a.get("Statistic"),
        "ExtendedStatistic": a.get("ExtendedStatistic"),
        "Dimensions": a.get("Dimensions", []),
        "Period": a["Period"],
        "Unit": a.get("Unit"),
        "EvaluationPeriods": a.get("EvaluationPeriods"),
        "DatapointsToAlarm": a.get("DatapointsToAlarm"),
        "Threshold": a["Threshold"],
        "ComparisonOperator": a["ComparisonOperator"],
        "TreatMissingData": a.get("TreatMissingData", "missing"),
        "Tags": a.get("Tags", [])
    }
    return {k: v for k, v in args.items() if v is not None}

def describe_metric_alarms():
    p = cw.get_paginator("describe_alarms")
    for page in p.paginate():
        for a in page.get("MetricAlarms", []):
            # Metric Math / Composite は除外（MetricNameを直接持たないもの）
            if a.get("Metrics"):
                continue
            yield a

def set_description(a, desc: str, dry_run: bool):
    put = build_put_args_from(a)
    put["AlarmDescription"] = desc
    if not dry_run:
        cw.put_metric_alarm(**put)
    return {"name": a["AlarmName"], "desc_set": True, "dry_run": dry_run}

def handler(event, context):
    action = (event or {}).get("action", "set_description")
    if action != "set_description":
        return {"error": "only set_description is supported in this function"}

    name_prefix = (event or {}).get("name_prefix")
    dry_run = bool((event or {}).get("dry_run", False))

    def match_prefix(n: str) -> bool:
        return (not name_prefix) or n.startswith(name_prefix)

    results = []
    for a in describe_metric_alarms():
        if not match_prefix(a["AlarmName"]):
            continue

        # すでに説明があるものは触らない
        cur_desc = a.get("AlarmDescription")
        if cur_desc is not None and str(cur_desc).strip():
            continue

        desc = pick_description(a)
        if not desc:  # 環境変数未設定 or 閾値が想定と違う
            continue

        r = set_description(a, desc, dry_run=dry_run)
        results.append(r)
        time.sleep(0.03)

    return {"result": "desc_set", "count": len(results), "items": results}
