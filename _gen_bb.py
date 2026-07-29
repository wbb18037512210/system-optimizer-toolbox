# -*- coding: utf-8 -*-
"""生成 bleachbit_cleaners.py：把 BleachBit 6.0.2 的 Windows 清理器配置
转换为本工具的原生 CLEAN_ITEMS 条目。
- 只抽取 command=delete/shred 的文件/目录清理动作（winreg/vacuum/sqlite/ini/...
  等非文件动作与现有框架不匹配，按要求省略）。
- 保留 %VAR% 与 $$var$$ 占位符，运行时再解析（保证跨用户/机器可移植）。
- 与现有 CLEAN_ITEMS 去重：完全被现有项覆盖的路径不再重复生成。
"""
import os, re, zipfile, importlib.util, xml.etree.ElementTree as ET

ZIP = r"D:\360极速浏览器X下载\bleachbit-6.0.2.zip"
MAIN = os.path.join(os.path.dirname(__file__), "系统优化工具箱.pyw")

# ---------- 导入主模块以读取现有 CLEAN_ITEMS（不创建 GUI） ----------
spec = importlib.util.spec_from_file_location("bb_main_mod", MAIN)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
EXISTING = m.CLEAN_ITEMS
print("现有 CLEAN_ITEMS 项数:", len(EXISTING))

# 现有项已解析的目标目录集合（小写），用于去重
EXISTING_DIRS = set()
EXISTING_GLOB_BASES = set()
for it in EXISTING:
    try:
        for f in m.item_folders(it):
            EXISTING_DIRS.add(f.lower().rstrip("/\\"))
    except Exception:
        pass
    if it.get("type") == "glob":
        b = it.get("base")
        if b:
            EXISTING_GLOB_BASES.add(b.lower().rstrip("/\\"))
    if it.get("type") == "ext":
        for r in it.get("roots", []):
            if r:
                EXISTING_DIRS.add(r.lower().rstrip("/\\"))

def existing_covers(dirs):
    """候选目录集合是否完全被现有项覆盖。"""
    if not dirs:
        return True
    return all(d in EXISTING_DIRS for d in dirs)

# ---------- 解析 zip 里的 Windows 清理器 ----------
z = zipfile.ZipFile(ZIP)
base = "bleachbit-6.0.2/cleaners/"

RISK_KW = re.compile(r"cookie|history|session|password|form|autofill|credential|login|bookmark|cache", re.I)
PRIVACY_KW = re.compile(r"cookie|history|session|password|form|autofill|credential|login|bookmark", re.I)
# 高敏感：删除会导致退出登录 / 丢失已保存凭据，默认不勾选更安全
HIGH_KW = re.compile(r"password|credential|login data|key(ring|chain)?|wallet", re.I)

raw_specs = []  # (cleaner_id, cleaner_label, option_id, option_label, risk, [(search, path)], vars)
cleaner_labels = {}

for n in sorted(z.namelist()):
    if not n.startswith(base) or not n.endswith(".xml"):
        continue
    try:
        _raw = z.read(n).decode("utf-8", "replace")
        root = ET.fromstring(_raw)
    except Exception as e:
        print("解析失败", n, e)
        continue
    osattr = (root.get("os") or "").lower()
    # 跨平台清理器（如 Chrome/Edge/Firefox/Discord）没有 os="windows" 属性，
    # 但其 <var> 指向 %LocalAppData% 等 Windows 路径；用原始文本判定是否 Windows 相关。
    win_marker = re.search(
        r"%LOCALAPPDATA%|%APPDATA%|%PROGRAMDATA%|%PROGRAMFILES|%USERPROFILE%|"
        r"%PUBLIC%|%WINDIR%|[A-Za-z]:\\\\", _raw, re.I)
    if osattr != "windows" and not win_marker:
        continue
    cid = root.get("id")
    clabel = (root.findtext("label") or cid).strip()
    cleaner_labels[cid] = clabel
    vars_ = {}
    for var in root.findall("var"):
        vn = var.get("name")
        vals = [v.text.strip() for v in var.findall("value") if v.text and v.text.strip()]
        if vn:
            vars_[vn] = vals
    for opt in root.findall("option"):
        oid = opt.get("id")
        olabel = (opt.findtext("label") or oid).strip()
        actions = []
        for a in opt.findall("action"):
            cmd = (a.get("command") or "").lower()
            if cmd not in ("delete", "shred"):
                continue
            search = (a.get("search") or "walk.files").lower()
            path = (a.get("path") or "").strip()
            if not path:
                continue
            actions.append((search, path))
        if not actions:
            continue
        # 风险：密码/凭据类标记“高”（默认不勾选，避免误删已保存登录）；
        # 其它隐私类（cookie/history/session/表单等）标记“中”；其余“低”。
        blob = (oid + " " + olabel).lower()
        if HIGH_KW.search(blob):
            risk = "高"
        elif PRIVACY_KW.search(blob):
            risk = "中"
        else:
            risk = "低"
        raw_specs.append((cid, clabel, oid, olabel, risk, actions, vars_))

print("原始 (cleaner,option) 文件清理条目数:", len(raw_specs))

# ---------- 路径解析（生成期，用于去重判定） ----------
ENV_FALL = {}
def env_resolve(val):
    def repl(mm):
        v = mm.group(1).upper()
        if v in ("PROGRAMFILES(X86)", "PROGRAMFILESX86"):
            return os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)"
        if v == "ALLUSERSPROFILE":
            return os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        if v == "COMMONPROGRAMFILES":
            return os.environ.get("COMMONPROGRAMFILES") or r"C:\Program Files\Common Files"
        if v == "COMMONPROGRAMFILES(X86)":
            return os.environ.get("COMMONPROGRAMFILES(X86)") or r"C:\Program Files (x86)\Common Files"
        ev = os.environ.get(v)
        if ev:
            return ev
        user = os.environ.get("USERPROFILE", "")
        fb = {
            "APPDATA": user + r"\AppData\Roaming",
            "LOCALAPPDATA": user + r"\AppData\Local",
            "USERPROFILE": user or r"C:\Users",
            "PUBLIC": r"C:\Users\Public",
            "PROGRAMDATA": r"C:\ProgramData",
            "PROGRAMFILES": r"C:\Program Files",
            "WINDIR": r"C:\Windows",
            "SYSTEMROOT": r"C:\Windows",
            "SYSTEMDRIVE": r"C:",
            "TMP": user + r"\AppData\Local\Temp",
            "TEMP": user + r"\AppData\Local\Temp",
            "HOMEDRIVE": r"C:",
        }
        return fb.get(v, mm.group(0))
    return re.sub(r"%([^%]+)%", repl, val)

def resolve_path(p, vars_):
    def vrep(mm):
        name = mm.group(1)
        vals = vars_.get(name)
        if vals:
            for v in vals:
                rv = env_resolve(v)
                if os.path.isdir(rv):
                    return rv
            return env_resolve(vals[0])
        return mm.group(0)
    p = re.sub(r"\$\$([^$]+)\$\$", vrep, p)
    p = env_resolve(p)
    p = p.replace("${users}", os.environ.get("USERPROFILE", r"C:\Users"))
    return p

def classify(resolved):
    """返回 (folder_dirs, glob_specs[(base,pattern)])。"""
    folder_dirs, glob_specs = [], []
    for rp in resolved:
        if "*" in rp:
            idx = rp.index("*")
            b = rp[:idx].rstrip("/\\")
            pat = rp[idx:]
            glob_specs.append((b, pat))
        else:
            d = rp.rstrip("/\\")
            folder_dirs.append(d)
    return folder_dirs, glob_specs

# ---------- 去重 + 生成最终条目 ----------
survivors = []          # 最终写入的 spec
seen_keys = set()       # 用于候选间去重
for cid, clabel, oid, olabel, risk, actions, vars_ in raw_specs:
    resolved = [resolve_path(p, vars_) for _, p in actions]
    folder_dirs, glob_specs = classify(resolved)
    # 候选间去重（相同目录集合只保留一次）
    key = (tuple(sorted(folder_dirs)), tuple(sorted(glob_specs)))
    if key in seen_keys:
        continue
    seen_keys.add(key)
    # 与现有项去重：若文件夹目录完全被现有项覆盖，且没有 glob 新增项，则跳过
    if folder_dirs and not glob_specs and existing_covers(set(d.lower() for d in folder_dirs)):
        # 但若有部分新增目录仍保留；此处仅当完全覆盖才跳过
        continue
    survivors.append({
        "c": cid, "cl": clabel, "o": oid, "ol": olabel,
        "r": risk,
        "acts": [(s, p) for s, p in actions],
        "v": vars_,
    })

print("去重后保留条目数:", len(survivors))

# 统计各 cleaner 贡献
from collections import Counter
cnt = Counter(s["c"] for s in survivors)
print("涉及 cleaner 数:", len(cnt))
for c, k in cnt.most_common():
    print(f"   {cleaner_labels.get(c, c):32} {k}")

# ---------- 写出 bleachbit_cleaners.py ----------
def py_str(s):
    return repr(s)

lines = []
lines.append("# -*- coding: utf-8 -*-")
lines.append('"""')
lines.append("本模块由 BleachBit 6.0.2 的 Windows 清理器配置（CleanerML）派生而来。")
lines.append("")
lines.append("版权：BleachBit (C) 2008-2025 Andrew Ziem 等，以 GNU GPL v3 许可发布。")
lines.append("原始 XML 配置位于 bleachbit-6.0.2/cleaners/，仅抽取 command=delete/shred 的")
lines.append("文件/目录清理动作；注册表(winreg)、SQLite 归档(vacuum)、ini/json/xml 等非文件")
lines.append("动作与现有清理框架不匹配，已省略。路径中的 %VAR% 与 $$var$$ 占位符在导入时解析，")
lines.append("以保证跨用户/机器可移植。")
lines.append('"""')
lines.append("import os")
lines.append("import re")
lines.append("")
lines.append("")
lines.append("# BleachBit <var> 表（cleaner -> {变量名: [候选值...]}），仅保存被用到的清理器")
lines.append("_BB_VARS = {")
for s in survivors:
    if s["v"]:
        lines.append(f"    {py_str(s['c'])}: {{")
        for vn, vals in s["v"].items():
            lines.append(f"        {py_str(vn)}: [{', '.join(py_str(x) for x in vals)}],")
        lines.append("    },")
lines.append("}")
lines.append("")
lines.append("")
lines.append("# 原始抽取结果：(cleaner_id, cleaner_label, option_id, option_label, risk, [(search, path)...])")
lines.append("# path 保留 BleachBit 占位符，导入时由 _bb_resolve() 解析。")
lines.append("_BB_RAW = [")
for s in survivors:
    acts = "[" + ", ".join(f"({py_str(se)}, {py_str(p)})" for se, p in s["acts"]) + "]"
    lines.append(f"    ({py_str(s['c'])}, {py_str(s['cl'])}, {py_str(s['o'])}, {py_str(s['ol'])}, {py_str(s['r'])}, {acts}),")
lines.append("]")
lines.append("")
lines.append("")
lines.append("def _bb_env(val):")
lines.append('    """解析 %VAR%（含 PROGRAMFILES(X86) 等）并做中文 locale 回退。"""')
lines.append("    def repl(mm):")
lines.append("        v = mm.group(1).upper()")
lines.append('        if v in ("PROGRAMFILES(X86)", "PROGRAMFILESX86"):')
lines.append('            return os.environ.get("PROGRAMFILES(X86)") or r"C:\\Program Files (x86)"')
lines.append('        if v == "ALLUSERSPROFILE":')
lines.append('            return os.environ.get("PROGRAMDATA") or r"C:\\ProgramData"')
lines.append('        if v == "COMMONPROGRAMFILES":')
lines.append('            return os.environ.get("COMMONPROGRAMFILES") or r"C:\\Program Files\\Common Files"')
lines.append('        if v == "COMMONPROGRAMFILES(X86)":')
lines.append('            return os.environ.get("COMMONPROGRAMFILES(X86)") or r"C:\\Program Files (x86)\\Common Files"')
lines.append("        ev = os.environ.get(v)")
lines.append("        if ev:")
lines.append("            return ev")
lines.append("        user = os.environ.get('USERPROFILE', '')")
lines.append("        fb = {")
lines.append('            "APPDATA": user + r"\\AppData\\Roaming",')
lines.append('            "LOCALAPPDATA": user + r"\\AppData\\Local",')
lines.append('            "USERPROFILE": user or r"C:\\Users",')
lines.append('            "PUBLIC": r"C:\\Users\\Public",')
lines.append('            "PROGRAMDATA": r"C:\\ProgramData",')
lines.append('            "PROGRAMFILES": r"C:\\Program Files",')
lines.append('            "WINDIR": r"C:\\Windows",')
lines.append('            "SYSTEMROOT": r"C:\\Windows",')
lines.append('            "SYSTEMDRIVE": r"C:",')
lines.append('            "TMP": user + r"\\AppData\\Local\\Temp",')
lines.append('            "TEMP": user + r"\\AppData\\Local\\Temp",')
lines.append('            "HOMEDRIVE": r"C:",')
lines.append("        }")
lines.append("        return fb.get(v, mm.group(0))")
lines.append("    return re.sub(r'%([^%]+)%', repl, val)")
lines.append("")
lines.append("")
lines.append("def _bb_resolve_path(p, vars_):")
lines.append('    """解析 $$var$$ 与 %VAR%，以及 ${users}。"""')
lines.append("    def vrep(mm):")
lines.append("        name = mm.group(1)")
lines.append("        vals = vars_.get(name)")
lines.append("        if vals:")
lines.append("            for v in vals:")
lines.append("                rv = _bb_env(v)")
lines.append("                if os.path.isdir(rv):")
lines.append("                    return rv")
lines.append("            return _bb_env(vals[0])")
lines.append("        return mm.group(0)")
lines.append("    p = re.sub(r'\\$\\$([^$]+)\\$\\$', vrep, p)")
lines.append("    p = _bb_env(p)")
lines.append("    p = p.replace('${users}', os.environ.get('USERPROFILE', r'C:\\Users'))")
lines.append("    return p")
lines.append("")
lines.append("")
lines.append("def _bb_classify(resolved):")
lines.append('    """把已解析路径分成文件夹目录与 glob 规格。"""')
lines.append("    folder_dirs, glob_specs = [], []")
lines.append("    for rp in resolved:")
lines.append("        if '*' in rp:")
lines.append("            idx = rp.index('*')")
lines.append("            b = rp[:idx].rstrip('/\\\\')")
lines.append("            pat = rp[idx:]")
lines.append("            glob_specs.append((b, pat))")
lines.append("        else:")
lines.append("            folder_dirs.append(rp.rstrip('/\\\\'))")
lines.append("    return folder_dirs, glob_specs")
lines.append("")
lines.append("")
lines.append("# 构建原生 CLEAN_ITEMS 条目")
lines.append("BLEACHBIT_CLEAN_ITEMS = []")
lines.append("for _c, _cl, _o, _ol, _r, _acts in _BB_RAW:")
lines.append("    _vars = _BB_VARS.get(_c, {})")
lines.append("    _resolved = [_bb_resolve_path(p, _vars) for _, p in _acts]")
lines.append("    _fdirs, _gspecs = _bb_classify(_resolved)")
lines.append("    _name = f'{_cl} - {_ol}'")
lines.append("    _detail = '; '.join(_resolved[:3])")
lines.append("    if len(_detail) > 120:")
lines.append("        _detail = _detail[:117] + '...'")
lines.append("    if _fdirs:")
lines.append("        BLEACHBIT_CLEAN_ITEMS.append({")
lines.append('            "id": f"bb_{_c}_{_o}",')
lines.append('            "name": _name,')
lines.append('            "detail": _detail,')
lines.append('            "type": "folder",')
lines.append('            "paths": _fdirs,')
lines.append('            "risk": _r,')
lines.append("        })")
lines.append("    # 按 base 合并 glob 规格；同一 option 可能跨多个 base，用序号区分 id 避免重复")
lines.append("    _gb = {}")
lines.append("    for _b, _pat in _gspecs:")
lines.append("        _gb.setdefault(_b, []).append(_pat)")
lines.append("    for _gi, (_b, _pats) in enumerate(_gb.items()):")
lines.append("        _suf = f'_{_gi}' if _gi > 0 else ''")
lines.append("        BLEACHBIT_CLEAN_ITEMS.append({")
lines.append('            "id": f"bb_{_c}_{_o}_g{_suf}",')
lines.append('            "name": _name + " (匹配文件)",')
lines.append('            "detail": _b,')
lines.append('            "type": "glob",')
lines.append('            "base": _b,')
lines.append('            "patterns": _pats,')
lines.append('            "risk": _r,')
lines.append("        })")
lines.append("")

out = "\n".join(lines)
with open(os.path.join(os.path.dirname(__file__), "bleachbit_cleaners.py"), "w", encoding="utf-8") as f:
    f.write(out)
print("已写出 bleachbit_cleaners.py，最终 BLEACHBIT_CLEAN_ITEMS 条目数（含 glob 拆分）将在导入时确定。")
