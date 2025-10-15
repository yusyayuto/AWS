# ==== 先頭の環境変数読み出し付近に追加 ====
MEM_FALLBACK = os.environ.get("MEMORY_BASELINE_FALLBACK")  # "1.6G" or "3.2G" or None

# ==== ユーティリティとして追加 ====
def _pick_mem_baseline_from_name(alarm_name: str):
    n = alarm_name.lower()
    pat_32 = ("3.2", "3200", "3g", "3gb", "3276", "3435")
    pat_16 = ("1.6", "1600", "1g", "1gb", "1717")
    if any(p in n for p in pat_32):
        return 3435973836.0  # ≈3.2GB
    if any(p in n for p in pat_16):
        return 1717986918.0  # ≈1.6GB
    if MEM_FALLBACK == "3.2G":
        return 3435973836.0
    if MEM_FALLBACK == "1.6G":
        return 1717986918.0
    return None  # 判定不能

# ==== 既存の ROLLBACK_RULES から「Memory」の行は削除してください ====
# （Disk/CPU/Status/Windows の行はそのまま）

# ==== do_rollback 内のループで、汎用ルール適用の前にメモリ専用処理を挿入 ====
def do_rollback(name_prefix: str | None, dry_run: bool):
    results = []
    for a in describe_all_metric_alarms():
        if name_prefix and not a["AlarmName"].startswith(name_prefix):
            continue

        metric = a["MetricName"]
        op = a["ComparisonOperator"]
        thr = float(a["Threshold"])

        # --- Memory Available Bytes の専用ロールバック ---
        if (metric == "Memory Available Bytes"
            and op == "LessThanOrEqualToThreshold"
            and thr == 1_000_000_000_000.0):
            base = _pick_mem_baseline_from_name(a["AlarmName"])
            if base is None:
                results.append({"name": a["AlarmName"], "status": "skip(mem-ambiguous)"})
            else:
                rb = build_put_args_from(a)
                rb["Threshold"] = base
                if not dry_run:
                    cw.put_metric_alarm(**rb)
                after_live = describe_alarm_by_name(a["AlarmName"]) if not dry_run else rb
                if after_live:
                    snapshot_merge_write(a["AlarmName"], "rollback", build_put_args_from(after_live))
                results.append({"name": a["AlarmName"], "restored_to": base, "op": rb["ComparisonOperator"], "dry_run": dry_run})
            time.sleep(0.05)
            continue  # メモリはここで処理完了

        # --- それ以外は既存の汎用 ROLLBACK_RULES を適用 ---
        restored = None
        for rule in ROLLBACK_RULES:
            ok, rb = _apply_rule_if_match(a, rule)
            if ok:
                restored = rb
                break
        if not restored:
            results.append({"name": a["AlarmName"], "status": "skip(no-rollback-match)"})
            continue

        if not dry_run:
            cw.put_metric_alarm(**restored)
        after_live = describe_alarm_by_name(a["AlarmName"]) if not dry_run else restored
        if after_live:
            snapshot_merge_write(a["AlarmName"], "rollback", build_put_args_from(after_live))
        results.append({"name": a["AlarmName"], "restored_to": restored["Threshold"], "op": restored["ComparisonOperator"], "dry_run": dry_run})
        time.sleep(0.05)

    return {"result": "rolled_back", "count": len(results), "items": results}
