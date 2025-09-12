import os
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

def main():
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(templates_dir))
    errors = []
    for root, _, files in os.walk(templates_dir):
        for f in files:
            if not f.endswith('.html'):
                continue
            rel_dir = os.path.relpath(root, templates_dir)
            name = f if rel_dir == '.' else os.path.join(rel_dir, f)
            try:
                # Load via env to resolve extends/includes
                env.get_template(name)
                print(f"OK: {name}")
            except TemplateSyntaxError as e:
                errors.append((name, e.lineno, e.message))
                print(f"SYNTAX ERROR in {name} at line {e.lineno}: {e.message}")
            except Exception as e:
                errors.append((name, None, str(e)))
                print(f"ERROR in {name}: {e}")
    if errors:
        print("\nFound syntax errors:")
        for name, line, msg in errors:
            print(f" - {name}:{line or '?'}: {msg}")
        raise SystemExit(1)
    print("All templates compiled successfully.")

if __name__ == '__main__':
    main()

