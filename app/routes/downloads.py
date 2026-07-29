import os
import logging
from flask import Blueprint, send_from_directory, flash, redirect, url_for
from flask_login import login_required
from config import AppConfig
from app.utils.turnus_helpers import get_user_turnus_set

logger = logging.getLogger(__name__)

downloads = Blueprint('downloads', __name__)


@downloads.route('/download_pdf')
@login_required
def download_pdf():
    # Get user's selected turnus set (same logic as other routes)
    turnus_set = get_user_turnus_set()
    if not turnus_set:
        flash('No turnus set found', 'danger')
        return redirect(url_for('shifts.turnusliste'))
    
    # Construct file path based on turnus set
    year_id = turnus_set['year_identifier'].lower()
    filename = f'turnuser_{turnus_set["year_identifier"]}.pdf'
    directory = os.path.join(AppConfig.turnusfiler_dir, year_id)
    file_path = os.path.join(directory, filename)
    
    # Check if file exists
    if not os.path.exists(file_path):
        flash(f'Turnus keys ZIP file not found for {turnus_set["year_identifier"]}. The file may not have been generated yet.', 'warning')
        return redirect(url_for('shifts.turnusliste'))
    
    return send_from_directory(directory, filename, as_attachment=True)


@downloads.route('/download/pdf/<path:filename>')
@login_required
def download_turnus_pdf(filename):
    """Serve a PDF from the user's turnus set's pdf/ directory.

    Replaces the dropdown's old url_for("static", …) links. Those worked only
    because the data store sat under app/static/, which served every file in it
    without authentication — the same hole that made the @login_required on
    download_pdf() and api.get_shift_image() decorative.
    """
    turnus_set = get_user_turnus_set()
    if not turnus_set:
        flash('Fant ingen turnus.', 'danger')
        return redirect(url_for('shifts.turnusliste'))

    year_id = turnus_set['year_identifier'].lower()
    directory = os.path.join(AppConfig.turnusfiler_dir, year_id, 'pdf')

    # Strip any directory component — the filename comes from a URL.
    safe_filename = os.path.basename(filename)
    if not safe_filename.lower().endswith('.pdf'):
        flash('Ugyldig fil.', 'danger')
        return redirect(url_for('shifts.turnusliste'))

    if not os.path.isfile(os.path.join(directory, safe_filename)):
        flash('Filen finnes ikke.', 'warning')
        return redirect(url_for('shifts.turnusliste'))

    return send_from_directory(directory, safe_filename)