from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "styles.css").read_text(encoding="utf-8")
        cls.nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
        cls.compose = (ROOT / "docker-compose.vps.yml").read_text(encoding="utf-8")

    def test_hebrew_rtl_and_landmarks(self):
        self.assertIn('<html lang="he" dir="rtl"', self.html)
        self.assertIn('<main id="main"', self.html)
        self.assertIn('class="skip-link"', self.html)
        self.assertIn('href="accessibility.html"', self.html)

    def test_live_data_disclosure_and_read_only_copy(self):
        self.assertIn("נתונים חיים מהטלפון המחובר", self.js)
        self.assertIn("קריאה בלבד", self.html)
        for mock_value in ("050-123-4587", "חברות מהכיתה", "חוג ריקוד", "אוהבת אותך", "נועה מהכיתה", "נתונים מדומים"):
            self.assertNotIn(mock_value, self.html + self.js)

    def test_required_live_surfaces_exist(self):
        for text in ("נתונים חיים", "מה דורש בדיקה", "מספרים לא מזוהים", "תמונות קבוצות", "מה חשוב עכשיו"):
            self.assertIn(text, self.html)
        for hook in ('id="alerts-feed"', 'id="groups-list"', 'id="contacts-list"', 'data-event-count="image"'):
            self.assertIn(hook, self.html)
        self.assertIn("group.snapshot", self.js)
        self.assertIn("imageBase64", self.js)
        self.assertIn("שולח שטרם זוהה", self.js)
        self.assertIn("התקבלה הודעה ממספר טלפון לא מזוהה:", self.js)
        self.assertIn("אין חריגים חדשים", self.js)
        self.assertNotIn("chat_jid ||", self.js)

    def test_settings_has_contact_mailto(self):
        self.assertIn('id="contact-link" href="https://mail.google.com/mail/?view=cm&amp;fs=1&amp;to=eldadi9@gmail.com&amp;', self.html)
        self.assertIn('id="contact-mailto" href="mailto:eldadi9@gmail.com?', self.html)

    def test_no_whatsapp_write_actions(self):
        combined = (self.html + self.js).lower()
        for forbidden in ("sendmessage", "/api/send", "/api/react", "/api/typing"):
            self.assertNotIn(forbidden, combined)

    def test_logical_css_is_used(self):
        self.assertIn("margin-inline", self.css)
        self.assertIn("inset-inline", self.css)

    def test_authenticated_read_only_api_adapter_exists(self):
        self.assertIn('id="api-connect-form"', self.html)
        self.assertIn('id="parent-username"', self.html)
        self.assertIn('id="parent-password"', self.html)
        self.assertIn('id="toggle-password"', self.html)
        self.assertIn('id="login-error"', self.html)
        self.assertIn('value="eldad"', self.html)
        self.assertNotIn('id="parent-totp"', self.html)
        self.assertIn('id="auth-gate"', self.html)
        self.assertIn("/api/watchup/dashboard", self.js)
        self.assertIn("data.connection", self.js)
        self.assertIn("/api/watchup/session", self.js)
        self.assertIn("/api/watchup/family", self.js)
        self.assertIn("restoreSession();", self.js)
        self.assertIn("if (!response.ok) throw new Error('logout failed')", self.js)
        self.assertIn("X-Forwarded-For $remote_addr", self.nginx)
        self.assertIn("X-WatchUp-CSRF", self.js)
        self.assertNotIn("const totp", self.js)
        self.assertIn("passwordInput.type = reveal ? 'text' : 'password'", self.js)
        self.assertIn("שם המשתמש או הסיסמה אינם נכונים", self.js)
        self.assertIn("מהו קוד אימות בן 6 ספרות?", self.html)
        self.assertIn("support.google.com/accounts/answer/1066447", self.html)
        self.assertIn("support.microsoft.com/en-us/authenticator", self.html)
        self.assertIn("credentials: 'same-origin'", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertNotIn("setDemoState", self.js)
        self.assertIn("location /api/", self.nginx)
        self.assertIn("set $watchup_upstream watchup-api:8769;", self.nginx)
        self.assertIn("proxy_pass http://$watchup_upstream;", self.nginx)
        self.assertIn("watchup-internal", self.compose)

    def test_owner_brand_assets_are_used(self):
        self.assertIn('assets/watchup-child-hero.png', self.html)
        self.assertIn('assets/watchup-eye-icon-owner.jpg', self.html)
        self.assertIn('class="watchup-hero"', self.html)

    def test_dashboard_summary_uses_illustrated_feature_artwork(self):
        summary = self.html.split('<section class="summary-strip"', 1)[1].split("</section>", 1)[0]
        for name in ("messages", "groups", "connection", "photos"):
            self.assertIn(f'class="summary-artwork {name}"', summary)
            asset = ROOT / "assets" / f"feature-{name}.jpg"
            self.assertTrue(asset.exists())
            self.assertGreater(asset.stat().st_size, 10000)
        self.assertEqual(summary.count('class="summary-artwork '), 4)
        self.assertIn(".summary-artwork img", self.css)
        self.assertNotIn("<svg", summary)
        for glyph in (">!</span>", ">#</span>", ">✓</span>", ">◉</span>"):
            self.assertNotIn(glyph, summary)

    def test_app_uses_one_complete_illustrated_icon_family(self):
        names = ("home", "messages", "groups", "connection", "photos", "settings", "privacy", "contact", "unresolved")
        for name in names:
            asset = ROOT / "assets" / f"feature-{name}.jpg"
            self.assertTrue(asset.exists())
            self.assertGreater(asset.stat().st_size, 10000)
        self.assertIn('class="topbar-artwork"', self.html)
        self.assertIn('class="privacy-artwork"', self.html)
        self.assertIn('class="people-artwork"', self.html)
        self.assertIn('class="setting-artwork"', self.html)
        self.assertIn("createArtwork(view.art, 'feed-artwork')", self.js)
        self.assertIn("createArtwork(view.art, 'timeline-artwork')", self.js)
        self.assertNotIn("passwordToggle.querySelector('span')", self.js)
        self.assertNotIn(">🔔<", self.html)

    def test_israeli_phone_and_date_formats(self):
        self.assertIn("function formatDateDDMMYYYY(date)", self.js)
        self.assertIn("function israeliMobileDigits(value)", self.js)
        self.assertIn("מספר לא בפורמט ישראלי", self.js)
        self.assertIn("רענון מסך:", self.js)
        self.assertIn('id="child-connection-label"', self.html)

    def test_audit_log_surface_exists(self):
        self.assertIn('id="audit-log"', self.html)
        self.assertIn('יומן צפייה', self.html)
        self.assertIn("/api/watchup/audit", self.js)
        self.assertIn("loadAuditLog", self.js)

    def test_protection_rules_alert_only_on_strangers_keywords_and_disconnect(self):
        self.assertIn("function isException(event, words)", self.js)
        self.assertIn("function matchedWord(event, words)", self.js)
        self.assertIn("if (!isRecognizedSender(event)) return true;", self.js)
        self.assertIn("return Boolean(matchedWord(event, words));", self.js)
        self.assertIn("if (event.type === 'group.snapshot' || event.account?.is_from_me || event.type === 'connection.status') return false;", self.js)
        self.assertIn("status === 'disconnected' || status === 'relink_required'", self.js)
        self.assertIn("event.type === 'connection.status') return false", self.js)
        self.assertIn("הניטור נעצר", self.js)
        self.assertIn("connection-down", self.js)
        self.assertIn("body.connection-down .connection-pill i{background:#ba1a1a", self.css)
        self.assertIn("category: 'keyword'", self.js)
        self.assertIn("`מילת מעקב: ${word}`", self.js)
        self.assertIn("severity: 'קריטי', tone: 'critical'", self.js)
        self.assertIn("function matchText(value)", self.js)
        self.assertIn("function messageText(event)", self.js)
        self.assertIn("id=\"group-dashboard\"", self.html)
        self.assertIn("הכי הרבה הודעות היום", self.js)
        self.assertIn("visibilitychange", self.js)
        self.assertIn("watchup-alerts", self.js)
        self.assertIn("dashboardRequest", self.js)
        self.assertIn(".severity.critical{background:#ffdad6;color:#93000a}", self.css)
        self.assertIn("image: 'תמונה', video: 'סרטון', audio: 'הודעה קולית', document: 'מסמך'", self.js)
        self.assertIn("function messageBody(event)", self.js)
        self.assertIn("סטטוס וואטסאפ", self.js)
        self.assertIn("body.className = 'feed-message'", self.js)
        self.assertIn("event.payload?.isRecognized === true", self.js)
        self.assertIn("קבוצה שטרם סונכרנה", self.js)

    def test_owner_feedback_repairs_are_present(self):
        self.assertIn("data.groups", self.js)
        self.assertIn("return event.account?.is_recognized === true || event.payload?.isRecognized === true;", self.js)
        self.assertNotIn("return Boolean(safeText(event.account?.display_name))", self.js)
        self.assertIn("/api/watchup/tracking-words", self.js)
        self.assertNotIn("localStorage.getItem('watchup-view')", self.js)
        self.assertIn("localStorage.setItem('watchup-view', view)", self.js)
        self.assertIn('id="enable-alerts"', self.html)
        self.assertIn('id="mobile-menu-button"', self.html)
        self.assertIn('id="mobile-nav"', self.html)
        self.assertNotIn("history.replaceState(null, '', '#home')", self.js)
        self.assertIn("showView('home', true)", self.js)
        self.assertIn("הרענון נכשל, הנתונים הקודמים נשארו על המסך", self.js)
        self.assertIn('grid-template-areas:"menu brand alerts"', self.css)
        self.assertNotIn("יולי", self.html + self.js)
        self.assertIn("body.auth-pending .auth-gate", self.html)
        self.assertIn("display: grid !important", self.html)
        self.assertIn("gap:12px;background:transparent;border:0;box-shadow:none;overflow:visible", self.css)
        self.assertIn(".audit-log small{direction:ltr", self.css)
        self.assertIn("function connectionHealth(connectionEvent)", self.js)
        self.assertIn("connectionHealth(connectionEvent).label", self.js)
        self.assertIn("health.verified", self.js)
        self.assertIn("@media(min-width:721px){", self.css)
        self.assertIn(".watchup-hero{width:min(100%,1060px);height:300px;min-height:300px;max-height:300px;aspect-ratio:auto;margin-inline:auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:minmax(0,1fr);gap:0;align-items:stretch;overflow:hidden;border-radius:28px;background:linear-gradient(165deg,#0b6b53 0%,#08775a 48%,#056047 100%)}", self.css)
        self.assertIn(".watchup-hero{position:relative;width:100%;height:auto;min-height:300px;max-height:none;aspect-ratio:auto;margin-inline:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0;align-items:stretch;overflow:hidden;border-radius:22px;background:linear-gradient(165deg,#0b6b53 0%,#08775a 48%,#056047 100%)}", self.css)
        self.assertNotIn("aspect-ratio:1060/300", self.css)
        self.assertIn(".watchup-hero>img{display:block;order:0;width:100%;height:100%;min-width:0;min-height:0;max-height:100%;object-fit:contain;object-position:center center;background:radial-gradient(circle at 50% 42%,#eef3f6 0%,#d7e0e6 70%,#cfd8df 100%)}", self.css)
        self.assertIn("row.setAttribute('aria-expanded', String(open));", self.js)
        self.assertIn("anchor.after(panel);", self.js)
        self.assertIn("let selectedGroupJid = '';", self.js)
        self.assertIn("object-fit:contain;object-position:center center", self.css)
        self.assertNotIn("height:440px", self.css)
        self.assertIn(".summary-strip button{background:#e8eff5", self.css)
        self.assertIn(".filter-bar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", self.css)

    def test_alert_tabs_word_forms_hours_and_retention_controls(self):
        for hook in ('data-filter="today"', 'data-filter="joined"', 'data-filter="hours"', 'id="schedule-form"', 'id="open-pairing"', 'id="reset-today"', 'id="group-sort"'):
            self.assertIn(hook, self.html)
        self.assertIn("function wordForms(word)", self.js)
        self.assertIn("character === 'ו'", self.js)
        self.assertIn("['stranger', 'keyword']", self.js)
        self.assertIn("watchup-seen-alerts", self.js)
        self.assertIn("Asia/Jerusalem", self.js)
        self.assertIn("/api/watchup/today", self.js)
        self.assertIn("/api/watchup/pairing", self.js)
        node = shutil.which("node")
        if not node:
            return
        script = r"""
const fs = require('fs');
const src = fs.readFileSync('app.js', 'utf8');
const start = src.indexOf('function safeText');
const end = src.indexOf('function matchedWord');
eval(src.slice(start, end));
const stuck = wordForms('\u05e1\u05ea\u05d5\u05dd');
if (!stuck.has('\u05e1\u05ea\u05d5\u05dd') || !stuck.has('\u05e1\u05ea\u05d5\u05de\u05d4') || !stuck.has('\u05e0\u05e1\u05ea\u05dd') || stuck.has('\u05e1\u05ea\u05dd')) process.exit(1);
if (wordForms('\u05e1\u05ea\u05dd').has('\u05e1\u05ea\u05d5\u05dd')) process.exit(2);
"""
        completed = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


class ProjectDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "project-dashboard.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "project-dashboard.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "project-dashboard.css").read_text(encoding="utf-8")
        cls.nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")

    def test_project_dashboard_is_read_only_sheet_backed_and_shows_guide(self):
        self.assertIn('<html lang="he" dir="rtl"', self.html)
        self.assertIn('guide-section', self.html)
        self.assertIn('מפת עבודה', self.html)
        self.assertIn('class="guide-figure guide-figure-centered"', self.html)
        self.assertIn('assets/project-work-map.png', self.html)
        self.assertIn('guide-section-centered', self.html)
        self.assertIn('class="guide-drawer"', self.html)
        self.assertIn('max-inline-size:1680px', self.css)
        self.assertTrue((ROOT / "assets" / "project-work-map.png").exists())
        self.assertIn('data-brand-direction="resonance-field"', self.html)
        self.assertIn('responseHandler', self.js)
        self.assertIn("loadSheet('Backlog'", self.js)
        self.assertNotIn('/api/send', self.html + self.js)
        self.assertIn("script-src 'self' https://docs.google.com;", self.nginx)
        self.assertIn("img-src 'self' data:;", self.nginx)

    def test_project_dashboard_captures_one_short_idea_through_n8n(self):
        self.assertIn('id="idea-form"', self.html)
        self.assertIn('name="idea"', self.html)
        self.assertIn('minlength="3"', self.html)
        self.assertIn('action="/idea-capture"', self.html)
        self.assertIn("fetch('/idea-capture'", self.js)
        self.assertIn('result.Idea !== submittedIdea', self.js)
        self.assertIn('location = /idea-capture', self.nginx)
        self.assertIn('watchup-idea-submit-20261008', self.nginx)

if __name__ == "__main__":
    unittest.main()
