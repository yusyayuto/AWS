# ssm_automation_notifier.py
import os, json, boto3

ssm = boto3.client("ssm")
sns = boto3.client("sns")
TOPIC = os.environ["SNS_TOPIC_ARN"]

def _get_new_instance_id(step_execs):
    # 例：ランブック内の runInstances ステップの出力 "InstanceId" を拾う
    for s in step_execs:
        if s.get("StepName") == "runInstances":
            outs = s.get("Outputs") or {}
            ids = outs.get("InstanceId") or outs.get("Instances") or []
            if isinstance(ids, list) and ids:
                return ids[0]
    return None

def _get_failed_step(step_execs):
    for s in step_execs:
        if s.get("StepStatus") == "Failed":
            return s.get("StepName"), (s.get("FailureMessage") or s.get("Response"))
    return None, None

def lambda_handler(event, _):
    # EventBridge input-transformer から受領
    exec_id = event.get("ExecutionId")
    status  = event.get("Status")
    doc     = event.get("DocumentName")

    if not exec_id or not status:
        return {"ok": False, "reason": "missing ExecutionId/Status", "event": event}

    # 実行詳細
    ae = ssm.get_automation_execution(AutomationExecutionId=exec_id)["AutomationExecution"]
    params = ae.get("Parameters") or {}
    old_iid = (params.get("UnhealthyInstanceId") or params.get("InstanceId") or [""])[0]

    # ステップ詳細（新インスタンスIDや失敗箇所取得用）
    steps_resp = ssm.describe_automation_step_executions(
        AutomationExecutionId=exec_id,
        ReverseOrder=True  # 直近から
    )
    steps = steps_resp.get("StepExecutions", [])

    subject = body = ""
    if status == "Success":
        new_iid = _get_new_instance_id(steps) or "<unknown>"
        subject = f"[SUCCESS] SSM Automation {doc}"
        body = (
            "フェイルオーバー処理が成功しました。\n\n"
            f"- Document : {doc}\n"
            f"- ExecutionId : {exec_id}\n"
            f"- 旧インスタンスID : {old_iid}\n"
            f"- 新インスタンスID : {new_iid}\n\n"
            "新インスタンスでアプリ/監視等が想定通り稼働しているか確認してください。"
        )
    else:  # Failed
        failed_step, failure_msg = _get_failed_step(steps)
        subject = f"[FAILED] SSM Automation {doc}"
        body = (
            "フェイルオーバー処理が失敗しました。運用手順書に従い手動で切替を実施してください。\n\n"
            f"- Document : {doc}\n"
            f"- ExecutionId : {exec_id}\n"
            f"- 失敗ステップ : {failed_step or '<unknown>'}\n"
            f"- 失敗メッセージ : {failure_msg or '<none>'}\n"
            f"- 旧インスタンスID : {old_iid}\n"
        )

    sns.publish(TopicArn=TOPIC, Subject=subject, Message=body)
    return {"ok": True, "status": status, "subject": subject}
