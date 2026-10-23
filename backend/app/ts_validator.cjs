// Isolated TypeScript syntax and AST parser runner
// Reads code from stdin and outputs JSON diagnostics and symbols

const fs = require('fs');
const path = require('path');

let ts;
const possiblePaths = [
  path.resolve(__dirname, '../../frontend/node_modules/typescript'),
  path.resolve(__dirname, '../node_modules/typescript'),
  'typescript'
];

for (const p of possiblePaths) {
  try {
    ts = require(p);
    if (ts) break;
  } catch (e) {}
}

if (!ts) {
  process.stdout.write(JSON.stringify({
    available: false,
    valid: null,
    status: 'parser_unavailable',
    error: 'TypeScript module could not be loaded'
  }));
  process.exit(0);
}

let inputCode = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { inputCode += chunk; });
process.stdin.on('end', () => {
  try {
    const sourceFile = ts.createSourceFile('snippet.ts', inputCode, ts.ScriptTarget.Latest, true);
    const diags = sourceFile.parseDiagnostics || [];

    if (diags.length > 0) {
      const errors = diags.map(d => {
        const { line, character } = sourceFile.getLineAndCharacterOfPosition(d.start || 0);
        const msg = typeof d.messageText === 'string' ? d.messageText : d.messageText.messageText;
        return { line: line + 1, col: character + 1, message: msg };
      });
      process.stdout.write(JSON.stringify({
        available: true,
        valid: false,
        status: 'invalid',
        errors: errors,
        symbols: []
      }));
      return;
    }

    const symbols = [];
    function visit(node) {
      if (ts.isFunctionDeclaration(node) && node.name) {
        const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        const params = node.parameters.map(p => p.name.getText(sourceFile));
        symbols.append ? null : symbols.push({
          type: 'Function',
          name: node.name.getText(sourceFile),
          line: line + 1,
          parameters: params
        });
      } else if (ts.isClassDeclaration(node) && node.name) {
        const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        symbols.push({
          type: 'Class',
          name: node.name.getText(sourceFile),
          line: line + 1,
          parameters: []
        });
      } else if (ts.isInterfaceDeclaration(node) && node.name) {
        const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        symbols.push({
          type: 'Interface',
          name: node.name.getText(sourceFile),
          line: line + 1,
          parameters: []
        });
      } else if (ts.isTypeAliasDeclaration(node) && node.name) {
        const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        symbols.push({
          type: 'TypeAlias',
          name: node.name.getText(sourceFile),
          line: line + 1,
          parameters: []
        });
      } else if (ts.isVariableStatement(node)) {
        for (const decl of node.declarationList.declarations) {
          if (decl.name) {
            const { line } = sourceFile.getLineAndCharacterOfPosition(decl.getStart(sourceFile));
            const isArrow = decl.initializer && (ts.isArrowFunction(decl.initializer) || ts.isFunctionExpression(decl.initializer));
            const params = isArrow ? decl.initializer.parameters.map(p => p.name.getText(sourceFile)) : [];
            symbols.push({
              type: isArrow ? 'ArrowFunction' : 'Variable',
              name: decl.name.getText(sourceFile),
              line: line + 1,
              parameters: params
            });
          }
        }
      }
      ts.forEachChild(node, visit);
    }

    visit(sourceFile);

    process.stdout.write(JSON.stringify({
      available: true,
      valid: true,
      status: 'verified',
      errors: [],
      symbols: symbols
    }));
  } catch (err) {
    process.stdout.write(JSON.stringify({
      available: true,
      valid: false,
      status: 'error',
      error: err.message,
      symbols: []
    }));
  }
});
