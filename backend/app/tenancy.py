"""Explicit account scope for application services; HTTP authentication constructs this context."""

from dataclasses import dataclass

from .common import APIError


@dataclass(frozen=True)
class AccountContext:
    workspace_id: str
    user_id: str

    def __post_init__(self):
        if not self.workspace_id or not self.user_id:
            raise ValueError('Account services require an authenticated workspace and user.')

    def query(self, model):
        return model.query.filter_by(workspace_id=self.workspace_id)

    def get(self, model, identifier, *, lock=False):
        query = self.query(model).filter_by(id=str(identifier))
        row = (query.with_for_update() if lock else query).first()
        if row is None:
            raise APIError('Registro não encontrado.', 404)
        return row
