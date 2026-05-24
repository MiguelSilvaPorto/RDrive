/**
 * RDrive Static UI — lógica única (sem módulos ES).
 * Visual: CSS. Estado: classList + dataset + textContent.
 */
(function () {
  "use strict";

  const THEME_KEY = "rdrive-ui-theme";
  const SHOW_HOME_TEST_TOOLS_KEY = "RDRIVE_SHOW_HOME_TEST_TOOLS";
  const SCAFFOLD_DISMISSED_KEY = "RDRIVE_SCAFFOLD_DISMISSED";
  const THEME_TRANSITION_MS = 500;
  const VIEW_HOME = "view-home";
  const VIEW_SETTINGS = "view-settings";
  const VIEW_ADD_DRIVE = "view-add-drive";

  /** Alinhado a ``AutoConnectService._AUTO_OAUTH_BACKENDS`` (rdrive.core.auto_connect). */
  const AUTO_CONNECT_SLUGS = new Set([
    "drive",
    "dropbox",
    "onedrive",
    "box",
    "pcloud",
    "mega",
  ]);

  const MOCK_REMOTE_SUGGESTIONS = {
    drive: "gdrive_pessoal",
    onedrive: "onedrive_pessoal",
    dropbox: "dropbox_pessoal",
    box: "box_pessoal",
    pcloud: "pcloud_pessoal",
    mega: "mega_pessoal",
    s3: "s3_pessoal",
    webdav: "webdav_pessoal",
    sftp: "sftp_pessoal",
    ftp: "ftp_pessoal",
    http: "http_pessoal",
    smb: "smb_pessoal",
  };

  const FALLBACK_SHARED_MOUNT_HINTS = {
    drive: {
      placeholder: "https://drive.google.com/drive/folders/1ABC…",
      help:
        "No Google Drive: abra a pasta partilhada no browser e copie o URL. O ID é o segmento após /folders/.",
      subpath_hint: "Opcional: subpasta dentro da raiz já limitada (ex.: Projetos/2024).",
    },
    dropbox: {
      placeholder: "Nome da pasta partilhada ou link dropbox.com/sh/…",
      help:
        "No Dropbox: use o nome exato da pasta em Partilhados convos ou cole o link de partilha.",
      subpath_hint: "Nome da pasta partilhada (recomendado) ou subpasta dentro dela.",
    },
    onedrive: {
      placeholder: "https://onedrive.live.com/…?id=…",
      help:
        "No OneDrive: copie o URL da pasta (parâmetro id=). Pode ser necessário adicionar a pasta a «Os meus ficheiros».",
      subpath_hint: "Opcional: subpasta dentro da raiz já limitada.",
    },
    default: {
      placeholder: "URL partilhado ou caminho no remote",
      help: "Limite a montagem com link/ID ou subcaminho dentro do remote rclone.",
      subpath_hint: "Caminho relativo no remote (ex.: Pasta/Subpasta).",
    },
  };

  const SLUG_GUIDANCE = {
    drive:
      "Google Drive: use «Configuração automática» para login no navegador. O remote é criado no rclone sem terminal.",
    dropbox:
      "Dropbox: configuração automática via OAuth no navegador — um clique e a conta fica ligada.",
    onedrive:
      "OneDrive: escolha pessoal ou empresarial abaixo, depois «Configuração automática». SharePoint avançado: terminal.",
    box: "Box: configuração automática via OAuth no navegador.",
    pcloud: "pCloud: configuração automática via OAuth no navegador.",
    mega: "Mega: configuração automática via OAuth no navegador.",
    terabox:
      "TeraBox (experimental): importe o cookie do Chrome (ndus=) — recomendado no Windows. " +
      "O navegador integrado costuma ficar em branco. O site bloqueia F12. Requer rclone não oficial (PR rclone#8508).",
    guided:
      "Preencha o formulário guiado — o RDrive configura o remote rclone sem terminal.",
    oauth_auto:
      "Este provedor suporta configuração automática: clique em «Configuração automática» e conclua o login no navegador. O assistente rclone no terminal continua disponível como alternativa.",
    s3: "S3 / compatíveis: preencha access key, secret e região no formulário guiado abaixo.",
    webdav: "WebDAV: informe URL, utilizador e senha no formulário guiado.",
    sftp: "SFTP: host, porta (22), utilizador e senha ou ficheiro/chave privada.",
    ftp: "FTP: host, porta (21), credenciais e FTPS explícito se o servidor exigir TLS.",
    http: "HTTP: informe a URL base (montagem só leitura).",
    smb: "SMB/CIFS: host NAS/PC, nome da partilha, domínio (opcional) e credenciais Windows.",
    manual:
      "Este provedor requer credenciais no assistente rclone. Abra «Modo técnico» ou «Configurar manualmente» e siga os passos no terminal.",
    default: "Selecione um provedor para ver o melhor método de autenticação.",
  };

  const GUIDED_FIELD_FALLBACK = {
    s3: [
      { name: "endpoint", label: "Endpoint (opcional)", type: "text", required: false },
      { name: "access_key", label: "Access Key", type: "text", required: true },
      { name: "secret", label: "Secret Key", type: "password", required: true },
      { name: "region", label: "Região", type: "text", required: true, placeholder: "us-east-1" },
      { name: "bucket", label: "Bucket (opcional)", type: "text", required: false },
    ],
    webdav: [
      { name: "url", label: "URL", type: "url", required: true },
      { name: "user", label: "Utilizador", type: "text", required: true },
      { name: "password", label: "Senha", type: "password", required: true },
    ],
    sftp: [
      { name: "host", label: "Host", type: "text", required: true },
      { name: "port", label: "Porta", type: "number", required: false, default: "22" },
      { name: "user", label: "Utilizador", type: "text", required: true },
      { name: "password", label: "Senha", type: "password", required: false },
      {
        name: "key_file",
        label: "Ficheiro de chave privada",
        type: "text",
        required: false,
        placeholder: "C:\\Users\\...\\id_rsa",
      },
      { name: "key", label: "Chave privada (PEM)", type: "textarea", required: false },
    ],
    ftp: [
      { name: "host", label: "Host", type: "text", required: true },
      { name: "port", label: "Porta", type: "number", required: false, default: "21" },
      { name: "user", label: "Utilizador", type: "text", required: true },
      { name: "password", label: "Senha", type: "password", required: true },
      {
        name: "explicit_tls",
        label: "FTPS explícito (TLS)",
        type: "checkbox",
        required: false,
        help: "Active se o servidor usar FTP sobre TLS (STARTTLS na porta 21).",
      },
    ],
    smb: [
      { name: "host", label: "Host / IP", type: "text", required: true },
      { name: "share", label: "Partilha", type: "text", required: true },
      { name: "domain", label: "Domínio (opcional)", type: "text", required: false },
      { name: "user", label: "Utilizador", type: "text", required: true },
      { name: "password", label: "Senha", type: "password", required: true },
    ],
    http: [{ name: "url", label: "URL", type: "url", required: true }],
    terabox: [
      {
        name: "confirmed_on_main",
        label: "Já estou na página principal (/main)",
        type: "checkbox",
        required: false,
        help:
          "Marque quando a URL do browser contiver /main (Meus ficheiros), após login.",
      },
      {
        name: "cookie",
        label: "Cookie de sessão",
        type: "password",
        required: true,
        help:
          "Preenchido após importar cookies.txt do Chrome ou captura automática. Deve conter ndus=.",
      },
    ],
  };

  const MOCK_PROVIDERS = [
    {
      slug: "terabox",
      label: "TeraBox (experimental)",
      icon_slug: "terabox",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      experimental: true,
      backend_available: false,
      manual_setup: true,
      guided_fields: GUIDED_FIELD_FALLBACK.terabox,
      description:
        "RDrive — uma das poucas apps a tentar montar TeraBox via rclone (build não oficial).",
    },
    {
      slug: "drive",
      label: "Google Drive",
      icon_slug: "drive",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "onedrive",
      label: "OneDrive",
      icon_slug: "onedrive",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "dropbox",
      label: "Dropbox",
      icon_slug: "dropbox",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "box",
      label: "Box",
      icon_slug: "box",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "pcloud",
      label: "pCloud",
      icon_slug: "pcloud",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "mega",
      label: "Mega",
      icon_slug: "mega",
      is_oauth: true,
      supports_auto_connect: true,
      manual_setup: true,
    },
    {
      slug: "s3",
      label: "Amazon S3",
      icon_slug: "s3",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
    {
      slug: "webdav",
      label: "WebDAV",
      icon_slug: "webdav",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
    {
      slug: "sftp",
      label: "SFTP",
      icon_slug: "sftp",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
    {
      slug: "ftp",
      label: "FTP",
      icon_slug: "ftp",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
    {
      slug: "http",
      label: "HTTP",
      icon_slug: "http",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
    {
      slug: "smb",
      label: "SMB / CIFS",
      icon_slug: "smb",
      is_oauth: false,
      supports_auto_connect: false,
      setup_mode: "guided",
      manual_setup: true,
    },
  ];

  const STATE_COPY = {
    connected: "Ligado",
    connecting: "A ligar…",
    disconnecting: "Desligando…",
    disconnected: "Desligado",
    error: "Erro",
  };

  const STATE_PILL_ANIMATED = {
    connecting: "A ligar",
    disconnecting: "Desligando",
  };

  const SWITCH_STATE = {
    connected: { checked: true, label: "Ligado", loading: false },
    connecting: { checked: false, label: "A ligar", loading: true },
    disconnecting: { checked: true, label: "Desligando", loading: true },
    disconnected: { checked: false, label: "Desligado", loading: false },
    error: { checked: false, label: "Desligado", loading: false },
  };

  const STARTUP_SWITCH_LABEL = {
    on: "Ligado",
    off: "Desligado",
  };

  const DUPLICATE_LABEL_MESSAGE = "Este nome já está em uso";

  /** Unidade exemplo para tuning de UI (browser / lista vazia). */
  const MOCK_DRIVES = [
    {
      id: "demo-scaffold-gdrive",
      provider: "drive",
      provider_label: "Google Drive",
      label: "t",
      remote_name: "demo_gdrive_t",
      mountpoint: "A:",
      status: "connected",
      connect_at_startup: true,
      integrity_level: "ok",
      _demo: true,
      _scaffold: true,
    },
  ];

  /** Presets adicionais para unidades fictícias (UI / tuning). */
  const DEMO_DRIVE_PRESETS = {
    google: {
      provider: "drive",
      provider_label: "Google Drive",
      label: "t",
      remote_name: "demo_gdrive_t",
      mountpoint: "A:",
      status: "connected",
      integrity_level: "ok",
      connect_at_startup: true,
    },
    onedrive: {
      provider: "onedrive",
      provider_label: "OneDrive",
      label: "Trabalho — Equipa",
      remote_name: "demo_onedrive_team",
      mountpoint: "H:",
      status: "disconnected",
      integrity_level: "warning",
      connect_at_startup: false,
    },
    dropbox: {
      provider: "dropbox",
      provider_label: "Dropbox",
      label: "Projetos Design",
      remote_name: "demo_dropbox_design",
      mountpoint: "I:",
      status: "connecting",
      integrity_level: "error",
      connect_at_startup: true,
    },
  };

  /** Valores por defeito alinhados a config_store.py */
  const DEFAULT_SETTINGS = {
    experimental_enabled: false,
    risk_acceptance_timestamp: null,
    enable_union_pool: false,
    enable_stripe: false,
    enable_preallocation: true,
    enable_auto_resume: true,
    retry_count: 10,
    retry_interval: 15,
    scan_interrupted_on_startup: true,
    register_startup: false,
    run_explorer_on_connect: false,
    use_custom_drive_icon: false,
    mount_as_local_drive: true,
    minimize_to_tray_on_close: true,
    confirm_close_with_mounts: true,
    http_proxy: "",
    auto_cleanup_safe: true,
    cleanup_interval_min: 30,
    enable_watchdog: true,
    watchdog_interval_sec: 10,
    watchdog_auto_reconnect: true,
    watchdog_hot_reload_on_code_change: true,
    watchdog_auto_restart_on_ui_change: false,
    watchdog_restart_on_code_change: true,
    watchdog_realtime_enabled: true,
    watchdog_realtime_interval_sec: 2,
    watchdog_event_history_limit: 100,
    watchdog_watch_project_root: true,
    watchdog_debug_log: false,
    watchdog_ide_compat_mode: false,
    watchdog_hot_reload_idle_sec: 5,
    watchdog_startup_grace_sec: 30,
    human_event_history_limit: 80,
    recovery_email: "",
    smtp_host: "",
    smtp_port: 465,
    smtp_user: "",
    smtp_password: "",
    smtp_from: "",
    vault_enabled: false,
    show_home_test_tools: false,
  };

  /** @type {{ command?: (name: string, args?: object) => Promise<unknown> } | null} */
  let bridge = null;
  let cachedSettings = { ...DEFAULT_SETTINGS };
  /** Snapshot JSON do formulário após load/apply/guardar (baseline para data-dirty). */
  let settingsFormSnapshot = "";

  let addDriveFormWired = false;

  /** Unidades reais do último snapshot da bridge. */
  let bridgeDrives = [];
  /** Mapa remote_name → nível de integridade (bridge). */
  let bridgeIntegrity = {};
  /** Unidades fictícias só em memória (não persistidas). */
  let demoDrives = [];
  /** Evita repor a unidade exemplo após o utilizador excluir. */
  let scaffoldDismissed = false;
  /** Bridge PyQt real (QWebChannel) — não confundir com mock/protótipo. */
  let bridgeIsLive = false;

  function loadScaffoldDismissed() {
    try {
      return localStorage.getItem(SCAFFOLD_DISMISSED_KEY) === "1";
    } catch {
      return false;
    }
  }

  function persistScaffoldDismissed() {
    scaffoldDismissed = true;
    try {
      localStorage.setItem(SCAFFOLD_DISMISSED_KEY, "1");
    } catch {
      /* ignore */
    }
  }

  const ADD_DRIVE_STEP_COUNT = 3;

  const CLOUD_SETUP_GUIDED_STEPS = [
    { id: "validating", label: "A validar provedor…" },
    { id: "suggesting", label: "A preparar sugestões…" },
    { id: "guided", label: "A configurar credenciais…" },
    { id: "remote", label: "A criar remote rclone…" },
    { id: "testing", label: "A testar ligação…" },
    { id: "saving", label: "A guardar unidade…" },
    { id: "done", label: "Concluído" },
  ];

  /** Etapas exibidas no painel do assistente automático (OAuth completo). */
  const CLOUD_SETUP_PROGRESS_STEPS = [
    { id: "validating", label: "A validar provedor…" },
    { id: "suggesting", label: "A preparar nome e letra…" },
    { id: "connecting", label: "A ligar conta…" },
    { id: "browser", label: "Login no browser" },
    { id: "remote", label: "A criar remote rclone…" },
    { id: "testing", label: "A testar ligação…" },
    { id: "saving", label: "A guardar unidade…" },
    { id: "done", label: "Concluído" },
  ];

  const CLOUD_SETUP_STAGE_ORDER = CLOUD_SETUP_PROGRESS_STEPS.map((s) => s.id);

  const addDriveState = {
    providers: [],
    selectedSlug: "",
    remoteAutoDirty: false,
    currentStep: 1,
    availableMountLetters: [],
    autoConnectInFlight: false,
    autoConnectAttempted: false,
    oauthConnected: false,
    onedriveType: "personal",
    assistantMode: true,
    cloudSetupInFlight: false,
    cloudSetupLastProvider: null,
    guidedProvider: null,
    guidedAnswersCache: {},
    teraboxLoginAutoOpened: false,
    teraboxBackendAvailable: null,
  };

  const TERABOX_LOGIN_URL = "https://www.terabox.com/login";
  const TERABOX_MAIN_URL = "https://www.terabox.com/main?category=all";
  const TERABOX_RCLONE_PR_URL = "https://github.com/rclone/rclone/pull/8508";
  const TERABOX_BACKEND_MISSING_PT =
    "O seu rclone não inclui TeraBox. Instale um build não oficial (PR rclone#8508) — veja README § Instalar rclone com TeraBox.";
  const TERABOX_LOGIN_TOAST_PT =
    "A abrir TeraBox no browser do sistema — use se o navegador integrado não estiver disponível";
  const TERABOX_EMBED_TOAST_PT =
    "Importar cookie TeraBox — escolha cookies.txt do Chrome ou cole ndus= (integrado é experimental)";
  const TERABOX_NDUS_WARN_PT =
    "O cookie deve conter «ndus=» — use «Importar cookie (Chrome)» ou Ajuda avançada";

  /** Alinhado a ``canonical_backend`` (remote_setup.py). */
  function canonicalProviderSlug(slug) {
    const key = String(slug || "")
      .trim()
      .toLowerCase()
      .replace(/-/g, "_");
    const aliases = {
      google_drive: "drive",
      googledrive: "drive",
      gdrive: "drive",
    };
    return aliases[key] || key;
  }

  function normalizeProvider(provider) {
    const slug = canonicalProviderSlug(provider.slug || "");
    const supports =
      provider.supports_auto_connect != null
        ? Boolean(provider.supports_auto_connect)
        : AUTO_CONNECT_SLUGS.has(slug);
    const setupMode =
      provider.setup_mode ||
      (supports
        ? "oauth"
        : GUIDED_FIELD_FALLBACK[slug] || slug === "terabox"
          ? "guided"
          : "manual");
    const guidedFields =
      Array.isArray(provider.guided_fields) && provider.guided_fields.length
        ? provider.guided_fields
        : GUIDED_FIELD_FALLBACK[slug] || [];
    return {
      ...provider,
      slug,
      supports_auto_connect: supports,
      is_oauth:
        provider.is_oauth != null ? Boolean(provider.is_oauth) : supports,
      manual_setup: provider.manual_setup !== false,
      setup_mode: setupMode,
      experimental: Boolean(provider.experimental),
      backend_available:
        provider.backend_available != null
          ? Boolean(provider.backend_available)
          : true,
      guided_fields: guidedFields,
      description: provider.description || "",
      docs_url: provider.docs_url || "",
      readme_section: provider.readme_section || "",
    };
  }

  function providerUsesGuidedSetup(provider) {
    if (!provider) return false;
    return provider.setup_mode === "guided";
  }

  function isTeraboxProvider(provider) {
    return canonicalProviderSlug(provider?.slug || "") === "terabox";
  }

  function teraboxCookieContainsNdus(value) {
    const text = String(value || "").trim();
    if (!text) return false;
    return /(?:^|;\s*)ndus=/i.test(text);
  }

  function isTeraboxBackendReady(provider) {
    if (!isTeraboxProvider(provider)) return true;
    if (provider && provider.backend_available === false) return false;
    if (addDriveState.teraboxBackendAvailable === false) return false;
    return addDriveState.teraboxBackendAvailable !== false;
  }

  function applyTeraboxBackendUi(provider) {
    if (!provider || !isTeraboxProvider(provider)) return;
    const els = getAddDriveEls();
    const ready = isTeraboxBackendReady(provider);
    if (els.teraboxBackendBanner) {
      els.teraboxBackendBanner.hidden = ready;
      const link = els.teraboxBackendBanner.querySelector(
        '[data-role="terabox-backend-pr-link"]'
      );
      if (link) link.href = TERABOX_RCLONE_PR_URL;
      const readmeBtn = els.teraboxBackendBanner.querySelector(
        '[data-role="terabox-backend-readme-btn"]'
      );
      if (readmeBtn) readmeBtn.dataset.provider = provider.slug;
    }
    updateTeraboxCookieFieldState();
  }

  async function refreshTeraboxBackendAvailability() {
    const provider = getSelectedAddDriveProvider();
    if (!provider || !isTeraboxProvider(provider)) {
      addDriveState.teraboxBackendAvailable = null;
      return null;
    }
    if (provider.backend_available === true) {
      addDriveState.teraboxBackendAvailable = true;
      applyTeraboxBackendUi(provider);
      return true;
    }
    if (!bridge || !bridge.command) {
      addDriveState.teraboxBackendAvailable = provider.backend_available !== false;
      applyTeraboxBackendUi(provider);
      return addDriveState.teraboxBackendAvailable;
    }
    try {
      const result = await bridge.command("checkTeraboxBackend", {});
      const available = Boolean(result && result.available);
      addDriveState.teraboxBackendAvailable = available;
      const idx = addDriveState.providers.findIndex((p) => p.slug === "terabox");
      if (idx >= 0) {
        addDriveState.providers[idx] = {
          ...addDriveState.providers[idx],
          backend_available: available,
        };
      }
      applyTeraboxBackendUi(getSelectedAddDriveProvider());
      return available;
    } catch (_err) {
      applyTeraboxBackendUi(provider);
      return addDriveState.teraboxBackendAvailable;
    }
  }

  function updateTeraboxCookieFieldState() {
    const confirmInput = document.querySelector('[data-guided-field="confirmed_on_main"]');
    const cookieInput = document.querySelector('[data-guided-field="cookie"]');
    const els = getAddDriveEls();
    const provider = getSelectedAddDriveProvider();
    const backendReady = isTeraboxBackendReady(provider);
    const onMain = Boolean(confirmInput && confirmInput.checked);
    if (cookieInput) {
      cookieInput.disabled = !onMain || !backendReady;
      if (cookieInput.disabled) cookieInput.setAttribute("aria-disabled", "true");
      else cookieInput.removeAttribute("aria-disabled");
    }
    if (els.guidedTestBtn) els.guidedTestBtn.disabled = !onMain || !backendReady;
    if (els.guidedSetupBtn) els.guidedSetupBtn.disabled = !onMain || !backendReady;
    updateTeraboxCookieWarn();
  }

  function updateTeraboxCookieWarn() {
    const els = getAddDriveEls();
    if (!els.teraboxCookieWarn) return;
    const cookieInput = document.querySelector('[data-guided-field="cookie"]');
    const value = cookieInput && !cookieInput.disabled ? String(cookieInput.value || "").trim() : "";
    if (!value) {
      els.teraboxCookieWarn.hidden = true;
      els.teraboxCookieWarn.textContent = "";
      return;
    }
    if (!teraboxCookieContainsNdus(value)) {
      els.teraboxCookieWarn.hidden = false;
      els.teraboxCookieWarn.textContent = TERABOX_NDUS_WARN_PT;
      return;
    }
    els.teraboxCookieWarn.hidden = true;
    els.teraboxCookieWarn.textContent = "";
  }

  function setTeraboxWizardVisible(show) {
    const els = getAddDriveEls();
    if (els.teraboxWizard) els.teraboxWizard.hidden = !show;
    if (els.teraboxAdvancedHelp) els.teraboxAdvancedHelp.hidden = !show;
  }

  function applyTeraboxCapturedCookie(cookie) {
    const value = String(cookie || "").trim();
    if (!value) return false;
    const input = document.querySelector('[data-guided-field="cookie"]');
    if (!input) return false;
    const confirm = document.querySelector('[data-guided-field="confirmed_on_main"]');
    if (confirm) confirm.checked = true;
    input.value = value;
    updateTeraboxCookieWarn();
    updateTeraboxCookieFieldState();
    const provider = getSelectedAddDriveProvider();
    if (provider) cacheGuidedAnswers(provider);
    return true;
  }

  async function openTeraboxEmbeddedBrowser(options = {}) {
    const manual = Boolean(options.manual);
    const autoTest = options.autoTest !== false && !manual;
    if (!bridge || !bridge.command) {
      setAddDriveFeedback(
        "Navegador integrado só na app RDrive (Iniciar.bat). Use «Abrir no browser do sistema» ou Ajuda avançada.",
        "warn"
      );
      return { ok: false, error: "bridge_unavailable", fallback: true };
    }
    try {
      if (!manual) {
        setAddDriveFeedback(
          "TeraBox: importe o cookie do Chrome (recomendado no Windows)…",
          "busy"
        );
      }
      const result = await bridge.command("openTeraboxEmbeddedBrowser", {});
      if (result && result.cancelled) {
        if (manual) setAddDriveFeedback("Captura de cookie TeraBox cancelada.", "warn");
        return result;
      }
      if (result && result.webengine_broken) {
        const installHint =
          (result && result.hint) ||
          "Instale ou repare: .venv\\Scripts\\python.exe -m pip install --upgrade \"PyQt6-WebEngine>=6.6.0\" " +
            "ou execute scripts\\verify_webengine.ps1";
        const err =
          (result && result.error) ||
          "PyQt6-WebEngine não instalado ou incompleto — navegador integrado em branco.";
        setAddDriveFeedback(`${err} ${installHint}`, "error");
        if (options.fallbackBrowser !== false) {
          return openTeraboxLoginBrowser({ manual: true });
        }
        return result;
      }
      if (result && result.ok && result.cookie) {
        applyTeraboxCapturedCookie(result.cookie);
        const hint =
          (result && result.hint) ||
          "Cookie capturado — sessão preenchida automaticamente.";
        setAddDriveFeedback(manual ? `TeraBox: ${hint}` : hint, "ok");
        if (autoTest) {
          const provider = getSelectedAddDriveProvider();
          if (provider && isTeraboxProvider(provider) && isTeraboxBackendReady(provider)) {
            await testGuidedConnection();
          }
        }
        return result;
      }
      const err =
        (result && result.error) || "Não foi possível capturar o cookie no navegador integrado.";
      if (result && result.fallback) {
        setAddDriveFeedback(
          `${err} Use o navegador integrado RDrive ou «Abrir no browser do sistema» e volte a capturar.`,
          "warn"
        );
        if (options.fallbackBrowser !== false) {
          return openTeraboxLoginBrowser({ manual: true });
        }
        return result || { ok: false, error: err, fallback: true };
      }
      setAddDriveFeedback(err, "error");
      return result || { ok: false, error: err };
    } catch (err) {
      const msg = (err && err.message) || "Não foi possível abrir o navegador TeraBox integrado.";
      setAddDriveFeedback(msg, "error");
      throw err;
    }
  }

  async function openTeraboxLoginBrowser(options = {}) {
    const manual = Boolean(options.manual);
    if (!bridge || !bridge.command) {
      if (typeof window !== "undefined" && window.open) {
        window.open(TERABOX_LOGIN_URL, "_blank", "noopener,noreferrer");
      }
      setAddDriveFeedback(TERABOX_LOGIN_TOAST_PT, "ok");
      return { ok: true, url: TERABOX_LOGIN_URL };
    }
    try {
      const result = await bridge.command("openTeraboxLogin", {});
      const hint =
        (result && result.hint) ||
        `Após login confirme URL com /main (ex.: ${TERABOX_MAIN_URL}).`;
      if (!manual) {
        setAddDriveFeedback(`${TERABOX_LOGIN_TOAST_PT}. ${hint}`, "ok");
      } else {
        setAddDriveFeedback(`TeraBox aberto — ${hint}`, "ok");
      }
      return result || { ok: true, url: TERABOX_LOGIN_URL, main_url: TERABOX_MAIN_URL };
    } catch (err) {
      const msg = (err && err.message) || "Não foi possível abrir o site TeraBox.";
      setAddDriveFeedback(msg, "error");
      throw err;
    }
  }

  function maybeAutoOpenTeraboxLogin(provider) {
    if (!isTeraboxProvider(provider) || addDriveState.teraboxLoginAutoOpened) {
      return;
    }
    if (isAddDriveAssistantMode() && addDriveState.currentStep === 1) {
      return;
    }
    const answers = collectGuidedAnswers(provider);
    if (answers.cookie && teraboxCookieContainsNdus(answers.cookie)) {
      return;
    }
    addDriveState.teraboxLoginAutoOpened = true;
    openTeraboxEmbeddedBrowser({ manual: false, autoTest: true, fallbackBrowser: false }).catch(
      () => {
        openTeraboxLoginBrowser({ manual: false }).catch(() => {});
      }
    );
  }

  function collectGuidedAnswers(provider) {
    const answers = {};
    if (!provider || !provider.guided_fields || !provider.guided_fields.length) {
      return answers;
    }
    provider.guided_fields.forEach((field) => {
      const name = field.name;
      if (!name) return;
      const input = document.querySelector(`[data-guided-field="${name}"]`);
      if (!input) return;
      const type = String(field.type || "text").toLowerCase();
      if (type === "checkbox") {
        answers[name] = Boolean(input.checked);
      } else {
        answers[name] = input.value != null ? String(input.value).trim() : "";
      }
    });
    return answers;
  }

  function cacheGuidedAnswers(provider) {
    if (!provider || !provider.slug) return;
    addDriveState.guidedAnswersCache[provider.slug] = collectGuidedAnswers(provider);
  }

  function restoreGuidedAnswers(provider) {
    if (!provider || !provider.slug) return;
    const cached = addDriveState.guidedAnswersCache[provider.slug];
    if (!cached) return;
    (provider.guided_fields || []).forEach((field) => {
      const name = field.name;
      if (!name || cached[name] == null) return;
      const input = document.querySelector(`[data-guided-field="${name}"]`);
      if (!input) return;
      const type = String(field.type || "text").toLowerCase();
      if (type === "checkbox") {
        input.checked = Boolean(cached[name]);
      } else {
        input.value = String(cached[name]);
      }
    });
  }

  function guidedAnswersComplete(provider) {
    if (!providerUsesGuidedSetup(provider)) return true;
    const answers = collectGuidedAnswers(provider);
    const fields = provider.guided_fields || [];
    for (const field of fields) {
      if (!field.required) continue;
      const type = String(field.type || "text").toLowerCase();
      if (type === "checkbox") continue;
      if (!answers[field.name]) return false;
    }
    const slug = canonicalProviderSlug(provider.slug || "");
    if (slug === "sftp") {
      if (!answers.password && !answers.key && !answers.key_file) return false;
    }
    if (slug === "terabox") {
      if (!answers.confirmed_on_main) return false;
      if (!answers.cookie || !teraboxCookieContainsNdus(answers.cookie)) return false;
    }
    return true;
  }

  function renderGuidedSetupPanel(provider) {
    const els = getAddDriveEls();
    if (!els.guidedPanel || !els.guidedFields) return;
    if (!providerUsesGuidedSetup(provider)) {
      els.guidedPanel.hidden = true;
      els.guidedFields.innerHTML = "";
      setTeraboxWizardVisible(false);
      if (els.teraboxBackendBanner) els.teraboxBackendBanner.hidden = true;
      if (els.teraboxCookieWarn) {
        els.teraboxCookieWarn.hidden = true;
        els.teraboxCookieWarn.textContent = "";
      }
      if (els.guidedTechnicalBtn) els.guidedTechnicalBtn.hidden = true;
      if (els.guidedDocs) els.guidedDocs.hidden = true;
      if (els.guidedTestStatus) {
        els.guidedTestStatus.hidden = true;
        els.guidedTestStatus.textContent = "";
      }
      return;
    }
    els.guidedPanel.hidden = false;
    setTeraboxWizardVisible(isTeraboxProvider(provider));
    if (els.guidedTechnicalBtn) els.guidedTechnicalBtn.hidden = false;
    let hint =
      provider.description ||
      SLUG_GUIDANCE[provider.slug] ||
      SLUG_GUIDANCE.guided;
    if (isTeraboxProvider(provider) && provider.backend_available === false) {
      hint =
        "Requer rclone não oficial com backend «terabox» (PR rclone#8508). " +
        "Sem esse build, «Testar ligação» e «Ligar e guardar» ficam desativados — veja o aviso acima.";
    }
    if (els.guidedHint) els.guidedHint.textContent = hint;
    if (els.guidedDocs) {
      els.guidedDocs.hidden = false;
      const readmeLabel = provider.readme_section
        ? `README § ${provider.readme_section.replace(/^agente-/, "")}`
        : "README";
      if (els.guidedReadmeLink) {
        els.guidedReadmeLink.textContent = readmeLabel;
        els.guidedReadmeLink.dataset.provider = provider.slug;
      }
      if (els.guidedRcloneLink) {
        els.guidedRcloneLink.textContent = "Documentação rclone";
        els.guidedRcloneLink.dataset.provider = provider.slug;
      }
    }
    if (els.guidedTestStatus) {
      els.guidedTestStatus.hidden = true;
      els.guidedTestStatus.textContent = "";
      delete els.guidedTestStatus.dataset.tone;
    }
    els.guidedFields.innerHTML = "";
    (provider.guided_fields || []).forEach((field) => {
      const type = String(field.type || "text").toLowerCase();
      let wrap;
      let input;
      if (type === "checkbox") {
        wrap = document.createElement("label");
        wrap.className = "field-check field-check-compact";
        input = document.createElement("input");
        input.type = "checkbox";
        input.id = `guided-${field.name}`;
        input.dataset.guidedField = field.name;
        if (field.default) input.checked = Boolean(field.default);
        wrap.appendChild(input);
        const title = document.createElement("span");
        title.textContent = field.label || field.name || "";
        wrap.appendChild(title);
      } else {
        wrap = document.createElement("label");
        wrap.className = "field-text field-compact";
        const title = document.createElement("span");
        title.textContent = field.label || field.name || "";
        wrap.appendChild(title);
        if (type === "textarea") {
          input = document.createElement("textarea");
          input.rows = 4;
        } else {
          input = document.createElement("input");
          input.type =
            type === "password" ? "password" : type === "number" ? "number" : "text";
        }
        input.id = `guided-${field.name}`;
        input.dataset.guidedField = field.name;
        input.autocomplete = "off";
        input.spellcheck = false;
        if (field.placeholder) input.placeholder = field.placeholder;
        if (field.default != null && field.default !== false) input.value = String(field.default);
        wrap.appendChild(input);
      }
      if (field.help) {
        const help = document.createElement("p");
        help.className = "field-hint";
        help.textContent = field.help;
        wrap.appendChild(help);
      }
      if (isTeraboxProvider(provider) && field.name === "cookie") {
        const row = document.createElement("div");
        row.className = "add-drive-terabox-cookie-row";
        row.appendChild(wrap);
        const actions = document.createElement("div");
        actions.className = "add-drive-terabox-login-actions";
        const embedBtn = document.createElement("button");
        embedBtn.type = "button";
        embedBtn.className = "tbtn primary";
        embedBtn.textContent = "Importar cookie (Chrome)";
        embedBtn.dataset.action = "open-terabox-embedded-browser";
        embedBtn.title = TERABOX_EMBED_TOAST_PT;
        actions.appendChild(embedBtn);
        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "tbtn ghost";
        openBtn.textContent = "Abrir no browser do sistema";
        openBtn.dataset.action = "open-terabox-login";
        actions.appendChild(openBtn);
        row.appendChild(actions);
        els.guidedFields.appendChild(row);
      } else {
        els.guidedFields.appendChild(wrap);
      }
      if (isTeraboxProvider(provider) && field.name === "confirmed_on_main") {
        input.addEventListener("change", () => updateTeraboxCookieFieldState());
      }
      if (isTeraboxProvider(provider) && field.name === "cookie") {
        input.addEventListener("input", () => updateTeraboxCookieWarn());
        input.addEventListener("blur", () => updateTeraboxCookieWarn());
      }
    });
    restoreGuidedAnswers(provider);
    addDriveState.guidedProvider = provider.slug;
    if (isTeraboxProvider(provider)) {
      applyTeraboxBackendUi(provider);
      updateTeraboxCookieFieldState();
      maybeAutoOpenTeraboxLogin(provider);
      void refreshTeraboxBackendAvailability();
    } else if (els.teraboxCookieWarn) {
      els.teraboxCookieWarn.hidden = true;
      els.teraboxCookieWarn.textContent = "";
    }
  }

  function getSelectedAddDriveProvider() {
    if (!addDriveState.selectedSlug) return null;
    return (
      addDriveState.providers.find((p) => p.slug === addDriveState.selectedSlug) ||
      null
    );
  }

  function providerSupportsAutoConnect(provider) {
    if (!provider) return false;
    if (provider.supports_auto_connect != null) {
      return Boolean(provider.supports_auto_connect);
    }
    return AUTO_CONNECT_SLUGS.has(String(provider.slug || "").toLowerCase());
  }

  /** Ordem preferida na grelha «Adicionar drive» (dentro de cada grupo auto/manual). */
  const ADD_DRIVE_PROVIDER_PRIORITY = [
    "terabox",
    "drive",
    "onedrive",
    "dropbox",
    "box",
    "pcloud",
    "mega",
  ];

  function addDriveProviderPriorityIndex(provider) {
    const slug = canonicalProviderSlug(provider.slug || "");
    const idx = ADD_DRIVE_PROVIDER_PRIORITY.indexOf(slug);
    return idx >= 0 ? idx : ADD_DRIVE_PROVIDER_PRIORITY.length;
  }

  function compareAddDriveProviders(a, b) {
    const autoA = providerSupportsAutoConnect(a) ? 0 : 1;
    const autoB = providerSupportsAutoConnect(b) ? 0 : 1;
    if (autoA !== autoB) return autoA - autoB;

    const priA = addDriveProviderPriorityIndex(a);
    const priB = addDriveProviderPriorityIndex(b);
    if (priA !== priB) return priA - priB;

    const labelA = (a.label || a.slug || "").toLowerCase();
    const labelB = (b.label || b.slug || "").toLowerCase();
    return labelA.localeCompare(labelB, undefined, { sensitivity: "base" });
  }

  function sortAddDriveProviders(providers) {
    return providers.slice().sort(compareAddDriveProviders);
  }

  let activityOpen = false;
  /** @type {{ message: string, level?: string }[]} */
  let activityEntries = [];

  // --- ATIVIDADE ---

  function getActivityLimit() {
    const raw = cachedSettings.human_event_history_limit;
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n)) return 80;
    return Math.max(20, Math.min(500, n));
  }

  function trimActivityEntries() {
    const limit = getActivityLimit();
    if (activityEntries.length > limit) {
      activityEntries = activityEntries.slice(0, limit);
    }
  }

  function renderActivityPanel() {
    const panel = document.getElementById("activity-panel");
    const list = document.getElementById("activity-list");
    if (!panel) return;
    panel.hidden = !activityOpen;
    document.body.dataset.activityOpen = activityOpen ? "true" : "false";
    if (!list) return;
    list.replaceChildren();
    activityEntries.forEach((entry) => {
      const li = document.createElement("li");
      li.textContent = entry.message || "";
      if (entry.level === "warn") li.classList.add("level-warn");
      if (entry.level === "error") li.classList.add("level-error");
      list.appendChild(li);
    });
  }

  function setActivityOpen(open) {
    activityOpen = Boolean(open);
    const btn = document.getElementById("toolbar-activity-btn");
    if (btn) btn.classList.toggle("is-active", activityOpen);
    renderActivityPanel();
  }

  function prependActivityEntry(entry) {
    if (!entry || !entry.message) return;
    activityEntries = [entry, ...activityEntries];
    trimActivityEntries();
    renderActivityPanel();
  }

  function replaceActivityEntries(entries) {
    activityEntries = Array.isArray(entries) ? entries.filter((e) => e && e.message) : [];
    trimActivityEntries();
    renderActivityPanel();
  }

  async function refreshLogTail() {
    const view = document.getElementById("log-tail-view");
    const limitInput = document.getElementById("log-tail-limit");
    const limit = limitInput ? parseInt(limitInput.value, 10) : 200;
    if (!bridge || !bridge.command) {
      if (view) {
        view.textContent =
          "Disponível apenas com o RDrive em execução (DevStatic-Live.bat ou Iniciar.bat).";
      }
      return;
    }
    if (view) view.textContent = "A carregar rdrive.log…";
    try {
      const result = await bridge.command("getLogTail", {
        log: "rdrive",
        limit: Number.isFinite(limit) ? limit : 200,
      });
      const lines = result && Array.isArray(result.lines) ? result.lines : [];
      const path = result && result.path ? result.path : "logs/rdrive.log";
      if (view) {
        view.textContent = lines.length
          ? lines.join("\n")
          : `[vazio] ${path}\nExecute Iniciar.bat se a app ainda não arrancou.`;
      }
    } catch (err) {
      if (view) {
        view.textContent = err && err.message ? err.message : "Falha ao ler rdrive.log.";
      }
    }
  }

  async function openLogsFolder() {
    if (!bridge || !bridge.command) {
      setSettingsFeedback("Abrir pasta: disponível apenas com o RDrive em execução.", "error");
      return;
    }
    try {
      await bridge.command("openLogsFolder", {});
    } catch (err) {
      setSettingsFeedback(err && err.message ? err.message : "Não foi possível abrir a pasta.", "error");
    }
  }

  // --- BRIDGE ---

  function connectBridge(callbacks) {
    const { onState, onEvent, onError } = callbacks;

    if (typeof QWebChannel === "undefined") {
      return Promise.resolve(createMockBridge(onState, onEvent));
    }

    return new Promise((resolve, reject) => {
      new QWebChannel(qt.webChannelTransport, (channel) => {
        const rdrive = channel.objects.rdrive;
        if (!rdrive) {
          reject(new Error("Objeto rdrive não exposto na bridge"));
          return;
        }

        rdrive.event.connect((payloadJson) => {
          try {
            const evt = JSON.parse(payloadJson);
            if (onEvent) onEvent(evt);
          } catch (err) {
            if (onError) onError(err);
          }
        });

        rdrive.state.connect((payloadJson) => {
          try {
            const snapshot = JSON.parse(payloadJson);
            if (onState) onState(snapshot);
          } catch (err) {
            if (onError) onError(err);
          }
        });

        const command = (name, args = {}) =>
          new Promise((res, rej) => {
            rdrive.dispatch(JSON.stringify({ name, args }), (resultJson) => {
              try {
                const result = resultJson ? JSON.parse(resultJson) : null;
                if (result && result.ok === false) {
                  rej(new Error(result.error || "Falha no comando"));
                  return;
                }
                const data = result ? result.data : null;
                if (data && typeof data === "object" && data.ok === false) {
                  rej(new Error(data.error || "Falha no comando"));
                  return;
                }
                res(data);
              } catch (err) {
                rej(err);
              }
            });
          });

        resolve({ command, raw: rdrive });
      });
    });
  }

  function createMockBridge(onState, onEvent) {
    const mockVaultPreview =
      typeof URLSearchParams !== "undefined" &&
      new URLSearchParams(window.location.search).get("vaultUnlock") === "1";
    const snapshot = {
      statusText: "Modo protótipo (sem PyQt)",
      tone: "ok",
      busy: false,
      drives: [],
      integrity: {},
      settings: { ...DEFAULT_SETTINGS },
      activeUser: "utilizador@local",
      vaultUnlock: mockVaultPreview
        ? {
            required: true,
            isSetup: false,
            recentUsers: ["utilizador@exemplo.com"],
            activeEmail: "utilizador@exemplo.com",
            hasLegacyEnc: false,
          }
        : { required: false },
    };
    const mockSettings = { ...DEFAULT_SETTINGS };
    const storedShowHomeTestTools = readShowHomeTestToolsFromStorage();
    if (storedShowHomeTestTools !== null) {
      mockSettings.show_home_test_tools = storedShowHomeTestTools;
    }
    snapshot.settings = { ...mockSettings };
    if (onState) {
      setTimeout(() => onState(snapshot), 0);
    }

    return {
      command(name, args = {}) {
        if (name === "ping") {
          return Promise.resolve({
            ok: true,
            message: "pong",
            at: new Date().toISOString(),
            bridgeApiVersion: 2,
            features: { cloudSetupAgent: true, sharedMountHints: true },
          });
        }
        if (name === "getSettings") {
          return Promise.resolve({ settings: { ...mockSettings } });
        }
        if (name === "saveSettings") {
          Object.assign(mockSettings, args);
          if (Object.prototype.hasOwnProperty.call(args, "show_home_test_tools")) {
            writeShowHomeTestToolsToStorage(Boolean(args.show_home_test_tools));
          }
          if (onState) {
            onState({
              settings: { ...mockSettings },
              statusText: "Definições guardadas (mock)",
              tone: "ok",
            });
          }
          return Promise.resolve({ ok: true });
        }
        if (name === "listProviders") {
          return Promise.resolve({
            providers: MOCK_PROVIDERS.map((p) => normalizeProvider({ ...p })),
          });
        }
        if (name === "listRemotes") {
          return Promise.resolve({ remotes: [] });
        }
        if (name === "suggestRemote") {
          const provider = String(args.provider || "drive").toLowerCase();
          const label = String(args.label || "").trim();
          if (label) {
            const base = label
              .toLowerCase()
              .normalize("NFD")
              .replace(/[\u0300-\u036f]/g, "")
              .replace(/[^a-z0-9]+/g, "_")
              .replace(/^_|_$/g, "");
            const prefix =
              MOCK_REMOTE_SUGGESTIONS[provider] ||
              `${provider.replace(/-/g, "_")}_pessoal`;
            const remote = `${prefix.split("_").slice(0, -1).join("_") || provider}_${base}`.slice(
              0,
              64
            );
            return Promise.resolve({ remote });
          }
          const remote =
            MOCK_REMOTE_SUGGESTIONS[provider] ||
            `${provider.replace(/-/g, "_")}_pessoal`;
          return Promise.resolve({ remote });
        }
        if (name === "sharedMountHints") {
          const provider = canonicalProviderSlug(String(args.provider || ""));
          const hints =
            FALLBACK_SHARED_MOUNT_HINTS[provider] || FALLBACK_SHARED_MOUNT_HINTS.default;
          return Promise.resolve({ ...hints });
        }
        if (name === "suggestMountLetter") {
          const excludeId = String(args.exclude_id || "").trim() || undefined;
          const mountpoint = suggestLocalMountLetter(excludeId);
          const letters = [];
          const reserved = collectReservedMountLetters(excludeId);
          for (let index = 0; index < 52; index += 1) {
            const slot = slotIndexToMountLabel(index);
            const available = !reserved.has(slot);
            letters.push({
              letter: slot,
              available,
              reason: available
                ? isFolderMountSlot(slot)
                  ? `Pasta de montagem (%LOCALAPPDATA%/RDrive/mounts/${slot})`
                  : null
                : `O ponto ${slot} já está em uso.`,
              kind: isFolderMountSlot(slot) ? "folder" : "letter",
            });
          }
          return Promise.resolve({ mountpoint, letters });
        }
        if (name === "listAvailableMountLetters") {
          const excludeId = String(args.exclude_id || "").trim() || undefined;
          const letters = listLocalAvailableMountLetters(excludeId);
          const suggested = suggestLocalMountLetter(excludeId);
          return Promise.resolve({ letters, suggested });
        }
        if (name === "supportsAutoConnect") {
          const provider = String(args.provider || "").toLowerCase();
          return Promise.resolve({ supported: AUTO_CONNECT_SLUGS.has(provider) });
        }
        if (name === "checkTeraboxBackend") {
          const terabox = MOCK_PROVIDERS.find((item) => item.slug === "terabox");
          const available = terabox ? terabox.backend_available !== false : false;
          return Promise.resolve({
            ok: true,
            available,
            message: available ? "" : TERABOX_BACKEND_MISSING_PT,
            pr_url: TERABOX_RCLONE_PR_URL,
          });
        }
        if (name === "openTeraboxLogin") {
          if (typeof window !== "undefined" && window.open) {
            window.open(TERABOX_LOGIN_URL, "_blank", "noopener,noreferrer");
          }
          if (onEvent) {
            onEvent({
              type: "toast",
              message: TERABOX_LOGIN_TOAST_PT,
              tone: "ok",
            });
          }
          return Promise.resolve({ ok: true, url: TERABOX_LOGIN_URL });
        }
        if (name === "openTeraboxEmbeddedBrowser") {
          const cookie =
            typeof window !== "undefined" && window.prompt
              ? window.prompt(
                  "Modo desenvolvimento: cole o cabeçalho Cookie TeraBox (tem de ter ndus=):",
                  ""
                )
              : "";
          if (!cookie || !String(cookie).trim()) {
            return Promise.resolve({ ok: false, cancelled: true });
          }
          const trimmed = String(cookie).trim();
          if (!teraboxCookieContainsNdus(trimmed)) {
            return Promise.resolve({
              ok: false,
              error: TERABOX_NDUS_WARN_PT,
            });
          }
          return Promise.resolve({
            ok: true,
            cookie: trimmed,
            ndus: true,
            hint: "Cookie simulado (modo estático).",
          });
        }
        if (name === "saveDrive") {
          const label = String(args.label || "Nova unidade").trim() || "Nova unidade";
          const provider = String(args.provider || "drive").trim() || "drive";
          const remoteName = String(args.remote_name || "").trim();
          const mountRaw = String(args.mountpoint || "").trim();
          const labelErr = validateAddDriveLabel(label);
          if (labelErr) {
            return Promise.reject(new Error(labelErr));
          }
          if (mountRaw) {
            const mountErr = validateAddDriveMount(mountRaw);
            if (mountErr) {
              return Promise.reject(new Error(mountErr));
            }
          }
          const mountpoint = mountRaw || suggestLocalMountLetter();
          const drive = {
            id: `mock-drive-${Date.now().toString(36)}`,
            label,
            provider,
            provider_label:
              (MOCK_PROVIDERS.find((item) => item.slug === provider) || {}).label ||
              provider,
            remote_name: remoteName,
            mountpoint,
            status: "disconnected",
            connect_at_startup: Boolean(args.connect_at_startup),
            session_only: Boolean(args.session_only),
          };
          snapshot.drives = Array.isArray(snapshot.drives) ? snapshot.drives : [];
          snapshot.drives.push(drive);
          if (onState) {
            onState({
              drives: snapshot.drives.slice(),
              statusText: `Unidade «${label}» guardada (mock)`,
              tone: "ok",
              busy: false,
            });
          }
          return Promise.resolve({ id: drive.id, mountpoint, ok: true });
        }
        if (name === "runAutoConnect") {
          const remoteName = String(args.remote_name || "gdrive_mock");
          if (onEvent) {
            setTimeout(() => {
              onEvent({
                type: "auto_connect_progress",
                message: "A abrir navegador para OAuth (mock)…",
                remote_name: remoteName,
              });
            }, 120);
            setTimeout(() => {
              onEvent({
                type: "auto_connect_finished",
                success: true,
                message: "Conta conectada (mock).",
                remote_name: remoteName,
              });
            }, 900);
          }
          return Promise.resolve({ remote_name: remoteName });
        }
        if (name === "startCloudSetupAgent") {
          const provider = canonicalProviderSlug(String(args.provider || "drive"));
          const remoteName =
            String(args.remote_name || "") ||
            MOCK_REMOTE_SUGGESTIONS[provider] ||
            `${provider}_pessoal`;
          const label =
            String(args.label || "").trim() ||
            (MOCK_PROVIDERS.find((p) => p.slug === provider) || {}).label ||
            provider;
          const supportsOAuth = AUTO_CONNECT_SLUGS.has(provider);
          const mockProvider = MOCK_PROVIDERS.find((p) => p.slug === provider);
          const usesGuided =
            Boolean(mockProvider && mockProvider.setup_mode === "guided") ||
            Boolean(GUIDED_FIELD_FALLBACK[provider]);
          if (onEvent) {
            const stages = supportsOAuth
              ? ["validating", "suggesting", "browser", "remote", "saving", "done"]
              : usesGuided
                ? ["validating", "suggesting", "guided", "remote", "testing", "saving", "done"]
                : ["validating", "suggesting", "manual"];
            stages.forEach((stage, index) => {
              setTimeout(() => {
                onEvent({
                  type: "cloud_setup_progress",
                  stage,
                  message: `Mock: ${stage}…`,
                  provider,
                  label,
                  remote_name: remoteName,
                  mountpoint: "Z:",
                });
              }, 150 * (index + 1));
            });
            setTimeout(() => {
              if (supportsOAuth || usesGuided) {
                onEvent({
                  type: "cloud_setup_finished",
                  success: true,
                  message: usesGuided
                    ? "Remote configurado (mock — sem rclone real)."
                    : "Unidade configurada (mock).",
                  stage: "done",
                  provider,
                  label,
                  remote_name: remoteName,
                  mountpoint: "Z:",
                  drive_id: `mock-${Date.now()}`,
                  used_manual: false,
                  used_guided: usesGuided,
                });
              } else {
                onEvent({
                  type: "cloud_setup_finished",
                  success: false,
                  message:
                    "Este provedor requer credenciais no terminal (mock). Use o assistente manual.",
                  stage: "manual",
                  provider,
                  label,
                  remote_name: remoteName,
                  used_manual: true,
                });
              }
            }, 150 * (stages.length + 2));
          }
          return Promise.resolve({
            ok: true,
            provider,
            label,
            remote_name: remoteName,
            supports_full_auto: supportsOAuth,
          });
        }
        if (name === "testTeraboxConnection" || name === "testGuidedConnection") {
          const provider = canonicalProviderSlug(String(args.provider || ""));
          const answers = args.guided_answers || {};
          const host = String(answers.host || answers.url || "").trim();
          const cookie = String(answers.cookie || "").trim();
          if (provider === "terabox") {
            if (!answers.confirmed_on_main) {
              return Promise.resolve({
                ok: false,
                message: "Marque que está na página /main antes de testar (mock).",
              });
            }
            if (!cookie || !teraboxCookieContainsNdus(cookie)) {
              return Promise.resolve({
                ok: false,
                message: TERABOX_NDUS_WARN_PT + " (mock).",
              });
            }
          } else if (!host && provider !== "terabox") {
            return Promise.resolve({
              ok: false,
              message: "Preencha host ou URL antes de testar (mock).",
            });
          }
          return Promise.resolve({
            ok: true,
            message: `Ligação simulada OK para ${provider} (mock — use Iniciar.bat para teste real).`,
          });
        }
        if (name === "openProviderDocs") {
          return Promise.resolve({
            ok: true,
            backend: String(args.provider || "drive"),
            mock: true,
          });
        }
        if (name === "cancelCloudSetupAgent") {
          return Promise.resolve({ ok: true });
        }
        if (name === "getCloudSetupState") {
          return Promise.resolve({ running: false, stage: "", message: "" });
        }
        if (name === "launchManualSetup") {
          return Promise.resolve({
            backend: String(args.provider || "drive"),
            docs_url: "https://rclone.org/",
            is_oauth: false,
            mock: true,
          });
        }
        if (name === "getLogTail") {
          return Promise.resolve({
            log: "rdrive",
            lines: ["[mock] rdrive.log indisponível sem PyQt."],
            path: "logs/rdrive.log",
          });
        }
        if (name === "openLogsFolder") {
          return Promise.resolve({ ok: true, mock: true });
        }
        if (name === "getVaultUnlockState") {
          const email = String(args.email || snapshot.vaultUnlock?.activeEmail || "");
          return Promise.resolve({
            required: Boolean(snapshot.vaultUnlock?.required),
            isSetup: false,
            recentUsers: snapshot.vaultUnlock?.recentUsers || [],
            activeEmail: email,
            hasLegacyEnc: false,
          });
        }
        if (name === "unlockVault") {
          if (!String(args.password || "").trim()) {
            return Promise.reject(new Error("Informe a senha mestra."));
          }
          snapshot.vaultUnlock = { required: false };
          if (onState) onState({ vaultUnlock: snapshot.vaultUnlock });
          return Promise.resolve({ ok: true });
        }
        if (name === "cancelVaultUnlock") {
          snapshot.vaultUnlock = { required: false, vaultEnabled: false };
          if (onState) onState({ vaultUnlock: snapshot.vaultUnlock });
          setVaultUnlockVisible(false);
          return Promise.resolve({ ok: true });
        }
        if (name === "forgotVaultPassword") {
          return Promise.resolve({ cancelled: true, mock: true });
        }
        if (name === "switchUser" || name === "restartApp" || name === "resetVault") {
          return Promise.resolve({ ok: true, mock: true });
        }
        if (name === "listDiagnosticOptions") {
          return Promise.resolve({ remotes: [], letters: [], cleanupEnabled: false });
        }
        if (name === "runSystemChecks") {
          return Promise.resolve({
            lines: [
              "✓ rclone no PATH — mock",
              "✓ WinFsp instalado — mock",
              "⚠ Instância única — modo protótipo",
              "✓ Pasta de logs — mock",
            ],
          });
        }
        if (name === "testRemote") {
          const remote = String(args.remote || "remote");
          return Promise.resolve({
            ok: true,
            lines: [`✓ Ligação`, `Remote: ${remote}`, "Latência (lsd): 42 ms (mock)"],
          });
        }
        if (name === "startSpeedTest") {
          if (onEvent) {
            setTimeout(() => {
              onEvent({
                type: "diag_speed_done",
                ok: true,
                cancelled: false,
                message: "Teste concluído (mock).",
                upload_mbps: 1.2,
                download_mbps: 2.4,
              });
            }, 800);
          }
          return Promise.resolve({ started: true });
        }
        if (name === "cancelSpeedTest") {
          return Promise.resolve({ ok: true });
        }
        if (name === "runMountChecks") {
          return Promise.resolve({ lines: ["Nenhum drive guardado (mock)."] });
        }
        if (name === "getHumanLogTail") {
          return Promise.resolve({ lines: ["(human.log vazio em modo protótipo)"], path: "logs/human.log" });
        }
        if (name === "getFeatureFlags") {
          return Promise.resolve({
            lines: Object.keys(mockSettings)
              .filter((k) => k.startsWith("enable_") || k === "mount_as_local_drive")
              .slice(0, 6)
              .map((k) => `${k}: ${mockSettings[k] ? "ON" : "OFF"}`),
          });
        }
        if (name === "forceCleanupLetter") {
          return Promise.resolve({
            ok: true,
            lines: ["✓ Limpeza simulada (disponível com RDrive em execução)."],
          });
        }
        if (name === "toggleConnection" || name === "setStartup") {
          return Promise.resolve({ ok: true, mock: true });
        }
        if (name === "editDrive") {
          const id = String(args.id || "");
          const drive = (snapshot.drives || []).find((item) => item.id === id);
          if (!drive) {
            return Promise.reject(new Error("Unidade não encontrada"));
          }
          return Promise.resolve({ drive: { ...drive } });
        }
        if (name === "deleteDrive") {
          const id = String(args.id || "");
          snapshot.drives = Array.isArray(snapshot.drives) ? snapshot.drives : [];
          const idx = snapshot.drives.findIndex((item) => item.id === id);
          if (idx < 0) {
            return Promise.reject(new Error("Unidade não encontrada"));
          }
          const label = snapshot.drives[idx].label || "Unidade";
          snapshot.drives.splice(idx, 1);
          if (onState) {
            onState({
              drives: snapshot.drives.slice(),
              statusText: `Unidade «${label}» excluída (mock)`,
              tone: "ok",
              busy: false,
            });
          }
          if (onEvent) {
            onEvent({
              type: "toast",
              message: `Unidade «${label}» excluída (mock).`,
              tone: "success",
            });
          }
          return Promise.resolve({ ok: true });
        }
        if (name === "updateDrive") {
          const id = String(args.id || "");
          const idx = (snapshot.drives || []).findIndex((item) => item.id === id);
          if (idx < 0) {
            return Promise.reject(new Error("Unidade não encontrada"));
          }
          const current = snapshot.drives[idx];
          snapshot.drives[idx] = { ...current, ...args, id: current.id };
          if (onState) {
            onState({ drives: snapshot.drives.slice(), statusText: "Unidade actualizada (mock)" });
          }
          return Promise.resolve({ ok: true });
        }
        if (name === "openTransferJobs" || name === "openStripeSplitter") {
          return Promise.resolve({ ok: true, mock: true });
        }
        return Promise.resolve({ ok: true });
      },
    };
  }

  // --- NAVEGAÇÃO VIEWS ---

  function showView(viewId) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    const target = document.getElementById(viewId);
    if (target) target.classList.add("active");
  }

  // --- ADICIONAR UNIDADE ---

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  /** Alinhado a provider_icons.py / canonical_backend (slug → ficheiro SVG). */
  const ICON_SLUG_ALIASES = {
    drive: "drive",
    google_drive: "drive",
    googledrive: "drive",
    gdrive: "drive",
    dropbox: "dropbox",
    onedrive: "onedrive",
    o365: "onedrive",
    o365sharepoint: "sharepoint",
    sharepoint: "sharepoint",
    s3: "s3",
    amazon: "s3",
    minio: "s3",
    wasabi: "s3",
    webdav: "webdav",
    dav: "webdav",
    http: "webdav",
    https: "webdav",
    sftp: "sftp",
    sftpgo: "sftp",
    ftp: "ftp",
    ftps: "ftp",
    box: "box",
    mega: "mega",
    pcloud: "pcloud",
    b2: "b2",
    backblaze: "b2",
    googlecloudstorage: "gcs",
    gcs: "gcs",
    azureblob: "azureblob",
    azurefiles: "azureblob",
    local: "local",
    alias: "local",
    mount: "local",
    hdfs: "hdfs",
    smb: "smb",
    terabox: "terabox",
  };

  function normalizeProviderSlug(slug) {
    return String(slug || "")
      .trim()
      .toLowerCase()
      .replace(/-/g, "_");
  }

  function resolveIconSlug(slug) {
    const key = normalizeProviderSlug(slug);
    if (!key) return "unknown";
    if (Object.prototype.hasOwnProperty.call(ICON_SLUG_ALIASES, key)) {
      return ICON_SLUG_ALIASES[key];
    }
    return key;
  }

  /** Backends rclone internos — alinhado a ``_HIDDEN_PROVIDER_BACKENDS`` (remote_setup.py). */
  const HIDDEN_PROVIDER_SLUGS = new Set([
    "alias",
    "mount",
    "cache",
    "chunker",
    "combine",
    "crypt",
    "hasher",
    "compress",
    "union",
    "archive",
  ]);

  function isUserFacingProvider(slug) {
    const key = normalizeProviderSlug(slug);
    return Boolean(key) && !HIDDEN_PROVIDER_SLUGS.has(key);
  }

  function providerLetterFallback(slug) {
    const key = resolveIconSlug(slug);
    if (key === "drive" || key === "googledrive" || key === "gdrive") return "G";
    if (key === "s3" || key === "b2") return key.toUpperCase();
    if (key.length >= 2) return key.slice(0, 2).toUpperCase();
    return (key.charAt(0) || "?").toUpperCase();
  }

  function providerIconHtml(slug) {
    const safeSlug = resolveIconSlug(slug).replace(/[^a-z0-9_]/gi, "_");
    const letter = providerLetterFallback(slug).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    return (
      `<img alt="" loading="lazy" decoding="async" ` +
      `src="providers/${safeSlug}.svg" ` +
      `onerror="if(this.dataset.fb){this.replaceWith(Object.assign(document.createElement('span'),{className:'provider-letter',textContent:this.dataset.fb}));this.onerror=null}else{this.dataset.fb='${letter}';this.onerror=null;this.src='providers/_generic.svg'}" />`
    );
  }

  function isUiDemoEnabled() {
    try {
      if (localStorage.getItem("RDRIVE_UI_DEMO") === "1") return true;
      if (new URLSearchParams(window.location.search).get("demo") === "1") return true;
    } catch (_err) {
      /* ignore */
    }
    return false;
  }

  function showDemoToast(message) {
    const chip = document.getElementById("status-chip");
    if (!chip) return;
    const prev = {
      text: chip.textContent,
      tone: chip.dataset.tone || "idle",
      busy: chip.dataset.busy || "false",
    };
    chip.textContent = message;
    chip.dataset.tone = "ok";
    chip.dataset.busy = "false";
    window.clearTimeout(showDemoToast._timer);
    showDemoToast._timer = window.setTimeout(() => {
      chip.textContent = prev.text;
      chip.dataset.tone = prev.tone;
      chip.dataset.busy = prev.busy;
    }, 2400);
  }

  let confirmDialogResolve = null;
  const connectionTogglePending = new Set();

  function closeConfirmDialog(result) {
    const overlay = document.getElementById("confirm-dialog");
    if (overlay) {
      overlay.hidden = true;
      overlay.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("modal-open");
    const resolve = confirmDialogResolve;
    confirmDialogResolve = null;
    if (resolve) resolve(Boolean(result));
  }

  function confirmDialog({ title, message }) {
    return new Promise((resolve) => {
      const overlay = document.getElementById("confirm-dialog");
      const titleEl = document.getElementById("confirm-dialog-title");
      const messageEl = document.getElementById("confirm-dialog-message");
      if (!overlay || !titleEl || !messageEl) {
        resolve(window.confirm([title, message].filter(Boolean).join("\n\n")));
        return;
      }
      titleEl.textContent = title || "Confirmar";
      messageEl.textContent = message || "";
      overlay.hidden = false;
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");
      confirmDialogResolve = resolve;
      const yesBtn = overlay.querySelector('[data-confirm="yes"]');
      if (yesBtn) yesBtn.focus();
    });
  }

  function wireConfirmDialog() {
    const overlay = document.getElementById("confirm-dialog");
    if (!overlay) return;
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeConfirmDialog(false);
    });
    overlay.querySelectorAll("[data-confirm]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeConfirmDialog(btn.dataset.confirm === "yes");
      });
    });
    document.addEventListener("keydown", (event) => {
      if (overlay.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeConfirmDialog(false);
      }
    });
  }

  let vaultUnlockVisible = false;
  let vaultUnlockBusy = false;
  let vaultUnlockEmailTimer = null;

  function maskEmail(email) {
    const text = String(email || "").trim();
    const at = text.indexOf("@");
    if (at <= 1) return text;
    return `${text.slice(0, 1)}***${text.slice(at)}`;
  }

  function setVaultUnlockError(message) {
    const el = document.getElementById("vault-unlock-error");
    if (!el) return;
    const text = String(message || "").trim();
    el.textContent = text;
    el.hidden = !text;
  }

  function vaultUnlockIntroCopy(ui) {
    const email = String((ui && ui.previewEmail) || ui?.activeEmail || "").trim();
    if (ui && ui.isSetup) {
      return (
        "Primeira configuração: indique o email e defina a senha mestra " +
        "para proteger o estado local (.enc)."
      );
    }
    if (email && email.includes("@")) {
      return `Conta: ${maskEmail(email)}\nIntroduza a senha mestra para desbloquear o cofre.`;
    }
    return (
      "Indique o email do utilizador (opcional) e a senha mestra da sessão " +
      "para proteger o estado local (.enc)."
    );
  }

  function applyVaultUnlockUi(ui, options = {}) {
    if (!ui || typeof ui !== "object") return;
    const overlay = document.getElementById("vault-unlock-overlay");
    if (!overlay) return;

    const emailInput = document.getElementById("vault-unlock-email");
    const previewEmail =
      options.previewEmail != null
        ? String(options.previewEmail)
        : emailInput
          ? emailInput.value
          : ui.activeEmail || "";

    const merged = {
      ...ui,
      previewEmail,
      recentUsers: Array.isArray(ui.recentUsers) ? ui.recentUsers : [],
    };

    const titleEl = document.getElementById("vault-unlock-title");
    const introEl = document.getElementById("vault-unlock-intro");
    const setupHint = document.getElementById("vault-unlock-setup-hint");
    const confirmWrap = document.getElementById("vault-unlock-confirm-wrap");
    const legacyHint = document.getElementById("vault-unlock-legacy-hint");
    const forgotBtn = overlay.querySelector('[data-action="vault-forgot-password"]');
    const datalist = document.getElementById("vault-unlock-email-list");
    const remember = document.getElementById("vault-unlock-remember");

    if (titleEl) {
      titleEl.textContent = merged.isSetup ? "Criar conta e cofre" : "Desbloquear cofre";
    }
    if (introEl) introEl.textContent = vaultUnlockIntroCopy(merged);
    if (setupHint) setupHint.hidden = !merged.isSetup;
    if (confirmWrap) confirmWrap.hidden = !merged.isSetup;
    if (legacyHint) legacyHint.hidden = !(merged.hasLegacyEnc && !previewEmail.trim());
    if (forgotBtn) forgotBtn.hidden = Boolean(merged.isSetup);
    if (remember && merged.isSetup) remember.checked = false;
    if (emailInput && options.fillEmail !== false && !emailInput.value.trim() && merged.activeEmail) {
      emailInput.value = merged.activeEmail;
    }
    if (emailInput) {
      emailInput.placeholder = merged.isSetup
        ? "email@exemplo.com (obrigatório)"
        : "email@exemplo.com";
    }
    if (datalist) {
      datalist.replaceChildren();
      merged.recentUsers.forEach((entry) => {
        const option = document.createElement("option");
        option.value = entry;
        datalist.appendChild(option);
      });
    }
  }

  function setVaultUnlockVisible(visible) {
    const overlay = document.getElementById("vault-unlock-overlay");
    if (!overlay) return;
    vaultUnlockVisible = Boolean(visible);
    overlay.hidden = !vaultUnlockVisible;
    overlay.setAttribute("aria-hidden", vaultUnlockVisible ? "false" : "true");
    document.body.classList.toggle("vault-locked", vaultUnlockVisible);
    document.body.classList.toggle("modal-open", vaultUnlockVisible);
    if (vaultUnlockVisible) {
      setVaultUnlockError("");
      const password = document.getElementById("vault-unlock-password");
      if (password) password.focus();
    }
  }

  async function refreshVaultUnlockMode() {
    const emailInput = document.getElementById("vault-unlock-email");
    const email = emailInput ? emailInput.value.trim() : "";
    if (!bridge || !bridge.command) {
      applyVaultUnlockUi(
        {
          isSetup: false,
          activeEmail: email,
          hasLegacyEnc: false,
          recentUsers: [],
        },
        { previewEmail: email, fillEmail: false }
      );
      return;
    }
    try {
      const ui = await bridge.command("getVaultUnlockState", { email });
      applyVaultUnlockUi(ui, { previewEmail: email, fillEmail: false });
    } catch (_err) {
      /* mantém UI actual */
    }
  }

  async function submitVaultUnlock(event) {
    if (event) event.preventDefault();
    if (vaultUnlockBusy) return;
    const emailEl = document.getElementById("vault-unlock-email");
    const passwordEl = document.getElementById("vault-unlock-password");
    const confirmEl = document.getElementById("vault-unlock-confirm");
    const rememberEl = document.getElementById("vault-unlock-remember");
    if (!passwordEl) return;

    const payload = {
      email: emailEl ? emailEl.value.trim() : "",
      password: passwordEl.value,
      confirmPassword: confirmEl ? confirmEl.value : "",
      rememberSession: rememberEl ? rememberEl.checked : false,
    };

    if (!bridge || !bridge.command) {
      setVaultUnlockError("Disponível apenas com o RDrive em execução.");
      return;
    }

    vaultUnlockBusy = true;
    setVaultUnlockError("");
    try {
      await bridge.command("unlockVault", payload);
      passwordEl.value = "";
      if (confirmEl) confirmEl.value = "";
      setVaultUnlockVisible(false);
    } catch (err) {
      setVaultUnlockError(err && err.message ? err.message : "Não foi possível desbloquear o cofre.");
      passwordEl.focus();
      passwordEl.select();
    } finally {
      vaultUnlockBusy = false;
    }
  }

  async function cancelVaultUnlock() {
    if (vaultUnlockBusy) return;
    if (!bridge || !bridge.command) {
      setVaultUnlockVisible(false);
      return;
    }
    try {
      const result = await bridge.command("cancelVaultUnlock", {});
      if (result && result.vaultUnlock) {
        applyVaultUnlockState(result.vaultUnlock);
      } else {
        setVaultUnlockVisible(false);
      }
    } catch (_err) {
      setVaultUnlockVisible(false);
    }
  }

  async function forgotVaultPassword() {
    if (vaultUnlockBusy) return;
    const emailEl = document.getElementById("vault-unlock-email");
    const passwordEl = document.getElementById("vault-unlock-password");
    if (!bridge || !bridge.command) {
      setVaultUnlockError("Recuperação disponível apenas com o RDrive em execução.");
      return;
    }
    vaultUnlockBusy = true;
    setVaultUnlockError("");
    try {
      const result = await bridge.command("forgotVaultPassword", {
        email: emailEl ? emailEl.value.trim() : "",
      });
      if (result && result.cancelled) return;
      if (result && result.password && passwordEl) {
        passwordEl.value = result.password;
      }
      if (result && result.vaultUnlock) {
        applyVaultUnlockUi(result.vaultUnlock, { fillEmail: false });
      }
      if (result && result.message) {
        setVaultUnlockError(result.message);
      }
    } catch (err) {
      setVaultUnlockError(err && err.message ? err.message : "Recuperação cancelada ou falhou.");
    } finally {
      vaultUnlockBusy = false;
    }
  }

  function wireVaultUnlockForm() {
    const form = document.getElementById("vault-unlock-form");
    const emailInput = document.getElementById("vault-unlock-email");
    const overlay = document.getElementById("vault-unlock-overlay");
    if (form) {
      form.addEventListener("submit", submitVaultUnlock);
    }
    if (emailInput) {
      emailInput.addEventListener("input", () => {
        window.clearTimeout(vaultUnlockEmailTimer);
        vaultUnlockEmailTimer = window.setTimeout(refreshVaultUnlockMode, 180);
      });
    }
    if (overlay) {
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) event.preventDefault();
      });
      document.addEventListener("keydown", (event) => {
        if (!vaultUnlockVisible || overlay.hidden) return;
        if (event.key === "Escape") {
          event.preventDefault();
          cancelVaultUnlock();
        }
      });
    }
  }

  function applyVaultUnlockState(ui) {
    if (!ui || typeof ui !== "object") return;
    if (ui.required) {
      applyVaultUnlockUi(ui);
      setVaultUnlockVisible(true);
      return;
    }
    setVaultUnlockVisible(false);
  }

  function disconnectConfirmCopy(drive) {
    const label = drive && drive.label ? drive.label : "esta unidade";
    return {
      title: "Desligar unidade",
      message: `Desligar «${label}»?\n\nA letra de unidade deixará de estar disponível.`,
    };
  }

  function deleteConfirmCopy(drive) {
    const label = drive && drive.label ? drive.label : "esta unidade";
    return {
      title: "Excluir unidade",
      message: `Tem certeza que deseja excluir «${label}»?\n\nA configuração será removida deste PC.`,
    };
  }

  function driveLabelKey(label) {
    return String(label || "")
      .trim()
      .toLocaleLowerCase();
  }

  function findDriveWithLabel(label, excludeId) {
    const key = driveLabelKey(label);
    if (!key) return null;
    return (
      bridgeDrives.find(
        (drive) =>
          drive.id !== excludeId && driveLabelKey(drive.label) === key
      ) || null
    );
  }

  function normalizeMountSlot(value) {
    const text = String(value || "").trim().toUpperCase();
    if (!text) return "";
    const core = text.endsWith(":") ? text.slice(0, -1) : text;
    if (core.length === 1 && core >= "A" && core <= "Z") return `${core}:`;
    if (core.length >= 2 && /^[A-Z]+$/.test(core)) return core;
    return "";
  }

  function normalizeMountLetterInput(value) {
    return normalizeMountSlot(value);
  }

  function isFolderMountSlot(slot) {
    return Boolean(slot) && !String(slot).endsWith(":");
  }

  function slotIndexToMountLabel(index) {
    if (index < 26) return `${String.fromCharCode(65 + index)}:`;
    let n = index + 1;
    let label = "";
    while (n > 0) {
      const rem = (n - 1) % 26;
      label = String.fromCharCode(65 + rem) + label;
      n = Math.floor((n - 1) / 26);
    }
    return label;
  }

  function collectReservedMountLetters(excludeId, options = {}) {
    const includeDemo = Boolean(options.includeDemo);
    const slots = new Set();
    const source = includeDemo ? [...bridgeDrives, ...demoDrives] : bridgeDrives;
    source.forEach((drive) => {
      if (excludeId && drive.id === excludeId) return;
      const slot = normalizeMountSlot(drive.mountpoint);
      if (slot) slots.add(slot);
    });
    return slots;
  }

  function listLocalAvailableMountLetters(excludeId, options = {}) {
    const reserved = collectReservedMountLetters(excludeId, options);
    const letters = [];
    const maxSlots = 26 + 26;
    for (let index = 0; index < maxSlots; index += 1) {
      const slot = slotIndexToMountLabel(index);
      if (!reserved.has(slot)) letters.push(slot);
    }
    return letters;
  }

  function suggestLocalMountLetter(excludeId, options = {}) {
    const letters = listLocalAvailableMountLetters(excludeId, options);
    return letters[0] || "AA";
  }

  function populateAddDriveMountSelect(selectEl, letters, suggested) {
    if (!selectEl) return;
    const normalizedLetters = (letters || [])
      .map((item) => normalizeMountSlot(item))
      .filter(Boolean);
    const unique = [...new Set(normalizedLetters)];
    const current = normalizeMountSlot(selectEl.value);
    const desired = normalizeMountSlot(suggested);

    selectEl.replaceChildren();
    unique.forEach((slot) => {
      const option = document.createElement("option");
      option.value = slot;
      option.textContent = isFolderMountSlot(slot) ? `${slot} (pasta)` : slot;
      if (isFolderMountSlot(slot)) {
        option.title = `Montagem em pasta (%LOCALAPPDATA%/RDrive/mounts/${slot})`;
      }
      selectEl.appendChild(option);
    });

    selectEl.disabled = unique.length === 0;
    const pick =
      (desired && unique.includes(desired) && desired) ||
      (current && unique.includes(current) && current) ||
      unique[0] ||
      "";
    selectEl.value = pick;
  }

  function setAddDriveMountSelection(mountpoint) {
    const els = getAddDriveEls();
    if (!els.mountInput) return;
    const normalized = normalizeMountSlot(mountpoint);
    if (!normalized) return;
    if (addDriveState.availableMountLetters.includes(normalized)) {
      els.mountInput.value = normalized;
    }
  }

  function nextUniqueDemoLabel(baseLabel) {
    const taken = new Set([
      ...bridgeDrives.map((drive) => driveLabelKey(drive.label)),
      ...demoDrives.map((drive) => driveLabelKey(drive.label)),
    ]);
    const base = String(baseLabel || "Demo").trim() || "Demo";
    if (!taken.has(driveLabelKey(base))) return base;
    let index = 2;
    while (taken.has(driveLabelKey(`${base} ${index}`))) index += 1;
    return `${base} ${index}`;
  }

  function validateAddDriveLabel(label) {
    if (findDriveWithLabel(label)) {
      return DUPLICATE_LABEL_MESSAGE;
    }
    return "";
  }

  function validateAddDriveMount(mountpoint) {
    const normalized = normalizeMountSlot(mountpoint);
    if (!normalized) {
      return "Selecione um ponto de montagem (A–Z ou AA+).";
    }
    const available = addDriveState.availableMountLetters;
    if (!available.length) {
      return "Não há pontos de montagem disponíveis.";
    }
    if (!available.includes(normalized)) {
      return `O ponto ${normalized} não está disponível.`;
    }
    return "";
  }

  async function refreshAddDriveMountLetters(excludeId) {
    const els = getAddDriveEls();
    if (!els.mountInput) return;

    let letters = [];
    let suggested = "";

    if (bridge && bridge.command) {
      try {
        const result = await bridge.command("listAvailableMountLetters", {
          exclude_id: excludeId || "",
        });
        if (result && Array.isArray(result.letters)) {
          letters = result.letters;
          suggested = result.suggested || "";
        }
      } catch {
        /* fallback abaixo */
      }
    }

    if (!letters.length) {
      letters = listLocalAvailableMountLetters(excludeId);
      suggested = suggestLocalMountLetter(excludeId);
    }

    addDriveState.availableMountLetters = letters
      .map((item) => normalizeMountSlot(item))
      .filter(Boolean);
    populateAddDriveMountSelect(els.mountInput, addDriveState.availableMountLetters, suggested);
  }

  function setAddDriveFeedback(message, tone) {
    const el = document.getElementById("add-drive-feedback");
    if (!el) return;
    el.textContent = message || "";
    if (tone) el.dataset.tone = tone;
    else delete el.dataset.tone;
  }

  function getAddDriveEls() {
    const view = document.getElementById(VIEW_ADD_DRIVE);
    return {
      view,
      form: document.getElementById("add-drive-form"),
      grid: document.getElementById("provider-grid"),
      search: document.getElementById("provider-search"),
      labelInput: document.getElementById("add-label"),
      remoteInput: document.getElementById("add-remote"),
      mountInput: document.getElementById("add-mount"),
      startupInput: document.getElementById("add-startup"),
      sessionInput: document.getElementById("add-session"),
      connectNowInput: document.getElementById("add-connect-now"),
      guidance: document.getElementById("provider-guidance"),
      status: document.getElementById("auto-connect-status"),
      oauthBtn: document.querySelector('[data-role="auto-connect-btn"]'),
      manualBtn: document.querySelector('[data-role="manual-setup-btn"]'),
      authActions: document.querySelector(".add-drive-auth-actions"),
      template: document.getElementById("provider-card-template"),
      stepPanels: view
        ? Array.from(view.querySelectorAll("[data-add-step-panel]"))
        : [],
      stepperItems: view
        ? Array.from(view.querySelectorAll(".add-drive-stepper-item"))
        : [],
      prevBtn: document.querySelector('[data-action="add-drive-prev"]'),
      nextBtn: document.querySelector('[data-action="add-drive-next"]'),
      saveBtn: document.querySelector('[data-role="add-drive-save"]'),
      onedriveTypePanel: document.getElementById("onedrive-type-panel"),
      onedriveTenantInput: document.getElementById("onedrive-tenant"),
      mapSharedOnlyInput: document.getElementById("add-map-shared-only"),
      sharedLinkInput: document.getElementById("add-shared-link"),
      rootPathInput: document.getElementById("add-root-path"),
      sharedFieldsPanel: document.getElementById("add-shared-fields"),
      sharedLinkHelp: document.getElementById("add-shared-link-help"),
      rootPathHint: document.getElementById("add-root-path-hint"),
      assistantModeInput: document.getElementById("add-assistant-mode"),
      cloudSetupProgress: document.getElementById("cloud-setup-progress"),
      cloudSetupSteps: document.getElementById("cloud-setup-steps"),
      cloudSetupStatus: document.getElementById("cloud-setup-status"),
      cancelCloudSetupBtn: document.querySelector('[data-role="cancel-cloud-setup-btn"]'),
      retryCloudSetupBtn: document.querySelector('[data-role="retry-cloud-setup-btn"]'),
      cloudSetupManualBtn: document.querySelector('[data-role="cloud-setup-manual-btn"]'),
      guidedPanel: document.getElementById("add-guided-panel"),
      guidedFields: document.getElementById("add-guided-fields"),
      guidedHint: document.getElementById("add-guided-hint"),
      guidedSetupBtn: document.querySelector('[data-role="guided-setup-btn"]'),
      guidedTestBtn: document.querySelector('[data-role="guided-test-btn"]'),
      guidedTechnicalBtn: document.querySelector('[data-role="guided-technical-btn"]'),
      guidedDocs: document.getElementById("add-guided-docs"),
      guidedReadmeLink: document.querySelector('[data-role="guided-readme-link"]'),
      guidedRcloneLink: document.querySelector('[data-role="guided-rclone-link"]'),
      guidedTestStatus: document.getElementById("add-guided-test-status"),
      teraboxWizard: document.getElementById("add-terabox-wizard"),
      teraboxAdvancedHelp: document.getElementById("add-terabox-advanced-help"),
      teraboxBackendBanner: document.getElementById("add-terabox-backend-banner"),
      teraboxCookieWarn: document.getElementById("add-terabox-cookie-warn"),
    };
  }

  function isAddDriveAssistantMode() {
    const els = getAddDriveEls();
    if (els.assistantModeInput) {
      return Boolean(els.assistantModeInput.checked);
    }
    return Boolean(addDriveState.assistantMode);
  }

  function renderCloudSetupStepsList(providerOrOAuth) {
    const els = getAddDriveEls();
    if (!els.cloudSetupSteps) return;
    const provider =
      providerOrOAuth && typeof providerOrOAuth === "object" ? providerOrOAuth : null;
    const supportsOAuth = provider
      ? providerSupportsAutoConnect(provider)
      : Boolean(providerOrOAuth);
  const steps = supportsOAuth
      ? CLOUD_SETUP_PROGRESS_STEPS
      : provider && providerUsesGuidedSetup(provider)
        ? CLOUD_SETUP_GUIDED_STEPS
        : [
            { id: "validating", label: "A validar provedor…" },
            { id: "suggesting", label: "A preparar sugestões…" },
            { id: "manual", label: "Assistente rclone (terminal)" },
          ];
    els.cloudSetupSteps.innerHTML = steps
      .map(
        (step) =>
          `<li class="is-pending" data-cloud-stage="${escapeHtml(step.id)}">${escapeHtml(step.label)}</li>`
      )
      .join("");
  }

  function updateCloudSetupProgressUI(stage, message) {
    const els = getAddDriveEls();
    if (!els.cloudSetupSteps) return;
    const stageId = String(stage || "").toLowerCase();
    const order = Array.from(els.cloudSetupSteps.querySelectorAll("[data-cloud-stage]")).map(
      (node) => node.getAttribute("data-cloud-stage") || ""
    );
    const activeIndex = order.indexOf(stageId);
    els.cloudSetupSteps.querySelectorAll("[data-cloud-stage]").forEach((node, index) => {
      node.classList.remove("is-pending", "is-active", "is-done");
      if (activeIndex < 0) {
        node.classList.add("is-pending");
        return;
      }
      if (index < activeIndex) node.classList.add("is-done");
      else if (index === activeIndex) node.classList.add("is-active");
      else node.classList.add("is-pending");
    });
    if (stageId === "done" || stageId === "error" || stageId === "cancelled") {
      els.cloudSetupSteps.querySelectorAll("[data-cloud-stage]").forEach((node, index) => {
        if (stageId === "done" && index <= order.length - 1) {
          node.classList.remove("is-pending", "is-active");
          node.classList.add("is-done");
        }
      });
    }
    if (els.cloudSetupStatus) {
      els.cloudSetupStatus.textContent = message || "";
      delete els.cloudSetupStatus.dataset.tone;
      if (stageId === "error") els.cloudSetupStatus.dataset.tone = "error";
      if (stageId === "done") els.cloudSetupStatus.dataset.tone = "ok";
    }
  }

  function setCloudSetupRunning(running) {
    addDriveState.cloudSetupInFlight = Boolean(running);
    const els = getAddDriveEls();
    if (els.view) {
      els.view.dataset.assistantRunning = running ? "1" : "0";
    }
    if (els.cloudSetupProgress) {
      els.cloudSetupProgress.hidden = !running;
      els.cloudSetupProgress.setAttribute("aria-busy", running ? "true" : "false");
    }
    if (els.cancelCloudSetupBtn) {
      els.cancelCloudSetupBtn.hidden = !running;
    }
    if (els.retryCloudSetupBtn) {
      els.retryCloudSetupBtn.hidden = running;
    }
    if (els.cloudSetupManualBtn) {
      els.cloudSetupManualBtn.hidden = running;
    }
  }

  function showCloudSetupRecovery(showManual) {
    const els = getAddDriveEls();
    setCloudSetupRunning(false);
    if (els.retryCloudSetupBtn) els.retryCloudSetupBtn.hidden = false;
    if (els.cloudSetupManualBtn) els.cloudSetupManualBtn.hidden = !showManual;
  }

  async function startCloudSetupAgentForProvider(provider) {
    const els = getAddDriveEls();
    if (!provider || !bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }

    const slug = canonicalProviderSlug(provider.slug);
    addDriveState.selectedSlug = slug;
    addDriveState.cloudSetupLastProvider = provider;
    renderAddDriveProviders();

    const supportsOAuth = providerSupportsAutoConnect(provider);
    renderCloudSetupStepsList(provider);
    setCloudSetupRunning(true);
    setAddDriveFeedback("");
    updateCloudSetupProgressUI("validating", "A iniciar assistente…");

    if (els.retryCloudSetupBtn) els.retryCloudSetupBtn.hidden = true;
    if (els.cloudSetupManualBtn) els.cloudSetupManualBtn.hidden = true;

    const guidedPayload = providerUsesGuidedSetup(provider)
      ? { guided_answers: collectGuidedAnswers(provider) }
      : {};

    try {
      await bridge.command("startCloudSetupAgent", {
        provider: slug,
        label: els.labelInput ? els.labelInput.value.trim() : "",
        remote_name: els.remoteInput ? els.remoteInput.value.trim() : "",
        mountpoint: els.mountInput ? els.mountInput.value.trim() : "",
        save_drive: true,
        connect_at_startup: els.startupInput ? els.startupInput.checked : false,
        session_only: els.sessionInput ? els.sessionInput.checked : false,
        connect_now: els.connectNowInput ? els.connectNowInput.checked : true,
        ...getOnedriveConnectPayload(),
        ...guidedPayload,
      });
    } catch (err) {
      setCloudSetupRunning(false);
      showCloudSetupRecovery(true);
      const msg = (err && err.message) || "Falha ao iniciar o assistente.";
      updateCloudSetupProgressUI("error", msg);
      setAddDriveFeedback(msg, "error");
    }
  }

  async function cancelCloudSetupAgent() {
    if (!bridge || !bridge.command) return;
    try {
      await bridge.command("cancelCloudSetupAgent", {});
    } catch {
      /* ignore */
    }
    setCloudSetupRunning(false);
    updateCloudSetupProgressUI("cancelled", "Configuração cancelada.");
    setAddDriveFeedback("Assistente cancelado.", "error");
  }

  async function retryCloudSetupAgent() {
    const provider =
      addDriveState.cloudSetupLastProvider ||
      getSelectedAddDriveProvider();
    if (!provider) {
      setAddDriveFeedback("Escolha um provedor para tentar novamente.", "error");
      return;
    }
    await startCloudSetupAgentForProvider(provider);
  }

  function useManualWizardFromAssistant() {
    const els = getAddDriveEls();
    setCloudSetupRunning(false);
    if (els.cloudSetupProgress) els.cloudSetupProgress.hidden = true;
    if (els.assistantModeInput) els.assistantModeInput.checked = false;
    addDriveState.assistantMode = false;
    if (addDriveState.selectedSlug) {
      setAddDriveStep(2);
      setAddDriveFeedback(
        "Modo manual: preencha nome, remote e ligação nos passos seguintes.",
        "ok"
      );
    }
  }

  function onCloudSetupProgress(evt) {
    const stage = evt && evt.stage ? evt.stage : "";
    const message = (evt && evt.message) || "";
    updateCloudSetupProgressUI(stage, message);
    setAddDriveFeedback(message, "busy");

    const els = getAddDriveEls();
    if (evt && evt.label && els.labelInput && !els.labelInput.value.trim()) {
      els.labelInput.value = evt.label;
    }
    if (evt && evt.remote_name && els.remoteInput) {
      els.remoteInput.value = evt.remote_name;
      addDriveState.remoteAutoDirty = true;
    }
    if (evt && evt.mountpoint) {
      setAddDriveMountSelection(evt.mountpoint);
    }
  }

  function onCloudSetupFinished(evt) {
    setCloudSetupRunning(false);
    const success = Boolean(evt && evt.success);
    const cancelled = Boolean(evt && evt.cancelled);
    const usedManual = Boolean(evt && evt.used_manual);
    const stage = evt && evt.stage ? evt.stage : success ? "done" : "error";
    const message = (evt && evt.message) || "";

    updateCloudSetupProgressUI(stage, message);

    const els = getAddDriveEls();
    if (evt && evt.label && els.labelInput) els.labelInput.value = evt.label;
    if (evt && evt.remote_name && els.remoteInput) {
      els.remoteInput.value = evt.remote_name;
      addDriveState.remoteAutoDirty = true;
      addDriveState.oauthConnected = success && !usedManual;
    }
    if (evt && evt.mountpoint) {
      setAddDriveMountSelection(evt.mountpoint);
    }

    if (success) {
      setAddDriveFeedback(message || "Unidade configurada.", "ok");
      resetAddDriveForm();
      showView(VIEW_HOME);
      return;
    }

    if (cancelled) {
      setAddDriveFeedback("Assistente cancelado.", "error");
      showCloudSetupRecovery(!usedManual);
      return;
    }

    if (stage === "guided") {
      const provider =
        addDriveState.cloudSetupLastProvider || getSelectedAddDriveProvider();
      if (provider) renderGuidedSetupPanel(provider);
      setAddDriveFeedback(
        message || "Preencha o formulário guiado e clique em «Ligar e guardar».",
        "ok"
      );
      showCloudSetupRecovery(true);
      return;
    }

    setAddDriveFeedback(message || "Não foi possível concluir a configuração.", "error");
    showCloudSetupRecovery(true);
  }

  async function runGuidedCloudSetup() {
    const provider = getSelectedAddDriveProvider();
    if (!provider) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!guidedAnswersComplete(provider)) {
      const msg = isTeraboxProvider(provider)
        ? "Faça login no navegador RDrive para capturar o cookie antes de ligar."
        : "Preencha todos os campos obrigatórios.";
      setAddDriveFeedback(msg, "error");
      return;
    }
    if (isTeraboxProvider(provider) && !isTeraboxBackendReady(provider)) {
      setAddDriveFeedback(TERABOX_BACKEND_MISSING_PT, "error");
      applyTeraboxBackendUi(provider);
      return;
    }
    cacheGuidedAnswers(provider);
    await startCloudSetupAgentForProvider(provider);
  }

  async function testGuidedConnection() {
    const provider = getSelectedAddDriveProvider();
    if (!provider) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!providerUsesGuidedSetup(provider)) {
      setAddDriveFeedback("Este provedor não usa formulário guiado.", "error");
      return;
    }
    if (!guidedAnswersComplete(provider)) {
      const teraboxHint = isTeraboxProvider(provider)
        ? "Faça login no navegador RDrive para obter o cookie (ndus=) antes de testar."
        : "Preencha todos os campos obrigatórios antes de testar.";
      setAddDriveFeedback(teraboxHint, "error");
      return;
    }
    if (isTeraboxProvider(provider) && !isTeraboxBackendReady(provider)) {
      setAddDriveFeedback(TERABOX_BACKEND_MISSING_PT, "error");
      applyTeraboxBackendUi(provider);
      return;
    }
    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }
    const els = getAddDriveEls();
    cacheGuidedAnswers(provider);
    if (els.guidedTestBtn) els.guidedTestBtn.disabled = true;
    if (els.guidedTestStatus) {
      els.guidedTestStatus.hidden = false;
      els.guidedTestStatus.textContent = isTeraboxProvider(provider)
        ? "A testar ligação TeraBox (pode demorar até 2 min)…"
        : "A testar ligação…";
      delete els.guidedTestStatus.dataset.tone;
    }
    setAddDriveFeedback(
      isTeraboxProvider(provider)
        ? "A testar TeraBox (timeouts longos, até 3 tentativas)…"
        : "A testar ligação (remote temporário)…",
      "busy"
    );
    const answers = collectGuidedAnswers(provider);
    const testCommand = isTeraboxProvider(provider)
      ? "testTeraboxConnection"
      : "testGuidedConnection";
    try {
      const result = await bridge.command(testCommand, {
        provider: provider.slug,
        guided_answers: answers,
      });
      const ok = Boolean(result && result.ok);
      const message = (result && result.message) || (ok ? "Ligação OK." : "Falha no teste.");
      if (els.guidedTestStatus) {
        els.guidedTestStatus.hidden = false;
        els.guidedTestStatus.textContent = message;
        els.guidedTestStatus.dataset.tone = ok ? "ok" : "error";
      }
      setAddDriveFeedback(message, ok ? "ok" : "error");
    } catch (err) {
      const message = (err && err.message) || "Falha ao testar ligação.";
      if (els.guidedTestStatus) {
        els.guidedTestStatus.hidden = false;
        els.guidedTestStatus.textContent = message;
        els.guidedTestStatus.dataset.tone = "error";
      }
      setAddDriveFeedback(message, "error");
    } finally {
      if (isTeraboxProvider(provider)) {
        updateTeraboxCookieFieldState();
      } else if (els.guidedTestBtn) {
        els.guidedTestBtn.disabled = false;
      }
    }
  }

  async function openProviderDocsLink(target) {
    const provider = getSelectedAddDriveProvider();
    if (!provider) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }
    try {
      await bridge.command("openProviderDocs", {
        provider: provider.slug,
        target: target === "readme" ? "readme" : "rclone",
      });
    } catch (err) {
      setAddDriveFeedback((err && err.message) || "Não foi possível abrir a documentação.", "error");
    }
  }

  async function runGuidedTechnicalMode() {
    const provider = getSelectedAddDriveProvider();
    if (!provider) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }
    const els = getAddDriveEls();
    addDriveState.selectedSlug = provider.slug;
    if (!addDriveState.remoteAutoDirty) {
      await suggestAddDriveRemote();
    }
    const remoteName = els.remoteInput ? els.remoteInput.value.trim() : "";
    try {
      const info = await bridge.command("launchManualSetup", {
        provider: provider.slug,
        remote_name: remoteName,
      });
      setAddDriveFeedback(
        `Modo técnico: assistente rclone aberto (${info.backend || provider.slug}). Remote sugerido: ${remoteName || "—"}`,
        "ok"
      );
    } catch (err) {
      setAddDriveFeedback((err && err.message) || "Falha ao abrir o terminal.", "error");
    }
  }

  function syncAddDriveSharedFieldsVisibility() {
    const els = getAddDriveEls();
    const enabled = els.mapSharedOnlyInput && els.mapSharedOnlyInput.checked;
    if (els.sharedFieldsPanel) {
      els.sharedFieldsPanel.hidden = !enabled;
    }
    if (els.sharedLinkInput) {
      els.sharedLinkInput.required = Boolean(enabled);
    }
  }

  async function refreshAddDriveSharedHints() {
    const els = getAddDriveEls();
    const slug = addDriveState.selectedSlug
      ? canonicalProviderSlug(addDriveState.selectedSlug)
      : "";
    let hints = FALLBACK_SHARED_MOUNT_HINTS[slug] || FALLBACK_SHARED_MOUNT_HINTS.default;

    if (slug && bridge && bridge.command) {
      try {
        const result = await bridge.command("sharedMountHints", { provider: slug });
        if (result && result.placeholder) {
          hints = result;
        }
      } catch {
        /* fallback */
      }
    }

    if (els.sharedLinkInput && hints.placeholder) {
      els.sharedLinkInput.placeholder = hints.placeholder;
    }
    if (els.sharedLinkHelp && hints.help) {
      els.sharedLinkHelp.textContent = hints.help;
    }
    if (els.rootPathHint && hints.subpath_hint) {
      els.rootPathHint.textContent = hints.subpath_hint;
    }
  }

  function validateAddDriveSharedScope() {
    const els = getAddDriveEls();
    if (!els.mapSharedOnlyInput || !els.mapSharedOnlyInput.checked) {
      return "";
    }
    const link = els.sharedLinkInput ? els.sharedLinkInput.value.trim() : "";
    const sub = els.rootPathInput ? els.rootPathInput.value.trim() : "";
    if (!link && !sub) {
      return "Indique o link/ID da pasta partilhada ou um subcaminho no remote.";
    }
    return "";
  }

  function getOnedriveConnectType() {
    const els = getAddDriveEls();
    if (!els.onedriveTypePanel || els.onedriveTypePanel.hidden) {
      return addDriveState.onedriveType || "personal";
    }
    const selected = els.onedriveTypePanel.querySelector(
      'input[name="onedrive-type"]:checked'
    );
    return selected && selected.value === "business" ? "business" : "personal";
  }

  function getOnedriveConnectPayload() {
    const payload = { onedrive_type: getOnedriveConnectType() };
    const els = getAddDriveEls();
    const tenant = els.onedriveTenantInput ? els.onedriveTenantInput.value.trim() : "";
    if (tenant) payload.tenant = tenant;
    return payload;
  }

  function syncOnedriveTypePanelVisibility() {
    const els = getAddDriveEls();
    if (!els.onedriveTypePanel) return;
    const isOnedrive = canonicalProviderSlug(addDriveState.selectedSlug) === "onedrive";
    els.onedriveTypePanel.hidden = !isOnedrive;
  }

  function setAddDriveStep(step) {
    const next = Math.max(1, Math.min(ADD_DRIVE_STEP_COUNT, step));
    addDriveState.currentStep = next;
    const els = getAddDriveEls();

    if (els.view) {
      els.view.dataset.addStep = String(next);
    }

    els.stepPanels.forEach((panel) => {
      const panelStep = parseInt(panel.dataset.addStepPanel || "0", 10);
      const active = panelStep === next;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });

    els.stepperItems.forEach((item) => {
      const target = parseInt(item.dataset.stepTarget || "0", 10);
      item.classList.toggle("is-active", target === next);
      item.classList.toggle("is-done", target < next);
    });

    if (els.prevBtn) {
      els.prevBtn.hidden = next <= 1;
    }
    if (els.nextBtn) {
      els.nextBtn.hidden = next >= ADD_DRIVE_STEP_COUNT;
    }
    if (els.saveBtn) {
      els.saveBtn.hidden = next < ADD_DRIVE_STEP_COUNT;
    }

    if (next === 1 && els.search) {
      els.search.focus();
    } else if (next === 2 && els.labelInput) {
      els.labelInput.focus();
      refreshAddDriveMountLetters().catch(() => {});
    } else if (next === 3) {
      if (!addDriveState.remoteAutoDirty) {
        suggestAddDriveRemote().catch(() => {});
      }
      updateAddDriveStep3UI({ autoStart: true }).catch(() => {});
    }
  }

  async function refreshAddDriveAutoSupport(provider) {
    const els = getAddDriveEls();
    if (!provider || !els.oauthBtn) return providerSupportsAutoConnect(provider);

    let supported = providerSupportsAutoConnect(provider);
    if (bridge && bridge.command) {
      try {
        const result = await bridge.command("supportsAutoConnect", {
          provider: canonicalProviderSlug(provider.slug),
        });
        if (result && result.supported != null) {
          supported = Boolean(result.supported);
          provider.supports_auto_connect = supported;
        }
      } catch {
        /* keep cached flag */
      }
    }
    return supported;
  }

  async function updateAddDriveStep3UI(options = {}) {
    const autoStart = Boolean(options.autoStart);
    const els = getAddDriveEls();
    const provider = getSelectedAddDriveProvider();
    syncOnedriveTypePanelVisibility();
    const supportsAuto = provider
      ? await refreshAddDriveAutoSupport(provider)
      : false;

    if (els.authActions) {
      els.authActions.dataset.addAuthMode = supportsAuto ? "auto" : "manual";
    }

    if (els.guidance) {
      if (!provider) {
        els.guidance.textContent = SLUG_GUIDANCE.default;
      } else if (supportsAuto) {
        const slug = canonicalProviderSlug(provider.slug);
        if (slug === "onedrive") {
          els.guidance.textContent =
            getOnedriveConnectType() === "business"
              ? "OneDrive empresarial: faça login com a conta Microsoft 365 da organização no browser."
              : "OneDrive pessoal: use a conta Microsoft pessoal (@outlook.com, @hotmail.com, etc.).";
        } else {
          els.guidance.textContent =
            SLUG_GUIDANCE[provider.slug] || SLUG_GUIDANCE.oauth_auto;
        }
      } else {
        els.guidance.textContent =
          SLUG_GUIDANCE[provider.slug] || SLUG_GUIDANCE.manual;
      }
    }

    if (els.oauthBtn) {
      els.oauthBtn.hidden = !supportsAuto;
      els.oauthBtn.disabled =
        !supportsAuto ||
        addDriveState.autoConnectInFlight ||
        addDriveState.oauthConnected;
      els.oauthBtn.classList.toggle("primary", supportsAuto);
      els.oauthBtn.textContent = addDriveState.oauthConnected
        ? "Conta ligada"
        : "Configuração automática — conectar conta";
    }

    if (els.manualBtn) {
      const demoteManual = supportsAuto;
      els.manualBtn.classList.toggle("ghost", demoteManual);
      els.manualBtn.classList.toggle("primary", !demoteManual);
      els.manualBtn.textContent = demoteManual
        ? "Alternativa: configurar no terminal"
        : "Configurar manualmente (terminal)";
    }

    if (autoStart && addDriveState.currentStep === 3) {
      await maybeAutoStartAddDriveOAuth(supportsAuto);
    }
  }

  async function maybeAutoStartAddDriveOAuth(supportsAuto) {
    const slug = canonicalProviderSlug(addDriveState.selectedSlug);
    if (slug !== "drive" || !supportsAuto) return;
    if (
      addDriveState.autoConnectAttempted ||
      addDriveState.oauthConnected ||
      addDriveState.autoConnectInFlight
    ) {
      return;
    }
    if (!bridge || !bridge.command) return;

    addDriveState.autoConnectAttempted = true;
    await runAddDriveAutoConnect();
  }

  function validateAddDriveStep(step) {
    if (step === 1 && !addDriveState.selectedSlug) {
      setAddDriveFeedback("Escolha um provedor para continuar.", "error");
      return false;
    }
    if (step === 2) {
      const els = getAddDriveEls();
      if (els.labelInput && !els.labelInput.value.trim()) {
        els.labelInput.focus();
        setAddDriveFeedback("Indique um nome para a unidade.", "error");
        return false;
      }
      const labelErr = validateAddDriveLabel(els.labelInput.value.trim());
      if (labelErr) {
        if (els.labelInput) els.labelInput.focus();
        setAddDriveFeedback(labelErr, "error");
        return false;
      }
      const mountVal = els.mountInput ? els.mountInput.value.trim() : "";
      const mountErr = validateAddDriveMount(mountVal);
      if (mountErr) {
        if (els.mountInput) els.mountInput.focus();
        setAddDriveFeedback(mountErr, "error");
        return false;
      }
      const sharedErr = validateAddDriveSharedScope();
      if (sharedErr) {
        if (els.sharedLinkInput) els.sharedLinkInput.focus();
        setAddDriveFeedback(sharedErr, "error");
        return false;
      }
    }
    return true;
  }

  function goAddDriveNext() {
    if (!validateAddDriveStep(addDriveState.currentStep)) return;
    setAddDriveFeedback("");
    setAddDriveStep(addDriveState.currentStep + 1);
  }

  function goAddDrivePrev() {
    setAddDriveFeedback("");
    setAddDriveStep(addDriveState.currentStep - 1);
  }

  function resetAddDriveForm() {
    const els = getAddDriveEls();
    if (!els.form) return;

    els.form.reset();
    if (els.sessionInput) els.sessionInput.checked = true;
    if (els.connectNowInput) els.connectNowInput.checked = true;

    addDriveState.selectedSlug = "";
    addDriveState.availableMountLetters = [];
    addDriveState.remoteAutoDirty = false;
    if (els.mountInput) {
      els.mountInput.replaceChildren();
      els.mountInput.disabled = true;
    }
    addDriveState.autoConnectInFlight = false;
    addDriveState.autoConnectAttempted = false;
    addDriveState.oauthConnected = false;
    addDriveState.onedriveType = "personal";
    addDriveState.cloudSetupInFlight = false;
    addDriveState.cloudSetupLastProvider = null;
    addDriveState.guidedProvider = null;
    addDriveState.guidedAnswersCache = {};
    addDriveState.teraboxLoginAutoOpened = false;
    if (els.assistantModeInput) {
      addDriveState.assistantMode = els.assistantModeInput.checked;
    }

    setCloudSetupRunning(false);
    if (els.cloudSetupProgress) els.cloudSetupProgress.hidden = true;

    setAddDriveStep(1);

    if (els.guidance) els.guidance.textContent = SLUG_GUIDANCE.default;
    if (els.status) {
      els.status.hidden = true;
      els.status.textContent = "";
      els.status.className = "form-status";
    }
    if (els.oauthBtn) {
      els.oauthBtn.hidden = true;
      els.oauthBtn.disabled = true;
    }
    if (els.authActions) els.authActions.dataset.addAuthMode = "pending";
    syncOnedriveTypePanelVisibility();

    syncAddDriveSharedFieldsVisibility();
    refreshAddDriveSharedHints().catch(() => {});

    if (els.guidedPanel) els.guidedPanel.hidden = true;
    if (els.guidedFields) els.guidedFields.innerHTML = "";

    setAddDriveFeedback("");
    renderAddDriveProviders();
  }

  function renderAddDriveProviders() {
    const els = getAddDriveEls();
    if (!els.grid || !els.template) return;

    els.grid.innerHTML = "";
    const query = (els.search && els.search.value ? els.search.value : "").trim().toLowerCase();
    const visible = sortAddDriveProviders(
      addDriveState.providers.filter((p) => {
        if (!query) return true;
        return (
          p.slug.toLowerCase().includes(query) ||
          (p.label || "").toLowerCase().includes(query) ||
          (p.icon_slug || "").toLowerCase().includes(query)
        );
      })
    );

    visible.forEach((provider) => {
      const fragment = els.template.content.cloneNode(true);
      const button = fragment.querySelector(".provider-card");
      if (!button) return;

      button.dataset.slug = provider.slug;
      button.setAttribute(
        "aria-checked",
        provider.slug === addDriveState.selectedSlug ? "true" : "false"
      );
      if (provider.slug === addDriveState.selectedSlug) {
        button.classList.add("is-selected");
      }

      const iconEl = fragment.querySelector('[data-role="icon"]');
      const nameEl = fragment.querySelector('[data-role="name"]');
      if (iconEl) {
        iconEl.innerHTML = providerIconHtml(provider.icon_slug || provider.slug);
      }
      if (nameEl) nameEl.textContent = provider.label || provider.slug;

      const badgeEl = fragment.querySelector('[data-role="auto-badge"]');
      if (badgeEl) {
        const showAuto = providerSupportsAutoConnect(provider);
        badgeEl.hidden = !showAuto;
      }

      const expBadge = fragment.querySelector('[data-role="exp-badge"]');
      if (expBadge) {
        expBadge.hidden = !provider.experimental;
        if (provider.experimental) {
          expBadge.textContent = provider.backend_available === false ? "Exp." : "Exp.";
          expBadge.title =
            provider.slug === "terabox"
              ? "TeraBox (experimental) — rclone não oficial"
              : "Provedor experimental";
        }
      }

      button.addEventListener("click", () => selectAddDriveProvider(provider));
      els.grid.appendChild(fragment);
    });

    if (visible.length === 0 && query) {
      els.grid.innerHTML = `<p class="empty-hint">Nenhum provedor coincide com «${escapeHtml(query)}».</p>`;
    }
  }

  async function selectAddDriveProvider(provider) {
    if (
      addDriveState.guidedProvider &&
      addDriveState.guidedProvider !== provider.slug
    ) {
      const previous = addDriveState.providers.find(
        (item) => item.slug === addDriveState.guidedProvider
      );
      if (previous) cacheGuidedAnswers(previous);
    }
    if (!isTeraboxProvider(provider)) {
      addDriveState.teraboxLoginAutoOpened = false;
    }
    addDriveState.selectedSlug = provider.slug;
    renderAddDriveProviders();
    renderGuidedSetupPanel(provider);

    const addEls = getAddDriveEls();
    if (addEls.guidance) {
      const key = provider.slug;
      addEls.guidance.textContent =
        SLUG_GUIDANCE[key] ||
        (providerUsesGuidedSetup(provider) ? SLUG_GUIDANCE.guided : SLUG_GUIDANCE.default);
    }

    if (isAddDriveAssistantMode() && addDriveState.currentStep === 1) {
      if (isTeraboxProvider(provider) && !guidedAnswersComplete(provider)) {
        addDriveState.teraboxLoginAutoOpened = true;
        setAddDriveFeedback("A abrir login TeraBox no RDrive…", "busy");
        const captured = await openTeraboxEmbeddedBrowser({
          manual: false,
          autoTest: false,
          fallbackBrowser: true,
        });
        if (captured && captured.cancelled) {
          setAddDriveFeedback("Login TeraBox cancelado.", "warn");
          return;
        }
        if (!guidedAnswersComplete(provider)) {
          setAddDriveFeedback(
            "Complete o login TeraBox no navegador integrado ou use «Abrir no browser do sistema».",
            "warn"
          );
          return;
        }
        await startCloudSetupAgentForProvider(provider);
        return;
      }
      if (providerUsesGuidedSetup(provider) && !guidedAnswersComplete(provider)) {
        setAddDriveFeedback(
          "Preencha as credenciais no formulário guiado e clique em «Ligar e guardar».",
          "ok"
        );
        return;
      }
      await startCloudSetupAgentForProvider(provider);
      return;
    }

    if (!addDriveState.remoteAutoDirty) {
      await suggestAddDriveRemote();
    }
    refreshAddDriveSharedHints().catch(() => {});
    await updateAddDriveStep3UI();

    if (addDriveState.currentStep === 1) {
      goAddDriveNext();
    }
  }

  async function suggestAddDriveRemote() {
    const els = getAddDriveEls();
    if (!addDriveState.selectedSlug || !bridge || !bridge.command || !els.remoteInput) return;

    try {
      const result = await bridge.command("suggestRemote", {
        provider: canonicalProviderSlug(addDriveState.selectedSlug),
        label: els.labelInput ? els.labelInput.value.trim() : "",
        ...getOnedriveConnectPayload(),
      });
      if (result && result.remote && !addDriveState.remoteAutoDirty) {
        els.remoteInput.value = result.remote;
      }
    } catch {
      /* ignore */
    }
  }

  function onAutoConnectProgress(payload) {
    const els = getAddDriveEls();
    addDriveState.autoConnectInFlight = true;
    if (els.oauthBtn) els.oauthBtn.disabled = true;
    if (!els.status) return;
    els.status.hidden = false;
    els.status.className = "form-status loading";
    els.status.textContent = (payload && payload.message) || "A processar…";
  }

  function onAutoConnectFinished(payload) {
    const els = getAddDriveEls();
    addDriveState.autoConnectInFlight = false;
    updateAddDriveStep3UI().catch(() => {});
    if (!els.status) return;

    els.status.hidden = false;
    if (payload && payload.success) {
      addDriveState.oauthConnected = true;
      els.status.className = "form-status success";
      els.status.textContent = payload.message || "Conta conectada.";
      if (payload.remote_name && els.remoteInput) {
        els.remoteInput.value = payload.remote_name;
        addDriveState.remoteAutoDirty = true;
      }
      setAddDriveFeedback(payload.message || "Conta conectada.", "ok");
    } else {
      els.status.className = "form-status error";
      els.status.textContent = (payload && payload.message) || "Falha na conexão.";
      setAddDriveFeedback((payload && payload.message) || "Falha na conexão.", "error");
    }
  }

  async function prepareAddDriveView() {
    resetAddDriveForm();
    if (!bridge || !bridge.command) {
      addDriveState.providers = sortAddDriveProviders(
        MOCK_PROVIDERS.map((p) => normalizeProvider({ ...p }))
      );
      renderAddDriveProviders();
      return;
    }

    try {
      const result = await bridge.command("listProviders", {});
      addDriveState.providers = sortAddDriveProviders(
        ((result && result.providers) || [])
          .map(normalizeProvider)
          .filter((p) => isUserFacingProvider(p.slug))
      );
      renderAddDriveProviders();
    } catch (err) {
      setAddDriveFeedback(
        err && err.message ? err.message : "Não foi possível carregar provedores.",
        "error"
      );
    }
  }

  async function runAddDriveAutoConnect() {
    const els = getAddDriveEls();
    if (!addDriveState.selectedSlug) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }

    const provider = getSelectedAddDriveProvider();
    if (!providerSupportsAutoConnect(provider)) {
      setAddDriveFeedback(
        "Este provedor não suporta configuração automática. Use o terminal.",
        "error"
      );
      return;
    }

    const remoteName = els.remoteInput ? els.remoteInput.value.trim() : "";
    addDriveState.autoConnectInFlight = true;
    if (els.oauthBtn) els.oauthBtn.disabled = true;
    if (els.status) {
      els.status.hidden = false;
      els.status.className = "form-status loading";
      els.status.textContent = "A abrir o navegador para login OAuth…";
    }

    try {
      await bridge.command("runAutoConnect", {
        provider: canonicalProviderSlug(addDriveState.selectedSlug),
        remote_name: remoteName,
        label: els.labelInput ? els.labelInput.value.trim() : "",
        ...getOnedriveConnectPayload(),
      });
    } catch (err) {
      addDriveState.autoConnectInFlight = false;
      updateAddDriveStep3UI().catch(() => {});
      if (els.status) {
        els.status.className = "form-status error";
        els.status.textContent = (err && err.message) || "Falha ao iniciar OAuth.";
      }
      setAddDriveFeedback((err && err.message) || "Falha ao iniciar OAuth.", "error");
    }
  }

  async function runAddDriveManualSetup() {
    if (!addDriveState.selectedSlug) {
      setAddDriveFeedback("Escolha um provedor primeiro.", "error");
      return;
    }
    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }

    const els = getAddDriveEls();
    try {
      const info = await bridge.command("launchManualSetup", {
        provider: addDriveState.selectedSlug,
        remote_name: els.remoteInput ? els.remoteInput.value.trim() : "",
      });
      setAddDriveFeedback(
        `Assistente aberto (backend ${info.backend || addDriveState.selectedSlug}). Documentação no navegador.`,
        "ok"
      );
    } catch (err) {
      setAddDriveFeedback((err && err.message) || "Falha no assistente.", "error");
    }
  }

  async function submitAddDriveForm(event) {
    if (event) event.preventDefault();

    const els = getAddDriveEls();
    if (!addDriveState.selectedSlug) {
      setAddDriveFeedback("Escolha um provedor antes de guardar.", "error");
      return;
    }
    if (!els.labelInput || !els.labelInput.value.trim()) {
      if (els.labelInput) els.labelInput.focus();
      setAddDriveFeedback("Dê um nome à unidade.", "error");
      return;
    }

    const label = els.labelInput.value.trim();
    const labelErr = validateAddDriveLabel(label);
    if (labelErr) {
      if (els.labelInput) els.labelInput.focus();
      setAddDriveFeedback(labelErr, "error");
      return;
    }

    const mountVal = els.mountInput ? els.mountInput.value.trim() : "";
    const mountErr = validateAddDriveMount(mountVal);
    if (mountErr) {
      if (els.mountInput) els.mountInput.focus();
      setAddDriveFeedback(mountErr, "error");
      return;
    }

    const sharedErr = validateAddDriveSharedScope();
    if (sharedErr) {
      if (els.sharedLinkInput) els.sharedLinkInput.focus();
      setAddDriveFeedback(sharedErr, "error");
      return;
    }

    if (!bridge || !bridge.command) {
      setAddDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }

    setAddDriveFeedback("A guardar…", "busy");

    try {
      await bridge.command("saveDrive", {
        label,
        provider: addDriveState.selectedSlug,
        remote_name: els.remoteInput ? els.remoteInput.value.trim() : "",
        mountpoint: mountVal,
        connect_at_startup: els.startupInput ? els.startupInput.checked : false,
        session_only: els.sessionInput ? els.sessionInput.checked : false,
        connect_now: els.connectNowInput ? els.connectNowInput.checked : false,
        map_shared_only: els.mapSharedOnlyInput ? els.mapSharedOnlyInput.checked : false,
        shared_link: els.sharedLinkInput ? els.sharedLinkInput.value.trim() : "",
        root_path: els.rootPathInput ? els.rootPathInput.value.trim() : "",
      });
      resetAddDriveForm();
      showView(VIEW_HOME);
    } catch (err) {
      setAddDriveFeedback((err && err.message) || "Falha ao guardar.", "error");
    }
  }

  function wireAddDriveForm() {
    if (addDriveFormWired) return;
    const els = getAddDriveEls();
    if (!els.form) return;
    addDriveFormWired = true;

    els.form.addEventListener("submit", submitAddDriveForm);

    if (els.search) {
      els.search.addEventListener("input", () => renderAddDriveProviders());
    }

    if (els.labelInput) {
      els.labelInput.addEventListener("input", () => {
        if (addDriveState.remoteAutoDirty) return;
        suggestAddDriveRemote().catch(() => {});
      });
    }

    if (els.remoteInput) {
      els.remoteInput.addEventListener("input", () => {
        addDriveState.remoteAutoDirty = els.remoteInput.value.trim().length > 0;
      });
    }

    if (els.mapSharedOnlyInput) {
      els.mapSharedOnlyInput.addEventListener("change", () => {
        syncAddDriveSharedFieldsVisibility();
      });
    }

    if (els.assistantModeInput) {
      els.assistantModeInput.addEventListener("change", () => {
        addDriveState.assistantMode = els.assistantModeInput.checked;
      });
    }

    if (els.onedriveTypePanel) {
      els.onedriveTypePanel.addEventListener("change", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement) || target.name !== "onedrive-type") {
          return;
        }
        addDriveState.onedriveType = target.value === "business" ? "business" : "personal";
        if (!addDriveState.remoteAutoDirty) {
          suggestAddDriveRemote().catch(() => {});
        }
        if (addDriveState.currentStep === 3) {
          updateAddDriveStep3UI().catch(() => {});
        }
      });
    }

  }

  function handleBridgeEvent(evt) {
    if (!evt || !evt.type) return;

    if (evt.type === "toast" && evt.message) {
      const settingsView = document.getElementById(VIEW_SETTINGS);
      const addView = document.getElementById(VIEW_ADD_DRIVE);
      if (addView && addView.classList.contains("active")) {
        setAddDriveFeedback(evt.message, evt.tone || "ok");
      } else if (settingsView && settingsView.classList.contains("active")) {
        setSettingsFeedback(evt.message, evt.tone || "ok");
      } else {
        const chip = document.getElementById("status-chip");
        if (chip) {
          chip.textContent = evt.message;
          chip.dataset.tone = evt.tone || "ok";
          chip.dataset.busy = "false";
        }
      }
      return;
    }

    if (evt.type === "auto_connect_progress") {
      const addView = document.getElementById(VIEW_ADD_DRIVE);
      if (addView && addView.classList.contains("active")) {
        onAutoConnectProgress(evt);
      }
      return;
    }

    if (evt.type === "auto_connect_finished") {
      const addView = document.getElementById(VIEW_ADD_DRIVE);
      if (addView && addView.classList.contains("active")) {
        onAutoConnectFinished(evt);
      }
      return;
    }

    if (evt.type === "cloud_setup_progress") {
      const addView = document.getElementById(VIEW_ADD_DRIVE);
      if (addView && addView.classList.contains("active")) {
        onCloudSetupProgress(evt);
      }
      return;
    }

    if (evt.type === "cloud_setup_finished") {
      const addView = document.getElementById(VIEW_ADD_DRIVE);
      if (addView && addView.classList.contains("active")) {
        onCloudSetupFinished(evt);
      }
      return;
    }

    if (evt.type === "activity" && evt.entry) {
      prependActivityEntry(evt.entry);
      return;
    }

    if (evt.type === "drives") {
      applySnapshot({ drives: Array.isArray(evt.drives) ? evt.drives : [] });
      return;
    }

    if (evt.type === "integrity") {
      applySnapshot({
        integrity: evt.levels && typeof evt.levels === "object" ? evt.levels : {},
      });
      return;
    }

    if (evt.type === "status_text" && evt.text != null) {
      applySnapshot({ statusText: String(evt.text), tone: "idle", busy: false });
      return;
    }

    if (evt.type === "diag_speed_done") {
      onDiagSpeedDone(evt);
    }
  }

  // --- DEFINIÇÕES → TESTES ---

  let diagBusy = false;

  function getDiagTab() {
    return document.getElementById("tab-testes");
  }

  function setDiagOutput(elementId, text) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = text || "";
  }

  function setDiagBusy(busy) {
    diagBusy = busy;
    const tab = getDiagTab();
    if (tab) tab.dataset.busy = busy ? "true" : "false";
    const speedBtn = document.getElementById("diag-speed-btn");
    const speedCancel = document.getElementById("diag-speed-cancel-btn");
    const progress = document.getElementById("diag-speed-progress");
    if (speedBtn && !speedBtn.dataset.speedRunning) {
      speedBtn.disabled = busy;
    }
    if (speedCancel) speedCancel.disabled = !speedBtn || !speedBtn.dataset.speedRunning;
    if (progress) progress.hidden = !(speedBtn && speedBtn.dataset.speedRunning === "true");
  }

  function fillDiagSelect(selectId, values, previous) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const keep = previous != null ? previous : select.value;
    select.replaceChildren();
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "—";
    select.appendChild(blank);
    (values || []).forEach((value) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    });
    if (keep && [...select.options].some((o) => o.value === keep)) {
      select.value = keep;
    }
  }

  async function refreshDiagnosticOptions() {
    if (!bridge || !bridge.command) return;
    try {
      const data = await bridge.command("listDiagnosticOptions", {});
      const remotes = (data && data.remotes) || [];
      const letters = (data && data.letters) || [];
      fillDiagSelect("diag-remote-select", remotes);
      fillDiagSelect("diag-speed-select", remotes);
      fillDiagSelect("diag-cleanup-letter", letters);
      const cleanupBtn = document.getElementById("diag-cleanup-btn");
      if (cleanupBtn) {
        cleanupBtn.disabled = !(data && data.cleanupEnabled);
      }
    } catch (_err) {
      /* silencioso — feedback nas acções */
    }
  }

  async function refreshDiagnosticFeatureFlags() {
    if (!bridge || !bridge.command) {
      setDiagOutput("diag-features-output", "Disponível com o RDrive em execução.");
      return;
    }
    try {
      const data = await bridge.command("getFeatureFlags", {});
      const lines = (data && data.lines) || [];
      setDiagOutput("diag-features-output", lines.join("\n"));
    } catch (err) {
      setDiagOutput(
        "diag-features-output",
        err && err.message ? err.message : "Falha ao actualizar checklist."
      );
    }
  }

  function onDiagSpeedDone(evt) {
    const speedBtn = document.getElementById("diag-speed-btn");
    const speedCancel = document.getElementById("diag-speed-cancel-btn");
    const progress = document.getElementById("diag-speed-progress");
    if (speedBtn) {
      speedBtn.textContent = "Iniciar teste";
      delete speedBtn.dataset.speedRunning;
      speedBtn.disabled = false;
    }
    if (speedCancel) speedCancel.disabled = true;
    if (progress) progress.hidden = true;
    setDiagBusy(false);

    if (evt.cancelled) {
      setDiagOutput("diag-speed-output", "Cancelado.");
      return;
    }
    const mark = evt.ok ? "✓" : "✗";
    const parts = [`${mark} ${evt.message || "Teste concluído."}`];
    if (evt.upload_mbps != null) parts.push(`Upload: ${Number(evt.upload_mbps).toFixed(2)} MB/s`);
    if (evt.download_mbps != null) {
      parts.push(`Download: ${Number(evt.download_mbps).toFixed(2)} MB/s`);
    }
    setDiagOutput("diag-speed-output", parts.join("\n"));
  }

  async function runDiagBridge(commandName, args, outputId, busyMessage) {
    if (!bridge || !bridge.command) {
      setSettingsFeedback("Disponível apenas com o RDrive em execução.", "error");
      if (outputId) {
        setDiagOutput(outputId, "Disponível apenas com o RDrive em execução.");
      }
      return null;
    }
    if (outputId) setDiagOutput(outputId, busyMessage || "A processar…");
    setDiagBusy(true);
    setSettingsFeedback(busyMessage || "A processar…", "busy");
    try {
      const data = await bridge.command(commandName, args || {});
      if (outputId && data && Array.isArray(data.lines)) {
        setDiagOutput(outputId, data.lines.join("\n"));
      }
      setSettingsFeedback("Operação concluída.", "ok");
      return data;
    } catch (err) {
      const msg = err && err.message ? err.message : "Operação falhou.";
      if (outputId) setDiagOutput(outputId, `✗ ${msg}`);
      setSettingsFeedback(msg, "error");
      return null;
    } finally {
      const speedBtn = document.getElementById("diag-speed-btn");
      if (!speedBtn || speedBtn.dataset.speedRunning !== "true") {
        setDiagBusy(false);
      }
    }
  }

  async function handleDiagAction(action) {
    const remoteSelect = document.getElementById("diag-remote-select");
    const speedSelect = document.getElementById("diag-speed-select");
    const letterSelect = document.getElementById("diag-cleanup-letter");

    switch (action) {
      case "diag-system-check":
        await runDiagBridge(
          "runSystemChecks",
          {},
          "diag-system-output",
          "A verificar…"
        );
        await refreshDiagnosticOptions();
        break;
      case "diag-remote-test": {
        const remote = remoteSelect ? remoteSelect.value.trim() : "";
        if (!remote) {
          setSettingsFeedback("Seleccione um remote.", "error");
          return;
        }
        await runDiagBridge(
          "testRemote",
          { remote },
          "diag-remote-output",
          `A testar «${remote}»…`
        );
        await refreshDiagnosticOptions();
        break;
      }
      case "diag-speed-start": {
        const remote = speedSelect ? speedSelect.value.trim() : "";
        if (!remote) {
          setSettingsFeedback("Seleccione um remote.", "error");
          return;
        }
        const ok = window.confirm(
          "O teste envia ~1 MB para o remote (pasta RDrive_speedtest) e descarrega de volta.\n\nConsome quota e banda. Continuar?"
        );
        if (!ok) return;
        const speedBtn = document.getElementById("diag-speed-btn");
        const speedCancel = document.getElementById("diag-speed-cancel-btn");
        const progress = document.getElementById("diag-speed-progress");
        if (speedBtn) {
          speedBtn.textContent = "A correr…";
          speedBtn.dataset.speedRunning = "true";
          speedBtn.disabled = true;
        }
        if (speedCancel) speedCancel.disabled = false;
        if (progress) progress.hidden = false;
        setDiagOutput("diag-speed-output", "Teste em curso…");
        setDiagBusy(true);
        setSettingsFeedback("Teste de velocidade em curso…", "busy");
        try {
          await bridge.command("startSpeedTest", { remote });
        } catch (err) {
          onDiagSpeedDone({
            ok: false,
            cancelled: false,
            message: err && err.message ? err.message : "Falha ao iniciar teste.",
          });
          setSettingsFeedback(
            err && err.message ? err.message : "Falha ao iniciar teste.",
            "error"
          );
        }
        break;
      }
      case "diag-speed-cancel":
        if (bridge && bridge.command) {
          try {
            await bridge.command("cancelSpeedTest", {});
            setDiagOutput("diag-speed-output", "Cancelamento solicitado…");
          } catch (err) {
            setSettingsFeedback(err && err.message ? err.message : "Falha ao cancelar.", "error");
          }
        }
        break;
      case "diag-mount-check":
        await runDiagBridge("runMountChecks", {}, "diag-mount-output", "A verificar drives…");
        await refreshDiagnosticOptions();
        break;
      case "diag-human-log": {
        if (!bridge || !bridge.command) {
          setDiagOutput("diag-mount-output", "Disponível apenas com o RDrive em execução.");
          return;
        }
        setDiagOutput("diag-mount-output", "A carregar human.log…");
        try {
          const data = await bridge.command("getHumanLogTail", { limit: 80 });
          const lines = (data && data.lines) || [];
          const path = (data && data.path) || "human.log";
          setDiagOutput(
            "diag-mount-output",
            lines.length ? lines.join("\n") : `(vazio — ${path})`
          );
          setSettingsFeedback("human.log actualizado.", "ok");
        } catch (err) {
          setDiagOutput(
            "diag-mount-output",
            err && err.message ? err.message : "Falha ao ler human.log."
          );
        }
        break;
      }
      case "diag-force-cleanup": {
        const letter = letterSelect ? letterSelect.value.trim() : "";
        if (!letter) {
          setSettingsFeedback("Seleccione uma letra de unidade guardada.", "error");
          return;
        }
        await runDiagBridge(
          "forceCleanupLetter",
          { letter },
          "diag-mount-output",
          `A limpar mapeamento de ${letter}…`
        );
        await refreshDiagnosticOptions();
        break;
      }
      case "diag-refresh-features":
        await refreshDiagnosticFeatureFlags();
        setSettingsFeedback("Checklist actualizado.", "ok");
        break;
      default:
        break;
    }
  }

  // --- NAVEGAÇÃO TABS ---

  function showTab(tabId) {
    const form = document.getElementById("settings-form");
    if (!form) return;

    form.querySelectorAll(".tab-content").forEach((panel) => {
      panel.classList.remove("active");
      panel.hidden = true;
    });

    form.querySelectorAll(".menu-item").forEach((btn) => {
      btn.classList.remove("active");
    });

    const panel = document.getElementById(tabId);
    if (panel) {
      panel.classList.add("active");
      panel.hidden = false;
    }

    const menuBtn = form.querySelector(`.menu-item[data-tab="${tabId}"]`);
    if (menuBtn) menuBtn.classList.add("active");

    if (tabId === "tab-testes") {
      refreshDiagnosticOptions();
      refreshDiagnosticFeatureFlags();
    }
  }

  // --- DEFINIÇÕES ---

  const FLOAT_SETTING_KEYS = new Set(["watchdog_hot_reload_idle_sec"]);

  function parseSettingsNumber(key, raw) {
    if (FLOAT_SETTING_KEYS.has(key)) {
      const n = parseFloat(raw);
      return Number.isFinite(n) ? n : 0;
    }
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  }

  function setSettingsFeedback(message, tone) {
    const el = document.getElementById("settings-feedback");
    if (!el) return;
    el.textContent = message || "";
    if (tone) el.dataset.tone = tone;
    else delete el.dataset.tone;
  }

  function clearVaultPasswordFields() {
    const ids = [
      "set-vault-current",
      "set-vault-new",
      "set-vault-confirm",
      "set-vault-enable-password",
      "set-vault-enable-confirm",
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
  }

  function updateVaultModeUi(enabled) {
    const on = enabled != null ? Boolean(enabled) : Boolean(
      document.getElementById("set-vault-enabled") &&
        document.getElementById("set-vault-enabled").checked
    );
    const hint = document.getElementById("set-vault-enabled-hint");
    const enablePanel = document.getElementById("vault-enable-panel");
    const toggle = document.getElementById("set-vault-enabled");
    if (toggle) toggle.checked = on;
    if (hint) {
      const legacyEnc =
        cachedSettings && cachedSettings.vault_legacy_enc_present && !on;
      hint.textContent = on
        ? "Experimental — senha mestra obrigatória no arranque; dados encriptados localmente"
        : legacyEnc
          ? "Modo simples activo. Existem ficheiros .enc antigos — active o cofre com a senha mestra para os voltar a usar."
          : "Modo simples — dados no disco sem encriptação do cofre (menos seguro)";
      hint.classList.toggle("warn", !on);
      hint.classList.toggle("vault-experimental-on", on);
    }
    document.querySelectorAll(".vault-only-section").forEach((section) => {
      section.hidden = !on;
    });
  }

  function updateVaultEnablePanelVisibility() {
    const toggle = document.getElementById("set-vault-enabled");
    const panel = document.getElementById("vault-enable-panel");
    if (!toggle || !panel) return;
    const wasEnabled = Boolean(cachedSettings && cachedSettings.vault_enabled);
    const turningOn = toggle.checked && !wasEnabled;
    panel.hidden = !turningOn;
    if (!turningOn) {
      ["set-vault-enable-password", "set-vault-enable-confirm"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });
    }
  }

  /** Estado serializado comparável (vault/smtp password só se preenchidos). */
  function serializeSettingsFormState() {
    const form = document.getElementById("settings-form");
    if (!form) return "";

    const state = {};

    form.querySelectorAll("input[name]").forEach((input) => {
      const key = input.name;
      if (!key || key === "risk_accepted") return;

      if (input.type === "checkbox") {
        state[key] = input.checked;
      } else if (input.type === "number") {
        state[key] = parseSettingsNumber(key, input.value);
      } else if (input.type === "password") {
        const v = input.value.trim();
        if (v) state[key] = v;
      } else {
        state[key] = input.value.trim();
      }
    });

    const riskAccepted = document.getElementById("set-accept-risk");
    if (riskAccepted) state.risk_accepted = riskAccepted.checked;

    const smtpToggle = document.getElementById("set-smtp-advanced");
    if (smtpToggle) state._smtpOpen = smtpToggle.checked;

    const vault = {};
    ["set-vault-current", "set-vault-new", "set-vault-confirm"].forEach((id) => {
      const el = document.getElementById(id);
      const v = el ? el.value.trim() : "";
      if (v) vault[id] = v;
    });
    if (Object.keys(vault).length) state._vault = vault;

    return JSON.stringify(state);
  }

  function setSettingsFormDirty(dirty) {
    const form = document.getElementById("settings-form");
    if (!form) return;
    form.dataset.dirty = dirty ? "true" : "false";
  }

  function captureSettingsFormSnapshot() {
    settingsFormSnapshot = serializeSettingsFormState();
    setSettingsFormDirty(false);
  }

  function updateSettingsFormDirtyState() {
    if (!settingsFormSnapshot) return;
    const current = serializeSettingsFormState();
    setSettingsFormDirty(current !== settingsFormSnapshot);
  }

  function updateSmtpPanelVisibility(open) {
    const form = document.getElementById("settings-form");
    const panel = document.getElementById("smtp-panel");
    const toggle = document.getElementById("set-smtp-advanced");
    if (!form || !panel) return;
    const show = open != null ? open : toggle && toggle.checked;
    form.dataset.smtpOpen = show ? "true" : "false";
    panel.hidden = !show;
  }

  function readShowHomeTestToolsFromStorage() {
    try {
      const value = localStorage.getItem(SHOW_HOME_TEST_TOOLS_KEY);
      if (value === "1") return true;
      if (value === "0") return false;
    } catch (_err) {
      /* ignore */
    }
    return null;
  }

  function writeShowHomeTestToolsToStorage(enabled) {
    try {
      localStorage.setItem(SHOW_HOME_TEST_TOOLS_KEY, enabled ? "1" : "0");
    } catch (_err) {
      /* ignore */
    }
  }

  function isMockUiMode() {
    return typeof QWebChannel === "undefined";
  }

  function resolveShowHomeTestTools(settings) {
    const source = settings && typeof settings === "object" ? settings : cachedSettings;
    if (source && Object.prototype.hasOwnProperty.call(source, "show_home_test_tools")) {
      return Boolean(source.show_home_test_tools);
    }
    if (isMockUiMode()) {
      const stored = readShowHomeTestToolsFromStorage();
      if (stored !== null) return stored;
    }
    return false;
  }

  function updateDevTestToolbarVisibility(settings) {
    const toolbar = document.getElementById("dev-test-toolbar");
    if (!toolbar) return;
    toolbar.hidden = !resolveShowHomeTestTools(settings);
  }

  function applySettingsToForm(settings) {
    const form = document.getElementById("settings-form");
    if (!form) return;

    cachedSettings = { ...DEFAULT_SETTINGS, ...settings };

    form.querySelectorAll("input[name]").forEach((input) => {
      const key = input.name;
      if (!key || !(key in cachedSettings)) return;

      if (input.type === "checkbox") {
        if (key === "risk_accepted") return;
        input.checked = Boolean(cachedSettings[key]);
      } else if (input.type === "number") {
        const num = cachedSettings[key];
        input.value = num != null && num !== "" ? String(num) : "";
      } else if (input.type === "password") {
        if (key === "smtp_password") input.value = "";
      } else if (input.type !== "password") {
        input.value = cachedSettings[key] != null ? String(cachedSettings[key]) : "";
      }
    });

    const riskAccepted = document.getElementById("set-accept-risk");
    if (riskAccepted) {
      riskAccepted.checked = Boolean(cachedSettings.risk_acceptance_timestamp);
    }

    const hasSmtp =
      String(cachedSettings.smtp_host || "").trim() ||
      String(cachedSettings.smtp_user || "").trim();
    const smtpToggle = document.getElementById("set-smtp-advanced");
    if (smtpToggle) smtpToggle.checked = hasSmtp;
    updateSmtpPanelVisibility(hasSmtp);
    updateVaultModeUi(Boolean(cachedSettings.vault_enabled));
    updateVaultEnablePanelVisibility();

    clearVaultPasswordFields();
    captureSettingsFormSnapshot();
    updateDevTestToolbarVisibility(cachedSettings);
  }

  function collectSettingsPatch() {
    const form = document.getElementById("settings-form");
    const patch = {};
    if (!form) return patch;

    form.querySelectorAll("input[name]").forEach((input) => {
      const key = input.name;
      if (!key || key === "risk_accepted") return;

      if (input.type === "checkbox") {
        patch[key] = input.checked;
      } else if (input.type === "number") {
        patch[key] = parseSettingsNumber(key, input.value);
      } else if (input.type === "password") {
        if (key === "smtp_password") {
          const v = input.value;
          if (v) patch[key] = v;
        }
      } else {
        patch[key] = input.value.trim();
      }
    });

    const riskAccepted = document.getElementById("set-accept-risk");
    if (riskAccepted) {
      patch.risk_accepted = riskAccepted.checked;
    }

    const current = document.getElementById("set-vault-current").value.trim();
    const newPw = document.getElementById("set-vault-new").value.trim();
    const confirm = document.getElementById("set-vault-confirm").value.trim();
    if (current || newPw || confirm) {
      patch.vaultCurrentPassword = current;
      patch.vaultNewPassword = newPw;
      patch.vaultConfirmPassword = confirm;
    }

    const enablePw = (document.getElementById("set-vault-enable-password") || {}).value;
    const enableConfirm = (document.getElementById("set-vault-enable-confirm") || {}).value;
    if (enablePw || enableConfirm) {
      patch.vaultEnablePassword = String(enablePw || "").trim();
      patch.vaultEnableConfirmPassword = String(enableConfirm || "").trim();
    }

    return patch;
  }

  async function loadSettingsFromBridge() {
    if (!bridge || !bridge.command) {
      const settings = { ...DEFAULT_SETTINGS };
      const stored = readShowHomeTestToolsFromStorage();
      if (stored !== null) settings.show_home_test_tools = stored;
      applySettingsToForm(settings);
      return;
    }
    try {
      const result = await bridge.command("getSettings", {});
      const settings = (result && result.settings) || {};
      applySettingsToForm(settings);
      setSettingsFeedback("");
    } catch (err) {
      setSettingsFeedback(
        err && err.message ? err.message : "Falha ao carregar definições.",
        "error"
      );
    }
  }

  async function saveSettings(stayOnPage) {
    if (!bridge || !bridge.command) {
      setSettingsFeedback("Sem ligação ao RDrive — definições não guardadas.", "error");
      return false;
    }

    const patch = collectSettingsPatch();
    const vaultToggle = document.getElementById("set-vault-enabled");
    const wasVaultEnabled = Boolean(cachedSettings && cachedSettings.vault_enabled);
    const wantsVaultEnabled = vaultToggle ? vaultToggle.checked : wasVaultEnabled;

    if (wasVaultEnabled && !wantsVaultEnabled) {
      const ok = await confirmDialog({
        title: "Desactivar cofre?",
        message:
          "Os dados passam a ser guardados em JSON legível no disco, sem encriptação do cofre.\n\n" +
          "Qualquer pessoa com acesso ao perfil local poderá ler unidades e definições.\n\n" +
          "Deseja continuar?",
      });
      if (!ok) {
        if (vaultToggle) vaultToggle.checked = true;
        updateVaultModeUi(true);
        updateVaultEnablePanelVisibility();
        return false;
      }
    }

    if (!wasVaultEnabled && wantsVaultEnabled) {
      const hasDrives = bridgeDrives.length > 0;
      let message =
        "O cofre encriptado é experimental e opcional.\n\n" +
        "Ao activar, o RDrive passa a pedir senha mestra no arranque e guarda unidades/definições " +
        "em ficheiros .enc neste PC.\n\n" +
        "Guarde a senha — sem ela não será possível recuperar os dados encriptados.";
      if (hasDrives) {
        message +=
          "\n\nAs unidades e definições existentes serão encriptadas com a nova senha mestra.";
      }
      const ok = await confirmDialog({
        title: "Activar cofre encriptado (experimental)?",
        message,
      });
      if (!ok) {
        if (vaultToggle) vaultToggle.checked = false;
        updateVaultModeUi(false);
        updateVaultEnablePanelVisibility();
        return false;
      }
      if (hasDrives) {
        patch.vaultEnableConfirmed = true;
      }
    }

    setSettingsFeedback("A guardar…", "busy");

    try {
      await bridge.command("saveSettings", patch);
      Object.assign(cachedSettings, patch);
      if (isMockUiMode() && Object.prototype.hasOwnProperty.call(patch, "show_home_test_tools")) {
        writeShowHomeTestToolsToStorage(Boolean(patch.show_home_test_tools));
      }
      updateDevTestToolbarVisibility(cachedSettings);
      clearVaultPasswordFields();
      updateVaultModeUi(Boolean(patch.vault_enabled != null ? patch.vault_enabled : cachedSettings.vault_enabled));
      updateVaultEnablePanelVisibility();
      captureSettingsFormSnapshot();
      setSettingsFeedback("Definições guardadas.", "ok");
      if (!stayOnPage) showView(VIEW_HOME);
      return true;
    } catch (err) {
      setSettingsFeedback(err && err.message ? err.message : "Falha ao guardar.", "error");
      return false;
    }
  }

  async function prepareSettingsView() {
    await loadSettingsFromBridge();
    showTab("tab-geral");
  }

  // --- ESTADO UI ---

  function integrityCopy(level) {
    switch (level) {
      case "warning":
        return "Atenção";
      case "error":
        return "Risco";
      default:
        return "OK";
    }
  }

  function isDemoDrive(drive) {
    return Boolean(drive && (drive._demo === true || String(drive.id || "").startsWith("demo-")));
  }

  function driveIntegrityLevel(drive, integrityMap) {
    if (drive.integrity_level) return drive.integrity_level;
    const remote = (drive.remote_name || "").trim();
    if (remote && integrityMap && integrityMap[remote]) return integrityMap[remote];
    return "ok";
  }

  function formatMountLabel(mountpoint) {
    const slot = normalizeMountSlot(mountpoint);
    if (!slot) {
      const mountText = (mountpoint || "-").trim();
      return mountText || "-";
    }
    return slot;
  }

  /** Garante sub-grelha toggles | links (paridade com webapp). */
  function ensureDriveActionsLayout(root) {
    const cell = root.querySelector(".cell.actions");
    if (!cell || cell.querySelector(".drive-actions")) return;
    const toggles = cell.querySelector(".toggles");
    const links = cell.querySelector(".links");
    if (!toggles || !links) return;
    const wrap = document.createElement("div");
    wrap.className = "drive-actions";
    cell.replaceChildren(wrap);
    wrap.append(toggles, links);
  }

  function createDemoDriveFromPreset(presetKey) {
    const preset = DEMO_DRIVE_PRESETS[presetKey];
    if (!preset) return null;
    const suffix = Date.now().toString(36);
    return {
      id: `demo-${presetKey}-${suffix}`,
      label: nextUniqueDemoLabel(preset.label),
      provider: preset.provider,
      provider_label: preset.provider_label,
      remote_name: `${preset.remote_name}_${suffix}`,
      mountpoint: suggestLocalMountLetter(undefined, { includeDemo: true }),
      status: preset.status,
      connect_at_startup: preset.connect_at_startup,
      session_only: false,
      integrity_level: preset.integrity_level,
      _demo: true,
    };
  }

  function addDemoDrive(presetKey) {
    const drive = createDemoDriveFromPreset(presetKey);
    if (!drive) return;
    demoDrives.push(drive);
    refreshDriveList();
  }

  function clearDemoDrives() {
    demoDrives = [];
    refreshDriveList();
  }

  function removeDemoDrive(driveId) {
    demoDrives = demoDrives.filter((d) => d.id !== driveId);
    refreshDriveList();
  }

  function patchDemoDrive(driveId, patch) {
    const idx = demoDrives.findIndex((d) => d.id === driveId);
    if (idx < 0) return;
    Object.assign(demoDrives[idx], patch);
    refreshDriveList();
  }

  function ensureScaffoldDemoDrive() {
    const showScaffold =
      isUiDemoEnabled() ||
      (!bridgeIsLive && bridgeDrives.length === 0 && !scaffoldDismissed);
    if (!showScaffold) {
      demoDrives = demoDrives.filter((d) => !d._scaffold);
      return;
    }
    const existing = demoDrives.find((d) => d._scaffold || d.id === MOCK_DRIVES[0].id);
    if (!existing) {
      demoDrives.unshift({ ...MOCK_DRIVES[0] });
    }
  }

  function mergeDrivesForDisplay() {
    return [...bridgeDrives, ...demoDrives];
  }

  function refreshDriveList() {
    ensureScaffoldDemoDrive();
    renderDriveList(mergeDrivesForDisplay(), bridgeIntegrity);
  }

  function findDriveById(driveId) {
    return (
      demoDrives.find((d) => d.id === driveId) ||
      bridgeDrives.find((d) => d.id === driveId) ||
      null
    );
  }

  function resolveDriveSwitch(target) {
    if (!target) return null;
    return (
      target.closest('[data-role="mount-switch"]') ||
      target.closest('[data-role="startup-switch"]') ||
      null
    );
  }

  function applySwitchVisual(switchEl, checked, toggleRow, stateEl, stateLabel) {
    if (!switchEl) return;
    switchEl.setAttribute("aria-checked", String(Boolean(checked)));
    switchEl.classList.toggle("is-on", Boolean(checked));
    if (toggleRow) toggleRow.dataset.state = checked ? "on" : "off";
    if (stateEl && stateLabel != null) stateEl.textContent = stateLabel;
  }

  function applyMountSwitchVisual(row, status) {
    const mState = SWITCH_STATE[status] || SWITCH_STATE.disconnected;
    const mountSwitch = row.querySelector('[data-role="mount-switch"]');
    const mountState = row.querySelector('[data-role="mount-state"]');
    const mountToggleRow = row.querySelector('[data-role="mount-toggle-row"]');
    if (mountSwitch) {
      mountSwitch.setAttribute("aria-checked", String(mState.checked));
      mountSwitch.classList.toggle("is-on", mState.checked);
      mountSwitch.dataset.loading = String(mState.loading);
      mountSwitch.disabled = mState.loading;
    }
    if (mountState) mountState.textContent = mState.label;
    if (mountToggleRow) {
      mountToggleRow.dataset.state = mState.loading ? "loading" : mState.checked ? "on" : "off";
    }
  }

  async function handleDriveRowAction(action, target) {
    const row = target.closest(".drive-row");
    if (!row) return;
    const driveId = row.dataset.driveId;
    if (!driveId) return;

    const drive = findDriveById(driveId);
    if (!drive) return;

    const demo = isDemoDrive(drive);
    const switchEl = resolveDriveSwitch(target) || target;

    if (action === "toggle-connection") {
      if (!switchEl.matches('[data-role="mount-switch"]')) return;
      if (switchEl.disabled || switchEl.dataset.loading === "true") return;
      if (connectionTogglePending.has(driveId)) return;

      const turningOn = drive.status !== "connected";
      connectionTogglePending.add(driveId);
      try {
        if (!turningOn) {
          const confirmed = await confirmDialog(disconnectConfirmCopy(drive));
          if (!confirmed) return;
        }

        const pendingStatus = turningOn ? "connecting" : "disconnecting";
        const demoDoneStatus = turningOn ? "connected" : "disconnected";
        applyMountSwitchVisual(row, demo ? demoDoneStatus : pendingStatus);

        if (demo) {
          patchDemoDrive(driveId, { status: demoDoneStatus });
          showDemoToast(`Demo: ${turningOn ? "Conectado" : "Desligado"}`);
        } else if (bridge && bridge.command) {
          const payload = { id: driveId, turnOn: turningOn };
          if (!turningOn) payload.confirmed = true;
          await bridge.command("toggleConnection", payload).catch((err) => {
            const current = findDriveById(driveId);
            applyMountSwitchVisual(row, current ? current.status : drive.status);
            setChipError(err && err.message ? err.message : "Falha ao alternar ligação");
          });
        }
      } finally {
        connectionTogglePending.delete(driveId);
      }
      return;
    }

    if (action === "set-startup") {
      if (!switchEl.matches('[data-role="startup-switch"]')) return;
      if (switchEl.disabled || switchEl.dataset.loading === "true") return;

      const next = !drive.connect_at_startup;
      const startupState = row.querySelector('[data-role="startup-state"]');
      const startupToggleRow = row.querySelector('[data-role="startup-toggle-row"]');
      applySwitchVisual(
        switchEl,
        next,
        startupToggleRow,
        startupState,
        next ? STARTUP_SWITCH_LABEL.on : STARTUP_SWITCH_LABEL.off
      );

      if (demo) {
        patchDemoDrive(driveId, { connect_at_startup: next });
        showDemoToast(
          `Demo: arranque com Windows ${next ? STARTUP_SWITCH_LABEL.on : STARTUP_SWITCH_LABEL.off}`
        );
      } else if (bridge && bridge.command) {
        bridge
          .command("setStartup", { id: driveId, enabled: next })
          .catch((err) => {
            applySwitchVisual(
              switchEl,
              drive.connect_at_startup,
              startupToggleRow,
              startupState,
              drive.connect_at_startup ? STARTUP_SWITCH_LABEL.on : STARTUP_SWITCH_LABEL.off
            );
            setChipError(err && err.message ? err.message : "Falha ao alterar arranque");
          });
      }
      return;
    }

    if (action === "edit-drive") {
      if (demo) {
        showDemoToast("Demo: editar unidade");
        return;
      }
      await openEditDriveById(driveId);
      return;
    }

    if (action === "delete-drive") {
      const confirmed = await confirmDialog(deleteConfirmCopy(drive));
      if (!confirmed) return;

      if (demo) {
        persistScaffoldDismissed();
        removeDemoDrive(driveId);
        showDemoToast("Demo: unidade exemplo removida");
        return;
      }
      if (!bridge || !bridge.command) {
        setChipError("Disponível apenas com o RDrive em execução.");
        return;
      }
      try {
        await bridge.command("deleteDrive", { id: driveId });
        persistScaffoldDismissed();
      } catch (err) {
        setChipError(err && err.message ? err.message : "Falha ao excluir a unidade");
      }
    }
  }

  function prefersReducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch {
      return false;
    }
  }

  function applyStatePillLabel(statePill, stateLabel, status) {
    if (!stateLabel) return;

    if (statePill) {
      statePill.classList.remove("is-connecting", "is-disconnecting");
    }

    const animatedBase = STATE_PILL_ANIMATED[status];
    if (animatedBase && !prefersReducedMotion()) {
      if (statePill) {
        statePill.classList.add(
          status === "connecting" ? "is-connecting" : "is-disconnecting"
        );
      }
      stateLabel.replaceChildren();
      stateLabel.append(document.createTextNode(animatedBase));
      const dots = document.createElement("span");
      dots.className = "status-dots";
      dots.setAttribute("aria-hidden", "true");
      for (let i = 1; i <= 3; i += 1) {
        const dot = document.createElement("span");
        dot.className = `dot-${i}`;
        dot.textContent = ".";
        dots.appendChild(dot);
      }
      stateLabel.appendChild(dots);
      return;
    }

    stateLabel.textContent = STATE_COPY[status] || status || "—";
  }

  function renderDriveList(drives, integrityMap) {
    const body = document.getElementById("drive-list-body");
    const empty = document.getElementById("drive-empty-state");
    const template = document.getElementById("drive-row-template");
    if (!body) return;

    const list = Array.isArray(drives) ? drives : [];
    const integrity = integrityMap && typeof integrityMap === "object" ? integrityMap : {};

    body.replaceChildren();

    if (empty) {
      empty.hidden = list.length > 0;
    }

    if (!template || list.length === 0) return;

    list.forEach((drive) => {
      const fragment = template.content.cloneNode(true);
      const row = fragment.querySelector(".drive-row");
      if (!row) return;

      ensureDriveActionsLayout(fragment);

      const demo = isDemoDrive(drive);
      row.dataset.state = drive.status || "disconnected";
      row.dataset.driveId = drive.id || "";
      if (demo) row.dataset.demo = "true";

      const providerIcon = fragment.querySelector('[data-role="provider-icon"]');
      const providerLabel = drive.provider_label || drive.provider || "Desconhecido";
      if (providerIcon) {
        providerIcon.innerHTML = providerIconHtml(drive.provider);
      }

      const providerNameEl = fragment.querySelector('[data-role="provider-name"]');
      if (providerNameEl) providerNameEl.textContent = providerLabel;

      const demoBadge = fragment.querySelector('[data-role="demo-badge"]');
      if (demoBadge) demoBadge.hidden = !demo;

      const nameLabel = fragment.querySelector('[data-role="drive-label"]');
      if (nameLabel) {
        nameLabel.textContent = drive.label || "(sem nome)";
        nameLabel.dataset.mount = formatMountLabel(drive.mountpoint);
      }

      const mountLabelEl = fragment.querySelector('[data-role="mount-label"]');
      if (mountLabelEl) mountLabelEl.textContent = formatMountLabel(drive.mountpoint);

      const statePill = fragment.querySelector('[data-role="state-pill"]');
      const stateLabel = fragment.querySelector('[data-role="state-label"]');
      applyStatePillLabel(statePill, stateLabel, drive.status);

      const integrityKey = driveIntegrityLevel(drive, integrity);
      const integrityPill = fragment.querySelector('[data-role="integrity-pill"]');
      const integrityLabel = fragment.querySelector('[data-role="integrity-label"]');
      if (integrityPill) integrityPill.dataset.level = integrityKey;
      if (integrityLabel) integrityLabel.textContent = integrityCopy(integrityKey);

      const mountSwitch = fragment.querySelector('[data-role="mount-switch"]');
      const mountState = fragment.querySelector('[data-role="mount-state"]');
      const mountToggleRow = fragment.querySelector('[data-role="mount-toggle-row"]');
      const startupSwitch = fragment.querySelector('[data-role="startup-switch"]');
      const startupState = fragment.querySelector('[data-role="startup-state"]');
      const startupToggleRow = fragment.querySelector('[data-role="startup-toggle-row"]');

      const mState = SWITCH_STATE[drive.status] || SWITCH_STATE.disconnected;
      if (mountSwitch) {
        mountSwitch.setAttribute("aria-checked", String(mState.checked));
        mountSwitch.classList.toggle("is-on", mState.checked);
        mountSwitch.dataset.loading = String(mState.loading);
        mountSwitch.disabled = mState.loading;
      }
      if (mountState) mountState.textContent = mState.label;
      if (mountToggleRow) {
        mountToggleRow.dataset.state = mState.loading ? "loading" : mState.checked ? "on" : "off";
      }

      if (startupSwitch) {
        const startupOn = Boolean(drive.connect_at_startup);
        startupSwitch.setAttribute("aria-checked", String(startupOn));
        startupSwitch.classList.toggle("is-on", startupOn);
        startupSwitch.dataset.loading = "false";
      }
      if (startupState) {
        startupState.textContent = drive.connect_at_startup
          ? STARTUP_SWITCH_LABEL.on
          : STARTUP_SWITCH_LABEL.off;
      }
      if (startupToggleRow) {
        startupToggleRow.dataset.state = drive.connect_at_startup ? "on" : "off";
      }

      const editBtn = fragment.querySelector('[data-role="edit-btn"]');
      if (demo && editBtn) editBtn.disabled = true;

      body.appendChild(fragment);
    });
  }

  function applySnapshot(state) {
    const chip = document.getElementById("status-chip");

    if (chip) {
      if (state.statusText != null) chip.textContent = state.statusText;
      chip.dataset.tone = state.tone || "idle";
      chip.dataset.busy = state.busy ? "true" : "false";
    }

    if (state.drives !== undefined) {
      bridgeDrives = Array.isArray(state.drives) ? state.drives : [];
    }
    if (state.integrity !== undefined) {
      bridgeIntegrity =
        state.integrity && typeof state.integrity === "object" ? state.integrity : {};
    }
    if (state.drives !== undefined || state.integrity !== undefined) {
      refreshDriveList();
    }

    if (state.activeUser != null) {
      const userLabel = document.getElementById("active-user-label");
      if (userLabel) {
        userLabel.textContent = `Utilizador activo: ${state.activeUser}`;
      }
    }

    if (state.settings && typeof state.settings === "object") {
      const settingsView = document.getElementById(VIEW_SETTINGS);
      if (settingsView && settingsView.classList.contains("active")) {
        applySettingsToForm(state.settings);
      } else {
        cachedSettings = { ...DEFAULT_SETTINGS, ...state.settings };
      }
      trimActivityEntries();
      renderActivityPanel();
      syncStripeToolbarButton(state.settings);
      updateDevTestToolbarVisibility(state.settings);
    }

    if (state.activity !== undefined) {
      replaceActivityEntries(state.activity);
    }

    if (state.vaultUnlock !== undefined) {
      applyVaultUnlockState(state.vaultUnlock);
    }
  }

  function setChipBusy(busy) {
    const chip = document.getElementById("status-chip");
    if (!chip) return;
    chip.dataset.busy = busy ? "true" : "false";
  }

  function setChipError(message) {
    const chip = document.getElementById("status-chip");
    if (!chip) return;
    chip.textContent = message;
    chip.dataset.tone = "error";
    chip.dataset.busy = "false";
  }

  // --- TEMA ---

  function loadTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    const theme = stored === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
  }

  let themeTransitionTimer = null;

  function toggleTheme() {
    const root = document.documentElement;
    const next = root.dataset.theme === "light" ? "dark" : "light";

    if (themeTransitionTimer !== null) {
      window.clearTimeout(themeTransitionTimer);
      themeTransitionTimer = null;
    }

    root.classList.add("theme-transitioning");
    void root.offsetHeight;
    root.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);

    themeTransitionTimer = window.setTimeout(() => {
      root.classList.remove("theme-transitioning");
      themeTransitionTimer = null;
    }, THEME_TRANSITION_MS);
  }

  // --- AÇÕES ---

  async function handleAction(action, target) {
    switch (action) {
      case "vault-unlock-cancel":
        await cancelVaultUnlock();
        break;
      case "vault-forgot-password":
        await forgotVaultPassword();
        break;
      case "open-settings":
        showView(VIEW_SETTINGS);
        await prepareSettingsView();
        break;
      case "go-home":
        showView(VIEW_HOME);
        break;
      case "toggle-theme":
        toggleTheme();
        break;
      case "toggle-smtp":
        updateSmtpPanelVisibility();
        break;
      case "ping":
        await runPing();
        break;
      case "apply-settings":
        await saveSettings(true);
        break;
      case "cancel-settings":
        await loadSettingsFromBridge();
        showView(VIEW_HOME);
        break;
      case "switch-user":
        await runBridgeAction("switchUser", {}, "A mudar de utilizador…");
        break;
      case "restart-app":
        await runBridgeAction("restartApp", {}, "A reiniciar…");
        break;
      case "reset-vault": {
        const confirmInput = document.getElementById("set-vault-reset-confirm");
        const confirmText = confirmInput ? confirmInput.value.trim() : "";
        await runBridgeAction(
          "resetVault",
          { confirmText },
          "A repor cofre…",
          () => {
            if (confirmInput) confirmInput.value = "";
          }
        );
        break;
      }
      case "add-drive":
        showView(VIEW_ADD_DRIVE);
        await prepareAddDriveView();
        break;
      case "cancel-add":
        resetAddDriveForm();
        showView(VIEW_HOME);
        break;
      case "add-drive-prev":
        goAddDrivePrev();
        break;
      case "add-drive-next":
        goAddDriveNext();
        break;
      case "run-auto-connect":
        await runAddDriveAutoConnect();
        break;
      case "manual-setup":
        await runAddDriveManualSetup();
        break;
      case "cancel-cloud-setup":
        await cancelCloudSetupAgent();
        break;
      case "retry-cloud-setup":
        await retryCloudSetupAgent();
        break;
      case "cloud-setup-use-manual":
        useManualWizardFromAssistant();
        break;
      case "run-guided-setup":
        await runGuidedCloudSetup();
        break;
      case "test-guided-connection":
        await testGuidedConnection();
        break;
      case "open-guided-readme":
        await openProviderDocsLink("readme");
        break;
      case "open-guided-rclone":
        await openProviderDocsLink("rclone");
        break;
      case "guided-technical-mode":
        await runGuidedTechnicalMode();
        break;
      case "open-terabox-login":
        await openTeraboxLoginBrowser({ manual: true });
        break;
      case "open-terabox-embedded-browser":
        await openTeraboxEmbeddedBrowser({ manual: true });
        break;
      case "toggle-connection":
      case "set-startup":
      case "edit-drive":
      case "delete-drive":
        await handleDriveRowAction(action, target);
        break;
      case "add-demo-drive": {
        const preset = target && target.dataset.preset;
        if (preset) addDemoDrive(preset);
        break;
      }
      case "clear-demo-drives":
        clearDemoDrives();
        break;
      case "open-activity":
        setActivityOpen(!activityOpen);
        break;
      case "open-transfer-jobs":
        await openTransferJobsPanel();
        break;
      case "open-stripe-splitter":
        await openStripeSplitterFlow();
        break;
      case "cancel-edit-drive":
        closeEditDriveModal();
        break;
      case "close-activity":
        setActivityOpen(false);
        break;
      case "refresh-log-tail":
        await refreshLogTail();
        break;
      case "open-logs-folder":
        await openLogsFolder();
        break;
      case "diag-system-check":
      case "diag-remote-test":
      case "diag-speed-start":
      case "diag-speed-cancel":
      case "diag-mount-check":
      case "diag-human-log":
      case "diag-force-cleanup":
      case "diag-refresh-features":
        await handleDiagAction(action);
        break;
      default:
        if (target && target.dataset.tab) {
          showTab(target.dataset.tab);
        }
        break;
    }
  }

  async function runBridgeAction(commandName, args, busyMsg, onSuccess) {
    if (!bridge || !bridge.command) {
      setSettingsFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }
    setSettingsFeedback(busyMsg, "busy");
    try {
      await bridge.command(commandName, args);
      setSettingsFeedback("Operação concluída.", "ok");
      if (onSuccess) onSuccess();
    } catch (err) {
      setSettingsFeedback(err && err.message ? err.message : "Operação falhou.", "error");
    }
  }

  async function runPing() {
    if (!bridge || !bridge.command) {
      applySnapshot({ statusText: "Sem bridge", tone: "error", busy: false });
      return;
    }

    setChipBusy(true);
    const chip = document.getElementById("status-chip");
    if (chip) {
      chip.dataset.tone = "busy";
      chip.textContent = "A testar…";
    }

    try {
      const result = await bridge.command("ping");
      applySnapshot({
        statusText: result && result.message ? `OK: ${result.message}` : "Ligação OK",
        tone: "ok",
        busy: false,
      });
    } catch (err) {
      setChipError(err && err.message ? err.message : "Falha no ping");
    }
  }

  function syncStripeToolbarButton(settings) {
    const btn = document.getElementById("toolbar-stripe-btn");
    if (!btn) return;
    const source = settings && typeof settings === "object" ? settings : cachedSettings;
    const enabled = Boolean(source.experimental_enabled) && Boolean(source.enable_stripe);
    btn.disabled = !enabled;
    btn.title = enabled
      ? "Dividir ficheiro grande entre várias contas (stripe)"
      : "Ative em Definições › Por sua conta e risco para usar stripe";
  }

  function setEditDriveFeedback(message, tone) {
    const el = document.getElementById("edit-drive-feedback");
    if (!el) return;
    el.textContent = message || "";
    el.dataset.tone = tone || "";
  }

  function openEditDriveModal(drive) {
    const overlay = document.getElementById("edit-drive-overlay");
    if (!overlay || !drive) return;

    const setValue = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value != null ? String(value) : "";
    };
    const setChecked = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.checked = Boolean(value);
    };

    setValue("edit-drive-id", drive.id || "");
    setValue("edit-drive-label", drive.label || "");
    setValue("edit-drive-remote", drive.remote_name || "");
    setValue("edit-drive-mount", drive.mountpoint || "");
    setChecked("edit-drive-startup", drive.connect_at_startup);
    setChecked("edit-drive-session", Boolean(drive.session_only));

    const cacheMode = document.getElementById("edit-drive-cache-mode");
    if (cacheMode) {
      cacheMode.value = drive.vfs_cache_mode || "full";
    }
    setValue("edit-drive-cache-size", drive.cache_max_size || "20G");
    setEditDriveFeedback("");

    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    const labelInput = document.getElementById("edit-drive-label");
    if (labelInput) labelInput.focus();
  }

  function closeEditDriveModal() {
    const overlay = document.getElementById("edit-drive-overlay");
    if (!overlay) return;
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    setEditDriveFeedback("");
  }

  async function openEditDriveById(driveId) {
    if (!bridge || !bridge.command) {
      setChipError("Disponível apenas com o RDrive em execução.");
      return;
    }
    try {
      const result = await bridge.command("editDrive", { id: driveId });
      const drive = result && result.drive;
      if (!drive) {
        throw new Error("Resposta inválida ao editar unidade.");
      }
      openEditDriveModal(drive);
    } catch (err) {
      setChipError(err && err.message ? err.message : "Falha ao abrir edição");
    }
  }

  async function submitEditDriveForm(event) {
    event.preventDefault();
    if (!bridge || !bridge.command) {
      setEditDriveFeedback("Disponível apenas com o RDrive em execução.", "error");
      return;
    }

    const idEl = document.getElementById("edit-drive-id");
    const driveId = idEl ? idEl.value.trim() : "";
    if (!driveId) {
      setEditDriveFeedback("Unidade inválida.", "error");
      return;
    }

    const cacheModeEl = document.getElementById("edit-drive-cache-mode");
    const payload = {
      id: driveId,
      label: (document.getElementById("edit-drive-label") || {}).value.trim(),
      remote_name: (document.getElementById("edit-drive-remote") || {}).value.trim(),
      mountpoint: (document.getElementById("edit-drive-mount") || {}).value.trim(),
      connect_at_startup: Boolean(
        document.getElementById("edit-drive-startup") &&
          document.getElementById("edit-drive-startup").checked
      ),
      session_only: Boolean(
        document.getElementById("edit-drive-session") &&
          document.getElementById("edit-drive-session").checked
      ),
      vfs_cache_mode: cacheModeEl ? cacheModeEl.value : "full",
      cache_max_size: (document.getElementById("edit-drive-cache-size") || {}).value.trim(),
    };

    setEditDriveFeedback("A guardar…", "busy");
    try {
      await bridge.command("updateDrive", payload);
      closeEditDriveModal();
    } catch (err) {
      setEditDriveFeedback(err && err.message ? err.message : "Falha ao guardar.", "error");
    }
  }

  async function openTransferJobsPanel() {
    if (!bridge || !bridge.command) {
      setChipError("Disponível apenas com o RDrive em execução.");
      return;
    }
    try {
      await bridge.command("openTransferJobs", {});
    } catch (err) {
      setChipError(err && err.message ? err.message : "Falha ao abrir transferências");
    }
  }

  async function openStripeSplitterFlow() {
    if (!bridge || !bridge.command) {
      setChipError("Disponível apenas com o RDrive em execução.");
      return;
    }
    try {
      await bridge.command("openStripeSplitter", {});
    } catch (err) {
      setChipError(err && err.message ? err.message : "Falha ao iniciar divisão stripe");
    }
  }

  function wireEditDriveForm() {
    const form = document.getElementById("edit-drive-form");
    if (form) {
      form.addEventListener("submit", submitEditDriveForm);
    }
    const overlay = document.getElementById("edit-drive-overlay");
    if (overlay) {
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) closeEditDriveModal();
      });
    }
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const panel = document.getElementById("edit-drive-overlay");
      if (panel && !panel.hidden) closeEditDriveModal();
    });
  }

  function wireActions() {
    wireAddDriveForm();
    wireConfirmDialog();
    wireVaultUnlockForm();
    wireEditDriveForm();

    const settingsForm = document.getElementById("settings-form");
    if (settingsForm) {
      settingsForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        await saveSettings(false);
      });
      settingsForm.addEventListener("input", updateSettingsFormDirtyState);
      settingsForm.addEventListener("change", updateSettingsFormDirtyState);
      const vaultToggle = document.getElementById("set-vault-enabled");
      if (vaultToggle) {
        vaultToggle.addEventListener("change", () => {
          updateVaultModeUi(vaultToggle.checked);
          updateVaultEnablePanelVisibility();
          updateSettingsFormDirtyState();
        });
      }
    }

    document.addEventListener("click", (event) => {
      const switchEl = resolveDriveSwitch(event.target);
      if (switchEl && switchEl.dataset.action) {
        event.preventDefault();
        event.stopPropagation();
        handleAction(switchEl.dataset.action, switchEl);
        return;
      }

      const toggleRow = event.target.closest(".toggle-row");
      if (toggleRow && !event.target.closest(".link-action")) {
        const rowSwitch = toggleRow.querySelector(".slide-switch");
        if (
          rowSwitch &&
          rowSwitch.dataset.action &&
          !rowSwitch.disabled &&
          rowSwitch.dataset.loading !== "true"
        ) {
          event.preventDefault();
          handleAction(rowSwitch.dataset.action, rowSwitch);
          return;
        }
      }

      const target = event.target.closest("[data-action], .menu-item[data-tab]");
      if (!target) return;

      if (target.classList.contains("menu-item") && target.dataset.tab) {
        event.preventDefault();
        showTab(target.dataset.tab);
        return;
      }

      const action = target.dataset.action;
      if (!action) return;

      event.preventDefault();
      event.stopPropagation();
      handleAction(action, target);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !activityOpen) return;
      event.preventDefault();
      setActivityOpen(false);
    });
  }

  // --- INIT ---

  async function init() {
    loadTheme();
    scaffoldDismissed = loadScaffoldDismissed();
    wireActions();
    renderActivityPanel();

    try {
      bridge = await connectBridge({
        onState: applySnapshot,
        onEvent: handleBridgeEvent,
        onError: (err) => setChipError(err && err.message ? err.message : "Erro"),
      });
      bridgeIsLive = typeof QWebChannel !== "undefined";
    } catch (_err) {
      bridge = createMockBridge(applySnapshot, handleBridgeEvent);
      bridgeIsLive = false;
    }

    if (bridge && bridge.command && typeof QWebChannel !== "undefined") {
      try {
        const ping = await bridge.command("ping", {});
        const version = ping && ping.bridgeApiVersion;
        const cloudOk = ping && ping.features && ping.features.cloudSetupAgent;
        if (!version || version < 2 || !cloudOk) {
          setChipError(
            "Backend desatualizado — feche o RDrive e execute Iniciar.bat de novo."
          );
        }
      } catch {
        /* ping opcional */
      }
    }

    document.body.dataset.ready = "true";
    syncStripeToolbarButton(cachedSettings);
    updateDevTestToolbarVisibility(cachedSettings);
    if (!bridgeIsLive) {
      refreshDriveList();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
