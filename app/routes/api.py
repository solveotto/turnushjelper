import glob
import logging
import os
import re

from flask import Blueprint, jsonify, request, send_from_directory
from flask_login import current_user, login_required

from app.database import get_db_session
from app.extensions import cache, favorite_lock
from app.models import DBUser, SoknadsskjemaChoice
from app.services import user_service
from app.utils import db_utils, shift_matcher
from app.utils.turnus_helpers import get_user_turnus_set
from config import AppConfig

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")


@api.route("/js_select_shift", methods=["POST"])
def select_shift():
    data = request.get_json() or {}
    shift_title = data.get("shift_title")

    if shift_title:
        # Redirect to the display_shift page instead of returning JSON
        from flask import redirect, url_for

        return redirect(url_for("shifts.display_shift", shift_title=shift_title))
    else:
        return jsonify({"status": "error", "message": "No shift title provided"})


@api.route("/toggle_favorite", methods=["POST"])
@login_required
def toggle_favorite():
    data = request.get_json() or {}
    favorite = data.get("favorite")
    shift_title = data.get("shift_title")

    # Validate input
    if not shift_title:
        return jsonify({"status": "error", "message": "No shift title provided"})

    if favorite not in [True, False]:
        return jsonify({"status": "error", "message": "Invalid favorite value"})

    with favorite_lock:
        try:
            # Get user's selected turnus set
            from app.utils.turnus_helpers import get_user_turnus_set

            user_turnus_set = get_user_turnus_set()
            turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

            if not turnus_set_id:
                return jsonify({"status": "error", "message": "No turnus set selected"})

            user_id = current_user.get_id()

            def _build_favorites_payload(message):
                updated = db_utils.get_favorite_lst(user_id, turnus_set_id)
                positions = {name: idx + 1 for idx, name in enumerate(updated)}
                # Invalidate the cached turnusliste page so the next full load reflects the change
                from app.extensions import cache as _cache
                _cache.delete(f"view/turnusliste/{user_id}/{turnus_set_id}")
                return {"status": "success", "message": message, "favorites": updated, "positions": positions}

            if favorite:
                # Check if already exists first (handle potential duplicates from hibernation)
                existing_favorites = db_utils.get_favorite_lst(user_id, turnus_set_id)
                if shift_title in existing_favorites:
                    # Already exists, just return success (cleanup handled in get_favorite_lst)
                    return jsonify(_build_favorites_payload("Already in favorites"))

                # Calculate the next order index for the user's selected turnus set
                order_index = db_utils.get_max_ordered_index(user_id, turnus_set_id) + 1
                success = db_utils.add_favorite(
                    user_id, shift_title, order_index, turnus_set_id
                )
                if success:
                    return jsonify(_build_favorites_payload("Added to favorites"))
                else:
                    return jsonify(
                        {
                            "status": "error",
                            "message": "Failed to add favorite - may already exist",
                        }
                    )
            else:
                # Check if exists before trying to remove
                existing_favorites = db_utils.get_favorite_lst(user_id, turnus_set_id)
                if shift_title not in existing_favorites:
                    return jsonify(_build_favorites_payload("Already removed from favorites"))

                success = db_utils.remove_favorite(user_id, shift_title, turnus_set_id)
                if success:
                    return jsonify(_build_favorites_payload("Removed from favorites"))
                else:
                    return jsonify(
                        {"status": "error", "message": "Failed to remove favorite"}
                    )
        except Exception as e:
            logger.error("Error in toggle_favorite: %s", e)
            return jsonify({"status": "error", "message": f"Server error: {str(e)}"})


@api.route("/move-favorite", methods=["POST"])
@login_required
def move_favorite():
    data = request.get_json() or {}
    shift_title = data.get("shift_title")
    direction = data.get("direction")
    user_id = current_user.get_id()

    if not shift_title or direction not in ["up", "down"]:
        return jsonify({"status": "error", "message": "Invalid parameters"})

    db_session = None
    try:
        # Get user's selected turnus set
        from app.utils.turnus_helpers import get_user_turnus_set

        user_turnus_set = get_user_turnus_set()
        turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

        if not turnus_set_id:
            return jsonify({"status": "error", "message": "No turnus set selected"})

        db_session = db_utils.get_db_session()

        # Get current favorites with order FOR THE SPECIFIC TURNUS SET
        current_favorites = (
            db_session.query(db_utils.Favorites)
            .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
            .order_by(db_utils.Favorites.order_index)
            .all()
        )

        if not current_favorites:
            db_session.close()
            return jsonify({"status": "error", "message": "No favorites found"})

        # Find current position
        current_index = None
        for i, favorite in enumerate(current_favorites):
            if favorite.shift_title == shift_title:
                current_index = i
                break

        if current_index is None:
            db_session.close()
            return jsonify({"status": "error", "message": "Favorite not found"})

        # Calculate new position
        if direction == "up" and current_index > 0:
            new_index = current_index - 1
        elif direction == "down" and current_index < len(current_favorites) - 1:
            new_index = current_index + 1
        else:
            db_session.close()
            return jsonify(
                {"status": "error", "message": "Cannot move in that direction"}
            )

        # Swap the order_index values
        current_favorite = current_favorites[current_index]
        target_favorite = current_favorites[new_index]

        # Store the current order_index values
        temp_order = current_favorite.order_index
        current_favorite.order_index = target_favorite.order_index
        target_favorite.order_index = temp_order

        # Commit the changes
        db_session.commit()
        db_session.close()

        return jsonify({"status": "success", "message": "Favorite moved successfully"})

    except Exception as e:
        if db_session is not None:
            db_session.rollback()
            db_session.close()
        return jsonify({"status": "error", "message": str(e)})


@api.route("/set-favorite-position", methods=["POST"])
@login_required
def set_favorite_position():
    """Move a favorite directly to a specific position."""
    data = request.get_json() or {}
    shift_title = data.get("shift_title")
    new_position = data.get("new_position")  # 1-indexed position from user
    user_id = current_user.get_id()

    if not shift_title or new_position is None:
        return jsonify({"status": "error", "message": "Invalid parameters"})

    try:
        new_position = int(new_position)
        if new_position < 1:
            return jsonify(
                {"status": "error", "message": "Position must be at least 1"}
            )
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Position must be a number"})

    db_session = None
    try:
        # Get user's selected turnus set
        from app.utils.turnus_helpers import get_user_turnus_set

        user_turnus_set = get_user_turnus_set()
        turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

        if not turnus_set_id:
            return jsonify({"status": "error", "message": "No turnus set selected"})

        db_session = db_utils.get_db_session()

        # Get current favorites ordered by order_index
        current_favorites = (
            db_session.query(db_utils.Favorites)
            .filter_by(user_id=user_id, turnus_set_id=turnus_set_id)
            .order_by(db_utils.Favorites.order_index)
            .all()
        )

        if not current_favorites:
            db_session.close()
            return jsonify({"status": "error", "message": "No favorites found"})

        # Clamp position to valid range
        max_position = len(current_favorites)
        new_position = min(new_position, max_position)
        new_index = new_position - 1  # Convert to 0-indexed

        # Find the favorite to move
        favorite_to_move = None
        current_index = 0
        for i, favorite in enumerate(current_favorites):
            if favorite.shift_title == shift_title:
                favorite_to_move = favorite
                current_index = i
                break

        if favorite_to_move is None:
            db_session.close()
            return jsonify({"status": "error", "message": "Favorite not found"})

        # If already at the target position, nothing to do
        if current_index == new_index:
            db_session.close()
            return jsonify({"status": "success", "message": "Already at that position"})

        # Remove the favorite from the list and reinsert at new position
        current_favorites.pop(current_index)
        current_favorites.insert(new_index, favorite_to_move)

        # Reassign order_index values based on new positions
        for i, favorite in enumerate(current_favorites):
            favorite.order_index = i

        db_session.commit()
        db_session.close()

        return jsonify({"status": "success", "message": "Favorite position updated"})

    except Exception as e:
        if db_session is not None:
            db_session.rollback()
            db_session.close()
        return jsonify({"status": "error", "message": str(e)})


@api.route("/generate-turnusnokkel", methods=["POST"])
@login_required
def generate_turnusnokkel():
    data = request.get_json() or {}
    turnus_name = data.get("turnus_name")
    turnus_set_id = data.get("turnus_set_id")

    if not turnus_name or not turnus_set_id:
        return jsonify(
            {"status": "error", "message": "Missing turnus name or turnus set ID"}
        )

    try:
        logger.debug(
            "Generating turnusnøkkel for turnus_name=%s, turnus_set_id=%s",
            turnus_name,
            turnus_set_id,
        )

        # Import the turnusnøkkel generator
        import tempfile

        from flask import send_file

        from app.utils.turnusnokkel_gen import TurnusnokkelGen

        # Create generator instance and generate the turnusnøkkel
        generator = TurnusnokkelGen(turnus_name, turnus_set_id)
        result = generator.generate_single_turnus_nokkel()

        logger.debug("Turnusnøkkel generator result: %s", result)

        if result["success"]:
            # Get the workbook object from the result
            workbook = result.get("workbook")
            filename = result["filename"]

            if workbook:
                # Create a temp file, close it, then save workbook to it
                # (Windows locks files so we can't have two handles open)
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                temp_file_path = temp_file.name
                temp_file.close()
                workbook.save(temp_file_path)

                try:
                    response = send_file(
                        temp_file_path,
                        as_attachment=True,
                        download_name=filename,
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    # Clean up temp file after response is sent
                    @response.call_on_close
                    def cleanup():
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)

                    return response
                except Exception as e:
                    logger.error("Error creating workbook: %s", e)
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                    raise
            else:
                return jsonify(
                    {"status": "error", "message": "Generated workbook not found"}
                )
        else:
            return jsonify({"status": "error", "message": result["error"]})

    except Exception as e:
        return jsonify(
            {"status": "error", "message": f"Failed to generate turnusnøkkel: {str(e)}"}
        )


@api.route("/import-favorites-preview", methods=["POST"])
@login_required
def import_favorites_preview():
    """
    Preview what favorites would be imported from one or more turnus sets.
    Finds shifts in the current turnus set that are statistically similar
    to the user's favorites from the source turnus set(s).

    Supports both single source (legacy) and multiple sources (new):
    - source_turnus_set_id: Single source ID (for backwards compatibility)
    - source_turnus_set_ids: List of source IDs (new multi-year feature)
    """
    data = request.get_json() or {}
    source_turnus_set_id = data.get("source_turnus_set_id")
    source_turnus_set_ids = data.get("source_turnus_set_ids")
    innplassering_source_ids = data.get("innplassering_source_ids")
    top_n = data.get("top_n", 5)

    # Handle top_n early so innplassering branch can use it
    try:
        top_n = int(top_n)
        if top_n == 0:
            top_n = 999
        elif top_n < 0:
            top_n = 5
    except (ValueError, TypeError):
        top_n = 5

    # Innplassering mode — must be checked before favorites mode
    if innplassering_source_ids is not None:
        try:
            inn_ids = [int(i) for i in innplassering_source_ids]
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Invalid innplassering source IDs"})

        from app.utils.turnus_helpers import get_user_turnus_set
        user_turnus_set = get_user_turnus_set()
        target_turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

        if not target_turnus_set_id:
            return jsonify({"status": "error", "message": "No active turnus set selected"})

        inn_ids = [i for i in inn_ids if i != target_turnus_set_id]
        if not inn_ids:
            return jsonify({"status": "error", "message": "Source and target turnus sets are the same"})

        user_id = current_user.get_id()
        result = shift_matcher.find_matches_from_innplassering(
            user_id=user_id,
            innplassering_source_ids=inn_ids,
            target_turnus_set_id=target_turnus_set_id,
            top_n=top_n,
        )

        if not result["all_favorites"]:
            return jsonify({"status": "error", "message": "Ingen innplasseringsdata funnet eller statistikk mangler."})

        target_set = db_utils.get_turnus_set_by_id(target_turnus_set_id)
        if not target_set:
            return jsonify({"status": "error", "message": "Target turnus set not found"}), 404

        return jsonify({
            "status": "success",
            "mode": "innplassering",
            "target_set": {
                "id": target_set["id"],
                "name": target_set["name"],
                "year_identifier": target_set["year_identifier"],
            },
            "by_source": result["by_source"],
            "matches": result["all_favorites"],
        })

    # Handle both single and multiple sources
    if source_turnus_set_ids:
        # New multi-source mode
        try:
            source_ids = [int(sid) for sid in source_turnus_set_ids]
        except (ValueError, TypeError):
            return jsonify(
                {"status": "error", "message": "Invalid source turnus set IDs"}
            )
    elif source_turnus_set_id:
        # Legacy single-source mode
        try:
            source_ids = [int(source_turnus_set_id)]
        except (ValueError, TypeError):
            return jsonify(
                {"status": "error", "message": "Invalid source turnus set ID"}
            )
    else:
        return jsonify({"status": "error", "message": "No source turnus set provided"})

    # Get current turnus set
    from app.utils.turnus_helpers import get_user_turnus_set

    user_turnus_set = get_user_turnus_set()
    target_turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    if not target_turnus_set_id:
        return jsonify({"status": "error", "message": "No active turnus set selected"})

    # Remove target from sources if present
    source_ids = [sid for sid in source_ids if sid != target_turnus_set_id]

    if not source_ids:
        return jsonify(
            {"status": "error", "message": "Source and target turnus sets are the same"}
        )

    user_id = current_user.get_id()

    # Use multi-source function if multiple sources, otherwise use original
    if len(source_ids) > 1:
        result = shift_matcher.find_matches_from_multiple_sources(
            user_id=user_id,
            source_turnus_set_ids=source_ids,
            target_turnus_set_id=target_turnus_set_id,
            top_n=top_n,
        )

        if not result["all_favorites"]:
            return jsonify(
                {
                    "status": "error",
                    "message": "No favorites found in source turnus sets or stats unavailable",
                }
            )

        target_set = db_utils.get_turnus_set_by_id(target_turnus_set_id)
        if not target_set:
            return jsonify(
                {"status": "error", "message": "Target turnus set not found"}
            ), 404

        return jsonify(
            {
                "status": "success",
                "mode": "multi_source",
                "target_set": {
                    "id": target_set["id"],
                    "name": target_set["name"],
                    "year_identifier": target_set["year_identifier"],
                },
                "by_source": result["by_source"],
                "matches": result["all_favorites"],  # Combined best matches
            }
        )
    else:
        # Single source - use original function
        matches = shift_matcher.find_matches_for_favorites(
            user_id=user_id,
            source_turnus_set_id=source_ids[0],
            target_turnus_set_id=target_turnus_set_id,
            top_n=top_n,
        )

        if not matches:
            return jsonify(
                {
                    "status": "error",
                    "message": "No favorites found in source turnus set or stats unavailable",
                }
            )

        # Get info about the turnus sets
        source_set = db_utils.get_turnus_set_by_id(source_ids[0])
        target_set = db_utils.get_turnus_set_by_id(target_turnus_set_id)

        if not source_set or not target_set:
            return jsonify({"status": "error", "message": "Turnus set not found"}), 404

        return jsonify(
            {
                "status": "success",
                "mode": "single_source",
                "source_set": {
                    "id": source_set["id"],
                    "name": source_set["name"],
                    "year_identifier": source_set["year_identifier"],
                },
                "target_set": {
                    "id": target_set["id"],
                    "name": target_set["name"],
                    "year_identifier": target_set["year_identifier"],
                },
                "matches": matches,
            }
        )


@api.route("/import-favorites-confirm", methods=["POST"])
@login_required
def import_favorites_confirm():
    """
    Add selected shifts as favorites in the current turnus set.
    """
    data = request.get_json() or {}
    shifts_to_add = data.get("shifts", [])

    if not shifts_to_add:
        return jsonify({"status": "error", "message": "No shifts provided"})

    if not isinstance(shifts_to_add, list):
        return jsonify({"status": "error", "message": "Shifts must be a list"})

    # Get current turnus set
    from app.utils.turnus_helpers import get_user_turnus_set

    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    if not turnus_set_id:
        return jsonify({"status": "error", "message": "No active turnus set selected"})

    user_id = current_user.get_id()

    with favorite_lock:
        try:
            # Get existing favorites to avoid duplicates
            existing_favorites = db_utils.get_favorite_lst(user_id, turnus_set_id)
            current_max_index = db_utils.get_max_ordered_index(user_id, turnus_set_id)

            added = []
            skipped = []

            for shift_title in shifts_to_add:
                if shift_title in existing_favorites:
                    skipped.append(shift_title)
                    continue

                current_max_index += 1
                success = db_utils.add_favorite(
                    user_id, shift_title, current_max_index, turnus_set_id
                )

                if success:
                    added.append(shift_title)
                    existing_favorites.append(shift_title)  # Update local list
                else:
                    skipped.append(shift_title)

            return jsonify(
                {
                    "status": "success",
                    "message": f"Added {len(added)} favorites",
                    "added": added,
                    "skipped": skipped,
                }
            )

        except Exception as e:
            return jsonify(
                {"status": "error", "message": f"Error adding favorites: {str(e)}"}
            )


@api.route("/get-turnus-sets-for-import", methods=["GET"])
@login_required
def get_turnus_sets_for_import():
    """
    Get list of turnus sets that can be used as import sources.
    Only returns sets where the user has favorites and stats are available.
    """
    user_id = current_user.get_id()

    # Get current turnus set to exclude it
    from app.utils.turnus_helpers import get_user_turnus_set

    user_turnus_set = get_user_turnus_set()
    current_turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Get all turnus sets with stats
    sets_with_stats = shift_matcher.get_all_turnus_sets_with_stats()

    # Filter to only sets where user has favorites (and not current set)
    available_sets = []
    for ts in sets_with_stats:
        if ts["id"] == current_turnus_set_id:
            continue

        # Check if user has favorites in this set
        favorites = db_utils.get_favorite_lst(user_id, ts["id"])
        if favorites:
            ts["favorite_count"] = len(favorites)
            available_sets.append(ts)

    return jsonify(
        {
            "status": "success",
            "turnus_sets": available_sets,
            "current_set": {
                "id": current_turnus_set_id,
                "name": user_turnus_set["name"] if user_turnus_set else None,
                "year_identifier": user_turnus_set["year_identifier"]
                if user_turnus_set
                else None,
            }
            if user_turnus_set
            else None,
        }
    )


@api.route("/shift-image/<int:turnus_set_id>/<shift_nr>")
@login_required
def get_shift_image(turnus_set_id, shift_nr):
    """
    Serve shift timeline PNG image from static files.
    Converts turnus_set_id to the appropriate version identifier.
    """
    # Get turnus set to find year_identifier
    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        return jsonify({"status": "error", "message": "Turnus set not found"}), 404

    # Convert year_identifier (e.g., "R26") to folder name (e.g., "r26")
    version = turnus_set["year_identifier"].lower()

    # Build path to PNG directory
    png_dir = os.path.join(AppConfig.turnusfiler_dir, version, "streklister", "png")

    # Sanitize shift_nr to prevent path traversal and normalize whitespace
    # Remove all whitespace to match filename convention (PDF names may have line breaks)
    safe_shift_nr = re.sub(r"\s+", "", os.path.basename(shift_nr))

    # Try exact match first
    exact_path = os.path.join(png_dir, f"{safe_shift_nr}.png")
    if os.path.isfile(exact_path):
        return send_from_directory(
            png_dir, f"{safe_shift_nr}.png", mimetype="image/png"
        )

    # Try to find files that start with the shift number (handles suffixes like -Mod_1, -N05_1)
    pattern = os.path.join(png_dir, f"{safe_shift_nr}*.png")
    matches = glob.glob(pattern)
    if matches:
        # Return the first match (prefer shorter names)
        matches.sort(key=len)
        filename = os.path.basename(matches[0])
        return send_from_directory(png_dir, filename, mimetype="image/png")

    return jsonify({"status": "error", "message": "Ingen tidslinje tilgjengelig"}), 404


@api.route("/mark-tour-seen", methods=["POST"])
@login_required
def mark_tour_seen():
    """Mark a guided tour as seen for the current user."""
    data = request.get_json() or {}
    tour_name = data.get("tour_name")

    # Map tour names to column names
    tour_columns = {
        "turnusliste": "has_seen_turnusliste_tour",
    }

    if tour_name not in tour_columns:
        return jsonify({"status": "error", "message": "Unknown tour name"}), 400

    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=current_user.id).first()
        if user:
            setattr(user, tour_columns[tour_name], 1)
            db_session.commit()
            # Invalidate the cached turnusliste page so the next load renders
            # with the updated has_seen_tour value instead of the stale cached one.
            ts = get_user_turnus_set()
            ts_id = ts["id"] if ts else "none"
            cache.delete(f"view/turnusliste/{current_user.get_id()}/{ts_id}")
            return jsonify({"status": "success", "message": "Tour marked as seen"})
        return jsonify({"status": "error", "message": "User not found"}), 404
    except Exception as e:
        db_session.rollback()
        logger.error("Error marking tour seen: %s", e)
        return jsonify({"status": "error", "message": "Server error"}), 500
    finally:
        db_session.close()


@api.route("/soknadsskjema-choice", methods=["POST"])
@login_required
def soknadsskjema_choice():
    """Upsert a single Kolonne 2 / 4 cell choice for the søknadsskjema."""
    data = request.get_json() or {}
    shift_title = data.get("shift_title", "").strip()
    field       = data.get("field")

    BOOL_FIELDS = ("linje_135", "linje_246", "h_dag")
    STR_FIELDS  = ("linjeprioritering",)

    if not shift_title or field not in (*BOOL_FIELDS, *STR_FIELDS):
        return jsonify(status="error", message="Invalid input"), 400

    user_id = int(current_user.get_id())

    from app.utils.turnus_helpers import get_user_turnus_set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    if turnus_set_id is None:
        return jsonify(status="error", message="No turnus set"), 400

    db_session = get_db_session()
    try:
        row = db_session.query(SoknadsskjemaChoice).filter_by(
            user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title
        ).first()
        if row is None:
            row = SoknadsskjemaChoice(
                user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title
            )
            db_session.add(row)
        if field in BOOL_FIELDS:
            value = bool(data.get("value"))
            setattr(row, field, int(value))
            return_value = value
        else:  # STR_FIELDS
            value = str(data.get("value") or "").strip()
            setattr(row, field, value or None)
            return_value = value
        db_session.commit()
        return jsonify(status="success", field=field, value=return_value)
    except Exception as e:
        db_session.rollback()
        logger.error("soknadsskjema_choice error: %s", e)
        return jsonify(status="error", message="DB error"), 500
    finally:
        db_session.close()


@api.route("/check-rullenummer")
def check_rullenummer():
    """Return stub-user info for the registration name-preview widget.

    Response shape:
        {found: true,  name: "Etternavn, Fornavn", stasjoneringssted: "OSLO"}
        {found: false, reason: "already_registered"}
        {found: false, reason: "not_authorized"}
    """
    rullenummer = (request.args.get("rullenummer") or "").strip()
    if not rullenummer:
        return jsonify({"found": False, "reason": "not_authorized"})

    stub = user_service.get_user_by_rullenummer(rullenummer)
    if stub is None:
        return jsonify({"found": False, "reason": "not_authorized"})
    if stub["is_stub"] != 1:
        return jsonify({"found": False, "reason": "already_registered"})

    return jsonify({
        "found": True,
        "name": stub["name"] or "",
        "stasjoneringssted": stub["stasjoneringssted"] or "",
    })
