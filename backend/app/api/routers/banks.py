"""Bancos suportados e análise (mascarada) do formato de um extrato de um banco ainda não suportado."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...deps import Auth, require_auth
from ...parsers.generic.detector import detect, verify
from ...parsers.registry import BANKS
from ...services.statement_mask import UnsupportedFormat, describe_bytes

router = APIRouter(prefix="/api/banks", tags=["banks"])

MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


@router.get("")
def list_banks(auth: Auth = Depends(require_auth)):
    """Bancos com parser. Qualquer outro banco pode ter conta, mas só importa quando existir parser."""
    return BANKS


@router.post("/structure")
def statement_structure(
    file: UploadFile = File(),
    mostrar_rotulos: bool = Form(False),
    auth: Auth = Depends(require_auth),
):
    """Estrutura do extrato com letras→x e dígitos→9 (nada é gravado). Serve para pedir suporte a um banco novo
    sem expor descrições, nomes, IBAN nem valores: só o formato (colunas, datas, casas decimais)."""
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Ficheiro demasiado grande (máx. 10 MB)")
    try:
        return {"estrutura": describe_bytes(content, mostrar_rotulos)}
    except UnsupportedFormat as e:
        raise HTTPException(415, str(e)) from e
    except Exception as e:
        raise HTTPException(422, "Não foi possível ler o ficheiro (formato inválido ou protegido).") from e


def _read(file: UploadFile) -> bytes:
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Ficheiro demasiado grande (máx. 10 MB)")
    return content


def _json(texto: str | None, nome: str) -> dict:
    try:
        v = json.loads(texto) if texto else {}
    except ValueError as e:
        raise HTTPException(422, f"{nome} não é JSON válido") from e
    if not isinstance(v, dict):
        raise HTTPException(422, f"{nome} tem de ser um objeto")
    return v


@router.post("/detect")
def detect_template(
    file: UploadFile = File(),
    respostas: str | None = Form(None),
    auth: Auth = Depends(require_auth),
):
    """Propõe (e verifica) um modelo de importação para um extrato de qualquer banco. Nada é gravado: o ficheiro
    só é lido para a resposta. Com ambiguidades devolve `perguntas`; reenvie com `respostas` (JSON)."""
    try:
        return detect(_read(file), _json(respostas, "respostas"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, "Não foi possível ler o ficheiro (formato inválido ou protegido).") from e


@router.post("/verify")
def verify_template(
    file: UploadFile = File(),
    modelo: str = Form(),
    auth: Auth = Depends(require_auth),
):
    """Valida um modelo (p.ex. editado pelo utilizador) contra o ficheiro e devolve a amostra para confirmar."""
    try:
        return verify(_read(file), _json(modelo, "modelo"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, "Não foi possível ler o ficheiro (formato inválido ou protegido).") from e
