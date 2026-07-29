import importlib.util, collections, os
spec = importlib.util.spec_from_file_location("bb_main_mod", r"C:\Users\Administrator\WorkBuddy\2026-07-24-10-37-44\系统优化工具箱.pyw")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

items = m.CLEAN_ITEMS
print("合并后 CLEAN_ITEMS 总数:", len(items))
ids = [it["id"] for it in items]
dup = [k for k, c in collections.Counter(ids).items() if c > 1]
print("重复 id 数:", len(dup), dup[:10])

bb = [it for it in items if it["id"].startswith("bb_")]
print("BleachBit 并入项数:", len(bb))
print("类型分布:", dict(collections.Counter(it["type"] for it in bb)))
print("风险分布:", dict(collections.Counter(it["risk"] for it in bb)))

# 只读计算若干项，确认不抛异常
sample = bb[:8] + [it for it in bb if it["type"] == "glob"][:4]
ok = 0
for it in sample:
    try:
        sz, cnt = m.compute_size(it)
        ok += 1
    except Exception as e:
        print("  [ERR]", it["id"], type(e).__name__, e)
print(f"compute_size 只读采样 {len(sample)} 项，成功 {ok} 项")

# 校验所有 BleachBit 项字段完整
bad = [it["id"] for it in bb if it["type"] == "folder" and not it.get("paths")
       or it["type"] == "glob" and (not it.get("base") or not it.get("patterns"))]
print("字段缺失项:", len(bad), bad[:10])
