import os, boto3

ssm = boto3.client("ssm")
sns = boto3.client("sns")
TOPIC = os.environ["SNS_TOPIC_ARN"]

def _get_new_instance_id(step_execs):
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
    detail = event.get("detail", {})
    exec_id = detail.get("ExecutionId")
    status  = detail.get("Status")
    doc     = detail.get("Definition")

    if not exec_id or not status:
        return {"ok": False, "reason": "missing ExecutionId/Status", "event": event}

    ae = ssm.get_automation_execution(AutomationExecutionId=exec_id)["AutomationExecution"]
    params = ae.get("Parameters") or {}
    old_iid = (params.get("UnhealthyInstanceId") or params.get("InstanceId") or [""])[0]

    # ステップ詳細
    steps_resp = ssm.describe_automation_step_executions(
        AutomationExecutionId=exec_id,
        ReverseOrder=True
    )
    steps = steps_resp.get("StepExecutions", [])

    # 本文データをリスト化（Success以外は失敗・タイムアウト共通）
    if status == "Success":
        new_iid = _get_new_instance_id(steps) or "<unknown>"
        info_array = [
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"旧インスタンスID : {old_iid}",
            f"新インスタンスID : {new_iid}", 
            "新インスタンスでアプリ/監視等が想定通り稼働しているか確認してください。"
        ]
        subject = f"[SUCCESS] SSM Automation {doc}"
        body = ["フェイルオーバー処理が成功しました。"] + info_array

    elif status in ["Failed", "TimedOut"]:
        failed_step, failure_msg = _get_failed_step(steps)
        info_array = [
            "＜ここに記載可能＞",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"失敗ステップ : {failed_step or '<unknown>'}",
            f"失敗メッセージ : {failure_msg or '<none>'}",
            f"旧インスタンスID : {old_iid}"
        ]
        subject = f"[{status.upper()}] SSM Automation {doc}"
        body = info_array

    else:
        subject = f"[{status}] SSM Automation {doc}"
        body = [f"想定外のステータスです: {status}"]

    # 通知（リストを文字列に結合して送信）
    sns.publish(
        TopicArn=TOPIC,
        Subject=subject,
        Message="\n".join(body)
    )
    return {"ok": True, "status": status, "subject": subject, "body": body}
