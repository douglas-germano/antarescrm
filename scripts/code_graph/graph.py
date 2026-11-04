"""Evidence-backed extraction and parameterized Neo4j queries (Python standard library)."""

import ast
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

VERSION = '1'
TYPES = ('DEFINES', 'IMPORTS', 'CALLS', 'REFERENCES', 'EXPOSES', 'APPLIES_TO', 'VERIFIED_BY', 'DOCUMENTED_BY')
SOURCE_DIRS = (
    'backend/app/',
    'backend/tests/',
    'frontend/src/',
    'frontend/tests/',
    'frontend/browser-tests/',
    'scripts/',
)
RULES = 'docs/code-graph/rules.json'


def inventory(root):
    paths = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=root)
    return sorted(
        path
        for path in set(paths.decode().strip('\0').split('\0'))
        if path
        and not (root / path).is_symlink()
        and (root / path).is_file()
        and (
            (
                path.startswith(SOURCE_DIRS)
                and Path(path).suffix in {'.py', '.ts', '.tsx', '.js', '.mjs', '.jsx', '.css', '.svg', '.html'}
            )
            or (path.startswith('docs/') and path.endswith('.md'))
            or path in {RULES, 'frontend/tsconfig.json', 'frontend/package-lock.json'}
        )
    )


def fingerprint(root, paths=None):
    digest = hashlib.sha256(VERSION.encode())
    for path in paths if paths is not None else inventory(root):
        digest.update(path.encode() + b'\0' + (root / path).read_bytes() + b'\0')
    return digest.hexdigest()


def is_test(path):
    return '/tests/' in path or '/browser-tests/' in path


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}

    def node(self, identifier, kind, name, path, line=1, **properties):
        self.nodes[identifier] = dict(id=identifier, kind=kind, name=name, path=path, line=line, **properties)
        return identifier

    def edge(self, source, target, kind, path, line=1, origin='static'):
        if source == target:
            return
        key = (source, target, kind, path, line)
        self.edges[key] = dict(source=source, target=target, kind=kind, path=path, line=line, origin=origin)


def module_name(path):
    value = path.removesuffix('.py').replace('/', '.')
    if value.startswith('backend.'):
        value = value[len('backend.') :]
    return value.removesuffix('.__init__')


def import_bindings(tree, module, package):
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                result[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parent = module.split('.') if package else module.split('.')[:-1]
                base = '.'.join(parent[: len(parent) - node.level + 1] + ([base] if base else []))
            for item in node.names:
                if item.name != '*':
                    result[item.asname or item.name] = base + '.' + item.name
    return result


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else ''
    return ''


def python_graph(root, graph, paths):
    trees = {p: ast.parse((root / p).read_text(), filename=p) for p in paths if p.endswith('.py')}
    modules = {module_name(p): p for p in trees}
    definitions = {}
    aliases = {}
    locations = {}

    def define(path, node, prefix=''):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                identifier = path + '::' + name
                graph.node(
                    identifier, 'class' if isinstance(child, ast.ClassDef) else 'function', name, path, child.lineno
                )
                graph.edge(path, identifier, 'DEFINES', path, child.lineno)
                definitions[module_name(path) + '.' + name] = identifier
                locations[(path, child.lineno)] = identifier
                define(path, child, name + '.')
            else:
                define(path, child, prefix)

    for path, tree in trees.items():
        define(path, tree)
        # Only module-level imports participate in package re-export resolution.
        for name, target in import_bindings(
            ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))], type_ignores=[]),
            module_name(path),
            path.endswith('__init__.py'),
        ).items():
            aliases[module_name(path) + '.' + name] = target

    def resolve(name):
        seen = set()
        while name not in seen:
            seen.add(name)
            if name in definitions:
                return definitions[name]
            if name in modules:
                return modules[name]
            parts = name.split('.')
            for index in range(len(parts), 0, -1):
                prefix = '.'.join(parts[:index])
                if prefix in aliases:
                    name = aliases[prefix] + ('.' + '.'.join(parts[index:]) if parts[index:] else '')
                    break
            else:
                return None
        return None

    prefix = '/api/v1'
    if 'backend/app/__init__.py' in trees:
        for node in ast.walk(trees['backend/app/__init__.py']):
            if isinstance(node, ast.Call) and dotted(node.func).endswith('.register_blueprint'):
                for keyword in node.keywords:
                    if keyword.arg == 'url_prefix' and isinstance(keyword.value, ast.Constant):
                        prefix = keyword.value.value

    for path, tree in trees.items():
        module = module_name(path)
        bindings = import_bindings(tree, module, path.endswith('__init__.py'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in import_bindings(
                    ast.Module(body=[node], type_ignores=[]), module, path.endswith('__init__.py')
                ).values():
                    resolved = resolve(target)
                    if resolved:
                        graph.edge(path, graph.nodes[resolved]['path'], 'IMPORTS', path, node.lineno)

        class Visitor(ast.NodeVisitor):
            def __init__(self, source_path, source_module, source_bindings):
                self.path = source_path
                self.module = source_module
                self.bindings = source_bindings
                self.owner = source_path
                self.blocked = set()

            def visit_FunctionDef(self, node):
                owner, blocked = self.owner, self.blocked
                self.owner = locations[(self.path, node.lineno)]
                self.blocked = blocked | {
                    a.arg for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
                }
                self.blocked |= {a.arg for a in (node.args.vararg, node.args.kwarg) if a}
                self.blocked |= {
                    n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                }
                self.generic_visit(node)
                self.owner, self.blocked = owner, blocked

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):
                name = dotted(node.func)
                first, _, rest = name.partition('.')
                if name and first not in self.blocked:
                    target = self.bindings.get(first, self.module + '.' + first) + ('.' + rest if rest else '')
                    resolved = resolve(target)
                    if resolved:
                        graph.edge(self.owner, resolved, 'CALLS', self.path, node.lineno)
                        graph.edge(self.path, graph.nodes[resolved]['path'], 'REFERENCES', self.path, node.lineno)
                self.generic_visit(node)

        Visitor(path, module, bindings).visit(tree)
        if '/app/routes/' in path:
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not decorator.args:
                        continue
                    method = dotted(decorator.func)
                    if not method.startswith('bp.') or method.split('.')[-1] not in {
                        'get',
                        'post',
                        'put',
                        'patch',
                        'delete',
                        'route',
                    }:
                        continue
                    route = decorator.args[0]
                    if not isinstance(route, ast.Constant) or not isinstance(route.value, str):
                        continue
                    methods = [method.split('.')[-1].upper()]
                    if methods == ['ROUTE']:
                        methods = ['GET']
                        for keyword in decorator.keywords:
                            if keyword.arg == 'methods':
                                methods = ast.literal_eval(keyword.value)
                    for verb in methods:
                        label = verb + ' ' + prefix + route.value
                        identifier = 'endpoint:' + label
                        graph.node(identifier, 'endpoint', label, path, decorator.lineno)
                        graph.edge(locations[(path, node.lineno)], identifier, 'EXPOSES', path, decorator.lineno)

    # HTTP-based tests often exercise routes without importing their handlers.
    for path, tree in trees.items():
        if not is_test(path):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args or not isinstance(node.func, ast.Attribute):
                continue
            url = node.args[0]
            if (
                node.func.attr not in {'get', 'post', 'put', 'patch', 'delete'}
                or not isinstance(url, ast.Constant)
                or not isinstance(url.value, str)
            ):
                continue
            endpoint = graph.nodes.get('endpoint:' + node.func.attr.upper() + ' ' + url.value.split('?')[0])
            if endpoint:
                graph.edge(path, endpoint['id'], 'CALLS', path, node.lineno, origin='inferred')
                graph.edge(path, endpoint['path'], 'REFERENCES', path, node.lineno, origin='inferred')


def add_rules(root, graph):
    file = root / RULES
    if not file.exists():
        return
    for rule in json.loads(file.read_text()):
        identifier = 'rule:' + rule['id']
        graph.node(identifier, 'rule', rule['title'], RULES, description=rule['description'])
        for field, relationship in (
            ('applies_to', 'APPLIES_TO'),
            ('tests', 'VERIFIED_BY'),
            ('documents', 'DOCUMENTED_BY'),
        ):
            for reference in rule.get(field, []):
                path, anchor = reference['path'], reference['anchor']
                if path not in graph.nodes:
                    raise ValueError(f'Rule {identifier}: missing indexed file {path}')
                lines = (root / path).read_text().splitlines()
                matches = [i + 1 for i, line in enumerate(lines) if anchor in line]
                if len(matches) != 1:
                    raise ValueError(f'Rule {identifier}: anchor must match exactly once: {path}: {anchor}')
                graph.edge(identifier, path, relationship, path, matches[0], origin='curated')


def build(root):
    paths = inventory(root)
    before = fingerprint(root, paths)
    graph = Graph()
    for path in paths:
        graph.node(
            path, 'file', path, path, test=is_test(path), sha256=hashlib.sha256((root / path).read_bytes()).hexdigest()
        )
    python_graph(root, graph, paths)
    frontend = [p for p in paths if p.startswith('frontend/')]
    if frontend:
        parsed = subprocess.run(
            ['node', str(Path(__file__).with_name('frontend.mjs')), str(root)],
            input=json.dumps(frontend),
            text=True,
            capture_output=True,
            check=False,
        )
        if parsed.returncode:
            raise ValueError('Frontend extraction failed: ' + parsed.stderr[-1500:])
        data = json.loads(parsed.stdout)
        for edge in data['imports']:
            graph.edge(edge['source'], edge['target'], 'IMPORTS', edge['path'], edge['line'])
        for definition in data['definitions']:
            identifier = definition['path'] + '::' + definition['name']
            graph.node(identifier, **definition)
            graph.edge(definition['path'], identifier, 'DEFINES', definition['path'], definition['line'])
        # Literal HTTP paths are candidates: middleware, overrides and dynamic paths need review.
        for request in data['requests']:
            endpoint = graph.nodes.get('endpoint:' + request['method'] + ' /api/v1' + request['url'].split('?')[0])
            if endpoint:
                graph.edge(
                    request['path'], endpoint['id'], 'CALLS', request['path'], request['line'], origin='inferred'
                )
                graph.edge(
                    request['path'], endpoint['path'], 'REFERENCES', request['path'], request['line'], origin='inferred'
                )
    add_rules(root, graph)
    if fingerprint(root) != before:
        raise ValueError('Sources changed during extraction. Retry sync.')
    return graph, before


class Client:
    def __init__(self, url, auth_file):
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('Code graph must use a local HTTP(S) URL.')
        username, password = auth_file.read_text().strip().split('/', 1)
        self.url = url.rstrip('/') + '/db/neo4j/query/v2'
        self.auth = base64.b64encode(f'{username}:{password}'.encode()).decode()

    def query(self, statement, **parameters):
        request = Request(
            self.url,
            data=json.dumps({'statement': statement, 'parameters': parameters}).encode(),
            headers={
                'Authorization': 'Basic ' + self.auth,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
        )
        try:
            with urlopen(request, timeout=120) as response:
                body = json.load(response)
        except HTTPError as exc:
            raise ValueError(f'Neo4j HTTP {exc.code}; check the service and credentials file.') from None
        except URLError:
            raise ValueError('Neo4j unavailable. Run python3 scripts/code-graph.py init.') from None
        if body.get('errors'):
            raise ValueError(
                'Neo4j: ' + '; '.join(e.get('message', e.get('code', 'query failed')) for e in body['errors'])
            )
        data = body.get('data', {})
        return [dict(zip(data['fields'], row, strict=True)) for row in data.get('values', [])]


def sync(client, root, extracted):
    graph, digest = extracted
    repo = str(root)
    client.query('CREATE CONSTRAINT code_entity_id IF NOT EXISTS FOR (n:CodeEntity) REQUIRE (n.repo, n.id) IS UNIQUE')
    client.query('CREATE CONSTRAINT code_graph_repo IF NOT EXISTS FOR (g:CodeGraph) REQUIRE g.repo IS UNIQUE')
    # A single transaction: failed extraction/import leaves the previous snapshot available.
    statement = """MERGE (g:CodeGraph {repo: $repo}) SET g.lock = coalesce(g.lock, 0) + 1
        WITH g CALL { WITH g MATCH (old:CodeEntity {repo: $repo}) DETACH DELETE old }
        WITH g CALL { WITH g UNWIND $nodes AS row CREATE (n:CodeEntity) SET n = row, n.repo = $repo }"""
    for kind in TYPES:
        statement += f""" WITH g CALL {{ WITH g UNWIND $edges AS row
            WITH row WHERE row.kind = '{kind}'
            MATCH (a:CodeEntity {{repo: $repo, id: row.source}}), (b:CodeEntity {{repo: $repo, id: row.target}})
            CREATE (a)-[r:{kind}]->(b) SET r.path = row.path, r.line = row.line, r.origin = row.origin }}"""
    statement += """ SET g.fingerprint = $fingerprint, g.updated_at = $updated_at,
        g.nodes = $node_count, g.edges = $edge_count, g.version = $version RETURN properties(g) AS graph"""
    return client.query(
        statement,
        repo=repo,
        nodes=list(graph.nodes.values()),
        edges=list(graph.edges.values()),
        fingerprint=digest,
        updated_at=datetime.now(timezone.utc).isoformat(),
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        version=VERSION,
    )[0]['graph']


def search(client, root, text):
    return client.query(
        """MATCH (n:CodeEntity {repo: $repo})
        WHERE toLower(n.name) CONTAINS toLower($text)
        RETURN n.id AS id, n.kind AS kind, n.path AS path, n.line AS line
        ORDER BY kind, path, line LIMIT 100""",
        repo=str(root),
        text=text,
    )


def impact(client, root, paths, depth=3, limit=100):
    if not 1 <= depth <= 6 or limit < 1:
        raise ValueError('Depth must be 1..6 and limit must be positive.')
    repo = str(root)
    rows = client.query(
        f"""UNWIND $paths AS target
        MATCH (source:CodeEntity {{repo: $repo, id: target, kind: 'file'}})
        MATCH (dependent:CodeEntity {{repo: $repo, kind: 'file'}})
        MATCH p=shortestPath((dependent)-[:IMPORTS|REFERENCES*0..{depth}]->(source))
        RETURN dependent.id AS path, dependent.test AS candidate_test, source.id AS changed,
            length(p) AS distance,
            [r IN relationships(p) | {{path: r.path, line: r.line, kind: type(r), origin: r.origin}}] AS evidence
        ORDER BY distance, path, changed LIMIT $limit""",
        repo=repo,
        paths=paths,
        limit=limit + 1,
    )
    affected = sorted({row['path'] for row in rows[:limit]} | set(paths))
    rules = client.query(
        """MATCH (rule:CodeEntity {repo: $repo, kind: 'rule'})-[a:APPLIES_TO]->(f:CodeEntity)
        WHERE f.id IN $affected
        OPTIONAL MATCH (rule)-[r:VERIFIED_BY|DOCUMENTED_BY]->(e:CodeEntity)
        RETURN rule.id AS id, rule.name AS title, rule.description AS description,
            collect(DISTINCT {path: a.path, line: a.line}) AS applies_to,
            collect(DISTINCT CASE WHEN e IS NOT NULL THEN {kind: type(r), path: e.path, line: r.line} END) AS evidence
        ORDER BY id""",
        repo=repo,
        affected=affected,
    )
    indexed = client.query(
        'MATCH (n:CodeEntity {repo: $repo, kind: "file"}) WHERE n.id IN $paths RETURN n.id AS path',
        repo=repo,
        paths=paths,
    )
    return dict(
        paths=paths,
        depth=depth,
        truncated=len(rows) > limit,
        dependents=rows[:limit],
        rules=rules,
        unindexed=sorted(set(paths) - {row['path'] for row in indexed}),
        note='Static dependency candidates, not runtime coverage. Curated VERIFIED_BY links do not mean tests passed.',
    )
