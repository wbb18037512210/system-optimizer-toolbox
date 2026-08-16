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

# BleachBit 6.0.2 中适用于 Windows 的文件/目录清理项（共 ~147 项，从
# `D:\360极速浏览器X下载\bleachbit-6.0.2.zip` 的 CleanerML 配置派生，
# 仅抽取 command=delete/shred 的文件动作；注册表/SQLite/ini 等非文件动作
# 与本框架不兼容已省略。BleachBit 原始版权 (C) 2008-2025 Andrew Ziem,
# GPL-3.0-or-later。原始配置在本程序同目录 bleachbit_cleaners.py。）
try:
    from bleachbit_cleaners import BLEACHBIT_CLEAN_ITEMS
    CLEAN_ITEMS.extend(BLEACHBIT_CLEAN_ITEMS)
except Exception as _bb_err:
    BLEACHBIT_CLEAN_ITEMS = []
    print("[bleachbit] 加载失败，已跳过：", _bb_err)

# LightC 2.15.0 清理能力派生：垃圾清理 / 社交软件缓存 / AI 模型缓存。
# 原始版权归 LightC 项目所有（Rust + Tauri）。文件型清理目标转换为原生
# CLEAN_ITEMS，派生自 light-c-2.15.0.zip 的扫描器源码。注册表/动态探测类
# 清理（注册表冗余、右键菜单、外壳图标、系统瘦身、旧驱动）超出本框架模型，已省略。
# 原始配置在本程序同目录 lightc_cleaners.py。
try:
    from lightc_cleaners import LIGHTC_CLEAN_ITEMS
    CLEAN_ITEMS.extend(LIGHTC_CLEAN_ITEMS)
except Exception as _lc_err:
    LIGHTC_CLEAN_ITEMS = []
    print("[lightc] 加载失败，已跳过：", _lc_err)

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


# ---- 清理安全模式（v5.0 回收站安全网）：recycle 回收站（默认）/ force 直删 / dry-run 模拟 ----
CLEAN_MODE = "recycle"


def _rm_recycle(path):
    """用 SHFileOperationW 将文件/目录移入回收站（可还原）。成功返回 True。"""
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FO_DELETE = 0x0003
        FOF_ALLOWUNDO = 0x0040        # 允许撤销 = 移入回收站
        FOF_NOCONFIRMATION = 0x0010   # 不弹确认框
        FOF_SILENT = 0x0004           # 不显示进度
        FOF_NOERRORUI = 0x0400        # 不弹错误 UI

        p_from = ctypes.create_unicode_buffer(path + "\x00", len(path) + 2)  # 双 null 结尾
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = p_from
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    except Exception:
        return False


def _safe_delete(path):
    """按全局清理模式删除路径。
    recycle：优先移入回收站，失败回退直删；dry-run：不删（仅模拟）；force：直接删除。"""
    mode = CLEAN_MODE
    if mode == "dry-run":
        return False
    if mode == "recycle":
        try:
            if _rm_recycle(path):
                return True
        except Exception:
            pass
    _rm_path(path)
    return True


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
                        _safe_delete(entry.path)
                    else:
                        freed += entry.stat().st_size
                        removed += 1
                        _safe_delete(entry.path)
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
                            _safe_delete(p)
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
                        _safe_delete(p)
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

# ---- 主题调色板：浅色 / 深色（v4.0 主题系统）----
# ================= 主题调色板 v7.0 =================
# 设计语言：「温暖编辑派现代主义 + 单一森林绿主色」
# 灵感：Linear / Notion / Things 这类高质感生产力工具
# 原则：
#   - 暖白纸感底 (#F8F6F2)，告别冰冷的 #f5f7fb
#   - 单一主色：深森林绿 (#1F6F4A)，契合"清理/优化/成长"的产品语义
#   - 副色（仅用于数据/统计）：冷湖蓝 (#0B6FA9)，与主色形成"安全 vs 信息"的对照
#   - 警示/危险色保持饱和度，但降亮度，避免刺眼
THEME_LIGHT = {
    "name": "浅色",
    # 表面层
    "bg":         "#F8F6F2",   # 整窗底色：暖白纸感
    "card":       "#FFFFFF",   # 卡片底：纯白，与 bg 形成层叠
    "card_hover": "#FAF8F3",   # 卡片 hover：暖白微底纹
    "border":     "#E8E4DD",   # 边框：暖灰（不是冷灰 #e3e8f1）
    "border_strong": "#D6D1C7",# 强调边框（用于激活态）
    # 文字
    "text":       "#1C1917",   # 主文字：暖近黑（不是 #1f2937 那种冷蓝黑）
    "text2":      "#78716C",   # 次文字：暖灰（不是冷灰 #64748b）
    "text3":      "#A8A29E",   # 三级文字（用于 hint/分隔符）
    # 主色：森林绿
    "accent":     "#1F6F4A",   # 主操作色（按钮、文字重点）
    "accent_h":   "#164D34",   # hover
    "accent_p":   "#0F3826",   # pressed
    "accent_t":   "#E8F1EC",   # 15% 透明淡绿（用于 chip 背景）
    # 副色：冷湖蓝（仅数据）
    "accent2":    "#0B6FA9",
    "accent2_t":  "#E4EFF7",
    # 语义色
    "warn":       "#B45309",   # 琥珀
    "warn_t":     "#FEF3E6",
    "danger":     "#B91C1C",   # 警示红（降饱和）
    "danger_h":   "#991B1B",
    "danger_t":   "#FEF2F2",
    # 工具类色
    "header":     "#FBF8F3",   # 表头底（暖白）
    "header_fg":  "#44403C",   # 表头字（暖深棕）
    "btn_active": "#E8F1EC",   # 按钮 hover（淡绿）
    "btn_pressed":"#D4E7DC",   # 按钮 pressed
    # 日志面板
    "log_bg":     "#1C1917",
    "log_fg":     "#E7E5E0",
    "log_border": "#292524",
    # Treeview
    "tree_checked":    "#E8F1EC",
    "tree_checked_fg": "#14532D",
    "tree_sel":        "#E0EAE4",
    "tree_sel_fg":     "#0F3826",
    "card_sub":   "#E8E4DD",
    "gauge_track":"#EFEAE0",   # 仪表轨底色
    # 标签色（v6 "卸载预装" 等高危按钮）
    "opt_fg":     "#7C2D12",
    "opt_bg":     "#FEF3E6",
    "opt_border": "#F5C4A1",
    "opt_active": "#FCE8D5",
}

THEME_DARK = {
    "name": "深色",
    "bg":         "#0F1115",   # 深近黑，带细微暖意
    "card":       "#18181B",   # 卡片：深炭灰
    "card_hover": "#1F1F23",
    "border":     "#2D2A26",
    "border_strong":"#3F3B36",
    "text":       "#FAFAF9",
    "text2":      "#A8A29E",
    "text3":      "#78716C",
    "accent":     "#4ADE80",   # 深色版主色：明翠绿（高亮但在黑底不刺眼）
    "accent_h":   "#86EFAC",
    "accent_p":   "#BBF7D0",
    "accent_t":   "#14532D",
    "accent2":    "#38BDF8",
    "accent2_t":  "#0C4A6E",
    "warn":       "#FBBF24",
    "warn_t":     "#451A03",
    "danger":     "#F87171",
    "danger_h":   "#FCA5A5",
    "danger_t":   "#450A0A",
    "header":     "#1F1F23",
    "header_fg":  "#D6D3D1",
    "btn_active": "#14532D",
    "btn_pressed":"#166534",
    "log_bg":     "#09090B",
    "log_fg":     "#D6D3D1",
    "log_border": "#27272A",
    "tree_checked":    "#14532D",
    "tree_checked_fg": "#86EFAC",
    "tree_sel":        "#1E3A4A",
    "tree_sel_fg":     "#BAE6FD",
    "card_sub":   "#D6D3D1",
    "gauge_track":"#27272A",
    "opt_fg":     "#FDBA74",
    "opt_bg":     "#1C1917",
    "opt_border": "#7C2D12",
    "opt_active": "#292524",
}

# ---- v5.0 设置中心：默认配置（持久化到 config/settings.json）----
DEFAULT_SETTINGS = {
    "theme": "light",                 # light / dark
    "clean_mode": "recycle",          # recycle 回收站 / force 直删 / dry-run 仅模拟
    "schedule": {"enabled": False, "hour": 12, "minute": 0},   # 每日定时自动清理
    "last_run": "",                   # 上次定时清理时间戳（防同日重复）
}


class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("系统优化工具箱（管理员 · 全盘）")
        self.root.geometry("1280x820")
        self.root.minsize(960, 640)
        self.root.resizable(True, True)
        _apply_app_icon(self.root)

        self.item_vars = {}
        self.item_size = {}
        self.item_count = {}
        self.cleaning = False
        self._scanning = False

        # ---- v4.0 状态：主题 / 健康分 / 监控 / 智能清理 ----
        self.theme_name = "light"
        self.T = THEME_LIGHT
        self.health_score = 0
        self.health_level = "未评估"
        self._gauge_cur = 0
        self._last_clean_bonus = 0
        self._auto_clean_pending = False
        self._mon_after = None
        self._mon_samples = []
        self._logo_ref = None
        self.settings = dict(DEFAULT_SETTINGS)
        self._sched_tick = None

        # v5.0：先加载设置（主题/清理模式/计划任务），再构建界面
        self._apply_settings()
        self._setup_styles()
        self._build_ui()
        self._refresh_admin_badge()
        self._update_status_bar()

    # ---- 统一 Style：从当前主题调色板读取（v4.0 支持浅/深色切换）----
    def _setup_styles(self):
        from tkinter import font as tkfont
        T = self.T
        COLOR_BG       = T["bg"]          # 整窗底色
        COLOR_CARD     = T["card"]        # 卡片底
        COLOR_BORDER   = T["border"]      # 卡片边框
        COLOR_TEXT     = T["text"]        # 主文字
        COLOR_TEXT2    = T["text2"]       # 次级文字
        COLOR_ACCENT   = T["accent"]      # 主色（操作按钮）
        COLOR_ACCENT2  = T["accent2"]     # 副色（统计/勾选）
        COLOR_WARN     = T["warn"]        # 警示橙
        COLOR_DANGER   = T["danger"]      # 危险红
        COLOR_HEADER   = T["header"]      # 表头底

        self.root.configure(bg=COLOR_BG)
        # ---- 全局字体体系 v7.0 ----
        # 中文 UI 用 Microsoft YaHei UI；标题用更醒目的字体；数字用 Consolas 等宽
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Microsoft YaHei UI", size=9)
            tkfont.nametofont("TkTextFont").configure(family="Microsoft YaHei UI", size=9)
        except Exception:
            pass

        # 注册自定义字体角色
        self.FONT_DISPLAY = ("Microsoft YaHei UI", 18, "bold")     # 顶栏主标题（粗壮、对照感强）
        self.FONT_SUB = ("Microsoft YaHei UI", 9)                    # 副标题
        self.FONT_SECTION = ("Microsoft YaHei UI", 10.5, "bold")    # 分组标题
        self.FONT_BODY = ("Microsoft YaHei UI", 9.5)                # 正文
        self.FONT_LABEL = ("Microsoft YaHei UI", 9)                 # 标签
        self.FONT_BTN = ("Microsoft YaHei UI", 9.5)                 # 按钮
        self.FONT_BTN_S = ("Microsoft YaHei UI", 9)                  # 按钮（小）
        self.FONT_STAT_NUM = ("Consolas", 11, "bold")                # 数据数字（等宽）
        self.FONT_STAT_LABEL = ("Microsoft YaHei UI", 8.5)           # 数据标签
        self.FONT_TAG = ("Microsoft YaHei UI", 8, "bold")            # 角落 tag
        self.FONT_TREE = ("Microsoft YaHei UI", 9)                   # 树
        self.FONT_LOG = ("Consolas", 9)                              # 日志

        ts = ttk.Style()
        try:
            ts.theme_use("vista")
        except Exception:
            pass

        ts.configure(".", background=COLOR_BG, foreground=COLOR_TEXT)
        ts.configure("TFrame", background=COLOR_BG)
        ts.configure("Card.TFrame", background=COLOR_CARD)
        ts.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT,
                     font=self.FONT_BODY)
        ts.configure("Card.TLabelframe", background=COLOR_CARD, bordercolor=T["border"],
                     lightcolor=T["border"], darkcolor=T["border"], relief="solid", borderwidth=1)
        ts.configure("Card.TLabelframe.Label", background=COLOR_CARD, foreground=T["text"],
                     font=self.FONT_SECTION, padding=(2, 0))

        # 普通按钮：白底浅边框 + hover/pressed
        ts.configure("TButton",
                     font=("Microsoft YaHei UI", 9),
                     padding=(12, 6),
                     foreground=COLOR_TEXT,
                     background=COLOR_CARD,
                     bordercolor=COLOR_BORDER,
                     lightcolor=COLOR_CARD, darkcolor=COLOR_BORDER)
        ts.map("TButton",
               background=[("active", T["btn_active"]), ("pressed", T["btn_pressed"]), ("disabled", COLOR_HEADER)],
               foreground=[("disabled", T["text2"])])

        # 强调绿色按钮（扫描 / 统计 / 管理员）
        ts.configure("Primary.TButton",
                     font=self.FONT_BTN_S,
                     padding=(16, 8),
                     foreground="#ffffff",
                     background=COLOR_ACCENT,
                     bordercolor=COLOR_ACCENT,
                     lightcolor=COLOR_ACCENT, darkcolor=COLOR_ACCENT)
        ts.map("Primary.TButton",
               background=[("active", T["accent_h"]), ("pressed", T["accent_p"]), ("disabled", "#A8D5BF")],
               foreground=[("disabled", "#f1f5f9")])

        # 危险红（开始清理）
        ts.configure("Action.TButton",
                     font=self.FONT_BTN_S,
                     padding=(16, 8),
                     foreground="#ffffff",
                     background=COLOR_DANGER,
                     bordercolor=COLOR_DANGER,
                     lightcolor=COLOR_DANGER, darkcolor=COLOR_DANGER)
        ts.map("Action.TButton",
               background=[("active", T["danger_h"]), ("pressed", "#7F1D1D"), ("disabled", "#FCA5A5")],
               foreground=[("disabled", "#f1f5f9")])

        # 智能一键（冷湖蓝，强调"信息/分析"）
        ts.configure("Smart.TButton",
                     font=self.FONT_BTN_S,
                     padding=(16, 8),
                     foreground="#ffffff",
                     background=COLOR_ACCENT2,
                     bordercolor=COLOR_ACCENT2,
                     lightcolor=COLOR_ACCENT2, darkcolor=COLOR_ACCENT2)
        ts.map("Smart.TButton",
               background=[("active", "#0C5A8A"), ("pressed", "#063E5E"), ("disabled", "#93C5DE")],
               foreground=[("disabled", "#f1f5f9")])

        # 一键优化橙色（高密度按钮）
        ts.configure("Opt.TButton",
                     font=self.FONT_BTN_S,
                     padding=(12, 6),
                     foreground=T["opt_fg"],
                     background=T["opt_bg"],
                     bordercolor=T["opt_border"],
                     lightcolor=T["opt_bg"], darkcolor=T["opt_border"])
        ts.map("Opt.TButton",
               background=[("active", T["opt_active"]), ("pressed", T["opt_border"])],
               foreground=[("active", COLOR_WARN)])

        # 次级按钮（用于清理面板内的"全选/全不选/低风险"）
        ts.configure("Secondary.TButton",
                     font=self.FONT_BTN_S,
                     padding=(12, 6),
                     foreground=COLOR_TEXT,
                     background=T["card"],
                     bordercolor=T["border"],
                     lightcolor=T["card"], darkcolor=T["border"])
        ts.map("Secondary.TButton",
               background=[("active", T["accent_t"]), ("pressed", T["btn_pressed"])],
               foreground=[("active", COLOR_ACCENT)],
               bordercolor=[("active", T["border_strong"])])

        # 顶栏标签
        ts.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"),
                     background=COLOR_BG, foreground=COLOR_TEXT)
        ts.configure("Sub.TLabel",   font=("Microsoft YaHei UI", 9),
                     background=COLOR_BG, foreground=COLOR_TEXT2)
        ts.configure("Badge.TLabel", font=("Microsoft YaHei UI", 9, "bold"),
                     background=COLOR_ACCENT2, foreground="#ffffff", padding=(6, 2))
        ts.configure("Badge2.TLabel", font=("Microsoft YaHei UI", 9, "bold"),
                     background=COLOR_WARN, foreground="#ffffff", padding=(6, 2))

        # Treeview 表格美化：行高、表头配色、选中柔和绿
        ts.configure("Cleanup.Treeview",
                     font=("Microsoft YaHei UI", 9),
                     rowheight=26,
                     background=COLOR_CARD,
                     fieldbackground=COLOR_CARD,
                     foreground=COLOR_TEXT,
                     bordercolor=COLOR_BORDER,
                     lightcolor=COLOR_CARD, darkcolor=COLOR_CARD)
        ts.configure("Cleanup.Treeview.Heading",
                     font=("Microsoft YaHei UI", 9, "bold"),
                     background=COLOR_HEADER,
                     foreground=T["header_fg"],
                     bordercolor=COLOR_BORDER,
                     lightcolor=COLOR_HEADER, darkcolor=COLOR_HEADER,
                     padding=(8, 6))
        ts.map("Cleanup.Treeview",
               background=[("selected", T["tree_sel"])],
               foreground=[("selected", T["tree_sel_fg"])])

        # 颜色常量挂到 self 上，方便日志框/_build_ui 其它处复用
        self.COLOR_BG = COLOR_BG
        self.COLOR_CARD = COLOR_CARD
        self.COLOR_BORDER = COLOR_BORDER
        self.COLOR_TEXT = COLOR_TEXT
        self.COLOR_TEXT2 = COLOR_TEXT2
        self.COLOR_ACCENT = COLOR_ACCENT
        self.COLOR_ACCENT2 = COLOR_ACCENT2
        self.COLOR_WARN = COLOR_WARN
        self.COLOR_DANGER = COLOR_DANGER

    # ================= v4.0 智能版：主题切换 =================
    def _apply_theme(self):
        """浅色/深色主题一键切换：整窗重建（保留扫描结果与健康分）。"""
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.T = THEME_DARK if self.theme_name == "dark" else THEME_LIGHT
        try:
            if self._mon_after:
                self.root.after_cancel(self._mon_after)
                self._mon_after = None
        except Exception:
            pass
        for w in self.root.winfo_children():
            w.destroy()
        self._setup_styles()
        self._build_ui()
        self._refresh_admin_badge()
        self._update_stat()
        if self.health_score:
            self._update_health(animate=False)
        self._update_status_bar()
        self._log(f"已切换至「{self.T['name']}」主题", "ok")

    # ================= v6.0 已废弃旧版仪表盘占位（旧 _build_left_column 调用链已移除） =================
    def _build_left_column(self, parent):
        # v6.0 改为单窗口布局，不再分左右栏。本方法仅为兼容旧逻辑保留空壳。
        pass

    # ---- 健康分仪表盘（Canvas 大圆环 + 动效）----
    def _build_health_widget(self, parent):
        box = tk.Frame(parent, bg=self.COLOR_CARD,
                       highlightthickness=1, highlightbackground=self.COLOR_BORDER, bd=0)
        box.pack(fill="x", padx=6, pady=(6, 6))
        inner = tk.Frame(box, bg=self.COLOR_CARD)
        inner.pack(fill="x", padx=12, pady=8)
        self.health_cv = tk.Canvas(inner, width=84, height=84, bg=self.COLOR_CARD,
                                   highlightthickness=0, bd=0)
        self.health_cv.pack(side="left")
        info = tk.Frame(inner, bg=self.COLOR_CARD)
        info.pack(side="left", padx=(12, 0), fill="both", expand=True)
        self.health_val = tk.Label(info, text="健康分 --", font=("Microsoft YaHei UI", 16, "bold"),
                                   bg=self.COLOR_CARD, fg=self.COLOR_TEXT)
        self.health_val.pack(anchor="w")
        self.health_lvl = tk.Label(info, text="扫描后自动评估系统状态", font=("Microsoft YaHei UI", 9),
                                   bg=self.COLOR_CARD, fg=self.COLOR_TEXT2)
        self.health_lvl.pack(anchor="w", pady=(4, 0))
        tk.Label(info, text="垃圾越少 · 健康分越高", font=("Microsoft YaHei UI", 8),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT2).pack(anchor="w", pady=(2, 0))
        self._gauge_color = "#10b981"
        self._health_draw(0)

    def _health_draw(self, score):
        try:
            cv = self.health_cv
            cv.delete("all")
            W = H = 84
            cx, cy, R = W / 2, H / 2, 32
            start, span = 135, -270
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=span,
                          style="arc", outline=self.T["gauge_track"], width=7)
            col = getattr(self, "_gauge_color", "#10b981")
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start,
                          extent=span * max(0, min(100, score)) / 100.0,
                          style="arc", outline=col, width=7)
            cv.create_text(cx, cy - 4, text=str(score), font=("Microsoft YaHei UI", 16, "bold"),
                           fill=self.COLOR_TEXT)
            cv.create_text(cx, cy + 16, text="健康分", font=("Microsoft YaHei UI", 8),
                           fill=self.COLOR_TEXT2)
        except Exception:
            pass

    def _animate_gauge(self, target):
        cur = getattr(self, "_gauge_cur", 0)

        def step(i):
            self._gauge_cur = cur + (target - cur) * i / 18.0
            self._health_draw(int(round(self._gauge_cur)))
            if i < 18:
                self.root.after(16, step, i + 1)

        self.root.after(10, step, 0)

    def _compute_health(self):
        junk = sum(self.item_size[i["id"]] for i in CLEAN_ITEMS)
        gb = junk / (1024.0 ** 3)
        score = 100.0
        score -= min(40.0, gb * 4)                                   # 垃圾占用
        high = sum(1 for i in CLEAN_ITEMS
                   if i.get("risk") == "高" and self.item_vars[i["id"]].get())
        score -= min(20.0, high * 3)                                 # 勾选高风险
        if not is_admin():
            score -= 8                                               # 权限不足
        score += self._last_clean_bonus                              # 清理加成
        return max(20, min(100, int(round(score))))

    def _update_health(self, animate=True):
        score = self._compute_health()
        self.health_score = score
        if score >= 85:
            lvl, tip, col = "极佳", "系统非常干净", "#10b981"
        elif score >= 70:
            lvl, tip, col = "良好", "有少量可清理项", "#0ea5e9"
        elif score >= 50:
            lvl, tip, col = "一般", "建议尽快清理", "#f59e0b"
        else:
            lvl, tip, col = "待优化", "垃圾占用较多", "#ef4444"
        self.health_level = lvl
        self._gauge_color = col
        try:
            self.health_val.configure(text=f"健康分 {score}", fg=col)
            self.health_lvl.configure(text=f"{lvl} · {tip}")
            if animate:
                self._animate_gauge(score)
            else:
                self._gauge_cur = score
                self._health_draw(score)
        except Exception:
            pass
        self._update_status_bar()

    # ================= v5.0 仪表盘：三环资源条 + 清理历史 =================
    def _gauge_draw(self, cv, pct, color):
        """画一个 40px 迷你圆环（用于 CPU/RAM/磁盘）。"""
        try:
            cv.delete("all")
            W = H = 40
            cx, cy, R = W / 2, H / 2, 15
            start, span = 135, -270
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=span,
                          style="arc", outline=self.T["gauge_track"], width=5)
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start,
                          extent=span * max(0.0, min(100.0, pct)) / 100.0,
                          style="arc", outline=color, width=5)
            cv.create_text(cx, cy, text=f"{pct:.0f}", font=("Consolas", 9, "bold"),
                           fill=self.COLOR_TEXT)
        except Exception:
            pass

    def _gauge_update(self):
        """刷新 CPU / RAM / 磁盘三环。"""
        try:
            cpu = self._mon_samples[-1][0] if self._mon_samples else 0.0
            ram = _ram_percent()
            disk = _disk_usage_pct()
            self._gauge_draw(self._gauge_cvs["cpu"], cpu, self.COLOR_ACCENT)
            self._gauge_draw(self._gauge_cvs["ram"], ram, self.COLOR_ACCENT2)
            self._gauge_draw(self._gauge_cvs["disk"], disk, self.COLOR_WARN)
            self._gauge_lbls["cpu"].configure(text=f"CPU {cpu:.0f}%")
            self._gauge_lbls["ram"].configure(text=f"内存 {ram:.0f}%")
            self._gauge_lbls["disk"].configure(text=f"磁盘 {disk:.0f}%")
        except Exception:
            pass

    def _hist_draw(self):
        """近 10 次清理迷你柱状图（数据来自 stats/history.json）。"""
        try:
            cv = self.hist_cv
            cv.delete("all")
            w = cv.winfo_width()
            if w <= 1:
                w = 380
            h = 46
            recent = self._load_stats()[-10:]
            if not recent:
                cv.create_text(w / 2, h / 2, text="暂无清理记录", fill=self.COLOR_TEXT2,
                               font=("Microsoft YaHei UI", 8))
                return
            mx = max(max(s.get("freed_mb", 0) for s in recent), 1)
            n = len(recent)
            bw = max(6, min(22, (w - 16) / n - 4))
            gap = 4
            x0 = (w - n * (bw + gap)) / 2 + gap / 2
            for i, s in enumerate(recent):
                bh = max(3, (h - 14) * s.get("freed_mb", 0) / mx)
                x = x0 + i * (bw + gap)
                cv.create_rectangle(x, h - 6 - bh, x + bw, h - 6,
                                    fill=self.COLOR_ACCENT, outline="")
            cv.create_text(w / 2, 8, text="📊 近 10 次清理（MB）", fill=self.COLOR_TEXT2,
                           font=("Microsoft YaHei UI", 8))
        except Exception:
            pass

    # ================= v6.0 经典智能版：UI 构建（经 v3 验证的 grid 布局，告别 PanedWindow） =================
    def _build_ui(self):
        # ---- 1. 顶栏（品牌区 + 操作区）----
        top = tk.Frame(self.root, bg=self.COLOR_BG)
        top.pack(fill="x", padx=16, pady=(14, 10))

        # 品牌区（左）
        brand = tk.Frame(top, bg=self.COLOR_BG)
        brand.pack(side="left")
        logo_box = tk.Frame(brand, bg=self.COLOR_BG)
        logo_box.pack(side="left")
        self._brand_logo_cv = tk.Canvas(logo_box, width=34, height=34, bg=self.COLOR_BG,
                                        highlightthickness=0, bd=0)
        self._brand_logo_cv.pack(side="left")
        self._draw_brand_logo(self._brand_logo_cv)

        title_box = tk.Frame(brand, bg=self.COLOR_BG)
        title_box.pack(side="left", padx=(12, 0))
        title_row = tk.Frame(title_box, bg=self.COLOR_BG)
        title_row.pack(anchor="w")
        tk.Label(title_row, text="系统优化工具箱",
                 font=self.FONT_DISPLAY,
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(side="left")
        self.version_tag = tk.Label(title_row, text="  v7.0  ",
                                    font=self.FONT_TAG,
                                    bg=self.COLOR_ACCENT, fg="#FFFFFF",
                                    padx=2, pady=1)
        self.version_tag.pack(side="left", padx=(10, 0))
        tk.Label(title_box,
                 text="轻巧专注的 Windows 维护套件 · 森林绿主题",
                 font=self.FONT_SUB,
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT2).pack(anchor="w", pady=(2, 0))

        # 操作区（右）
        right = tk.Frame(top, bg=self.COLOR_BG)
        right.pack(side="right")
        self.admin_badge = tk.Label(right, text="  ",
                                    font=self.FONT_BTN_S,
                                    bg=self.COLOR_ACCENT, fg="#FFFFFF",
                                    padx=10, pady=3)
        self.admin_badge.pack(side="right", anchor="e")

        self.theme_btn = tk.Label(right, text="深色模式",
                                  font=self.FONT_BTN_S,
                                  bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                                  padx=12, pady=4, cursor="hand2",
                                  highlightthickness=1, highlightbackground=self.COLOR_BORDER)
        self.theme_btn.pack(side="right", anchor="e", padx=(8, 0))
        self.theme_btn.bind("<Button-1>", lambda e: self._apply_theme())

        def _short(icon, command):
            b = tk.Label(right, text=icon, font=("Segoe UI Emoji", 14),
                         bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                         cursor="hand2", padx=4, pady=3,
                         highlightthickness=1, highlightbackground=self.COLOR_BORDER)
            b.pack(side="right", anchor="e", padx=(8, 0))
            b.bind("<Button-1>", lambda e: command())

            def on_enter(e):
                b.configure(bg=self.T["accent_t"], fg=self.COLOR_ACCENT,
                            highlightbackground=self.T["border_strong"])
            def on_leave(e):
                b.configure(bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                            highlightbackground=self.COLOR_BORDER)
            b.bind("<Enter>", on_enter)
            b.bind("<Leave>", on_leave)
        _short("⚙", self.open_settings)
        _short("💽", self.open_diskmap)

        # ---- 2. 紧凑状态条 ----
        self._build_compact_dashboard()

        # ---- 3. 主分割：v5.0 验证过的 grid + minsize=440 方案 ----
        main = tk.Frame(self.root, bg=self.COLOR_BG)
        main.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        main.grid_columnconfigure(0, minsize=440)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        left_outer = tk.Frame(main, bg=self.COLOR_CARD,
                              highlightthickness=1, highlightbackground=self.COLOR_BORDER)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self._build_tools_panel(left_outer)

        right_outer = tk.Frame(main, bg=self.COLOR_BG)
        right_outer.grid(row=0, column=1, sticky="nsew", pady=0)
        right_outer.grid_columnconfigure(0, weight=1)
        right_outer.grid_rowconfigure(0, weight=1)
        right_outer.grid_rowconfigure(1, weight=0)
        self._build_cleanup_panel(right_outer)
        self._build_log_into(right_outer)

        # ---- 4. 底部状态栏 ----
        self._build_status_bar()

        # ---- 5. 启动监控定时器 ----
        self._mon_after = None
        self._mon_tick()

    # ---- v7.0 品牌 LOGO 自绘（Canvas 几何）----
    def _draw_brand_logo(self, cv):
        """森林绿圆角方形底 + 白色 W + 右上角光点。"""
        cv.delete("all")
        w = cv.winfo_width() or 34
        h = cv.winfo_height() or 34
        cv.create_rectangle(2, 2, w - 2, h - 2, fill=self.COLOR_ACCENT, outline="", width=0)
        cx, cy = w / 2, h / 2
        cv.create_polygon(
            cx - 9, cy - 7, cx - 6, cy + 8, cx - 3, cy - 2,
            cx,      cy + 8, cx + 3, cy - 2,
            cx + 6,  cy + 8, cx + 9, cy - 7,
            fill="#FFFFFF", outline="", width=0, smooth=True,
        )
        cv.create_oval(w - 9, 4, w - 5, 8, fill=self.COLOR_ACCENT2, outline="")

    # ================= v7.0 紧凑状态条：4 个 stat chip + 操作区 =================
    def _build_compact_dashboard(self):
        """设计：4 个 stat chip（健康/CPU/内存/磁盘）| 摘要文本 | 3 个快捷操作。
        每个 chip 是一个垂直堆叠的小卡片：大号数字 + 小号标签，用细线分隔。
        """
        # 强制显式高度 + 锁住传播
        strip = tk.Frame(self.root, bg=self.COLOR_CARD,
                         highlightthickness=1, highlightbackground=self.COLOR_BORDER, bd=0,
                         height=88)
        strip.pack(fill="x", padx=16, pady=(0, 8))
        strip.pack_propagate(False)
        inner = tk.Frame(strip, bg=self.COLOR_CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        # ---- 左：健康分环 ----
        health_chip = tk.Frame(inner, bg=self.COLOR_CARD)
        health_chip.pack(side="left")
        self.health_cv = tk.Canvas(health_chip, width=48, height=48, bg=self.COLOR_CARD,
                                   highlightthickness=0, bd=0)
        self.health_cv.pack(side="left")
        self._gauge_color = self.COLOR_ACCENT
        self._health_draw(0)
        health_text = tk.Frame(health_chip, bg=self.COLOR_CARD)
        health_text.pack(side="left", padx=(8, 0))
        self.health_val = tk.Label(health_text, text="健康分 --",
                                   font=self.FONT_STAT_NUM,
                                   bg=self.COLOR_CARD, fg=self.COLOR_TEXT)
        self.health_val.pack(anchor="w")
        self.health_lvl = tk.Label(health_text, text="未评估",
                                   font=self.FONT_STAT_LABEL,
                                   bg=self.COLOR_CARD, fg=self.COLOR_TEXT2)
        self.health_lvl.pack(anchor="w")

        # ---- 分隔线 ----
        sep1 = tk.Frame(inner, bg=self.COLOR_BORDER, width=1)
        sep1.pack(side="left", fill="y", padx=18)

        # ---- CPU / 内存 / 磁盘 三 chip ----
        self._gauge_cvs = {}
        self._gauge_lbls = {}
        for key, color, label, unit in (
                ("cpu",  self.COLOR_ACCENT,  "CPU",  "%"),
                ("ram",  self.COLOR_ACCENT2, "内存", "%"),
                ("disk", self.COLOR_WARN,     "磁盘", "%"),
        ):
            chip = tk.Frame(inner, bg=self.COLOR_CARD)
            chip.pack(side="left", padx=(0, 14))
            # 小环
            cv = tk.Canvas(chip, width=40, height=40, bg=self.COLOR_CARD,
                           highlightthickness=0, bd=0)
            cv.pack(side="top", anchor="w")
            # 数值 + 标签（水平堆叠，节省垂直空间）
            num_lbl = tk.Label(chip, text="--%",
                               font=self.FONT_STAT_NUM,
                               bg=self.COLOR_CARD, fg=self.COLOR_TEXT)
            num_lbl.pack(side="top", anchor="w")
            sub_lbl = tk.Label(chip, text=label,
                               font=self.FONT_STAT_LABEL,
                               bg=self.COLOR_CARD, fg=self.COLOR_TEXT2)
            sub_lbl.pack(side="top", anchor="w")
            self._gauge_cvs[key] = cv
            self._gauge_lbls[key] = num_lbl
            self._gauge_draw(cv, 0, color)

        # ---- 分隔线 2 ----
        sep2 = tk.Frame(inner, bg=self.COLOR_BORDER, width=1)
        sep2.pack(side="left", fill="y", padx=18)

        # ---- 摘要文本 ----
        self.summary_lbl = tk.Label(inner, text="就绪",
                                    font=self.FONT_BODY,
                                    bg=self.COLOR_CARD, fg=self.COLOR_TEXT2)
        self.summary_lbl.pack(side="left", padx=(0, 8))

        # ---- 右：快捷操作 ----
        actions = tk.Frame(inner, bg=self.COLOR_CARD)
        actions.pack(side="right")
        ttk.Button(actions, text="✨ 智能一键", command=self._smart_clean,
                   style="Smart.TButton").pack(side="left", padx=2)
        ttk.Button(actions, text="扫描占用", command=self._scan,
                   style="Primary.TButton").pack(side="left", padx=2)
        ttk.Button(actions, text="开始清理", command=self._ask_clean,
                   style="Action.TButton").pack(side="left", padx=2)

    def _update_summary(self):
        try:
            sessions = self._load_stats()
            total_mb = sum(s.get("freed_mb", 0) for s in sessions)
            perm = "管理员" if is_admin() else "普通权限"
            self.summary_lbl.configure(
                text=f"累计释放 {human_size(int(total_mb * 1048576))} ｜ "
                     f"清理 {len(sessions)} 次 ｜ 权限：{perm}")
        except Exception:
            pass

    # ================= v6.0 工具面板（左侧滚动区） =================
    def _make_icon_button(self, parent, kind, text, command):
        """v7.0 精炼版：19px Canvas 自绘图标 + 中文标签 + 圆角感 + accent hover。
        视觉处理：
          - 边框 1px，使用 border / border_strong 二级对比
          - hover：bg → accent_t（淡绿），icon 中心填色高亮，文字 → accent
          - 按下：bg → accent_p 半透明（pressed 用 btn_pressed）
        """
        bg = self.COLOR_CARD
        bg_hov = self.T["accent_t"]
        bg_pressed = self.T["btn_pressed"]
        border = self.COLOR_BORDER
        border_hov = self.T["border_strong"]
        accent = self.COLOR_ACCENT

        f = tk.Frame(parent, bg=bg, cursor="hand2",
                     highlightthickness=1, highlightbackground=border)
        f.bind("<Button-1>", lambda e: command())
        inner = tk.Frame(f, bg=bg)
        inner.pack(padx=10, pady=5, fill="x")
        cv = tk.Canvas(inner, width=19, height=19, bg=bg, highlightthickness=0, bd=0)
        cv.pack(side="left")
        # 默认 icon 用 accent 色（视觉锚点）
        self._draw_card_icon(cv, kind, 10, 10, s=14, bg_cut=bg, color=accent)
        lbl = tk.Label(inner, text=text, bg=bg, fg=self.COLOR_TEXT,
                       font=self.FONT_BTN)
        lbl.pack(side="left", padx=(8, 0))
        lbl.bind("<Button-1>", lambda e: command())

        widgets = (f, inner, cv, lbl)

        def _restyle(bg_, border_, fg_, ic_color):
            for w in (f, inner, cv, lbl):
                try:
                    if w is f:
                        w.configure(bg=bg_, highlightbackground=border_)
                    elif w is cv:
                        w.configure(bg=bg_)
                    else:
                        w.configure(bg=bg_)
                except Exception:
                    pass
            try:
                lbl.configure(fg=fg_)
            except Exception:
                pass
            # 重绘 icon（用 active 色）
            try:
                self._draw_card_icon(cv, kind, 10, 10, s=14, bg_cut=bg_, color=ic_color)
            except Exception:
                pass

        def on_enter(e):
            _restyle(bg_hov, border_hov, accent, accent)

        def on_leave(e):
            _restyle(bg, border, self.COLOR_TEXT, accent)

        def on_press(e):
            _restyle(bg_pressed, border_hov, accent, accent)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<ButtonPress-1>", on_press)
            w.bind("<ButtonRelease-1>",
                   lambda e: (_restyle(bg_hov, border_hov, accent, accent), command()))
        return f

    def _build_tools_panel(self, parent):
        """左侧工具面板：3 个分组 + 自绘渐变条 + 2 列网格按钮。
        v7.0 设计：
          - 分组容器用 tk.LabelFrame + 色卡边框
          - 每个分组标题左侧一道森林绿渐变竖条（视觉锚点）
          - 按钮之间预留呼吸空间
        """
        def _section(title, hint=None):
            """构造一个分组：LabelFrame + 渐变竖条 + 标题 + 可选提示。"""
            sec = tk.LabelFrame(parent, text="",
                                bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                                padx=10, pady=8, bd=0,
                                highlightthickness=1,
                                highlightbackground=self.COLOR_BORDER)
            sec.pack(fill="x", pady=(0, 10), padx=4)
            # 标题栏（左侧渐变竖条 + 标题文字 + 可选提示）
            head = tk.Frame(sec, bg=self.COLOR_CARD)
            head.pack(fill="x", pady=(0, 8))
            # 左侧森林绿竖条
            stripe = tk.Frame(head, bg=self.COLOR_ACCENT, width=4, height=14)
            stripe.pack(side="left", padx=(0, 8))
            stripe.pack_propagate(False)
            tk.Label(head, text=title,
                     bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                     font=self.FONT_SECTION).pack(side="left")
            if hint:
                tk.Label(head, text="  " + hint,
                         bg=self.COLOR_CARD, fg=self.COLOR_TEXT3,
                         font=("Microsoft YaHei UI", 8.5)).pack(side="left")
            return sec

        def _grid(sec):
            g = tk.Frame(sec, bg=self.COLOR_CARD)
            g.pack(fill="x")
            for c in range(2):
                g.columnconfigure(c, weight=1)
            return g

        # ===== 系统快捷工具 =====
        sec1 = _section("系统快捷工具", "9 项 · Windows 自带")
        grid1 = _grid(sec1)
        sys_tools = [
            ("monitor",   "控制面板",       lambda: self._open_target("control.exe")),
            ("rocket",    "任务管理器",     lambda: self._open_target("taskmgr.exe")),
            ("box",       "卸载程序",       lambda: self._open_target("appwiz.cpl")),
            ("broom",     "磁盘清理",       lambda: self._open_target("cleanmgr.exe")),
            ("shield",    "系统信息",       lambda: self._open_target("ms-settings:about")),
            ("gear",      "设备管理器",     lambda: self._open_target("devmgmt.msc")),
            ("globe",     "磁盘管理",       lambda: self._open_target("diskmgmt.msc")),
            ("monitor",   "服务",           lambda: self._open_target("services.msc")),
            ("box",       "上帝模式",       self.open_godmode),
        ]
        for i, (kind, text, cmd) in enumerate(sys_tools):
            r, c = i // 2, i % 2
            self._make_icon_button(grid1, kind, text, cmd).grid(
                row=r, column=c, padx=2, pady=2, sticky="ew")

        # ===== 优化与卸载面板 =====
        sec2 = _section("优化与卸载面板", "4 项 · 推荐")
        grid2 = _grid(sec2)
        opt_tools = [
            ("box",     "卸载预装",     self.open_debloat),
            ("broom",   "深度优化",     self.open_deep),
            ("lightning", "Win10 优化", self.launch_win10_optimizer),
            ("globe",   "360 联网助手", self.launch_net_assist),
        ]
        for i, (kind, text, cmd) in enumerate(opt_tools):
            r, c = i // 2, i % 2
            self._make_icon_button(grid2, kind, text, cmd).grid(
                row=r, column=c, padx=2, pady=2, sticky="ew")

        # ===== 一键优化（需管理员） =====
        sec3 = _section("一键优化", "15 项 · 需管理员权限")
        warn_frame = tk.Frame(sec3, bg=self.COLOR_WARN_T,
                              highlightthickness=1,
                              highlightbackground=self.T.get("warn", "#F5C4A1"))
        warn_frame.pack(fill="x", pady=(0, 8))
        tk.Label(warn_frame,
                 text="⚠  高危操作：执行前会二次确认，全部操作可逆",
                 bg=self.COLOR_WARN_T, fg=self.COLOR_WARN,
                 font=("Microsoft YaHei UI", 8.5), padx=8, pady=4
                 ).pack(anchor="w")
        grid3 = _grid(sec3)
        for c in range(2):
            grid3.columnconfigure(c, weight=1)
        one_click = [
            ("broom",   "清理 DNS 缓存",   self.opt_dns_flush),
            ("battery", "高性能电源",     self.opt_high_perf),
            ("battery", "卓越电源",       self.opt_ultimate_perf),
            ("lightning", "快速启动",     self.opt_fastboot_on),
            ("lightning", "禁用 SysMain",  self.opt_sysmain_off),
            ("lightning", "关传递优化",    self.opt_dosvc_off),
            ("lightning", "关搜索索引",    self.opt_search_off),
            ("lightning", "关透明动画",    self.opt_visual_off),
            ("lightning", "关遥测",        self.opt_telemetry_off),
            ("lightning", "关休眠",        self.opt_hibernate_off),
            ("shield",  "关防火墙",       self.opt_firewall_off),
            ("shield",  "关 Defender",    self.opt_defender_off),
            ("shield",  "关 UAC",         self.opt_uac_off),
            ("shield",  "关系统还原",     self.opt_system_restore_off),
            ("shield",  "关 Win 更新",    self.opt_wu_off),
        ]
        for i, (kind, text, cmd) in enumerate(one_click):
            r, c = i // 2, i % 2
            self._make_icon_button(grid3, kind, text, cmd).grid(
                row=r, column=c, padx=2, pady=2, sticky="ew")

    # ================= v6.0 精简健康分大环（44px 给状态条） =================
    def _health_draw(self, score):
        try:
            cv = self.health_cv
            cv.delete("all")
            W = H = 48
            cx, cy, R = W / 2 - 1, H / 2 - 1, 17
            start, span = 135, -270
            # 轨
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=span,
                          style="arc", outline=self.T["gauge_track"], width=4)
            col = getattr(self, "_gauge_color", self.COLOR_ACCENT)
            # 进度
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start,
                          extent=span * max(0, min(100, score)) / 100.0,
                          style="arc", outline=col, width=4)
            cv.create_text(cx, cy, text=str(score),
                           font=("Consolas", 12, "bold"),
                           fill=self.COLOR_TEXT)
        except Exception:
            pass

    # ================= v6.0 实时监控（轻量化：仅刷新文本，环 3s 刷一次） =================
    def _gauge_draw(self, cv, pct, color):
        try:
            cv.delete("all")
            W = H = 36
            cx, cy, R = W / 2, H / 2, 13
            start, span = 135, -270
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=span,
                          style="arc", outline=self.T["gauge_track"], width=4)
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start,
                          extent=span * max(0.0, min(100.0, pct)) / 100.0,
                          style="arc", outline=color, width=4)
        except Exception:
            pass

    def _gauge_update(self):
        """三环轻量更新：CPU 每 2s 刷，RAM/Disk 每 3s 刷（避免无谓 IO）。"""
        try:
            cpu = self._mon_samples[-1][0] if self._mon_samples else 0.0
            self._gauge_draw(self._gauge_cvs["cpu"], cpu, self.COLOR_ACCENT)
            self._gauge_lbls["cpu"].configure(text=f"{cpu:.0f}")
            if not getattr(self, "_t", 0) % 3:
                ram = _ram_percent()
                disk = _disk_usage_pct()
                self._gauge_draw(self._gauge_cvs["ram"], ram, self.COLOR_ACCENT2)
                self._gauge_draw(self._gauge_cvs["disk"], disk, self.COLOR_WARN)
                self._gauge_lbls["ram"].configure(text=f"{ram:.0f}")
                self._gauge_lbls["disk"].configure(text=f"{disk:.0f}")
            self._t = (self._t or 0) + 1
        except Exception:
            pass

    def _mon_tick(self):
        try:
            cpu = _cpu_percent()
            ram = _ram_percent()
        except Exception:
            cpu, ram = 0.0, 0.0
        self._mon_samples.append((cpu, ram))
        if len(self._mon_samples) > 40:
            self._mon_samples.pop(0)
        try:
            self._gauge_update()
            self._update_summary()
        except Exception:
            pass
        try:
            self._mon_after = self.root.after(2000, self._mon_tick)
        except Exception:
            self._mon_after = None

    # ================= v4.0 智能版：状态栏 =================
    def _build_status_bar(self):
        """状态栏：左侧运行摘要 ｜ 右侧版本 tag。
        视觉处理：细微顶部边框线，文字采用 refined typography。"""
        bar = tk.Frame(self.root, bg=self.COLOR_BG)
        bar.pack(fill="x", padx=16, pady=(2, 10))
        # 顶部细线分隔
        sep = tk.Frame(bar, bg=self.COLOR_BORDER, height=1)
        sep.pack(fill="x", pady=(0, 6))
        # 内容区
        content = tk.Frame(bar, bg=self.COLOR_BG)
        content.pack(fill="x")
        self.status_lbl = tk.Label(content, text="就绪",
                                   font=self.FONT_LABEL,
                                   bg=self.COLOR_BG, fg=self.COLOR_TEXT2)
        self.status_lbl.pack(side="left")
        self.status_lbl2 = tk.Label(content, text="v7.0 经典智能版 · 森林绿",
                                    font=self.FONT_TAG,
                                    bg=self.COLOR_BG, fg=self.COLOR_ACCENT)
        self.status_lbl2.pack(side="right")

    def _update_status_bar(self):
        try:
            sessions = self._load_stats()
            total_mb = sum(s.get("freed_mb", 0) for s in sessions)
            perm = "管理员" if is_admin() else "普通权限"
            self.status_lbl.configure(
                text=f"健康分 {self.health_score}（{self.health_level}）"
                     f"    ·    累计释放 {human_size(int(total_mb * 1048576))}"
                     f"    ·    清理 {len(sessions)} 次"
                     f"    ·    权限：{perm}")
        except Exception:
            pass

    # ================= v5.0 设置中心：配置持久化 =================
    def _settings_path(self):
        return os.path.join(self._data_dir("config"), "settings.json")

    def _load_settings(self):
        """读取 settings.json 并与默认值合并（缺失键用默认）。"""
        try:
            import json
            if os.path.exists(self._settings_path()):
                with open(self._settings_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                merged.update(data)
                if isinstance(merged.get("schedule"), dict):
                    s = dict(DEFAULT_SETTINGS["schedule"])
                    s.update(merged["schedule"])
                    merged["schedule"] = s
                return merged
        except Exception:
            pass
        return dict(DEFAULT_SETTINGS)

    def _save_settings(self):
        try:
            import json
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _apply_settings(self):
        """把设置应用到运行态：主题 / 清理模式 / 定时器。"""
        self.settings = self._load_settings()
        # 主题
        if self.settings.get("theme") == "dark" and self.theme_name != "dark":
            self.theme_name = "dark"
            self.T = THEME_DARK
        # 清理安全模式（全局变量）
        global CLEAN_MODE
        CLEAN_MODE = self.settings.get("clean_mode", "recycle")
        if CLEAN_MODE not in ("recycle", "force", "dry-run"):
            CLEAN_MODE = "recycle"
        # 启动每日定时清理调度器（UI 构建完成后延迟启动，每分钟检查一次）
        try:
            if self._sched_tick:
                self.root.after_cancel(self._sched_tick)
        except Exception:
            pass
        self._sched_tick = self.root.after(15000, self._sched_check)

    def _sched_check(self):
        """计划任务：命中设置时间且当日未执行 → 自动低风险清理。"""
        try:
            import datetime
            sched = self.settings.get("schedule", {})
            if sched.get("enabled"):
                now = datetime.datetime.now()
                if now.hour == int(sched.get("hour", 12)) and now.minute == int(sched.get("minute", 0)):
                    today = now.strftime("%Y-%m-%d")
                    if self.settings.get("last_run") != today:
                        self.settings["last_run"] = today
                        self._save_settings()
                        self._log(f"⏱ 计划任务触发：每日自动清理（{today}）", "head")
                        self._smart_clean()
        except Exception:
            pass
        try:
            self._sched_tick = self.root.after(30000, self._sched_check)
        except Exception:
            self._sched_tick = None

    def open_settings(self):
        """设置中心：主题 / 清理模式 / 每日计划任务。"""
        win = tk.Toplevel(self.root)
        self._add_title_bar(win, "设置中心", "⚙️", (0x47, 0x55, 0x69))
        win.title("设置中心")
        win.geometry("560x520")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)

        def group(title):
            f = ttk.LabelFrame(body, text=f"  {title}  ", padding=10, style="Card.TLabelframe")
            f.pack(fill="x", pady=(0, 12))
            return f

        # ---- 主题 ----
        g = group("🎨 界面主题")
        self._set_theme_var = tk.StringVar(value=self.theme_name)
        ttk.Radiobutton(g, text="浅色「晴空」", value="light",
                        variable=self._set_theme_var).pack(anchor="w", pady=2)
        ttk.Radiobutton(g, text="深色「深空驾驶舱」", value="dark",
                        variable=self._set_theme_var).pack(anchor="w", pady=2)

        # ---- 清理安全模式 ----
        g = group("🛡 清理安全模式")
        self._set_mode_var = tk.StringVar(value=CLEAN_MODE)
        ttk.Radiobutton(g, text="移入回收站（推荐 · 可还原，误删零风险）", value="recycle",
                        variable=self._set_mode_var).pack(anchor="w", pady=2)
        ttk.Radiobutton(g, text="直接删除（释放更彻底，不可恢复）", value="force",
                        variable=self._set_mode_var).pack(anchor="w", pady=2)
        ttk.Radiobutton(g, text="仅模拟 dry-run（只统计不删除）", value="dry-run",
                        variable=self._set_mode_var).pack(anchor="w", pady=2)

        # ---- 每日计划任务 ----
        g = group("⏱ 每日定时自动清理")
        self._set_sched_var = tk.BooleanVar(value=bool(self.settings.get("schedule", {}).get("enabled")))
        ttk.Checkbutton(g, text="启用（低风险项自动清理，完成后轻提示；需保持程序运行）",
                        variable=self._set_sched_var).pack(anchor="w", pady=2)
        row = ttk.Frame(g)
        row.pack(anchor="w", pady=(8, 0))
        ttk.Label(row, text="每日 ").pack(side="left")
        self._set_hour_var = tk.StringVar(value=str(self.settings.get("schedule", {}).get("hour", 12)).zfill(2))
        ttk.Spinbox(row, from_=0, to=23, width=4, textvariable=self._set_hour_var,
                    format="%02.0f").pack(side="left")
        ttk.Label(row, text=" 时 ").pack(side="left")
        self._set_min_var = tk.StringVar(value=str(self.settings.get("schedule", {}).get("minute", 0)).zfill(2))
        ttk.Spinbox(row, from_=0, to=59, width=4, textvariable=self._set_min_var,
                    format="%02.0f").pack(side="left")
        ttk.Label(row, text=" 分 自动清理").pack(side="left")

        def _save():
            try:
                self.settings["theme"] = self._set_theme_var.get()
                self.settings["clean_mode"] = self._set_mode_var.get()
                self.settings["schedule"] = {
                    "enabled": bool(self._set_sched_var.get()),
                    "hour": int(self._set_hour_var.get() or 12),
                    "minute": int(self._set_min_var.get() or 0),
                }
                self._save_settings()
                global CLEAN_MODE
                CLEAN_MODE = self.settings["clean_mode"]
                theme_changed = self.settings["theme"] != self.theme_name
                self._log("⚙️ 设置已保存并生效", "ok")
                self._toast("⚙️ 设置已保存", bg="#0f766e")
                try:
                    win.destroy()   # 若主题切换触发整窗重建，窗口已被销毁，忽略
                except Exception:
                    pass
                if theme_changed:
                    self._apply_theme()
            except Exception as e:
                messagebox.showerror("保存失败", f"设置保存出错：{e}")

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="💾 保存设置", command=_save, style="Primary.TButton").pack(side="left", padx=4)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=4)

    # ================= v5.0 磁盘地图：空间占比 + 大文件 TOP50 =================
    def open_diskmap(self):
        """磁盘地图面板：各盘占比进度条 + 大文件 TOP50（后台线程扫描，双击定位）。"""
        win = tk.Toplevel(self.root)
        self._add_title_bar(win, "磁盘地图", "💽", (0xea, 0x58, 0x0c))
        win.title("磁盘地图 · 空间占比与大文件")
        win.geometry("720x600")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        # ---- 各盘占比 ----
        ttk.Label(body, text="📀 各盘空间占比", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        drives_box = tk.Frame(body, bg=self.COLOR_CARD, highlightthickness=1,
                              highlightbackground=self.COLOR_BORDER, bd=0)
        drives_box.pack(fill="x", pady=(4, 12))
        try:
            import ctypes
            for letter in get_fixed_drives():
                total = ctypes.c_ulonglong(0)
                free = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    f"{letter}:\\", None, ctypes.byref(total), ctypes.byref(free))
                used = total.value - free.value
                pct = used / total.value * 100 if total.value else 0
                row = ttk.Frame(drives_box)
                row.pack(fill="x", padx=10, pady=5)
                ttk.Label(row, text=f"{letter}:", font=("Consolas", 11, "bold"),
                          foreground=self.COLOR_ACCENT).pack(side="left", width=4)
                ttk.Label(row, text=f"{human_size(used)} / {human_size(total.value)}",
                          font=("Microsoft YaHei UI", 8),
                          foreground=self.COLOR_TEXT2).pack(side="right")
                bar = ttk.Progressbar(row, maximum=100, value=pct)
                bar.pack(side="left", fill="x", expand=True, padx=8)
                ttk.Label(row, text=f"{pct:.0f}%", font=("Consolas", 9, "bold"),
                          foreground=self.COLOR_WARN if pct > 85 else self.COLOR_TEXT2).pack(side="left")
        except Exception:
            ttk.Label(drives_box, text="无法读取磁盘信息", foreground=self.COLOR_TEXT2).pack(pady=8)

        # ---- 大文件 TOP50 ----
        ttk.Label(body, text="🗃 大文件 TOP 50（用户目录 + 各盘根目录，跳过系统目录）",
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        top_box = tk.Frame(body, bg=self.COLOR_CARD, highlightthickness=1,
                           highlightbackground=self.COLOR_BORDER, bd=0)
        top_box.pack(fill="both", expand=True, pady=(4, 0))
        self.dm_tree = ttk.Treeview(top_box, columns=("size", "path"), show="headings", height=14)
        self.dm_tree.heading("size", text="大小")
        self.dm_tree.heading("path", text="路径")
        self.dm_tree.column("size", width=100, anchor="e", stretch=False)
        self.dm_tree.column("path", width=560, stretch=True)
        self.dm_tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(top_box, orient="vertical", command=self.dm_tree.yview)
        vsb.pack(side="right", fill="y")
        self.dm_tree.configure(yscrollcommand=vsb.set)
        self.dm_tree.bind("<Double-1>", lambda e: self._dm_open())

        foot = ttk.Frame(body)
        foot.pack(fill="x", pady=(8, 0))
        self.dm_status = tk.StringVar(value="就绪：点击「开始扫描」查找大文件")
        ttk.Label(foot, textvariable=self.dm_status, font=("Microsoft YaHei UI", 8),
                  foreground=self.COLOR_TEXT2).pack(side="left")
        ttk.Button(foot, text="定位选中", command=self._dm_open).pack(side="right", padx=4)
        ttk.Button(foot, text="🔍 开始扫描", command=self._dm_scan,
                   style="Primary.TButton").pack(side="right", padx=4)

    def _dm_scan(self):
        """后台线程扫描大文件（堆取 Top50），完成后主线程填充表格。"""
        if getattr(self, "_dm_busy", False):
            return
        self._dm_busy = True
        for item in self.dm_tree.get_children():
            self.dm_tree.delete(item)
        self.dm_status.set("扫描中……（大目录较慢，请耐心等待）")

        def worker():
            import heapq
            top = []          # 小顶堆 (size, path)，保持前 50
            roots = []
            up = os.path.expanduser("~")
            if os.path.isdir(up):
                roots.append(up)
            for letter in get_fixed_drives():
                roots.append(f"{letter}:\\")
            skip_dirs = {"Windows", "$Recycle.Bin", "System Volume Information",
                         "node_modules", ".git", "Program Files", "Program Files (x86)"}
            for base in roots:
                if not os.path.isdir(base):
                    continue
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    for f in files:
                        p = os.path.join(root, f)
                        try:
                            sz = os.path.getsize(p)
                        except Exception:
                            continue
                        if len(top) < 50:
                            heapq.heappush(top, (sz, p))
                        elif sz > top[0][0]:
                            heapq.heapreplace(top, (sz, p))
            rows = sorted(top, reverse=True)
            try:
                self.root.after(0, self._dm_fill, rows)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _dm_fill(self, rows):
        self._dm_busy = False
        for sz, p in rows:
            self.dm_tree.insert("", "end", values=(human_size(sz), p))
        self.dm_status.set(f"✅ 扫描完成：找到 {len(rows)} 个大文件。双击定位 / 右键打开位置。")

    def _dm_open(self, event=None):
        sel = self.dm_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择一个大文件。")
            return
        path = self.dm_tree.item(sel[0], "values")[1]
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            try:
                os.startfile(os.path.dirname(path))
            except Exception:
                pass

    # ================= v4.0 智能版：战报 / 成就 / 数据 =================
    def _data_dir(self, name):
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        d = os.path.join(base, name)
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def _load_stats(self):
        try:
            import json
            p = os.path.join(self._data_dir("stats"), "history.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("sessions", [])
        except Exception:
            pass
        return []

    def _record_clean(self, freed, removed):
        try:
            import datetime
            import json
            sessions = self._load_stats()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sessions.append({"ts": now, "freed_mb": round(freed / 1048576.0, 2), "items": removed})
            if len(sessions) > 200:
                sessions = sessions[-200:]
            p = os.path.join(self._data_dir("stats"), "history.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"sessions": sessions}, f, ensure_ascii=False, indent=1)
            for icon, name, desc in self._check_achievements(sessions):
                self._log(f"{icon} 解锁成就「{name}」：{desc}", "ok")
                self._toast(f"{icon} 解锁成就「{name}」！", bg="#7c3aed")
        except Exception:
            pass

    @staticmethod
    def _check_achievements(sessions):
        total_mb = sum(s.get("freed_mb", 0) for s in sessions)
        days = len({s.get("ts", "")[:10] for s in sessions})
        rules = [
            ("🎯", "首战告捷", "完成第一次清理", len(sessions) >= 1),
            ("🔁", "渐入佳境", "累计清理 3 次", len(sessions) >= 3),
            ("🏅", "清理大师", "累计清理 10 次", len(sessions) >= 10),
            ("📦", "空间解放者", "累计释放 2 GB", total_mb >= 2048),
            ("🚀", "超级清理员", "累计释放 10 GB", total_mb >= 10240),
            ("💥", "单次暴击", "单次释放超 1 GB", any(s.get("freed_mb", 0) >= 1024 for s in sessions)),
            ("⏰", "早起鸟儿", "8 点前完成清理", any(int(s.get("ts", "12:00")[11:13]) < 8 for s in sessions)),
            ("💪", "勤勉之星", "累计清理 2 天", days >= 2),
        ]
        return [(i, n, d) for (i, n, d, ok) in rules if ok]

    def _toast(self, msg, bg="#0f766e", fg="#ffffff"):
        """右下角轻提示：2.6 秒后自动消失。"""
        try:
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            tk.Label(t, text=msg, bg=bg, fg=fg, font=("Microsoft YaHei UI", 10, "bold"),
                     padx=18, pady=10).pack()
            t.update_idletasks()
            x = self.root.winfo_rootx() + self.root.winfo_width() - t.winfo_width() - 24
            y = self.root.winfo_rooty() + self.root.winfo_height() - t.winfo_height() - 64
            t.geometry(f"+{x}+{y}")
            t.after(2600, t.destroy)
        except Exception:
            pass

    def open_stats(self):
        """战报窗口：统计卡 + 成就徽章 + 近 10 次清理柱状图。"""
        sessions = self._load_stats()
        total_mb = sum(s.get("freed_mb", 0) for s in sessions)
        best = max((s.get("freed_mb", 0) for s in sessions), default=0)
        win = tk.Toplevel(self.root)
        self._add_title_bar(win, "我的战报", "🏆", (0x7c, 0x3a, 0xed))
        win.title("我的战报")
        win.geometry("660x580")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)

        def stat_card(parent, icon, label, value):
            c = ttk.LabelFrame(parent, text="", padding=8, style="Card.TLabelframe")
            c.pack(side="left", expand=True, fill="x", padx=4)
            ttk.Label(c, text=icon, font=("Segoe UI Emoji", 18)).pack(anchor="w")
            ttk.Label(c, text=label, font=("Microsoft YaHei UI", 8),
                      foreground=self.COLOR_TEXT2).pack(anchor="w")
            ttk.Label(c, text=value, font=("Microsoft YaHei UI", 13, "bold"),
                      foreground=self.COLOR_ACCENT).pack(anchor="w")
            return c

        row0 = ttk.Frame(body)
        row0.pack(fill="x")
        stat_card(row0, "📦", "累计释放", human_size(int(total_mb * 1048576)))
        stat_card(row0, "🔁", "清理次数", f"{len(sessions)} 次")
        stat_card(row0, "💥", "最佳单次", human_size(int(best * 1048576)))

        ttk.Label(body, text="🏅 成就徽章", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(12, 4))
        unlocked = {n for _, n, _ in self._check_achievements(sessions)}
        all_achs = [
            ("🎯", "首战告捷", "完成第一次清理"), ("🔁", "渐入佳境", "累计清理 3 次"),
            ("🏅", "清理大师", "累计清理 10 次"), ("📦", "空间解放者", "累计释放 2 GB"),
            ("🚀", "超级清理员", "累计释放 10 GB"), ("💥", "单次暴击", "单次释放超 1 GB"),
            ("⏰", "早起鸟儿", "8 点前完成清理"), ("💪", "勤勉之星", "累计清理 2 天"),
        ]
        ach = ttk.Frame(body)
        ach.pack(fill="x")
        for i in range(0, len(all_achs), 2):
            row = ttk.Frame(ach)
            row.pack(fill="x", pady=2)
            for icon, name, desc in all_achs[i:i + 2]:
                on = name in unlocked
                c = ttk.Frame(row, style="Card.TFrame")
                c.pack(side="left", expand=True, fill="x", padx=4)
                ttk.Label(c, text=f"{icon} {name}", font=("Microsoft YaHei UI", 10, "bold"),
                          foreground=self.COLOR_ACCENT2 if on else "#94a3b8").pack(anchor="w")
                ttk.Label(c, text=desc, font=("Microsoft YaHei UI", 8),
                          foreground=self.COLOR_TEXT2 if on else "#94a3b8").pack(anchor="w")

        ttk.Label(body, text="📊 近 10 次清理", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(12, 4))
        cv = tk.Canvas(body, height=120, width=620, bg=self.COLOR_CARD, highlightthickness=0, bd=0)
        cv.pack(fill="x")
        recent = sessions[-10:]
        if recent:
            mx = max(max(s.get("freed_mb", 0) for s in recent), 1)
            n = len(recent)
            bw, gap = 38, 14
            x0 = (620 - n * (bw + gap)) // 2
            for i, s in enumerate(recent):
                h = max(4, 96 * s.get("freed_mb", 0) / mx)
                x = x0 + i * (bw + gap)
                y = 108 - h
                cv.create_rectangle(x, y, x + bw, 108, fill="#6366f1", outline="")
                cv.create_text(x + bw / 2, y - 8,
                               text=f"{s.get('freed_mb', 0) / 1024:.1f}G" if s.get("freed_mb", 0) >= 1024
                               else f"{s.get('freed_mb', 0):.0f}M",
                               font=("Microsoft YaHei UI", 8), fill=self.COLOR_TEXT2)
        else:
            cv.create_text(310, 60, text="还没有清理记录，去清理一次吧 🧹", fill=self.COLOR_TEXT2)

    # ================= v4.0 智能版：智能一键 =================
    def _smart_clean(self):
        """只勾选低/中风险项 → 自动扫描 → 自动清理 → 自动记录战报。"""
        if self.cleaning or self._scanning:
            return
        for item in CLEAN_ITEMS:
            self.item_vars[item["id"]].set(item["risk"] != "高")
            self._redraw_check(item["id"])
        self._auto_clean_pending = True
        self._log("✨ 智能一键：仅清理低/中风险缓存，全程自动，安全可靠", "head")
        self._scan()

    # ===== 圆角彩色卡片组件（PIL 生成圆角渐变背景 + Canvas 叠文字）=====
    def _card_bg_image(self, w, h, cfrom, cto, radius=14):
        """生成带透明圆角的垂直渐变背景图（PhotoImage），用于工具卡片。"""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(cfrom[0] * (1 - t) + cto[0] * t)
            g = int(cfrom[1] * (1 - t) + cto[1] * t)
            b = int(cfrom[2] * (1 - t) + cto[2] * t)
            dr.line([(0, y), (w, y)], fill=(r, g, b, 255))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        img.putalpha(mask)
        try:
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    @staticmethod
    def _lighten(c, amt=22):
        return tuple(min(255, v + amt) for v in c)

    @staticmethod
    def _draw_card_icon(cv, kind, cx, cy, s=26, bg_cut="#ffffff", color="#1F6F4A"):
        """在卡片 Canvas 上画一个固定 s 像素的几何图标（默认森林绿）。
        所有图标在 s×s 包围盒内居中、对齐、永远等大——彻底摆脱 emoji 字体回退问题。
        color 参数允许任意颜色（默认 #1F6F4A 森林绿）。"""
        h = s // 2
        if kind == "lightning":  # 一键优化
            pts = [cx + 1, cy - h, cx - h * 0.45, cy + 1, cx - h * 0.1, cy + 1,
                   cx - h * 0.45, cy + h, cx + h * 0.55, cy - h * 0.15,
                   cx + h * 0.1, cy - h * 0.15, cx + h * 0.5, cy - h * 0.55]
            cv.create_polygon(pts, fill=color, outline="")
        elif kind == "shield":  # 进程拦截
            cv.create_polygon([cx, cy - h, cx + h, cy - h * 0.6, cx + h * 0.85, cy + h * 0.4,
                                cx, cy + h, cx - h * 0.85, cy + h * 0.4, cx - h, cy - h * 0.6],
                              fill=color, outline="")
        elif kind == "box":  # 系统瘦身（立方体）
            cv.create_rectangle(cx - h, cy - h * 0.55, cx + h * 0.55, cy + h * 0.85,
                                outline=color, width=2)
            cv.create_polygon([cx - h, cy - h * 0.55, cx, cy - h,
                                cx + h * 0.55, cy - h * 0.55],
                              outline=color, width=2, fill="")
            cv.create_polygon([cx + h * 0.55, cy - h * 0.55, cx + h, cy - h,
                                cx + h, cy + h * 0.85, cx + h * 0.55, cy + h * 0.85],
                              outline=color, width=2, fill="")
        elif kind == "broom":  # 深度清理
            cv.create_polygon([cx - h * 0.3, cy + h * 0.85, cx - h, cy + h,
                                cx - h * 0.7, cy - h * 0.4, cx, cy - h * 0.6],
                              fill=color, outline="")
            for i in range(3):
                y = cy - h * 0.4 + i * h * 0.22
                cv.create_line(cx - h * 0.7 + i * h * 0.28, y,
                               cx - h * 0.35 + i * h * 0.28, y + h * 0.55,
                               fill=color, width=2)
        elif kind == "battery":  # 电源方案
            cv.create_rectangle(cx - h, cy - h * 0.5, cx + h * 0.7, cy + h * 0.5,
                                outline=color, width=2)
            cv.create_rectangle(cx + h * 0.7, cy - h * 0.22, cx + h * 1.0, cy + h * 0.22,
                                fill=color, outline="")
            cv.create_rectangle(cx - h * 0.7, cy - h * 0.28, cx + h * 0.3, cy + h * 0.28,
                                fill=color, outline="")
        elif kind == "gamepad":  # GPU 配置
            cv.create_polygon([cx - h, cy - h * 0.5, cx - h * 0.7, cy - h * 0.55,
                                cx + h * 0.7, cy - h * 0.55, cx + h, cy - h * 0.5,
                                cx + h * 1.1, cy - h * 0.1, cx + h, cy + h * 0.5,
                                cx - h, cy + h * 0.5, cx - h * 1.1, cy - h * 0.1],
                              fill=color, outline="")
            cv.create_oval(cx - h * 0.55, cy - h * 0.15, cx - h * 0.2, cy + h * 0.15,
                           fill=bg_cut, outline="")
            cv.create_oval(cx + h * 0.2, cy - h * 0.15, cx + h * 0.55, cy + h * 0.15,
                           fill=bg_cut, outline="")
        elif kind == "rocket":  # 启动项
            cv.create_polygon([cx, cy - h, cx + h * 0.4, cy - h * 0.35,
                                cx + h * 0.4, cy + h * 0.55, cx - h * 0.4, cy + h * 0.55,
                                cx - h * 0.4, cy - h * 0.35],
                              fill=color, outline="")
            cv.create_polygon([cx - h * 0.4, cy + h * 0.2, cx - h, cy + h * 0.9,
                                cx - h * 0.4, cy + h * 0.55],
                              fill=color, outline="")
            cv.create_polygon([cx + h * 0.4, cy + h * 0.2, cx + h, cy + h * 0.9,
                                cx + h * 0.4, cy + h * 0.55],
                              fill=color, outline="")
            cv.create_polygon([cx - h * 0.25, cy + h * 0.7, cx, cy + h * 1.05,
                                cx + h * 0.25, cy + h * 0.7],
                              fill=color, outline="")
        elif kind == "gear":  # 系统设置
            import math as _m
            cv.create_oval(cx - h * 0.7, cy - h * 0.7, cx + h * 0.7, cy + h * 0.7,
                           fill=color, outline="")
            for i in range(8):
                a = i * _m.pi / 4
                x1 = cx + _m.cos(a) * h * 0.7
                y1 = cy + _m.sin(a) * h * 0.7
                x2 = cx + _m.cos(a) * h * 1.05
                y2 = cy + _m.sin(a) * h * 1.05
                cv.create_line(x1, y1, x2, y2, fill=color, width=3)
            cv.create_oval(cx - h * 0.35, cy - h * 0.35, cx + h * 0.35, cy + h * 0.35,
                           fill=bg_cut, outline=color, width=1)
        elif kind == "globe":  # 外部工具
            cv.create_oval(cx - h, cy - h, cx + h, cy + h, outline=color, width=2)
            cv.create_oval(cx - h * 0.35, cy - h, cx + h * 0.35, cy + h,
                           outline=color, width=1.5)
            cv.create_line(cx - h, cy, cx + h, cy, fill=color, width=1.5)
            cv.create_line(cx, cy - h, cx, cy + h, fill=color, width=1.5)
        elif kind == "monitor":  # 系统工具
            cv.create_rectangle(cx - h, cy - h * 0.7, cx + h, cy + h * 0.4,
                                outline=color, width=2)
            cv.create_polygon([cx - h * 0.4, cy + h * 0.4, cx - h * 0.3, cy + h * 0.85,
                                cx + h * 0.3, cy + h * 0.85, cx + h * 0.4, cy + h * 0.4],
                              fill=color, outline="")
            cv.create_line(cx - h * 0.65, cy + h * 0.95, cx + h * 0.65, cy + h * 0.95,
                           fill=color, width=2)
        elif kind == "document":  # 导出报告
            cv.create_rectangle(cx - h * 0.65, cy - h, cx + h * 0.7, cy + h,
                                outline=color, width=2)
            cv.create_line(cx - h * 0.35, cy - h * 0.5, cx + h * 0.4, cy - h * 0.5,
                           fill=color, width=2)
            cv.create_line(cx - h * 0.35, cy, cx + h * 0.4, cy,
                           fill=color, width=2)
            cv.create_line(cx - h * 0.35, cy + h * 0.5, cx + h * 0.4, cy + h * 0.5,
                           fill=color, width=2)
        elif kind == "trophy":  # 我的战报
            cv.create_polygon([cx - h * 0.5, cy - h, cx + h * 0.5, cy - h,
                                cx + h * 0.5, cy + h * 0.1, cx + h * 0.3, cy + h * 0.45,
                                cx - h * 0.3, cy + h * 0.45, cx - h * 0.5, cy + h * 0.1],
                              fill=color, outline="")
            cv.create_oval(cx - h * 0.95, cy - h * 0.75, cx - h * 0.5, cy - h * 0.1,
                           outline=color, width=2)
            cv.create_oval(cx + h * 0.5, cy - h * 0.75, cx + h * 0.95, cy - h * 0.1,
                           outline=color, width=2)
            cv.create_polygon([cx - h * 0.4, cy + h * 0.45, cx + h * 0.4, cy + h * 0.45,
                                cx + h * 0.4, cy + h * 0.65, cx - h * 0.4, cy + h * 0.65],
                              fill=color, outline="")
            cv.create_rectangle(cx - h * 0.6, cy + h * 0.65, cx + h * 0.6, cy + h * 0.95,
                                fill=color, outline="")

    def _make_tool_card(self, parent, icon, title, subtitle, cfrom, cto, command, wide=False):
        """圆角彩色工具卡片（Canvas 自绘图标 · 等大 26×26 · 等高 78px）。
        图标、字号、位置都按固定像素绘制，**永远等大 + 横平竖直**，避免 emoji 字体回退。"""
        h = 78
        REF_W = 200
        cv = tk.Canvas(parent, bd=0, highlightthickness=0, bg=self.COLOR_CARD, height=h)
        cv._last_key = None
        cv._bg_item = None
        cv._img = None
        cv._img_hi = None

        def draw():
            w = cv.winfo_width()
            if w <= 1:
                return
            key = (w, h)
            if cv._last_key == key:
                return
            cv._last_key = key
            cv.delete("all")
            cv._bg_item = None

            img = self._card_bg_image(w, h, cfrom, cto)
            if img is None:
                cv.configure(bg="#%02x%02x%02x" % cto)
            else:
                cv._img = img
                cv._img_hi = self._card_bg_image(w, h, self._lighten(cfrom), self._lighten(cto))
                cv._bg_item = cv.create_image(0, 0, image=img, anchor="nw")

            # 文字区：标题 12pt 加粗 + 副标题 9pt，右侧固定像素布局
            r = w / REF_W
            title_size = max(9, int(11 * r))
            sub_size   = max(7, int(9  * r))
            icon_cx    = int(w * 0.15)
            text_x     = int(w * 0.30)
            # 固定 26×26 的几何图标（canvas 绘制，bg_cut 用于挖空）
            self._draw_card_icon(cv, icon, icon_cx, h / 2, s=26,
                                 bg_cut=self.COLOR_CARD)
            cv.create_text(text_x, h * 0.36, text=title,
                           font=("Microsoft YaHei UI", title_size, "bold"),
                           fill=color, anchor="w")
            cv.create_text(text_x, h * 0.68, text=subtitle,
                           font=("Microsoft YaHei UI", sub_size),
                           fill="#e2e8f0", anchor="w")

            def on_enter(e):
                cv.configure(cursor="hand2")
                if cv._img_hi is not None and cv._bg_item is not None:
                    cv.itemconfig(cv._bg_item, image=cv._img_hi)

            def on_leave(e):
                cv.configure(cursor="")
                if cv._img is not None and cv._bg_item is not None:
                    cv.itemconfig(cv._bg_item, image=cv._img)

            cv.bind("<Enter>", on_enter)
            cv.bind("<Leave>", on_leave)
            if cv._bg_item is not None:
                cv.tag_bind(cv._bg_item, "<Enter>", on_enter)
                cv.tag_bind(cv._bg_item, "<Leave>", on_leave)

        cv.bind("<Configure>", lambda e: draw())
        cv.after(20, draw)
        cv.bind("<Button-1>", lambda e: command())
        return cv

    def _build_tool_cards(self, parent):
        """左栏：圆角彩色工具卡片网格（紧凑 2 列等宽，无 columnspan 避免虚拟宽度坑）。"""
        grid = ttk.Frame(parent, style="Card.TFrame")
        grid.pack(fill="both", expand=True, padx=6, pady=6)
        for c in range(2):
            grid.columnconfigure(c, weight=1)

        # (icon_kind, title, subtitle, cfrom, cto, command)
        # 工具卡 12 张（磁盘地图 / 设置中心改为顶栏快捷入口，避免 3 列下溢出挤掉右栏）
        # 图标全部用 Canvas 自绘几何图形（_draw_card_icon），永远等大 + 横平竖直
        tools = [
            ("lightning", "一键优化", "全自动维护",     (0x25, 0x63, 0xeb), (0x0e, 0xa5, 0xe9), self.open_optduck),
            ("shield",    "进程拦截", "广告/挖矿拦截",   (0x63, 0x66, 0xf1), (0x8b, 0x5c, 0xf6), self.open_process_block),
            ("box",       "系统瘦身", "卸载预装",         (0x0e, 0xa5, 0xe9), (0x06, 0xb6, 0xd4), self.open_debloat),
            ("broom",     "深度清理", "注册表/驱动",     (0x10, 0xb9, 0x81), (0x14, 0xb8, 0xa6), self.open_deep),
            ("battery",   "电源方案", "电源切换",         (0xf9, 0x73, 0x16), (0xef, 0x44, 0x44), self.open_power),
            ("gamepad",   "GPU 配置", "显卡调度",         (0xec, 0x48, 0x99), (0xf4, 0x3f, 0x5e), self.open_gpu),
            ("rocket",    "启动项",   "开机加速",         (0x0d, 0x94, 0x88), (0x0e, 0xa5, 0xe9), self.open_startup),
            ("gear",      "系统设置", "高级/网络",         (0x47, 0x55, 0x69), (0x64, 0x74, 0x8b), self.open_godmode),
            ("globe",     "外部工具", "Win10/360",        (0x25, 0x63, 0xeb), (0x38, 0xbd, 0xf8), self.open_external_tools),
            ("monitor",   "系统工具", "控制面板",         (0x4f, 0x46, 0xe5), (0x7c, 0x3a, 0xed), self.open_systools),
            ("document",  "导出报告", "导出结果",         (0x0d, 0x94, 0x88), (0x10, 0xb9, 0x81), self._export_report),
            ("trophy",    "我的战报", "成就图表",         (0x7c, 0x3a, 0xed), (0xc0, 0x26, 0xd3), self.open_stats),
        ]
        # 流式布局（3 列等宽，避免 columnspan 引起的 Canvas 虚拟宽度不触发 Configure 陷阱）
        COLS = 3
        r, c = 0, 0
        for icon, title, subtitle, cfrom, cto, cmd in tools:
            if c + 1 > COLS:
                r += 1
                c = 0
            card = self._make_tool_card(grid, icon, title, subtitle, cfrom, cto, cmd)
            card.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            c += 1
            if c >= COLS:
                r += 1
                c = 0

    def _build_cleanup_panel(self, parent):
        """主页中区：可清理项目列表（占满全宽），沿用原 Treeview 逻辑。"""
        panel = ttk.LabelFrame(parent, text="  🧹  可清理项目（勾选后点击扫描）",
                               padding=10, style="Card.TLabelframe")
        panel.grid(row=0, column=0, sticky="nsew", pady=(2, 4), padx=4)
        self._build_cleanup_list_into(panel)
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(6, 3))
        self._build_select_stats_into(panel)
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(6, 3))
        self._build_action_buttons_into(panel)

    def _add_title_bar(self, win, title, icon, color):
        """给二级面板 Toplevel 加一条彩色渐变标题栏（替代系统灰标题），含关闭按钮。"""
        bar = tk.Frame(win, bg="#%02x%02x%02x" % color, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=icon, bg=bar["bg"], fg="white",
                 font=("Segoe UI Emoji", 16)).pack(side="left", padx=(12, 6))
        tk.Label(bar, text=title, bg=bar["bg"], fg="white",
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        close = tk.Label(bar, text="✕", bg=bar["bg"], fg="white",
                         font=("Microsoft YaHei UI", 12), cursor="hand2")
        close.pack(side="right", padx=12)
        close.bind("<Button-1>", lambda e: win.destroy())

    # ---- UI 构建 ----
    def _build_ui(self):
        # 顶部：左侧 logo 圆角色块 + 标题/副标题
        top = tk.Frame(self.root, bg=self.COLOR_BG)
        top.pack(fill="x", padx=14, pady=(10, 4))

        try:
            from PIL import Image, ImageDraw, ImageTk
            _logo_img = Image.new("RGBA", (44, 44), (37, 99, 235, 255))  # 主色蓝
            _d = ImageDraw.Draw(_logo_img)
            _d.ellipse((0, 0, 44, 44), fill=(37, 99, 235, 255))
            _tk_logo = ImageTk.PhotoImage(_logo_img)
        except Exception:
            _tk_logo = None

        logo_box = tk.Frame(top, bg=self.COLOR_BG)
        logo_box.pack(side="left")
        if _tk_logo is not None:
            tk.Label(logo_box, image=_tk_logo, bg=self.COLOR_BG).pack(side="left")
            self._logo_ref = _tk_logo  # 防止被 GC
        else:
            # 退化方案：用一块色块 + emoji
            tk.Label(logo_box, text="🛠", font=("Segoe UI Emoji", 22),
                     bg=self.COLOR_ACCENT, fg="#ffffff", width=2, height=1).pack(side="left", padx=(0, 2))

        title_box = tk.Frame(top, bg=self.COLOR_BG)
        title_box.pack(side="left", padx=(10, 0))
        tk.Label(title_box, text="系统优化工具箱",
                 font=("Microsoft YaHei UI", 16, "bold"),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor="w")
        tk.Label(title_box, text="轻巧专注的 Windows 维护套件 · v4.0 智能版（健康分 / 战报 / 深色主题）",
                 font=("Microsoft YaHei UI", 9),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT2).pack(anchor="w")

        # 右侧：顶栏快捷入口（磁盘地图 / 设置中心）+ 主题切换 + 管理员徽章
        right = tk.Frame(top, bg=self.COLOR_BG)
        right.pack(side="right")
        self.admin_badge = tk.Label(right, text="  ",
                                    font=("Microsoft YaHei UI", 9, "bold"),
                                    bg=self.COLOR_ACCENT2, fg="#ffffff",
                                    padx=8, pady=2)
        self.admin_badge.pack(side="right", anchor="e")
        self.theme_btn = tk.Label(right, text="🌙 深色", font=("Microsoft YaHei UI", 9, "bold"),
                                  bg=self.COLOR_CARD, fg=self.COLOR_TEXT, padx=10, pady=3,
                                  cursor="hand2", highlightthickness=1,
                                  highlightbackground=self.COLOR_BORDER)
        self.theme_btn.pack(side="right", anchor="e", padx=(8, 0))
        self.theme_btn.bind("<Button-1>", lambda e: self._apply_theme())

        def _short(icon, title, command):
            b = tk.Label(right, text=icon, font=("Segoe UI Emoji", 16),
                         bg=self.COLOR_BG, fg=self.COLOR_TEXT, cursor="hand2",
                         padx=6, pady=1)
            b.pack(side="right", anchor="e", padx=(6, 0))
            b.bind("<Button-1>", lambda e: command())
            try:
                b.bind("<Enter>", lambda e: b.configure(fg=self.COLOR_ACCENT))
                b.bind("<Leave>", lambda e: b.configure(fg=self.COLOR_TEXT))
            except Exception:
                pass
        _short("⚙", "设置中心", self.open_settings)
        _short("💽", "磁盘地图", self.open_diskmap)

        # 细分割线，弱化但保留
        tk.Frame(self.root, bg=self.COLOR_BORDER, height=1).pack(fill="x", padx=14, pady=(2, 6))

        # ---- 主体：左右分栏 ----
        # 左栏（固定宽）= 健康分仪表 + 圆角彩色工具卡片网格 + 实时资源监控
        # 右栏（弹性）  = 可清理项目面板（弹性高度）+ 运行日志（固定高度）
        main = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0, minsize=420)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # 左：健康分 + 工具卡片 + 监控（锁定宽度 420，禁止内容撑大后挤压右栏）
        left = ttk.Frame(main, style="Card.TFrame", width=420)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 8))
        left.pack_propagate(False)
        self._build_left_column(left)

        # 右：清理项目 + 日志（垂直分栏）
        right_p = ttk.Frame(main)
        right_p.grid(row=0, column=1, sticky="nsew")
        right_p.rowconfigure(0, weight=1)   # 清理项目：弹性高度
        right_p.rowconfigure(1, weight=0)   # 日志：自然高度
        self._build_cleanup_panel(right_p)
        self._build_log_into(right_p)

        # 底部状态栏
        self._build_status_bar()

    # ---- 顶部一行：4 个功能区分组横向并排 ----
    def _build_tools_top_row(self, parent):
        # 列 1：Windows 系统工具
        g1 = ttk.LabelFrame(parent, text="  🖥  Windows 系统工具", padding=10, style="Card.TLabelframe")
        g1.grid(row=0, column=0, sticky="nsew", padx=(4, 3), pady=2)
        self._button_grid(g1, [
            ("🎛 控制面板",   lambda: self._open_target("control.exe")),
            ("📊 任务管理器", lambda: self._open_target("taskmgr.exe")),
            ("🗑 卸载程序",   lambda: self._open_target("appwiz.cpl")),
            ("🧹 磁盘清理",   lambda: self._open_target("cleanmgr.exe")),
            ("📋 系统信息",   lambda: self._open_target("ms-settings:about")),
            ("🔧 设备管理器", lambda: self._open_target("devmgmt.msc")),
            ("💽 磁盘管理",   lambda: self._open_target("diskmgmt.msc")),
            ("⚙ 服务",        lambda: self._open_target("services.msc")),
            ("👑 上帝模式",   self.open_godmode),
        ], per_row=2, padx=4, pady_top=4, width=12, style="TButton")

        # 列 2：优化与卸载面板
        g2 = ttk.LabelFrame(parent, text="  🧩  优化与卸载面板", padding=10, style="Card.TLabelframe")
        g2.grid(row=0, column=1, sticky="nsew", padx=3, pady=2)
        self._button_grid(g2, [
            ("🧯 卸载预装",  self.open_debloat),
            ("🛠 深度优化",  self.open_deep),
            ("🎮 GPU 优化",  self.open_gpu),
            ("⚡ 电源/性能", self.open_power),
            ("🚀 启动项",    self.open_startup),
            ("🧩 Duck 全功能", self.open_optduck),
        ], per_row=2, padx=4, pady_top=4, width=12, style="TButton")

        # 列 3：外部工具
        g3 = ttk.LabelFrame(parent, text="  🌐  外部工具", padding=10, style="Card.TLabelframe")
        g3.grid(row=0, column=2, sticky="nsew", padx=3, pady=2)
        self._button_grid(g3, [
            ("🚀 Win10 优化",   self.launch_win10_optimizer),
            ("🌐 360 联网助手", self.launch_net_assist),
            ("🛡 进程拦截",     self.open_process_block),
        ], per_row=1, padx=4, pady_top=4, width=18, style="TButton")

        # 列 4：一键优化（橙色按钮强调高危）
        g4 = ttk.LabelFrame(parent, text="  ⚡  一键优化（需管理员）", padding=10, style="Card.TLabelframe")
        g4.grid(row=0, column=3, sticky="nsew", padx=(3, 4), pady=2)
        ttk.Label(
            g4,
            text="⚠ 高危：二次确认，全部可逆；非管理员触发 UAC。",
            foreground=self.COLOR_WARN, background=self.COLOR_CARD,
            font=("Microsoft YaHei UI", 8, "bold"),
            wraplength=220, justify="left",
        ).pack(anchor="w", pady=(0, 4))
        self._button_grid(g4, [
            ("🧹 DNS 缓存",     self.opt_dns_flush),
            ("🔋 高性能电源",   self.opt_high_perf),
            ("🏆 卓越电源",     self.opt_ultimate_perf),
            ("⚡ 快速启动",     self.opt_fastboot_on),
            ("⚡ 禁用 SysMain", self.opt_sysmain_off),
            ("📡 关传递优化",   self.opt_dosvc_off),
            ("🔎 关搜索索引",   self.opt_search_off),
            ("🎨 关透明动画",   self.opt_visual_off),
            ("📊 关遥测",       self.opt_telemetry_off),
            ("💤 关休眠",       self.opt_hibernate_off),
            ("🧱 关防火墙",     self.opt_firewall_off),
            ("🦠 关 Defender",  self.opt_defender_off),
            ("🔓 关 UAC",       self.opt_uac_off),
            ("🗑 关系统还原",   self.opt_system_restore_off),
            ("⬇ 关 Win 更新",   self.opt_wu_off),
        ], per_row=2, padx=2, pady_top=2, width=15, style="Opt.TButton")

    # ---- 按钮网格：每排 per_row 个，竖排 ----
    def _button_grid(self, parent, buttons, per_row=2, padx=12, pady_top=8, width=None, style="TButton"):
        for i in range(0, len(buttons), per_row):
            row = ttk.Frame(parent, style="Card.TFrame")
            row.pack(fill="x", pady=(pady_top, 0))
            for label, command in buttons[i:i + per_row]:
                btn = ttk.Button(row, text=label, command=command, style=style)
                if width:
                    btn.configure(width=width)
                btn.pack(side="left", padx=padx, expand=True, fill="x")

    # ---- 右侧（合并面板第一部分）：可清理项目列表 ----
    def _build_cleanup_list_into(self, parent):
        # 清理列表卡片：白底 + 圆角模拟（用 Frame 包一层 + highlightthickness）
        list_box = tk.Frame(parent, bg=self.COLOR_CARD, highlightthickness=0, bd=0)
        list_box.pack(fill="x", pady=(2, 0))

        # 内部再加一层白底 + 浅边框，让 Treeview 看起来像在卡片里
        inner = tk.Frame(list_box, bg=self.COLOR_CARD,
                         highlightthickness=1, highlightbackground=self.COLOR_BORDER, bd=0)
        inner.pack(fill="x", padx=2, pady=2)

        cols = ("check", "name", "detail", "size")
        self.tree = ttk.Treeview(inner, columns=cols, show="headings",
                                 style="Cleanup.Treeview", height=13)
        self.tree.heading("check", text="")
        self.tree.heading("name", text="项目")
        self.tree.heading("detail", text="位置")
        self.tree.heading("size", text="已占用")
        self.tree.column("check", width=40, anchor="center", stretch=False)
        self.tree.column("name", width=200, stretch=False)
        self.tree.column("detail", width=420, stretch=True)
        self.tree.column("size", width=110, anchor="e", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)
        inner.columnconfigure(0, weight=1)

        # 标签：选中行柔和薄荷绿，高危深红；强制未选行也用卡片底（避免默认主题残留）
        self.tree.tag_configure("checked", background=self.T["tree_checked"],
                                foreground=self.T["tree_checked_fg"])
        self.tree.tag_configure("unchecked", background=self.COLOR_CARD, foreground=self.COLOR_TEXT)
        self.tree.tag_configure("highrisk", foreground=self.COLOR_DANGER)
        for item in CLEAN_ITEMS:
            self.item_vars[item["id"]] = tk.BooleanVar(value=item["checked"])
            self.item_size[item["id"]] = 0
            self.item_count[item["id"]] = 0
            mark = "☑" if item["checked"] else "☐"
            tags = []
            if item["checked"]:
                tags.append("checked")
            else:
                tags.append("unchecked")
            if item["risk"] == "高":
                tags.append("highrisk")
            _sz = self.item_size.get(item["id"], 0)
            _cnt = self.item_count.get(item["id"], 0)
            _size_txt = f"{human_size(_sz)} ({_cnt})" if _sz else "未扫描"
            self.tree.insert(
                "", "end", iid=item["id"],
                values=(mark, item["name"], _elide(item["detail"], 28), _size_txt),
                tags=tuple(tags)
            )
        self.tree.bind("<Button-1>", self._on_tree_click)

    # ---- 右侧（合并面板第二部分）：全选 / 统计 ----
    def _build_select_stats_into(self, parent):
        f = ttk.Frame(parent, style="Card.TFrame")
        f.pack(fill="x")
        sel = ttk.Frame(f, style="Card.TFrame")
        sel.pack(fill="x")
        ttk.Button(sel, text="☑ 全选",   command=lambda: self._set_all(True),  style="TButton").pack(side="left", padx=2)
        ttk.Button(sel, text="☐ 全不选", command=lambda: self._set_all(False), style="TButton").pack(side="left", padx=2)
        ttk.Button(sel, text="✓ 仅低风险", command=self._only_low,            style="TButton").pack(side="left", padx=2)
        self.stat_var = tk.StringVar(value="已选占用：0 B ｜ 文件数：0")
        ttk.Label(f, textvariable=self.stat_var,
                  font=("Microsoft YaHei UI", 9, "bold"),
                  foreground=self.COLOR_ACCENT2, background=self.COLOR_CARD).pack(anchor="w", pady=(4, 0))

    # ---- 右侧（合并面板第三部分）：主操作按钮 ----
    def _build_action_buttons_into(self, parent):
        inner = ttk.Frame(parent, style="Card.TFrame")
        inner.pack(fill="x", anchor="w")
        self.btn_smart = ttk.Button(inner, text="✨  智能一键", command=self._smart_clean, style="Smart.TButton")
        self.btn_smart.pack(side="left", padx=5)
        self.btn_scan = ttk.Button(inner, text="🔍  扫描占用",  command=self._scan,  style="Primary.TButton")
        self.btn_scan.pack(side="left", padx=5)
        self.btn_clean = ttk.Button(inner, text="🚀  开始清理", command=self._ask_clean, style="Action.TButton")
        self.btn_clean.pack(side="left", padx=5)
        self.btn_export = ttk.Button(inner, text="📄 导出报告", command=self._export_report)
        self.btn_export.pack(side="left", padx=5)

    # ---- 底部：运行日志（全宽，卡片化 + 深色对比） ----
    def _build_log_into(self, parent):
        log_frame = ttk.LabelFrame(parent, text="  📜  运行日志", padding=8, style="Card.TLabelframe")
        log_frame.grid(row=1, column=0, sticky="ew", pady=(4, 0), padx=4)

        # 用一块 Frame 包裹 Text，模拟圆角（highlightthickness 留 1 像素浅深边框）
        wrap = tk.Frame(log_frame, bg="#0f172a",
                        highlightthickness=1, highlightbackground="#1e293b", bd=0)
        wrap.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(
            wrap, height=5, wrap="word",
            font=("Consolas", 9),
            bg="#0f172a", fg="#e2e8f0",
            insertbackground="#e2e8f0",
            selectbackground="#2563eb", selectforeground="#ffffff",
            relief="flat", bd=0, padx=10, pady=6,
        )
        self.log.pack(fill="both", expand=True)
        # 日志分级着色：ok 绿 / warn 橙 / err 红 / head 蓝
        self.log.tag_configure("ok", foreground="#34d399")
        self.log.tag_configure("warn", foreground="#fbbf24")
        self.log.tag_configure("err", foreground="#f87171")
        self.log.tag_configure("head", foreground="#93c5fd")
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
        self._add_title_bar(win, "卸载 Windows 预装应用", "🧯", (0x0e, 0xa5, 0xe9))

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
        self._add_title_bar(win, "Windows 深度优化", "🧹", (0x10, 0xb9, 0x81))

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
        self._add_title_bar(win, "电源/性能细项", "🔋", (0xf9, 0x73, 0x16))

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
        self._add_title_bar(win, "GPU 优化", "🎮", (0xec, 0x48, 0x99))

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
        self._add_title_bar(win, "启动项管理", "🚀", (0x0d, 0x94, 0x88))

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
        self._add_title_bar(win, "optimizerDuck 全功能优化", "🧩", (0x25, 0x63, 0xeb))

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
            self.admin_badge.configure(
                text="  🛡 已以管理员运行（最高权限）  ",
                bg=self.COLOR_ACCENT2, fg="#ffffff",
                font=("Microsoft YaHei UI", 9, "bold"),
            )
        else:
            self.admin_badge.configure(
                text="  ⚠ 普通权限（部分项无法清理）  ",
                bg=self.COLOR_DANGER, fg="#ffffff",
                font=("Microsoft YaHei UI", 9, "bold"),
            )

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

    def _log(self, msg, level="info"):
        """输出运行日志。线程安全——后台线程调用会通过 after(0) 转发到主线程，
        避免与 Tk 事件循环争抢 Tcl 解释器锁造成的卡死或崩溃。
        level: info / ok / warn / err / head（分级着色）。"""
        try:
            if threading.current_thread() is not threading.main_thread():
                self.root.after(0, self._log, msg, level)
                return
        except Exception:
            pass
        try:
            tag = {"ok": "ok", "warn": "warn", "err": "err", "head": "head"}.get(level, "")
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n", tag or ())
            self.log.see("end")
            self.log.configure(state="disabled")
        except Exception:
            pass

    # ---- 扫描 ----
    def _scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._last_clean_bonus = 0
        self.btn_scan.configure(state="disabled")
        drives = "、".join(d + "盘" for d in get_fixed_drives())
        self._log(f"开始扫描已选项目的占用空间……（已探测固定硬盘：{drives}）", "head")

        def _scan_update_row(iid, vals):
            # 仅主线程：直接更新 Treeview 行
            try:
                self.tree.item(iid, values=vals)
            except Exception:
                pass

        def _scan_done():
            self._scanning = False
            self._update_stat()
            self.btn_scan.configure(state="normal")
            self._update_health()
            if self._auto_clean_pending:
                self._auto_clean_pending = False
                self._log("✅ 扫描完成，低/中风险项已自动进入清理……", "ok")
                self._clean()
            else:
                self._log("✅ 扫描完成。可点击「开始清理」或「✨ 智能一键」。", "ok")

        def worker():
            for item in CLEAN_ITEMS:
                if not self.item_vars[item["id"]].get():
                    continue
                try:
                    sz, cnt = compute_size(item)
                except Exception as e:
                    sz, cnt = 0, 0
                    self._log(f"  [跳过] {item['name']} 扫描出错：{e}", "warn")
                self.item_size[item["id"]] = sz
                self.item_count[item["id"]] = cnt
                vals = list(self.tree.item(item["id"], "values"))
                vals[3] = f"{human_size(sz)} ({cnt})"
                # 跨线程：把 UI 更新转发到主线程
                try:
                    self.root.after(0, _scan_update_row, item["id"], vals)
                except Exception:
                    pass
                self._log(f"  {item['name']}：{human_size(sz)}（{cnt} 个文件）")
            try:
                self.root.after(0, _scan_done)
            except Exception:
                pass

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
        self._log("====== 开始清理 ======", "head")

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
                    self._log(f"  [错误] {item['name']}：{e}", "err")
                total_freed += freed
                total_removed += removed
                self._log(f"  ✓ 释放 {human_size(freed)}（{removed} 项）")
            self._log("====== 清理完成 ======", "ok")
            self._log(f"✅ 共释放：{human_size(total_freed)}，删除 {total_removed} 个文件/目录。", "ok")
            self.root.after(0, lambda: self._finish_clean(total_freed, total_removed))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_clean(self, freed, removed):
        self.cleaning = False
        self.btn_scan.configure(state="normal")
        self.btn_clean.configure(state="normal")
        # v4.0：记录战报 + 健康分加成 + 轻提示
        self._record_clean(freed, removed)
        self._last_clean_bonus = min(15, 5 + int(freed / (256 * 1024 * 1024)))
        self._update_health()
        self._hist_draw()   # 刷新仪表盘历史柱状图
        self._toast(f"🎉 本次释放 {human_size(freed)}，删除 {removed} 项！")
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
    # =====================================================================
    # 进程拦截（融合自 block-ads：按目录/签名黑名单拦截程序运行）
    # 复刻其核心能力：folder/sign 黑名单白名单管理 + 后台监控（轮询并终止
    # 被拦截的进程）。说明：Python 版为“监控并阻止运行”，非驱动级“启动即拦截”，
    # 行为语义与 block-ads 一致（阻止被拦截程序继续运行），但拦截时机为运行后轮询。
    # 原始规则文件（folder.txt/sign.txt/...）的目录/签名条目已作为默认规则内嵌。
    # =====================================================================
    # 默认规则（取自 block-ads 1.3 的 folder.txt / sign.txt，仅做融合基线）
    _PB_DEFAULT_FOLDER_BLACK = [
        "ZxVxTidy", "MultiWeChat", "NetPowerDLLRepair", "武汉优思干科技有限公司",
        "driverpro360", "winToolBox", "XFQDXTool", "ProZip", "NetPowerZipBingTwo",
        "WinOptimize", "Adobe Installers", "bizhigame",
    ]
    _PB_DEFAULT_SIGN_BLACK = [
        "天津微极智科技有限公司", "成都智云界科技有限公司", "武汉优思干科技有限公司",
        "Beijing AoLanDe Information Technology Co., Ltd.",
        "长沙亿语科技有限公司", "成都汇电时代科技有限公司", "北京创想界科技有限公司",
        "天津六六游科技有限公司", "Changsha Little Tomato Technology Co., Ltd.",
        "Shenzhen Chaoshidai Software Co., Ltd.",
        "Jiangxia Information Technology (Huizhou) Co., Ltd.",
        "珠海市莫停之科技有限公司",
    ]

    def _pb_rules_dir(self):
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        d = os.path.join(base, "blockrules")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return d

    def _pb_rule_path(self, name):
        return os.path.join(self._pb_rules_dir(), name)

    def _pb_load_rules(self):
        """读取 4 个规则文件；不存在则用默认规则写入。返回 dict。"""
        files = {
            "folder_black": ("folder_black.txt", self._PB_DEFAULT_FOLDER_BLACK),
            "sign_black": ("sign_black.txt", self._PB_DEFAULT_SIGN_BLACK),
            "folder_white": ("folder_white.txt", []),
            "sign_white": ("sign_white.txt", []),
        }
        out = {}
        for key, (fname, default) in files.items():
            p = self._pb_rule_path(fname)
            if not os.path.exists(p):
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write("\n".join(default) + ("\n" if default else ""))
                except Exception:
                    pass
            try:
                with open(p, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f.read().splitlines()
                             if ln.strip() and not ln.strip().startswith("#")]
            except Exception:
                lines = list(default)
            out[key] = lines
        return out

    def _pb_save_rules(self, rules):
        mapping = {
            "folder_black": "folder_black.txt",
            "sign_black": "sign_black.txt",
            "folder_white": "folder_white.txt",
            "sign_white": "sign_white.txt",
        }
        for key, fname in mapping.items():
            p = self._pb_rule_path(fname)
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write("\n".join(rules.get(key, [])) + "\n")
            except Exception as e:
                self._log(f"[进程拦截] 保存规则失败：{e}")

    def _pb_company_cache(self):
        if not hasattr(self, "_pb_company"):
            self._pb_company = {}
        return self._pb_company

    def _pb_get_company(self, path):
        """读取 exe 的数字签名/版本信息中的公司名（CompanyName）。失败返回 ''。"""
        cache = self._pb_company_cache()
        if path in cache:
            return cache[path]
        company = ""
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$OutputEncoding=[System.Text.Encoding]::UTF8;"
                 "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                 "(Get-Item -LiteralPath '%s').VersionInfo.CompanyName" % path.replace("'", "''")],
                capture_output=True, encoding="utf-8", errors="replace", timeout=8,
            )
            company = (out.stdout or "").strip()
        except Exception:
            company = ""
        cache[path] = company
        return company

    def _pb_enum_processes(self):
        """返回 [(pid, path, name), ...]，path 可能为空。"""
        procs = []
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$OutputEncoding=[System.Text.Encoding]::UTF8;"
                 "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
                 "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath | "
                 "ForEach-Object { \"$($_.ProcessId)|$($_.Name)|$($_.ExecutablePath)\" }"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=20,
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 2)
                pid = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else ""
                path = parts[2].strip() if len(parts) > 2 else ""
                if pid.isdigit():
                    procs.append((int(pid), path, name))
        except Exception as e:
            self._log(f"[进程拦截] 枚举进程失败：{e}")
        return procs

    def _pb_is_blocked(self, path, name, rules):
        """判定进程是否应被拦截。返回 (是否拦截, 命中规则描述)。"""
        fb = [r.lower() for r in rules.get("folder_black", [])]
        fw = [r.lower() for r in rules.get("folder_white", [])]
        sb = [r.lower() for r in rules.get("sign_black", [])]
        sw = [r.lower() for r in rules.get("sign_white", [])]
        pl = (path or "").lower()
        # 目录白名单优先
        for w in fw:
            if w and w in pl:
                return False, ""
        # 签名白名单（需查公司名）
        if sb or sw:
            comp = self._pb_get_company(path).lower() if path else ""
            for w in sw:
                if w and w in comp:
                    return False, ""
        # 目录黑名单：路径包含该片段（匹配目录名或完整路径前缀）
        for r in fb:
            if r and r in pl:
                return True, f"目录黑名单：{r}"
        # 签名黑名单：公司名包含该片段
        if sb:
            comp = self._pb_get_company(path).lower() if path else ""
            for r in sb:
                if r and r in comp:
                    return True, f"签名黑名单：{r}"
        return False, ""

    def _pb_terminate(self, pid, name):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, encoding="utf-8", errors="replace", timeout=10)
            return True
        except Exception as e:
            self._log(f"[进程拦截] 终止 {name}({pid}) 失败：{e}")
            return False

    def _pb_log(self, widget, msg):
        try:
            if threading.current_thread() is not threading.main_thread():
                self.root.after(0, self._pb_log, widget, msg)
                return
        except Exception:
            pass
        try:
            widget.configure(state="normal")
            widget.insert("end", msg + "\n")
            widget.see("end")
            widget.configure(state="disabled")
        except Exception:
            pass

    def _pb_monitor_loop(self, log_widget, status_var):
        import time
        check_interval = 5
        while getattr(self, "_pb_running", False):
            rules = self._pb_load_rules()
            procs = self._pb_enum_processes()
            blocked_count = 0
            for pid, path, name in procs:
                if pid in (os.getpid(),):
                    continue
                try:
                    blocked, reason = self._pb_is_blocked(path, name, rules)
                except Exception:
                    blocked = False
                    reason = ""
                if blocked:
                    ok = self._pb_terminate(pid, name)
                    verb = "已终止" if ok else "终止失败"
                    self._pb_log(log_widget,
                                 f"[{time.strftime('%H:%M:%S')}] {verb} {name} "
                                 f"(PID={pid}) 路径={path or '?'} 规则={reason}")
                    blocked_count += 1
            if blocked_count:
                self.root.after(0, status_var.set,
                                f"监控中 · 本轮拦截 {blocked_count} 个进程")
            else:
                self.root.after(0, status_var.set, "监控中 · 未命中")
            # 分段睡眠，保证可及时停止
            for _ in range(check_interval * 2):
                if not getattr(self, "_pb_running", False):
                    break
                time.sleep(0.5)

    def open_process_block(self):
        """打开“进程拦截”子窗口（block-ads 核心能力融合）。"""
        win = tk.Toplevel(self.root)
        win.title("进程拦截（融合 block-ads）")
        win.geometry("920x600")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        self._add_title_bar(win, "进程拦截", "🛡", (0x63, 0x66, 0xf1))

        # 顶部工具栏
        bar = ttk.Frame(win, padding=(8, 6))
        bar.pack(fill="x")
        self._pb_status = tk.StringVar(value="已停止")
        btn_start = ttk.Button(bar, text="▶ 启动监控")
        btn_stop = ttk.Button(bar, text="■ 停止监控", state="disabled")
        btn_save = ttk.Button(bar, text="💾 保存规则")
        btn_reset = ttk.Button(bar, text="↺ 恢复默认")
        btn_start.pack(side="left", padx=4)
        btn_stop.pack(side="left", padx=4)
        btn_save.pack(side="left", padx=4)
        btn_reset.pack(side="left", padx=4)
        ttk.Label(bar, textvariable=self._pb_status, foreground="#b00020").pack(
            side="left", padx=10)

        # 主体：左右分栏
        pane = ttk.PanedWindow(win, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=6)

        # 左：规则编辑（4 个标签页）
        left = ttk.Notebook(pane)
        rules = self._pb_load_rules()
        editors = {}
        tabs = [
            ("目录黑名单", "folder_black.txt", "folder_black"),
            ("签名黑名单", "sign_black.txt", "sign_black"),
            ("目录白名单", "folder_white.txt", "folder_white"),
            ("签名白名单", "sign_white.txt", "sign_white"),
        ]
        for title, fname, key in tabs:
            frm = ttk.Frame(left)
            left.add(frm, text=title)
            txt = tk.Text(frm, wrap="word", font=("Microsoft YaHei UI", 10),
                          undo=True)
            txt.pack(fill="both", expand=True, padx=4, pady=4)
            txt.insert("1.0", "\n".join(rules.get(key, [])))
            editors[key] = txt
        pane.add(left, weight=1)

        # 右：拦截记录
        right = ttk.LabelFrame(pane, text="拦截记录", padding=4)
        logw = tk.Text(right, wrap="word", font=("Consolas", 9),
                       state="disabled", foreground="#222")
        logw.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        ttk.Button(right, text="清空记录",
                   command=lambda: (logw.configure(state="normal"),
                                    logw.delete("1.0", "end"),
                                    logw.configure(state="disabled"))).pack(anchor="e", padx=4, pady=(0, 4))
        pane.add(right, weight=1)

        # ---- 行为 ----
        def do_save():
            new_rules = {key: editors[key].get("1.0", "end").splitlines() for _, _, key in tabs}
            new_rules = {k: [ln.strip() for ln in v if ln.strip()
                             and not ln.strip().startswith("#")] for k, v in new_rules.items()}
            self._pb_save_rules(new_rules)
            self._pb_log(logw, "[规则已保存]")
            self._log("[进程拦截] 规则已保存")

        def do_reset():
            self._pb_save_rules({
                "folder_black": self._PB_DEFAULT_FOLDER_BLACK,
                "sign_black": self._PB_DEFAULT_SIGN_BLACK,
                "folder_white": [],
                "sign_white": [],
            })
            for _, _, key in tabs:
                editors[key].delete("1.0", "end")
                editors[key].insert("1.0", "\n".join(self._pb_load_rules().get(key, [])))
            self._pb_log(logw, "[已恢复 block-ads 默认规则]")

        def do_start():
            if getattr(self, "_pb_running", False):
                return
            self._pb_running = True
            self._pb_company = {}
            btn_start.configure(state="disabled")
            btn_stop.configure(state="normal")
            self._pb_status.set("监控中…")
            self._pb_log(logw, "[监控已启动]")
            t = threading.Thread(target=self._pb_monitor_loop,
                                 args=(logw, self._pb_status), daemon=True)
            self._pb_thread = t
            t.start()

        def do_stop():
            self._pb_running = False
            btn_start.configure(state="normal")
            btn_stop.configure(state="disabled")
            self._pb_status.set("已停止")
            self._pb_log(logw, "[监控已停止]")

        btn_start.configure(command=do_start)
        btn_stop.configure(command=do_stop)
        btn_save.configure(command=do_save)
        btn_reset.configure(command=do_reset)

        # 关闭窗口时若仍在监控，提示（不强制停止，让用户自行决定）
        def on_close():
            if getattr(self, "_pb_running", False):
                self._pb_log(logw, "[窗口关闭，监控仍在后台运行；再次打开可停止]")
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        self._pb_log(logw, "[进程拦截已就绪] 点击“启动监控”开始按规则拦截运行中的程序。")




    def open_external_tools(self):
        """外部工具集合：Win10 优化、360 联网助手。"""
        win = tk.Toplevel(self.root)
        win.title("外部工具")
        win.geometry("420x240")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        self._add_title_bar(win, "外部工具", "🌐", (0x25, 0x63, 0xeb))
        body = ttk.Frame(win, padding=14, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="以下工具为第三方/独立脚本，点击后以独立窗口运行：",
                  font=("Microsoft YaHei UI", 10), foreground=self.COLOR_TEXT2).pack(anchor="w", pady=(0, 10))
        self._button_grid(body, [
            ("🪟 Win10 优化版", self.launch_win10_optimizer),
            ("🌐 360 联网助手", self.launch_net_assist),
        ], per_row=1, width=24, style="TButton")

    def open_systools(self):
        """Windows 系统工具快捷入口集合。"""
        win = tk.Toplevel(self.root)
        win.title("系统工具")
        win.geometry("460x340")
        win.transient(self.root)
        try:
            win.iconbitmap(self._icon_path)
        except Exception:
            pass
        self._add_title_bar(win, "系统工具", "🖥", (0x4f, 0x46, 0xe5))
        body = ttk.Frame(win, padding=14, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        self._button_grid(body, [
            ("🎛 控制面板",   lambda: self._open_target("control.exe")),
            ("📊 任务管理器", lambda: self._open_target("taskmgr.exe")),
            ("🗑 卸载程序",   lambda: self._open_target("appwiz.cpl")),
            ("🧹 磁盘清理",   lambda: self._open_target("cleanmgr.exe")),
            ("📋 系统信息",   lambda: self._open_target("ms-settings:about")),
            ("🔧 设备管理器", lambda: self._open_target("devmgmt.msc")),
            ("💽 磁盘管理",   lambda: self._open_target("diskmgmt.msc")),
            ("⚙ 服务",        lambda: self._open_target("services.msc")),
            ("👑 上帝模式",   self.open_godmode),
        ], per_row=2, width=18, style="TButton")


# ---- v4.0 实时监控：ctypes 读取 CPU / 内存（零新依赖）----
_cpu_last = None


def _cpu_percent():
    """基于两次采样差值的 CPU 使用率（Windows GetSystemTimes）。"""
    global _cpu_last
    try:
        import ctypes as _ct

        class FT(_ct.Structure):
            _fields_ = [("dwLowDateTime", _ct.c_uint32), ("dwHighDateTime", _ct.c_uint32)]

        def _times():
            i, k, u = FT(), FT(), FT()
            _ct.windll.kernel32.GetSystemTimes(_ct.byref(i), _ct.byref(k), _ct.byref(u))

            def tot(f):
                return (f.dwHighDateTime << 32) | f.dwLowDateTime

            return tot(i), tot(k), tot(u)

        cur = _times()
        if _cpu_last is None:
            _cpu_last = cur
            return 0.0
        i1, k1, u1 = _cpu_last
        i2, k2, u2 = cur
        _cpu_last = cur
        idle, total = i2 - i1, (k2 - k1) + (u2 - u1)
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, (1 - idle / total) * 100))
    except Exception:
        return 0.0


def _ram_percent():
    """内存使用率（GlobalMemoryStatusEx.dwMemoryLoad，0-100）。"""
    try:
        import ctypes as _ct

        class MS(_ct.Structure):
            _fields_ = [
                ("dwLength", _ct.c_ulong), ("dwMemoryLoad", _ct.c_ulong),
                ("ullTotalPhys", _ct.c_ulonglong), ("ullAvailPhys", _ct.c_ulonglong),
                ("ullTotalPageFile", _ct.c_ulonglong), ("ullAvailPageFile", _ct.c_ulonglong),
                ("ullTotalVirtual", _ct.c_ulonglong), ("ullAvailVirtual", _ct.c_ulonglong),
                ("ullAvailExtendedVirtual", _ct.c_ulonglong),
            ]

        m = MS()
        m.dwLength = _ct.sizeof(MS)
        _ct.windll.kernel32.GlobalMemoryStatusEx(_ct.byref(m))
        return float(m.dwMemoryLoad)
    except Exception:
        return 0.0


def _disk_usage_pct(letter="C"):
    """指定盘符使用率（0-100）。GetDiskFreeSpaceExW。"""
    try:
        import ctypes
        total = ctypes.c_ulonglong(0)
        free = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            f"{letter}:\\", None, ctypes.byref(total), ctypes.byref(free))
        if total.value:
            return 100.0 * (1 - free.value / total.value)
    except Exception:
        pass
    return 0.0


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

        # 启动淡入动效（Windows 支持窗口透明度）
        try:
            root.attributes("-alpha", 0.0)

            def _fade(step=0):
                try:
                    root.attributes("-alpha", min(1.0, step * 0.1))
                except Exception:
                    return
                if step < 10:
                    root.after(18, _fade, step + 1)

            _fade()
        except Exception:
            pass

        # 打开即自动扫描已勾选项目的占用（_scan 内部走后台线程，不卡 UI）
        root.after(500, app._scan)
        root.mainloop()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            None, f"启动失败：{e}\n（请确认以管理员身份运行）", "系统优化工具箱", 0x10
        )


if __name__ == "__main__":
    main()
