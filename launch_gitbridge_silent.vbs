Dim Shell, FSO, AppDir
Set Shell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
AppDir = FSO.GetParentFolderName(WScript.ScriptFullName)
Shell.CurrentDirectory = AppDir
Shell.Run """" & AppDir & "\.venv\Scripts\pythonw.exe"" -m gitbridge.tray_app", 0, False
Set Shell = Nothing
