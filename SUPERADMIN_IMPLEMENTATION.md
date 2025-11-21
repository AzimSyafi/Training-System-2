# Superadmin Role Implementation Guide

## Overview

This document describes the implementation of the Superadmin role in the Training System. The Superadmin role provides elevated privileges for critical system operations that regular admins should not have access to.

## Key Features

### 1. Role Differentiation

**Regular Admin** capabilities:
- View and manage users, trainers, and authority accounts
- Manage courses and modules
- Monitor progress and generate reports
- View certificates

**Superadmin** exclusive capabilities:
- Create, edit, and delete admin accounts
- Promote admins to superadmin
- Delete admin accounts (except their own)
- Future: System configuration, logs viewer, backups

## Implementation Details

### Database Schema

**Table:** `admin`

New column added:
- `is_superadmin` BOOLEAN NOT NULL DEFAULT FALSE

### Files Modified

1. **models.py**
   - Added `is_superadmin` field to Admin model

2. **utils.py**
   - Added `is_superadmin(user=None)` function
   - Added `@superadmin_required` decorator
   - Added `@admin_or_superadmin_required` decorator
   - Registered `is_superadmin` as Jinja global function

3. **routes.py**
   - Updated `/create_user` endpoint to require superadmin for creating admins
   - Added superadmin checkbox support for creating superadmins
   - Added `/delete_admin` endpoint (superadmin only)

4. **templates/base.html**
   - Added superadmin badge styling
   - Display "Superadmin" badge in sidebar for superadmin users

5. **create_admin.py**
   - Added `is_superadmin` parameter
   - Interactive prompt for creating superadmins

### Migration Script

**File:** `migrations/add_superadmin_column.py`

Run this script to add the `is_superadmin` column to the database:

```bash
python migrations/add_superadmin_column.py
```

## Usage Instructions

### Creating a Superadmin Account

**Method 1: Using create_admin.py script**

```bash
python create_admin.py
```

Follow the prompts and answer "yes" when asked about superadmin creation.

**Method 2: Promoting existing admin**

```sql
UPDATE admin SET is_superadmin = TRUE WHERE admin_id = <id>;
```

### Checking Superadmin Status

In Python code:
```python
from utils import is_superadmin

if is_superadmin():
    # Superadmin-only code
    pass
```

In Jinja templates:
```jinja
{% if is_superadmin() %}
    <!-- Superadmin-only UI elements -->
{% endif %}
```

### Protecting Routes

Use the decorator on sensitive routes:

```python
from utils import superadmin_required

@main_bp.route('/sensitive_operation', methods=['POST'])
@login_required
@superadmin_required
def sensitive_operation():
    # Only superadmins can access this
    pass
```

## Security Considerations

1. **Self-Deletion Prevention**: Superadmins cannot delete their own account
2. **Role Elevation**: Only superadmins can create or promote other superadmins
3. **Access Control**: All superadmin-only operations check permissions server-side
4. **Audit Trail**: All admin operations are logged with user information

## User Interface

### Superadmin Badge

Superadmins see a gold "SUPERADMIN" badge in the sidebar next to their username.

### Admin Management UI

The admin creation form includes a checkbox "Create as Superadmin" that is only visible to superadmins.

## Future Enhancements

Planned features for superadmin role:
1. System logs viewer
2. Database backup and restore
3. System configuration management
4. Global settings administration
5. Authority account management
6. Advanced reporting and analytics

## Troubleshooting

### Issue: is_superadmin column doesn't exist

**Solution:** Run the migration script:
```bash
python migrations/add_superadmin_column.py
```

### Issue: No superadmin accounts exist

**Solution:** Create a superadmin using create_admin.py or manually update an existing admin:
```sql
UPDATE admin SET is_superadmin = TRUE WHERE email = 'admin@example.com';
```

### Issue: Superadmin badge not showing

**Solution:** Ensure `is_superadmin` is registered as a Jinja global in utils.py and the function is being imported correctly.

## Testing Checklist

- [ ] Regular admin cannot create admin accounts
- [ ] Regular admin cannot delete admin accounts
- [ ] Superadmin can create regular admin accounts
- [ ] Superadmin can create superadmin accounts
- [ ] Superadmin can delete other admin accounts
- [ ] Superadmin cannot delete their own account
- [ ] Superadmin badge appears in sidebar
- [ ] Migration script runs without errors
- [ ] create_admin.py script supports superadmin creation

## Support

For issues or questions about the superadmin implementation, contact the development team.
