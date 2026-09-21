import io
import datetime
import pandas as pd
from backend.models.database import db
from backend.services.attendance_service import attendance_service

class ReportService:
    """Analytics, Statistics, and Multi-Format Report Exporter (Excel, CSV, HTML)."""

    @staticmethod
    def get_dashboard_summary() -> dict:
        """Computes executive metrics for dashboard display."""
        now = datetime.datetime.now()
        date_dmy = now.strftime("%d-%m-%Y")
        date_iso = now.strftime("%Y-%m-%d")

        rule = attendance_service.get_active_rule()
        min_pct = rule.get("min_attendance_percent", 75.0)

        with db.get_connection() as conn:
            cur = conn.cursor()

            # Total active staff / students
            cur.execute("SELECT COUNT(*) FROM employees WHERE status = 'active'")
            total_employees = cur.fetchone()[0] or 0

            # Today's attendance records
            cur.execute("""
                SELECT COUNT(DISTINCT student_id) FROM attendance
                WHERE (date = ? OR date = ?) AND status = 'Present'
            """, (date_dmy, date_iso))
            present_today = cur.fetchone()[0] or 0

            # Late arrivals today
            cur.execute("""
                SELECT COUNT(*) FROM attendance
                WHERE (date = ? OR date = ?) AND shift_status = 'Late'
            """, (date_dmy, date_iso))
            late_today = cur.fetchone()[0] or 0

            # Today's attendance percentage
            attendance_pct = round((present_today / total_employees * 100), 1) if total_employees > 0 else 0.0

            # Past 7 days attendance trend
            trend_dates = []
            trend_present = []
            trend_late = []

            for i in range(6, -1, -1):
                day = now - datetime.timedelta(days=i)
                d_dmy = day.strftime("%d-%m-%Y")
                d_iso = day.strftime("%Y-%m-%d")
                label = day.strftime("%a %d")

                cur.execute("""
                    SELECT COUNT(DISTINCT student_id),
                           SUM(CASE WHEN shift_status = 'Late' THEN 1 ELSE 0 END)
                    FROM attendance
                    WHERE (date = ? OR date = ?) AND status = 'Present'
                """, (d_dmy, d_iso))
                row = cur.fetchone()
                p_cnt = row[0] or 0
                l_cnt = row[1] or 0

                trend_dates.append(label)
                trend_present.append(p_cnt)
                trend_late.append(l_cnt)

            # Department breakdown
            cur.execute("""
                SELECT COALESCE(d.name, 'General') as dept_name, COUNT(a.id) as att_count
                FROM attendance a
                JOIN employees e ON a.student_id = e.employee_code
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE a.date = ? OR a.date = ?
                GROUP BY d.name
            """, (date_dmy, date_iso))
            dept_breakdown = [dict(r) for r in cur.fetchall()]

            # Low attendance warning count
            low_att_list = ReportService.get_low_attendance_employees(threshold_pct=min_pct)
            low_attendance_count = len(low_att_list)

        return {
            "total_employees": total_employees,
            "present_today": present_today,
            "late_today": late_today,
            "attendance_percentage": attendance_pct,
            "low_attendance_count": low_attendance_count,
            "min_required_percentage": min_pct,
            "trend": {
                "labels": trend_dates,
                "present": trend_present,
                "late": trend_late
            },
            "department_breakdown": dept_breakdown
        }

    @staticmethod
    def get_low_attendance_employees(threshold_pct: float = 75.0) -> list:
        """Identifies enrolled individuals whose attendance is below policy threshold."""
        with db.get_connection() as conn:
            cur = conn.cursor()

            # Find distinct attendance dates in system (total class/work sessions)
            cur.execute("SELECT COUNT(DISTINCT date) FROM attendance")
            total_sessions = cur.fetchone()[0] or 1

            cur.execute("""
                SELECT e.id, e.employee_code, e.full_name, e.email, e.phone,
                       d.name as department_name, e.designation_class,
                       COUNT(DISTINCT a.date) as attended_sessions
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                LEFT JOIN attendance a ON e.employee_code = a.student_id AND a.status = 'Present'
                WHERE e.status = 'active'
                GROUP BY e.id
            """)
            rows = cur.fetchall()

            low_list = []
            for r in rows:
                att_sessions = r["attended_sessions"]
                pct = round((att_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0.0
                if pct < threshold_pct:
                    low_list.append({
                        "employee_id": r["id"],
                        "employee_code": r["employee_code"],
                        "full_name": r["full_name"],
                        "email": r["email"],
                        "department": r["department_name"] or "General",
                        "designation": r["designation_class"],
                        "attended_sessions": att_sessions,
                        "total_sessions": total_sessions,
                        "percentage": pct
                    })
            return sorted(low_list, key=lambda x: x["percentage"])

    @staticmethod
    def generate_export(report_type: str = "daily", export_format: str = "excel", 
                        date_from: str = None, date_to: str = None, department_id: int = None) -> tuple[bytes, str, str]:
        """Generates downloadable Excel (.xlsx), CSV, or Printable HTML file buffer.
        Returns: (file_bytes, mime_type, filename)
        """
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")

        if report_type == "low_attendance":
            data = ReportService.get_low_attendance_employees()
            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["employee_code", "full_name", "department", "attended_sessions", "total_sessions", "percentage"])
            df.rename(columns={
                "employee_code": "Employee/Student ID",
                "full_name": "Full Name",
                "department": "Department",
                "designation": "Role / Designation",
                "attended_sessions": "Sessions Attended",
                "total_sessions": "Total Sessions",
                "percentage": "Attendance %"
            }, inplace=True)
            filename_base = f"low_attendance_report_{timestamp}"

        else:
            # Query standard attendance records
            records_res = attendance_service.get_attendance_history(
                date_from=date_from,
                date_to=date_to,
                department_id=department_id,
                limit=10000
            )
            records = records_res["records"]
            if not records:
                df = pd.DataFrame(columns=["Date", "Student ID", "Name", "Department", "Check-In", "Check-Out", "Duration (Mins)", "Status", "Shift Status", "Subject"])
            else:
                formatted_records = []
                for r in records:
                    formatted_records.append({
                        "Date": r.get("date"),
                        "Student ID": r.get("student_id"),
                        "Name": r.get("name"),
                        "Department": r.get("department_name") or "General",
                        "Check-In": r.get("check_in_time") or r.get("time"),
                        "Check-Out": r.get("check_out_time") or "N/A",
                        "Duration (Mins)": r.get("duration_minutes", 0),
                        "Status": r.get("status"),
                        "Shift Status": r.get("shift_status", "On-Time"),
                        "Subject": r.get("subject", "General")
                    })
                df = pd.DataFrame(formatted_records)
            filename_base = f"attendance_{report_type}_{timestamp}"

        # Export according to chosen format
        if export_format == "csv":
            csv_str = df.to_csv(index=False)
            return csv_str.encode("utf-8"), "text/csv", f"{filename_base}.csv"

        elif export_format == "html":
            html_table = df.to_html(classes="report-table", index=False)
            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Attendance Report - {timestamp}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; color: #1e293b; }}
  h1 {{ color: #0f172a; margin-bottom: 5px; }}
  .meta {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
  .report-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
  .report-table th, .report-table td {{ border: 1px solid #cbd5e1; padding: 10px 14px; text-align: left; font-size: 14px; }}
  .report-table th {{ background-color: #f1f5f9; font-weight: 600; }}
  .report-table tr:nth-child(even) {{ background-color: #f8fafc; }}
  @media print {{
    body {{ margin: 10px; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
  <div class="no-print" style="margin-bottom: 20px;">
    <button onclick="window.print()" style="padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Print Report / Save as PDF</button>
  </div>
  <h1>Enterprise Attendance Report</h1>
  <div class="meta">Generated on: {now.strftime('%Y-%m-%d %I:%M:%S %p')} | Type: {report_type.upper()}</div>
  {html_table}
</body>
</html>"""
            return html_content.encode("utf-8"), "text/html", f"{filename_base}.html"

        else: # Default Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name="Attendance Data", index=False)
            excel_bytes = output.getvalue()
            return excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{filename_base}.xlsx"

report_service = ReportService()
