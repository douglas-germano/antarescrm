"""Build-time API contracts from registered routes, Marshmallow inputs and public CRM models.

Generation requires the development-only apispec dependency. No database connection,
provider call or HTTP route is needed to generate these artifacts.
"""

import ast
import inspect
import re
import textwrap

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from marshmallow import Schema
from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, Numeric

from . import models, schemas
from .schemas.communications import WhatsAppSendSchema

CORE = {
    'Company': (models.Company, schemas.CompanySchema, '/companies', 'company_id'),
    'Contact': (models.Contact, schemas.ContactSchema, '/contacts', 'contact_id'),
    'Opportunity': (models.Opportunity, schemas.OpportunitySchema, '/opportunities', 'opportunity_id'),
    'Task': (models.Task, schemas.TaskSchema, '/tasks', 'task_id'),
    'PipelineStage': (models.PipelineStage, schemas.StageSchema, '/pipeline/stages', 'stage_id'),
    'Activity': (models.Activity, schemas.ActivitySchema, '/activities', 'activity_id'),
}


def response_schema(model, input_schema):
    properties = {}
    fields = input_schema().fields
    for column in model.__table__.columns:
        kind = column.type
        if isinstance(kind, Boolean):
            field = {'type': 'boolean'}
        elif isinstance(kind, Integer):
            field = {'type': 'integer'}
        elif isinstance(kind, Numeric):
            field = {'type': 'string', 'pattern': r'^-?\d+\.\d{2}$'}
        elif isinstance(kind, DateTime) or isinstance(getattr(kind, 'impl', None), DateTime):
            field = {'type': 'string', 'format': 'date-time'}
        elif isinstance(kind, Date):
            field = {'type': 'string', 'format': 'date'}
        elif isinstance(kind, JSON):
            field = (
                {'type': 'array', 'items': {'type': 'string'}}
                if column.name == 'tags'
                else {'type': 'object', 'additionalProperties': True}
            )
        else:
            field = {'type': 'string'}
            if getattr(kind, 'length', None):
                field['maxLength'] = kind.length
            if column.name == 'id' or column.name.endswith('_id'):
                field['format'] = 'uuid'
        if column.nullable:
            field['nullable'] = True
        validators = fields[column.name].validators if column.name in fields else []
        for validator in validators:
            if hasattr(validator, 'choices'):
                field['enum'] = list(validator.choices)
        if model is models.Opportunity and column.name == 'status':
            closed = schemas.CloseSchema().fields['status'].validators[0].choices
            field['enum'] = [column.default.arg, *closed]
        properties[column.name] = field
    return {'type': 'object', 'properties': properties, 'required': list(properties)}


def view_details(view):
    original = inspect.unwrap(view)
    try:
        function = next(
            node
            for node in ast.parse(textwrap.dedent(inspect.getsource(original))).body
            if isinstance(node, ast.FunctionDef)
        )
    except (OSError, StopIteration):
        return [], False
    inputs = []
    for node in ast.walk(function):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id != 'payload'
            or not node.args
        ):
            continue
        candidate = original.__globals__.get(node.args[0].id) if isinstance(node.args[0], ast.Name) else None
        if inspect.isclass(candidate) and issubclass(candidate, Schema):
            inputs.append(candidate)
    authenticated = any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id in ('require', 'jwt_required')
        for decorator in function.decorator_list
    )
    return list(dict.fromkeys(inputs)), authenticated


def build_spec(app):
    plugin = MarshmallowPlugin()
    spec = APISpec(title='Antares CRM API', version='1.0.0', openapi_version='3.0.3', plugins=[plugin])
    spec.components.security_scheme('bearerAuth', {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'})
    for name, header in {
        'instagramSignature': 'X-Hub-Signature-256',
        'whatsappSecret': 'X-Webhook-Secret',
        'whatsappSignature': 'X-Webhook-Signature',
        'communicationsSignature': 'X-Signature',
        'brevoSecret': 'X-Brevo-Secret',
    }.items():
        spec.components.security_scheme(name, {'type': 'apiKey', 'in': 'header', 'name': header})
    spec.components.schema(
        'ErrorResponse',
        {
            'type': 'object',
            'required': ['error'],
            'properties': {
                'error': {
                    'type': 'object',
                    'required': ['code', 'message'],
                    'properties': {
                        'code': {'type': 'string'},
                        'message': {'type': 'string'},
                        'details': {'nullable': True},
                    },
                }
            },
        },
    )
    names = {}
    for name, (model, schema, _, _) in CORE.items():
        spec.components.schema(name + 'Record', response_schema(model, schema))
        names[schema] = name + 'Input'
        spec.components.schema(name + 'Input', schema=schema)
        spec.components.schema(name + 'PatchInput', schema=schema(partial=True))
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: (item.rule, item.endpoint)):
        if not rule.rule.startswith('/api/v1/'):
            continue
        view = app.view_functions[rule.endpoint]
        inputs, authenticated = view_details(view)
        path = re.sub(r'<(?:[^:>]+:)?([^>]+)>', r'{\1}', rule.rule.removeprefix('/api/v1'))
        whatsapp_send = path in (
            '/whatsapp/conversations/{conversation_id}/messages',
            '/inbox/{source}/{thread_id}/messages',
        )
        if whatsapp_send and WhatsAppSendSchema not in inputs:
            inputs.append(WhatsAppSendSchema)
        parameters = [
            {
                'name': name,
                'in': 'path',
                'required': True,
                'schema': {
                    'type': 'string',
                    **({'format': 'uuid'} if converter.__class__.__name__ == 'UUIDConverter' else {}),
                },
            }
            for name, converter in sorted(rule._converters.items())
        ]
        operations = {}
        for method in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
            operation = {
                'operationId': rule.endpoint.replace('.', '_')
                + '_'
                + method.lower()
                + '_'
                + re.sub(r'\W+', '_', path).strip('_'),
                'tags': [rule.endpoint.split('.')[0]],
                'parameters': list(parameters),
                'responses': {
                    '2XX': {
                        'description': 'Operação concluída. Schemas de resposta detalhados estão disponíveis para os recursos CRM principais.'
                    },
                    'default': {
                        'description': 'Falha de validação, acesso ou processamento.',
                        'content': {'application/json': {'schema': {'$ref': '#/components/schemas/ErrorResponse'}}},
                    },
                },
            }
            if authenticated:
                operation['security'] = [{'bearerAuth': []}]
                operation['parameters'].append(
                    {
                        'name': 'X-Workspace-ID',
                        'in': 'header',
                        'required': False,
                        'schema': {'type': 'string', 'format': 'uuid'},
                    }
                )
            if method == 'POST' and path.startswith('/whatsapp/webhook'):
                operation['security'] = [{'whatsappSecret': []}, {'whatsappSignature': []}]
            elif method == 'POST' and path == '/instagram/webhook':
                operation['security'] = [{'instagramSignature': []}]
            elif method == 'POST' and path.startswith('/communications/receive/'):
                operation['security'] = [{'communicationsSignature': []}]
                operation['parameters'].append(
                    {
                        'name': 'X-Timestamp',
                        'in': 'header',
                        'required': True,
                        'schema': {'type': 'string', 'pattern': r'^\d+$'},
                    }
                )
            elif method == 'POST' and path.startswith('/brevo/webhook/'):
                operation['security'] = [{'brevoSecret': []}]
            for response in operation['responses'].values():
                response['headers'] = {
                    'X-Request-ID': {
                        'description': 'Identificador da operação nos logs do backend.',
                        'schema': {'type': 'string'},
                    }
                }
            if method in ('POST', 'PATCH', 'PUT') and inputs:
                references = []
                for schema in inputs:
                    name = names.get(schema)
                    if name is None:
                        name = (
                            ''.join(part.title().replace('_', '') for part in schema.__module__.split('.')[2:])
                            + schema.__name__.removesuffix('Schema')
                            + 'Input'
                        )
                        names[schema] = name
                        spec.components.schema(name, schema=schema)
                    if method == 'PATCH':
                        name = name.removesuffix('Input') + 'PatchInput'
                        if name not in spec.components.schemas:
                            spec.components.schema(name, schema=schema(partial=True))
                    references.append({'$ref': '#/components/schemas/' + name})
                operation['requestBody'] = {
                    'required': True,
                    'content': {
                        'application/json': {'schema': references[0] if len(references) == 1 else {'anyOf': references}}
                    },
                }
                if whatsapp_send:
                    operation['requestBody']['content']['multipart/form-data'] = {
                        'schema': {
                            'type': 'object',
                            'required': ['file', 'idempotency_key'],
                            'properties': {
                                'file': {'type': 'string', 'format': 'binary'},
                                'content': {'type': 'string', 'maxLength': 20000},
                                'idempotency_key': {'type': 'string', 'minLength': 1, 'maxLength': 100},
                            },
                        }
                    }
            for name, (_, _, collection, identifier) in CORE.items():
                if path not in (collection, collection + '/{' + identifier + '}') or method == 'DELETE':
                    continue
                result = {'$ref': '#/components/schemas/' + name + 'Record'}
                if method == 'GET' and path == collection:
                    paginated = collection != '/pipeline/stages'
                    result = {
                        'type': 'object',
                        'required': ['items'],
                        'properties': {'items': {'type': 'array', 'items': result}},
                    }
                    if paginated:
                        result['required'] += ['page', 'per_page', 'pages', 'total']
                        result['properties'].update(
                            {key: {'type': 'integer'} for key in ('page', 'per_page', 'pages', 'total')}
                        )
                        operation['parameters'] += [
                            {
                                'name': key,
                                'in': 'query',
                                'schema': {
                                    'type': 'integer',
                                    'minimum': 1,
                                    **({'maximum': 100} if key == 'per_page' else {}),
                                },
                            }
                            for key in ('page', 'per_page')
                        ]
                operation['responses']['2XX']['content'] = {'application/json': {'schema': result}}
            operations[method.lower()] = operation
        spec.path(path=path, operations=operations)
    result = spec.to_dict()
    result['servers'] = [{'url': '/api/v1'}]
    result['info']['description'] = (
        'Inventário gerado das rotas. Entradas reutilizam Marshmallow; respostas tipadas cobrem os recursos CRM principais. Endpoints de provedores têm autenticação própria descrita no guia de manutenção.'
    )
    return result
