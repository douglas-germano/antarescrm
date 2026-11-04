from app.extensions import db
from app.models import Contact


def contact_for(d, **kw):
    row = Contact(workspace_id=d['ws'].id, name=kw.pop('name', 'Lead'), tags=kw.pop('tags', []), **kw)
    db.session.add(row)
    db.session.commit()
    return row
