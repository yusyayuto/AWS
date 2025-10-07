# Lambda構成まとめ（Failover Automation 用）

## 概要

このLambdaは **CloudWatchアラーム発火** または **EC2停止イベント** をトリガーに、  
対象インスタンス情報や関連アラーム名をSSMオートメーションに渡す役割を担います。  

以下では LambdaA（アラーム発火用）と LambdaB（停止検知＋アラーム更新用）の設定・差分・環境変数をまとめます。

---

## LambdaA：複合アラーム発火用

### 想定動作
- CloudWatch複合アラームが「ALARM」へ遷移したときに発火。
- 子アラーム名を解析し、そのDimensionsから `InstanceId` を取得。
- `InstanceId` と `AlarmName` をSSMオートメーションに渡す。
- 夜間や休日（Change Calendarが`CLOSED`）は自動実行をスキップ。

### ファイル名・ハンドラー
| 項目 | 値 |
|------|----|
| ファイル名 | `lambda_alarm_trigger.py` |
| handler | `lambda_handler_alarm` |

### 環境変数
| 変数名 | 用途 | 例 |
|--------|------|----|
| `AUTOMATION_DOC` | 呼び出すSSMオートメーションドキュメント名 | `stg-sgn-pf-ssm-failover` |
| `PARAM_KEY_INSTANCE_ID` | SSM側で受け取るインスタンスIDパラメータ名 | `UnhealthyInstanceId` |
| `PARAM_KEY_COMPOSITE` | SSM側で受け取るアラーム名パラメータ名 | `AlarmName` |
| `CALENDAR_ARN` | Change Calendar ARN（時間帯制御用） | `arn:aws:ssm:ap-northeast-1:123456789012:calendar/stg-operating-hours` |
| `REGION` | Lambda実行リージョン | `ap-northeast-1` |

---

## LambdaB：EC2停止イベント＋アラーム更新用

### 想定動作
- EC2インスタンスが「stopped」状態になったときに発火。
- EC2タグから `RelatedAlarmName` を検索し、その値（複合アラーム名）を取得。
- SSMオートメーションに `UnhealthyInstanceId` と `AlarmName` を渡す。
- Change Calendarが`CLOSED`なら処理をスキップ。
- フェイルオーバー後、関連する全アラームのインスタンスIDを更新。

### ファイル名・ハンドラー
| 項目 | 値 |
|------|----|
| ファイル名 | `lambda_instance_stop.py` |
| handler | `lambda_handler_stop` |

### 環境変数
| 変数名 | 用途 | 例 |
|--------|------|----|
| `AUTOMATION_DOC` | 呼び出すSSMオートメーションドキュメント名 | `stg-sgn-pf-ssm-failover` |
| `PARAM_KEY_INSTANCE_ID` | SSM側で受け取るパラメータ名 | `UnhealthyInstanceId` |
| `PARAM_KEY_COMPOSITE` | SSM側で受け取るパラメータ名 | `AlarmName` |
| `CALENDAR_ARN` | Change Calendar ARN | `arn:aws:ssm:ap-northeast-1:123456789012:calendar/stg-operating-hours` |
| `RELATED_ALARM_TAG_KEY` | EC2とアラーム共通のタグキー | `RelatedAlarmName` |

---

## IAMポリシー（共通）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:StartAutomationExecution",
        "ssm:GetCalendarState",
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "cloudwatch:DescribeAlarms",
        "cloudwatch:ListTagsForResource"
      ],
      "Resource": "*"
    }
  ]
}
## 運用上のポイント
	•	RelatedAlarmName タグは CloudWatchアラーム と EC2インスタンス の両方に設定すること。
	•	タグの値が一致するアラーム群のみが自動更新対象となる。
	•	CALENDAR_ARN が CLOSED の場合、Lambdaは SSMオートメーションを起動しない。
	•	すべてのLambdaは同一SSMドキュメントを呼び出す。環境ごとにAUTOMATION_DOCを切り替える。

