from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...parsers.banks.bankinter.xls_export import is_xls
from ...services import import_service as svc
from ...services.import_service import ConfirmIn, ServiceError

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB


def _raise(e: ServiceError):
    raise HTTPException(e.status_code, e.detail) from e


@router.post("/preview")
def preview(
    conta_id: int = Form(),
    file: UploadFile = File(),
    auth: Auth = Depends(require_auth),
    db: Session = Depends(get_db),
):
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Ficheiro demasiado grande (máx. 10 MB)")
    # Tipo real pelo conteúdo, não pela extensão: .xls (contentor binário) ou CSV de texto
    if is_xls(content):
        pass
    elif content.startswith(b"PK"):
        raise HTTPException(415, "Ficheiros .xlsx não são aceites: carregue o .xls original do homebanking")
    elif content.startswith(b"%PDF"):
        raise HTTPException(415, "PDF ainda não é aceite: carregue o .xls original do homebanking")
    elif b"\x00" in content:
        raise HTTPException(415, "O ficheiro não é um .xls nem um CSV de texto")
    try:
        return svc.preview(db, conta_id, file.filename or "ficheiro.csv", content, auth.utilizador.id)
    except ServiceError as e:
        _raise(e)


@router.get("")
def list_imports(_: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    return svc.list_imports(db)


@router.get("/{imp_id}")
def get_import(imp_id: int, _: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    try:
        return svc.get_view(db, imp_id)
    except ServiceError as e:
        _raise(e)


@router.post("/{imp_id}/confirm")
def confirm(imp_id: int, body: ConfirmIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    try:
        return svc.confirm(db, imp_id, body, auth.utilizador.id)
    except ServiceError as e:
        _raise(e)


@router.delete("/{imp_id}", status_code=204)
def revert(imp_id: int, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    try:
        svc.revert_or_cancel(db, imp_id, auth.utilizador.id)
    except ServiceError as e:
        _raise(e)
    return Response(status_code=204)
