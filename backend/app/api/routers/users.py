from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...deps import Auth, get_db, require_auth
from ...models import Utilizador

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    username: str
    nome: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[UserOut])
def list_users(auth: Auth = Depends(require_auth), db: Session = Depends(get_db)):
    """Só o próprio utilizador: os outros utilizadores não são visíveis (isolamento por dono)."""
    return db.scalars(select(Utilizador).where(Utilizador.id == auth.utilizador.id)).all()
