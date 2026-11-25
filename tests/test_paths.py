from pathlib import Path

from src.config import OUTPUTS_DIR
from src.security.paths import safe_output_path, sanitize_filename


def test_sanitize_basename():
    assert sanitize_filename("../../etc/passwd") == "passwd.png"
    assert sanitize_filename("..\\..\\secret.png") == "secret.png"
    assert ".." not in sanitize_filename("..\\..\\x\\secret.png")
    assert sanitize_filename("informe chart.png").endswith(".png")


def test_safe_output_stays_inside():
    p = safe_output_path("../../evil.png", base_dir=OUTPUTS_DIR)
    assert p.resolve().is_relative_to(OUTPUTS_DIR.resolve()) or str(p.resolve()).startswith(
        str(OUTPUTS_DIR.resolve())
    )
    assert p.name.endswith(".png")
