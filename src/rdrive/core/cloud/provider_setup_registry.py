"""Registo central de estratégias de configuração por provedor rclone.

Estratégias:
- ``oauth`` — login no browser (drive, dropbox, onedrive, …)
- ``guided_form`` — formulário dinâmico + teste + remote não-interativo
- ``cookie_chrome`` — sessão via Chrome + cookies.txt (TeraBox, …)
- ``guided_generic`` — host/url/user/pass para backends sem template dedicado
- ``manual_terminal`` — último recurso (wrappers internos rclone)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rdrive.core.cloud.remote_setup import canonical_backend

FieldDef = dict[str, str | bool]
Answers = dict[str, object] | None
BuildFn = Callable[[Answers], dict[str, str]]
ValidateFn = Callable[[Answers], tuple[bool, str]]
TestPathFn = Callable[[str, Answers], str]


class SetupStrategy(str, Enum):
    OAUTH = "oauth"
    GUIDED_FORM = "guided_form"
    COOKIE_CHROME = "cookie_chrome"
    GUIDED_GENERIC = "guided_generic"
    MANUAL_TERMINAL = "manual_terminal"


# Provedores documentados que usam cookie de sessão (Chrome + cookies.txt).
COOKIE_CHROME_PROVIDERS: frozenset[str] = frozenset({"terabox"})

# Wrappers / backends internos — só terminal.
_MANUAL_ONLY_BACKENDS: frozenset[str] = frozenset(
    {
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
    }
)

_OAUTH_BACKENDS: frozenset[str] = frozenset(
    {"drive", "dropbox", "onedrive", "box", "pcloud", "mega"}
)

# Ordem preferida na lista «Adicionar unidade» (OAuth → cookie → protocolos → resto).
_OAUTH_DISPLAY_ORDER: tuple[str, ...] = (
    "drive",
    "onedrive",
    "dropbox",
    "box",
    "pcloud",
    "mega",
)

_POPULAR_GUIDED_ORDER: tuple[str, ...] = ("s3", "webdav", "sftp", "ftp")

_GENERIC_FIELDS: list[FieldDef] = [
    {
        "name": "host",
        "label": "Host / URL",
        "type": "text",
        "required": True,
        "placeholder": "servidor.exemplo.com ou https://…",
        "help": "Endereço do servidor ou URL base conforme o protocolo.",
    },
    {
        "name": "user",
        "label": "Utilizador",
        "type": "text",
        "required": False,
    },
    {
        "name": "password",
        "label": "Senha / chave",
        "type": "password",
        "required": False,
        "help": "Preencha se o backend exigir autenticação.",
    },
]

_COOKIE_FIELDS: list[FieldDef] = [
    {
        "name": "confirmed_on_main",
        "label": "Sessão activa no site do provedor",
        "type": "checkbox",
        "required": False,
        "help": "Marque após login completo na página principal do serviço.",
    },
    {
        "name": "cookie",
        "label": "Cookie de sessão",
        "type": "password",
        "required": True,
        "placeholder": "Importar cookies.txt ou colar manualmente",
        "help": "Use «Edge RDrive» + «Importar cookies» após login no browser dedicado.",
    },
]

from rdrive.core.cloud.guided_field_defs import GUIDED_FIELD_DEFS as _CORE_GUIDED_FIELDS


def _answer_str(answers: Answers, key: str) -> str:
    if not answers:
        return ""
    return str(answers.get(key, "") or "").strip()


def _answer_bool(answers: Answers, key: str) -> bool:
    if not answers:
        return False
    raw = answers.get(key)
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on", "sim"}


def _build_core(backend: str, answers: Answers) -> dict[str, str]:
    from rdrive.core.cloud.remote_setup import build_core_guided_rclone_options

    return build_core_guided_rclone_options(backend, answers)  # type: ignore[arg-type]


def _validate_core(backend: str, answers: Answers) -> tuple[bool, str]:
    from rdrive.core.cloud.remote_setup import validate_core_guided_answers

    return validate_core_guided_answers(backend, answers)  # type: ignore[arg-type]


def _test_path_core(backend: str, remote: str, answers: Answers) -> str:
    name = remote.strip()
    if backend == "s3":
        bucket = _answer_str(answers, "bucket")
        if bucket:
            return f"{name}:{bucket}"
    return f"{name}:"


def _build_b2(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {}
    account = _answer_str(answers, "account")
    key = _answer_str(answers, "key")
    if account:
        opts["account"] = account
    if key:
        opts["key"] = key
    return opts


def _build_gcs(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {}
    project = _answer_str(answers, "project_number")
    sa_file = _answer_str(answers, "service_account_file")
    if project:
        opts["project_number"] = project
    if sa_file:
        opts["service_account_file"] = sa_file
    bucket = _answer_str(answers, "bucket")
    if bucket:
        opts["bucket"] = bucket
    return opts


def _build_swift(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {
        "user": _answer_str(answers, "user"),
        "key": _answer_str(answers, "key"),
        "auth": _answer_str(answers, "auth") or "https://auth.cloud.ovh.net/v3",
    }
    tenant = _answer_str(answers, "tenant")
    if tenant:
        opts["tenant"] = tenant
    endpoint = _answer_str(answers, "endpoint")
    if endpoint:
        opts["endpoint"] = endpoint
    region = _answer_str(answers, "region")
    if region:
        opts["region"] = region
    return {k: v for k, v in opts.items() if v}


def _build_azureblob(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {
        "account": _answer_str(answers, "account"),
        "key": _answer_str(answers, "key"),
    }
    endpoint = _answer_str(answers, "endpoint")
    if endpoint:
        opts["endpoint"] = endpoint
    return {k: v for k, v in opts.items() if v}


def _build_storj(answers: Answers) -> dict[str, str]:
    grant = _answer_str(answers, "access_grant")
    return {"access_grant": grant} if grant else {}


def _build_hdfs(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {"namenode": _answer_str(answers, "namenode")}
    user = _answer_str(answers, "username")
    if user:
        opts["username"] = user
    return {k: v for k, v in opts.items() if v}


def _build_seafile(answers: Answers) -> dict[str, str]:
    return {
        "url": _answer_str(answers, "url"),
        "user": _answer_str(answers, "user"),
        "pass": _answer_str(answers, "password"),
    }


def _build_koofr(answers: Answers) -> dict[str, str]:
    return {
        "user": _answer_str(answers, "user"),
        "password": _answer_str(answers, "password"),
    }


def _build_hidrive(answers: Answers) -> dict[str, str]:
    return _build_koofr(answers)


def _build_baidu(answers: Answers) -> dict[str, str]:
    return {
        "user": _answer_str(answers, "user"),
        "passwd": _answer_str(answers, "password"),
    }


def _build_alist(answers: Answers) -> dict[str, str]:
    opts: dict[str, str] = {
        "url": _answer_str(answers, "url"),
        "password": _answer_str(answers, "password"),
    }
    user = _answer_str(answers, "user")
    if user:
        opts["username"] = user
    return {k: v for k, v in opts.items() if v}


def _build_opendrive(answers: Answers) -> dict[str, str]:
    return {
        "username": _answer_str(answers, "username"),
        "password": _answer_str(answers, "password"),
    }


def _build_generic(answers: Answers) -> dict[str, str]:
    host = _answer_str(answers, "host")
    user = _answer_str(answers, "user")
    password = _answer_str(answers, "password")
    opts: dict[str, str] = {}
    if host.startswith("http://") or host.startswith("https://"):
        opts["url"] = host
    elif host:
        opts["host"] = host
    if user:
        opts["user"] = user
    if password:
        opts["pass"] = password
    return opts


def _validate_required(fields: list[FieldDef], answers: Answers) -> tuple[bool, str]:
    for fld in fields:
        if not fld.get("required"):
            continue
        name = str(fld.get("name", ""))
        if not _answer_str(answers, name):
            label = str(fld.get("label", name))
            return False, f"O campo «{label}» é obrigatório."
    return True, ""


def _validate_terabox(answers: Answers) -> tuple[bool, str]:
    ok, msg = _validate_required(_COOKIE_FIELDS, answers)
    if not ok:
        return ok, msg
    from rdrive.core.cloud.terabox_setup import validate_terabox_cookie

    return validate_terabox_cookie(_answer_str(answers, "cookie"))


def _validate_sftp_extra(answers: Answers) -> tuple[bool, str]:
    ok, msg = _validate_core("sftp", answers)
    if not ok:
        return ok, msg
    if (
        not _answer_str(answers, "password")
        and not _answer_str(answers, "key")
        and not _answer_str(answers, "key_file")
    ):
        return False, "Informe senha, ficheiro de chave ou PEM para SFTP."
    return True, ""


@dataclass(frozen=True, slots=True)
class ProviderSetupSpec:
    strategy: SetupStrategy
    hint_pt: str
    guided_fields: tuple[FieldDef, ...] = ()
    build_options: BuildFn | None = None
    validate: ValidateFn | None = None
    test_remote_path: TestPathFn | None = None
    docs_anchor: str = "agente-configuracao"


@dataclass(frozen=True, slots=True)
class ProviderSetupPlan:
    """Plano de UI/fluxo para um slug de provedor."""

    backend: str
    strategy: SetupStrategy
    hint_pt: str
    guided_fields: list[FieldDef]
    supports_oauth_auto: bool
    supports_guided: bool
    allows_manual_fallback: bool


def _spec(
    strategy: SetupStrategy,
    hint_pt: str,
    *,
    fields: list[FieldDef] | None = None,
    build: BuildFn | None = None,
    validate: ValidateFn | None = None,
    test_path: TestPathFn | None = None,
    anchor: str = "",
) -> ProviderSetupSpec:
    backend_fields = tuple(fields or [])
    return ProviderSetupSpec(
        strategy=strategy,
        hint_pt=hint_pt,
        guided_fields=backend_fields,
        build_options=build,
        validate=validate,
        test_remote_path=test_path,
        docs_anchor=anchor or "agente-configuracao",
    )


def _guided(
    backend: str,
    hint_pt: str,
    *,
    fields: list[FieldDef] | None = None,
    validate: ValidateFn | None = None,
    anchor: str = "",
) -> ProviderSetupSpec:
    flds = fields if fields is not None else _CORE_GUIDED_FIELDS.get(backend, [])
    val = validate or (lambda a, b=backend: _validate_core(b, a))
    return _spec(
        SetupStrategy.GUIDED_FORM,
        hint_pt,
        fields=flds,
        build=lambda a, b=backend: _build_core(b, a),
        validate=val,
        test_path=lambda r, a, b=backend: _test_path_core(b, r, a),
        anchor=anchor or f"agente-{backend}",
    )


_REGISTRY: dict[str, ProviderSetupSpec] = {}

# --- OAuth ---
for _oauth_slug, _oauth_hint in (
    (
        "drive",
        "Google Drive: «Configuração automática» abre o Edge RDrive (perfil isolado). "
        "O Google pode recusar («navegador não seguro»); alternativa: rclone authorize drive "
        "--auth-no-open-browser e abra o URL no browser diário, ou rclone config → renovar token.",
    ),
    ("dropbox", "Dropbox: OAuth automático no browser."),
    ("onedrive", "OneDrive: escolha pessoal/empresarial se necessário, depois OAuth automático."),
    ("box", "Box: OAuth automático no browser."),
    ("pcloud", "pCloud: OAuth automático no browser."),
    ("mega", "Mega: OAuth automático no browser."),
):
    _REGISTRY[_oauth_slug] = _spec(
        SetupStrategy.OAUTH,
        _oauth_hint,
        anchor="agente-oauth",
    )

# --- Cookie Chrome ---
_REGISTRY["terabox"] = _spec(
    SetupStrategy.COOKIE_CHROME,
    (
        "TeraBox (experimental): Edge dedicado + cookies.txt. "
        "Requer rclone não oficial com backend terabox. "
        "Passos: 1) Dados 2) Testar 3) Guardar."
    ),
    fields=_CORE_GUIDED_FIELDS.get("terabox", _COOKIE_FIELDS),
    build=lambda a: _build_core("terabox", a),
    validate=_validate_terabox,
    test_path=lambda r, a: _test_path_core("terabox", r, a),
    anchor="agente-terabox",
)

# --- Formulários guiados (core) ---
_REGISTRY["s3"] = _guided(
    "s3",
    "S3 / compatíveis: access key, secret e região — teste antes de guardar.",
    anchor="agente-s3",
)
_REGISTRY["webdav"] = _guided("webdav", "WebDAV: URL, utilizador e senha.", anchor="agente-webdav")
_REGISTRY["sftp"] = _guided(
    "sftp",
    "SFTP: host, porta, utilizador e senha ou chave privada.",
    validate=_validate_sftp_extra,
    anchor="agente-sftp",
)
_REGISTRY["ftp"] = _guided("ftp", "FTP/FTPS: host, credenciais e TLS explícito se necessário.", anchor="agente-ftp")
_REGISTRY["http"] = _guided("http", "HTTP: URL base (montagem só leitura).", anchor="agente-http")
_REGISTRY["smb"] = _guided("smb", "SMB/CIFS: host, partilha e credenciais Windows.", anchor="agente-smb")

# --- Formulários guiados (extensão) ---
_REGISTRY["b2"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Backblaze B2: ID da conta e chave de aplicação.",
    fields=[
        {"name": "account", "label": "Account ID", "type": "text", "required": True},
        {"name": "key", "label": "Application Key", "type": "password", "required": True},
        {
            "name": "bucket",
            "label": "Bucket (opcional)",
            "type": "text",
            "required": False,
            "help": "Usado apenas no teste de ligação.",
        },
    ],
    build=_build_b2,
    validate=lambda a: _validate_required(_REGISTRY["b2"].guided_fields, a),  # type: ignore[arg-type]
    test_path=lambda r, a: f"{r}:{_answer_str(a, 'bucket')}" if _answer_str(a, "bucket") else f"{r}:",
    anchor="agente-b2",
)
_REGISTRY["backblaze"] = _REGISTRY["b2"]

_REGISTRY["googlecloudstorage"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Google Cloud Storage: número do projeto e ficheiro JSON da conta de serviço.",
    fields=[
        {"name": "project_number", "label": "Número do projeto", "type": "text", "required": True},
        {
            "name": "service_account_file",
            "label": "Ficheiro JSON (conta de serviço)",
            "type": "text",
            "required": True,
            "placeholder": r"C:\...\service-account.json",
        },
        {"name": "bucket", "label": "Bucket (opcional)", "type": "text", "required": False},
    ],
    build=_build_gcs,
    validate=lambda a: _validate_required(_REGISTRY["googlecloudstorage"].guided_fields, a),  # type: ignore[arg-type]
    test_path=lambda r, a: f"{r}:{_answer_str(a, 'bucket')}" if _answer_str(a, "bucket") else f"{r}:",
    anchor="agente-gcs",
)
_REGISTRY["gcs"] = _REGISTRY["googlecloudstorage"]

_REGISTRY["swift"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "OpenStack Swift: utilizador, chave, tenant e endpoint de autenticação.",
    fields=[
        {"name": "user", "label": "Utilizador", "type": "text", "required": True},
        {"name": "key", "label": "Chave", "type": "password", "required": True},
        {
            "name": "auth",
            "label": "URL de autenticação",
            "type": "url",
            "required": True,
            "placeholder": "https://auth.cloud.ovh.net/v3",
        },
        {"name": "tenant", "label": "Tenant", "type": "text", "required": True},
        {"name": "endpoint", "label": "Endpoint (opcional)", "type": "text", "required": False},
        {"name": "region", "label": "Região (opcional)", "type": "text", "required": False},
    ],
    build=_build_swift,
    validate=lambda a: _validate_required(_REGISTRY["swift"].guided_fields, a),  # type: ignore[arg-type]
    anchor="agente-swift",
)

_REGISTRY["azureblob"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Azure Blob: nome da conta de armazenamento e chave.",
    fields=[
        {"name": "account", "label": "Conta de armazenamento", "type": "text", "required": True},
        {"name": "key", "label": "Chave", "type": "password", "required": True},
        {"name": "endpoint", "label": "Endpoint (opcional)", "type": "text", "required": False},
    ],
    build=_build_azureblob,
    validate=lambda a: _validate_required(_REGISTRY["azureblob"].guided_fields, a),  # type: ignore[arg-type]
    anchor="agente-azure",
)

_REGISTRY["storj"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Storj: access grant gerado no painel Storj.",
    fields=[
        {
            "name": "access_grant",
            "label": "Access Grant",
            "type": "password",
            "required": True,
        },
    ],
    build=_build_storj,
    validate=lambda a: _validate_required(_REGISTRY["storj"].guided_fields, a),  # type: ignore[arg-type]
    anchor="agente-storj",
)

_REGISTRY["hdfs"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "HDFS: namenode e utilizador (cluster Hadoop).",
    fields=[
        {"name": "namenode", "label": "Namenode", "type": "text", "required": True, "placeholder": "hdfs://host:8020"},
        {"name": "username", "label": "Utilizador", "type": "text", "required": False},
    ],
    build=_build_hdfs,
    validate=lambda a: _validate_required(_REGISTRY["hdfs"].guided_fields, a),  # type: ignore[arg-type]
    anchor="agente-hdfs",
)

_REGISTRY["seafile"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Seafile: URL do servidor, utilizador e senha.",
    fields=[
        {"name": "url", "label": "URL", "type": "url", "required": True},
        {"name": "user", "label": "Utilizador", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_seafile,
    validate=lambda a: _validate_required(_REGISTRY["seafile"].guided_fields, a),  # type: ignore[arg-type]
    anchor="agente-seafile",
)

_REGISTRY["koofr"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Koofr: email e palavra-passe da conta.",
    fields=[
        {"name": "user", "label": "Email", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_koofr,
    validate=lambda a: _validate_required(_REGISTRY["koofr"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["hidrive"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "HiDrive: utilizador e senha STRATO.",
    fields=[
        {"name": "user", "label": "Utilizador", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_hidrive,
    validate=lambda a: _validate_required(_REGISTRY["hidrive"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["baidu"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Baidu Pan: utilizador e senha (backend rclone padrão — não usa cookies).",
    fields=[
        {"name": "user", "label": "Utilizador", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_baidu,
    validate=lambda a: _validate_required(_REGISTRY["baidu"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["alist"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "AList: URL do servidor AList, utilizador e senha/token.",
    fields=[
        {"name": "url", "label": "URL", "type": "url", "required": True},
        {"name": "user", "label": "Utilizador", "type": "text", "required": False},
        {"name": "password", "label": "Senha / token", "type": "password", "required": True},
    ],
    build=_build_alist,
    validate=lambda a: _validate_required(_REGISTRY["alist"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["opendrive"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "OpenDrive: credenciais da conta.",
    fields=[
        {"name": "username", "label": "Utilizador", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_opendrive,
    validate=lambda a: _validate_required(_REGISTRY["opendrive"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["oracleobjectstorage"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Oracle Object Storage: namespace, região e chaves API.",
    fields=[
        {"name": "namespace", "label": "Namespace", "type": "text", "required": True},
        {"name": "region", "label": "Região", "type": "text", "required": True, "placeholder": "eu-frankfurt-1"},
        {"name": "access_key_id", "label": "Access Key ID", "type": "text", "required": True},
        {"name": "secret_access_key", "label": "Secret Access Key", "type": "password", "required": True},
        {"name": "compartment", "label": "Compartment OCID (opcional)", "type": "text", "required": False},
    ],
    build=lambda a: {
        k: v
        for k, v in {
            "namespace": _answer_str(a, "namespace"),
            "region": _answer_str(a, "region"),
            "access_key_id": _answer_str(a, "access_key_id"),
            "secret_access_key": _answer_str(a, "secret_access_key"),
            "compartment": _answer_str(a, "compartment"),
        }.items()
        if v
    },
    validate=lambda a: _validate_required(_REGISTRY["oracleobjectstorage"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["mailru"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Mail.ru Cloud: email e senha.",
    fields=[
        {"name": "user", "label": "Email", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_koofr,
    validate=lambda a: _validate_required(_REGISTRY["mailru"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["protondrive"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Proton Drive: credenciais da conta (ver documentação rclone).",
    fields=[
        {"name": "username", "label": "Utilizador", "type": "text", "required": True},
        {"name": "password", "label": "Senha", "type": "password", "required": True},
    ],
    build=_build_opendrive,
    validate=lambda a: _validate_required(_REGISTRY["protondrive"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["putio"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "put.io: token de API da conta.",
    fields=[
        {"name": "token", "label": "Token API", "type": "password", "required": True},
    ],
    build=lambda a: {"token": _answer_str(a, "token")},
    validate=lambda a: _validate_required(_REGISTRY["putio"].guided_fields, a),  # type: ignore[arg-type]
)

_REGISTRY["premiumizeme"] = _spec(
    SetupStrategy.GUIDED_FORM,
    "Premiumize.me: token de API.",
    fields=[
        {"name": "token", "label": "Token API", "type": "password", "required": True},
    ],
    build=lambda a: {"token": _answer_str(a, "token")},
    validate=lambda a: _validate_required(_REGISTRY["premiumizeme"].guided_fields, a),  # type: ignore[arg-type]
)

# SharePoint avançado — manual (OAuth parcial não coberto pelo agente)
_REGISTRY["sharepoint"] = _spec(
    SetupStrategy.MANUAL_TERMINAL,
    "SharePoint: use o assistente rclone no terminal para sites/libraries específicos.",
    anchor="agente-manual",
)


def get_provider_spec(slug: str) -> ProviderSetupSpec:
    backend = canonical_backend(slug)
    if backend in _REGISTRY:
        return _REGISTRY[backend]
    if backend in _MANUAL_ONLY_BACKENDS:
        return _spec(
            SetupStrategy.MANUAL_TERMINAL,
            f"«{backend}» é um wrapper rclone — configure no terminal (modo técnico).",
            anchor="agente-manual",
        )
    return _spec(
        SetupStrategy.GUIDED_GENERIC,
        (
            f"«{backend}»: preencha host/URL e credenciais. "
            "Passos: 1) Dados 2) Testar 3) Guardar. Terminal só em último recurso."
        ),
        fields=list(_GENERIC_FIELDS),
        build=_build_generic,
        validate=lambda a: _validate_required(list(_GENERIC_FIELDS), a),
    )


def plan_for_provider(slug: str) -> ProviderSetupPlan:
    backend = canonical_backend(slug)
    spec = get_provider_spec(slug)
    strategy = spec.strategy
    fields = [dict(f) for f in spec.guided_fields]
    if strategy == SetupStrategy.GUIDED_GENERIC and not fields:
        fields = [dict(f) for f in _GENERIC_FIELDS]
    oauth = strategy == SetupStrategy.OAUTH or backend in _OAUTH_BACKENDS
    guided = strategy in {
        SetupStrategy.GUIDED_FORM,
        SetupStrategy.COOKIE_CHROME,
        SetupStrategy.GUIDED_GENERIC,
    }
    manual_only = strategy == SetupStrategy.MANUAL_TERMINAL
    return ProviderSetupPlan(
        backend=backend,
        strategy=strategy,
        hint_pt=spec.hint_pt,
        guided_fields=fields,
        supports_oauth_auto=oauth,
        supports_guided=guided,
        allows_manual_fallback=not manual_only,
    )


def setup_strategy_for_backend(slug: str) -> SetupStrategy:
    return get_provider_spec(slug).strategy


def provider_list_tier(slug: str) -> int:
    """Prioridade de secção na grelha «Adicionar unidade» (menor = mais acima)."""
    strategy = setup_strategy_for_backend(slug)
    if strategy == SetupStrategy.OAUTH:
        return 0
    if strategy == SetupStrategy.COOKIE_CHROME:
        return 1
    backend = canonical_backend(slug)
    if backend in _POPULAR_GUIDED_ORDER:
        return 2
    return 3


def provider_list_sort_key(label: str, slug: str) -> tuple[int, int, str]:
    """Chave estável: tier → ordem intra-tier → nome."""
    backend = canonical_backend(slug)
    tier = provider_list_tier(slug)
    if tier == 0:
        rank = (
            _OAUTH_DISPLAY_ORDER.index(backend)
            if backend in _OAUTH_DISPLAY_ORDER
            else len(_OAUTH_DISPLAY_ORDER)
        )
    elif tier == 2:
        rank = (
            _POPULAR_GUIDED_ORDER.index(backend)
            if backend in _POPULAR_GUIDED_ORDER
            else len(_POPULAR_GUIDED_ORDER)
        )
    else:
        rank = 0
    return tier, rank, label.casefold()


def sort_provider_entries(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Ordena ``(label, slug)`` para UI «Adicionar unidade»."""
    return sorted(entries, key=lambda item: provider_list_sort_key(item[0], item[1]))


_CONNECTION_PROTOCOL_BACKENDS: frozenset[str] = frozenset(
    {
        "s3",
        "webdav",
        "sftp",
        "ftp",
        "http",
        "alist",
        "swift",
        "b2",
        "azureblob",
        "gcs",
        "hdfs",
        "smb",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderUiSection:
    section_id: str
    title_pt: str
    entries: tuple[tuple[str, str], ...]


def _section_for_slug(slug: str) -> str:
    tier = provider_list_tier(slug)
    backend = canonical_backend(slug)
    if tier <= 1:
        return "cloud_accounts"
    if backend in _CONNECTION_PROTOCOL_BACKENDS or tier == 2:
        return "connections"
    return "other"


_SECTION_TITLES_PT: dict[str, str] = {
    "cloud_accounts": "Contas na nuvem",
    "connections": "Ligações e protocolos",
    "other": "Outros",
}


def group_provider_entries(entries: list[tuple[str, str]]) -> list[ProviderUiSection]:
    """Agrupa provedores para a lista lateral em Adicionar unidade."""
    sorted_entries = sort_provider_entries(entries)
    buckets: dict[str, list[tuple[str, str]]] = {
        "cloud_accounts": [],
        "connections": [],
        "other": [],
    }
    for label, slug in sorted_entries:
        buckets[_section_for_slug(slug)].append((label, slug))
    sections: list[ProviderUiSection] = []
    for section_id in ("cloud_accounts", "connections", "other"):
        items = buckets[section_id]
        if not items:
            continue
        sections.append(
            ProviderUiSection(
                section_id=section_id,
                title_pt=_SECTION_TITLES_PT[section_id],
                entries=tuple(items),
            )
        )
    return sections


def is_cookie_chrome_provider(slug: str) -> bool:
    return setup_strategy_for_backend(slug) == SetupStrategy.COOKIE_CHROME


def cookie_chrome_providers() -> list[str]:
    return sorted(COOKIE_CHROME_PROVIDERS)


def setup_mode_for_backend(slug: str, *, oauth_auto: bool | None = None) -> str:
    """Modo legado para Static/JS: ``oauth``, ``guided`` ou ``manual``."""
    backend = canonical_backend(slug)
    if oauth_auto is None:
        oauth_auto = backend in _OAUTH_BACKENDS
    if oauth_auto:
        return "oauth"
    strategy = setup_strategy_for_backend(slug)
    if strategy in {
        SetupStrategy.GUIDED_FORM,
        SetupStrategy.COOKIE_CHROME,
        SetupStrategy.GUIDED_GENERIC,
    }:
        return "guided"
    return "manual"


def supports_guided_setup(slug: str) -> bool:
    return plan_for_provider(slug).supports_guided


def guided_fields_for_backend(slug: str) -> list[FieldDef]:
    return plan_for_provider(slug).guided_fields


def provider_hint_pt(slug: str) -> str:
    return plan_for_provider(slug).hint_pt


def validate_guided_answers(slug: str, answers: Answers) -> tuple[bool, str]:
    backend = canonical_backend(slug)
    spec = get_provider_spec(slug)
    if spec.validate:
        return spec.validate(answers)
    if spec.strategy == SetupStrategy.MANUAL_TERMINAL:
        return False, f"O backend «{backend}» não suporta configuração guiada."
    return _validate_required(list(spec.guided_fields), answers)


def build_guided_rclone_options(slug: str, answers: Answers) -> dict[str, str]:
    backend = canonical_backend(slug)
    spec = get_provider_spec(slug)
    if spec.build_options:
        built = spec.build_options(answers)
        if built:
            return built
    if backend in _CORE_GUIDED_FIELDS:
        return _build_core(backend, answers)
    return {}


def guided_test_remote_path(slug: str, remote_name: str, answers: Answers) -> str:
    spec = get_provider_spec(slug)
    backend = canonical_backend(slug)
    if spec.test_remote_path:
        return spec.test_remote_path(remote_name.strip(), answers)
    return _test_path_core(backend, remote_name, answers)


def provider_setup_info_dict(slug: str) -> dict[str, Any]:
    """Payload para ``getProviderSetupInfo`` (WebUI) e CTk."""
    plan = plan_for_provider(slug)
    spec = get_provider_spec(slug)
    return {
        "backend": plan.backend,
        "strategy": plan.strategy.value,
        "setup_mode": setup_mode_for_backend(slug, oauth_auto=plan.supports_oauth_auto),
        "hint_pt": plan.hint_pt,
        "guided_fields": plan.guided_fields,
        "supports_oauth_auto": plan.supports_oauth_auto,
        "supports_guided": plan.supports_guided,
        "allows_manual_fallback": plan.allows_manual_fallback,
        "is_cookie_chrome": plan.strategy == SetupStrategy.COOKIE_CHROME,
        "readme_section": spec.docs_anchor,
    }


def registry_stats() -> dict[str, int]:
    """Contagens para relatório (testes / docs)."""
    guided = manual = oauth = cookie = generic = 0
    seen: set[str] = set()
    for key in set(_REGISTRY) | _OAUTH_BACKENDS | _GUIDED_BACKENDS_LEGACY():
        if key in seen:
            continue
        seen.add(key)
        strat = get_provider_spec(key).strategy
        if strat == SetupStrategy.OAUTH:
            oauth += 1
        elif strat == SetupStrategy.COOKIE_CHROME:
            cookie += 1
        elif strat == SetupStrategy.GUIDED_GENERIC:
            generic += 1
        elif strat == SetupStrategy.MANUAL_TERMINAL:
            manual += 1
        else:
            guided += 1
    return {
        "oauth": oauth,
        "guided_form": guided,
        "cookie_chrome": cookie,
        "guided_generic": generic,
        "manual_terminal": manual,
        "registered": len(_REGISTRY),
    }


def _GUIDED_BACKENDS_LEGACY() -> set[str]:
    return set(_CORE_GUIDED_FIELDS.keys())


# Expandir _GUIDED_BACKENDS em remote_setup após import circular
_GUIDED_BACKENDS: frozenset[str] = frozenset(
    {
        b
        for b, s in _REGISTRY.items()
        if s.strategy
        in {SetupStrategy.GUIDED_FORM, SetupStrategy.COOKIE_CHROME, SetupStrategy.GUIDED_GENERIC}
    }
    | set(_CORE_GUIDED_FIELDS.keys())
)
