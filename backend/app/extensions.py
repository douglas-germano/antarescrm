from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Same application-factory/blueprint/service separation as SDental.
db = SQLAlchemy()
migrate = Migrate(compare_type=True)
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=['300 per minute'])
