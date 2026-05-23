from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass

from rdrive.core.rclone.rclone import RcloneCli


_DISPLAY_NAMES: dict[str, str] = {
    "drive": "Google Drive",
    "google_drive": "Google Drive",
    "googledrive": "Google Drive",
    "gdrive": "Google Drive",
    "onedrive": "OneDrive (Pessoal e Empresas)",
    "dropbox": "Dropbox",
    "s3": "S3",
    "webdav": "WebDAV",
    "sftp": "SFTP",
    "ftp": "FTP",
    "http": "HTTP",
    "amazon_drive": "Amazon Drive",
    "opendrive": "OpenDrive",
    "protondrive": "Proton Drive",
    "box": "Box",
    "mega": "Mega",
    "pcloud": "pCloud",
    "sharepoint": "SharePoint",
    "googlecloudstorage": "Google Cloud Storage",
    "gcs": "Google Cloud Storage",
    "b2": "Backblaze B2",
    "backblaze": "Backblaze B2",
    "hdfs": "HDFS",
    "smb": "SMB / CIFS",
    "local": "Local",
    "terabox": "TeraBox",
}

_BACKEND_ALIASES: dict[str, str] = {
    "google_drive": "drive",
    "googledrive": "drive",
    "gdrive": "drive",
    "dropbox": "dropbox",
    "onedrive": "onedrive",
    "s3": "s3",
    "webdav": "webdav",
    "sftp": "sftp",
    "ftp": "ftp",
}

_BACKEND_DOCS_URL: dict[str, str] = {
    "drive": "https://rclone.org/drive/",
    "dropbox": "https://rclone.org/dropbox/",
    "onedrive": "https://rclone.org/onedrive/",
    "s3": "https://rclone.org/s3/",
    "webdav": "https://rclone.org/webdav/",
    "sftp": "https://rclone.org/sftp/",
    "ftp": "https://rclone.org/ftp/",
    "http": "https://rclone.org/http/",
    "smb": "https://rclone.org/smb/",
}

# Âncoras em README.md (secção «Agente de configuração»).
_README_SECTION_ANCHORS: dict[str, str] = {
    "drive": "agente-oauth",
    "dropbox": "agente-oauth",
    "onedrive": "agente-oauth",
    "box": "agente-oauth",
    "pcloud": "agente-oauth",
    "mega": "agente-oauth",
    "s3": "agente-s3",
    "webdav": "agente-webdav",
    "sftp": "agente-sftp",
    "ftp": "agente-ftp",
    "http": "agente-http",
    "smb": "agente-smb",
    "terabox": "agente-terabox",
    "hdfs": "agente-manual",
}

_OAUTH_BACKENDS = {"drive", "dropbox", "onedrive", "box", "pcloud", "mega"}

_GUIDED_BACKENDS = frozenset({"s3", "webdav", "sftp", "ftp", "http", "smb", "terabox"})

# Metadados dos formulários guiados (Static UI + validação Python).
_GUIDED_FIELD_DEFS: dict[str, list[dict[str, str | bool]]] = {
    "s3": [
        {
            "name": "endpoint",
            "label": "Endpoint (opcional)",
            "type": "text",
            "required": False,
            "placeholder": "https://s3.example.com",
            "help": "Deixe vazio para AWS S3 padrão.",
        },
        {
            "name": "access_key",
            "label": "Access Key",
            "type": "text",
            "required": True,
            "placeholder": "AKIA…",
        },
        {
            "name": "secret",
            "label": "Secret Key",
            "type": "password",
            "required": True,
        },
        {
            "name": "region",
            "label": "Região",
            "type": "text",
            "required": True,
            "placeholder": "us-east-1",
        },
        {
            "name": "bucket",
            "label": "Bucket (opcional)",
            "type": "text",
            "required": False,
            "help": "Usado para testar a ligação; pode ficar vazio.",
        },
    ],
    "webdav": [
        {
            "name": "url",
            "label": "URL",
            "type": "url",
            "required": True,
            "placeholder": "https://dav.example.com/remote.php/webdav/",
        },
        {
            "name": "user",
            "label": "Utilizador",
            "type": "text",
            "required": True,
        },
        {
            "name": "password",
            "label": "Senha",
            "type": "password",
            "required": True,
        },
    ],
    "sftp": [
        {
            "name": "host",
            "label": "Host",
            "type": "text",
            "required": True,
            "placeholder": "sftp.example.com",
        },
        {
            "name": "port",
            "label": "Porta",
            "type": "number",
            "required": False,
            "placeholder": "22",
            "default": "22",
        },
        {
            "name": "user",
            "label": "Utilizador",
            "type": "text",
            "required": True,
        },
        {
            "name": "password",
            "label": "Senha",
            "type": "password",
            "required": False,
            "help": "Preencha senha, ficheiro de chave ou PEM colado.",
        },
        {
            "name": "key_file",
            "label": "Ficheiro de chave privada",
            "type": "text",
            "required": False,
            "placeholder": r"C:\Users\...\id_rsa",
            "help": "Caminho local para chave OpenSSH/PEM (alternativa à senha).",
        },
        {
            "name": "key",
            "label": "Chave privada (PEM)",
            "type": "textarea",
            "required": False,
            "help": "Alternativa à senha — cole o conteúdo PEM.",
        },
    ],
    "ftp": [
        {
            "name": "host",
            "label": "Host",
            "type": "text",
            "required": True,
            "placeholder": "ftp.example.com",
        },
        {
            "name": "port",
            "label": "Porta",
            "type": "number",
            "required": False,
            "placeholder": "21",
            "default": "21",
        },
        {
            "name": "user",
            "label": "Utilizador",
            "type": "text",
            "required": True,
        },
        {
            "name": "password",
            "label": "Senha",
            "type": "password",
            "required": True,
        },
        {
            "name": "explicit_tls",
            "label": "FTPS explícito (TLS)",
            "type": "checkbox",
            "required": False,
            "default": False,
            "help": "Active se o servidor exigir FTP sobre TLS (porta 21 com STARTTLS).",
        },
    ],
    "smb": [
        {
            "name": "host",
            "label": "Host / IP",
            "type": "text",
            "required": True,
            "placeholder": "192.168.1.10 ou nas.local",
        },
        {
            "name": "share",
            "label": "Partilha",
            "type": "text",
            "required": True,
            "placeholder": "Public ou backup",
            "help": "Nome da pasta partilhada SMB (não inclua barras).",
        },
        {
            "name": "domain",
            "label": "Domínio (opcional)",
            "type": "text",
            "required": False,
            "placeholder": "WORKGROUP",
            "help": "Domínio Windows ou grupo de trabalho; deixe vazio para conta local.",
        },
        {
            "name": "user",
            "label": "Utilizador",
            "type": "text",
            "required": True,
        },
        {
            "name": "password",
            "label": "Senha",
            "type": "password",
            "required": True,
        },
    ],
    "http": [
        {
            "name": "url",
            "label": "URL",
            "type": "url",
            "required": True,
            "placeholder": "https://example.com/files/",
        },
    ],
    "terabox": [
        {
            "name": "confirmed_on_main",
            "label": "Já estou na página principal (/main)",
            "type": "checkbox",
            "required": False,
            "help": (
                "Marque quando a URL do browser contiver /main (ex.: Meus ficheiros), "
                "após login em terabox.com."
            ),
        },
        {
            "name": "cookie",
            "label": "Cookie de sessão",
            "type": "password",
            "required": True,
            "placeholder": "Preenchido por «Login e capturar cookie» ou cole manualmente",
            "help": (
                "Preenchido automaticamente pelo navegador integrado RDrive após login. "
                "Deve conter ndus=. TeraBox bloqueia F12 — não copie cookies no site."
            ),
        },
    ],
}

_LOCAL_OR_NETWORK_BACKENDS = {"sftp", "ftp", "hdfs", "local", "smb", "alias", "mount"}

# Backends rclone internos / wrappers — não aparecem na grelha «Nova unidade».
_HIDDEN_PROVIDER_BACKENDS: frozenset[str] = frozenset(
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

_REMOTE_NAME_SUGGESTIONS: dict[str, str] = {
    "google_drive": "gdrive_pessoal",
    "googledrive": "gdrive_pessoal",
    "gdrive": "gdrive_pessoal",
    "drive": "gdrive_pessoal",
    "onedrive": "onedrive_pessoal",
    "dropbox": "dropbox_pessoal",
    "s3": "s3_pessoal",
    "webdav": "webdav_pessoal",
    "sftp": "sftp_pessoal",
    "ftp": "ftp_pessoal",
    "http": "http_pessoal",
    "smb": "smb_pessoal",
    "hdfs": "hdfs_pessoal",
    "box": "box_pessoal",
    "mega": "mega_pessoal",
    "pcloud": "pcloud_pessoal",
    "terabox": "terabox_pessoal",
}


@dataclass(slots=True)
class RemoteSetupInfo:
    backend: str
    docs_url: str
    is_oauth: bool


def _normalize_backend_slug(slug: str) -> str:
    return slug.strip().lower().replace("-", "_")


def is_user_facing_provider(slug: str) -> bool:
    """True se o backend deve aparecer na lista de provedores do utilizador."""
    key = _normalize_backend_slug(slug)
    return bool(key) and key not in _HIDDEN_PROVIDER_BACKENDS


def display_name_for_backend(slug: str) -> str:
    """Nome amigável do provedor; slug interno permanece o do rclone (ex.: drive)."""
    key = _normalize_backend_slug(slug)
    if not key:
        return _DISPLAY_NAMES["drive"]
    if key in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[key]
    return key.replace("_", " ").title()


def canonical_backend(value: str) -> str:
    backend = _normalize_backend_slug(value)
    if not backend:
        return "drive"
    return _BACKEND_ALIASES.get(backend, backend)


def backend_setup_info(value: str) -> RemoteSetupInfo:
    backend = canonical_backend(value)
    docs_url = _BACKEND_DOCS_URL.get(backend, f"https://rclone.org/{backend}/")
    return RemoteSetupInfo(backend=backend, docs_url=docs_url, is_oauth=backend in _OAUTH_BACKENDS)


def supports_guided_setup(backend_or_slug: str) -> bool:
    """True se o backend tem formulário guiado no assistente (sem OAuth)."""
    return canonical_backend(backend_or_slug) in _GUIDED_BACKENDS


def setup_mode_for_backend(backend_or_slug: str, *, oauth_auto: bool | None = None) -> str:
    """Modo de configuração: ``oauth``, ``guided`` ou ``manual``."""
    backend = canonical_backend(backend_or_slug)
    if oauth_auto is None:
        oauth_auto = backend in _OAUTH_BACKENDS
    if oauth_auto:
        return "oauth"
    if backend in _GUIDED_BACKENDS:
        return "guided"
    return "manual"


def guided_fields_for_backend(backend_or_slug: str) -> list[dict[str, str | bool]]:
    """Campos do questionário guiado para o Static (PT)."""
    backend = canonical_backend(backend_or_slug)
    return [dict(field) for field in _GUIDED_FIELD_DEFS.get(backend, [])]


def readme_section_for_backend(backend_or_slug: str) -> str:
    """Âncora HTML em README.md para documentação do protocolo."""
    backend = canonical_backend(backend_or_slug)
    return _README_SECTION_ANCHORS.get(backend, "agente-configuracao")


def _answer_bool(answers: dict[str, object] | None, key: str) -> bool:
    if not answers:
        return False
    raw = answers.get(key)
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    return text in {"1", "true", "yes", "on", "sim"}


def guided_connection_error_hints(backend_or_slug: str, error_text: str) -> str:
    """Sugestões PT para falhas comuns ao testar ligação guiada."""
    backend = canonical_backend(backend_or_slug)
    text = (error_text or "").lower()
    hints: list[str] = []

    if any(token in text for token in ("connection refused", "timeout", "i/o timeout", "no route")):
        hints.append(
            "Verifique firewall, VPN e se o host/porta estão corretos e acessíveis a partir deste PC."
        )
    if "401" in text or "403" in text or "unauthorized" in text or "permission denied" in text:
        hints.append("Credenciais recusadas — confirme utilizador, senha e permissões no servidor.")
    if "name resolution" in text or "no such host" in text or "lookup" in text:
        hints.append("O host não foi encontrado (DNS) — tente o endereço IP em vez do nome.")

    if backend == "ftp":
        if any(token in text for token in ("425", "passive", "pasv", "data connection")):
            hints.append(
                "FTP passivo: o servidor pode precisar de portas extra abertas no router/firewall."
            )
        if any(token in text for token in ("tls", "ssl", "certificate", "explicit")):
            hints.append(
                "Experimente activar ou desactivar «FTPS explícito» conforme o servidor (21+STARTTLS vs FTP simples)."
            )
        if "530" in text:
            hints.append("Login FTP recusado — confirme utilizador/senha e se a conta permite FTP.")
    elif backend == "sftp":
        if "key" in text or "publickey" in text or "handshake" in text:
            hints.append(
                "SFTP: confirme senha, caminho da chave privada ou PEM; a chave deve corresponder ao utilizador."
            )
        if "22" in text and "connection" in text:
            hints.append("Porta SFTP habitual: 22. Alguns servidores usam outra porta — confirme com o administrador.")
    elif backend == "smb":
        if any(token in text for token in ("access denied", "logon", "authentication", "nt status")):
            hints.append(
                "SMB: confirme domínio/grupo de trabalho, nome exacto da partilha e permissões de rede."
            )
        if "445" in text or "139" in text:
            hints.append("SMB usa portas 445/139 — verifique firewall Windows e partilhas no servidor NAS/PC.")
    elif backend == "webdav":
        if "404" in text or "not found" in text:
            hints.append("WebDAV: confirme o URL completo (incluindo barra final) e o caminho exposto pelo servidor.")
    elif backend == "http":
        hints.append("HTTP remoto é só leitura — confirme que o URL aponta para uma listagem de ficheiros acessível.")

    return "\n".join(hints)


def format_guided_connection_error(backend_or_slug: str, error_text: str) -> str:
    """Mensagem de erro enriquecida com dicas PT."""
    base = (error_text or "").strip() or "Remote não respondeu ao teste."
    hints = guided_connection_error_hints(backend_or_slug, base)
    if hints:
        return f"{base}\n\n{hints}"
    return base


def _answer_str(answers: dict[str, object] | None, key: str) -> str:
    if not answers:
        return ""
    return str(answers.get(key, "") or "").strip()


def validate_guided_answers(
    backend_or_slug: str,
    answers: dict[str, object] | None,
) -> tuple[bool, str]:
    """Valida respostas mínimas antes de chamar o rclone."""
    backend = canonical_backend(backend_or_slug)
    if backend not in _GUIDED_BACKENDS:
        return False, f"O backend «{backend}» não suporta configuração guiada."

    fields = _GUIDED_FIELD_DEFS.get(backend, [])
    for field in fields:
        if not field.get("required"):
            continue
        name = str(field.get("name", ""))
        if not _answer_str(answers, name):
            label = str(field.get("label", name))
            return False, f"O campo «{label}» é obrigatório."

    if backend == "sftp":
        if (
            not _answer_str(answers, "password")
            and not _answer_str(answers, "key")
            and not _answer_str(answers, "key_file")
        ):
            return False, "Informe senha, ficheiro de chave ou PEM para SFTP."

    if backend == "terabox":
        from rdrive.core.cloud.terabox_setup import validate_terabox_cookie

        ok_cookie, cookie_msg = validate_terabox_cookie(_answer_str(answers, "cookie"))
        if not ok_cookie:
            return False, cookie_msg

    return True, ""


def check_guided_rclone_backend(
    backend_or_slug: str,
    rclone_cli: RcloneCli,
) -> tuple[bool, str]:
    """Pré-voo: o rclone instalado suporta o backend antes de ``config create``."""
    backend = canonical_backend(backend_or_slug)
    if backend == "terabox":
        from rdrive.core.cloud.terabox_setup import (
            terabox_backend_available,
            terabox_backend_install_message,
        )

        if not terabox_backend_available(rclone_cli):
            return False, terabox_backend_install_message()
    return True, ""


def build_guided_rclone_options(
    backend_or_slug: str,
    answers: dict[str, object] | None,
) -> dict[str, str]:
    """Mapeia respostas UI → opções ``rclone config create``."""
    backend = canonical_backend(backend_or_slug)
    opts: dict[str, str] = {}

    if backend == "s3":
        access_key = _answer_str(answers, "access_key")
        secret = _answer_str(answers, "secret")
        region = _answer_str(answers, "region")
        endpoint = _answer_str(answers, "endpoint")
        if access_key:
            opts["access_key_id"] = access_key
        if secret:
            opts["secret_access_key"] = secret
        if region:
            opts["region"] = region
        opts["env_auth"] = "false"
        if endpoint:
            opts["endpoint"] = endpoint
            opts["provider"] = "Other"
        else:
            opts["provider"] = "AWS"
    elif backend == "webdav":
        opts["url"] = _answer_str(answers, "url")
        user = _answer_str(answers, "user")
        password = _answer_str(answers, "password")
        if user:
            opts["user"] = user
        if password:
            opts["pass"] = password
        opts.setdefault("vendor", "other")
    elif backend == "sftp":
        opts["host"] = _answer_str(answers, "host")
        port = _answer_str(answers, "port") or "22"
        opts["port"] = port
        opts["user"] = _answer_str(answers, "user")
        password = _answer_str(answers, "password")
        key = _answer_str(answers, "key")
        key_file = _answer_str(answers, "key_file")
        if key_file:
            opts["key_file"] = key_file
        elif key:
            opts["key_pem"] = key
        elif password:
            opts["pass"] = password
    elif backend == "ftp":
        opts["host"] = _answer_str(answers, "host")
        opts["port"] = _answer_str(answers, "port") or "21"
        opts["user"] = _answer_str(answers, "user")
        opts["pass"] = _answer_str(answers, "password")
        if _answer_bool(answers, "explicit_tls"):
            opts["explicit_tls"] = "true"
    elif backend == "smb":
        opts["host"] = _answer_str(answers, "host")
        opts["share"] = _answer_str(answers, "share")
        domain = _answer_str(answers, "domain")
        if domain:
            opts["domain"] = domain
        opts["user"] = _answer_str(answers, "user")
        opts["pass"] = _answer_str(answers, "password")
    elif backend == "http":
        opts["url"] = _answer_str(answers, "url")
    elif backend == "terabox":
        from rdrive.core.cloud.terabox_setup import build_terabox_rclone_options, normalize_terabox_cookie

        cookie = normalize_terabox_cookie(_answer_str(answers, "cookie"))
        opts.update(build_terabox_rclone_options(cookie))

    return {key: value for key, value in opts.items() if value}


def guided_test_remote_path(
    backend_or_slug: str,
    remote_name: str,
    answers: dict[str, object] | None,
) -> str:
    """Caminho remoto para ``rclone lsd`` após criar o remote."""
    backend = canonical_backend(backend_or_slug)
    name = remote_name.strip()
    if backend == "s3":
        bucket = _answer_str(answers, "bucket")
        if bucket:
            return f"{name}:{bucket}"
    return f"{name}:"


def _sanitize_remote_part(text: str) -> str:
    """Converte texto legível num segmento seguro para nome de remote rclone."""
    normalized = text.strip().lower()
    if not normalized:
        return ""
    slug = re.sub(r"[^\w]+", "_", normalized, flags=re.ASCII)
    return re.sub(r"_+", "_", slug).strip("_")


def suggest_remote_name(provider_slug: str) -> str:
    """Sugere um nome de remote rclone a partir do slug do provedor."""
    key = provider_slug.strip().lower()
    if not key:
        return _REMOTE_NAME_SUGGESTIONS["drive"]
    if key in _REMOTE_NAME_SUGGESTIONS:
        return _REMOTE_NAME_SUGGESTIONS[key]
    backend = canonical_backend(key)
    if backend in _REMOTE_NAME_SUGGESTIONS:
        return _REMOTE_NAME_SUGGESTIONS[backend]
    safe = backend.replace("-", "_")
    if safe.endswith("_pessoal"):
        return safe
    return f"{safe}_pessoal"


def derive_remote_name(display_name: str, provider_slug: str) -> str:
    """Deriva o nome técnico do remote a partir do nome da unidade e do provedor."""
    fallback = suggest_remote_name(provider_slug)
    cleaned = display_name.strip()
    if not cleaned:
        return fallback

    part = _sanitize_remote_part(cleaned)
    if not part:
        return fallback

    provider_part = _sanitize_remote_part(display_name_for_backend(provider_slug))
    if part == provider_part:
        return fallback

    prefix = fallback.rsplit("_", 1)[0] if "_" in fallback else canonical_backend(provider_slug)
    provider_words = {word for word in provider_part.split("_") if word}
    name_words = [word for word in part.split("_") if word and word not in provider_words]
    suffix = "_".join(name_words) if name_words else "pessoal"
    candidate = f"{prefix}_{suffix}"
    return candidate[:64]


def provider_connection_guidance(provider_slug: str) -> str:
    """Texto de ajuda contextual conforme o tipo de autenticação do backend."""
    info = backend_setup_info(provider_slug)
    backend = info.backend
    if info.is_oauth:
        return (
            f"{backend}: clique em «Conectar conta» para OAuth no browser. "
            "O remote é guardado automaticamente no rclone."
        )
    if backend == "terabox":
        return (
            "TeraBox (experimental): rclone não oficial (PR rclone#8508). "
            "«Login e capturar cookie» no navegador integrado — o site bloqueia F12/DevTools. "
            "URL com /main após login."
        )
    if backend in _GUIDED_BACKENDS:
        return (
            f"{backend}: preencha o formulário guiado — o assistente configura o rclone "
            "sem terminal. Modo técnico disponível como alternativa."
        )
    if backend in _LOCAL_OR_NETWORK_BACKENDS:
        return (
            f"{backend}: configure host, pasta ou credenciais no assistente rclone (terminal). "
            "O nome sugerido do remote pode ser alterado antes de salvar."
        )
    return (
        f"{backend}: informe chaves, URL ou usuário/senha conforme o assistente rclone. "
        "Use «Conectar conta» para OAuth automático ou «Configurar manualmente» no terminal."
    )


def open_backend_docs(value: str) -> None:
    info = backend_setup_info(value)
    webbrowser.open(info.docs_url, new=2)


def open_readme_section(value: str) -> None:
    """Abre README.md na secção do agente para o backend indicado."""
    from rdrive.core.paths.project_paths import resolve_project_root

    anchor = readme_section_for_backend(value)
    readme = resolve_project_root() / "README.md"
    if readme.is_file():
        webbrowser.open(readme.resolve().as_uri() + f"#{anchor}", new=2)
    else:
        open_backend_docs(value)


def launch_setup_flow(
    rclone_cli: RcloneCli,
    backend_hint: str,
    remote_name: str,
) -> RemoteSetupInfo:
    info = backend_setup_info(backend_hint)
    open_backend_docs(info.backend)
    try:
        if remote_name.strip():
            rclone_cli.launch_config_in_terminal(remote_name=remote_name.strip(), backend=info.backend)
        else:
            rclone_cli.launch_config_in_terminal()
    except Exception:
        # A abertura do terminal pode falhar por ambiente; docs ainda ficam como fallback.
        pass
    return info
