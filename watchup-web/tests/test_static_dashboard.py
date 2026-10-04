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

    def test_synthetic_disclosure_and_read_only_copy(self):
        self.assertIn("כל הנתונים במסך זה מדומים", self.html)
        self.assertIn("קריאה בלבד", self.html)

    def test_required_poc_surfaces_exist(self):
        for text in ("מצב הדגמה", "מילים וביטויים במעקב", "איש קשר חדש", "קבוצה חדשה", "מספר לא מזוהה", "קבוצות ואנשי קשר", "פרטי הקבוצה"):
            self.assertIn(text, self.html)

    def test_no_whatsapp_write_actions(self):
        combined = (self.html + self.js).lower()
        for forbidden in ("sendmessage", "/api/send", "/api/react", "/api/typing"):
            self.assertNotIn(forbidden, combined)

    def test_logical_css_is_used(self):
        self.assertIn("margin-inline", self.css)
        self.assertIn("inset-inline", self.css)

    def test_authenticated_read_only_api_adapter_exists(self):
        self.assertIn('id="api-connect-form"', self.html)
        self.assertIn("/api/watchup/dashboard", self.js)
        self.assertIn("sessionStorage", self.js)
        self.assertIn("location /api/", self.nginx)
        self.assertIn("http://watchup-api:8769/", self.nginx)
        self.assertIn("watchup-internal", self.compose)

    def test_owner_brand_assets_are_used(self):
        self.assertIn('assets/watchup-child-hero.jpg', self.html)
        self.assertIn('assets/watchup-eye-icon-owner.jpg', self.html)
        self.assertIn('class="watchup-hero"', self.html)


if __name__ == "__main__":
    unittest.main()
