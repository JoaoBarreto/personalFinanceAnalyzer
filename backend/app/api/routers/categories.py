from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryIn(BaseModel):
    nome: str = Field(min_length=1)
    parent_id: int | None = None
    tipo: str | None = Field(
        default=None, pattern="^(despesa|receita|transferencia)$"
    )  # ignorado se tiver pai
    cor: str | None = None
    icone: str | None = None


class CategoryPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1)
    cor: str | None = None
    icone: str | None = None
    ativa: bool | None = None


class CategoryOut(BaseModel):
    id: int
    nome: str
    parent_id: int | None
    tipo: str
    cor: str | None
    icone: str | None
    ativa: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CategoryOut])
def list_categories(_: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    return db.scalars(select(Categoria).order_by(Categoria.parent_id.nulls_first(), Categoria.nome)).all()


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, _: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    tipo = body.tipo
    if body.parent_id is not None:
        parent = db.get(Categoria, body.parent_id)
        if parent is None:
            raise HTTPException(422, "Categoria-pai inexistente")
        if parent.parent_id is not None:
            raise HTTPException(422, "Máximo de 2 níveis de categorias")
        tipo = parent.tipo  # o filho herda o tipo do pai
    if tipo is None:
        raise HTTPException(422, "tipo é obrigatório para categorias de topo")
    cat = Categoria(nome=body.nome, parent_id=body.parent_id, tipo=tipo, cor=body.cor, icone=body.icone)
    db.add(cat)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma categoria com esse nome neste nível") from e
    return cat


@router.patch("/{cat_id}", response_model=CategoryOut)
def patch_category(
    cat_id: int, body: CategoryPatch, _: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    cat = db.get(Categoria, cat_id)
    if cat is None:
        raise HTTPException(404, "Categoria não encontrada")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma categoria com esse nome neste nível") from e
    return cat
