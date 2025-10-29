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
    return "<unknown>"

def _get_failed_step(steps):
    for s in steps:
        if s.get("StepStatus") == "Failed":
            return s.get("StepName") or "<unknown>", (s.get("FailureMessage") or s.get("Response") or "<none>")
    return "<unknown>", "<none>"

def lambda_handler(event, _):
    # イベント必須項目
    d = event.get("detail", {})
    exec_id = d.get("ExecutionId")
    status  = d.get("Status")
    doc     = d.get("Definition") or "<unknown>"
    start_t = d.get("StartTime") or "<unknown>"
    end_t   = d.get("EndTime") or "<unknown>"
    region  = event.get("region") or "<unknown>"
    account = event.get("account") or "<unknown>"
    evt_time= event.get("time") or "<unknown>"

    if not exec_id or not status:
        return {"ok": False, "reason": "missing ExecutionId/Status", "detail": d}

    # 実行詳細取得
    ae = ssm.get_automation_execution(AutomationExecutionId=exec_id)["AutomationExecution"]
    params = ae.get("Parameters") or {}

    # 追加パラメータ
    failover = (params.get("failover") or ["<unknown>"])[0]

    # 旧/新インスタンスID
    # 成功時の旧IDは UnhealthyInstanceId のみ
    old_iid_success = (params.get("UnhealthyInstanceId") or ["<unknown>"])[0]
    # 失敗時は従来ロジック（必要なら上と同じに変更可）
    old_iid_any = (params.get("UnhealthyInstanceId") or params.get("InstanceId") or ["<unknown>"])[0]

    # ステップ一覧
    steps = ssm.describe_automation_step_executions(
        AutomationExecutionId=exec_id,
        ReverseOrder=True
    ).get("StepExecutions", [])

    if status == "Success":
        new_iid = _get_new_instance_id(steps)
        lines = [
            f"フェイルオーバー: {failover}",
            "フェイルオーバー処理が成功しました。",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"旧インスタンスID : {old_iid_success}",
            f"新インスタンスID : {new_iid}",
            f"region/account : {region}/{account}",
            f"Start/End : {start_t} / {end_t}",
            f"EventTime : {evt_time}",
        ]
        subject = f"[SUCCESS] SSM Automation {doc}"

    elif status in ["Failed", "TimedOut"]:
        step, msg = _get_failed_step(steps)
        lines = [
            f"フェイルオーバー: {failover}",
            "フェイルオーバー処理が失敗またはタイムアウトしました。",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"失敗ステップ : {step}",
            f"失敗メッセージ : {msg}",
            f"旧インスタンスID : {old_iid_any}",
            f"region/account : {region}/{account}",
            f"Start/End : {start_t} / {end_t}",
            f"EventTime : {evt_time}",
        ]
        subject = f"[{status.upper()}] SSM Automation {doc}"

    else:
        lines = [
            f"フェイルオーバー: {failover}",
            f"想定外のステータス: {status}",
            f"Document : {doc}",
            f"ExecutionId : {exec_id}",
            f"region/account : {region}/{account}",
            f"Start/End : {start_t} / {end_t}",
            f"EventTime : {evt_time}",
        ]
        subject = f"[{status}] SSM Automation {doc}"

    sns.publish(
        TopicArn=TOPIC,
        Subject=subject[:100],
        Message="\n".join(lines)
    )
    return {"ok": True, "status": status, "subject": subject}
