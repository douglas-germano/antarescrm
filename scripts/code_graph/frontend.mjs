// Parse imports with the project's TypeScript compiler; never execute application code.
import ts from '../../frontend/node_modules/typescript/lib/typescript.js';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.argv[2]);
const files = JSON.parse(fs.readFileSync(0, 'utf8'));
const configPath = path.join(root, 'frontend/tsconfig.json');
const config = ts.readConfigFile(configPath, ts.sys.readFile);
if (config.error) throw new Error(ts.flattenDiagnosticMessageText(config.error.messageText, '\n'));
const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, path.dirname(configPath));
if (parsed.errors.length) throw new Error(parsed.errors.map(e => ts.flattenDiagnosticMessageText(e.messageText, '\n')).join('\n'));
const known = new Set(files);
const imports = [];
const definitions = [];
const requests = [];
for (const file of files) {
  if (!/\.(?:[cm]?js|jsx|ts|tsx)$/.test(file)) continue;
  const absolute = path.join(root, file);
  const source = ts.createSourceFile(absolute, fs.readFileSync(absolute, 'utf8'), ts.ScriptTarget.Latest, true);
  if (source.parseDiagnostics.length) throw new Error(`Cannot parse ${file}`);
  const line = node => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  const apiNames = new Map();
  for (const node of source.statements) {
    if (!ts.isImportDeclaration(node) || !node.importClause?.namedBindings ||
        !ts.isNamedImports(node.importClause.namedBindings)) continue;
    const resolved = ts.resolveModuleName(node.moduleSpecifier.text, absolute, parsed.options, ts.sys).resolvedModule;
    if (resolved?.resolvedFileName !== path.join(root, 'frontend/src/lib/api.ts')) continue;
    for (const item of node.importClause.namedBindings.elements) {
      apiNames.set(item.name.text, item.propertyName?.text ?? item.name.text);
    }
  }
  const addImport = node => {
    const module = node.moduleSpecifier ?? node.arguments?.[0];
    if (!module || !ts.isStringLiteralLike(module)) return;
    const resolved = ts.resolveModuleName(module.text, absolute, parsed.options, ts.sys).resolvedModule;
    if (!resolved) {
      const asset = module.text.startsWith('@/') ? path.join(root, 'frontend/src', module.text.slice(2)) :
        module.text.startsWith('.') ? path.resolve(path.dirname(absolute), module.text) : null;
      const target = asset ? path.relative(root, asset).split(path.sep).join('/') : null;
      if (target && known.has(target)) {
        imports.push({source: file, target, path: file, line: line(node)});
        return;
      }
      if (module.text.startsWith('.') || module.text.startsWith('@/')) {
        throw new Error(`Unresolved local import ${module.text} at ${file}:${line(node)}`);
      }
      return;
    }
    const target = path.relative(root, resolved.resolvedFileName).split(path.sep).join('/');
    if (known.has(target)) imports.push({source: file, target, path: file, line: line(node)});
  };
  const visit = node => {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) addImport(node);
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(node.expression) && node.expression.text === 'require'))) addImport(node);
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.arguments[0] &&
        ts.isStringLiteralLike(node.arguments[0])) {
      const name = apiNames.get(node.expression.text);
      const methods = {useData: 'GET', useList: 'GET', usePage: 'GET', listAll: 'GET',
        post: 'POST', patch: 'PATCH', remove: 'DELETE'};
      if (methods[name]) requests.push({path: file, line: line(node), method: methods[name], url: node.arguments[0].text});
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  for (const node of source.statements) {
    if (node.name && (ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node) ||
        ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node))) {
      definitions.push({path: file, line: line(node), name: node.name.text,
        kind: ts.isFunctionDeclaration(node) ? 'function' : ts.isClassDeclaration(node) ? 'class' : 'type'});
    }
  }
}
process.stdout.write(JSON.stringify({imports, definitions, requests}));
