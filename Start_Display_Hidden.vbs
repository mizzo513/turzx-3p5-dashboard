Option Explicit
Dim fso, shell, folder, py, main
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
py = folder & "\.venv\Scripts\pythonw.exe"
main = folder & "\turzx_dashboard.py"
If Not fso.FileExists(py) Then
    MsgBox "Python environment is missing. Run START_HERE_Setup_and_Run.bat once.", vbExclamation, "TURZX"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run Chr(34) & py & Chr(34) & " " & Chr(34) & main & Chr(34), 0, False
