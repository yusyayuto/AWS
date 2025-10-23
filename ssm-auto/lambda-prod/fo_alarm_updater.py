import json
import boto3
import os

cw = boto3.client("cloudwatch")
TAG_KEY = os.environ.get("TAG_KEY", "failover")

def lambda_handler(event, context):
    """
    更新対象:
      - タグキー failover の値が event["AlarmName"] と一致するアラーム
    更新内容:
      - Dimensions 内の InstanceId と ImageId を新しい値に置換
    """
    print("### Raw Event ###")
    print(json.dumps(event, ensure_ascii=False, indent=2))

    # --- パラメータ取得 ---
    alarm_name = event.get("AlarmName")
    new_instance_id = event.get("NewInstanceId")
    new_ami_id = event.get("NewAmiId")

    if not alarm_name or not new_instance_id:
        return {"status": "error", "reason": "missing AlarmName or NewInstanceId"}

    print(f"Processing alarms tagged with {TAG_KEY}={alarm_name}")

    updated_count = 0
    skipped_count = 0

    # --- すべてのアラームを取得 ---
    paginator = cw.get_paginator("describe_alarms")
    for page in paginator.paginate():
        for alarm in page.get("MetricAlarms", []):
            alarm_arn = alarm.get("AlarmArn")

            # タグ取得
            try:
                tags_response = cw.list_tags_for_resource(ResourceARN=alarm_arn)
                tags = {t["Key"]: t["Value"] for t in tags_response.get("Tags", [])}
            except Exception as e:
                print(f"Tag fetch failed for {alarm_arn}: {e}")
                continue

            # タグが一致しない場合スキップ
            if tags.get(TAG_KEY) != alarm_name:
                continue

            # --- Dimensionsの書き換え ---
            changed = False
            for dim in alarm.get("Dimensions", []):
                if dim["Name"] == "InstanceId" and dim["Value"] != new_instance_id:
                    print(f"Updating InstanceId: {dim['Value']} → {new_instance_id}")
                    dim["Value"] = new_instance_id
                    changed = True
                elif dim["Name"] == "ImageId" and new_ami_id and dim["Value"] != new_ami_id:
                    print(f"Updating ImageId: {dim['Value']} → {new_ami_id}")
                    dim["Value"] = new_ami_id
                    changed = True

            # 変更がない場合はスキップ
            if not changed:
                skipped_count += 1
                continue

            # --- アラーム再登録 ---
            try:
                cw.put_metric_alarm(
                    AlarmName=alarm["AlarmName"],
                    ComparisonOperator=alarm["ComparisonOperator"],
                    EvaluationPeriods=alarm["EvaluationPeriods"],
                    MetricName=alarm["MetricName"],
                    Namespace=alarm["Namespace"],
                    Period=alarm["Period"],
                    Statistic=alarm.get("Statistic"),
                    ExtendedStatistic=alarm.get("ExtendedStatistic"),
                    Threshold=alarm["Threshold"],
                    ActionsEnabled=alarm["ActionsEnabled"],
                    AlarmActions=alarm.get("AlarmActions", []),
                    OKActions=alarm.get("OKActions", []),
                    InsufficientDataActions=alarm.get("InsufficientDataActions", []),
                    Dimensions=alarm["Dimensions"],
                    Unit=alarm.get("Unit"),
                    TreatMissingData=alarm.get("TreatMissingData", "missing"),
                    Tags=[{"Key": k, "Value": v} for k, v in tags.items()],
                )
                print("Updated alarm: {alarm['AlarmName']}")
                updated_count += 1
            except Exception as e:
                print("Failed to update {alarm['AlarmName']}: {e}")

    result = {
        "status": "completed",
        "targetAlarm": alarm_name,
        "updated": updated_count,
        "skipped": skipped_count,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
