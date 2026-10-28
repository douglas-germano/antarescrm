from werkzeug.security import generate_password_hash

from test_growth import env  # noqa: F401
from app.extensions import db
from app.models import AuditLog, User


def test_changing_the_login_email_needs_the_current_password_and_a_free_address(env):
    client, d = env
    owner = db.session.get(User, d['owner'].id)
    owner.password_hash = generate_password_hash('senha-atual-123')
    db.session.commit()
    patch = lambda body: client.patch('/api/v1/auth/me', headers=d['headers'](), json=body)  # noqa: E731
    assert patch({'email': 'novo@exemplo.com'}).status_code == 400
    assert patch({'email': 'novo@exemplo.com', 'current_password': 'errada'}).status_code == 400
    assert patch({'email': 'MEMBER@example.com', 'current_password': 'senha-atual-123'}).status_code == 409
    assert patch({'email': 'Novo@Exemplo.com', 'current_password': 'senha-atual-123'}).status_code == 200
    assert db.session.get(User, owner.id).email == 'novo@exemplo.com'
    assert AuditLog.query.filter_by(action='email_change').count() == 1
    # Saving the same address again, or only the name, needs no password.
    assert patch({'email': 'novo@exemplo.com', 'name': 'Dono'}).status_code == 200
