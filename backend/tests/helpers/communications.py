from app.extensions import db
from app.models import Contact, MessageTemplate


def setup_channel(client, d):
    client.application.config['COMMUNICATION_ACCOUNTS'] = {
        d['ws'].id: {
            'email': {
                'host': 'smtp.example.test',
                'from_address': 'agency@example.test',
                'inbound_secret': 'test-inbound-secret',
            }
        }
    }
    contact = Contact(workspace_id=d['ws'].id, name='Lead', email='lead@example.test', phone='+5565999999999')
    template = MessageTemplate(
        workspace_id=d['ws'].id, name='Hello', channel='email', subject='Hello {{name}}', content='Welcome {{name}}'
    )
    db.session.add_all([contact, template])
    db.session.commit()
    return contact, template
