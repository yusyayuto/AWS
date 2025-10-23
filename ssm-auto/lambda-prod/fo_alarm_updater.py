# fo_alarm_updater.py
# 目的:
#  - 複合アラーム配下の「子アラーム」すべてについて、
#    Dimensions の InstanceId を新IDへ、ImageId(あれば) を新AMIへ更新する
#
# 想定入力(EventBridge/SSM から Lambda イベントに渡す):
# {
#   "AlarmName":       "<CompositeAlarmName>",        # 複合アラーム名（必須）
#   "OldInstanceId":   "i-0old...",                   # 旧インスタンスID（任意：一致時のみ置換）
#   "NewInstanceId":   "i-0new...",                   # 新インスタンスID（必須）
#   "NewAmiId":        "ami-0abcd123...",            # 新AMI ID（任意：子に ImageId があれば置換）
# }
#
# 環境変数: なし
#
# ポイント:
#  - DescribeAlarms(ChildrenOfAlarmName=...) で子アラーム名一覧を取得
#  - 各子アラームを DescribeAlarms(AlarmNames=[...]) で完全取得
#  - Dimensions を編集して PutMetricAlarm で同定義を再作成(上書き)
#  - ImageId ディメンションが無いアラームはそのままスキップ（InstanceId だけ更新）
#  - Metrics(メトリックマス) 型／単一メトリック型の両方に対応
#  - 可能な限り元定義を踏襲(AlarmActions, TreatMissingData等)
#
# 必要権限 (Lambda 実行ロール):
#  - cloudwatch:DescribeAlarms
#  - cloudwatch:PutMetricAlarm

import json
import boto3
from botocore.exceptions import ClientError

cw = boto3.client("cloudwatch")

# PutMetricAlarm で受け付けられる主要キー（必要十分）
_SINGLE_METRIC_KEYS = {
    "AlarmName",
    "AlarmDescription",
    "ActionsEnabled",
    "OKActions",
    "AlarmActions",
    "InsufficientDataActions",
    "MetricName",
    "Namespace",
    "Statistic",
    "ExtendedStatistic",
    "Dimensions",
    "Period",
    "Unit",
    "EvaluationPeriods",
    "DatapointsToAlarm",
    "Threshold",
    "ComparisonOperator",
    "TreatMissingData",
    "EvaluateLowSampleCountPercentile"
}

# Metrics(メトリックマス) アラームで利用するキー
_METRIC_MATH_KEYS = {
    "AlarmName",
    "AlarmDescription",
    "ActionsEnabled",
    "OKActions",
    "AlarmActions",
    "InsufficientDataActions",
    "Metrics",                    # ★ こちらが存在する場合は単一メトリックの各種キーは不要
    "EvaluationPeriods",
    "DatapointsToAlarm",
    "Threshold",
    "ComparisonOperator",
    "TreatMissingData",
    "EvaluateLowSampleCountPercentile"
}

def _list_child_alarm_names(composite_name: str) -> list[str]:
    names = []
    token = None
    while True:
        resp = cw.describe_alarms(ChildrenOfAlarmName=composite_name, NextToken=token) if token else \
               cw.describe_alarms(ChildrenOfAlarmName=composite_name)
        # 子は MetricAlarms に入って返る
        for ma in resp.get("MetricAlarms", []):
            names.append(ma["AlarmName"])
        token = resp.get("NextToken")
        if not token:
            break
    return names

def _describe_alarm(name: str) -> dict | None:
    resp = cw.describe_alarms(AlarmNames=[name])
    arr = resp.get("MetricAlarms", [])
    return arr[0] if arr else None

def _update_dimensions_list(dims: list, old_iid: str | None, new_iid: str, new_ami: str | None) -> tuple[list, bool]:
    """
    Dimensions を更新:
      - InstanceId: old_iid が指定されていれば一致時のみ置換。未指定なら無条件で new_iid をセット
      - ImageId:    存在する場合のみ new_ami を上書き（new_ami 未指定なら変更なし）
    返り値: (更新後リスト, 何か変更があったか)
    """
    changed = False
    out = []
    has_iid = False
    for d in dims:
        n, v = d.get("Name"), d.get("Value")
        if n == "InstanceId":
            has_iid = True
            if old_iid:
                if v == old_iid and v != new_iid:
                    v = new_iid
                    changed = True
            else:
                if v != new_iid:
                    v = new_iid
                    changed = True
            out.append({"Name": n, "Value": v})
        elif n == "ImageId" and new_ami:
            if v != new_ami:
                v = new_ami
                changed = True
            out.append({"Name": n, "Value": v})
        else:
            out.append({"Name": n, "Value": v})

    # 念のため、InstanceId ディメンションが無かった場合は追加（構成上まず無い想定だが安全策）
    if not has_iid:
        out.append({"Name": "InstanceId", "Value": new_iid})
        changed = True

    return out, changed

def _put_metric_alarm_from_desc(desc: dict) -> None:
    """
    DescribeAlarms の戻り(desc)から PutMetricAlarm のパラメータを再構築し、上書きする。
    Metrics(メトリックマス) と単一メトリックの両対応。
    """
    params = {}
    # Metrics があればメトリックマス
    if "Metrics" in desc and desc["Metrics"]:
        for k in _METRIC_MATH_KEYS:
            if k in desc:
                params[k] = desc[k]
    else:
        for k in __SINGLE_METRIC_KEYS:
            if k in desc:
                params[k] = desc[k]

    # AlarmName は必須
    params["AlarmName"] = desc["AlarmName"]
    # Put
    cw.put_metric_alarm(**params)

def lambda_handler(event, _context):
    """
    期待入力:
      AlarmName      : 複合アラーム名（必須）
      OldInstanceId  : 旧IID（任意）
      NewInstanceId  : 新IID（必須）
      NewAmiId       : 新AMI（任意）
    """
    print("### Raw Event ###")
    print(json.dumps(event, ensure_ascii=False))

    comp = event.get("AlarmName")
    new_iid = event.get("NewInstanceId")
    if not comp or not new_iid:
        return {"status": "error", "reason": "AlarmName and NewInstanceId are required."}

    old_iid = event.get("OldInstanceId")
    new_ami = event.get("NewAmiId")

    # 子アラーム一覧
    children = _list_child_alarm_names(comp)
    if not children:
        return {"status": "skipped", "reason": "no child alarms", "composite": comp}

    updated, skipped, errors = [], [], []

    for name in children:
        try:
            desc = _describe_alarm(name)
            if not desc:
                skipped.append({"alarm": name, "reason": "not found"})
                continue

            # 単一メトリック or メトリックマスで分岐して Dimensions を更新
            changed_any = False

            if "Metrics" in desc and desc["Metrics"]:
                # メトリックマス: Metrics[].MetricStat.Metric.Dimensions を走査
                metrics = []
                for m in desc["Metrics"]:
                    m2 = dict(m)
                    if "MetricStat" in m and "Metric" in m["MetricStat"]:
                        dims = m["MetricStat"]["Metric"].get("Dimensions", [])
                        new_dims, changed = _update_dimensions_list(dims, old_iid, new_iid, new_ami)
                        m2["MetricStat"] = dict(m["MetricStat"])
                        m2["MetricStat"]["Metric"] = dict(m["MetricStat"]["Metric"])
                        m2["MetricStat"]["Metric"]["Dimensions"] = new_dims
                        if changed:
                            changed_any = True
                    metrics.append(m2)
                if changed_any:
                    desc = dict(desc)
                    desc["Metrics"] = metrics

            else:
                # 単一メトリック: desc.Dimensions を更新
                dims = desc.get("Dimensions", [])
                new_dims, changed = _update_dimensions_list(dims, old_iid, new_iid, new_ami)
                if changed:
                    changed_any = True
                    desc = dict(desc)
                    desc["Dimensions"] = new_dims

            if changed_any:
                _put_metric_alarm_from_desc(desc)
                updated.append(name)
            else:
                skipped.append({"alarm": name, "reason": "no dimension change"})

        except ClientError as e:
            errors.append({"alarm": name, "error": str(e)})
        except Exception as e:
            errors.append({"alarm": name, "error": str(e)})

    return {
        "status": "ok",
        "composite": comp,
        "updatedCount": len(updated),
        "skippedCount": len(skipped),
        "errorCount": len(errors),
        "updated": updated,
        "skipped": skipped[:10],  # 多すぎるとログが見づらいので先頭だけ
        "errors": errors[:10]
    }
