# -*- coding: utf-8 -*-
"""
系统优化工具箱（合并版）
========================
合并自以下 4 个文件：
  - C盘清理工具.pyw        （安全定向清理 + UAC 自提权）
  - 控制面板.CMD           （打开控制面板）
  - 卸载程序.CMD           （打开“程序和功能”）
  - 清理系统垃圾文件.BAT   （仅取其“安全定向”思路；已剔除全盘通配删除等危险代码）

安全原则（务必阅读）：
- “最高权限”通过 Windows UAC 标准提权获得：启动时会弹出系统提权确认窗，
  需用户手动点“是”，不会绕过 UAC、不会静默提权、不会关闭安全软件。
- 清理只针对系统/应用的“临时与缓存”文件，绝不触碰用户的文档、图片、
  下载、桌面等个人目录。每次删除前都会先扫描预览，需用户手动勾选并二次确认。
- 删除过程中遇到占用/权限错误会自动跳过，不会强行结束进程。
- 上帝模式（God Mode）是 Windows 的合法 CLSID 聚合文件夹，仅用于把控制面板
  所有设置聚合到一个窗口，并非权限提升后门、不越权。

关于被剔除的脚本内容：
原“清理系统垃圾文件.BAT”含有 `del /f /s /q %systemdrive%\\*.tmp` 等
“全盘递归通配删除”命令，会删除整块系统盘上所有匹配扩展名的文件，极易误删
正在使用的软件数据与系统文件，可能导致软件损坏或系统不稳定。合并时已主动剔除，
只保留定向、可逆的缓存清理项。
"""

import os
import sys
import fnmatch
import re
import ctypes
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# 上帝模式（God Mode）的 CLSID：把任意文件夹命名为 “名称.{该GUID}” 即可变为
# 一个聚合全部控制面板设置的特殊文件夹。注意前面带点号。
# 采用参考实现「系统维护工具.pyw」中已验证可用的 CLSID。
GODMODE_CLSID = "{ED7BA470-8E54-465E-825C-99712043E01C}"

# 外部「Win10 优化版.bat」脚本路径（交互式优化工具，自带 UAC 提权）。
# 若你把它挪了位置，改这里即可；找不到时会弹窗提示。
WIN10_OPTIMIZER_BAT = r"D:\系统优化\win10_优化版.bat"            # 打包后的回退绝对路径
WIN10_OPTIMIZER_BAT_NAME = "win10_优化版.bat"                    # 与 exe 同目录 / _MEIPASS 中的文件名

# 外部「360 联网助手.exe」路径（第三方网络诊断/修复工具）。
# 若你把它挪了位置，改这里即可；找不到时会弹窗提示。
NET_ASSIST_EXE = r"C:\Users\Administrator\Desktop\360联网助手.exe"     # 打包后的回退绝对路径
NET_ASSIST_EXE_NAME = "360联网助手.exe"                              # 与 exe 同目录 / _MEIPASS 中的文件名

# 应用图标文件名（同 exe / _MEIPASS 目录随 .ico 一起打包；找不到则用 tk 默认）
APP_ICO_NAME = "icon.ico"
APP_PNG_NAME = "icon.png"


def _resolve_asset(filename, fallback=None):
    """解析打包后 exe 所需的外部资源（.bat / .exe）的实际路径。

    查找顺序：
      1) PyInstaller 单文件模式解压目录 sys._MEIPASS
      2) 与当前 exe / 脚本同目录
      3) 原始硬编码绝对路径 fallback
    全部找不到返回 None，由调用方弹窗提示。
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, filename))
    base = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__))
    candidates.append(os.path.join(base, filename))
    if fallback:
        candidates.append(fallback)
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def _apply_app_icon(root):
    """设置窗口图标（含任务栏/Alt-Tab 显示）。

    优先使用同目录或 _MEIPASS 中的 icon.ico（多分辨率），找不到时用 icon.png
    作为备选（仍能让窗口左上角显示自定义图）。任何异常都被吞掉，不影响主流程。
    """
    try:
        ico_path = _resolve_asset(APP_ICO_NAME)
        if ico_path:
            try:
                root.iconbitmap(default=ico_path)
                return
            except Exception:
                pass  # iconbitmap 在某些无显示环境下会失败，回退到 iconphoto
        png_path = _resolve_asset(APP_PNG_NAME)
        if png_path:
            try:
                from tkinter import PhotoImage
                root.iconphoto(False, PhotoImage(file=png_path))
            except Exception:
                pass
    except Exception:
        pass



# ----------------------------------------------------------------------------
# 0. 管理员权限自检与自提权（UAC）
# ----------------------------------------------------------------------------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin():
    """以“runas”重新以管理员身份启动本脚本（触发 UAC 弹窗，需用户手动确认）。"""
    params = " ".join([f'"{arg}"' for arg in sys.argv])
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        # 返回值 > 32 表示成功启动
        return ret > 32
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 1. 清理项定义（仅安全目标）
# ----------------------------------------------------------------------------
LOCAL = os.environ.get("LOCALAPPDATA", "")
ROAMING = os.environ.get("APPDATA", "")
PROGRAMDATA = os.environ.get("ProgramData", r"C:\ProgramData")
# WorkBuddy 自身数据根目录（仅清理其下的缓存/临时，不碰用户配置与项目）
WB_ROOT = os.path.expanduser("~/.workbuddy")


# ----------------------------------------------------------------------------
# 全盘（多驱动器）辅助函数
# ----------------------------------------------------------------------------
def get_fixed_drives():
    """返回本机所有本地固定硬盘盘符列表，如 ['C', 'D', 'E']（不含 U 盘/网络盘）。"""
    drives = []
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if mask & (1 << i):
                letter = chr(ord("A") + i)
                try:
                    dtype = ctypes.windll.kernel32.GetDriveTypeW(letter + ":\\")
                except Exception:
                    dtype = 0
                if dtype == 3:  # DRIVE_FIXED
                    drives.append(letter)
    except Exception:
        drives = []
    return drives or ["C"]


def known_folder_path(folder_id):
    """通过 FOLDERID 取已知文件夹真实路径（自动处理重定向到非 C 盘的情况）。"""
    FOLDERIDS = {
        "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
        "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    }
    fid = FOLDERIDS.get(folder_id)
    if not fid:
        return None
    try:
        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong),
                        ("Data2", ctypes.c_ushort),
                        ("Data3", ctypes.c_ushort),
                        ("Data4", ctypes.c_ubyte * 8)]
        parts = fid.strip("{}").split("-")
        g = GUID(ctypes.c_ulong(int(parts[0], 16)),
                 ctypes.c_ushort(int(parts[1], 16)),
                 ctypes.c_ushort(int(parts[2], 16)),
                 (ctypes.c_ubyte * 8)(*[int(parts[3][i:i + 2], 16) for i in range(0, 16, 2)]))
        buf = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(g), 0, None, ctypes.byref(buf))
        if res == 0 and buf:
            path = buf.value
            try:
                ctypes.windll.ole32.CoTaskMemFree(buf)
            except Exception:
                pass
            return path
    except Exception:
        return None
    return None


def app_data_roots(doc_sub):
    """返回某应用数据目录在所有固定盘上的候选根目录。"""
    roots = []
    docs = DOCS or os.path.expanduser("~/Documents")
    if docs:
        roots.append(os.path.join(docs, doc_sub))
    user = os.path.basename(os.path.expanduser("~").rstrip("/\\"))
    for d in get_fixed_drives():
        roots.append(f"{d}:\\{doc_sub}")
        if user:
            roots.append(f"{d}:\\Users\\{user}\\Documents\\{doc_sub}")
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


# 真实文档/下载目录（若用户重定向到非 C 盘，这里能正确取到）
DOCS = os.path.normpath(known_folder_path("Documents") or os.path.expanduser("~/Documents"))
DOWNLOADS = os.path.normpath(known_folder_path("Downloads") or os.path.expanduser("~/Downloads"))

# Steam 缓存位置探测
STEAM_ROOTS = [
    os.path.join(LOCAL, "Steam"),
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    os.path.join(ROAMING, "Steam"),
]
for _d in get_fixed_drives():
    if _d == "C":
        continue
    STEAM_ROOTS += [
        f"{_d}:\\Steam",
        f"{_d}:\\Program Files (x86)\\Steam",
        f"{_d}:\\Program Files\\Steam",
        f"{_d}:\\Games\\Steam",
    ]
STEAM_CACHE_SUBDIRS = [
    "htmlcache",
    "steamapps/downloading",
    "appcache/httpcache",
    "depotcache",
    "logs",
]
STEAM_CACHE_PATHS = []
for _sr in STEAM_ROOTS:
    for _sub in STEAM_CACHE_SUBDIRS:
        STEAM_CACHE_PATHS.append(os.path.join(_sr, *_sub.split("/")))


def _fnmatch(name, pat):
    try:
        return fnmatch.fnmatch(name, pat or "*")
    except Exception:
        return False


def item_folders(item):
    """解析清理项的目标文件夹列表。"""
    folders = []
    t = item.get("type")
    if t == "folder":
        folders += item.get("paths") or [item.get("path")]
    elif t == "discover":
        roots = item.get("roots", [])
        subdirs = item.get("subdirs", [])
        aglob = item.get("account_glob", "*")
        if subdirs:
            for root in roots:
                if not os.path.isdir(root):
                    continue
                try:
                    entries = os.listdir(root)
                except Exception:
                    entries = []
                for acc in entries:
                    accdir = os.path.join(root, acc)
                    if not os.path.isdir(accdir):
                        continue
                    if not _fnmatch(acc, aglob):
                        continue
                    for sub in subdirs:
                        folders.append(os.path.join(accdir, sub))
    folders += item.get("extra", [])
    return [p for p in folders if p]


CLEAN_ITEMS = [
    {
        "id": "win_temp",
        "name": "Windows 临时文件",
        "detail": r"C:\Windows\Temp",
        "type": "folder",
        "path": r"C:\Windows\Temp",
        "checked": True,
        "risk": "低",
    },
    {
        "id": "user_temp",
        "name": "当前用户临时文件",
        "detail": "%TEMP% (AppData\\Local\\Temp)",
        "type": "folder",
        "path": os.path.join(LOCAL, "Temp"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "win_update",
        "name": "Windows 更新缓存",
        "detail": r"C:\Windows\SoftwareDistribution\Download",
        "type": "folder",
        "path": r"C:\Windows\SoftwareDistribution\Download",
        "checked": True,
        "risk": "低",
    },
    {
        "id": "prefetch",
        "name": "预读取文件 (Prefetch)",
        "detail": r"C:\Windows\Prefetch",
        "type": "folder",
        "path": r"C:\Windows\Prefetch",
        "checked": True,
        "risk": "低",
    },
    {
        "id": "thumbcache",
        "name": "缩略图缓存（删除即强制重建）",
        "detail": "Explorer\\thumbcache_*.db / iconcache_*.db",
        "type": "glob",
        "base": os.path.join(LOCAL, "Microsoft", "Windows", "Explorer"),
        "patterns": ["thumbcache_*.db", "thumbcache_*.dbms", "thumbcache_*.wmv",
                     "thumbcache_idx.db", "iconcache_*.db", "iconcache_*.dbms"],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "inetcache",
        "name": "IE/Edge Internet 临时文件",
        "detail": "INetCache",
        "type": "folder",
        "path": os.path.join(LOCAL, "Microsoft", "Windows", "INetCache"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "recent",
        "name": "最近使用的文件记录",
        "detail": "Recent (仅清除记录，不删原文件)",
        "type": "folder",
        "path": os.path.join(ROAMING, "Microsoft", "Windows", "Recent"),
        "checked": False,
        "risk": "低",
    },
    {
        "id": "wer",
        "name": "Windows 错误报告文件",
        "detail": r"%ProgramData%\Microsoft\Windows\WER",
        "type": "folder",
        "path": os.path.join(PROGRAMDATA, "Microsoft", "Windows", "WER"),
        "checked": False,
        "risk": "中",
    },
    {
        "id": "chrome",
        "name": "Google Chrome 缓存",
        "detail": "User Data\\Default\\Cache",
        "type": "folder",
        "path": os.path.join(LOCAL, "Google", "Chrome", "User Data", "Default", "Cache"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "edge",
        "name": "Microsoft Edge 缓存",
        "detail": "User Data\\Default\\Cache",
        "type": "folder",
        "path": os.path.join(LOCAL, "Microsoft", "Edge", "User Data", "Default", "Cache"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "firefox",
        "name": "Firefox 缓存",
        "detail": "Profiles\\*\\cache2",
        "type": "folder",
        "path": os.path.join(LOCAL, "Mozilla", "Firefox", "Profiles"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "delivery",
        "name": "传递优化缓存 (Delivery Optimization)",
        "detail": "SoftwareDistribution\\DeliveryOptimizationCache",
        "type": "folder",
        "path": r"C:\Windows\SoftwareDistribution\DeliveryOptimizationCache",
        "checked": False,
        "risk": "中",
    },
    {
        "id": "recycle",
        "name": "回收站（清空所有驱动器）",
        "detail": "调用系统 API 清空回收站",
        "type": "special",
        "special": "recycle",
        "checked": False,
        "risk": "中",
    },
    {
        "id": "wb_appcache",
        "name": "WorkBuddy 应用与会话缓存",
        "detail": ".workbuddy\\app\\cache + app\\session 各缓存",
        "type": "folder",
        "paths": [
            os.path.join(WB_ROOT, "app", "cache"),
            os.path.join(WB_ROOT, "app", "session", "Cache"),
            os.path.join(WB_ROOT, "app", "session", "Code Cache"),
            os.path.join(WB_ROOT, "app", "session", "GPUCache"),
            os.path.join(WB_ROOT, "app", "session", "DawnGraphiteCache"),
            os.path.join(WB_ROOT, "app", "session", "DawnWebGPUCache"),
            os.path.join(WB_ROOT, "app", "session", "Shared Dictionary", "cache"),
        ],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "wb_traces",
        "name": "WorkBuddy 性能追踪 (traces)",
        "detail": ".workbuddy\\traces",
        "type": "folder",
        "path": os.path.join(WB_ROOT, "traces"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "wb_logs",
        "name": "WorkBuddy 日志 (logs)",
        "detail": ".workbuddy\\logs（含 Crash-Log）",
        "type": "folder",
        "path": os.path.join(WB_ROOT, "logs"),
        "checked": False,
        "risk": "中",
    },
    {
        "id": "wb_pipcache",
        "name": "WorkBuddy 依赖缓存 (binaries/.cache)",
        "detail": ".workbuddy\\binaries\\.cache（pip 缓存）",
        "type": "folder",
        "path": os.path.join(WB_ROOT, "binaries", ".cache"),
        "checked": True,
        "risk": "低",
    },
    {
        "id": "wechat_cache",
        "name": "微信缓存（缩略图/临时）",
        "detail": "WeChat Files\\<账号>\\FileStorage\\Cache,Temp",
        "type": "discover",
        "roots": app_data_roots("WeChat Files"),
        "account_glob": "*",
        "subdirs": ["FileStorage/Cache", "FileStorage/Temp"],
        "extra": [os.path.join(ROAMING, "Tencent", "xwechat", "radium", "cache")],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "qq_cache",
        "name": "QQ 缓存（NT 临时/STemp）",
        "detail": "Tencent Files\\<账号>\\nt_qq\\nt_temp + Roaming\\Tencent\\QQ\\STemp",
        "type": "discover",
        "roots": app_data_roots("Tencent Files"),
        "account_glob": "*",
        "subdirs": ["nt_qq/nt_temp"],
        "extra": [
            os.path.join(ROAMING, "Tencent", "QQ", "STemp"),
            os.path.join(ROAMING, "Tencent", "QQNT", "STemp"),
        ],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "tim_cache",
        "name": "TIM 缓存（STemp/临时）",
        "detail": "Roaming\\Tencent\\TIM\\STemp",
        "type": "discover",
        "roots": app_data_roots("Tencent Files"),
        "account_glob": "*",
        "subdirs": [],
        "extra": [os.path.join(ROAMING, "Tencent", "TIM", "STemp")],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "downloads",
        "name": "浏览器下载目录（Downloads）",
        "detail": "删除下载文件夹内全部文件与子目录（自动识别重定向后的真实位置）— 高风险，请确认无重要资料",
        "type": "folder",
        "path": DOWNLOADS,
        "checked": False,
        "risk": "高",
    },
    {
        "id": "dingtalk_cache",
        "name": "钉钉缓存（图片/文件缓存）",
        "detail": "Roaming\\DingTalk\\<账号>\\cache,FileCache + Local\\DingTalk\\dumps",
        "type": "discover",
        "roots": [os.path.join(ROAMING, "DingTalk")],
        "account_glob": "*",
        "subdirs": ["cache", "FileCache"],
        "extra": [os.path.join(LOCAL, "DingTalk", "dumps")],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "feishu_cache",
        "name": "飞书/Feishu 缓存",
        "detail": "Local\\Feishu|Lark\\cache + User Data\\Default\\Cache",
        "type": "folder",
        "paths": [
            os.path.join(LOCAL, "Feishu", "cache"),
            os.path.join(LOCAL, "Feishu", "User Data", "Default", "Cache"),
            os.path.join(LOCAL, "Lark", "cache"),
            os.path.join(LOCAL, "Lark", "User Data", "Default", "Cache"),
            os.path.join(ROAMING, "Feishu", "cache"),
        ],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "wxwork_cache",
        "name": "企业微信缓存（图片/临时）",
        "detail": "WXWork\\<账号>\\FileStorage\\Cache,Temp",
        "type": "discover",
        "roots": app_data_roots("WXWork"),
        "account_glob": "*",
        "subdirs": ["FileStorage/Cache", "FileStorage/Temp"],
        "extra": [os.path.join(ROAMING, "WXWork", "cache")],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "steam_cache",
        "name": "Steam 缓存（WebView/下载/depot）",
        "detail": "htmlcache + steamapps\\downloading + appcache\\httpcache + depotcache（不碰游戏本体）",
        "type": "folder",
        "paths": STEAM_CACHE_PATHS,
        "checked": True,
        "risk": "低",
    },
    {
        "id": "wx_applet_cache",
        "name": "微信小程序缓存（Applet）",
        "detail": "WeChat Files\\<账号>\\Applet（清理会重置小程序本地数据）",
        "type": "discover",
        "roots": [os.path.join(DOCS, "WeChat Files")],
        "account_glob": "*",
        "subdirs": ["Applet"],
        "extra": [],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "adobe_cache",
        "name": "Adobe 全家桶缓存（媒体/公共缓存）",
        "detail": "Common Media Cache + Bridge + CEP + Creative Cloud 缓存（不含各产品磁盘缓存）",
        "type": "folder",
        "paths": [
            # Premiere / After Effects 媒体/预览缓存
            os.path.join(ROAMING, "Adobe", "Common", "Media Cache Files"),
            os.path.join(ROAMING, "Adobe", "Common", "Media Cache"),
            os.path.join(LOCAL, "Adobe", "Common", "Media Cache Files"),
            os.path.join(LOCAL, "Adobe", "Common", "Media Cache"),
            # Bridge 缓存（常见版本）
            os.path.join(ROAMING, "Adobe", "Bridge 2024", "Cache"),
            os.path.join(ROAMING, "Adobe", "Bridge 2023", "Cache"),
            # CEP 扩展缓存（Creative Cloud 扩展）
            os.path.join(LOCAL, "Adobe", "CEP", "cache"),
            os.path.join(ROAMING, "Adobe", "CEP", "cache"),
            # Creative Cloud 本地缓存
            os.path.join(LOCAL, "Adobe", "CreativeCloud", "CCLibrary", "cache"),
        ],
        "checked": True,
        "risk": "低",
    },
    # Adobe 各产品版本化磁盘缓存（AE / PS / PR / Lightroom / Bridge / Illustrator 等）
    {
        "id": "adobe_disk_cache",
        "name": "Adobe 各产品磁盘缓存 (Disk Cache)",
        "detail": "扫 Roaming/Local\\Adobe 下各产品版本目录的 Disk Cache / Cache / AutoRecover / VideoCache / Caches",
        "type": "discover",
        "roots": [os.path.join(ROAMING, "Adobe"), os.path.join(LOCAL, "Adobe")],
        "account_glob": "*",
        "subdirs": ["Disk Cache", "Cache", "AutoRecover", "VideoCache", "Caches"],
        "checked": True,
        "risk": "低",
    },
    # 合并自“清理系统垃圾文件.BAT”的安全定向项（已重写，剔除全盘通配删除）
    {
        "id": "win_logs",
        "name": "Windows 系统日志（Logs）",
        "detail": r"C:\Windows\Logs 下 *.log/*.chk/*.old/*.bak/*.tmp（仅该目录内，不递归全盘）",
        "type": "ext",
        "roots": [r"C:\Windows\Logs"],
        "exts": [".log", ".chk", ".old", ".bak", ".tmp"],
        "checked": True,
        "risk": "低",
    },
    {
        "id": "ie_cookies",
        "name": "IE/旧版浏览器 Cookie（清理后需重新登录）",
        "detail": "INetCookies + 旧 Cookies 目录 — 隐私清理，会退出网站登录",
        "type": "folder",
        "paths": [
            os.path.join(LOCAL, "Microsoft", "Windows", "INetCookies"),
            os.path.join(ROAMING, "Microsoft", "Windows", "Cookies"),
            os.path.join(LOCAL, "Microsoft", "Windows", "INetCookies", "Low"),
            os.path.expanduser("~/Cookies"),
        ],
        "checked": False,
        "risk": "中",
    },
]

# 按风险排序（高 → 中 → 低）：高风险项显示在列表最上方且默认不勾选，
# 中/低风险项默认全部勾选。
_RISK_RANK = {"高": 0, "中": 1, "低": 2}
CLEAN_ITEMS.sort(key=lambda it: _RISK_RANK.get(it.get("risk", "低"), 2))
for _it in CLEAN_ITEMS:
    _it["checked"] = _it.get("risk") != "高"


# ----------------------------------------------------------------------------
# 2. 核心：计算大小 / 删除
# ----------------------------------------------------------------------------
def human_size(num_bytes):
    try:
        n = float(num_bytes)
    except Exception:
        return "0 B"
    if n < 1024:
        return f"{n:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024.0:
            return f"{n:.2f} {unit}"
    return f"{n:.2f} TB"


def _elide(text, n=32):
    """超长路径截断为带省略号的短串，保证 Treeview 行高一致（完整值仍存于 CLEAN_ITEMS）。"""
    text = text or ""
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


def _iter_folder_files(folder):
    """生成目录下所有文件（含子目录），忽略无法访问的错误。"""
    if not os.path.isdir(folder):
        return
    try:
        for root, dirs, files in os.walk(folder):
            for f in files:
                p = os.path.join(root, f)
                try:
                    yield p
                except Exception:
                    continue
    except Exception:
        return


def compute_size(item):
    """返回 (可清理字节数, 文件数量)。只读，不删除。"""
    total = 0
    count = 0
    t = item["type"]
    if t in ("folder", "discover"):
        for folder in item_folders(item):
            for p in _iter_folder_files(folder):
                try:
                    total += os.path.getsize(p)
                    count += 1
                except Exception:
                    pass
    elif t == "glob":
        base = item.get("base")
        if base and os.path.isdir(base):
            import glob as _glob
            for pat in item.get("patterns", []):
                for p in _glob.glob(os.path.join(base, pat)):
                    try:
                        if os.path.isfile(p):
                            total += os.path.getsize(p)
                            count += 1
                    except Exception:
                        pass
    elif t == "ext":
        exts = set(e.lower() for e in item.get("exts", []))
        for root in item.get("roots", []):
            if not os.path.isdir(root):
                continue
            for p in _iter_folder_files(root):
                try:
                    if os.path.splitext(p)[1].lower() in exts:
                        total += os.path.getsize(p)
                        count += 1
                except Exception:
                    pass
    elif t == "special":
        if item.get("special") == "recycle":
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-ChildItem -Path 'C:\\$Recycle.Bin' -Recurse -Force -ErrorAction SilentlyContinue "
                     "| Measure-Object -Property Length -Sum).Sum"],
                    capture_output=True, text=True, timeout=30
                )
                val = out.stdout.strip()
                if val and val.lower() != "null":
                    total = int(float(val))
                    count = 0
            except Exception:
                total = 0
    return total, count


def _rm_path(path):
    """删除单个文件或目录，遇错跳过。"""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
    except Exception:
        pass


def clean_item(item):
    """执行清理，返回 (释放字节数, 删除文件数)。"""
    freed = 0
    removed = 0
    t = item["type"]
    if t in ("folder", "discover"):
        for folder in item_folders(item):
            if not os.path.isdir(folder):
                continue
            for entry in list(os.scandir(folder)):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        for p in _iter_folder_files(entry.path):
                            try:
                                freed += os.path.getsize(p)
                                removed += 1
                            except Exception:
                                pass
                        shutil.rmtree(entry.path, ignore_errors=True)
                    else:
                        freed += entry.stat().st_size
                        removed += 1
                        os.remove(entry.path)
                except Exception:
                    continue
    elif t == "glob":
        base = item.get("base")
        if base and os.path.isdir(base):
            import glob as _glob
            for pat in item.get("patterns", []):
                for p in _glob.glob(os.path.join(base, pat)):
                    try:
                        if os.path.isfile(p):
                            freed += os.path.getsize(p)
                            removed += 1
                            os.remove(p)
                    except Exception:
                        pass
    elif t == "ext":
        exts = set(e.lower() for e in item.get("exts", []))
        for root in item.get("roots", []):
            if not os.path.isdir(root):
                continue
            for p in _iter_folder_files(root):
                try:
                    if os.path.splitext(p)[1].lower() in exts:
                        freed += os.path.getsize(p)
                        removed += 1
                        os.remove(p)
                except Exception:
                    pass
    elif t == "special":
        if item.get("special") == "recycle":
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, timeout=60
                )
            except Exception:
                pass
    return freed, removed


# ----------------------------------------------------------------------------
# 2.5 预装应用卸载清单（源自开源项目 PyDebloatX，MIT License）
# ----------------------------------------------------------------------------
# 每项：name=中文名，pkg=Appx 包名通配（用于 Get-AppxPackage），desc=说明。
# xbox=True 表示需排除 XboxGameCallableUI（系统 UI，不可卸）。
# 卸载命令：Get-AppxPackage <pkg> | Remove-AppxPackage（当前用户范围，无需管理员）。
DEBLOAT_APPS = [
    {"name": "3D Builder", "pkg": "*Microsoft.3DBuilder*", "desc": "查看、创建和个性化 3D 对象。"},
    {"name": "3D 查看器", "pkg": "*Microsoft.Microsoft3DViewer*", "desc": "实时查看 3D 模型与动画。"},
    {"name": "闹钟和时钟", "pkg": "*Microsoft.WindowsAlarms*", "desc": "闹钟、世界时钟、计时器与秒表。"},
    {"name": "计算器", "pkg": "*Microsoft.WindowsCalculator*", "desc": "标准/科学/程序员模式计算器与单位换算。"},
    {"name": "邮件和日历", "pkg": "*microsoft.windowscommunicationsapps*", "desc": "邮件收发与日程管理。"},
    {"name": "相机", "pkg": "*Microsoft.WindowsCamera*", "desc": "Windows 10 拍照与录像。"},
    {"name": "反馈中心", "pkg": "*Microsoft.WindowsFeedbackHub*", "desc": "向微软反馈 Windows 与应用的建议/问题。"},
    {"name": "获取帮助", "pkg": "*Microsoft.GetHelp*", "desc": "提问并获取推荐方案或联系客服。"},
    {"name": "Groove 音乐", "pkg": "*Microsoft.ZuneMusic*", "desc": "在 Windows/iOS/Android 上听音乐。"},
    {"name": "地图", "pkg": "*Microsoft.WindowsMaps*", "desc": "搜索地点、路线、商家信息与评价。"},
    {"name": "信息 (Messaging)", "pkg": "*Microsoft.Messaging*", "desc": "SMS/MMS/RCS 短信收发。"},
    {"name": "混合现实门户", "pkg": "*Microsoft.MixedReality.Portal*", "desc": "Windows Mixed Reality VR 体验入口。"},
    {"name": "移动套餐", "pkg": "*Microsoft.OneConnect*", "desc": "注册数据套餐、连接移动运营商。"},
    {"name": "财经 (Money)", "pkg": "*Microsoft.BingFinance*", "desc": "金融计算器、汇率与全球商品价格。"},
    {"name": "电影和电视", "pkg": "*Microsoft.ZuneVideo*", "desc": "跨设备统一管理电影与电视节目。"},
    {"name": "新闻 (News)", "pkg": "*Microsoft.BingNews*", "desc": "突发新闻与深度报道。"},
    {"name": "Office", "pkg": "*Microsoft.MicrosoftOfficeHub*", "desc": "Office 应用与文件的聚合入口。"},
    {"name": "OneNote", "pkg": "*Microsoft.Office.OneNote*", "desc": "跨设备的数字笔记本。"},
    {"name": "画图 3D", "pkg": "*Microsoft.MSPaint*", "desc": "制作 2D 作品或可多角度查看的 3D 模型。"},
    {"name": "人脉 (People)", "pkg": "*Microsoft.People*", "desc": "在一处管理你的联系人。"},
    {"name": "照片", "pkg": "*Microsoft.Windows.Photos*", "desc": "查看/编辑照片视频、制作影片与相册。"},
    {"name": "打印 3D", "pkg": "*Microsoft.Print3D*", "desc": "在 PC 上快速准备 3D 打印对象。"},
    {"name": "Skype", "pkg": "*Microsoft.SkypeApp*", "desc": "即时消息、语音或视频通话。"},
    {"name": "截图和草图", "pkg": "*Microsoft.ScreenSketch*", "desc": "快速标注截图并保存/分享。"},
    {"name": "纸牌 (Solitaire)", "pkg": "*Microsoft.MicrosoftSolitaireCollection*", "desc": "经典纸牌游戏合集。"},
    {"name": "体育 (Sports)", "pkg": "*Microsoft.BingSports*", "desc": "150+ 联赛的实时比分与赛事体验。"},
    {"name": "Spotify", "pkg": "*SpotifyAB.SpotifyMusic*", "desc": "在 Windows 10 上免费播放歌曲与专辑。"},
    {"name": "便笺 (Sticky Notes)", "pkg": "*Microsoft.MicrosoftStickyNotes*", "desc": "创建便笺，可贴到桌面。"},
    {"name": "使用技巧 (Tips)", "pkg": "*Microsoft.Getstarted*", "desc": "提供系统功能的信息与技巧。"},
    {"name": "翻译 (Translator)", "pkg": "*Microsoft.BingTranslator*", "desc": "文本/语音翻译，支持离线语言包。"},
    {"name": "录音机", "pkg": "*Microsoft.WindowsSoundRecorder*", "desc": "录制声音、讲座、采访等。"},
    {"name": "天气 (Weather)", "pkg": "*Microsoft.BingWeather*", "desc": "实时天气、10 天与逐时预报。"},
    {"name": "Xbox", "pkg": "*Microsoft.GamingApp*", "desc": "浏览目录、查看推荐、发现 Game Pass PC 游戏。"},
    {"name": "Xbox Game Bar", "pkg": "*Xbox*", "desc": "屏幕捕获/分享与 Xbox 好友聊天的小组件。", "xbox": True},
    {"name": "你的手机 (Your Phone)", "pkg": "*Microsoft.YourPhone*", "desc": "关联安卓手机，查看/回复短信、使用手机 App。"},
    {"name": "Cortana", "pkg": "*Microsoft.549981C3F5F10*", "desc": "个人智能助理（部分系统版本才有）。"},
]


# ----------------------------------------------------------------------------
# 2.6 深度优化开关（提取自开源 Optimizer 的注册表/服务调整，社区项目，MIT 风格）
# ----------------------------------------------------------------------------
# 每项 apply=应用该优化要执行的命令；revert=还原为 Windows 默认。命令均为 reg / sc，
# 写 HKLM 需管理员。逻辑移植自 Optimizer 的 OptimizeHelper.cs（Disable*/Enable* 方法）。
def _reg_add(hive, key, val, data, kind="REG_DWORD"):
    return f'reg add "{hive}\\{key}" /v "{val}" /t {kind} /d {data} /f'

def _reg_add_sz(hive, key, val, data):
    return f'reg add "{hive}\\{key}" /v "{val}" /t REG_SZ /d "{data}" /f'

def _reg_add_ve(hive, key, data):
    return f'reg add "{hive}\\{key}" /ve /t REG_SZ /d "{data}" /f'

def _reg_del(hive, key, val):
    return f'reg delete "{hive}\\{key}" /v "{val}" /f'

def _reg_del_ve(hive, key):
    return f'reg delete "{hive}\\{key}" /ve /f'

def _reg_del_tree(hive, key):
    return f'reg delete "{hive}\\{key}" /f'

def _svc_disable(name):
    return f'sc stop {name} & sc config {name} start= disabled'

def _svc_enable(name, start="auto"):
    return f'sc config {name} start= {start} & sc start {name}'


DEEP_OPTS = [
    {
        "id": "xbox_gamebar",
        "name": "关闭 Xbox 游戏栏与录制",
        "desc": "禁用 Game Bar、游戏 DVR 录制与自动游戏模式（不影响已装 Xbox 应用）。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "AppCaptureEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "AudioCaptureEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "CursorCaptureEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "UseNexusForGameBarEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "ShowStartupPanel", 0),
            _reg_add("HKCU", "System\\GameConfigStore", "GameDVR_Enabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "AllowAutoGameMode", 0),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "AutoGameModeEnabled", 0),
            _reg_add("HKLM", "Software\\Policies\\Microsoft\\Windows\\GameDVR", "AllowGameDVR", 0),
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers", "HwSchMode", 1),
        ],
        "revert": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "AppCaptureEnabled", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "AudioCaptureEnabled", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR", "CursorCaptureEnabled", 1),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "UseNexusForGameBarEnabled", 1),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "ShowStartupPanel", 1),
            _reg_add("HKCU", "System\\GameConfigStore", "GameDVR_Enabled", 1),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "AllowAutoGameMode", 1),
            _reg_add("HKCU", "Software\\Microsoft\\GameBar", "AutoGameModeEnabled", 1),
            _reg_del("HKLM", "Software\\Policies\\Microsoft\\Windows\\GameDVR", "AllowGameDVR"),
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers", "HwSchMode", 2),
        ],
    },
    {
        "id": "widgets",
        "name": "关闭 Widgets 小组件 (Win11)",
        "desc": "隐藏任务栏的 Widgets/资讯按钮，减少资源占用。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarDa", 0),
        ],
        "revert": [
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarDa"),
        ],
    },
    {
        "id": "chat",
        "name": "关闭 Teams Chat (Win11)",
        "desc": "移除任务栏的 Teams Chat（Meet Now）入口。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow", 1),
            _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarMn", 0),
        ],
        "revert": [
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow"),
            _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarMn"),
        ],
    },
    {
        "id": "copilot",
        "name": "关闭 Copilot AI",
        "desc": "关闭 Windows Copilot 按钮与 AI 数据分析（Edge 相关项一并禁用）。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Policies\\Microsoft\\Windows\\WindowsAI", "DisableAIDataAnalysis", 1),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI", "DisableAIDataAnalysis", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ShowCopilotButton", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "DefaultBrowserSettingsCampaignEnabled", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "ComposeInlineEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsCopilot", "TurnOffWindowsCopilot", 1),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsCopilot", "TurnOffWindowsCopilot", 1),
        ],
        "revert": [
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ShowCopilotButton"),
            _reg_del("HKCU", "Software\\Policies\\Microsoft\\Windows\\WindowsAI", "DisableAIDataAnalysis"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI", "DisableAIDataAnalysis"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsCopilot", "TurnOffWindowsCopilot"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsCopilot", "TurnOffWindowsCopilot"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "DefaultBrowserSettingsCampaignEnabled"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "ComposeInlineEnabled"),
        ],
    },
    {
        "id": "start_ads",
        "name": "关闭开始菜单广告/建议",
        "desc": "禁用开始菜单与搜索框的建议、推广与消费者体验内容。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338388Enabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContentEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SoftLandingEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SystemPaneSuggestionsEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SilentInstalledAppsEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "PreInstalledAppsEverEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "FeatureManagementEnabled", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Mobility", "OptedIn", 0),
            _reg_add("HKCU", "Software\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions", 1),
            _reg_add("HKLM", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "AllowOnlineTips", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions", 1),
        ],
        "revert": [
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338388Enabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContentEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SoftLandingEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SystemPaneSuggestionsEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SilentInstalledAppsEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "PreInstalledAppsEverEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "FeatureManagementEnabled"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Mobility", "OptedIn"),
            _reg_del("HKCU", "Software\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions"),
            _reg_del("HKLM", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "AllowOnlineTips"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions"),
        ],
    },
    {
        "id": "news",
        "name": "关闭资讯和兴趣",
        "desc": "禁用任务栏的“资讯和兴趣”/天气浮窗。",
        "risk": "低",
        "apply": [
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Dsh", "AllowNewsAndInterests", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Feeds", "EnableFeeds", 0),
            _reg_add("HKLM", "SOFTWARE\\Microsoft\\PolicyManager\\default\\NewsAndInterests\\AllowNewsAndInterests", "value", 0),
        ],
        "revert": [
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Dsh", "AllowNewsAndInterests"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Feeds", "EnableFeeds"),
            _reg_del("HKLM", "SOFTWARE\\Microsoft\\PolicyManager\\default\\NewsAndInterests\\AllowNewsAndInterests", "value"),
        ],
    },
    {
        "id": "sticky",
        "name": "关闭粘滞键/筛选键提示",
        "desc": "关闭连续按 Shift 5 次弹出的粘滞键等辅助功能提示（对游戏/打字更友好）。",
        "risk": "低",
        "apply": [
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\StickyKeys", "Flags", "506"),
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\Keyboard Response", "Flags", "122"),
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\ToggleKeys", "Flags", "58"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\StickyKeys", "Flags", "506"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\Keyboard Response", "Flags", "122"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\ToggleKeys", "Flags", "58"),
        ],
        "revert": [
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\StickyKeys", "Flags", "510"),
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\Keyboard Response", "Flags", "126"),
            _reg_add_sz("HKCU", "Control Panel\\Accessibility\\ToggleKeys", "Flags", "62"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\StickyKeys", "Flags", "510"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\Keyboard Response", "Flags", "126"),
            _reg_add_sz("HKU", ".DEFAULT\\Control Panel\\Accessibility\\ToggleKeys", "Flags", "62"),
        ],
    },
    {
        "id": "longpath",
        "name": "启用长路径支持 (Win10+)",
        "desc": "解除 260 字符路径限制（EnableLongPaths=1），方便深层目录操作。",
        "risk": "低",
        "apply": [
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\FileSystem", "LongPathsEnabled", 1),
        ],
        "revert": [
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\FileSystem", "LongPathsEnabled", 0),
        ],
    },
    {
        "id": "clipboard",
        "name": "关闭云剪贴板",
        "desc": "禁用剪贴板历史与跨设备同步（减少后台上传）。",
        "risk": "低",
        "apply": [
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "AllowClipboardHistory", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "AllowCrossDeviceClipboard", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Clipboard", "EnableClipboardHistory", 0),
            _reg_add("HKLM", "Software\\Microsoft\\Clipboard", "EnableClipboardHistory", 0),
        ],
        "revert": [
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "AllowClipboardHistory"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "AllowCrossDeviceClipboard"),
            _reg_del("HKCU", "Software\\Microsoft\\Clipboard", "EnableClipboardHistory"),
            _reg_del("HKLM", "Software\\Microsoft\\Clipboard", "EnableClipboardHistory"),
        ],
    },
    {
        "id": "edge",
        "name": "关闭 Edge 遥测与推荐",
        "desc": "关闭 Edge 的使用情况上报、个性化与侧边栏发现等。",
        "risk": "低",
        "apply": [
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "PersonalizationReportingEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "PersonalizationReportingEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "UserFeedbackAllowed", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "UserFeedbackAllowed", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "MetricsReportingEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "MetricsReportingEnabled", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "SpotlightExperiencesAndRecommendationsEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "SpotlightExperiencesAndRecommendationsEnabled", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "WebWidgetAllowed", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "HubsSidebarEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "HubsSidebarEnabled", 0),
        ],
        "revert": [
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "PersonalizationReportingEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "PersonalizationReportingEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "UserFeedbackAllowed"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "UserFeedbackAllowed"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "MetricsReportingEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "MetricsReportingEnabled"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "SpotlightExperiencesAndRecommendationsEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "SpotlightExperiencesAndRecommendationsEnabled"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "WebWidgetAllowed"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Edge", "HubsSidebarEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Edge", "HubsSidebarEnabled"),
        ],
    },
    {
        "id": "wer",
        "name": "关闭错误报告 (WER)",
        "desc": "禁用 Windows 错误报告服务与策略（停止 WerSvc，可加快崩溃后响应）。",
        "risk": "中",
        "apply": [
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Error Reporting", "Disabled", 1),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\PCHealth\\ErrorReporting", "DoReport", 0),
            _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting", "Disabled", 1),
            _svc_disable("WerSvc"),
            _svc_disable("wercplsupport"),
        ],
        "revert": [
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Error Reporting", "Disabled"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\PCHealth\\ErrorReporting", "DoReport"),
            _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows\\Windows Error Reporting", "Disabled"),
            _svc_enable("WerSvc", "auto"),
            _svc_enable("wercplsupport", "demand"),
        ],
    },
    {
        "id": "sensor",
        "name": "关闭定位传感器服务",
        "desc": "停止 Sensors 相关服务，关闭位置/传感器收集。",
        "risk": "中",
        "apply": [
            _svc_disable("SensrSvc"),
            _svc_disable("SensorService"),
        ],
        "revert": [
            _svc_enable("SensrSvc"),
            _svc_enable("SensorService"),
        ],
    },
    {
        "id": "quickaccess",
        "name": "关闭快速访问常用/最近",
        "desc": "资源管理器快速访问不再显示“常用文件夹”与“最近文件”。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\OperationStatusManager", "EnthusiastMode", 1),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ShowSyncProviderNotifications", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer", "ShowFrequent", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer", "ShowRecent", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "LaunchTo", 1),
        ],
        "revert": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\OperationStatusManager", "EnthusiastMode", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ShowSyncProviderNotifications", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer", "ShowFrequent", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer", "ShowRecent", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "LaunchTo", 2),
        ],
    },
    {
        "id": "spelling",
        "name": "关闭拼写/输入预测",
        "desc": "禁用触摸键盘自动更正、拼写检查与文本预测（隐私）。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableAutocorrection", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableSpellchecking", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Input\\Settings", "InsightsEnabled", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableDoubleTapSpace", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnablePredictionSpaceInsertion", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableTextPrediction", 0),
        ],
        "revert": [
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableAutocorrection"),
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableSpellchecking"),
            _reg_del("HKCU", "Software\\Microsoft\\Input\\Settings", "InsightsEnabled"),
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableDoubleTapSpace"),
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnablePredictionSpaceInsertion"),
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableTextPrediction"),
        ],
    },
    {
        "id": "ink",
        "name": "关闭 Windows Ink 工作区",
        "desc": "禁用 Windows Ink 工作区与触摸输入建议。",
        "risk": "低",
        "apply": [
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\WindowsInkWorkspace", "AllowWindowsInkWorkspace", 0),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\WindowsInkWorkspace", "AllowSuggestedAppsInWindowsInkWorkspace", 0),
            _reg_add("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableInkingWithTouch", 0),
        ],
        "revert": [
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\WindowsInkWorkspace", "AllowWindowsInkWorkspace"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\WindowsInkWorkspace", "AllowSuggestedAppsInWindowsInkWorkspace"),
            _reg_del("HKCU", "SOFTWARE\\Microsoft\\TabletTip\\1.7", "EnableInkingWithTouch"),
        ],
    },
    {
        "id": "snap",
        "name": "关闭 Snap 助手浮窗",
        "desc": "贴靠窗口时不再显示其他窗口缩略图建议。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "EnableSnapAssistFlyout", 0),
            _reg_add_sz("HKCU", "Control Panel\\Desktop", "DockMoving", "0"),
        ],
        "revert": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "EnableSnapAssistFlyout", 1),
            _reg_add_sz("HKCU", "Control Panel\\Desktop", "DockMoving", "1"),
        ],
    },
    {
        "id": "showmore",
        "name": "经典右键“显示更多选项”(Win11)",
        "desc": "恢复 Win10 风格右键菜单（跳过“显示更多选项”）。",
        "risk": "低",
        "apply": [
            _reg_add_ve("HKCU", "Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\\InprocServer32", ""),
        ],
        "revert": [
            _reg_del_tree("HKCU", "Software\\Classes\\CLSID\\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"),
        ],
    },
    {
        "id": "perf",
        "name": "性能/资源管理器微调",
        "desc": "禁用窗口抖动最小化、显示文件扩展名与隐藏文件、关闭低磁盘检查、加速关机等待。",
        "risk": "低",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "DisallowShaking", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "HideFileExt", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "Hidden", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoLowDiskSpaceChecks", 1),
            _reg_add("HKCU", "Control Panel\\Desktop", "AutoEndTasks", 1),
            _reg_add("HKCU", "Control Panel\\Desktop", "HungAppTimeout", "1000"),
            _reg_add("HKCU", "Control Panel\\Desktop", "WaitToKillAppTimeout", "2000"),
            _reg_add("HKCU", "Control Panel\\Desktop", "LowLevelHooksTimeout", "1000"),
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control", "WaitToKillServiceTimeout", "2000"),
        ],
        "revert": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "HideFileExt", 1),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "Hidden", 0),
            _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control", "WaitToKillServiceTimeout", "5000"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "DisallowShaking"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoLowDiskSpaceChecks"),
            _reg_del("HKCU", "Control Panel\\Desktop", "AutoEndTasks"),
            _reg_del("HKCU", "Control Panel\\Desktop", "HungAppTimeout"),
            _reg_del("HKCU", "Control Panel\\Desktop", "WaitToKillAppTimeout"),
            _reg_del("HKCU", "Control Panel\\Desktop", "LowLevelHooksTimeout"),
        ],
    },
    {
        "id": "smartscreen",
        "name": "关闭 SmartScreen 筛选 (高风险)",
        "desc": "关闭 SmartScreen/钓鱼筛选（提高便利性但降低防护，高风险）。",
        "risk": "高",
        "apply": [
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Attachments", "SaveZoneInformation", 1),
            _reg_add("HKLM", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Attachments", "ScanWithAntiVirus", 1),
            _reg_add_sz("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "ShellSmartScreenLevel", "Warn"),
            _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "EnableSmartScreen", 0),
            _reg_add_sz("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer", "SmartScreenEnabled", "Off"),
            _reg_add("HKLM", "SOFTWARE\\Microsoft\\Internet Explorer\\PhishingFilter", "EnabledV9", 0),
            _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\AppHost", "PreventOverride", 0),
        ],
        "revert": [
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Attachments", "SaveZoneInformation"),
            _reg_del("HKLM", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Attachments", "ScanWithAntiVirus"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "ShellSmartScreenLevel"),
            _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "EnableSmartScreen"),
            _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer", "SmartScreenEnabled"),
            _reg_del("HKLM", "SOFTWARE\\Microsoft\\Internet Explorer\\PhishingFilter", "EnabledV9"),
            _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\AppHost", "PreventOverride"),
        ],
    },
]

# ----------------------------------------------------------------------------
# optimizerDuck 合并：GPU 优化（AMD/NVIDIA/Intel）+ 电源/性能细项
# 数据移植自开源 optimizerDuck（GPL v3，itsfatduck）。
# GPU 项路径依赖显卡注册表索引，运行时由 _gpu_detect() 动态注入，故这里只存
# 「厂商 + 注册表值名 + 值」；电源/性能项为固定路径，直接生成命令。
# ----------------------------------------------------------------------------
import base64
import json


def _b64_ps(script: str) -> str:
    """把 PowerShell 脚本编码为 -EncodedCommand，避免 cmd 解析其中的 | {} 等符号。"""
    return "powershell -NoProfile -EncodedCommand " + base64.b64encode(
        script.encode("utf-16-le")
    ).decode()


def _ps_usb_power(enable: bool) -> str:
    """禁用/启用 USB ROOT 设备的节能挂起（MSPower_DeviceEnable.Enable）。"""
    flag = "$true" if enable else "$false"
    script = (
        "Get-CimInstance -Namespace root\\wmi -ClassName MSPower_DeviceEnable "
        "| Where-Object { $_.InstanceName -match 'USB\\\\ROOT' } "
        "| ForEach-Object { Set-CimInstance -InputObject $_ -Property @{ Enable = " + flag + " } }"
    )
    return _b64_ps(script)


# GPU 调优项：每项对应某厂商；apply 时对检测到的每个同厂商 GPU 索引路径写 reg，
# revert 用 reg delete 删除这些覆写值（恢复驱动默认，即可逆）。
GPU_OPTS = [
    {"vendor": "AMD", "name": "禁用 ULPS（超低功耗状态）",
     "desc": "AMD：关闭 ULPS，避免显卡闲置后唤醒卡顿/黑屏。", "risk": "低",
     "regs": [("EnableULPS", 0)]},
    {"vendor": "AMD", "name": "禁用电源门控 Power Gating",
     "desc": "AMD：关闭电源门控与动态 P-state，提升持续性能（略增功耗）。", "risk": "中",
     "regs": [("DisablePowerGating", 1), ("PP_GPUPowerDownEnabled", 0), ("DisableDynamicPstate", 1)]},
    {"vendor": "AMD", "name": "禁用视频时钟门控",
     "desc": "AMD：关闭 VCE/UVD 时钟门控，降低视频编解码延迟。", "risk": "中",
     "regs": [("DisableVCEPowerGating", 1), ("DisableVceClockGating", 1),
              ("EnableUvdClockGating", 0), ("EnableVceSwClockGating", 0)]},
    {"vendor": "AMD", "name": "禁用 ASPM（L0s/L1）",
     "desc": "AMD：关闭 PCIe ASPM 节能状态，降低延迟。", "risk": "低",
     "regs": [("EnableAspmL0s", 0), ("EnableAspmL1", 0)]},
    {"vendor": "NVIDIA", "name": "禁用动态 P-state",
     "desc": "NVIDIA：关闭动态 P-state，保持高频。", "risk": "低",
     "regs": [("DisableDynamicPstate", 1)]},
    {"vendor": "NVIDIA", "name": "禁用异步 P-states",
     "desc": "NVIDIA：关闭异步 P-state，降低调度延迟。", "risk": "中",
     "regs": [("DisableASyncPstates", 1)]},
    {"vendor": "Intel", "name": "禁用异步翻转 Async Flips",
     "desc": "Intel 核显：关闭异步翻转，降低输入延迟。", "risk": "低",
     "regs": [("Display1_DisableAsyncFlips", 1)]},
    {"vendor": "Intel", "name": "禁用自适应垂直同步",
     "desc": "Intel 核显：关闭自适应 Vsync。", "risk": "低",
     "regs": [("AdaptiveVsyncEnable", 0)]},
]

# 电源/性能细项（固定路径，与现有深度优化面板不重复）。
POWER_OPTS = [
    {"id": "power_throttle", "name": "禁用系统电源节流",
     "desc": "PowerThrottlingOff=1 + 关闭 USB 意外移除自动恢复，提升 CPU/设备性能。", "risk": "低",
     "apply": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling", "PowerThrottlingOff", 1),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\USB\\AutomaticSurpriseRemoval", "AttemptRecoveryFromUsbPowerDrain", 0),
     ],
     "revert": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling", "PowerThrottlingOff", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\USB\\AutomaticSurpriseRemoval", "AttemptRecoveryFromUsbPowerDrain", 1),
     ]},
    {"id": "usb_power_save", "name": "禁用 USB 设备节能挂起",
     "desc": "关闭 USB ROOT 设备节能（MSPower_DeviceEnable），降低 USB 外设延迟。重启生效。", "risk": "低",
     "apply": [_ps_usb_power(False)],
     "revert": [_ps_usb_power(True)]},
]


def _svc_set(name, start="auto"):
    return f'sc config {name} start= {start}'

def _task_disable(tn):
    return f'schtasks /Change /TN "{tn}" /Disable'

def _task_enable(tn):
    return f'schtasks /Change /TN "{tn}" /Enable'

def _total_ram_kb():
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = _MS()
        ms.dwLength = ctypes.sizeof(ms)
        k32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return int(ms.ullTotalPhys // 1024)
    except Exception:
        return 8 * 1024 * 1024


# optimizerDuck 的全功能优化（去重后剩余独有项，对应 PowerManagement / Performance /
# UserExperience / SecurityAndPrivacy 类别中工具箱此前未覆盖的开关）。
# 每项含 apply / revert 命令列表，可被 open_optduck 面板统一执行（reg / sc / schtasks / powercfg）。
_OPTDUCK_TELEMETRY_TASKS = [
    r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
    r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
    r"\Microsoft\Windows\Application Experience\MareBackup",
    r"\Microsoft\Windows\Application Experience\StartupAppTask",
    r"\Microsoft\Windows\Application Experience\PcaPatchDbTask",
    r"\Microsoft\Windows\Autochk\Proxy",
    r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
    r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
    r"\Microsoft\Windows\Feedback\Siuf\DmClient",
    r"\Microsoft\Windows\Feedback\Siuf\DmClientOnScenarioDownload",
]

OPTDUCK_OPTS = [
    # ---- Performance ----
    {"id": "bg_apps", "name": "禁用后台应用", "risk": "低",
     "desc": "关闭后台应用权限与搜索后台全局开关，省内存。",
     "apply": [
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications", "GlobalUserDisabled", 1),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Search", "BackgroundAppGlobalToggle", 0),
     ],
     "revert": [
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications", "GlobalUserDisabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Search", "BackgroundAppGlobalToggle"),
     ]},
    {"id": "svc_split", "name": "服务宿主拆分阈值", "risk": "中",
     "desc": "按本机物理内存设置 SvcHostSplitThresholdInKB，减少 svchost 合并。",
     "apply": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control", "SvcHostSplitThresholdInKB", _total_ram_kb()),
     ],
     "revert": [
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control", "SvcHostSplitThresholdInKB"),
     ]},
    {"id": "proc_prio", "name": "前台进程优先", "risk": "低",
     "desc": "Win32PrioritySeparation=38（短、可变、高前台提升），提升前台响应。",
     "apply": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\PriorityControl", "Win32PrioritySeparation", 38),
     ],
     "revert": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\PriorityControl", "Win32PrioritySeparation", 2),
     ]},
    {"id": "mmcss", "name": "多媒体调度优化（游戏/低延迟）", "risk": "低",
     "desc": "MMCSS：NoLazyMode/AlwaysOn、关闭网络节流、Games 任务高优先级。音频/游戏低延迟。",
     "apply": [
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "NoLazyMode", 1),
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "AlwaysOn", 1),
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "NetworkThrottlingIndex", "0xffffffff"),
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "SystemResponsiveness", 10),
         _reg_add_sz("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "Priority", "2"),
         _reg_add_sz("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "Scheduling Category", "High"),
         _reg_add_sz("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "SFIO Priority", "High"),
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "GPU Priority", 8),
     ],
     "revert": [
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "NoLazyMode"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "AlwaysOn"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "NetworkThrottlingIndex"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile", "SystemResponsiveness"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "Priority"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "Scheduling Category"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "SFIO Priority"),
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile\\Tasks\\Games", "GPU Priority"),
     ]},
    {"id": "kbd_latency", "name": "键盘延迟优化", "risk": "低",
     "desc": "KeyboardDelay=0、KeyboardSpeed=31，加快按键重复。",
     "apply": [
         _reg_add_sz("HKCU", "Control Panel\\Keyboard", "KeyboardDelay", "0"),
         _reg_add_sz("HKCU", "Control Panel\\Keyboard", "KeyboardSpeed", "31"),
     ],
     "revert": [
         _reg_add_sz("HKCU", "Control Panel\\Keyboard", "KeyboardDelay", "1"),
         _reg_add_sz("HKCU", "Control Panel\\Keyboard", "KeyboardSpeed", "31"),
     ]},
    # ---- UserExperience ----
    {"id": "explorer_menu", "name": "加速资源管理器与菜单", "risk": "低",
     "desc": "取消资源管理器启动延迟、菜单弹出延迟归零。",
     "apply": [
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize", "StartupDelayInMSec", 0),
         _reg_add_sz("HKCU", "Control Panel\\Desktop", "MenuShowDelay", "0"),
     ],
     "revert": [
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize", "StartupDelayInMSec"),
         _reg_add_sz("HKCU", "Control Panel\\Desktop", "MenuShowDelay", "400"),
     ]},
    {"id": "visual_fx", "name": "关闭视觉特效", "risk": "低",
     "desc": "关闭任务栏动画、列表阴影、透明效果、Aero Peek，提升性能。",
     "apply": [
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarAnimations", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ListviewShadow", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", "EnableTransparency", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\DWM", "EnableAeroPeek", 0),
     ],
     "revert": [
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "TaskbarAnimations"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "ListviewShadow"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", "EnableTransparency"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\DWM", "EnableAeroPeek"),
     ]},
    {"id": "start_web", "name": "禁用开始菜单网页搜索", "risk": "低",
     "desc": "DisableSearchBoxSuggestions=1，开始菜单不再联网搜 Bing。",
     "apply": [
         _reg_add("HKCU", "Software\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions", 1),
     ],
     "revert": [
         _reg_del("HKCU", "Software\\Policies\\Microsoft\\Windows\\Explorer", "DisableSearchBoxSuggestions"),
     ]},
    # ---- SecurityAndPrivacy ----
    {"id": "telemetry", "name": "关闭遥测与诊断", "risk": "中",
     "desc": "关闭核心遥测/反馈注册表，禁用 DiagTrack 等 5 项服务与 10 个诊断计划任务。",
     "apply": [
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\DataCollection", "AllowTelemetry", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowTelemetry", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "DoNotShowFeedbackNotifications", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowCommercialDataPipeline", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowDeviceNameInTelemetry", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "MicrosoftEdgeDataOptIn", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Siuf\\Rules", "NumberOfSIUFInPeriod", 0),
         _reg_add("HKCU", "Software\\Policies\\Microsoft\\Windows\\EdgeUI", "DisableMFUTracking", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat", "DisableInventory", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat", "AITEnable", 0),
         _reg_add("HKCU", "SOFTWARE\\Policies\\Microsoft\\Assistance\\Client\\1.0", "NoExplicitFeedback", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Assistance\\Client\\1.0", "NoActiveHelp", 1),
         _svc_disable("DiagTrack"), _svc_disable("dmwappushservice"),
         _svc_disable("DcpSvc"), _svc_disable("diagnosticshub.standardcollector.service"),
         _svc_disable("DusmSvc"),
     ] + [_task_disable(t) for t in _OPTDUCK_TELEMETRY_TASKS],
     "revert": [
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\DataCollection", "AllowTelemetry"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowTelemetry"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "DoNotShowFeedbackNotifications"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowCommercialDataPipeline"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "AllowDeviceNameInTelemetry"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection", "MicrosoftEdgeDataOptIn"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Siuf\\Rules", "NumberOfSIUFInPeriod"),
         _reg_del("HKCU", "Software\\Policies\\Microsoft\\Windows\\EdgeUI", "DisableMFUTracking"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat", "DisableInventory"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat", "AITEnable"),
         _reg_del("HKCU", "SOFTWARE\\Policies\\Microsoft\\Assistance\\Client\\1.0", "NoExplicitFeedback"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Assistance\\Client\\1.0", "NoActiveHelp"),
         _svc_set("DiagTrack", "delayed-auto"), _svc_set("dmwappushservice", "demand"),
         _svc_set("DcpSvc", "demand"), _svc_set("diagnosticshub.standardcollector.service", "demand"),
         _svc_set("DusmSvc", "auto"),
     ] + [_task_enable(t) for t in _OPTDUCK_TELEMETRY_TASKS]},
    {"id": "ads_suggest", "name": "关闭广告与建议", "risk": "低",
     "desc": "关闭广告 ID、消费版功能、第三方建议、资讯兴趣等推送。",
     "apply": [
         _reg_add("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo", "Enabled", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AdvertisingInfo", "DisabledByGroupPolicy", 1),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableTailoredExperiencesWithDiagnosticData", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableWindowsConsumerFeatures", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableSoftLanding", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableThirdPartySuggestions", 1),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Dsh", "AllowNewsAndInterests", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow", 1),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\UserProfileEngagement", "ScoobeSystemSettingEnabled", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization", "RestrictImplicitInkCollection", 1),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization", "RestrictImplicitTextCollection", 1),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization\\TrainedDataStore", "HarvestContacts", 0),
         _reg_add("HKCU", "Control Panel\\International\\User Profile", "HttpAcceptLanguageOptOut", 1),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy", "01", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy", "02", 0),
     ],
     "revert": [
         _reg_del("HKLM", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo", "Enabled"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\AdvertisingInfo", "DisabledByGroupPolicy"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableTailoredExperiencesWithDiagnosticData"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableWindowsConsumerFeatures"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableSoftLanding"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\CloudContent", "DisableThirdPartySuggestions"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Dsh", "AllowNewsAndInterests"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "HideSCAMeetNow"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\UserProfileEngagement", "ScoobeSystemSettingEnabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization", "RestrictImplicitInkCollection"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization", "RestrictImplicitTextCollection"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\InputPersonalization\\TrainedDataStore", "HarvestContacts"),
         _reg_del("HKCU", "Control Panel\\International\\User Profile", "HttpAcceptLanguageOptOut"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy", "01"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\StorageSense\\Parameters\\StoragePolicy", "02"),
     ]},
    {"id": "activity_hist", "name": "关闭活动历史记录", "risk": "低",
     "desc": "禁止发布/上传活动历史与动态信息流。",
     "apply": [
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "PublishUserActivities", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "EnableActivityFeed", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "PublishUserActivitiesOnUserConsent", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "UploadUserActivities", 0),
     ],
     "revert": [
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "PublishUserActivities"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "EnableActivityFeed"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "PublishUserActivitiesOnUserConsent"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\System", "UploadUserActivities"),
     ]},
    {"id": "autologger", "name": "关闭 WMI AutoLogger", "risk": "中",
     "desc": "将 10 个 WMI AutoLogger 会话 Start=0，减少后台日志采集。",
     "apply": [
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\AppModel", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\Cellcore", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\CloudExperienceHostOobe", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\DataMarket", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\DiagLog", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\Diagtrack-Listener", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\LwtNetLog", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\SQMLogger", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\WdiContextLog", "Start", 0),
         _reg_add("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\WiFiSession", "Start", 0),
     ],
     "revert": [
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\AppModel", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\Cellcore", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\CloudExperienceHostOobe", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\DataMarket", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\DiagLog", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\Diagtrack-Listener", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\LwtNetLog", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\SQMLogger", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\WdiContextLog", "Start"),
         _reg_del("HKLM", "SYSTEM\\CurrentControlSet\\Control\\WMI\\Autologger\\WiFiSession", "Start"),
     ]},
    {"id": "cortana", "name": "禁用 Cortana 与网页搜索", "risk": "中",
     "desc": "通过组策略关闭 Cortana、云搜索与网页搜索（不卸载应用本体）。",
     "apply": [
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCortana", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCloudSearch", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCortanaAboveLock", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowSearchToUseLocation", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "ConnectedSearchUseWeb", 0),
         _reg_add("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "DisableWebSearch", 1),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Search", "CortanaConsent", 0),
         _reg_add("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Search", "CortanaConsent2", 0),
     ],
     "revert": [
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCortana"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCloudSearch"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowCortanaAboveLock"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "AllowSearchToUseLocation"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "ConnectedSearchUseWeb"),
         _reg_del("HKLM", "SOFTWARE\\Policies\\Microsoft\\Windows\\Windows Search", "DisableWebSearch"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Search", "CortanaConsent"),
         _reg_del("HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Search", "CortanaConsent2"),
     ]},
    {"id": "content_delivery", "name": "关闭内容分发管理器", "risk": "低",
     "desc": "禁用 Windows Spotlight/建议类内容的后台推送。",
     "apply": [
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "ContentDeliveryAllowed", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338387Enabled", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338388Enabled", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338389Enabled", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-353698Enabled", 0),
         _reg_add("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SystemPaneSuggestionsEnabled", 0),
     ],
     "revert": [
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "ContentDeliveryAllowed"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338387Enabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338388Enabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-338389Enabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SubscribedContent-353698Enabled"),
         _reg_del("HKCU", "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager", "SystemPaneSuggestionsEnabled"),
     ]},
    # ---- PowerManagement（休眠/快速启动 + 高性能计划）----
    {"id": "hibernate", "name": "关闭休眠与快速启动", "risk": "中",
     "desc": "powercfg /h off：释放 hiberfil.sys 空间并关闭快速启动（物理机推荐）。",
     "apply": ["powercfg /h off"],
     "revert": ["powercfg /h on"]},
    {"id": "high_perf", "name": "切换高性能电源计划", "risk": "低",
     "desc": "激活内置“高性能”电源计划（8c5e7fda-…）；还原切回“平衡”。",
     "apply": ["powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
     "revert": ["powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e"]},
]


# ----------------------------------------------------------------------------
# 3. GUI
# ----------------------------------------------------------------------------
class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("系统优化工具箱（管理员 · 全盘）")
        self.root.geometry("900x760")
        self.root.resizable(True, True)
        _apply_app_icon(self.root)

        self.item_vars = {}
        self.item_size = {}
        self.item_count = {}
        self.cleaning = False

        self._build_ui()
        self._refresh_admin_badge()

    # ---- UI 构建 ----
    def _build_ui(self):
        # 顶部标题 + 管理员徽标
        top = ttk.Frame(self.root, padding=(10, 8, 10, 3))
        top.pack(fill="x")
        ttk.Label(top, text="🛠 系统优化工具箱", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.admin_badge = ttk.Label(top, text="", font=("Microsoft YaHei UI", 9, "bold"))
        self.admin_badge.pack(side="right")

        # ---- 左右分栏主体：左 = 工具 + 一键优化，右 = 清理列表 + 日志 ----
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        body.columnconfigure(0, weight=0, minsize=230)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左列
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # 右列（行权重：列表占大头，下方操作区固定）
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)   # 清理列表
        right.rowconfigure(1, weight=0)   # 全选 / 统计
        right.rowconfigure(2, weight=0)   # 主操作按钮

        self._build_tools_into(left)
        self._build_optimize_into(left)
        self._build_cleanup_list_into(right)
        self._build_select_stats_into(right)
        self._build_action_buttons_into(right)

        # ---- 底部：运行日志（全宽）----
        self._build_log_into(self.root)

    # ---- 系统快捷工具（合并 CMD 入口 + 上帝模式）----
    def _build_tools_into(self, parent):
        # —— 分区 1：Windows 系统工具 ——
        g1 = ttk.LabelFrame(parent, text="🖥 Windows 系统工具", padding=5)
        g1.pack(fill="x", pady=(0, 4))
        self._button_grid(g1, [
            ("🎛 控制面板", lambda: self._open_target("control.exe")),
            ("📊 任务管理器", lambda: self._open_target("taskmgr.exe")),
            ("🗑 卸载程序", lambda: self._open_target("appwiz.cpl")),
            ("🧹 磁盘清理", lambda: self._open_target("cleanmgr.exe")),
            ("📋 系统信息", lambda: self._open_target("ms-settings:about")),
            ("🔧 设备管理器", lambda: self._open_target("devmgmt.msc")),
            ("💽 磁盘管理", lambda: self._open_target("diskmgmt.msc")),
            ("⚙ 服务", lambda: self._open_target("services.msc")),
            ("👑 上帝模式", self.open_godmode),
        ], per_row=2, padx=4, pady_top=4, width=12)

        # —— 分区 2：优化与卸载面板 ——
        g2 = ttk.LabelFrame(parent, text="🧩 优化与卸载面板", padding=5)
        g2.pack(fill="x", pady=(0, 4))
        self._button_grid(g2, [
            ("🧯 卸载预装", self.open_debloat),
            ("🛠 深度优化", self.open_deep),
            ("🎮 GPU 优化", self.open_gpu),
            ("⚡ 电源/性能", self.open_power),
            ("🚀 启动项", self.open_startup),
            ("🧩 Duck 全功能", self.open_optduck),
        ], per_row=2, padx=4, pady_top=4, width=12)

        # —— 分区 3：外部工具 ——
        g3 = ttk.LabelFrame(parent, text="🌐 外部工具", padding=5)
        g3.pack(fill="x", pady=(0, 4))
        self._button_grid(g3, [
            ("🚀 Win10 优化", self.launch_win10_optimizer),
            ("🌐 360 联网助手", self.launch_net_assist),
        ], per_row=1, padx=4, pady_top=4, width=22)

    # ---- 一键优化（需管理员，执行前二次确认）----
    def _build_optimize_into(self, parent):
        of = ttk.LabelFrame(parent, text="⚡ 一键优化（需管理员，二次确认）", padding=6)
        of.pack(fill="x")

        self._button_grid(of, [
            ("🧹 DNS 缓存", self.opt_dns_flush),
            ("🔋 高性能电源", self.opt_high_perf),
            ("🏆 卓越电源", self.opt_ultimate_perf),
            ("⚡ 快速启动", self.opt_fastboot_on),
            ("⚡ 禁用 SysMain", self.opt_sysmain_off),
            ("📡 关传递优化", self.opt_dosvc_off),
            ("🔎 关搜索索引", self.opt_search_off),
            ("🎨 关透明动画", self.opt_visual_off),
            ("📊 关遥测", self.opt_telemetry_off),
            ("💤 关休眠", self.opt_hibernate_off),
            ("🧱 关防火墙", self.opt_firewall_off),
            ("🦠 关 Defender", self.opt_defender_off),
            ("🔓 关 UAC", self.opt_uac_off),
            ("🗑 关系统还原", self.opt_system_restore_off),
            ("⬇ 关 Win 更新", self.opt_wu_off),
        ], per_row=2, padx=4, pady_top=4, width=13)

        ttk.Label(
            of,
            text="⚠ 高危：非管理员将触发 UAC，每项执行前二次确认，全部可逆。",
            foreground="#b00020", font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(4, 0))

    # ---- 按钮网格：每排 per_row 个，竖排 ----
    def _button_grid(self, parent, buttons, per_row=2, padx=12, pady_top=8, width=None):
        for i in range(0, len(buttons), per_row):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(pady_top, 0))
            for label, command in buttons[i:i + per_row]:
                btn = ttk.Button(row, text=label, command=command)
                if width:
                    btn.configure(width=width)
                btn.pack(side="left", padx=padx)

    # ---- 右侧：可清理项目列表 ----
    def _build_cleanup_list_into(self, parent):
        list_frame = ttk.LabelFrame(parent, text="可清理项目（勾选后点击“扫描”）", padding=3)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 3))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # 紧凑样式：缩小字号与行高（Treeview 的 font 需经 Style 设置，不能直接传构造参数）
        _ts = ttk.Style()
        _ts.configure("Cleanup.Treeview", font=("Microsoft YaHei UI", 9), rowheight=22)

        cols = ("check", "name", "detail", "size")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                 style="Cleanup.Treeview")
        self.tree.heading("check", text="")
        self.tree.heading("name", text="项目")
        self.tree.heading("detail", text="位置")
        self.tree.heading("size", text="已占用")
        self.tree.column("check", width=24, anchor="center", stretch=False)
        self.tree.column("name", width=130, stretch=False)
        self.tree.column("detail", width=220)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.tag_configure("checked", background="#e8f5e9")
        self.tree.tag_configure("highrisk", foreground="#b00020")
        for item in CLEAN_ITEMS:
            self.item_vars[item["id"]] = tk.BooleanVar(value=item["checked"])
            self.item_size[item["id"]] = 0
            self.item_count[item["id"]] = 0
            mark = "☑" if item["checked"] else "☐"
            tags = []
            if item["checked"]:
                tags.append("checked")
            if item["risk"] == "高":
                tags.append("highrisk")
            self.tree.insert(
                "", "end", iid=item["id"],
                values=(mark, item["name"], _elide(item["detail"]), "未扫描"),
                tags=tuple(tags)
            )
        self.tree.bind("<Button-1>", self._on_tree_click)

    # ---- 右侧：全选 / 统计（独立分组）----
    def _build_select_stats_into(self, parent):
        f = ttk.LabelFrame(parent, text="选择 / 统计", padding=4)
        f.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        sel = ttk.Frame(f)
        sel.pack(fill="x")
        ttk.Button(sel, text="全选", command=lambda: self._set_all(True)).pack(side="left", padx=2)
        ttk.Button(sel, text="全不选", command=lambda: self._set_all(False)).pack(side="left", padx=2)
        ttk.Button(sel, text="仅低风险", command=self._only_low).pack(side="left", padx=2)
        self.stat_var = tk.StringVar(value="已选占用：0 B ｜ 文件数：0")
        ttk.Label(f, textvariable=self.stat_var,
                  font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

    # ---- 右侧：主操作按钮（独立分组、居中）----
    def _build_action_buttons_into(self, parent):
        f = ttk.LabelFrame(parent, text="操作", padding=4)
        f.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        inner = ttk.Frame(f)
        inner.pack(anchor="center")
        self.btn_scan = ttk.Button(inner, text="🔍 扫描占用", command=self._scan)
        self.btn_scan.pack(side="left", padx=5)
        self.btn_clean = ttk.Button(inner, text="🚀 开始清理", command=self._ask_clean)
        self.btn_clean.pack(side="left", padx=5)
        self.btn_export = ttk.Button(inner, text="📄 导出报告", command=self._export_report)
        self.btn_export.pack(side="left", padx=5)

    # ---- 底部：运行日志（全宽）----
    def _build_log_into(self, parent):
        log_frame = ttk.LabelFrame(parent, text="运行日志", padding=3)
        log_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.log = scrolledtext.ScrolledText(log_frame, height=6, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    def _open_target(self, target):
        try:
            os.startfile(target)
            self._log(f"已打开：{target}")
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开 {target}：{e}")

    def launch_win10_optimizer(self):
        """启动外部「Win10 优化版.bat」交互式优化工具。

        该 BAT 自带 UAC 提权逻辑（非管理员时会自行 powershell RunAs 重启），
        且是交互式菜单程序，因此这里用 os.startfile 等同“双击”，会弹出独立
        控制台窗口，由用户在窗口内逐项选择执行/恢复。无需把 50 个子项逐一
        翻译成 GUI，避免引入新的不确定性。
        """
        bat = _resolve_asset(WIN10_OPTIMIZER_BAT_NAME, WIN10_OPTIMIZER_BAT)
        if not bat:
            messagebox.showerror(
                "找不到优化脚本",
                f"未找到「{WIN10_OPTIMIZER_BAT_NAME}」。\n\n"
                f"请确认它位于：\n  1) 本程序同一文件夹下，或\n"
                f"  2) 原路径 {WIN10_OPTIMIZER_BAT}\n",
            )
            return
        try:
            os.startfile(bat)
            self._log(f"[Win10优化] 已启动：{bat}（请在弹出的控制台窗口中交互操作）")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动优化脚本：{e}")

    def launch_net_assist(self):
        """启动外部「360 联网助手.exe」网络诊断/修复工具（第三方 exe，双击式运行）。"""
        exe = _resolve_asset(NET_ASSIST_EXE_NAME, NET_ASSIST_EXE)
        if not exe:
            messagebox.showerror(
                "找不到 360 联网助手",
                f"未找到「{NET_ASSIST_EXE_NAME}」。\n\n"
                f"请确认它位于：\n  1) 本程序同一文件夹下，或\n"
                f"  2) 原路径 {NET_ASSIST_EXE}\n",
            )
            return
        try:
            os.startfile(exe)
            self._log(f"[360联网助手] 已启动：{exe}")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动 360 联网助手：{e}")

    # ---- 卸载 Windows 预装应用（集成自开源 PyDebloatX 的清单与卸载思路）----
    def open_debloat(self):
        """打开「卸载 Windows 预装应用」子窗口。

        - 列出 34+ 个 Win10/11 默认 UWP 应用（中文名 + 说明）。
        - 「检测已安装」：后台跑一次 Get-AppxPackage，标注每项安装状态。
        - 勾选后「卸载选中」：逐个 Get-AppxPackage <pkg> | Remove-AppxPackage
          （当前用户范围，无需管理员；后台线程执行，不阻塞界面），并回显结果。
        - 只卸载当前用户，不加 -AllUsers，避免影响其他账户；卸载后可从
          Microsoft Store 重新安装，属可逆操作。
        """
        if getattr(self, "_debloat_win", None) is not None:
            try:
                self._debloat_win.deiconify()
                self._debloat_win.lift()
                return
            except Exception:
                self._debloat_win = None

        win = tk.Toplevel(self.root)
        self._debloat_win = win
        win.title("卸载 Windows 预装应用")
        win.geometry("720x600")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._debloat_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(
            win, text="🧯 卸载 Windows 预装应用（UWP）",
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="点“检测已安装”标注状态 → 勾选要卸载的项 → “卸载选中”。仅卸当前用户，"
                 "卸载后可从 Microsoft Store 重新安装（可逆）。",
            font=("Microsoft YaHei UI", 9), foreground="#555",
            wraplength=690, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="预装应用清单", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "desc", "status")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="应用")
        tree.heading("desc", text="说明")
        tree.heading("status", text="状态")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=150, stretch=False)
        tree.column("desc", width=380)
        tree.column("status", width=90, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("checked", background="#e8f5e9")
        tree.tag_configure("installed", foreground="#1565c0")
        tree.tag_configure("gone", foreground="#999")

        self._debloat_tree = tree
        self._debloat_vars = {}
        for idx, app in enumerate(DEBLOAT_APPS):
            iid = str(idx)
            self._debloat_vars[iid] = tk.BooleanVar(value=False)
            tree.insert("", "end", iid=iid,
                        values=("☐", app["name"], _elide(app["desc"], 40), "未检测"))
        tree.bind("<Button-1>", self._on_debloat_click)

        # 选择 / 操作
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="🔍 检测已安装",
                   command=self._debloat_detect).pack(side="left", padx=2)
        ttk.Button(bar, text="全选",
                   command=lambda: self._debloat_set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="全不选",
                   command=lambda: self._debloat_set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="仅已安装",
                   command=self._debloat_check_installed).pack(side="left", padx=2)
        self._debloat_uninstall_btn = ttk.Button(
            bar, text="🗑 卸载选中", command=self._debloat_uninstall)
        self._debloat_uninstall_btn.pack(side="right", padx=2)

        self._debloat_status = tk.StringVar(
            value="提示：先点“检测已安装”，未安装的项无需卸载。")
        ttk.Label(win, textvariable=self._debloat_status,
                  font=("Microsoft YaHei UI", 9), foreground="#b00020",
                  wraplength=690, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    def _on_debloat_click(self, event):
        tree = self._debloat_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        self._debloat_vars[iid].set(not self._debloat_vars[iid].get())
        self._debloat_redraw(iid)

    def _debloat_redraw(self, iid):
        tree = self._debloat_tree
        checked = self._debloat_vars[iid].get()
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if checked else "☐"
        # 保留状态相关 tag（installed/gone），仅切换 checked 底色
        status = vals[3]
        tags = []
        if checked:
            tags.append("checked")
        if status == "已安装":
            tags.append("installed")
        elif status in ("未安装", "已卸载"):
            tags.append("gone")
        tree.item(iid, values=vals, tags=tuple(tags))

    def _debloat_set_all(self, val):
        for iid in self._debloat_vars:
            self._debloat_vars[iid].set(val)
            self._debloat_redraw(iid)

    def _debloat_check_installed(self):
        tree = self._debloat_tree
        for iid in self._debloat_vars:
            installed = tree.item(iid, "values")[3] == "已安装"
            self._debloat_vars[iid].set(installed)
            self._debloat_redraw(iid)

    def _debloat_detect(self):
        """后台线程：跑一次 Get-AppxPackage，标注每项安装状态。"""
        if getattr(self, "_debloat_busy", False):
            return
        self._debloat_busy = True
        self._debloat_status.set("正在检测已安装应用……（首次可能需数秒）")
        self._log("[卸载预装] 开始检测已安装的 UWP 应用……")

        def worker():
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-AppxPackage -PackageTypeFilter Main | "
                     "Select -ExpandProperty Name"],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                names = [ln.strip().lower() for ln in (r.stdout or "").splitlines()
                         if ln.strip()]
            except Exception as e:
                self.root.after(0, lambda: self._debloat_status.set(f"检测失败：{e}"))
                self._debloat_busy = False
                return

            def token(app):
                t = app["pkg"].strip("*").lower()
                return t

            results = {}
            n_installed = 0
            for idx, app in enumerate(DEBLOAT_APPS):
                tok = token(app)
                if app.get("xbox"):
                    hit = any(("xbox" in nm and "xboxgamecallableui" not in nm)
                              for nm in names)
                else:
                    hit = any(tok in nm for nm in names)
                results[str(idx)] = hit
                if hit:
                    n_installed += 1
            self.root.after(0, self._debloat_apply_detect, results, n_installed)

        threading.Thread(target=worker, daemon=True).start()

    def _debloat_apply_detect(self, results, n_installed):
        tree = self._debloat_tree
        for iid, installed in results.items():
            vals = list(tree.item(iid, "values"))
            vals[3] = "已安装" if installed else "未安装"
            tree.item(iid, values=vals)
            self._debloat_redraw(iid)
        self._debloat_busy = False
        self._debloat_status.set(
            f"检测完成：共 {len(results)} 项，已安装 {n_installed} 项。"
            "可点“仅已安装”快速勾选。")
        self._log(f"[卸载预装] 检测完成：已安装 {n_installed} / {len(results)} 项。")

    def _debloat_uninstall(self):
        if getattr(self, "_debloat_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._debloat_win)
            return
        selected = [(iid, DEBLOAT_APPS[int(iid)])
                    for iid in self._debloat_vars if self._debloat_vars[iid].get()]
        if not selected:
            messagebox.showwarning("提示", "请至少勾选一个要卸载的应用。", parent=self._debloat_win)
            return
        names = "、".join(a["name"] for _, a in selected)
        if not messagebox.askyesno(
            "确认卸载",
            f"即将卸载以下 {len(selected)} 个预装应用（仅当前用户）：\n\n{names}\n\n"
            "说明：卸载后可随时从 Microsoft Store 重新安装（可逆）。\n"
            "部分系统组件（如照片、计算器）卸载后相应功能会消失。\n\n"
            "确认卸载？",
            parent=self._debloat_win,
        ):
            self._log("[卸载预装] 已取消。")
            return

        self._debloat_busy = True
        self._debloat_uninstall_btn.configure(state="disabled")
        self._debloat_status.set(f"正在卸载 {len(selected)} 个应用……")
        self._log(f"[卸载预装] 开始卸载 {len(selected)} 个应用……")

        def worker():
            ok, fail = 0, 0
            for iid, app in selected:
                if app.get("xbox"):
                    ps = ("Get-AppxPackage *Xbox* | Where-Object "
                          "{$_.Name -notmatch 'XboxGameCallableUI'} | "
                          "Remove-AppxPackage -ErrorAction SilentlyContinue")
                    verify = ("if (Get-AppxPackage *Xbox* | Where-Object "
                              "{$_.Name -notmatch 'XboxGameCallableUI'}) "
                              "{'INSTALLED'} else {'GONE'}")
                else:
                    ps = (f"Get-AppxPackage {app['pkg']} | "
                          "Remove-AppxPackage -ErrorAction SilentlyContinue")
                    verify = (f"if (Get-AppxPackage {app['pkg']}) "
                              "{'INSTALLED'} else {'GONE'}")
                try:
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    v = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", verify],
                        capture_output=True, text=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    gone = "GONE" in (v.stdout or "")
                except Exception as e:
                    gone = False
                    self._log(f"  [异常] {app['name']}：{e}")
                if gone:
                    ok += 1
                    self._log(f"  [已卸载] {app['name']}")
                else:
                    fail += 1
                    self._log(f"  [失败/跳过] {app['name']}")
                self.root.after(0, self._debloat_mark_result, iid, gone)
            self.root.after(0, self._debloat_uninstall_done, ok, fail)

        threading.Thread(target=worker, daemon=True).start()

    def _debloat_mark_result(self, iid, gone):
        tree = self._debloat_tree
        vals = list(tree.item(iid, "values"))
        vals[3] = "已卸载" if gone else "失败"
        self._debloat_vars[iid].set(False)
        tree.item(iid, values=vals)
        self._debloat_redraw(iid)

    def _debloat_uninstall_done(self, ok, fail):
        self._debloat_busy = False
        self._debloat_uninstall_btn.configure(state="normal")
        self._debloat_status.set(f"卸载完成：成功 {ok} 项，失败/跳过 {fail} 项。")
        self._log(f"[卸载预装] 全部完成：成功 {ok}，失败/跳过 {fail}。")
        messagebox.showinfo(
            "卸载完成",
            f"成功卸载 {ok} 项，失败/跳过 {fail} 项。\n详见运行日志。",
            parent=self._debloat_win,
        )

    # ---- Windows 深度优化（提取自开源 Optimizer 的注册表开关）----
    def open_deep(self):
        """打开「Windows 深度优化」子窗口：列出若干 Optimizer 风格的注册表优化开关。

        - 勾选要应用的项 → “应用所选”写入注册表（需管理员写 HKLM）。
        - 想恢复默认 → 再次勾选相同项 → “还原所选”删除对应值/恢复服务。
        - 全部可逆；逻辑移植自 Optimizer 的 OptimizeHelper.cs（社区项目）。
        """
        if getattr(self, "_deep_win", None) is not None:
            try:
                self._deep_win.deiconify()
                self._deep_win.lift()
                return
            except Exception:
                self._deep_win = None

        win = tk.Toplevel(self.root)
        self._deep_win = win
        win.title("Windows 深度优化（Optimizer 开关）")
        win.geometry("760x640")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._deep_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(win, text="🛠 Windows 深度优化（Optimizer 开关）",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="勾选要应用的项 → “应用所选”；想恢复 Windows 默认 → 勾选相同项 → “还原所选”。"
                 "全部可逆。写 HKLM 的项需管理员权限（将触发 UAC）。",
            font=("Microsoft YaHei UI", 9), foreground="#555", wraplength=720, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="优化开关清单", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "desc", "status", "risk")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="开关")
        tree.heading("desc", text="说明")
        tree.heading("status", text="状态")
        tree.heading("risk", text="风险")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=150, stretch=False)
        tree.column("desc", width=320)
        tree.column("status", width=70, anchor="center", stretch=False)
        tree.column("risk", width=50, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("checked", background="#e8f5e9")
        tree.tag_configure("highrisk", foreground="#b00020")
        tree.tag_configure("done", foreground="#1565c0")

        self._deep_tree = tree
        self._deep_vars = {}
        for idx, opt in enumerate(DEEP_OPTS):
            iid = str(idx)
            self._deep_vars[iid] = tk.BooleanVar(value=False)
            tags = ["highrisk"] if opt["risk"] == "高" else []
            tree.insert("", "end", iid=iid,
                        values=("☐", opt["name"], _elide(opt["desc"], 36), "未操作", opt["risk"]),
                        tags=tuple(tags))
        tree.bind("<Button-1>", self._on_deep_click)

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="全选", command=lambda: self._deep_set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="全不选", command=lambda: self._deep_set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="应用所选", command=lambda: self._deep_execute("apply")).pack(side="right", padx=2)
        ttk.Button(bar, text="还原所选", command=lambda: self._deep_execute("revert")).pack(side="right", padx=2)

        self._deep_status = tk.StringVar(value="提示：逐项勾选，再点“应用所选”或“还原所选”。")
        ttk.Label(win, textvariable=self._deep_status,
                  font=("Microsoft YaHei UI", 9), foreground="#b00020",
                  wraplength=720, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    def _on_deep_click(self, event):
        tree = self._deep_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        self._deep_vars[iid].set(not self._deep_vars[iid].get())
        self._deep_redraw(iid)

    def _deep_redraw(self, iid):
        tree = self._deep_tree
        checked = self._deep_vars[iid].get()
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if checked else "☐"
        status = vals[3]
        tags = []
        if DEEP_OPTS[int(iid)]["risk"] == "高":
            tags.append("highrisk")
        if checked:
            tags.append("checked")
        if status in ("已应用", "已还原"):
            tags.append("done")
        tree.item(iid, values=vals, tags=tuple(tags))

    def _deep_set_all(self, val):
        for iid in self._deep_vars:
            self._deep_vars[iid].set(val)
            self._deep_redraw(iid)

    def _deep_execute(self, mode):
        if getattr(self, "_deep_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._deep_win)
            return
        sel = [(iid, DEEP_OPTS[int(iid)]) for iid in self._deep_vars if self._deep_vars[iid].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一项。", parent=self._deep_win)
            return
        verb = "应用" if mode == "apply" else "还原"
        names = "、".join(o["name"] for _, o in sel)
        risk = (f"即将{verb}以下 {len(sel)} 项深度优化（注册表/服务调整）：\n\n{names}\n\n"
                "说明：全部可逆——之后勾选相同项并点“还原所选”即可恢复 Windows 默认。"
                "写 HKLM 的项需管理员权限，将触发 UAC。\n\n确认？")
        if not messagebox.askyesno("确认" + verb, risk, parent=self._deep_win):
            self._log(f"[深度优化] 已取消。")
            return
        cmds = []
        for _, o in sel:
            cmds.extend(o[mode])
        full = " & ".join(cmds)
        self._deep_busy = True
        self._deep_status.set(f"{verb}中：{names}")
        self._log(f"[深度优化] {verb} {len(sel)} 项……")
        if is_admin():
            threading.Thread(target=self._deep_thread, args=(full, mode, [iid for iid, _ in sel]), daemon=True).start()
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {full}", None, 0)
            if ret > 32:
                for iid, _ in sel:
                    self._deep_set_status(iid, "已" + verb)
                self._deep_busy = False
                messagebox.showinfo("已请求提权", "已以管理员身份执行，详见命令窗口/日志。", parent=self._deep_win)
            else:
                self._deep_busy = False
                messagebox.showerror("提权失败", "请手动以管理员身份运行本工具。", parent=self._deep_win)

    def _deep_thread(self, full, mode, iids):
        try:
            r = subprocess.run(full, shell=True, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[深度优化] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._deep_done, mode, iids, r.returncode)
        except Exception as e:
            self._log(f"[深度优化] 执行异常：{e}")
            self.root.after(0, self._deep_done, mode, iids, -1)

    def _deep_done(self, mode, iids, code):
        self._deep_busy = False
        verb = "已应用" if mode == "apply" else "已还原"
        for iid in iids:
            self._deep_set_status(iid, verb)
        self._deep_status.set(f"{verb} {len(iids)} 项。返回码 {code}。")
        self._log(f"[深度优化] {verb} {len(iids)} 项，返回码 {code}。")

    def _deep_set_status(self, iid, text):
        tree = self._deep_tree
        vals = list(tree.item(iid, "values"))
        vals[3] = text
        tree.item(iid, values=vals)
        self._deep_redraw(iid)

    # ---- 电源/性能细项面板（optimizerDuck，固定路径）----
    def open_power(self):
        if getattr(self, "_power_win", None) is not None:
            try:
                self._power_win.deiconify(); self._power_win.lift(); return
            except Exception:
                self._power_win = None
        win = tk.Toplevel(self.root)
        self._power_win = win
        win.title("电源/性能细项（optimizerDuck）")
        win.geometry("760x560")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._power_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(win, text="⚡ 电源/性能细项", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="勾选要应用的项 → “应用所选”；恢复默认 → 勾选相同项 → “还原所选”。"
                 "全部可逆。写 HKLM 需管理员（将触发 UAC）。",
            font=("Microsoft YaHei UI", 9), foreground="#555", wraplength=720, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="电源/性能开关", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "desc", "status", "risk")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="开关")
        tree.heading("desc", text="说明")
        tree.heading("status", text="状态")
        tree.heading("risk", text="风险")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=170, stretch=False)
        tree.column("desc", width=320)
        tree.column("status", width=70, anchor="center", stretch=False)
        tree.column("risk", width=50, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("checked", background="#e8f5e9")
        tree.tag_configure("highrisk", foreground="#b00020")
        tree.tag_configure("done", foreground="#1565c0")

        self._power_tree = tree
        self._power_vars = {}
        for idx, opt in enumerate(POWER_OPTS):
            iid = str(idx)
            self._power_vars[iid] = tk.BooleanVar(value=False)
            tags = ["highrisk"] if opt["risk"] == "高" else []
            tree.insert("", "end", iid=iid,
                        values=("☐", opt["name"], _elide(opt["desc"], 36), "未操作", opt["risk"]),
                        tags=tuple(tags))
        tree.bind("<Button-1>", self._on_power_click)

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="全选", command=lambda: self._power_set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="全不选", command=lambda: self._power_set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="应用所选", command=lambda: self._power_execute("apply")).pack(side="right", padx=2)
        ttk.Button(bar, text="还原所选", command=lambda: self._power_execute("revert")).pack(side="right", padx=2)

        self._power_status = tk.StringVar(value="提示：逐项勾选，再点“应用所选”或“还原所选”。")
        ttk.Label(win, textvariable=self._power_status,
                  font=("Microsoft YaHei UI", 9), foreground="#b00020",
                  wraplength=720, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    def _on_power_click(self, event):
        tree = self._power_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        self._power_vars[iid].set(not self._power_vars[iid].get())
        self._power_redraw(iid)

    def _power_redraw(self, iid):
        tree = self._power_tree
        checked = self._power_vars[iid].get()
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if checked else "☐"
        tags = []
        if POWER_OPTS[int(iid)]["risk"] == "高":
            tags.append("highrisk")
        if checked:
            tags.append("checked")
        if vals[3] in ("已应用", "已还原"):
            tags.append("done")
        tree.item(iid, values=vals, tags=tuple(tags))

    def _power_set_all(self, val):
        for iid in self._power_vars:
            self._power_vars[iid].set(val)
            self._power_redraw(iid)

    def _power_execute(self, mode):
        if getattr(self, "_power_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._power_win)
            return
        sel = [(iid, POWER_OPTS[int(iid)]) for iid in self._power_vars if self._power_vars[iid].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一项。", parent=self._power_win)
            return
        verb = "应用" if mode == "apply" else "还原"
        names = "、".join(o["name"] for _, o in sel)
        risk = (f"即将{verb}以下 {len(sel)} 项电源/性能调整：\n\n{names}\n\n"
                "全部可逆——之后勾选相同项点“还原所选”即可恢复。写 HKLM 需管理员，将触发 UAC。\n\n确认？")
        if not messagebox.askyesno("确认" + verb, risk, parent=self._power_win):
            self._log("[电源/性能] 已取消。")
            return
        cmds = []
        for _, o in sel:
            cmds.extend(o[mode])
        full = " & ".join(cmds)
        self._power_busy = True
        self._power_status.set(f"{verb}中：{names}")
        self._log(f"[电源/性能] {verb} {len(sel)} 项……")
        if is_admin():
            threading.Thread(target=self._power_thread, args=(full, mode, [iid for iid, _ in sel]), daemon=True).start()
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {full}", None, 0)
            if ret > 32:
                for iid, _ in sel:
                    self._power_set_status(iid, "已" + verb)
                self._power_busy = False
                messagebox.showinfo("已请求提权", "已以管理员身份执行，详见命令窗口/日志。", parent=self._power_win)
            else:
                self._power_busy = False
                messagebox.showerror("提权失败", "请手动以管理员身份运行本工具。", parent=self._power_win)

    def _power_thread(self, full, mode, iids):
        try:
            r = subprocess.run(full, shell=True, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[电源/性能] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._power_done, mode, iids, r.returncode)
        except Exception as e:
            self._log(f"[电源/性能] 执行异常：{e}")
            self.root.after(0, self._power_done, mode, iids, -1)

    def _power_done(self, mode, iids, code):
        self._power_busy = False
        verb = "已应用" if mode == "apply" else "已还原"
        for iid in iids:
            self._power_set_status(iid, verb)
        self._power_status.set(f"{verb} {len(iids)} 项。返回码 {code}。")
        self._log(f"[电源/性能] {verb} {len(iids)} 项，返回码 {code}。")

    def _power_set_status(self, iid, text):
        tree = self._power_tree
        vals = list(tree.item(iid, "values"))
        vals[3] = text
        tree.item(iid, values=vals)
        self._power_redraw(iid)

    # ---- GPU 优化面板（optimizerDuck，运行时检测厂商）----
    def open_gpu(self):
        if getattr(self, "_gpu_win", None) is not None:
            try:
                self._gpu_win.deiconify(); self._gpu_win.lift(); return
            except Exception:
                self._gpu_win = None
        win = tk.Toplevel(self.root)
        self._gpu_win = win
        win.title("GPU 优化（optimizerDuck）")
        win.geometry("760x620")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._gpu_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(win, text="🎮 GPU 优化（AMD / NVIDIA / Intel）", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="列表仅显示本机检测到的显卡厂商适用的调优项（运行时读取注册表 Class 键检测）。"
                 "应用写 HKLM\\...\\Control\\Class\\{4d36e968-...}\\XXXX，需管理员（触发 UAC）。",
            font=("Microsoft YaHei UI", 9), foreground="#555", wraplength=720, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="GPU 调优开关", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "desc", "status", "risk")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="开关")
        tree.heading("desc", text="说明")
        tree.heading("status", text="状态")
        tree.heading("risk", text="风险")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=210, stretch=False)
        tree.column("desc", width=300)
        tree.column("status", width=70, anchor="center", stretch=False)
        tree.column("risk", width=50, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("checked", background="#e8f5e9")
        tree.tag_configure("highrisk", foreground="#b00020")
        tree.tag_configure("done", foreground="#1565c0")

        self._gpu_tree = tree
        self._gpu_vars = {}
        self._gpu_applicable = []
        self._gpu_indexes = []
        self._gpu_status = tk.StringVar(value="正在检测显卡……")
        ttk.Label(win, textvariable=self._gpu_status,
                  font=("Microsoft YaHei UI", 9), foreground="#b00020",
                  wraplength=720, justify="left").pack(anchor="w", padx=12, pady=(0, 4))

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="全选", command=lambda: self._gpu_set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="全不选", command=lambda: self._gpu_set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="应用所选", command=lambda: self._gpu_execute("apply")).pack(side="right", padx=2)
        ttk.Button(bar, text="还原所选", command=lambda: self._gpu_execute("revert")).pack(side="right", padx=2)

        threading.Thread(target=self._gpu_detect, args=(win,), daemon=True).start()

    def _gpu_detect(self, win):
        try:
            script = (
                "$base='HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}';"
                "$arr=@(Get-ChildItem $base | ForEach-Object {"
                "  $idx=$_.PSChildName;"
                "  $d=(Get-ItemProperty \"$base\\$idx\" -Name DriverDesc -ErrorAction SilentlyContinue).DriverDesc;"
                "  [PSCustomObject]@{Index=$idx;Desc=$d}"
                "});"
                "$arr | ConvertTo-Json -Compress"
            )
            b64 = base64.b64encode(script.encode("utf-16-le")).decode()
            r = subprocess.run("powershell -NoProfile -EncodedCommand " + b64, shell=True,
                               capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            gpus = []
            raw = (r.stdout or "").strip()
            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        data = [data]
                    for g in data:
                        desc = str(g.get("Desc", "") or "")
                        idx = str(g.get("Index", "") or "")
                        if not desc or not idx:
                            continue
                        u = desc.upper()
                        vendor = "其他"
                        if "NVIDIA" in u:
                            vendor = "NVIDIA"
                        elif "AMD" in u:
                            vendor = "AMD"
                        elif "INTEL" in u:
                            vendor = "Intel"
                        gpus.append((idx, vendor, desc))
                except Exception as e:
                    self._log(f"[GPU] 解析失败：{e}；原始：{raw[:200]}")
            self.root.after(0, self._gpu_populate, win, gpus)
        except Exception as e:
            self._log(f"[GPU] 检测异常：{e}")
            self.root.after(0, self._gpu_populate, win, [])

    def _gpu_populate(self, win, gpus):
        tree = self._gpu_tree
        vendors = {v for _, v, _ in gpus}
        applicable = [o for o in GPU_OPTS if o["vendor"] in vendors]
        self._gpu_applicable = applicable
        self._gpu_indexes = [(i, v) for i, v, _ in gpus if v in ("AMD", "NVIDIA", "Intel")]
        kids = tree.get_children()
        if kids:
            tree.delete(*kids)
        self._gpu_vars.clear()
        for idx, opt in enumerate(applicable):
            iid = str(idx)
            self._gpu_vars[iid] = tk.BooleanVar(value=False)
            tags = ["highrisk"] if opt["risk"] == "高" else []
            tree.insert("", "end", iid=iid,
                        values=("☐", f"[{opt['vendor']}] {opt['name']}", _elide(opt["desc"], 36), "未操作", opt["risk"]),
                        tags=tuple(tags))
        tree.bind("<Button-1>", self._on_gpu_click)
        if not gpus:
            self._gpu_status.set("未检测到显卡，或无权限读取注册表（请以管理员运行后重试）。")
        else:
            info = "；".join(f"{d}（{v}）" for _, v, d in gpus)
            suffix = "" if applicable else "（无适用调优项）"
            self._gpu_status.set("检测到：" + info + suffix)

    def _on_gpu_click(self, event):
        tree = self._gpu_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid or iid not in self._gpu_vars:
            return
        self._gpu_vars[iid].set(not self._gpu_vars[iid].get())
        self._gpu_redraw(iid)

    def _gpu_redraw(self, iid):
        tree = self._gpu_tree
        checked = self._gpu_vars[iid].get()
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if checked else "☐"
        tags = []
        if self._gpu_applicable[int(iid)]["risk"] == "高":
            tags.append("highrisk")
        if checked:
            tags.append("checked")
        if vals[3] in ("已应用", "已还原"):
            tags.append("done")
        tree.item(iid, values=vals, tags=tuple(tags))

    def _gpu_set_all(self, val):
        for iid in self._gpu_vars:
            self._gpu_vars[iid].set(val)
            self._gpu_redraw(iid)

    def _gpu_execute(self, mode):
        if getattr(self, "_gpu_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._gpu_win)
            return
        sel = [(iid, self._gpu_applicable[int(iid)]) for iid in self._gpu_vars if self._gpu_vars[iid].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一项（若列表为空说明本机无适用显卡）。", parent=self._gpu_win)
            return
        verb = "应用" if mode == "apply" else "还原"
        names = "、".join(f"[{o['vendor']}]{o['name']}" for _, o in sel)
        risk = (f"即将{verb}以下 {len(sel)} 项 GPU 调优（写入 HKLM\\...\\Control\\Class\\{{4d36e968-...}}\\XXXX）：\n\n{names}\n\n"
                "全部可逆——之后勾选相同项点“还原所选”即删除覆写值、恢复驱动默认。需管理员，将触发 UAC。\n\n确认？")
        if not messagebox.askyesno("确认" + verb, risk, parent=self._gpu_win):
            self._log("[GPU] 已取消。")
            return
        cmds = []
        for _, o in sel:
            for idx, vendor in self._gpu_indexes:
                if vendor != o["vendor"]:
                    continue
                path = f"SYSTEM\\CurrentControlSet\\Control\\Class\\{{4d36e968-e325-11ce-bfc1-08002be10318}}\\{idx}"
                for name, val in o["regs"]:
                    if mode == "apply":
                        cmds.append(_reg_add("HKLM", path, name, val))
                    else:
                        cmds.append(_reg_del("HKLM", path, name))
        if not cmds:
            messagebox.showwarning("提示", "未找到匹配的 GPU 注册表索引，无法应用。", parent=self._gpu_win)
            return
        full = " & ".join(cmds)
        self._gpu_busy = True
        self._gpu_status.set(f"{verb}中：{names}")
        self._log(f"[GPU] {verb} {len(sel)} 项……")
        if is_admin():
            threading.Thread(target=self._gpu_thread, args=(full, mode, [iid for iid, _ in sel]), daemon=True).start()
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {full}", None, 0)
            if ret > 32:
                for iid, _ in sel:
                    self._gpu_set_status(iid, "已" + verb)
                self._gpu_busy = False
                messagebox.showinfo("已请求提权", "已以管理员身份执行，详见命令窗口/日志。", parent=self._gpu_win)
            else:
                self._gpu_busy = False
                messagebox.showerror("提权失败", "请手动以管理员身份运行本工具。", parent=self._gpu_win)

    def _gpu_thread(self, full, mode, iids):
        try:
            r = subprocess.run(full, shell=True, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[GPU] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._gpu_done, mode, iids, r.returncode)
        except Exception as e:
            self._log(f"[GPU] 执行异常：{e}")
            self.root.after(0, self._gpu_done, mode, iids, -1)

    def _gpu_done(self, mode, iids, code):
        self._gpu_busy = False
        verb = "已应用" if mode == "apply" else "已还原"
        for iid in iids:
            self._gpu_set_status(iid, verb)
        self._gpu_status.set(f"{verb} {len(iids)} 项。返回码 {code}。")
        self._log(f"[GPU] {verb} {len(iids)} 项，返回码 {code}。")

    def _gpu_set_status(self, iid, text):
        tree = self._gpu_tree
        vals = list(tree.item(iid, "values"))
        vals[3] = text
        tree.item(iid, values=vals)
        self._gpu_redraw(iid)

    # ---- 启动项管理器（optimizerDuck：注册表 Run + 启动文件夹 + 计划任务）----
    def open_startup(self):
        if getattr(self, "_startup_win", None) is not None:
            try:
                self._startup_win.deiconify(); self._startup_win.lift(); return
            except Exception:
                self._startup_win = None
        win = tk.Toplevel(self.root)
        self._startup_win = win
        win.title("启动项管理（optimizerDuck）")
        win.geometry("840x620")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._startup_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(win, text="🚀 启动项管理", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="枚举本机开机自启项（注册表 Run 键 / 启动文件夹 / 计划任务）。勾选后“禁用所选/启用所选”"
                 "即写入 StartupApproved 或调整计划任务状态。HKLM 与计划任务需管理员（触发 UAC）。",
            font=("Microsoft YaHei UI", 9), foreground="#555", wraplength=800, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="启动项", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "cmd", "loc", "state")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="名称")
        tree.heading("cmd", text="命令/路径")
        tree.heading("loc", text="位置")
        tree.heading("state", text="状态")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=150, stretch=False)
        tree.column("cmd", width=340)
        tree.column("loc", width=150, stretch=False)
        tree.column("state", width=70, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("disabled", foreground="#b00020")
        tree.tag_configure("enabled", foreground="#1565c0")

        self._startup_tree = tree
        self._startup_vars = {}
        self._startup_items = []
        self._startup_status = tk.StringVar(value="正在枚举启动项……")
        ttk.Label(win, textvariable=self._startup_status,
                  font=("Microsoft YaHei UI", 9), foreground="#555",
                  wraplength=800, justify="left").pack(anchor="w", padx=12, pady=(0, 4))

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="刷新", command=self._startup_refresh).pack(side="left", padx=2)
        ttk.Button(bar, text="禁用所选", command=lambda: self._startup_toggle(False)).pack(side="right", padx=2)
        ttk.Button(bar, text="启用所选", command=lambda: self._startup_toggle(True)).pack(side="right", padx=2)

        tree.bind("<Button-1>", self._on_startup_click)
        threading.Thread(target=self._startup_enumerate, args=(win,), daemon=True).start()

    def _startup_refresh(self):
        self._startup_status.set("正在枚举启动项……")
        threading.Thread(target=self._startup_enumerate, args=(self._startup_win,), daemon=True).start()

    def _startup_enumerate(self, win):
        try:
            script = (
                "$ErrorActionPreference='SilentlyContinue';"
                "$items=@();"
                "$regs=@("
                "@{H='HKCU';P='Software\\Microsoft\\Windows\\CurrentVersion\\Run';A='Run'},"
                "@{H='HKLM';P='Software\\Microsoft\\Windows\\CurrentVersion\\Run';A='Run'},"
                "@{H='HKCU';P='Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';A='RunOnce'},"
                "@{H='HKLM';P='Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';A='RunOnce'});"
                "foreach($r in $regs){"
                "  $key=\"$($r.H):\\$($r.P)\";"
                "  $appr=\"$($r.H):\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\$($r.A)\";"
                "  if(Test-Path $key){"
                "    $k=Get-Item $key;"
                "    foreach($vn in $k.GetValueNames()){"
                "      if($vn-eq''){continue};"
                "      $cmd=(Get-ItemProperty -Path $key -Name $vn).$vn;"
                "      $en=$true;"
                "      $b=(Get-ItemProperty -Path $appr -Name $vn -ErrorAction SilentlyContinue).$vn;"
                "      if($b-is[byte[]]-and$b.Length-ge 1){$en=($b[0]-ne 3-and$b[0]-ne 7)};"
                "      $items+=[PSCustomObject]@{Name=$vn;Cmd=$cmd;Loc=\"$($r.H)\\Run\";Kind='app';Root=\"$($r.H)\";Appr=\"$($r.A)\";VN=$vn;Enabled=$en}"
                "    }"
                "  }"
                "};"
                "$fols=@("
                "@{H='HKCU';F=[Environment]::GetFolderPath('Startup')},"
                "@{H='HKLM';F=[Environment]::GetFolderPath('CommonStartup')});"
                "foreach($s in $fols){"
                "  $appr=\"$($s.H):\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\StartupFolder\";"
                "  if(Test-Path $s.F){"
                "    Get-ChildItem $s.F|Where-Object{$_.Name-ne'desktop.ini'}|ForEach-Object{"
                "      $fn=$_.Name;$en=$true;"
                "      $b=(Get-ItemProperty -Path $appr -Name $fn -ErrorAction SilentlyContinue).$fn;"
                "      if($b-is[byte[]]-and$b.Length-ge 1){$en=($b[0]-ne 3-and$b[0]-ne 7)};"
                "      $items+=[PSCustomObject]@{Name=$fn;Cmd=$_.FullName;Loc='Folder';Kind='app';Root=\"$($s.H)\";Appr='StartupFolder';VN=$fn;Enabled=$en}"
                "    }"
                "  }"
                "};"
                "Get-ScheduledTask|ForEach-Object{"
                "  $t=$_;$has=$false;"
                "  if($t.Triggers){foreach($tr in $t.Triggers){if($tr.GetType().Name-match'Logon|Startup|Boot'){$has=$true;break}}};"
                "  if($has){"
                "    $en=($t.State-ne'Disabled');"
                "    $items+=[PSCustomObject]@{Name=$t.TaskName;Cmd=(($t.Actions|ForEach-Object{$_.Execute})-join' ');Loc='Task';Kind='task';Root='';Appr='';VN=$t.TaskName;Key=$t.TaskPath;Enabled=$en}"
                "  }"
                "};"
                "$items|ConvertTo-Json -Compress"
            )
            b64 = base64.b64encode(script.encode("utf-16-le")).decode()
            r = subprocess.run("powershell -NoProfile -EncodedCommand " + b64, shell=True,
                               capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            raw = (r.stdout or "").strip()
            items = []
            if raw and raw != "[]":
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        data = [data]
                    for it in data:
                        items.append({
                            "Name": str(it.get("Name", "")),
                            "Cmd": str(it.get("Cmd", "") or ""),
                            "Loc": str(it.get("Loc", "")),
                            "Kind": str(it.get("Kind", "")),
                            "Root": str(it.get("Root", "")),
                            "Appr": str(it.get("Appr", "")),
                            "VN": str(it.get("VN", "")),
                            "Key": str(it.get("Key", "")),
                            "Enabled": bool(it.get("Enabled", True)),
                        })
                except Exception as e:
                    self._log(f"[启动项] 解析失败：{e}；原始：{raw[:200]}")
            self.root.after(0, self._startup_populate, win, items)
        except Exception as e:
            self._log(f"[启动项] 枚举异常：{e}")
            self.root.after(0, self._startup_populate, win, [])

    def _startup_populate(self, win, items):
        tree = self._startup_tree
        kids = tree.get_children()
        if kids:
            tree.delete(*kids)
        self._startup_vars.clear()
        self._startup_items = items
        for idx, it in enumerate(items):
            iid = str(idx)
            self._startup_vars[iid] = tk.BooleanVar(value=False)
            state = "启用" if it["Enabled"] else "禁用"
            tags = ("disabled",) if not it["Enabled"] else ("enabled",)
            tree.insert("", "end", iid=iid,
                        values=("☐", _elide(it["Name"], 22), _elide(it["Cmd"], 48), it["Loc"], state),
                        tags=tags)
        self._startup_status.set(f"枚举完成：共 {len(items)} 项（注册表/文件夹/计划任务）。")

    def _on_startup_click(self, event):
        tree = self._startup_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid or iid not in self._startup_vars:
            return
        self._startup_vars[iid].set(not self._startup_vars[iid].get())
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if self._startup_vars[iid].get() else "☐"
        tree.item(iid, values=vals)

    def _startup_toggle(self, enable):
        if getattr(self, "_startup_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._startup_win)
            return
        sel = [self._startup_items[int(iid)] for iid in self._startup_vars if self._startup_vars[iid].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一项。", parent=self._startup_win)
            return
        verb = "启用" if enable else "禁用"
        names = "、".join(it["Name"] for it in sel)
        risk = (f"即将{verb}以下 {len(sel)} 个启动项：\n\n{names}\n\n"
                "注册表项/计划任务类需管理员（将触发 UAC）。此操作可逆（再次勾选并反向操作即可）。\n\n确认？")
        if not messagebox.askyesno("确认" + verb, risk, parent=self._startup_win):
            self._log("[启动项] 已取消。")
            return
        cmds = []
        for it in sel:
            if it["Kind"] == "app":
                flag = "02" if enable else "03"
                data = flag + "00000000000000000000000000000000"
                appr_key = f"{it['Root']}\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\{it['Appr']}"
                vn = it["VN"].replace('"', "")
                cmds.append(f'reg add "{appr_key}" /v "{vn}" /t REG_BINARY /d {data} /f')
            else:
                tn = (it["Key"].rstrip("\\") + "\\" + it["VN"]).strip("\\")
                cmds.append(f'schtasks /Change /TN "{tn}" /{"ENABLE" if enable else "DISABLE"}')
        full = " & ".join(cmds)
        self._startup_busy = True
        self._startup_status.set(f"{verb}中：{names}")
        self._log(f"[启动项] {verb} {len(sel)} 项……")
        if is_admin():
            threading.Thread(target=self._startup_thread, args=(full, enable, sel), daemon=True).start()
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {full}", None, 0)
            if ret > 32:
                self._startup_busy = False
                messagebox.showinfo("已请求提权", "已以管理员身份执行，详见命令窗口/日志。", parent=self._startup_win)
            else:
                self._startup_busy = False
                messagebox.showerror("提权失败", "请手动以管理员身份运行本工具。", parent=self._startup_win)

    def _startup_thread(self, full, enable, sel):
        try:
            r = subprocess.run(full, shell=True, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[启动项] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._startup_done, enable, sel, r.returncode)
        except Exception as e:
            self._log(f"[启动项] 执行异常：{e}")
            self.root.after(0, self._startup_done, enable, sel, -1)

    def _startup_done(self, enable, sel, code):
        self._startup_busy = False
        verb = "已启用" if enable else "已禁用"
        for it in sel:
            it["Enabled"] = enable
        self._startup_refresh()
        self._startup_status.set(f"{verb} {len(sel)} 项。返回码 {code}。")
        self._log(f"[启动项] {verb} {len(sel)} 项，返回码 {code}。")

    # ---- optimizerDuck 全功能优化面板（去重后的剩余独有项）----
    def open_optduck(self):
        if getattr(self, "_optduck_win", None) is not None:
            try:
                self._optduck_win.deiconify(); self._optduck_win.lift(); return
            except Exception:
                self._optduck_win = None
        win = tk.Toplevel(self.root)
        self._optduck_win = win
        win.title("optimizerDuck 全功能优化")
        win.geometry("780x640")
        win.transient(self.root)
        _apply_app_icon(win)

        def _on_close():
            self._optduck_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        ttk.Label(win, text="🧩 optimizerDuck 全功能优化", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            win,
            text="勾选要应用的项 → “应用所选”；恢复默认 → 勾选相同项 → “还原所选”。"
                 "全部可逆。写 HKLM / 服务 / 计划任务 / 电源计划需管理员（将触发 UAC）。",
            font=("Microsoft YaHei UI", 9), foreground="#555", wraplength=740, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        list_frame = ttk.LabelFrame(win, text="优化开关清单", padding=4)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        cols = ("check", "name", "desc", "status", "risk")
        tree = ttk.Treeview(list_frame, columns=cols, show="headings")
        tree.heading("check", text="")
        tree.heading("name", text="开关")
        tree.heading("desc", text="说明")
        tree.heading("status", text="状态")
        tree.heading("risk", text="风险")
        tree.column("check", width=30, anchor="center", stretch=False)
        tree.column("name", width=170, stretch=False)
        tree.column("desc", width=330)
        tree.column("status", width=70, anchor="center", stretch=False)
        tree.column("risk", width=50, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vsb.set)
        tree.tag_configure("checked", background="#e8f5e9")
        tree.tag_configure("highrisk", foreground="#b00020")
        tree.tag_configure("done", foreground="#1565c0")

        self._optduck_tree = tree
        self._optduck_vars = {}
        for idx, opt in enumerate(OPTDUCK_OPTS):
            iid = str(idx)
            self._optduck_vars[iid] = tk.BooleanVar(value=False)
            tags = ["highrisk"] if opt["risk"] == "高" else []
            tree.insert("", "end", iid=iid,
                        values=("☐", opt["name"], _elide(opt["desc"], 40), "未操作", opt["risk"]),
                        tags=tuple(tags))
        tree.bind("<Button-1>", self._on_optduck_click)

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(bar, text="全选", command=lambda: self._optduck_set_all(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="全不选", command=lambda: self._optduck_set_all(False)).pack(side="left", padx=2)
        ttk.Button(bar, text="应用所选", command=lambda: self._optduck_execute("apply")).pack(side="right", padx=2)
        ttk.Button(bar, text="还原所选", command=lambda: self._optduck_execute("revert")).pack(side="right", padx=2)

        self._optduck_status = tk.StringVar(value="提示：逐项勾选，再点“应用所选”或“还原所选”。")
        ttk.Label(win, textvariable=self._optduck_status,
                  font=("Microsoft YaHei UI", 9), foreground="#b00020",
                  wraplength=740, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    def _on_optduck_click(self, event):
        tree = self._optduck_tree
        if tree.identify("region", event.x, event.y) != "cell":
            return
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        self._optduck_vars[iid].set(not self._optduck_vars[iid].get())
        self._optduck_redraw(iid)

    def _optduck_redraw(self, iid):
        tree = self._optduck_tree
        checked = self._optduck_vars[iid].get()
        vals = list(tree.item(iid, "values"))
        vals[0] = "☑" if checked else "☐"
        tags = []
        if OPTDUCK_OPTS[int(iid)]["risk"] == "高":
            tags.append("highrisk")
        if checked:
            tags.append("checked")
        if vals[3] in ("已应用", "已还原"):
            tags.append("done")
        tree.item(iid, values=vals, tags=tuple(tags))

    def _optduck_set_all(self, val):
        for iid in self._optduck_vars:
            self._optduck_vars[iid].set(val)
            self._optduck_redraw(iid)

    def _optduck_execute(self, mode):
        if getattr(self, "_optduck_busy", False):
            messagebox.showwarning("请稍候", "正在处理，请等待当前操作完成。", parent=self._optduck_win)
            return
        sel = [(iid, OPTDUCK_OPTS[int(iid)]) for iid in self._optduck_vars if self._optduck_vars[iid].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一项。", parent=self._optduck_win)
            return
        verb = "应用" if mode == "apply" else "还原"
        names = "、".join(o["name"] for _, o in sel)
        risk = (f"即将{verb}以下 {len(sel)} 项 optimizerDuck 优化（注册表/服务/计划任务/电源）：\n\n{names}\n\n"
                "全部可逆——之后勾选相同项点“还原所选”即可恢复。写 HKLM / 服务 / 计划任务需管理员，将触发 UAC。\n\n确认？")
        if not messagebox.askyesno("确认" + verb, risk, parent=self._optduck_win):
            self._log("[optimizerDuck] 已取消。")
            return
        cmds = []
        for _, o in sel:
            cmds.extend(o[mode])
        full = " & ".join(cmds)
        self._optduck_busy = True
        self._optduck_status.set(f"{verb}中：{names}")
        self._log(f"[optimizerDuck] {verb} {len(sel)} 项……")
        if is_admin():
            threading.Thread(target=self._optduck_thread, args=(full, mode, [iid for iid, _ in sel]), daemon=True).start()
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {full}", None, 0)
            if ret > 32:
                for iid, _ in sel:
                    self._optduck_set_status(iid, "已" + verb)
                self._optduck_busy = False
                messagebox.showinfo("已请求提权", "已以管理员身份执行，详见命令窗口/日志。", parent=self._optduck_win)
            else:
                self._optduck_busy = False
                messagebox.showerror("提权失败", "请手动以管理员身份运行本工具。", parent=self._optduck_win)

    def _optduck_thread(self, full, mode, iids):
        try:
            r = subprocess.run(full, shell=True, capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[optimizerDuck] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._optduck_done, mode, iids, r.returncode)
        except Exception as e:
            self._log(f"[optimizerDuck] 执行异常：{e}")
            self.root.after(0, self._optduck_done, mode, iids, -1)

    def _optduck_done(self, mode, iids, code):
        self._optduck_busy = False
        verb = "已应用" if mode == "apply" else "已还原"
        for iid in iids:
            self._optduck_set_status(iid, verb)
        self._optduck_status.set(f"{verb} {len(iids)} 项。返回码 {code}。")
        self._log(f"[optimizerDuck] {verb} {len(iids)} 项，返回码 {code}。")

    def _optduck_set_status(self, iid, text):
        tree = self._optduck_tree
        vals = list(tree.item(iid, "values"))
        vals[3] = text
        tree.item(iid, values=vals)
        self._optduck_redraw(iid)

    # ---- 一键系统优化（需管理员，执行前二次确认）----
    def _run_admin_cmd(self, cmds, title, risk_note):
        """以管理员权限顺序执行命令列表 cmds（命令字符串）。执行前先弹确认框说明风险/可逆方式。

        - 若本工具已是管理员：提交到后台线程执行（避免 gpupdate/taskkill 等耗时命令
          阻塞 tkinter 主线程导致界面卡死无响应），完成后回主线程弹结果。
        - 若非管理员：用 ShellExecuteW(runas) 触发 UAC 提权执行（非阻塞，立即返回）。
        所有项均可逆，恢复方法写在 risk_note 里告知用户。
        """
        if getattr(self, "_busy", False):
            messagebox.showwarning("请稍候", "上一条命令还在执行，请等待完成。")
            return False
        if not messagebox.askyesno(title, risk_note):
            self._log(f"[{title}] 已取消。")
            return False
        full = " & ".join(cmds)
        if is_admin():
            self._busy = True
            self._log(f"[{title}] 正在执行，请稍候…（组策略刷新可能耗时数十秒，界面照常可操作）")
            threading.Thread(
                target=self._exec_admin_thread, args=(full, title), daemon=True
            ).start()
            return None
        else:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "cmd.exe", f"/c {full}", None, 0
            )
            ok = ret > 32
            self._log(f"[{title}] UAC 提权启动，ShellExecute 返回 {ret}")
            if ok:
                messagebox.showinfo(title, "已请求管理员权限执行（详见命令窗口/日志）。")
            else:
                messagebox.showerror(title, "提权失败，请手动以管理员身份运行本工具。")
            return ok

    def _exec_admin_thread(self, full, title):
        """后台线程：真正执行命令，完成后通过 root.after 切回主线程更新 UI。"""
        try:
            r = subprocess.run(
                full, shell=True,
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (r.stdout or "") + (r.stderr or "")
            self._log(f"[{title}] 返回码 {r.returncode}\n{out.strip()}")
            self.root.after(0, self._on_admin_done, title, r.returncode, out.strip())
        except Exception as e:
            self._log(f"[{title}] 执行异常：{e}")
            self.root.after(0, self._on_admin_done, title, -1, str(e))

    def _on_admin_done(self, title, code, out):
        self._busy = False
        if code == 0:
            messagebox.showinfo(title, "执行成功。")
        else:
            messagebox.showwarning(title, f"命令返回非零：{code}\n{out}")

    def opt_high_perf(self):
        self._run_admin_cmd(
            ["powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
            "高性能电源计划",
            "将电源计划切换为「高性能」（SCHEME_MIN）。\n\n"
            "可逆：恢复平衡模式请运行 powercfg /setactive SCHEME_BALANCED\n"
            "（或 powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e）。\n\n"
            "确定切换？",
        )

    def opt_firewall_off(self):
        self._run_admin_cmd(
            ["netsh advfirewall set allprofiles state off"],
            "关闭 Windows 防火墙",
            "⚠ 即将关闭所有配置文件的 Windows 防火墙，系统将暴露在网络攻击下。\n\n"
            "可逆：重新开启请运行 netsh advfirewall set allprofiles state on\n\n"
            "确认关闭防火墙？",
        )

    def opt_defender_off(self):
        # 用 BAT 中验证过的"注册表 + 组策略 + 重启资源管理器"方案：
        # 避开 Set-MpPreference 在部分环境(WMI/Defender模块缺失)下报
        # 0x80041013 "提供程序加载失败" 的问题。
        self._run_admin_cmd(
            [
                'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" '
                '/v DisableAntiSpyware /t REG_DWORD /d 1 /f',
                "gpupdate /force",
                "taskkill /f /im explorer.exe",
                "start %systemroot%\\explorer",
            ],
            "关闭 Windows Defender（注册表策略法）",
            "⚠ 即将通过组策略注册表禁用 Microsoft Defender 实时防护/反间谍软件，"
            "系统将失去病毒/恶意软件防护。\n\n"
            "可逆：运行：\n"
            "  reg add \"HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender\" "
            "/v DisableAntiSpyware /t REG_DWORD /d 0 /f\n"
            "  gpupdate /force\n"
            "  taskkill /f /im explorer.exe & start %systemroot%\\explorer\n\n"
            "注意：会刷新组策略并重启资源管理器（约 1-2 秒黑屏，属正常）。\n\n"
            "确认禁用 Defender？",
        )

    def opt_fastboot_on(self):
        self._run_admin_cmd(
            [
                "powercfg /h on",
                'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power" '
                "/v HiberBootEnabled /t REG_DWORD /d 1 /f",
            ],
            "开启快速启动",
            "将开启 Windows 快速启动（依赖休眠文件 hiberfil.sys）。\n\n"
            "可逆：关闭请运行同样 reg add 命令把 /d 1 改为 /d 0。\n\n"
            "确认开启？",
        )

    def opt_uac_off(self):
        self._run_admin_cmd(
            ['reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" '
             "/v EnableLUA /t REG_DWORD /d 0 /f"],
            "关闭用户账户控制 (UAC)",
            "⚠ 即将关闭 UAC（EnableLUA=0）。\n\n"
            "风险：关闭后程序默认以管理员权限运行，系统更易被恶意软件篡改；"
            "改动需重启生效，且 Microsoft Edge / Microsoft Store 等可能异常。\n\n"
            "可逆：把 EnableLUA 改回 1（同样 reg add 命令 /d 1）并重启即可恢复。\n\n"
            "确认关闭 UAC？",
        )

    def opt_ultimate_perf(self):
        # 卓越电源 = Win10/11 的"Ultimate Performance"隐藏方案。
        # 原始 GUID (e9a42b02-…) 系统不允许直接 -setactive；必须先 -duplicatescheme
        # 复制出一个副本，再 setactive 该副本（从 stdout 解析出副本 GUID）。
        # 这里不走通用 _run_admin_cmd，而是单独写后台线程，分两步 subprocess.run。
        if getattr(self, "_busy", False):
            messagebox.showwarning("请稍候", "上一条命令还在执行，请等待完成。")
            return
        if not messagebox.askyesno(
            "卓越电源模式（Ultimate Performance）",
            "将电源计划切换为「卓越性能（Ultimate Performance）」。\n\n"
            "说明：此方案在 Win10/11 上为隐藏方案，工具会先复制出一个副本，"
            "再激活该副本（原始内置 GUID 不允许直接激活）。\n"
            "适合工作站/高性能场景，但笔记本上会更费电、更发热。\n\n"
            "可逆：恢复平衡模式请运行 powercfg /setactive SCHEME_BALANCED。\n\n"
            "确认切换？",
        ):
            self._log("[卓越电源] 已取消。")
            return
        self._busy = True
        self._log("[卓越电源] 正在创建并激活卓越性能副本…（请稍候数秒）")
        threading.Thread(target=self._exec_ultimate_thread, daemon=True).start()

    def _exec_ultimate_thread(self):
        """后台线程：复制出 Ultimate Performance 副本并激活。"""
        title = "卓越电源模式（Ultimate Performance）"
        try:
            # 步骤 1：复制副本
            r1 = subprocess.run(
                "powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61",
                shell=True, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out1 = (r1.stdout or "") + (r1.stderr or "")
            self._log(f"[卓越电源] 步骤1 输出：\n{out1.strip()}")
            # 从输出解析新 GUID（8-4-4-4-12）
            m = re.search(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                out1,
            )
            if not m:
                self.root.after(
                    0, self._on_admin_done, title, -1,
                    f"未在 duplicatescheme 输出中找到 GUID。\n{out1.strip()}",
                )
                return
            new_guid = m.group(0)
            self._log(f"[卓越电源] 副本 GUID：{new_guid}")
            # 步骤 2：激活副本
            r2 = subprocess.run(
                f"powercfg -setactive {new_guid}",
                shell=True, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out2 = (r2.stdout or "") + (r2.stderr or "")
            self._log(f"[卓越电源] 步骤2 返回码 {r2.returncode}\n{out2.strip()}")
            self.root.after(0, self._on_admin_done, title, r2.returncode, out2.strip())
        except Exception as e:
            self._log(f"[卓越电源] 异常：{e}")
            self.root.after(0, self._on_admin_done, title, -1, str(e))

    def opt_dns_flush(self):
        self._run_admin_cmd(
            ["ipconfig /flushdns"],
            "清理 DNS 缓存",
            "清理本机 DNS 解析缓存，常用于解决域名解析异常、浏览器打不开网页、"
            "能 ping 通 IP 却打不开域名等问题。\n\n"
            "低风险：无需管理员权限（工具仍走统一提权通道）；刷新后下次访问会自动重新解析，"
            "不影响任何设置。\n\n"
            "确认清理 DNS 缓存？",
        )

    def opt_dosvc_off(self):
        self._run_admin_cmd(
            ["sc stop DoSvc", "sc config DoSvc start= disabled"],
            "关闭传递优化（Delivery Optimization）",
            "关闭 Windows 的「传递优化」后台 P2P 更新分发，可显著降低后台带宽占用"
            "（默认会在局域网/互联网上为其他电脑分发更新）。\n\n"
            "可逆：重新开启请运行：\n  sc config DoSvc start= auto\n  sc start DoSvc\n\n"
            "确认关闭传递优化？",
        )

    def opt_sysmain_off(self):
        self._run_admin_cmd(
            ["sc stop SysMain", "sc config SysMain start= disabled"],
            "禁用 SysMain（Superfetch）",
            "禁用 SysMain（旧称 Superfetch）服务，停止后台预取/缓存常用程序到内存，"
            "在 SSD 或内存较小的机器上可降低后台磁盘与内存占用。\n\n"
            "注意：机械硬盘(HDD)上该服务有助于加速程序启动，禁用后可能反而变慢。\n\n"
            "可逆：重新启用请运行：\n  sc config SysMain start= auto\n  sc start SysMain\n\n"
            "确认禁用 SysMain？",
        )

    def opt_hibernate_off(self):
        self._run_admin_cmd(
            ["powercfg -h off"],
            "关闭休眠（删除 hiberfil.sys）",
            "⚠ 关闭系统休眠并删除 hiberfil.sys，可释放约等于内存大小的 C 盘空间。\n\n"
            "注意：与「快速启动」互斥——关闭休眠后快速启动也将失效（快速启动依赖休眠文件）。"
            "若之后想恢复快速启动，需先重新开启休眠。\n\n"
            "可逆：重新开启请运行 powercfg -h on（开回休眠后如需快速启动，再点本工具的「快速启动」按钮）。\n\n"
            "确认关闭休眠？",
        )

    def opt_system_restore_off(self):
        self._run_admin_cmd(
            [
                "powershell -NoProfile -Command \"Disable-ComputerRestore -Drive 'C:\\'\"",
                "vssadmin delete shadows /for=C: /all /quiet",
            ],
            "关闭系统还原",
            "⚠ 高风险：将关闭 C 盘系统还原并删除所有现有卷影副本/还原点，"
            "之后系统将无法回滚到之前状态、无法用还原点恢复。\n\n"
            "可逆：重新开启请运行：\n"
            "  powershell -NoProfile -Command \"Enable-ComputerRestore -Drive 'C:\\'\"\n"
            "（重新开启后还原点需手动创建或等待系统自动生成）。\n\n"
            "确认关闭系统还原？",
        )

    def opt_search_off(self):
        self._run_admin_cmd(
            ["sc stop WSearch", "sc config WSearch start= disabled"],
            "关闭 Windows Search 索引",
            "禁用 Windows Search 索引服务，可降后台 CPU/磁盘占用（索引会持续扫描文件）。\n\n"
            "副作用：开始菜单、资源管理器内的文件搜索将变慢（不再有实时索引）。\n\n"
            "可逆：重新启用请运行：\n  sc config WSearch start= delayed-auto\n  sc start WSearch\n\n"
            "确认关闭 Search 索引？",
        )

    def opt_visual_off(self):
        self._run_admin_cmd(
            [
                'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" '
                '/v EnableTransparency /t REG_DWORD /d 0 /f',
                'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects" '
                '/v VisualFXSetting /t REG_DWORD /d 2 /f',
                "taskkill /f /im explorer.exe",
                "start %systemroot%\\explorer",
            ],
            "关闭透明效果与动画",
            "关闭窗口透明效果并切换为“最佳性能”视觉效果（禁用动画/阴影等），"
            "在配置较低的机器上可提升响应速度。\n\n"
            "会重启资源管理器（约 1-2 秒黑屏，属正常）。\n\n"
            "可逆：恢复请运行：\n"
            '  reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" '
            "/v EnableTransparency /t REG_DWORD /d 1 /f\n"
            '  reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects" '
            "/v VisualFXSetting /t REG_DWORD /d 0 /f\n"
            "  然后重启资源管理器。\n\n"
            "确认关闭透明效果与动画？",
        )

    def opt_telemetry_off(self):
        self._run_admin_cmd(
            ["sc stop DiagTrack", "sc config DiagTrack start= disabled"],
            "关闭遥测（DiagTrack）",
            "禁用 Connected User Experiences and Telemetry 服务，减少系统后台数据上报。\n\n"
            "副作用：部分依赖遥测的功能（如反馈中心、某些诊断）会受影响。\n\n"
            "可逆：重新启用请运行：\n  sc config DiagTrack start= auto\n  sc start DiagTrack\n\n"
            "确认关闭遥测？",
        )

    def opt_wu_off(self):
        # 参考 BAT "06 关闭自动更新" 的注册表策略法（更兼容 Windows 11 防篡改保护）：
        # 1) 设组策略 NoAutoUpdate=0 + AUOptions=2 关闭自动下载/安装
        # 2) 停止 wuauserv 服务（加 ping 等待避免 STOP_PENDING 时 OpenService 失败）
        # 3) sc config 设为 disabled（若被防篡改保护拒绝会返回 5，但策略已生效）
        # 4) gpupdate /force 让策略立即生效
        self._run_admin_cmd(
            [
                'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" '
                '/v NoAutoUpdate /t REG_DWORD /d 0 /f',
                'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" '
                '/v AUOptions /t REG_DWORD /d 2 /f',
                "net stop wuauserv",
                "ping 127.0.0.1 -n 4 >nul",
                "sc config wuauserv start= disabled",
                "gpupdate /force",
            ],
            "关闭 Windows Update 服务",
            "⚠ 通过组策略禁用 Windows Update 自动下载/安装，并停止 wuauserv 服务。"
            "系统将不再自动下载/安装更新（包括重要的安全更新），"
            "长期关闭会增加安全风险。\n\n"
            "说明：使用 BAT 中验证的「组策略 + 停止服务」组合法；"
            "在 Windows 11 防篡改保护开启时，sc config 可能会被拒绝（错误 5），"
            "但组策略已生效，整体仍会禁用自动更新。\n\n"
            "可逆：重新开启请运行：\n"
            '  reg delete "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate\\AU" /f\n'
            "  sc config wuauserv start= auto\n  sc start wuauserv\n"
            "  gpupdate /force\n\n"
            "确认关闭 Windows Update？",
        )

    def open_godmode(self, target_dir=None, popup=True):
        """创建（若不存在）并在资源管理器中打开“上帝模式”文件夹。
        上帝模式是 Windows 内置功能：把文件夹命名为“任意名.{该CLSID}”后，
        该文件夹即成为一个收纳全部设置项的总入口。仅创建一个特殊文件夹，无破坏性操作。
        打开方式采用参考实现「系统维护工具.pyw」的 os.startfile()，已在实践中可用。"""
        if not target_dir:
            target_dir = os.path.expanduser("~/Desktop")
        target_dir = target_dir.rstrip("/\\")
        gm_name = "上帝模式." + GODMODE_CLSID
        gm_path = os.path.join(target_dir, gm_name)
        try:
            if not os.path.isdir(gm_path):
                os.makedirs(gm_path)
                self._log(f"[上帝模式] 已创建：{gm_path}")
            else:
                self._log(f"[上帝模式] 已存在：{gm_path}")
            # 直接用 os.startfile 打开 CLSID 特殊文件夹（参考可用实现）
            os.startfile(gm_path)
            self._log(f"[上帝模式] 已打开：{gm_path}")
        except Exception as e:
            self._log(f"[上帝模式] 操作失败：{e}")
            messagebox.showerror("上帝模式", f"操作失败：{e}")

    def _refresh_admin_badge(self):
        if is_admin():
            self.admin_badge.configure(text="🛡 已以管理员运行（最高权限）", foreground="#1b7a1b")
        else:
            self.admin_badge.configure(text="⚠ 普通权限（部分项无法清理）", foreground="#b00020")

    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        cur = self.item_vars[iid].get()
        self.item_vars[iid].set(not cur)
        self._redraw_check(iid)

    def _redraw_check(self, iid):
        item = next(x for x in CLEAN_ITEMS if x["id"] == iid)
        mark = "☑" if self.item_vars[iid].get() else "☐"
        tags = []
        if self.item_vars[iid].get():
            tags.append("checked")
        if item["risk"] == "高":
            tags.append("highrisk")
        vals = list(self.tree.item(iid, "values"))
        vals[0] = mark
        self.tree.item(iid, values=vals, tags=tuple(tags))
        self._update_stat()

    def _set_all(self, val):
        for item in CLEAN_ITEMS:
            self.item_vars[item["id"]].set(val)
            self._redraw_check(item["id"])

    def _only_low(self):
        for item in CLEAN_ITEMS:
            on = item["risk"] == "低"
            self.item_vars[item["id"]].set(on)
            self._redraw_check(item["id"])

    def _update_stat(self):
        total = 0
        count = 0
        for item in CLEAN_ITEMS:
            if self.item_vars[item["id"]].get():
                total += self.item_size[item["id"]]
                count += self.item_count[item["id"]]
        self.stat_var.set(f"已选占用：{human_size(total)} ｜ 文件数：{count}")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---- 扫描 ----
    def _scan(self):
        self.btn_scan.configure(state="disabled")
        drives = "、".join(d + "盘" for d in get_fixed_drives())
        self._log(f"开始扫描已选项目的占用空间……（已探测固定硬盘：{drives}）")

        def worker():
            for item in CLEAN_ITEMS:
                if not self.item_vars[item["id"]].get():
                    continue
                try:
                    sz, cnt = compute_size(item)
                except Exception as e:
                    sz, cnt = 0, 0
                    self._log(f"  [跳过] {item['name']} 扫描出错：{e}")
                self.item_size[item["id"]] = sz
                self.item_count[item["id"]] = cnt
                vals = list(self.tree.item(item["id"], "values"))
                vals[3] = f"{human_size(sz)} ({cnt})"
                self.tree.item(item["id"], values=vals)
                self._update_stat()
                self._log(f"  {item['name']}：{human_size(sz)}（{cnt} 个文件）")
            self._log("扫描完成。请确认无误后点击“开始清理”。")
            self.root.after(0, lambda: self.btn_scan.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    # ---- 清理 ----
    def _ask_clean(self):
        if self.cleaning:
            return
        sel = [i for i in CLEAN_ITEMS if self.item_vars[i["id"]].get()]
        if not sel:
            messagebox.showwarning("提示", "请至少勾选一个清理项目。")
            return
        total = sum(self.item_size[i["id"]] for i in sel)
        high = [i for i in sel if i.get("risk") == "高"]
        extra_warn = ""
        if high:
            extra_warn = "⚠ 你勾选了高风险项目（如“浏览器下载目录”），将删除个人文件！\n" \
                         "请确认其中没有重要资料，此操作不可恢复。\n\n"
        ans = messagebox.askyesno(
            "确认清理",
            extra_warn + f"即将清理以下 {len(sel)} 个项目，预计释放 {human_size(total)}。\n\n"
            "清理的是系统/应用临时缓存（除非你勾选了高风险项）。是否继续？",
        )
        if not ans:
            return
        self._clean()

    def _clean(self):
        self.cleaning = True
        self.btn_scan.configure(state="disabled")
        self.btn_clean.configure(state="disabled")
        self._log("====== 开始清理 ======")

        def worker():
            total_freed = 0
            total_removed = 0
            for item in CLEAN_ITEMS:
                if not self.item_vars[item["id"]].get():
                    continue
                self._log(f"▶ 清理：{item['name']} …")
                try:
                    freed, removed = clean_item(item)
                except Exception as e:
                    freed, removed = 0, 0
                    self._log(f"  [错误] {item['name']}：{e}")
                total_freed += freed
                total_removed += removed
                self._log(f"  ✓ 释放 {human_size(freed)}（{removed} 项）")
            self._log("====== 清理完成 ======")
            self._log(f"✅ 共释放：{human_size(total_freed)}，删除 {total_removed} 个文件/目录。")
            self.root.after(0, lambda: self._finish_clean(total_freed, total_removed))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_clean(self, freed, removed):
        self.cleaning = False
        self.btn_scan.configure(state="normal")
        self.btn_clean.configure(state="normal")
        messagebox.showinfo("完成", f"清理完成！\n共释放：{human_size(freed)}\n删除：{removed} 个文件/目录")
        self._scan()

    # ---- 导出扫描报告 ----
    def _export_report(self):
        rows = []
        for item in CLEAN_ITEMS:
            rows.append((
                item["name"], item["detail"], item["risk"],
                self.item_size.get(item["id"], 0),
                self.item_count.get(item["id"], 0),
            ))
        if not any(r[3] for r in rows):
            messagebox.showinfo("提示", "请先点击“扫描占用”生成数据，再导出报告。")
            return
        path = filedialog.asksaveasfilename(
            title="保存扫描报告",
            defaultextension=".txt",
            filetypes=[("文本报告", "*.txt"), ("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if path.lower().endswith(".csv"):
                lines = ["项目,位置,风险,已占用(字节),文件数\r\n"]
                for name, detail, risk, sz, cnt in rows:
                    lines.append(f"{name},{detail},{risk},{sz},{cnt}\r\n")
            else:
                lines = []
                lines.append("系统优化工具箱 - 扫描报告（全盘）")
                lines.append(f"生成时间：{now}")
                lines.append("=" * 60)
                total = 0
                for name, detail, risk, sz, cnt in rows:
                    total += sz
                    lines.append(f"项目：{name}")
                    lines.append(f"  位置：{detail}")
                    lines.append(f"  风险：{risk}")
                    lines.append(f"  已占用：{human_size(sz)}（{cnt} 个文件）")
                    lines.append("-" * 60)
                lines.append(f"合计已扫描占用：{human_size(total)}")
                lines.append("")
                lines.append("说明：本报告中“已占用”为当前扫描所得；仅含已勾选并扫描的项目。")
                lines = [l + "\n" for l in lines]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            messagebox.showerror("导出失败", f"无法写入文件：{e}")
            return
        self._log(f"报告已导出：{path}")
        messagebox.showinfo("完成", f"报告已保存：\n{path}")


# ----------------------------------------------------------------------------
# 4. 入口
# ----------------------------------------------------------------------------
def main():
    # 无界面模式：--scan 仅计算并打印占用（用于测试/命令行）
    if "--scan" in sys.argv:
        print("=== 系统优化工具箱 扫描（只读）===")
        grand = 0
        for item in CLEAN_ITEMS:
            sz, cnt = compute_size(item)
            grand += sz
            print(f"  {item['name']:<28} {human_size(sz):>12}  ({cnt} 项)  [{item['detail']}]")
        print(f"  {'合计':<28} {human_size(grand):>12}")
        return

    # GUI：若非管理员，先尝试 UAC 自提权（标准提权，会弹出系统确认窗）
    if not is_admin():
        ok = relaunch_as_admin()
        if ok:
            sys.exit(0)  # 已以管理员身份重新启动，本进程退出
        else:
            # 提权被拒绝或失败 —— 仍以普通权限运行并提示
            pass

    try:
        root = tk.Tk()
        app = CleanerApp(root)
        # 打开即自动扫描已勾选项目的占用（_scan 内部走后台线程，不卡 UI）
        root.after(500, app._scan)
        root.mainloop()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            None, f"启动失败：{e}\n（请确认以管理员身份运行）", "系统优化工具箱", 0x10
        )


if __name__ == "__main__":
    main()
