from pathlib import Path
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
        self.assertIn('<html lang="he" dir="rtl">', self.html)
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
        self.assertIn("http://watchup-api:8769/", self.nginx)
        self.assertIn("watchup-internal", self.compose)

    def test_owner_brand_assets_are_used(self):
        self.assertIn('assets/watchup-child-hero.jpg', self.html)
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
        self.assertIn("if (event.type === 'group.snapshot' || event.account?.is_from_me) return false;", self.js)
        self.assertIn("status === 'disconnected' || status === 'relink_required'", self.js)
        self.assertIn("category: 'keyword'", self.js)
        self.assertIn("`מילת מעקב: ${word}`", self.js)
        self.assertIn("image: 'תמונה', video: 'סרטון', audio: 'הודעה קולית', document: 'מסמך'", self.js)
        self.assertIn("return event.account?.chat_type === 'group' ? 'קבוצה שטרם סונכרנה' : 'שיחה פרטית';", self.js)

    def test_owner_feedback_repairs_are_present(self):
        self.assertIn("data.groups", self.js)
        self.assertIn("return event.account?.is_recognized === true;", self.js)
        self.assertNotIn("return Boolean(safeText(event.account?.display_name))", self.js)
        self.assertIn("/api/watchup/tracking-words", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertIn('id="enable-alerts"', self.html)
        self.assertIn('id="mobile-menu-button"', self.html)
        self.assertIn('id="mobile-nav"', self.html)
        self.assertIn("showView('home', false)", self.js)
        self.assertIn(".audit-log small{direction:ltr", self.css)
        self.assertIn("function connectionHealth(connectionEvent)", self.js)
        self.assertIn("connectionHealth(connectionEvent).label", self.js)
        self.assertIn("connectionHealth(connectionEvent).verified", self.js)
        self.assertIn(".watchup-hero{grid-template-columns:repeat(2,minmax(0,1fr))}", self.css)
        self.assertIn(".summary-strip button{background:#e8eff5", self.css)
        self.assertIn(".filter-bar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))", self.css)


if __name__ == "__main__":
    unittest.main()
