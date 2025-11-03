# Quick inspector: print normalized quiz data per module
# Run: python scripts\admin_quiz_inspector.py
from app import app
from models import Module
import json

# Reuse same normalization logic as admin_debug_quiz

def normalize(obj):
    if obj is None:
        return []
    # If it's already a list of new-format
    if isinstance(obj, list) and obj:
        first = obj[0]
        if isinstance(first, dict) and (first.get('text') or (isinstance(first.get('answers'), list) and isinstance(first.get('answers')[0] if first.get('answers') else None, dict))):
            return obj
        # legacy list with question/answers
        if isinstance(first, dict) and (first.get('question') or isinstance(first.get('answers'), list)):
            out = []
            for q in obj:
                raw_answers = q.get('answers') or q.get('choices') or []
                mapped = []
                if isinstance(raw_answers, list):
                    for i, a in enumerate(raw_answers):
                        if isinstance(a, dict):
                            mapped.append({'text': a.get('text', str(a)), 'isCorrect': bool(a.get('isCorrect', False))})
                        else:
                            try:
                                is_corr = (q.get('correct') is not None and int(q.get('correct')) == (i+1))
                            except Exception:
                                is_corr = False
                            mapped.append({'text': str(a), 'isCorrect': is_corr})
                out.append({'text': q.get('question') or q.get('text') or '', 'answers': mapped})
            return out
    # object with questions key
    if isinstance(obj, dict):
        if isinstance(obj.get('questions'), list):
            return normalize(obj.get('questions'))
        if isinstance(obj.get('quiz'), list):
            return normalize(obj.get('quiz'))
        if obj.get('text') and obj.get('answers'):
            raw_answers = obj.get('answers') or []
            mapped = []
            if isinstance(raw_answers, list):
                for a in raw_answers:
                    if isinstance(a, dict):
                        mapped.append({'text': a.get('text', str(a)), 'isCorrect': bool(a.get('isCorrect', False))})
                    else:
                        mapped.append({'text': str(a), 'isCorrect': False})
            return [{'text': obj.get('text'), 'answers': mapped}]
    return []


with app.app_context():
    modules = Module.query.all()
    print('Total modules in DB:', len(modules))
    found_any = False
    if not modules:
        print('No modules found in DB')
    for m in modules:
        raw = getattr(m, 'quiz_json', None)
        # Treat empty string or '[]' as effectively empty for admin UI
        is_blank = raw is None or (isinstance(raw, str) and raw.strip() in ('', '[]', 'null'))
        if is_blank:
            # Print short line for modules without quiz
            print(f"Module: {m.module_id} - {m.module_name}  (no quiz_json)")
            continue
        found_any = True
        parsed = None
        parse_ok = False
        try:
            parsed = json.loads(raw)
            parse_ok = True
        except Exception as e:
            parsed = str(e)
            parse_ok = False
        normalized = normalize(parsed if parse_ok else None)
        print('Module:', m.module_id, '-', m.module_name)
        print('  course_id:', getattr(m, 'course_id', None), 'series:', getattr(m, 'series_number', None))
        print('  raw preview:', (raw[:200] + '...') if isinstance(raw, str) and len(raw) > 200 else raw)
        print('  parse_ok:', parse_ok)
        if parse_ok:
            if isinstance(parsed, list):
                print('  parsed: list length', len(parsed))
            elif isinstance(parsed, dict):
                print('  parsed: dict keys', list(parsed.keys()))
            else:
                print('  parsed type:', type(parsed))
        else:
            print('  parse_error:', parsed)
        print('  normalized_count:', len(normalized))
        if len(normalized) > 0:
            sample = normalized[0]
            try:
                print('  sample[0]: text_len=', len(sample.get('text','')) , 'answers_count=', len(sample.get('answers', [])))
            except Exception:
                print('  sample[0]:', sample)
        print('-' * 60)
    if not found_any:
        print('No modules with non-empty quiz_json found')
