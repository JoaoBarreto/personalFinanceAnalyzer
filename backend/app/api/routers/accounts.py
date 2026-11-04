from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Conta
from ...parsers.registry import PARSERS
from ..scope import get_owned

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountIn(BaseModel):
    nome: str = Field(min_length=1)
    banco: str = Field(min_length=1)
    parser_id: str
    iban_mascarado: str | None = None
    moeda: str = Field(default="EUR", min_length=3, max_length=3)


class AccountOut(AccountIn):
    id: int
    arquivada: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AccountOut])
def list_accounts(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    return db.scalars(select(Conta).where(Conta.dono_id == auth.utilizador.id).order_by(Conta.id)).all()


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    if body.parser_id not in PARSERS:
        raise HTTPException(422, f"parser_id desconhecido; disponíveis: {sorted(PARSERS)}")
    conta = Conta(**body.model_dump(), dono_id=auth.utilizador.id)
    db.add(conta)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma conta com esse nome") from e
    return conta


class AccountPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1)
    arquivada: bool | None = None


@router.patch("/{conta_id}", response_model=AccountOut)
def patch_account(
    conta_id: int, body: AccountPatch, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    conta = get_owned(db, Conta, conta_id, auth.utilizador)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(conta, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma conta com esse nome") from e
    return conta
