Dim Shell, FSO, AppDir, Env
Set Shell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
AppDir = FSO.GetParentFolderName(WScript.ScriptFullName)
Shell.CurrentDirectory = AppDir
If WScript.Arguments.Count > 0 Then
    Set Env = Shell.Environment("PROCESS")
    Env("NO_AUTO_BROWSER") = "1"
End If
Shell.Run """" & AppDir & "\.venv\Scripts\pythonw.exe"" -m gitbridge.tray_app", 0, False
Set Shell = Nothing
