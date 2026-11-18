Option Explicit
Dim fso, folder, file
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
Set file = fso.CreateTextFile(folder & "\STOP_REQUEST.flag", True)
file.WriteLine "stop"
file.Close
