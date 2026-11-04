from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Conta
from ...parsers.generic.template import Template
from ...parsers.registry import GENERIC, PARSERS, PENDING
from ..scope import get_owned

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountIn(BaseModel):
    nome: str = Field(min_length=1)
    banco: str = Field(min_length=1)
    parser_id: str
    iban_mascarado: str | None = None
    moeda: str = Field(default="EUR", min_length=3, max_length=3)
    config_importacao: dict | None = None  # modelo do extrato (parser «generico»)


class AccountOut(AccountIn):
    id: int
    arquivada: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AccountOut])
def list_accounts(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    return db.scalars(select(Conta).where(Conta.dono_id == auth.utilizador.id).order_by(Conta.id)).all()


@router.post("", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    if body.parser_id not in (PENDING, GENERIC) and body.parser_id not in PARSERS:
        raise HTTPException(
            422, f"parser_id desconhecido; disponíveis: {sorted(PARSERS)}, {GENERIC!r} ou {PENDING!r}"
        )
    config = _validated_config(body.parser_id, body.config_importacao)
    conta = Conta(
        **{**body.model_dump(exclude={"config_importacao"}), "config_importacao": config},
        dono_id=auth.utilizador.id,
    )
    db.add(conta)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma conta com esse nome") from e
    return conta


def _validated_config(parser_id: str, config: dict | None) -> dict:
    """O modelo do parser genérico é validado SEMPRE (valores fixos, extra proibido); nos outros fica vazio."""
    if parser_id != GENERIC:
        if config:
            raise HTTPException(422, "config_importacao só se aplica ao parser «generico»")
        return {}
    try:
        return Template.model_validate(config or {}).model_dump(mode="json")
    except ValidationError as e:
        msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        raise HTTPException(422, f"Modelo de importação inválido: {msg}") from e


class AccountPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1)
    parser_id: str | None = None  # p.ex. passar de «pendente» ao parser do banco quando passar a existir
    config_importacao: dict | None = None
    arquivada: bool | None = None


@router.patch("/{conta_id}", response_model=AccountOut)
def patch_account(
    conta_id: int, body: AccountPatch, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    conta = get_owned(db, Conta, conta_id, auth.utilizador)
    data = body.model_dump(exclude_unset=True)
    if "parser_id" in data or "config_importacao" in data:
        parser_id = data.get("parser_id", conta.parser_id)
        if parser_id is None or (parser_id not in (PENDING, GENERIC) and parser_id not in PARSERS):
            raise HTTPException(
                422, f"parser_id desconhecido; disponíveis: {sorted(PARSERS)}, {GENERIC!r} ou {PENDING!r}"
            )
        data["parser_id"] = parser_id
        # só o parser «generico» tem modelo; ao mudar para outro parser o modelo antigo sai
        if parser_id == GENERIC:
            data["config_importacao"] = _validated_config(
                parser_id, data.get("config_importacao", conta.config_importacao)
            )
        else:
            _validated_config(
                parser_id, data.get("config_importacao")
            )  # recusa um modelo enviado sem sentido
            data["config_importacao"] = {}
    for k, v in data.items():
        setattr(conta, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma conta com esse nome") from e
    return conta
