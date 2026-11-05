from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.routes.admin import admin
from app.services import broadcast_email_service, user_service

STATE_LABELS = {
    broadcast_email_service.DRAFT: ("Utkast", "secondary"),
    broadcast_email_service.SENDING: ("Sender", "primary"),
    broadcast_email_service.STOPPED: ("Stoppet", "warning"),
    broadcast_email_service.DONE: ("Sendt", "success"),
    broadcast_email_service.CLOSED: ("Avsluttet", "secondary"),
}


def _flash_result(ok, message):
    flash(message, "success" if ok else "danger")


def _to_detail(broadcast_id):
    return redirect(url_for("admin.broadcast_detail", broadcast_id=broadcast_id))


def _own_address():
    """The admin's address, if it is one: create_user() can store the username."""
    data = user_service.get_user_data(current_user.username)
    email = (data or {}).get("email") or ""
    return email if "@" in email else ""


@admin.route("/epost", methods=["GET"])
@admin_required
def broadcast_index():
    mode, addresses = broadcast_email_service.recipient_mode()
    return render_template(
        "admin_broadcast.html",
        mode=mode,
        addresses=addresses,
        recipient_count=broadcast_email_service.recipient_count(),
        broadcasts=broadcast_email_service.list_broadcasts(),
        state_labels=STATE_LABELS,
        max_subject=broadcast_email_service.MAX_SUBJECT_CHARS,
        max_body=broadcast_email_service.MAX_BODY_CHARS,
    )


@admin.route("/epost", methods=["POST"])
@admin_required
def broadcast_create():
    ok, message, broadcast_id = broadcast_email_service.create_draft(
        request.form.get("subject"), request.form.get("body"), current_user.id
    )
    _flash_result(ok, message)
    return _to_detail(broadcast_id) if ok else redirect(url_for("admin.broadcast_index"))


@admin.route("/epost/<int:broadcast_id>", methods=["GET"])
@admin_required
def broadcast_detail(broadcast_id):
    broadcast = broadcast_email_service.get_broadcast(broadcast_id)
    if broadcast is None:
        abort(404)
    _, preview_html = broadcast_email_service.render_email(broadcast["subject"], broadcast["body"], "#")
    mode, addresses = broadcast_email_service.recipient_mode()
    return render_template(
        "admin_broadcast_detail.html",
        broadcast=broadcast,
        preview_html=preview_html,
        mode=mode,
        addresses=addresses,
        recipient_count=broadcast_email_service.recipient_count(),
        own_address=_own_address(),
        state_labels=STATE_LABELS,
        max_subject=broadcast_email_service.MAX_SUBJECT_CHARS,
        max_body=broadcast_email_service.MAX_BODY_CHARS,
    )


@admin.route("/epost/<int:broadcast_id>/rediger", methods=["POST"])
@admin_required
def broadcast_edit(broadcast_id):
    _flash_result(*broadcast_email_service.update_text(
        broadcast_id, request.form.get("subject"), request.form.get("body")
    ))
    return _to_detail(broadcast_id)


@admin.route("/epost/<int:broadcast_id>/test", methods=["POST"])
@admin_required
def broadcast_test(broadcast_id):
    _flash_result(*broadcast_email_service.send_test(
        broadcast_id, request.form.get("address"), current_user.id, request.url_root
    ))
    return _to_detail(broadcast_id)


@admin.route("/epost/<int:broadcast_id>/send", methods=["POST"])
@admin_required
def broadcast_send(broadcast_id):
    """Start the send, or carry on with a stopped one."""
    _flash_result(*broadcast_email_service.start(
        broadcast_id,
        current_user.id,
        request.url_root,
        typed_count=request.form.get("confirm_count", type=int),
    ))
    return _to_detail(broadcast_id)


@admin.route("/epost/<int:broadcast_id>/stopp", methods=["POST"])
@admin_required
def broadcast_stop(broadcast_id):
    _flash_result(*broadcast_email_service.request_stop(broadcast_id))
    return _to_detail(broadcast_id)


@admin.route("/epost/<int:broadcast_id>/avslutt", methods=["POST"])
@admin_required
def broadcast_close(broadcast_id):
    _flash_result(*broadcast_email_service.close(broadcast_id))
    return _to_detail(broadcast_id)


@admin.route("/epost/<int:broadcast_id>/status", methods=["GET"])
@admin_required
def broadcast_status(broadcast_id):
    status = broadcast_email_service.get_status(broadcast_id)
    if status is None:
        abort(404)
    return jsonify(status)
