; Oneiro for Windows. Build with: ISCC installer\oneiro.iss   (after installer\build-payload.ps1)
;
; Per-user install, no administrator rights, no autostart. The owner's data lives in
; %USERPROFILE%\.oneiro and the Docker volume oneiro-graph-kb-v1; neither is an uninstall
; target: removing the program leaves the memory in place. Docker Desktop is a prerequisite:
; the memory substrate (OSTIS) runs in it, so setup refuses to continue until `docker info`
; answers. Setup loads the bundled graph image; uninstall stops and removes only the
; oneiro-graph container it may have started.

#define AppVersion "0.2.0"

[Setup]
AppName=Oneiro
AppVersion={#AppVersion}
AppPublisher=Oneiro
DefaultDirName={localappdata}\Programs\Oneiro
DefaultGroupName=Oneiro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=OneiroSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=Oneiro
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "payload\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Oneiro"; Filename: "{app}\start-oneiro.cmd"; WorkingDir: "{app}"; Comment: "Start Oneiro on this computer"

[UninstallRun]
; Stops our container gracefully (SIGINT saves the graph); the volume and the image stay.
Filename: "{cmd}"; Parameters: "/C docker stop --time 90 oneiro-graph >nul 2>&1 & docker rm oneiro-graph >nul 2>&1"; Flags: runhidden waituntilterminated; RunOnceId: "StopOneiroGraph"

[Code]
function DockerRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C docker info > nul 2>&1', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // The launcher also loads the image if this fails, so a failure here is not fatal.
    if not Exec(ExpandConstant('{cmd}'),
      '/C docker load -i "' + ExpandConstant('{app}\graph\oneiro-graph-0.2.0.tar') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      MsgBox('The memory image could not be loaded during setup. Oneiro will try again when it starts.',
        mbInformation, MB_OK);
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  while not DockerRunning() do
  begin
    // A silent run has no one to answer the question, so it stops instead of looping.
    if WizardSilent() then
    begin
      MsgBox('Oneiro needs Docker Desktop, which is not running. Start it and run the installer again.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if MsgBox('Oneiro keeps its memory in OSTIS, which runs in Docker Desktop.' + #13#10 + #13#10 +
      'Docker Desktop is not installed or not running. Start it, wait until it reports that it is running, ' +
      'then click Retry. Cancel stops the installation; nothing has been changed.',
      mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  end;
end;
