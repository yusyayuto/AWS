# handler.py
import os, time, boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")
ddb = boto3.resource("dynamodb").Table(os.environ["DEDUP_TABLE"])

TAG_KEY = os.environ["TAG_KEY"]
TTL_SEC = int(os.environ.get("DEDUP_TTL_SEC", "900"))
DOC     = os.environ["AUTOMATION_DOC"]
P_IID   = os.environ.get("PARAM_KEY_INSTANCE_ID", "InstanceId")
P_GRP   = os.environ.get("PARAM_KEY_GROUP", "Group")

def lock(key: str) -> bool:
    now = int(time.time())
    try:
        ddb.put_item(Item={"k": key, "ttl": now + TTL_SEC, "ts": now},
                     ConditionExpression="attribute_not_exists(k)")
        return True
    except ClientError:
        return False

def get_group_and_iid(iid: str) -> tuple[str, str]:
    r = ec2.describe_instances(InstanceIds=[iid])
    tags = {t["Key"]: t["Value"] for t in r["Reservations"][0]["Instances"][0].get("Tags", [])}
    grp = tags.get(TAG_KEY)
    return grp, iid

def lambda_handler(event, _):
    iid = event.get("instance_id")
    if not iid:
        return {"status": "ignored_no_instance"}
    grp, _ = get_group_and_iid(iid)
    if not grp:
        return {"status": "ignored_no_group", "instanceId": iid}

    # グループタグで排他
    if not lock(grp):
        return {"status": "skipped_dedup", "group": grp}

    resp = ssm.start_automation_execution(
        DocumentName=DOC,
        Parameters={P_IID: [iid], P_GRP: [grp]},
        ClientToken=event.get("event_id")  # 冪等
    )
    return {"status": "started", "group": grp, "iid": iid,
            "executionId": resp.get("AutomationExecutionId")}
