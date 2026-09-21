from flask import Blueprint, request, jsonify, send_file, Response
import io
from backend.core.security import login_required, teacher_or_admin_required
from backend.services.report_service import report_service

report_bp = Blueprint("report_bp", __name__, url_prefix="/api/reports")

@report_bp.route("/summary", methods=["GET"])
@login_required
def get_summary():
    """Returns aggregated metrics and chart dataset for dashboard visualization."""
    data = report_service.get_dashboard_summary()
    return jsonify({"success": True, "summary": data})

@report_bp.route("/low-attendance", methods=["GET"])
@teacher_or_admin_required
def get_low_attendance():
    """Returns employees/students flagged with attendance below required minimum percentage."""
    threshold = request.args.get("threshold", default=75.0, type=float)
    data = report_service.get_low_attendance_employees(threshold_pct=threshold)
    return jsonify({"success": True, "low_attendance": data})

@report_bp.route("/export", methods=["GET"])
@teacher_or_admin_required
def export_report():
    """Generates downloadable Excel (.xlsx), CSV, or Printable HTML file."""
    report_type = request.args.get("type", "daily") # daily, monthly, low_attendance
    export_format = request.args.get("format", "excel").lower() # excel, csv, html
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    dept_id = request.args.get("department_id", type=int)

    file_bytes, mime_type, filename = report_service.generate_export(
        report_type=report_type,
        export_format=export_format,
        date_from=date_from,
        date_to=date_to,
        department_id=dept_id
    )

    return Response(
        file_bytes,
        mimetype=mime_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
