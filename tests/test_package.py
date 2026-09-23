from pathlib import Path
from zipfile import ZipFile

from tools.package import package


def test_source_package_includes_scoped_ca_but_excludes_secrets(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("Project", encoding="utf-8")
    ca = root / "config" / "ca"
    ca.mkdir(parents=True)
    (ca / "russian-trusted-root.pem").write_text("public certificate", encoding="utf-8")
    (ca / "private-key.pem").write_text("private key", encoding="utf-8")
    (root / ".env").write_text("LLM_API_KEY=secret", encoding="utf-8")
    reports = root / "reports"
    reports.mkdir()
    (reports / "holdout-quality.json").write_text("{}", encoding="utf-8")

    output = tmp_path / "source.zip"
    package(root, output)

    with ZipFile(output) as archive:
        assert "config/ca/russian-trusted-root.pem" in archive.namelist()
        assert "config/ca/private-key.pem" not in archive.namelist()
        assert ".env" not in archive.namelist()
        assert "reports/holdout-quality.json" not in archive.namelist()
