import os, boto3, json

ssm = boto3.client("ssm")
sns = boto3.client("sns")
TOPIC = os.environ["SNS_TOPIC_ARN"]

def _get_new_instance_id(steps):
    for s in steps:
        if s.get("StepName") == "runInstances":
            outs = s.get("Outputs") or {}
            ids = outs.get("InstanceId") or outs.get("Instances") or []
            if isinstance(ids, list) and ids:
                return ids[0]
    return None

def _get_failed_step(steps):
    for s in steps:
        if s.get("StepStatus") == "Failed":
            return s.get("StepName"), (s.get("FailureMessage") or s.get("Response"))
    return None, None

def lambda_handler(event, _):
    print(json.dumps(event, ensure_ascii=False))  # デバッグ用

    d = event.get("detail", {})
    exec_id = d.get("ExecutionId")
    status  = d.get("Status")
    doc     = d.get("Definition") or "<unknown>"

    if not exec_id or not status:
        return {"ok": False, "reason": "missing ExecutionId/Status", "detail": d}

    ae = ssm.get_automation_execution(AutomationExecutionId=exec_id)["AutomationExecution"]
    params = ae.get("Parameters") or {}
    old_iid = (params.get("UnhealthyInstanceId") or params.get("InstanceId") or [""])[0]

    steps = ssm.describe_automation_step_executions(
        AutomationExecutionId=exec_id,
        ReverseOrder=True
    ).get("StepExecutions", [])

    if status == "Success":
        new_iid = _get_new_instance_id(steps) or "<unknown>"
        lines = [
            "フェイルオーバー処理が成功しました。",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"旧インスタンスID : {old_iid}",
            f"新インスタンスID : {new_iid}",
            "新インスタンスが正常稼働していることを確認してください。"
        ]
        subject = f"[SUCCESS] SSM Automation {doc}"

    elif status in ["Failed", "TimedOut"]:
        step, msg = _get_failed_step(steps)
        lines = [
            "フェイルオーバー処理が失敗またはタイムアウトしました。",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"失敗ステップ : {step or '<unknown>'}",
            f"失敗メッセージ : {msg or '<none>'}",
            f"旧インスタンスID : {old_iid}",
            "運用手順書を確認し、手動でフェイルオーバー対応を実施してください。"
        ]
        subject = f"[{status.upper()}] SSM Automation {doc}"

    else:
        lines = [f"想定外のステータス: {status}", f"Document : {doc}", f"ExecutionId : {exec_id}"]
        subject = f"[{status}] SSM Automation {doc}"

    sns.publish(
        TopicArn=TOPIC,
        Subject=subject[:100],
        Message="\n".join(lines)
    )
    return {"ok": True, "status": status, "subject": subject}
