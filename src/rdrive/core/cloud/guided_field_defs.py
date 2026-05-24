"""Campos dos formulários guiados (Static + CTk)."""

from __future__ import annotations

GUIDED_FIELD_DEFS: dict[str, list[dict[str, str | bool]]] = {
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
            "name": "cookie",
            "label": "Cookie de sessão",
            "type": "password",
            "required": True,
            "placeholder": "Preenchido automaticamente por «Ligar conta TeraBox»",
            "help": (
                "Use «Ligar conta TeraBox» — faça login no Edge do RDrive; "
                "o cookie é importado automaticamente (deve conter ndus=)."
            ),
        },
    ],
}
