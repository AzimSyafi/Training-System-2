"""
Repair PostgreSQL sequences so they no longer produce duplicate key violations.

Usage examples:
  python repair_sequences.py               # run actual repair
  python repair_sequences.py --dry-run     # show what would be changed
  python repair_sequences.py --verbose     # verbose output

Logic:
  For each detected serial/identity-backed primary key sequence, set the sequence value
  to the current MAX(pk). If table empty, set sequence to 1 (is_called = false) so first
  nextval returns 1.

Safe: Does NOT drop or recreate tables; only adjusts sequences.

Requires: PostgreSQL (no-op on other dialects).
"""
from __future__ import annotations
import argparse
from typing import List, Tuple
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
from app import app
from models import db

# Optional explicit table/pk list fallback if pg_get_serial_sequence returns None
FALLBACK_PK_MAP = {
    'admin': 'admin_id',
    'agency': 'agency_id',
    'user': 'User_id',
    'module': 'module_id',
    'certificate': 'certificate_id',
    'trainer': 'trainer_id',
    'user_module': 'id',
    'course': 'course_id'
}

def detect_tables_with_pk() -> List[Tuple[str, str]]:
    insp = inspect(db.engine)
    tables = []
    for tbl in insp.get_table_names():
        try:
            pk = insp.get_pk_constraint(tbl)
            cols = pk.get('constrained_columns') if pk else []
            if cols:
                # Only handle single-column PK sequences
                if len(cols) == 1:
                    tables.append((tbl, cols[0]))
        except Exception:
            continue
    return tables

def get_sequence_name(table: str, pk_col: str) -> str | None:
    # Use pg_get_serial_sequence; returns qualified sequence name or None.
    sql = text("SELECT pg_get_serial_sequence(:table, :col)")
    seq = db.session.execute(sql, {"table": f"public.{table}", "col": pk_col}).scalar()
    if seq:
        return seq
    # Fallback to conventional naming
    candidate = f"{table}_{pk_col}_seq"
    try:
        exists = db.session.execute(text("SELECT 1 FROM pg_class WHERE relkind='S' AND relname=:r"), {"r": candidate}).scalar()
        if exists:
            return candidate
    except Exception:
        pass
    return None

def repair_sequences(dry_run: bool = False, verbose: bool = False) -> int:
    if db.engine.dialect.name != 'postgresql':
        print('[INFO] Non-PostgreSQL dialect detected; no sequence repair needed.')
        return 0

    pairs = detect_tables_with_pk()
    if verbose:
        print(f"[DEBUG] Detected PK tables: {pairs}")

    adjusted = 0
    for table, pk in pairs:
        seq_name = get_sequence_name(table, pk) or get_sequence_name(table, FALLBACK_PK_MAP.get(table, pk))
        if not seq_name:
            if verbose:
                print(f"[WARN] No sequence found for {table}.{pk}; skipping.")
            continue
        try:
            # Quote identifier safely (simple replace) to handle mixed-case edge though normally lowercased
            ident = pk.replace('"', '')
            max_id = db.session.execute(text(f'SELECT COALESCE(MAX("{ident}"), 0) FROM {table}')).scalar()
            # If table empty -> setval(seq, 1, false) so nextval returns 1.
            if max_id == 0:
                stmt = text("SELECT setval(:seq, 1, false)")
                action_desc = f"set {seq_name} to 1 (empty table)"
            else:
                # Align sequence to max_id (is_called = true so nextval = max_id+1)
                stmt = text("SELECT setval(:seq, :val, true)")
                action_desc = f"set {seq_name} to {max_id} (next will be {max_id + 1})"
            if dry_run:
                print(f"[DRY] Would {action_desc} for {table}.{pk}")
            else:
                db.session.execute(stmt, {"seq": seq_name, "val": max_id})
                adjusted += 1
                if verbose or True:
                    print(f"[OK] {action_desc} for {table}.{pk}")
        except SQLAlchemyError as e:
            if verbose:
                print(f"[ERR] Failed adjusting sequence for {table}.{pk}: {e}")
            db.session.rollback()
        except Exception as e:
            if verbose:
                print(f"[ERR] Unexpected error for {table}.{pk}: {e}")
            db.session.rollback()
    if not dry_run:
        try:
            db.session.commit()
        except Exception as e:
            print(f"[ERR] Commit failed: {e}")
            db.session.rollback()
            return 2
    print(f"Completed. Sequences adjusted: {adjusted}. Dry-run={dry_run}")
    return 0

def main():
    parser = argparse.ArgumentParser(description='Repair PostgreSQL sequences to prevent duplicate key errors.')
    parser.add_argument('--dry-run', action='store_true', help='Show planned changes without applying them')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    with app.app_context():
        code = repair_sequences(dry_run=args.dry_run, verbose=args.verbose)
    raise SystemExit(code)

if __name__ == '__main__':
    main()
