; RDrive — instalador Windows (Inno Setup 6+)
; Compilar: scripts\build\build_installer.ps1  (ou ISCC manual — ver docs\INSTALLER.md)
;
; Ficheiros de origem: dist\installer-staging\ (gerado pelo script de build)

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#ifndef MyAppVersionInfo
  #define MyAppVersionInfo "0.1.0.0"
#endif

#define MyAppName "RDrive"
#define MyAppPublisher "Miguel Silva Porto"
#define MyAppURL "https://github.com/MiguelSilvaPorto/RDrive"
#define MyAppExeName "Iniciar.bat"
#define SourceDir "..\dist\installer-staging"

[Setup]
AppId={{8F3D2A1B-4C5E-6D7F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
OutputDir=..\dist
OutputBaseFilename=RDriveSetup
SetupIconFile=rdrive.ico
UninstallDisplayIcon={app}\src\rdrive\assets\branding\rdrive.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
VersionInfoVersion={#MyAppVersionInfo}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} — instalador
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
ChangesAssociations=no
CloseApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
brazilianportuguese.ScopePageTitle=Modo de instalação
brazilianportuguese.ScopePageSubtitle=Escolha para quem o RDrive ficará disponível neste computador.
brazilianportuguese.ScopeUser=Apenas para o utilizador atual (recomendado)
brazilianportuguese.ScopeAll=Para todos os utilizadores (requer administrador)
brazilianportuguese.ScopeHintUser=Não pede UAC. Pasta predefinida: %LOCALAPPDATA%\Programs\RDrive. Dados da app em %LOCALAPPDATA%\RDrive.
brazilianportuguese.ScopeHintAll=Pedirá elevação. Pasta predefinida: Program Files. Todos os perfis Windows podem executar o atalho.
brazilianportuguese.DesktopShortcut=Criar atalho na Área de trabalho
brazilianportuguese.DesktopShortcutDesc=Atalho que executa o launcher Iniciar.bat (primeira execução cria .venv e dependências).
brazilianportuguese.LaunchAfter=Abrir o RDrive após concluir a instalação
brazilianportuguese.UninstallNote=Os dados em %LOCALAPPDATA%\RDrive (cofre, montagens) não são removidos automaticamente.

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "launchapp"; Description: "{cm:LaunchAfter}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked postinstall nowait

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: ".git\*;.venv\*;venv\*;__pycache__\*;*.pyc;logs\*.log"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; \
  IconFilename: "{app}\src\rdrive\assets\branding\rdrive.ico"; Comment: "Montar nuvens como unidades locais (rclone + WinFsp)"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; \
  IconFilename: "{app}\src\rdrive\assets\branding\rdrive.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent; Tasks: launchapp

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\logs"

[Code]
var
  ScopePage: TWizardPage;
  ScopeUserRadio: TNewRadioButton;
  ScopeAllRadio: TNewRadioButton;
  ScopeHintLabel: TNewStaticText;
  ScopeAllUsersWanted: Boolean;

procedure ScopeUpdateHint;
begin
  if ScopeAllRadio.Checked then
    ScopeHintLabel.Caption := ExpandConstant('{cm:ScopeHintAll}')
  else
    ScopeHintLabel.Caption := ExpandConstant('{cm:ScopeHintUser}');
end;

procedure ScopeRadioClick(Sender: TObject);
begin
  ScopeAllUsersWanted := ScopeAllRadio.Checked;
  ScopeUpdateHint;
  if ScopeAllRadio.Checked then
    WizardForm.DirEdit.Text := ExpandConstant('{commonpf}\{#MyAppName}')
  else
    WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\{#MyAppName}');
end;

procedure InitializeScopePage;
var
  TopPos: Integer;
begin
  ScopePage := CreateCustomPage(
    wpWelcome,
    ExpandConstant('{cm:ScopePageTitle}'),
    ExpandConstant('{cm:ScopePageSubtitle}'));

  TopPos := 0;

  ScopeUserRadio := TNewRadioButton.Create(ScopePage);
  ScopeUserRadio.Parent := ScopePage.Surface;
  ScopeUserRadio.Left := 0;
  ScopeUserRadio.Top := TopPos;
  ScopeUserRadio.Width := ScopePage.SurfaceWidth;
  ScopeUserRadio.Caption := ExpandConstant('{cm:ScopeUser}');
  ScopeUserRadio.Checked := True;
  ScopeUserRadio.OnClick := @ScopeRadioClick;
  TopPos := ScopeUserRadio.Top + ScopeUserRadio.Height + ScaleY(8);

  ScopeAllRadio := TNewRadioButton.Create(ScopePage);
  ScopeAllRadio.Parent := ScopePage.Surface;
  ScopeAllRadio.Left := 0;
  ScopeAllRadio.Top := TopPos;
  ScopeAllRadio.Width := ScopePage.SurfaceWidth;
  ScopeAllRadio.Caption := ExpandConstant('{cm:ScopeAll}');
  ScopeAllRadio.OnClick := @ScopeRadioClick;
  TopPos := ScopeAllRadio.Top + ScopeAllRadio.Height + ScaleY(12);

  ScopeHintLabel := TNewStaticText.Create(ScopePage);
  ScopeHintLabel.Parent := ScopePage.Surface;
  ScopeHintLabel.Left := 0;
  ScopeHintLabel.Top := TopPos;
  ScopeHintLabel.Width := ScopePage.SurfaceWidth;
  ScopeHintLabel.Height := ScaleY(64);
  ScopeHintLabel.AutoSize := False;
  ScopeHintLabel.WordWrap := True;

  if ExpandConstant('{param:ALLUSERS|}') <> '' then
  begin
    ScopeAllRadio.Checked := True;
    ScopeUserRadio.Checked := False;
  end;

  ScopeRadioClick(nil);
end;

function InitializeSetup(): Boolean;
begin
  ScopeAllUsersWanted := False;
  Result := True;
end;

procedure InitializeWizard;
begin
  InitializeScopePage;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
  Params: String;
begin
  Result := True;

  if CurPageID = ScopePage.ID then
  begin
    if ScopeAllRadio.Checked and not IsAdminInstallMode then
    begin
      Params := '/ALLUSERS';
      Params := Params + ' /DIR="' + WizardForm.DirEdit.Text + '"';
      if WizardIsTaskSelected('desktopicon') then
        Params := Params + ' /TASKS=desktopicon';
      if WizardIsTaskSelected('launchapp') then
        Params := Params + ' /TASKS=launchapp';

      if ShellExec('runas', ExpandConstant('{srcexe}'), Params, '', SW_SHOW, ewNoWait, ResultCode) then
      begin
        Result := False;
        WizardForm.Close;
      end
      else
        MsgBox('Não foi possível pedir elevação de administrador. Escolha instalação só para o utilizador atual ou execute o instalador como administrador.',
          mbError, MB_OK);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
    ScopeRadioClick(nil);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;
