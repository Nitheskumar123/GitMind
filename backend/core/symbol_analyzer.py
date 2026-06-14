"""
Symbol Analyzer - AST-based code symbol extraction.
Uses Python's ast module for Python files and pattern-based heuristics for JS.
"""

import ast
import re
import hashlib
import logging

logger = logging.getLogger(__name__)


class SymbolAnalyzer:
    """Extracts code symbols (functions, classes, variables, imports) using AST parsing."""

    def parse_file(self, code, file_path):
        """Parse a file and return extracted symbols based on file extension."""
        if file_path.endswith('.py'):
            return self.parse_python_symbols(code, file_path)
        elif file_path.endswith(('.js', '.jsx', '.ts', '.tsx')):
            return self.parse_javascript_symbols(code, file_path)
        return []

    def parse_python_symbols(self, code, file_path):
        """Extract symbols from Python code using ast module."""
        symbols = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"SyntaxError parsing {file_path}: {e}")
            return symbols

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                sig = self._extract_python_function_signature(node)
                symbols.append({
                    'type': 'function',
                    'name': node.name,
                    'line_start': node.lineno,
                    'line_end': node.end_lineno or node.lineno,
                    'signature': sig,
                    'hash': self._hash_lines(code, node.lineno, node.end_lineno),
                    'file_path': file_path,
                })

            elif isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(item.name)
                symbols.append({
                    'type': 'class',
                    'name': node.name,
                    'line_start': node.lineno,
                    'line_end': node.end_lineno or node.lineno,
                    'signature': {
                        'bases': [self._get_name(b) for b in node.bases],
                        'methods': methods,
                    },
                    'hash': self._hash_lines(code, node.lineno, node.end_lineno),
                    'file_path': file_path,
                })

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbols.append({
                        'type': 'import',
                        'name': alias.name,
                        'line_start': node.lineno,
                        'line_end': node.lineno,
                        'signature': {'alias': alias.asname},
                        'hash': '',
                        'file_path': file_path,
                    })

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    symbols.append({
                        'type': 'import',
                        'name': f"{module}.{alias.name}",
                        'line_start': node.lineno,
                        'line_end': node.lineno,
                        'signature': {'from': module, 'import': alias.name, 'alias': alias.asname},
                        'hash': '',
                        'file_path': file_path,
                    })

            elif isinstance(node, ast.Assign) and hasattr(node, 'lineno'):
                # Top-level variable assignments
                if isinstance(node, ast.Assign) and self._is_top_level(tree, node):
                    for target in node.targets:
                        name = self._get_name(target)
                        if name:
                            symbols.append({
                                'type': 'variable',
                                'name': name,
                                'line_start': node.lineno,
                                'line_end': node.end_lineno or node.lineno,
                                'signature': {},
                                'hash': self._hash_lines(code, node.lineno, node.end_lineno),
                                'file_path': file_path,
                            })

        return symbols

    def parse_javascript_symbols(self, code, file_path):
        """Extract symbols from JavaScript/TypeScript using pattern-based heuristics with bracket counting."""
        symbols = []
        lines = code.split('\n')

        # Function declarations: function name(...) {
        func_pattern = re.compile(
            r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            re.MULTILINE
        )
        # Arrow functions: const name = (...) => {
        arrow_pattern = re.compile(
            r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>',
            re.MULTILINE
        )
        # Class declarations: class Name {
        class_pattern = re.compile(
            r'^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{',
            re.MULTILINE
        )
        # Import statements
        import_pattern = re.compile(
            r'^\s*import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]',
            re.MULTILINE
        )

        # Parse functions
        for match in func_pattern.finditer(code):
            name = match.group(1)
            params = [p.strip() for p in match.group(2).split(',') if p.strip()]
            line_start = code[:match.start()].count('\n') + 1
            line_end = self._find_block_end(lines, line_start - 1)
            symbols.append({
                'type': 'function',
                'name': name,
                'line_start': line_start,
                'line_end': line_end,
                'signature': {'params': params},
                'hash': self._hash_lines(code, line_start, line_end),
                'file_path': file_path,
            })

        # Parse arrow functions
        for match in arrow_pattern.finditer(code):
            name = match.group(1)
            params = [p.strip() for p in match.group(2).split(',') if p.strip()]
            line_start = code[:match.start()].count('\n') + 1
            line_end = self._find_block_end(lines, line_start - 1)
            symbols.append({
                'type': 'function',
                'name': name,
                'line_start': line_start,
                'line_end': line_end,
                'signature': {'params': params},
                'hash': self._hash_lines(code, line_start, line_end),
                'file_path': file_path,
            })

        # Parse classes
        for match in class_pattern.finditer(code):
            name = match.group(1)
            base = match.group(2) or ''
            line_start = code[:match.start()].count('\n') + 1
            line_end = self._find_block_end(lines, line_start - 1)
            symbols.append({
                'type': 'class',
                'name': name,
                'line_start': line_start,
                'line_end': line_end,
                'signature': {'bases': [base] if base else []},
                'hash': self._hash_lines(code, line_start, line_end),
                'file_path': file_path,
            })

        # Parse imports
        for match in import_pattern.finditer(code):
            line_start = code[:match.start()].count('\n') + 1
            module = match.group(3)
            if match.group(1):
                # Named imports: { a, b }
                for imp in match.group(1).split(','):
                    imp = imp.strip()
                    if imp:
                        symbols.append({
                            'type': 'import',
                            'name': f"{module}.{imp}",
                            'line_start': line_start,
                            'line_end': line_start,
                            'signature': {'from': module, 'import': imp},
                            'hash': '',
                            'file_path': file_path,
                        })
            elif match.group(2):
                # Default import
                symbols.append({
                    'type': 'import',
                    'name': f"{module}.default",
                    'line_start': line_start,
                    'line_end': line_start,
                    'signature': {'from': module, 'import': match.group(2)},
                    'hash': '',
                    'file_path': file_path,
                })

        return symbols

    def build_dependency_graph(self, symbols):
        """Build inter-symbol dependency relationships."""
        symbol_names = {s['name'] for s in symbols}
        for sym in symbols:
            deps = []
            dependents = []
            # For imports, the dependency is the imported module
            if sym['type'] == 'import':
                continue
            # Check if any other symbol name appears in this symbol's hash (body)
            for other in symbols:
                if other['name'] == sym['name']:
                    continue
                if other['name'] in symbol_names:
                    # Simplified: just track names for now
                    if other['type'] in ('function', 'class') and sym.get('hash'):
                        deps.append(other['name'])
            sym['dependencies'] = deps
        return symbols

    # --- Helper methods ---

    def _extract_python_function_signature(self, node):
        """Extract function signature from AST FunctionDef node."""
        params = []
        for arg in node.args.args:
            param = {'name': arg.arg}
            if arg.annotation:
                param['annotation'] = self._get_name(arg.annotation)
            params.append(param)

        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, default in enumerate(node.args.defaults):
            params[defaults_offset + i]['default'] = True

        return_type = None
        if node.returns:
            return_type = self._get_name(node.returns)

        return {
            'params': params,
            'return_type': return_type,
            'decorators': [self._get_name(d) for d in node.decorator_list],
            'is_async': isinstance(node, ast.AsyncFunctionDef),
        }

    def _get_name(self, node):
        """Get name from various AST node types."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Subscript):
            return f"{self._get_name(node.value)}[{self._get_name(node.slice)}]"
        return str(type(node).__name__)

    def _is_top_level(self, tree, node):
        """Check if a node is at the top level of the module."""
        return node in tree.body

    def _hash_lines(self, code, start, end):
        """Hash a range of lines for change detection."""
        if not start or not end:
            return ''
        lines = code.split('\n')
        content = '\n'.join(lines[start - 1:end])
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _find_block_end(self, lines, start_idx):
        """Find the end of a JS block by counting braces."""
        brace_count = 0
        found_open = False
        for i in range(start_idx, len(lines)):
            for char in lines[i]:
                if char == '{':
                    brace_count += 1
                    found_open = True
                elif char == '}':
                    brace_count -= 1
            if found_open and brace_count <= 0:
                return i + 1  # 1-indexed
        return len(lines)
