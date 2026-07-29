# -*- coding: utf-8 -*-
"""
本模块由 BleachBit 6.0.2 的 Windows 清理器配置（CleanerML）派生而来。

版权：BleachBit (C) 2008-2025 Andrew Ziem 等，以 GNU GPL v3 许可发布。
原始 XML 配置位于 bleachbit-6.0.2/cleaners/，仅抽取 command=delete/shred 的
文件/目录清理动作；注册表(winreg)、SQLite 归档(vacuum)、ini/json/xml 等非文件
动作与现有清理框架不匹配，已省略。路径中的 %VAR% 与 $$var$$ 占位符在导入时解析，
以保证跨用户/机器可移植。
"""
import os
import re


# BleachBit <var> 表（cleaner -> {变量名: [候选值...]}），仅保存被用到的清理器
_BB_VARS = {
    'brave': {
        'base': ['%LocalAppData%\\BraveSoftware\\Brave-Browser\\User Data', '$XDG_CONFIG_HOME/BraveSoftware/Brave-Browser', '~/snap/brave/current/.config/BraveSoftware/Brave-Browser'],
        'profile': ['%LocalAppData%\\BraveSoftware\\Brave-Browser\\User Data\\Default', '$XDG_CONFIG_HOME/BraveSoftware/Brave-Browser/Default', '~/snap/brave/current/.config/BraveSoftware/Brave-Browser/Default'],
    },
    'brave': {
        'base': ['%LocalAppData%\\BraveSoftware\\Brave-Browser\\User Data', '$XDG_CONFIG_HOME/BraveSoftware/Brave-Browser', '~/snap/brave/current/.config/BraveSoftware/Brave-Browser'],
        'profile': ['%LocalAppData%\\BraveSoftware\\Brave-Browser\\User Data\\Default', '$XDG_CONFIG_HOME/BraveSoftware/Brave-Browser/Default', '~/snap/brave/current/.config/BraveSoftware/Brave-Browser/Default'],
    },
    'chromium': {
        'base': ['%LocalAppData%\\Chromium\\User Data', '$XDG_CONFIG_HOME/chromium', '~/snap/chromium/common/chromium', '~/.var/app/org.chromium.Chromium/config/chromium', '~/.var/app/io.github.ungoogled_software.ungoogled_chromium/config/chromium', '$XDG_CONFIG_HOME/chromium', '$XDG_CONFIG_HOME/chromium'],
        'profile': ['%LocalAppData%\\Chromium\\User Data\\Default', '$XDG_CONFIG_HOME/chromium/Default', '~/snap/chromium/common/chromium/Default', '~/.var/app/org.chromium.Chromium/config/chromium/Default', '~/.var/app/io.github.ungoogled_software.ungoogled_chromium/config/chromium/Default', '$XDG_CONFIG_HOME/chromium/Default', '$XDG_CONFIG_HOME/chromium/Default'],
    },
    'chromium': {
        'base': ['%LocalAppData%\\Chromium\\User Data', '$XDG_CONFIG_HOME/chromium', '~/snap/chromium/common/chromium', '~/.var/app/org.chromium.Chromium/config/chromium', '~/.var/app/io.github.ungoogled_software.ungoogled_chromium/config/chromium', '$XDG_CONFIG_HOME/chromium', '$XDG_CONFIG_HOME/chromium'],
        'profile': ['%LocalAppData%\\Chromium\\User Data\\Default', '$XDG_CONFIG_HOME/chromium/Default', '~/snap/chromium/common/chromium/Default', '~/.var/app/org.chromium.Chromium/config/chromium/Default', '~/.var/app/io.github.ungoogled_software.ungoogled_chromium/config/chromium/Default', '$XDG_CONFIG_HOME/chromium/Default', '$XDG_CONFIG_HOME/chromium/Default'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'firefox': {
        'base': ['%AppData%\\Mozilla\\Firefox', '~/.mozilla/firefox', '~/snap/firefox/common/.mozilla/firefox', '~/.var/app/org.mozilla.firefox/.mozilla/firefox'],
        'profile': ['%AppData%\\Mozilla\\Firefox\\Profiles\\*', '~/.mozilla/firefox/*', '~/snap/firefox/common/.mozilla/firefox/*', '~/.var/app/org.mozilla.firefox/.mozilla/firefox/*'],
    },
    'google_chrome': {
        'base': ['%LocalAppData%\\Google\\Chrome\\User Data', '$XDG_CONFIG_HOME/google-chrome', '~/.var/app/com.google.Chrome/config/google-chrome/', '~/.var/app/com.google.ChromeDev/config/google-chrome/'],
        'profile': ['%LocalAppData%\\Google\\Chrome\\User Data\\Default', '%LocalAppData%\\Google\\Chrome\\User Data\\Profile *', '$XDG_CONFIG_HOME/google-chrome/Default', '$XDG_CONFIG_HOME/google-chrome/Profile *', '$XDG_CONFIG_HOME/google-chrome-beta/Default', '$XDG_CONFIG_HOME/google-chrome-beta/Profile *', '$XDG_CONFIG_HOME/google-chrome-unstable/Default', '$XDG_CONFIG_HOME/google-chrome-unstable/Profile *', '~/.var/app/com.google.Chrome/config/google-chrome/Default', '~/.var/app/com.google.Chrome/config/google-chrome/Profile *', '~/.var/app/com.google.ChromeDev/config/google-chrome/Default', '~/.var/app/com.google.ChromeDev/config/google-chrome/Profile *'],
    },
    'google_chrome': {
        'base': ['%LocalAppData%\\Google\\Chrome\\User Data', '$XDG_CONFIG_HOME/google-chrome', '~/.var/app/com.google.Chrome/config/google-chrome/', '~/.var/app/com.google.ChromeDev/config/google-chrome/'],
        'profile': ['%LocalAppData%\\Google\\Chrome\\User Data\\Default', '%LocalAppData%\\Google\\Chrome\\User Data\\Profile *', '$XDG_CONFIG_HOME/google-chrome/Default', '$XDG_CONFIG_HOME/google-chrome/Profile *', '$XDG_CONFIG_HOME/google-chrome-beta/Default', '$XDG_CONFIG_HOME/google-chrome-beta/Profile *', '$XDG_CONFIG_HOME/google-chrome-unstable/Default', '$XDG_CONFIG_HOME/google-chrome-unstable/Profile *', '~/.var/app/com.google.Chrome/config/google-chrome/Default', '~/.var/app/com.google.Chrome/config/google-chrome/Profile *', '~/.var/app/com.google.ChromeDev/config/google-chrome/Default', '~/.var/app/com.google.ChromeDev/config/google-chrome/Profile *'],
    },
    'internet_explorer': {
        'IELocalAppData': ['%LocalAppData%\\Microsoft\\Windows', '%UserProfile%\\Local Settings', '%UserProfile%\\Ustawienia lokalne'],
    },
    'internet_explorer': {
        'IELocalAppData': ['%LocalAppData%\\Microsoft\\Windows', '%UserProfile%\\Local Settings', '%UserProfile%\\Ustawienia lokalne'],
    },
    'internet_explorer': {
        'IELocalAppData': ['%LocalAppData%\\Microsoft\\Windows', '%UserProfile%\\Local Settings', '%UserProfile%\\Ustawienia lokalne'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'librewolf': {
        'base': ['%AppData%\\librewolf', '~/.librewolf'],
        'profile': ['%AppData%\\librewolf\\Profiles\\*', '~/.librewolf/*', '~/.config/librewolf/librewolf/*', '~/.var/app/io.gitlab.librewolf-community/.librewolf/*'],
    },
    'microsoft_edge': {
        'base': ['%LocalAppData%\\Microsoft\\Edge\\User Data', '$XDG_CONFIG_HOME/microsoft-edge-beta', '$XDG_CONFIG_HOME/microsoft-edge'],
        'profile': ['%LocalAppData%\\Microsoft\\Edge\\User Data\\Default', '%LocalAppData%\\Microsoft\\Edge\\User Data\\Profile *', '$XDG_CONFIG_HOME/microsoft-edge-beta/Default', '$XDG_CONFIG_HOME/microsoft-edge-beta/Profile *', '$XDG_CONFIG_HOME/microsoft-edge/Default', '$XDG_CONFIG_HOME/microsoft-edge/Profile *'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'opera': {
        'base': ['%AppData%\\Opera Software\\Opera*', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*'],
        'profile': ['%AppData%\\Opera Software\\Opera*', '%AppData%\\Opera Software\\Opera*\\Default', '$XDG_CONFIG_HOME/opera', '~/snap/opera*/*/.config/opera*', '~/snap/opera*/*/.config/opera*/Default'],
        'localapp': ['%LocalAppData%\\Opera Software\\Opera*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'palemoon': {
        'base': ['%AppData%\\moonchild productions\\value', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon', '~/.moonchild productions/pale moon'],
        'profile': ['%AppData%\\moonchild productions\\pale moon\\Profiles\\*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*', '~/.moonchild productions/pale moon/*'],
    },
    'teamviewer': {
        'Profile': ['%AppData%\\TeamViewer'],
    },
    'thunderbird': {
        'profile': ['~/.thunderbird/*', '~/.mozilla-thunderbird/*', '~/.thunderbird/Profiles/*', '~/.var/app/org.mozilla.Thunderbird/.thunderbird/*', '%AppData%\\Thunderbird\\Profiles\\*'],
    },
    'thunderbird': {
        'profile': ['~/.thunderbird/*', '~/.mozilla-thunderbird/*', '~/.thunderbird/Profiles/*', '~/.var/app/org.mozilla.Thunderbird/.thunderbird/*', '%AppData%\\Thunderbird\\Profiles\\*'],
    },
    'thunderbird': {
        'profile': ['~/.thunderbird/*', '~/.mozilla-thunderbird/*', '~/.thunderbird/Profiles/*', '~/.var/app/org.mozilla.Thunderbird/.thunderbird/*', '%AppData%\\Thunderbird\\Profiles\\*'],
    },
    'thunderbird': {
        'profile': ['~/.thunderbird/*', '~/.mozilla-thunderbird/*', '~/.thunderbird/Profiles/*', '~/.var/app/org.mozilla.Thunderbird/.thunderbird/*', '%AppData%\\Thunderbird\\Profiles\\*'],
    },
    'thunderbird': {
        'profile': ['~/.thunderbird/*', '~/.mozilla-thunderbird/*', '~/.thunderbird/Profiles/*', '~/.var/app/org.mozilla.Thunderbird/.thunderbird/*', '%AppData%\\Thunderbird\\Profiles\\*'],
    },
    'vuze': {
        'Profile': ['%AppData%\\Azureus', '~/.azureus'],
        'ProgramFiles': ['$$ProgramFiles$$\\Vuze'],
    },
    'vuze': {
        'Profile': ['%AppData%\\Azureus', '~/.azureus'],
        'ProgramFiles': ['$$ProgramFiles$$\\Vuze'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'waterfox': {
        'base': ['%AppData%\\Waterfox', '~/.waterfox', '~/.var/app/net.waterfox.waterfox/.waterfox'],
        'profile': ['%AppData%\\Waterfox\\Profiles\\*', '~/.waterfox/*', '~/.var/app/net.waterfox.waterfox/.waterfox/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zen': {
        'base': ['%AppData%\\Zen', '~/.zen', '~/snap/zen/common/.zen', '~/.var/app/app.zen_browser.zen/.zen', '~/.zen', '~/.zen'],
        'profile': ['%AppData%\\Zen\\Profiles\\*', '~/.zen/*', '~/snap/zen/common/.zen/*', '~/.var/app/app.zen_browser.zen/.zen/*', '~/.zen/*', '~/.zen/*'],
    },
    'zoom': {
        'base': ['%AppData%\\Zoom', '~/snap/zoom-client/*/.zoom', '~/.zoom'],
        'doc': ['%Documents%\\Zoom', '~/Documents/Zoom'],
    },
}


# 原始抽取结果：(cleaner_id, cleaner_label, option_id, option_label, risk, [(search, path)...])
# path 保留 BleachBit 占位符，导入时由 _bb_resolve() 解析。
_BB_RAW = [
    ('brave', 'Brave', 'cache', 'Cache', '低', [('file', '$$base$$/Safe Browsing Channel IDs-journal'), ('file', '$$profile$$/Network Persistent State'), ('walk.all', '$$base$$/component_crx_cache'), ('walk.all', '$$base$$/extensions_crx_cache'), ('walk.all', '$$base$$/GraphiteDawnCache'), ('walk.all', '$$base$$/GrShaderCache'), ('walk.all', '$$base$$/ShaderCache'), ('walk.all', '$$profile$$/Code Cache'), ('walk.all', '$$profile$$/GPUCache/'), ('walk.all', '$$profile$$/Pepper Data/Shockwave Flash/CacheWritableAdobeRoot/'), ('walk.all', '$$profile$$/Storage/ext/*/*def/GPUCache'), ('walk.all', '$XDG_CACHE_HOME/BraveSoftware/Brave-Browser/'), ('walk.all', '~/snap/brave/common/.cache/BraveSoftware/'), ('walk.all', '~/snap/brave/common/.cache/mesa_shader_cache'), ('glob', '$$base$$\\B*.tmp'), ('walk.all', '$$profile$$\\Default\\Application Cache\\'), ('walk.all', '$$profile$$\\Cache\\'), ('walk.all', '$$profile$$\\Media Cache\\')]),
    ('brave', 'Brave', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/databases/http*/'), ('walk.all', '$$profile$$/File System'), ('walk.all', '$$profile$$/IndexedDB'), ('walk.all', '$$profile$$/Local Storage'), ('walk.all', '$$profile$$/Pepper Data/Shockwave Flash/WritableRoot/'), ('walk.all', '$$profile$$/Service Worker'), ('walk.all', '$$profile$$/WebStorage'), ('file', '$$profile$$/QuotaManager'), ('file', '$$profile$$/QuotaManager-journal'), ('walk.all', '$$profile$$/Extension State'), ('walk.files', '$$profile$$/Session Storage/')]),
    ('chromium', 'Chromium', 'cache', 'Cache', '低', [('file', '$$base$$/Safe Browsing Channel IDs-journal'), ('walk.all', '$$base$$/component_crx_cache'), ('walk.all', '$$base$$/extensions_crx_cache'), ('walk.all', '$$base$$/GraphiteDawnCache'), ('walk.all', '$$base$$/GrShaderCache'), ('walk.all', '$$base$$/ShaderCache'), ('file', '$$profile$$/Network Persistent State'), ('file', '$$profile$$/Network/Network Persistent State'), ('walk.all', '$$profile$$/Code Cache'), ('walk.all', '$$profile$$/DawnCache/'), ('walk.all', '$$profile$$/GPUCache/'), ('walk.all', '$$profile$$/Storage/ext/*/*def/GPUCache'), ('walk.all', '$XDG_CACHE_HOME/chromium/'), ('walk.all', '$$profile$$/Cache'), ('walk.all', '~/.var/app/org.chromium.Chromium/cache/'), ('walk.all', '~/.var/app/io.github.ungoogled_software.ungoogled_chromium/cache/'), ('walk.all', '~/snap/chromium/common/.cache/mesa_shader_cache_db'), ('walk.all', '~/snap/chromium/common/.cache/mesa_shader_cache'), ('walk.all', '~/snap/chromium/common/chromium'), ('glob', '$$base$$\\B*.tmp'), ('walk.all', '$$profile$$\\Default\\Application Cache\\'), ('walk.all', '$$profile$$\\Cache\\'), ('walk.all', '$$profile$$\\Media Cache\\')]),
    ('chromium', 'Chromium', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/databases/http*/'), ('walk.all', '$$profile$$/File System'), ('walk.all', '$$profile$$/IndexedDB'), ('walk.all', '$$profile$$/Local Storage'), ('walk.all', '$$profile$$/Service Worker'), ('walk.all', '$$profile$$/WebStorage'), ('file', '$$profile$$/QuotaManager'), ('file', '$$profile$$/QuotaManager-journal'), ('walk.all', '$$profile$$/Extension State'), ('walk.files', '$$profile$$/Session Storage/')]),
    ('firefox', 'Firefox', 'backup', 'Backup files', '低', [('glob', '$$profile$$/bookmarkbackups/*.json'), ('glob', '$$profile$$/bookmarkbackups/*.jsonlz4')]),
    ('firefox', 'Firefox', 'cache', 'Cache', '低', [('walk.all', '~/.cache/mozilla/'), ('walk.all', '~/snap/firefox/common/.cache/'), ('walk.all', '~/.var/app/org.mozilla.firefox/cache/mozilla/'), ('walk.all', '%LocalAppData%\\Mozilla\\Firefox\\Profiles\\*\\cache2'), ('walk.all', '%LocalAppData%\\Mozilla\\Firefox\\Profiles\\*\\jumpListCache'), ('walk.all', '%LocalAppData%\\Mozilla\\Firefox\\Profiles\\*\\OfflineCache'), ('file', '$$profile$$/netpredictions.sqlite')]),
    ('firefox', 'Firefox', 'cookies', 'Cookies', '中', [('file', '$$profile$$/cookies.txt')]),
    ('firefox', 'Firefox', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/'), ('glob', '$$profile$$/minidumps/*.dmp')]),
    ('firefox', 'Firefox', 'forms', 'Form history', '中', [('file', '$$profile$$/formhistory.dat'), ('file', '$$profile$$/formhistory.sqlite')]),
    ('firefox', 'Firefox', 'passwords', 'Passwords', '高', [('file', '$$profile$$/signons.txt'), ('file', '$$profile$$/signons2.txt'), ('file', '$$profile$$/signons3.txt'), ('file', '$$profile$$/signons.sqlite'), ('file', '$$profile$$/logins.json')]),
    ('firefox', 'Firefox', 'session', 'Session', '中', [('file', '$$profile$$/sessionCheckpoints.json'), ('glob', '$$profile$$/sessionstore*.js*'), ('glob', '$$profile$$/sessionstore.bak*'), ('glob', '$$profile$$/sessionstore-backups/previous.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.bak*'), ('file', '$$profile$$/sessionstore-backups/previous.bak'), ('glob', '$$profile$$/sessionstore-backups/upgrade.js*-20*')]),
    ('firefox', 'Firefox', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/storage/default/http*'), ('glob', '$$profile$$/storage/default/http*'), ('file', '$$profile$$/webappsstore.sqlite'), ('file', '$$profile$$/storage.sqlite')]),
    ('firefox', 'Firefox', 'site_preferences', 'Site preferences', '低', [('file', '$$profile$$/content-prefs.sqlite'), ('file', '$$profile$$/permissions.sqlite')]),
    ('firefox', 'Firefox', 'url_history', 'URL history', '中', [('file', '$$profile$$/bounce-tracking-protection.sqlite'), ('file', '$$profile$$/SiteSecurityServiceState.txt'), ('file', '$$profile$$/SiteSecurityServiceState.bin'), ('walk.all', '%LocalAppData%\\Mozilla\\Firefox\\Profiles\\*\\thumbnails'), ('file', '$$profile$$/history.dat'), ('file', '$$profile$$/downloads.rdf'), ('file', '$$profile$$/downloads.sqlite'), ('file', '$$profile$$/AlternateServices.txt'), ('file', '$$profile$$/AlternateServices.bin')]),
    ('google_chrome', 'Google Chrome', 'cache', 'Cache', '低', [('file', '$$base$$/Safe Browsing Channel IDs-journal'), ('walk.all', '$$base$$/component_crx_cache'), ('walk.all', '$$base$$/extensions_crx_cache'), ('walk.all', '$$base$$/GraphiteDawnCache'), ('walk.all', '$$base$$/GrShaderCache'), ('walk.all', '$$base$$/ShaderCache'), ('file', '$$profile$$/Network Persistent State'), ('file', '$$profile$$/Network/Network Persistent State'), ('walk.all', '$$profile$$/GPUCache/'), ('walk.all', '$$profile$$/Pepper Data/Shockwave Flash/CacheWritableAdobeRoot/'), ('walk.all', '$$profile$$/Storage/ext/*/*def/GPUCache'), ('walk.files', '$XDG_CACHE_HOME/google-chrome/'), ('walk.files', '$XDG_CACHE_HOME/google-chrome-beta/'), ('walk.files', '$XDG_CACHE_HOME/google-chrome-unstable/'), ('walk.files', '~/.var/app/com.google.Chrome/cache/'), ('walk.files', '~/.var/app/com.google.ChromeDev/cache/'), ('glob', '$$base$$\\B*.tmp'), ('walk.all', '$$profile$$\\Default\\Application Cache\\'), ('walk.files', '$$profile$$\\Cache\\'), ('walk.files', '$$profile$$\\Code Cache\\'), ('walk.files', '$$profile$$\\Media Cache\\')]),
    ('google_chrome', 'Google Chrome', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/databases/http*/'), ('walk.all', '$$profile$$/File System'), ('walk.all', '$$profile$$/IndexedDB'), ('walk.all', '$$profile$$/Local Storage'), ('walk.all', '$$profile$$/Pepper Data/Shockwave Flash/WritableRoot/'), ('walk.all', '$$profile$$/Service Worker'), ('walk.all', '$$profile$$/WebStorage'), ('file', '$$profile$$/QuotaManager'), ('file', '$$profile$$/QuotaManager-journal'), ('walk.files', '$$profile$$/Session Storage/')]),
    ('internet_explorer', 'Internet Explorer', 'history', 'History', '中', [('walk.files', '$$IELocalAppData$$\\History\\'), ('walk.files', '%LocalAppData%\\Microsoft\\Internet Explorer\\Recovery\\Active\\'), ('walk.files', '%LocalAppData%\\Microsoft\\Internet Explorer\\Recovery\\Immersive\\Active\\'), ('walk.files', '%LocalAppData%\\Microsoft\\Internet Explorer\\Recovery\\Last Active\\'), ('walk.files', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\Microsoft\\CLR_v4.0\\UsageLogs\\'), ('walk.files', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\Microsoft\\CryptnetUrlCache\\'), ('walk.files', '%LocalAppData%\\Packages\\windows_ie_ac_*\\LocalState\\navigationHistory\\')]),
    ('internet_explorer', 'Internet Explorer', 'cache', 'Cache', '低', [('walk.all', '$$IELocalAppData$$\\Temporary Internet Files\\'), ('walk.all', '%AppData%\\Microsoft\\Internet Explorer\\UserData\\'), ('walk.all', '%AppData%\\Microsoft\\Windows\\IETldCache\\'), ('walk.all', '%AppData%\\Microsoft\\Windows\\IECompatCache\\'), ('walk.all', '%AppData%\\Microsoft\\Windows\\IECompatUACache\\'), ('walk.all', '%AppData%\\Microsoft\\Windows\\IECompat*Cache\\'), ('walk.all', '$$IELocalAppData$$\\INetCache\\'), ('walk.all', '$$IELocalAppData$$\\WebCache\\'), ('walk.top', '$$IELocalAppData$$\\WebCache.old\\'), ('walk.all', '%LocalAppDataLow%\\Microsoft\\Internet Explorer\\iconcache\\'), ('walk.all', '$$IELocalAppData$$\\AppCache\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\AppCache\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\IECompat*Cache\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\INet*\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\Microsoft\\Internet Explorer\\DOMStore\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\Microsoft\\Internet Explorer\\Emie*List\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\PRICache\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\Temp\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\LocalState\\Cache\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\TempState\\'), ('walk.all', '%WindowsSystem%\\config\\systemprofile\\AppData\\Local\\Microsoft\\Windows\\INetCache\\'), ('walk.all', '%LocalAppData%\\Microsoft\\Feeds Cache\\')]),
    ('internet_explorer', 'Internet Explorer', 'downloads', 'Download history', '中', [('walk.all', '%AppData%\\Microsoft\\Windows\\IEDownloadHistory\\'), ('walk.all', '%LocalAppData%\\Packages\\windows_ie_ac_*\\AC\\IEDownloadHistory\\')]),
    ('librewolf', 'LibreWolf', 'backup', 'Backup files', '低', [('glob', '$$profile$$/bookmarkbackups/*.json'), ('glob', '$$profile$$/bookmarkbackups/*.jsonlz4')]),
    ('librewolf', 'LibreWolf', 'cache', 'Cache', '低', [('walk.all', '~/.cache/librewolf/'), ('walk.all', '~/.var/app/io.gitlab.librewolf-community/cache'), ('walk.all', '%LocalAppData%\\librewolf\\Profiles\\*\\cache2'), ('walk.all', '%LocalAppData%\\librewolf\\Profiles\\*\\jumpListCache'), ('walk.all', '%LocalAppData%\\librewolf\\Profiles\\*\\OfflineCache'), ('file', '$$profile$$/netpredictions.sqlite')]),
    ('librewolf', 'LibreWolf', 'cookies', 'Cookies', '中', [('file', '$$profile$$/cookies.txt')]),
    ('librewolf', 'LibreWolf', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/'), ('glob', '$$profile$$/minidumps/*.dmp')]),
    ('librewolf', 'LibreWolf', 'forms', 'Form history', '中', [('file', '$$profile$$/formhistory.dat'), ('file', '$$profile$$/formhistory.sqlite')]),
    ('librewolf', 'LibreWolf', 'passwords', 'Passwords', '高', [('file', '$$profile$$/signons.txt'), ('file', '$$profile$$/signons2.txt'), ('file', '$$profile$$/signons3.txt'), ('file', '$$profile$$/signons.sqlite'), ('file', '$$profile$$/logins.json')]),
    ('librewolf', 'LibreWolf', 'session', 'Session', '中', [('file', '$$profile$$/sessionCheckpoints.json'), ('glob', '$$profile$$/sessionstore*.js*'), ('glob', '$$profile$$/sessionstore.bak*'), ('glob', '$$profile$$/sessionstore-backups/previous.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.bak*'), ('file', '$$profile$$/sessionstore-backups/previous.bak'), ('glob', '$$profile$$/sessionstore-backups/upgrade.js*-20*')]),
    ('librewolf', 'LibreWolf', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/storage/default/http*'), ('glob', '$$profile$$/storage/default/http*'), ('file', '$$profile$$/webappsstore.sqlite'), ('file', '$$profile$$/storage.sqlite')]),
    ('librewolf', 'LibreWolf', 'site_preferences', 'Site preferences', '低', [('file', '$$profile$$/content-prefs.sqlite'), ('file', '$$profile$$/permissions.sqlite')]),
    ('librewolf', 'LibreWolf', 'url_history', 'URL history', '中', [('file', '$$profile$$/bounce-tracking-protection.sqlite'), ('file', '$$profile$$/SiteSecurityServiceState.txt'), ('walk.all', '%LocalAppData%\\librewolf\\Profiles\\*\\thumbnails'), ('file', '$$profile$$/history.dat'), ('file', '$$profile$$/downloads.rdf'), ('file', '$$profile$$/downloads.sqlite'), ('file', '$$profile$$/AlternateServices.txt'), ('file', '$$profile$$/AlternateServices.bin')]),
    ('microsoft_edge', 'Microsoft Edge', 'cache', 'Cache', '低', [('walk.all', '$$base$$/component_crx_cache'), ('walk.all', '$$base$$/extensions_crx_cache'), ('walk.all', '$$base$$/GraphiteDawnCache'), ('walk.all', '$$base$$/ShaderCache'), ('walk.all', '$$base$$/GrShaderCache'), ('file', '$$profile$$/Network Persistent State'), ('file', '$$profile$$/Network/Network Persistent State'), ('walk.all', '$$profile$$/GPUCache/'), ('walk.all', '$$profile$$/Storage/ext/*/*def/GPUCache'), ('glob', '$$base$$\\B*.tmp'), ('walk.all', '$$profile$$\\Default\\Application Cache\\'), ('walk.all', '$$profile$$\\Cache\\'), ('walk.all', '$$profile$$\\Code Cache\\'), ('walk.all', '$$profile$$\\Media Cache\\')]),
    ('opera', 'Opera', 'cache', 'Cache', '低', [('walk.all', '$$base$$/component_crx_cache'), ('walk.all', '$$base$$/extensions_crx_cache'), ('walk.all', '$$base$$/GraphiteDawnCache'), ('walk.all', '$$base$$/GrShaderCache'), ('walk.all', '$$base$$/ShaderCache'), ('walk.all', '$$profile$$/Code Cache'), ('walk.all', '$$profile$$/GPUCache/'), ('file', '$$profile$$/Preferences.backup'), ('file', '$$profile$$/suggestions_cache.json'), ('walk.files', '$XDG_CACHE_HOME/opera/'), ('walk.all', '~/snap/opera/common/.cache/mesa_shader_cache_db'), ('walk.all', '~/snap/opera/common/.cache/mesa_shader_cache'), ('walk.all', '~/snap/opera/common/.cache/opera'), ('walk.all', '~/snap/opera-beta/common/.cache/opera-beta'), ('walk.all', '$$localapp$$\\Cache\\'), ('walk.all', '$$localapp$$\\Media Cache\\'), ('walk.files', '%LocalAppData%\\Opera\\Opera*\\cache\\'), ('walk.files', '%LocalAppData%\\Opera\\Opera*\\opcache\\'), ('walk.files', '%LocalAppData%\\Opera\\Opera*\\thumbnails\\'), ('walk.files', '%LocalAppData%\\Opera\\Opera*\\profile\\cache4\\'), ('walk.files', '%LocalAppData%\\Opera\\Opera*\\profile\\opcache\\'), ('walk.files', '~/.opera/cache/'), ('walk.files', '~/.opera/cache4/'), ('walk.files', '~/.opera/opcache/'), ('walk.files', '~/.opera/thumbnails/')]),
    ('opera', 'Opera', 'cookies', 'Cookies', '中', [('file', '$$profile$$/Cookies-journal'), ('file', '$$profile$$/Network/Cookies-journal'), ('file', '$$profile$$/Extension Cookies-journal'), ('glob', '%AppData%\\Opera\\Opera*\\cookies4.dat'), ('glob', '%AppData%\\Opera\\Opera*\\profile\\cookies4.dat'), ('file', '~/.opera/cookies4.dat')]),
    ('opera', 'Opera', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/')]),
    ('opera', 'Opera', 'history', 'History', '中', [('file', '$$profile$$/Favicons-journal'), ('file', '$$profile$$/DIPS'), ('file', '$$profile$$/History Provider Cache'), ('file', '$$profile$$/History-journal'), ('file', '$$profile$$/MediaDeviceSalts-journal'), ('file', '$$profile$$/MediaDeviceSalts'), ('file', '$$profile$$/Network Action Predictor-journal'), ('file', '$$profile$$/Network Action Predictor'), ('file', '$$profile$$/Origin Bound Certs-journal'), ('file', '$$profile$$/Reporting and NEL-journal'), ('file', '$$profile$$/Reporting and NEL'), ('file', '$$profile$$/Shortcuts-journal'), ('file', '$$profile$$/Shortcuts'), ('file', '$$profile$$/Visited Links'), ('walk.files', '$$profile$$\\JumpListIconsOld\\'), ('walk.files', '$$profile$$\\JumpListIcons\\'), ('walk.files', '$$profile$$\\Jump List Icons\\'), ('walk.files', '$$profile$$\\Jump List IconsOld\\'), ('glob', '%AppData%\\Opera\\Opera*\\download.dat'), ('file', '%AppData%\\Opera\\Opera\\profile\\download.dat'), ('file', '~/.opera/download.dat'), ('file', '%AppData%\\Opera\\Opera*\\search_field_history.dat'), ('file', '~/.opera/search_field_history.dat'), ('file', '%AppData%\\Opera\\Opera\\profile\\global.dat'), ('file', '%AppData%\\Opera\\Opera\\profile\\typed_history.xml'), ('file', '%AppData%\\Opera\\Opera\\profile\\vlink4.dat'), ('file', '%LocalAppData%\\Opera\\Opera\\profile\\vps\\????\\md.dat'), ('glob', '%AppData%\\Opera\\Opera*\\global_history.dat'), ('glob', '%AppData%\\Opera\\Opera*\\typed_history.xml'), ('glob', '%AppData%\\Opera\\Opera*\\vlink4.dat'), ('glob', '%LocalAppData%\\Opera\\Opera*\\icons\\*.gif'), ('glob', '%LocalAppData%\\Opera\\Opera*\\icons\\*.ico'), ('glob', '%LocalAppData%\\Opera\\Opera*\\icons\\*.idx'), ('glob', '%LocalAppData%\\Opera\\Opera*\\vps\\????\\md.dat'), ('file', '~/.opera/global.dat'), ('file', '~/.opera/global_history.dat'), ('file', '~/.opera/typed_history.xml'), ('file', '~/.opera/vlink4.dat'), ('glob', '~/.opera/icons/*.gif'), ('glob', '~/.opera/icons/*.ico'), ('glob', '~/.opera/icons/*.idx'), ('glob', '~/.opera/vps/????/md.dat')]),
    ('opera', 'Opera', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/databases/http*/'), ('walk.all', '$$profile$$/File System'), ('walk.all', '$$profile$$/IndexedDB'), ('walk.all', '$$profile$$/Local Storage'), ('walk.all', '$$profile$$/Service Worker'), ('walk.all', '$$profile$$/WebStorage'), ('file', '$$profile$$/QuotaManager'), ('file', '$$profile$$/QuotaManager-journal'), ('walk.all', '$$profile$$/Extension State'), ('walk.all', '$$profile$$/Session Storage'), ('walk.all', '%AppData%\\Opera\\Opera*\\pstorage\\'), ('walk.all', '~/.opera/pstorage/')]),
    ('opera', 'Opera', 'passwords', 'Passwords', '高', [('file', '$$profile$$/Login Data'), ('file', '$$profile$$/Login Data-journal'), ('file', '~/.opera/wand.dat')]),
    ('opera', 'Opera', 'session', 'Session', '中', [('file', '$$profile$$/Current Session'), ('file', '$$profile$$/Current Tabs'), ('file', '$$profile$$/Last Session'), ('file', '$$profile$$/Last Tabs'), ('walk.all', '$$profile$$/Sessions/'), ('glob', '%AppData%\\Opera\\Opera*\\sessions\\autosave.win'), ('glob', '%AppData%\\Opera\\Opera*\\sessions\\autosave.win.bak'), ('file', '~/.opera/sessions/autosave.win'), ('file', '~/.opera/sessions/autosave.win.bak')]),
    ('palemoon', 'Pale Moon', 'backup', 'Backup files', '低', [('glob', '$$profile$$/bookmarkbackups/*.json'), ('glob', '$$profile$$/bookmarkbackups/*.jsonlz4')]),
    ('palemoon', 'Pale Moon', 'cache', 'Cache', '低', [('walk.all', '~/.cache/moonchild productions/'), ('walk.all', '%LocalAppData%\\moonchild productions\\pale moon\\Profiles\\*\\cache2'), ('walk.all', '%LocalAppData%\\moonchild productions\\pale moon\\Profiles\\*\\jumpListCache'), ('walk.all', '%LocalAppData%\\moonchild productions\\pale moon\\Profiles\\*\\OfflineCache')]),
    ('palemoon', 'Pale Moon', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/'), ('glob', '$$profile$$/minidumps/*.dmp')]),
    ('palemoon', 'Pale Moon', 'forms', 'Form history', '中', [('file', '$$profile$$/formhistory.sqlite')]),
    ('palemoon', 'Pale Moon', 'passwords', 'Passwords', '高', [('file', '$$profile$$/logins.json')]),
    ('palemoon', 'Pale Moon', 'session', 'Session', '中', [('file', '$$profile$$/sessionCheckpoints.json'), ('glob', '$$profile$$/sessionstore*.js*'), ('glob', '$$profile$$/sessionstore.bak*'), ('glob', '$$profile$$/sessionstore-backups/previous.js*'), ('file', '$$profile$$/sessionstore-backups/recovery.js'), ('file', '$$profile$$/sessionstore-backups/previous.bak'), ('glob', '$$profile$$/sessionstore-backups/upgrade.js*-20*')]),
    ('palemoon', 'Pale Moon', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/storage/default/http*'), ('walk.all', '$$profile$$/storage/temporary/http*'), ('glob', '$$profile$$/storage/default/http*'), ('file', '$$profile$$/webappsstore.sqlite'), ('file', '$$profile$$/webappsstore.sqlite-shm'), ('file', '$$profile$$/webappsstore.sqlite-wal')]),
    ('palemoon', 'Pale Moon', 'site_preferences', 'Site preferences', '低', [('file', '$$profile$$/content-prefs.sqlite')]),
    ('palemoon', 'Pale Moon', 'url_history', 'URL history', '中', [('file', '$$profile$$/SiteSecurityServiceState.txt'), ('file', '$$profile$$/downloads.sqlite')]),
    ('silverlight', 'Silverlight', 'temp', 'Temporary files', '低', [('glob', '%Temp%\\Silverlight*.log')]),
    ('teamviewer', 'TeamViewer', 'logs', 'Logs', '低', [('glob', '$$Profile$$\\TeamViewer*_Logfile.log')]),
    ('thunderbird', 'Thunderbird', 'cache', 'Cache', '低', [('walk.all', '$$profile$$/Cache/'), ('walk.all', '~/.cache/thunderbird/'), ('walk.all', '~/.var/app/org.mozilla.Thunderbird/cache/thunderbird/'), ('walk.all', '%LocalAppData%\\Thunderbird\\Profiles\\*\\cache2\\'), ('walk.all', '%LocalAppData%\\Thunderbird\\Profiles\\*\\startupCache\\')]),
    ('thunderbird', 'Thunderbird', 'cookies', 'Cookies', '中', [('file', '$$profile$$/cookies.sqlite')]),
    ('thunderbird', 'Thunderbird', 'index', 'Index', '低', [('walk.files', '$$profile$$')]),
    ('thunderbird', 'Thunderbird', 'sessionjson', 'Session restore', '中', [('file', '$$profile$$/session.json')]),
    ('thunderbird', 'Thunderbird', 'passwords', 'Passwords', '高', [('file', '$$profile$$/signons.sqlite'), ('file', '$$profile$$/signons.txt'), ('file', '$$profile$$/signons3.txt')]),
    ('vuze', 'Vuze/Azureus', 'logs', 'Logs', '低', [('walk.all', '$$Profile$$\\logs\\'), ('glob', '$$Profile$$\\plugins\\*\\*.log'), ('glob', '$$Profile$$\\plugins\\*\\eventlog.txt'), ('file', '$$Profile$$\\update.log'), ('file', '$$Profile$$\\tracker.log'), ('glob', '$$ProgramFiles$$\\*.log'), ('walk.files', '$$ProgramFiles$$\\log\\'), ('glob', '$$ProgramFiles$$\\.install4j\\*.log')]),
    ('vuze', 'Vuze/Azureus', 'temp', 'Temporary files', '低', [('walk.files', '$$Profile$$\\tmp\\'), ('glob', '$$Profile$$\\torrents\\*.tmp'), ('glob', '$$Profile$$\\subs\\*.results.bad*'), ('walk.files', '$$Profile$$\\subs\\temp\\'), ('glob', '$$Profile$$\\torrents\\*.tmp._az'), ('glob', '$$Profile$$\\torrents\\*.torrent._az.saving'), ('walk.all', '$$Profile$$\\updates\\'), ('walk.all', '%Temp%\\AzureusInstall\\'), ('file', '%Temp%\\AzureusInstall\\'), ('glob', '%Temp%\\core_Azureus*')]),
    ('waterfox', 'Waterfox', 'backup', 'Backup files', '低', [('glob', '$$profile$$/bookmarkbackups/*.json'), ('glob', '$$profile$$/bookmarkbackups/*.jsonlz4')]),
    ('waterfox', 'Waterfox', 'cache', 'Cache', '低', [('walk.all', '~/.cache/waterfox/'), ('walk.all', '~/.var/app/net.waterfox.waterfox/cache'), ('walk.all', '%LocalAppData%\\Waterfox\\Profiles\\*\\cache2'), ('walk.all', '%LocalAppData%\\Waterfox\\Profiles\\*\\jumpListCache'), ('walk.all', '%LocalAppData%\\Waterfox\\Profiles\\*\\OfflineCache'), ('file', '$$profile$$/netpredictions.sqlite')]),
    ('waterfox', 'Waterfox', 'cookies', 'Cookies', '中', [('file', '$$profile$$/cookies.txt')]),
    ('waterfox', 'Waterfox', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/'), ('glob', '$$profile$$/minidumps/*.dmp')]),
    ('waterfox', 'Waterfox', 'forms', 'Form history', '中', [('file', '$$profile$$/formhistory.dat'), ('file', '$$profile$$/formhistory.sqlite')]),
    ('waterfox', 'Waterfox', 'passwords', 'Passwords', '高', [('file', '$$profile$$/signons.txt'), ('file', '$$profile$$/signons2.txt'), ('file', '$$profile$$/signons3.txt'), ('file', '$$profile$$/signons.sqlite'), ('file', '$$profile$$/logins.json')]),
    ('waterfox', 'Waterfox', 'session', 'Session', '中', [('glob', '$$profile$$/sessionstore*.js*'), ('glob', '$$profile$$/sessionstore.bak*'), ('walk.all', '$$profile$$/sessionstore-backups/')]),
    ('waterfox', 'Waterfox', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/storage/default/http*'), ('glob', '$$profile$$/storage/default/http*'), ('file', '$$profile$$/webappsstore.sqlite'), ('file', '$$profile$$/storage.sqlite')]),
    ('waterfox', 'Waterfox', 'site_preferences', 'Site preferences', '低', [('file', '$$profile$$/content-prefs.sqlite'), ('file', '$$profile$$/permissions.sqlite')]),
    ('waterfox', 'Waterfox', 'url_history', 'URL history', '中', [('file', '$$profile$$/bounce-tracking-protection.sqlite'), ('file', '$$profile$$/SiteSecurityServiceState.txt'), ('file', '$$profile$$/SiteSecurityServiceState.bin'), ('file', '$$profile$$/history.dat'), ('file', '$$profile$$/downloads.rdf'), ('file', '$$profile$$/downloads.sqlite'), ('file', '$$profile$$/AlternateServices.bin')]),
    ('windows_defender', 'Windows Defender', 'temp', 'Temporary files', '低', [('file', '%WinDir%\\Temp\\MpCmdRun.log'), ('file', '%WinDir%\\Temp\\MpSigStub.log'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\mpas-d.exe'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\mpas-fe.exe'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\mpas-fe_bd.exe'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Engine.exe'), ('glob', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Engine_Patch_*.exe'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Base.exe'), ('glob', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Base_Patch*.exe'), ('file', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Delta.exe'), ('glob', '%WinDir%\\SoftwareDistribution\\Download\\Install\\AS_Delta_Patch_*.exe'), ('walk.files', '%CommonAppData%\\Microsoft\\Windows Defender\\Definition Updates\\Updates\\')]),
    ('windows_defender', 'Windows Defender', 'logs', 'Logs', '低', [('file', '%CommonAppData%\\Microsoft\\Windows Defender\\Scans\\History\\Service\\Detections.log'), ('file', '%CommonAppData%\\Microsoft\\Windows Defender\\Scans\\History\\Service\\History.Log'), ('file', '%CommonAppData%\\Microsoft\\Windows Defender\\Scans\\History\\Service\\Unknown.Log'), ('glob', '%CommonAppData%\\Microsoft\\Windows Defender\\Support\\MPLog-*.log')]),
    ('windows_explorer', 'Windows Explorer', 'recent_documents', 'Recent documents list', '低', [('glob', '%USERPROFILE%\\Recent\\*.lnk'), ('glob', '%APPDATA%\\Microsoft\\Windows\\Recent\\*.lnk'), ('glob', '%APPDATA%\\Microsoft\\Windows\\Recent\\AutomaticDestinations\\*.automaticDestinations-ms'), ('glob', '%APPDATA%\\Microsoft\\Windows\\Recent\\CustomDestinations\\*customDestinations-ms')]),
    ('windows_explorer', 'Windows Explorer', 'thumbnails', 'Thumbnails', '低', [('glob', '%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache*.db')]),
    ('windows_media_player', 'Windows Media Player', 'cache', 'Cache', '低', [('walk.all', '%LocalAppData%\\Microsoft\\Media Player\\Cache*\\'), ('glob', '%LocalAppData%\\Microsoft\\Media Player\\Cache*\\'), ('walk.all', '%LocalAppData%\\Microsoft\\Media Player\\Grafikcache\\LocalMLS\\'), ('walk.all', '%LocalAppData%\\Microsoft\\Media Player\\Transcoded Files Cache\\'), ('file', '%Temp%\\wmsetup.log')]),
    ('winrar', 'WinRAR', 'temp', 'Temporary files', '低', [('walk.files', '%LocalAppData%\\VirtualStore\\Program Files*\\WinRAR\\'), ('walk.files', '%ProgramFiles%\\WinRAR\\')]),
    ('yahoo_messenger', 'Yahoo! Messenger', 'chat_logs', 'Chat logs', '低', [('glob', '%PROGRAMFILES%\\Yahoo!\\Messenger\\Profiles\\*\\Archive\\Messages\\*\\*.dat')]),
    ('zen', 'Zen', 'backup', 'Backup files', '低', [('glob', '$$profile$$/bookmarkbackups/*.json'), ('glob', '$$profile$$/bookmarkbackups/*.jsonlz4')]),
    ('zen', 'Zen', 'cache', 'Cache', '低', [('walk.all', '~/.cache/zen/'), ('walk.all', '~/snap/zen/common/.zen/mozilla/'), ('walk.all', '~/.var/app/app.zen_browser.zen/cache/zen/'), ('walk.all', '%LocalAppData%\\Zen\\Profiles\\*\\cache2'), ('walk.all', '%LocalAppData%\\Zen\\Profiles\\*\\jumpListCache'), ('walk.all', '%LocalAppData%\\Zen\\Profiles\\*\\OfflineCache'), ('file', '$$profile$$/netpredictions.sqlite')]),
    ('zen', 'Zen', 'cookies', 'Cookies', '中', [('file', '$$profile$$/cookies.txt')]),
    ('zen', 'Zen', 'crash_reports', 'Crash reports', '低', [('walk.all', '$$base$$/Crash Reports/'), ('glob', '$$profile$$/minidumps/*.dmp')]),
    ('zen', 'Zen', 'forms', 'Form history', '中', [('file', '$$profile$$/formhistory.dat'), ('file', '$$profile$$/formhistory.sqlite')]),
    ('zen', 'Zen', 'passwords', 'Passwords', '高', [('file', '$$profile$$/signons.txt'), ('file', '$$profile$$/signons2.txt'), ('file', '$$profile$$/signons3.txt'), ('file', '$$profile$$/signons.sqlite'), ('file', '$$profile$$/logins.json')]),
    ('zen', 'Zen', 'session', 'Session', '中', [('file', '$$profile$$/sessionCheckpoints.json'), ('glob', '$$profile$$/sessionstore*.js*'), ('glob', '$$profile$$/sessionstore.bak*'), ('glob', '$$profile$$/sessionstore-backups/previous.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.js*'), ('glob', '$$profile$$/sessionstore-backups/recovery.bak*'), ('file', '$$profile$$/sessionstore-backups/previous.bak'), ('glob', '$$profile$$/sessionstore-backups/upgrade.js*-20*')]),
    ('zen', 'Zen', 'site_data', 'Site data', '低', [('walk.all', '$$profile$$/storage/default/http*'), ('glob', '$$profile$$/storage/default/http*'), ('file', '$$profile$$/webappsstore.sqlite')]),
    ('zen', 'Zen', 'site_preferences', 'Site preferences', '低', [('file', '$$profile$$/content-prefs.sqlite')]),
    ('zen', 'Zen', 'url_history', 'URL history', '中', [('file', '$$profile$$/SiteSecurityServiceState.txt'), ('walk.all', '%LocalAppData%\\Zen\\Profiles\\*\\thumbnails'), ('file', '$$profile$$/history.dat'), ('file', '$$profile$$/downloads.rdf'), ('file', '$$profile$$/downloads.sqlite'), ('file', '$$profile$$/AlternateServices.txt')]),
    ('zoom', 'Zoom', 'recordings', 'Recordings', '低', [('glob', '~/Downloads/zoom_*.mp4'), ('walk.all', '$$doc$$')]),
]


def _bb_env(val):
    """解析 %VAR%（含 PROGRAMFILES(X86) 等）并做中文 locale 回退。"""
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
        user = os.environ.get('USERPROFILE', '')
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
    return re.sub(r'%([^%]+)%', repl, val)


def _bb_resolve_path(p, vars_):
    """解析 $$var$$ 与 %VAR%，以及 ${users}。"""
    def vrep(mm):
        name = mm.group(1)
        vals = vars_.get(name)
        if vals:
            for v in vals:
                rv = _bb_env(v)
                if os.path.isdir(rv):
                    return rv
            return _bb_env(vals[0])
        return mm.group(0)
    p = re.sub(r'\$\$([^$]+)\$\$', vrep, p)
    p = _bb_env(p)
    p = p.replace('${users}', os.environ.get('USERPROFILE', r'C:\Users'))
    return p


def _bb_classify(resolved):
    """把已解析路径分成文件夹目录与 glob 规格。"""
    folder_dirs, glob_specs = [], []
    for rp in resolved:
        if '*' in rp:
            idx = rp.index('*')
            b = rp[:idx].rstrip('/\\')
            pat = rp[idx:]
            glob_specs.append((b, pat))
        else:
            folder_dirs.append(rp.rstrip('/\\'))
    return folder_dirs, glob_specs


# 构建原生 CLEAN_ITEMS 条目
BLEACHBIT_CLEAN_ITEMS = []
for _c, _cl, _o, _ol, _r, _acts in _BB_RAW:
    _vars = _BB_VARS.get(_c, {})
    _resolved = [_bb_resolve_path(p, _vars) for _, p in _acts]
    _fdirs, _gspecs = _bb_classify(_resolved)
    _name = f'{_cl} - {_ol}'
    _detail = '; '.join(_resolved[:3])
    if len(_detail) > 120:
        _detail = _detail[:117] + '...'
    if _fdirs:
        BLEACHBIT_CLEAN_ITEMS.append({
            "id": f"bb_{_c}_{_o}",
            "name": _name,
            "detail": _detail,
            "type": "folder",
            "paths": _fdirs,
            "risk": _r,
        })
    # 按 base 合并 glob 规格；同一 option 可能跨多个 base，用序号区分 id 避免重复
    _gb = {}
    for _b, _pat in _gspecs:
        _gb.setdefault(_b, []).append(_pat)
    for _gi, (_b, _pats) in enumerate(_gb.items()):
        _suf = f'_{_gi}' if _gi > 0 else ''
        BLEACHBIT_CLEAN_ITEMS.append({
            "id": f"bb_{_c}_{_o}_g{_suf}",
            "name": _name + " (匹配文件)",
            "detail": _b,
            "type": "glob",
            "base": _b,
            "patterns": _pats,
            "risk": _r,
        })
