import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DeploymentArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cls.environment = (ROOT / ".env.example").read_text(encoding="utf-8")
        cls.deploy = (ROOT / "scripts" / "deploy_watchup_api.sh").read_text(encoding="utf-8")
        cls.backup = (ROOT / "scripts" / "backup_watchup.sh").read_text(encoding="utf-8")
        cls.restore = (ROOT / "scripts" / "restore_test_watchup.sh").read_text(encoding="utf-8")

    def test_api_binds_to_all_internal_interfaces_without_publishing_a_port(self):
        self.assertIn("WATCHUP_API_HOST=0.0.0.0", self.dockerfile)
        self.assertIn("WATCHUP_API_HOST=0.0.0.0", self.environment)
        self.assertIn("--network \"$WATCHUP_INTERNAL_NETWORK\"", self.deploy)
        self.assertNotIn("--publish", self.deploy)
        self.assertNotIn("EXPOSE", self.dockerfile)
        self.assertIn("--restart unless-stopped", self.deploy)

    def test_ca_is_mounted_read_only_for_verify_full(self):
        self.assertIn("WATCHUP_DB_HOST=watchup-postgres", self.environment)
        self.assertIn("WATCHUP_DB_SSLMODE=verify-full", self.environment)
        self.assertIn("WATCHUP_DB_SSLROOTCERT=/run/secrets/watchup_db_ca.crt", self.environment)
        self.assertIn("WATCHUP_DB_SSLROOTCERT_HOST", self.deploy)
        self.assertIn("dst=$WATCHUP_DB_SSLROOTCERT,readonly", self.deploy)

    def test_api_has_fixed_non_root_identity_for_secret_group_access(self):
        self.assertIn("groupadd --gid 2001 watchup", self.dockerfile)
        self.assertIn("useradd --uid 2001 --gid watchup", self.dockerfile)
        self.assertIn("USER watchup", self.dockerfile)

    def test_backup_and_restore_have_one_closed_case_statement(self):
        for script in (self.backup, self.restore):
            self.assertEqual(script.count("esac"), 1)

    def test_restore_requires_and_checks_the_expected_synthetic_event(self):
        self.assertIn("${2:?pass the expected synthetic event id}", self.restore)
        self.assertIn("WHERE event_id = :'expected_event_id'", self.restore)
        self.assertIn('test "$restored_count" = "1"', self.restore)
        self.assertIn("trap cleanup EXIT", self.restore)

    def test_backups_are_encrypted_without_persisting_plaintext(self):
        self.assertIn("WATCHUP_BACKUP_PASSPHRASE_FILE", self.backup)
        self.assertIn("--symmetric --cipher-algo AES256", self.backup)
        self.assertIn(".dump.gpg", self.backup)
        self.assertIn("rm -f \"$plain\"", self.backup)
        self.assertIn("--decrypt \"$backup\"", self.restore)


if __name__ == "__main__":
    unittest.main()
