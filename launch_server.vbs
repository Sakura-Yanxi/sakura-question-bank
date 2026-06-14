Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = projectDir
shell.Run Chr(34) & fso.BuildPath(projectDir, "run_server.bat") & Chr(34) & " /hidden", 0, False
