; 智筛 Agent · HSD 图号助手 —— Windows 安装包脚本
;
; 编译：ISCC.exe installer\HSD图号助手.iss
; 前置：先运行 build.ps1 生成 dist\v<版本>\HSD图号助手\
; 产物：交付\HSD图号助手-Setup-<版本>.exe
;
; 部署方式：
;   1. 默认按当前用户安装（不需要管理员），装到 %LOCALAPPDATA%\Programs\HSD图号助手。
;   2. 如需让这一批客户端走内网 AI 网关：把 gateway.json 放在 Setup.exe 同目录，
;      安装时会一并复制到程序目录（程序只从 exe 同目录读取 gateway.json）。
;   3. 支持静默安装：Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART

#define MyAppName "智筛 Agent · HSD 图号助手"
#define MyAppShortName "HSD图号助手"
#define MyAppVersion "1.9.0"
#define MyAppPublisher "DZH166"
#define MyAppURL "https://github.com/DZH166/Smart-Screening-Agent"
#define MyAppExeName "HSD图号助手.exe"
#define MySourcePath "..\dist\v" + MyAppVersion + "\HSD图号助手"

[Setup]
AppId={{A7C41E63-5B28-4F9D-9E31-6D2F8B0A4C57}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir=..\交付
OutputBaseFilename={#MyAppShortName}-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppShortName}
VersionInfoProductVersion={#MyAppVersion}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "autostart"; Description: "本机作为内网 AI 网关，开机自动运行（仅主机需要）"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#MySourcePath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 可选：把与 Setup.exe 放在一起的 gateway.json 复制到程序目录
Source: "{src}\gateway.json"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist ignoreversion

[InstallDelete]
; 升级时清掉上一版的冻结产物，避免旧 _internal 残留
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\源代码"
Type: filesandordirs; Name: "{app}\第三方组件说明"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 仅主机勾选本任务：开机后静默运行内网 AI 网关（不弹浏览器）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HSD内网网关"; ValueData: """{app}\{#MyAppExeName}"" --gateway --no-browser"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "现在启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只删安装目录内由安装器生成的文件；用户数据在 %LOCALAPPDATA%\HSD图片编号工具，不在此处
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\源代码"
Type: filesandordirs; Name: "{app}\第三方组件说明"
