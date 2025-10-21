# Certificate Field Placement Editor - Feature Documentation

## Overview
This feature allows administrators to customize the position and font size of certificate fields (name, IC, date, etc.) through a visual drag-and-drop interface. The editor is fully mobile responsive and saves settings to the database for use in certificate generation.

## Features Implemented

### 1. Database Model (CertificateTemplate)
- Stores position (x, y) and font size for 7 certificate fields:
  - Name
  - IC/Passport
  - Course Type
  - Percentage
  - Grade
  - Text
  - Date
- Supports multiple templates (only active template is used)
- Tracks creation and update timestamps

### 2. Visual Editor Interface
- **Drag-and-drop interface**: Field markers can be dragged to new positions
- **Real-time preview**: Changes are reflected immediately on the canvas
- **Manual input**: Precise positioning via input fields
- **Mobile responsive**: Works on tablets and smartphones with touch support
- **Active field highlighting**: Selected fields are highlighted in red
- **Coordinate display**: Shows current position on each marker

### 3. Routes Added
- `/certificate_template_editor` - Editor interface (GET)
- `/update_certificate_template` - Save settings (POST JSON)

### 4. Certificate Generation Integration
- `generate_certificate.py` updated to use template settings
- Automatically creates default template if none exists
- Falls back to default positions if template missing

## Installation & Setup

### Step 1: Run Database Migration
```bash
python migrate_certificate_template.py
```

This creates the `certificate_template` table and inserts a default template.

### Step 2: Access the Editor
1. Login as an admin user
2. Navigate to **Admin Dashboard** → **Certificate Management**
3. Click the **"Edit Field Placement"** button (green button at top)

## How to Use

### Basic Usage
1. **Drag markers**: Click and drag any colored marker to reposition it
2. **Use inputs**: Manually enter X/Y coordinates and font sizes in the right panel
3. **Click to select**: Click a marker to highlight it and scroll to its controls
4. **Save**: Click "Save Template" button to persist changes

### Understanding Coordinates
- **X-axis**: 0 (left) to 850 (right)
- **Y-axis**: 0 (bottom) to 600 (top) - PDF coordinate system
- **Canvas**: Visual representation with inverted Y-axis for easier positioning

### Field Descriptions
- **Name**: User's full name (default: center, large font)
- **IC/Passport**: Identification number
- **Course Type**: Course code (e.g., "TNG")
- **Percentage**: Overall score percentage
- **Grade**: Letter grade based on attempts
- **Text**: Static text "received training and fulfilled..."
- **Date**: Certificate issue date

### Reset to Defaults
Click "Reset to Defaults" to restore original positions:
- Name: (425, 290) - 28pt
- IC: (425, 260) - 14pt
- Course Type: (425, 230) - 14pt
- Percentage: (425, 200) - 14pt
- Grade: (425, 185) - 14pt
- Text: (425, 170) - 12pt
- Date: (425, 150) - 12pt

## Mobile Responsiveness

### Desktop (>1024px)
- Side-by-side layout: Preview on left, controls on right
- Large canvas for precise positioning
- Full-size markers and controls

### Tablet (768px - 1024px)
- Stacked layout: Preview on top, controls below
- Medium canvas size
- Touch-enabled dragging

### Mobile (<768px)
- Compact layout optimized for small screens
- Smaller markers and fonts
- Single-column input fields
- Touch-friendly controls

## Technical Details

### Database Schema
```sql
CREATE TABLE certificate_template (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) DEFAULT 'Default Template',
    name_x INTEGER DEFAULT 425,
    name_y INTEGER DEFAULT 290,
    name_font_size INTEGER DEFAULT 28,
    -- ... (similar for other fields)
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME,
    updated_at DATETIME
);
```

### API Endpoints

#### GET /certificate_template_editor
Returns the editor page with current template settings.

#### POST /update_certificate_template
Saves template settings. Expects JSON:
```json
{
  "name_x": 425,
  "name_y": 290,
  "name_font_size": 28,
  "ic_x": 425,
  ...
}
```

Returns:
```json
{
  "success": true,
  "message": "Template updated successfully"
}
```

### Files Modified/Created

#### New Files:
- `templates/certificate_template_editor.html` - Editor UI
- `migrate_certificate_template.py` - Database migration

#### Modified Files:
- `models.py` - Added CertificateTemplate model
- `routes.py` - Added editor routes
- `generate_certificate.py` - Updated to use template settings
- `templates/admin_certificates.html` - Added editor button

## Troubleshooting

### Issue: Template not saving
**Solution**: Check browser console for errors. Ensure admin is logged in.

### Issue: Markers not appearing
**Solution**: Check that certificate template PDF exists in `static/cert_templates/`

### Issue: Database error
**Solution**: Run migration script: `python migrate_certificate_template.py`

### Issue: Changes not reflected in certificates
**Solution**: 
1. Ensure changes are saved (check for success message)
2. Regenerate certificates after making changes
3. Check that CertificateTemplate.is_active = True

## Best Practices

1. **Test before deployment**: Generate test certificates after making changes
2. **Backup settings**: Note down working coordinates before major changes
3. **Use preview**: Visual preview helps but generate actual PDF to verify
4. **Font sizes**: Keep readable (name: 24-32pt, others: 12-16pt)
5. **Avoid edges**: Keep fields away from margins (50px buffer recommended)

## Future Enhancements

Potential improvements:
- Multiple template support with selection dropdown
- PDF background upload and preview
- Text color and font family customization
- Alignment options (left, center, right)
- Template import/export
- Undo/redo functionality

## Support

For issues or questions:
1. Check this documentation first
2. Verify all files are updated correctly
3. Check browser console for JavaScript errors
4. Review server logs for Python errors

---

**Last Updated**: October 14, 2025
**Version**: 1.0.0

