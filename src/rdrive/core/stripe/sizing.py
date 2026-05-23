from __future__ import annotations


_UNITS = {
    "B": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
}


def parse_size(value: str) -> int:
    text = value.strip().upper()
    if not text:
        return 0
    if text[-1].isdigit():
        return int(text)
    unit = text[-1]
    number = float(text[:-1])
    factor = _UNITS.get(unit)
    if not factor:
        raise ValueError(f"Unidade inválida em tamanho: {value}")
    return int(number * factor)
