要件確認（最終版）

スコープ
	•	対象リージョン: ap-northeast-1
	•	対象: 単体メトリクスアラームのみ（複合は除外）
	•	抽出条件: **あなたが渡した“現行しきい値条件”**と一致するアラームのみ更新
	•	ディメンション: 全て退避（差分確認用）

変更内容（ALARMに寄せる一時値）
	•	LogicalDisk % Free Space <=10 → <=99.5
	•	Memory Available Bytes <=1,717,986,918 → <=1,000,000,000,000
	•	Processor % Processor Time >90 → >1
	•	StatusCheckFailed_Instance >=1 → >=0
	•	StatusCheckFailed_System >=1 → >=0
	•	Windows_service_status <1 → <2
	•	評価設定: 既存を維持（EvaluationPeriods / DatapointsToAlarm）
	•	例外: オプションで --force-one-datapoint を指定した実行時のみ =1/1 に更新

退避・保管
	•	退避先: 〈パラメータストア名〉（SSM Parameter Store / String）
	•	保存スキーマ（アラーム単位）: before / after / rollback を保持
	•	各オブジェクトに以下を含む
	•	MetricName, Namespace, ComparisonOperator, Threshold
	•	EvaluationPeriods, DatapointsToAlarm, Period, Statistic(or ExtendedStatistic), Unit
	•	Dimensions[]（全件）
	•	TreatMissingData, AlarmActions, OKActions, InsufficientDataActions, Tags

実行形態
	•	Lambda関数を手動またはEventBridgeスケジュールで実行
	•	目的は「アラームをALARM側に寄せる更新」。アラーム遷移をトリガーにLambdaを起動しない（循環回避）
	•	検証はあなたが手動で確認（アラーム状態/SNS到達/履歴）

ロールバック
	•	〈パラメータストア名〉の before を読み出し、put_metric_alarm で元値へ復元
	•	評価設定やDimensions含む関連プロパティは退避値を復元

失敗時リトライ・分割
	•	APIスロットリングは指数バックオフ
	•	件数多い場合はタグや接頭辞で分割実行可能

IAM（最小権限）
	•	cloudwatch:DescribeAlarms
	•	cloudwatch:PutMetricAlarm
	•	ssm:PutParameter
	•	ssm:GetParameter

環境変数（Lambda/ローカル共通）
	•	PARAM_NAME = 〈パラメータストア名〉
	•	FORCE_ONE_DATAPOINT = true or false（既定: false）
	•	AWS_REGION = ap-northeast-1（Lambdaは実行リージョンに依存）

⸻

ここまででOKなら、次でスクリプト一式を出す。
内容: Lambda本体（Python 3.12）、ハンドラ名、ZIPファイル名、環境変数例、IAMポリシーJSON、デプロイと実行手順、ロールバックスクリプト。
