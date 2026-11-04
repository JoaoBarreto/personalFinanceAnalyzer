from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Categoria, CategorizacaoGuardada, Movimento, Regra
from ..scope import get_owned, scope_conds

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
    n_movimentos: int = 0  # só preenchido na listagem

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CategoryOut])
def list_categories(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    user = auth.utilizador
    usados = dict(
        db.execute(
            select(Movimento.categoria_id, func.count())
            .where(*scope_conds(user))
            .group_by(Movimento.categoria_id)
        ).all()
    )
    cats = db.scalars(
        select(Categoria)
        .where(Categoria.dono_id == user.id)
        .order_by(Categoria.parent_id.nulls_first(), Categoria.nome)
    ).all()
    return [
        CategoryOut.model_validate(c).model_copy(update={"n_movimentos": usados.get(c.id, 0)}) for c in cats
    ]


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    tipo = body.tipo
    if body.parent_id is not None:
        parent = get_owned(
            db, Categoria, body.parent_id, auth.utilizador, status=422, msg="Categoria-pai inexistente"
        )
        if parent.parent_id is not None:
            raise HTTPException(422, "Máximo de 2 níveis de categorias")
        tipo = parent.tipo  # o filho herda o tipo do pai
    if tipo is None:
        raise HTTPException(422, "tipo é obrigatório para categorias de topo")
    cat = Categoria(
        nome=body.nome,
        parent_id=body.parent_id,
        tipo=tipo,
        cor=body.cor,
        icone=body.icone,
        dono_id=auth.utilizador.id,
    )
    db.add(cat)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma categoria com esse nome neste nível") from e
    return cat


@router.patch("/{cat_id}", response_model=CategoryOut)
def patch_category(
    cat_id: int, body: CategoryPatch, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)
):
    cat = get_owned(db, Categoria, cat_id, auth.utilizador)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(cat, k, v)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Já existe uma categoria com esse nome neste nível") from e
    return cat


@router.delete("/{cat_id}", status_code=204)
def delete_category(cat_id: int, auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    """Só se não estiver em uso (filhas, movimentos ou regras); caso contrário, desative-a."""
    cat = get_owned(db, Categoria, cat_id, auth.utilizador)
    if db.scalar(select(func.count()).select_from(Categoria).where(Categoria.parent_id == cat_id)):
        raise HTTPException(409, "Tem subcategorias: apague-as primeiro (ou desative a categoria).")
    if db.scalar(select(func.count()).select_from(Movimento).where(Movimento.categoria_id == cat_id)):
        raise HTTPException(409, "Há movimentos nesta categoria: desative-a em vez de a apagar.")
    if db.scalar(select(func.count()).select_from(Regra).where(Regra.categoria_id == cat_id)):
        raise HTTPException(
            409, "Há regras que usam esta categoria: apague-as primeiro (ou desative a categoria)."
        )
    # categorizações manuais guardadas (reset/reversão) para esta categoria: deixam de fazer sentido
    db.execute(delete(CategorizacaoGuardada).where(CategorizacaoGuardada.categoria_id == cat_id))
    db.delete(cat)
    db.commit()
