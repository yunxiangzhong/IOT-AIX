import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = SERVICE_ROOT.parent
sys.path.insert(0, str(SERVICE_ROOT))


class DeploymentScriptTests(unittest.TestCase):
    def test_installer_pins_yolo26_and_exports_fp16_engine(self) -> None:
        installer = (MODEL_ROOT / "install.ps1").read_text(encoding="utf-8")
        setup = (MODEL_ROOT / "setup_yolo.py").read_text(encoding="utf-8")

        self.assertIn("ultralytics==8.4.96", installer)
        self.assertIn('weights\\YOLO26m', installer)
        self.assertIn("setup_yolo.py", installer)
        self.assertIn('format="engine"', setup)
        self.assertIn("quantize=16", setup)
        self.assertIn("imgsz=512", setup)
        self.assertIn("image_size=512", (SERVICE_ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertNotIn("SSDLite320", installer)

    def test_launcher_keeps_ultralytics_cache_under_model_root(self) -> None:
        launcher = (MODEL_ROOT / "run_service.ps1").read_text(encoding="utf-8")

        self.assertIn("YOLO_CONFIG_DIR", launcher)
        self.assertIn('cache\\ultralytics', launcher)

    def test_readme_documents_processed_frame_and_agpl_boundary(self) -> None:
        readme = (MODEL_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("YOLO26m", readme)
        self.assertIn("/v1/frame/processed.jpg", readme)
        self.assertIn("AGPL-3.0", readme)


if __name__ == "__main__":
    unittest.main()
