# Adding Guided Tours

This project uses [Driver.js v1.3.1](https://driverjs.com/) for step-by-step guided tours. Tour completion is tracked per-user in the database so each tour only auto-shows once.

## Architecture

```
app/static/js/modules/guided-tour.js          ← Tour manager (shared logic)
app/static/js/modules/tour-definitions/        ← Per-page step definitions
app/static/css/components/guided-tour.css      ← Styling overrides
```

## How to Add a New Tour

### 1. Create step definitions

Create a new file in `app/static/js/modules/tour-definitions/`:

```js
// tour-definitions/my-page-tour.js
export function getMyPageTourSteps() {
    return [
        {
            // Centered popover (no element)
            popover: {
                title: 'Welcome!',
                description: '<p>Introduction text...</p>',
                side: 'over',
                align: 'center',
            }
        },
        {
            // Anchored to an element
            element: '.my-selector',
            popover: {
                title: 'Feature Name',
                description: '<p>Explanation...</p>',
                side: 'bottom',
                align: 'start',
            }
        },
    ];
}
```

### 2. Add page detection in `guided-tour.js`

In the `getStepsForCurrentPage()` method, add a new case:

```js
if (document.querySelector('[data-tour-page="my-page"]')) {
    const { getMyPageTourSteps } = await import('./tour-definitions/my-page-tour.js');
    return getMyPageTourSteps();
}
```

### 3. Add database tracking column

In `app/models.py`, add to `DBUser`:

```python
has_seen_my_page_tour: Mapped[int] = mapped_column(Integer, default=0)
```

### 4. Create and run migration

```bash
alembic revision --autogenerate -m "add my_page tour tracking"
alembic upgrade head
```

### 5. Update the API endpoint

In `app/routes/api.py`, add to the `tour_columns` dict in `mark_tour_seen()`:

```python
tour_columns = {
    "turnusliste": "has_seen_turnusliste_tour",
    "my_page": "has_seen_my_page_tour",  # ← add this
}
```

### 6. Pass flag in route template context

In your route function, query the user's tour status and pass it to the template:

```python
has_seen_tour = 0
db_session = get_db_session()
try:
    db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
    if db_user:
        has_seen_tour = db_user.has_seen_my_page_tour or 0
finally:
    db_session.close()

return render_template("my_page.html", ..., has_seen_tour=has_seen_tour)
```

### 7. Add data attributes to template

On the main container div in your template:

```html
<div class="page-layout" data-tour-seen="{{ has_seen_tour }}" data-tour-page="my-page">
```

## Step Types

| Type | Config | Use Case |
|------|--------|----------|
| Anchored | `element: '.selector'` + `popover: {...}` | Highlight a specific UI element |
| Centered | `popover: {...}` (no `element`) | Informational steps, visual examples |

## Driver.js Reference

- [Driver.js Documentation](https://driverjs.com/docs/installation)
- Popover options: `title`, `description` (HTML allowed), `side`, `align`
- `side` values: `top`, `bottom`, `left`, `right`, `over`
- `align` values: `start`, `center`, `end`
