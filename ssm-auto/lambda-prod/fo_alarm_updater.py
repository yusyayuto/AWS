# fo_alarm_updater.py
import boto3, os, json, traceback
from typing import List, Dict, Any, Tuple

cw  = boto3.client("cloudwatch")
rgt = boto3.client("resourcegroupstaggingapi")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DEFAULT_TAG_KEY = os.environ.get("TAG_KEY", "failover")  # ← 既定は failover

def _log(level: str, msg: str, **kw):
    if level == "ERROR" or LOG_LEVEL == "DEBUG":
        print(json.dumps({"level": level, "msg": msg, **kw}, ensure_ascii=False))

def _as_int(v):
    try: return int(v)
    except: return None

def _as_float(v):
    try: return float(v)
    except: return None

def _as_bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, str):  return v.lower() == "true"
    return bool(v) if v is not None else None

def _replace_dims(dims: List[Dict[str, Any]], new_iid: str, new_ami: str|None) -> Tuple[bool, List[Dict[str, Any]]]:
    """Dimensions 内の InstanceId / ImageId を新値に置換（存在時のみ）。変更有無と新配列を返す"""
    if not dims: return False, dims
    changed = False
    for d in dims:
        if d.get("Name") == "InstanceId" and new_iid and d.get("Value") != new_iid:
            d["Value"] = new_iid; changed = True
        elif d.get("Name") == "ImageId" and new_ami and d.get("Value") != new_ami:
            d["Value"] = new_ami; changed = True
    return changed, dims

def _list_alarms_by_tag(tag_key: str, tag_value: str) -> List[str]:
    """Resource Groups Tagging API でタグ一致する CloudWatch アラーム名を列挙"""
    names: List[str] = []
    token: str = ""
    while True:
        resp = rgt.get_resources(
            ResourceTypeFilters=['cloudwatch:alarm'],
            TagFilters=[{'Key': tag_key, 'Values': [tag_value]}],
            PaginationToken=token
        )
        for m in resp.get('ResourceTagMappingList', []):
            arn = m['ResourceARN']                 # arn:aws:cloudwatch:region:acct:alarm:AlarmName
            name = arn.split(':alarm:', 1)[1]
            names.append(name)
        token = resp.get('PaginationToken') or ""
        if not token:
            break
    return names

def _put_metric_alarm_single(ma: Dict[str, Any], dims: List[Dict[str, Any]]):
    """単一メトリクスの再定義（必須項目を全指定）"""
    req = {
        "AlarmName": ma["AlarmName"],
        "AlarmDescription": ma.get("AlarmDescription"),
        "ActionsEnabled": _as_bool(ma.get("ActionsEnabled", True)),
        "OKActions": ma.get("OKActions") or [],
        "AlarmActions": ma.get("AlarmActions") or [],
        "InsufficientDataActions": ma.get("InsufficientDataActions") or [],
        "Namespace": ma.get("Namespace"),
        "MetricName": ma.get("MetricName"),
        "Dimensions": dims,
        "Period": _as_int(ma.get("Period")),
        "EvaluationPeriods": _as_int(ma.get("EvaluationPeriods")),
        "DatapointsToAlarm": _as_int(ma.get("DatapointsToAlarm")) if ma.get("DatapointsToAlarm") is not None else None,
        "Threshold": _as_float(ma.get("Threshold")),
        "ComparisonOperator": ma.get("ComparisonOperator"),
        "TreatMissingData": ma.get("TreatMissingData"),
        "EvaluateLowSampleCountPercentile": ma.get("EvaluateLowSampleCountPercentile"),
        "Unit": ma.get("Unit"),
    }
    if ma.get("ExtendedStatistic"):
        req["ExtendedStatistic"] = ma["ExtendedStatistic"]
    elif ma.get("Statistic"):
        req["Statistic"] = ma["Statistic"]
    req = {k: v for k, v in req.items() if v is not None}
    cw.put_metric_alarm(**req)

def _put_metric_alarm_math(ma: Dict[str, Any], metrics: List[Dict[str, Any]]):
    """Metric Math / Metrics[] の再定義（必須項目を全指定）"""
    req = {
        "AlarmName": ma["AlarmName"],
        "AlarmDescription": ma.get("AlarmDescription"),
        "ActionsEnabled": _as_bool(ma.get("ActionsEnabled", True)),
        "OKActions": ma.get("OKActions") or [],
        "AlarmActions": ma.get("AlarmActions") or [],
        "InsufficientDataActions": ma.get("InsufficientDataActions") or [],
        "EvaluationPeriods": _as_int(ma.get("EvaluationPeriods")),
        "DatapointsToAlarm": _as_int(ma.get("DatapointsToAlarm")) if ma.get("DatapointsToAlarm") is not None else None,
        "Threshold": _as_float(ma.get("Threshold")),
        "ComparisonOperator": ma.get("ComparisonOperator"),
        "TreatMissingData": ma.get("TreatMissingData"),
        "EvaluateLowSampleCountPercentile": ma.get("EvaluateLowSampleCountPercentile"),
        "Metrics": metrics
    }
    if ma.get("ThresholdMetricId"):
        req["ThresholdMetricId"] = ma["ThresholdMetricId"]
    req = {k: v for k, v in req.items() if v is not None}
    cw.put_metric_alarm(**req)

def lambda_handler(event, _):
    """
    期待入力:
      NewInstanceId (str) : 新インスタンスID（必須）
      TagValue      (str) : タグ値＝複合アラーム名（必須）
      AlarmName     (str) : （同上。TagValueが無ければこちらを見る）
      NewAmiId      (str) : 新AMI ID（任意）
      TagKey        (str) : 省略可（既定: failover or env TAG_KEY）
    """
    newi = event.get("NewInstanceId")
    tag_value = event.get("TagValue") or event.get("AlarmName")
    tag_key = event.get("TagKey") or DEFAULT_TAG_KEY
    new_ami = event.get("NewAmiId")

    if not (newi and tag_value):
        return {"ok": False, "reason": "missing required fields", "event": event}

    targets = _list_alarms_by_tag(tag_key, tag_value)
    _log("DEBUG", "targets resolved by tag", tagKey=tag_key, tagValue=tag_value, targets=targets)

    updated, skipped, errors = [], [], []

    for name in targets:
        try:
            d = cw.describe_alarms(AlarmNames=[name])
            mals = d.get("MetricAlarms", [])
            if not mals:
                skipped.append({"alarm": name, "reason": "not_metric_alarm"})
                continue
            ma = mals[0]

            if ma.get("Metrics"):
                # Metric Math
                new_metrics = []
                changed_any = False
                for q in ma["Metrics"]:
                    q2 = json.loads(json.dumps(q))  # deep copy
                    ms = q2.get("MetricStat")
                    if ms and ms.get("Metric"):
                        dims = ms["Metric"].get("Dimensions", [])
                        changed, dims2 = _replace_dims(dims, newi, new_ami)
                        if changed:
                            ms["Metric"]["Dimensions"] = dims2
                            q2["MetricStat"] = ms
                            changed_any = True
                    new_metrics.append(q2)
                if not changed_any:
                    skipped.append({"alarm": name, "reason": "no_dimension_change"})
                    continue
                _put_metric_alarm_math(ma, new_metrics)

            else:
                # 単一メトリクス
                dims = list(ma.get("Dimensions", []))
                changed, dims2 = _replace_dims(dims, newi, new_ami)
                if not changed:
                    skipped.append({"alarm": name, "reason": "no_dimension_change"})
                    continue
                _put_metric_alarm_single(ma, dims2)

            updated.append(name)

        except Exception as e:
            errors.append({"alarm": name, "error": str(e), "trace": traceback.format_exc()})

    return {
        "ok": True,
        "tagKey": tag_key,
        "tagValue": tag_value,
        "updated": updated,
        "skipped": skipped,
        "errors": errors
    }
