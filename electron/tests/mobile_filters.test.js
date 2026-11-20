const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const MOBILE_HTML_PATH = path.resolve(__dirname, "..", "..", "..", "sscp", "public", "mobile", "index.html");

function extractScriptFunctions() {
    const html = fs.readFileSync(MOBILE_HTML_PATH, "utf-8");
    const fnStart = html.indexOf("function addDaysLocalStr(");
    assert.ok(fnStart !== -1, "addDaysLocalStr helper not found in index.html");
    const filterStart = html.indexOf("function filterUpcomingAppointments(");
    assert.ok(filterStart !== -1, "filterUpcomingAppointments helper not found in index.html");

    // Extract small standalone slice around addDaysLocalStr/toLocalDateStr + filterUpcomingAppointments
    const toLocalEnd = html.indexOf("\n        function toLocalTimeStr(", fnStart);
    const filterEnd = html.indexOf("\n        window.__sscpHandleAndroidBack", filterStart);
    const code = html.slice(fnStart, toLocalEnd) + "\n" + html.slice(filterStart, filterEnd);

    const sandbox = { Date, Array, String, Math, localStorage: { getItem: () => "" } };
    vm.runInNewContext(code, sandbox);
    return sandbox;
}

describe("Mobile Próximas Citas filterUpcomingAppointments & Clinical QR", () => {
    it("filters strictly future dates for tomorrow/week/15days/all (excluding today and waiting room)", () => {
        const ctx = extractScriptFunctions();
        const now = new Date();
        const addDays = (d) => ctx.addDaysLocalStr(now, d);

        const appts = [
            { id: 1, date: addDays(-2), patient_name: "Pasada", status: "Pendiente" },
            { id: 2, date: addDays(0), patient_name: "Hoy Ana", status: "Pendiente", whatsapp_reminder_sent: false },
            { id: 3, date: addDays(1), patient_name: "Manana Luis", status: "Confirmada", whatsapp_reminder_sent: true },
            { id: 4, date: addDays(1), patient_name: "Manana Cancelada", status: "Cancelada" },
            { id: 5, date: addDays(5), patient_name: "Semana Rosa", status: "Pendiente", whatsapp_reminder_sent: false },
            { id: 6, date: addDays(12), patient_name: "Quince Carlos", status: "Confirmada", whatsapp_reminder_sent: false },
            { id: 7, date: addDays(25), patient_name: "Mes Eva", status: "Pendiente", whatsapp_reminder_sent: true },
            { id: 8, date: addDays(0), patient_name: "Hoy En Espera", status: "En Espera", queue_number: 1 },
        ];

        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "today" }).map((a) => a.id),
            [2, 8]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "tomorrow" }).map((a) => a.id),
            [3]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "this_week" }).map((a) => a.id),
            [3, 5]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "next_15_days" }).map((a) => a.id),
            [3, 5, 6]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "all" }).map((a) => a.id),
            [3, 5, 6, 7]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "all", status: "confirmed" }).map((a) => a.id),
            [3, 6]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "all", status: "unconfirmed" }).map((a) => a.id),
            [5, 7]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "all", status: "unsent_wa" }).map((a) => a.id),
            [5, 6]
        );
        assert.deepEqual(
            ctx.filterUpcomingAppointments(appts, { range: "all", search: "quince" }).map((a) => a.id),
            [6]
        );
    });

    it("has SupabaseBridge 409 guard, separate confirmed section, due_reminders, and copy button", () => {
        const html = fs.readFileSync(MOBILE_HTML_PATH, "utf-8");
        const supaBlockStart = html.indexOf("if (cleanUrl === '/api/mobile/appointments/upcoming'");
        assert.ok(supaBlockStart !== -1);
        const supaBlock = html.slice(supaBlockStart, supaBlockStart + 3500);
        assert.ok(supaBlock.includes("params.get('range')"), "SupabaseBridge must read range query param");
        assert.ok(supaBlock.includes("filterUpcomingAppointments("), "SupabaseBridge must apply filterUpcomingAppointments");
        assert.ok(html.includes('id="chip-upcoming-today"'), "UI chip Hoy must exist");
        assert.ok(html.includes('id="upcoming-section-confirmed"'), "Confirmed appointments must move to separate section");
        assert.ok(html.includes('id="secretary-due-reminders-panel"'), "Proactive Secretary reminders panel must exist");
        assert.ok(html.includes("copyReminderText("), "1-click copy reminder helper must exist");
        assert.ok(html.includes("detectedPatientId"), "QR scanner must distinguish patient QRs");
        assert.ok(!html.includes("100.82.124.125"), "No hardcoded Tailscale IP should remain");
    });
});
