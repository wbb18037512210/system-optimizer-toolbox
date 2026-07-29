import bleachbit_cleaners as bb

items = bb.BLEACHBIT_CLEAN_ITEMS
print("BLEACHBIT_CLEAN_ITEMS 总数:", len(items))

CRIT = {
    r"c:\windows", r"c:\program files", r"c:\program files (x86)", r"c:\programdata",
    r"c:\users", r"c:\users\public", "c:\\", r"c:\windows\system32", r"c:\windows\syswow64",
}
flags = []
broad = []
for it in items:
    paths = []
    if it["type"] == "folder":
        paths = it.get("paths", [])
    elif it["type"] == "glob":
        paths = [it.get("base", "")]
    for p in paths:
        pl = p.lower().rstrip("/\\")
        if pl in CRIT:
            flags.append((it["id"], p))
        parts = [x for x in pl.split("\\") if x]
        if parts and parts[0].endswith(":"):
            depth = len(parts) - 1
            if depth <= 1 and pl not in CRIT:
                broad.append((it["id"], p, depth))

print("\n[!!] 命中风控目录(应无):", len(flags))
for f in flags:
    print("   ", f)
print("\n[~] 层级<=1 的宽泛路径(审视):", len(broad))
for b in broad[:40]:
    print("   ", b)

from collections import Counter
print("\n类型分布:", dict(Counter(it["type"] for it in items)))
print("风险分布:", dict(Counter(it["risk"] for it in items)))

print("\n样例(Google Chrome):")
for it in items:
    if it["id"].startswith("bb_google_chrome_"):
        print("  ", it["id"], "|", it["type"], "|", it["risk"], "|", it["detail"][:90])

print("\n样例(Windows Defender):")
for it in items:
    if it["id"].startswith("bb_windows_defender_"):
        print("  ", it["id"], "|", it["type"], "|", it["risk"], "|", it["detail"][:90])
