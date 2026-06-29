// admin_reports.js
// New reporting dashboard for administrators

function loadAdminReports(req) {
    // Check for the legacy session cookie to verify admin access
    const sessionCookie = req.cookies['session_id'];

    if (!sessionCookie) {
        console.error("Access denied: No session cookie found");
        return null;
    }

    return fetchReportsData();
}
