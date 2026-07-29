# -*- coding: utf-8 -*-
"""
本模块由 LightC 2.15.0 的清理能力派生而来。

版权：LightC (C) 2024-2025，基于 Rust + Tauri 构建（仓库 light-c）。
原始清理逻辑位于 light-c-2.15.0/src-tauri/src/ 各扫描器（scanner/deep_junk.rs、
scanner/social_scanner.rs、ai_models/*、driver_cleanup 等）。本模块仅抽取其中
**文件型、可静态表达的清理目标**（垃圾清理 / 社交软件缓存 / AI 模型缓存），
并转换为系统优化工具箱原生的 CLEAN_ITEMS 条目，与现有清理框架统一。

明确省略（需注册表/动态探测，超出 CLEAN_ITEMS 文件清理模型，未移植）：
- 注册表冗余清理 (scanner/registry.rs)
- 右键菜单清理 (scanner/context_menu.rs)
- 外壳图标管理 (scanner/shell_icons.rs)
- 系统瘦身 (system_slim) 中的注册表/组件项
- 旧驱动清理 (driver_cleanup)：需判定“正在使用的驱动”，静态删除 DriverStore 风险过高，已省略
- 大文件 / 卸载残留 / 磁盘变化分析：动态扫描器，无固定目标，已省略

路径在导入时解析（与系统优化工具箱 CLEAN_ITEMS 一致）：%VAR% 形式的目录用
os.environ 在用户机器上展开，保证跨用户/机器可移植。

风险分级（沿用工具箱约定）：
- 低：临时/缓存，删除后系统自动重建，默认可勾选
- 中：接收到的文件 / 升级残留，谨慎清理，默认不勾选
- 高：用户主动下载的大体积数据（AI 模型），误删损失大，默认不勾选
"""
import os

_LA = os.environ.get("LOCALAPPDATA", "")
_RA = os.environ.get("APPDATA", "")
_UP = os.environ.get("USERPROFILE", "")
_PD = os.environ.get("PROGRAMDATA", "")
_SD = os.environ.get("SYSTEMDRIVE", "C:").rstrip("\\") + "\\"
_WIN = os.environ.get("WINDIR", os.path.join(_SD, "Windows"))


def _j(*parts):
    return os.path.join(*parts)


# ----------------------------------------------------------------------------
# 垃圾清理（对应 deep_junk.rs 的已知安全垃圾根）
# ----------------------------------------------------------------------------
_JUNK = [
    ("lc_junk_deliveryopt", "传递优化缓存 (Delivery Optimization)",
     [_j(_WIN, "SoftwareDistribution", "DeliveryOptimization")], "低",
     "Windows\\SoftwareDistribution\\DeliveryOptimization"),
    ("lc_junk_do_cache", "传递优化缓存 (NetworkService)",
     [_j(_WIN, "ServiceProfiles", "NetworkService", "AppData", "Local",
         "Microsoft", "Windows", "DeliveryOptimization", "Cache")], "低",
     "ServiceProfiles\\NetworkService\\...\\DeliveryOptimization\\Cache"),
    ("lc_junk_windows_logs", "Windows 日志目录",
     [_j(_WIN, "Logs")], "低", "Windows\\Logs"),
    ("lc_junk_minidump", "Windows 小内存转储 (Minidump)",
     [_j(_WIN, "Minidump")], "低", "Windows\\Minidump"),
    ("lc_junk_wer", "Windows 错误报告 (WER)",
     [_j(_PD, "Microsoft", "Windows", "WER")], "低",
     "ProgramData\\Microsoft\\Windows\\WER"),
    ("lc_junk_defender_localcopy", "Microsoft Defender LocalCopy 缓存",
     [_j(_PD, "Microsoft", "Windows Defender", "LocalCopy")], "低",
     "ProgramData\\Microsoft\\Windows Defender\\LocalCopy（可重建）"),
    ("lc_junk_defender_support", "Microsoft Defender Support 缓存",
     [_j(_PD, "Microsoft", "Windows Defender", "Support")], "低",
     "ProgramData\\Microsoft\\Windows Defender\\Support（可重建）"),
    ("lc_junk_d3dscache", "DirectX 着色器缓存 (D3DSCache)",
     [_j(_LA, "Microsoft", "Windows", "D3DSCache"),
      _j(_LA, "D3DSCache")], "低",
     "%LOCALAPPDATA%\\Microsoft\\Windows\\D3DSCache"),
    ("lc_junk_windows_old", "旧系统目录 (Windows.old)",
     [_j(_SD, "Windows.old")], "中",
     "Windows.old（系统升级残留，体积大，确认无用后可清）"),
    ("lc_junk_winbt", "升级临时目录 ($Windows.~BT / $Windows.~WS)",
     [_j(_SD, "$Windows.~BT"), _j(_SD, "$Windows.~WS")], "中",
     "$Windows.~BT / $Windows.~WS（升级预留目录）"),
]

# ----------------------------------------------------------------------------
# 社交软件专清（对应 social_scanner.rs；只纳入“安全缓存”子目录，
# 聊天记录数据库 .db 与接收到的文件按风险分别处理）
# ----------------------------------------------------------------------------
# (id, name, roots, subdirs, risk, detail)
_SOCIAL = [
    ("lc_soc_wechat_cache", "微信缓存（图片/视频/临时）",
     [_j(_UP, "Documents", "WeChat Files")],
     ["FileStorage/Image", "FileStorage/Video", "FileStorage/Cache",
      "FileStorage/Temp"], "低",
     "微信 FileStorage 下的图片/视频/缓存/临时（不含聊天记录）"),
    ("lc_soc_wechat_recv", "微信接收的文件",
     [_j(_UP, "Documents", "WeChat Files")],
     ["FileStorage/File"], "中",
     "微信接收的文件（可能含重要文档，谨慎清理）"),
    ("lc_soc_qq_cache", "QQ 缓存（图片/视频/临时）",
     [_j(_UP, "Documents", "Tencent Files")],
     ["Image", "Video", "Cache", "Temp"], "低",
     "QQ NT 缓存目录"),
    ("lc_soc_qq_recv", "QQ 接收的文件",
     [_j(_UP, "Documents", "Tencent Files")],
     ["FileRecv"], "中",
     "QQ 接收的文件（可能含重要文档，谨慎清理）"),
    ("lc_soc_wxwork_cache", "企业微信缓存（图片/视频/临时）",
     [_j(_UP, "Documents", "WXWork")],
     ["FileStorage/Image", "FileStorage/Video", "FileStorage/Cache",
      "FileStorage/Temp"], "低",
     "企业微信 FileStorage 缓存（不含聊天记录）"),
    ("lc_soc_wxwork_recv", "企业微信接收的文件",
     [_j(_UP, "Documents", "WXWork")],
     ["FileStorage/File"], "中",
     "企业微信接收的文件（谨慎清理）"),
    ("lc_soc_dingtalk_cache", "钉钉缓存",
     [_j(_RA, "DingTalk")],
     ["cache", "Cache", "logs"], "低",
     "钉钉缓存目录"),
    ("lc_soc_lark_cache", "飞书缓存",
     [_j(_LA, "Lark")],
     ["sdk_storage", "file_storage", "Cache"], "低",
     "飞书 LarkShell 缓存目录"),
    ("lc_soc_telegram", "Telegram 本地数据",
     [_j(_RA, "Telegram Desktop")],
     ["tdata"], "中",
     "Telegram 本地数据（含登录会话，清理后需重新登录，谨慎）"),
]

# ----------------------------------------------------------------------------
# AI 模型存储（对应 ai_models/*；用户主动下载的大体积数据，默认不勾选）
# ----------------------------------------------------------------------------
_AI = [
    ("lc_ai_huggingface", "HuggingFace 模型缓存",
     [_j(_UP, ".cache", "huggingface")], "高",
     "~/.cache/huggingface（模型/数据集缓存，体积大）"),
    ("lc_ai_ollama", "Ollama 模型",
     [_j(_UP, ".ollama")], "高",
     "~/.ollama（本地大模型，重新拉取耗时）"),
    ("lc_ai_lmstudio", "LM Studio 模型",
     [_j(_UP, ".lmstudio", "models")], "高",
     "~/.lmstudio/models（本地模型）"),
    ("lc_ai_comfyui", "ComfyUI 模型",
     [_j(_UP, "Documents", "ComfyUI", "models")], "高",
     "Documents\\ComfyUI\\models（AI 绘图模型）"),
]


def _build():
    items = []
    for _id, _name, _paths, _risk, _detail in _JUNK:
        items.append({
            "id": _id,
            "name": _name,
            "detail": _detail,
            "type": "folder",
            "paths": _paths,
            "risk": _risk,
        })
    for _id, _name, _roots, _subdirs, _risk, _detail in _SOCIAL:
        items.append({
            "id": _id,
            "name": _name,
            "detail": _detail,
            "type": "discover",
            "roots": _roots,
            "subdirs": _subdirs,
            "account_glob": "*",
            "risk": _risk,
        })
    for _id, _name, _paths, _risk, _detail in _AI:
        items.append({
            "id": _id,
            "name": _name,
            "detail": _detail,
            "type": "folder",
            "paths": _paths,
            "risk": _risk,
        })
    return items


LIGHTC_CLEAN_ITEMS = _build()
