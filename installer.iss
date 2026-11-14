[Setup]
AppName=Video Translator
AppVersion=1.0
DefaultDirName={autopf}\VideoTranslator
DefaultGroupName=Video Translator
OutputDir=installer_out
OutputBaseFilename=VideoTranslator-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\VideoTranslator\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Video Translator"; Filename: "{app}\VideoTranslator.exe"
Name: "{autodesktop}\Video Translator"; Filename: "{app}\VideoTranslator.exe"
