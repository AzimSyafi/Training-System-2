"""
Direct migration runner - Run this with: python run_migration_direct.py
"""
import subprocess
import sys

print("="*60)
print("Certificate Template Field Visibility Migration")
print("="*60)
print()

try:
    # Run the migration script
    result = subprocess.run(
        [sys.executable, 'add_field_visibility_columns.py'],
        capture_output=True,
        text=True
    )

    # Print output
    print(result.stdout)

    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 0:
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Restart your Flask application")
        print("2. Go to Admin > Certificates > Edit Field Placement")
        print("3. Use the Hide/Show buttons for each field")
    else:
        print(f"\n❌ Migration failed with return code: {result.returncode}")
        sys.exit(1)

except Exception as e:
    print(f"\n❌ Error running migration: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

input("\nPress Enter to exit...")

