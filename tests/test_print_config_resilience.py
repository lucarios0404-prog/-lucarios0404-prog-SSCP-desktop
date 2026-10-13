import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

class TestPrintConfigResilience(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="sscp_test_print_"))
        os.environ["SSCP_DATA_DIR"] = str(self.test_dir)
        # Limpiar caché si existiera
        import app.services.print_config_service as pcs
        self.pcs = pcs

    def tearDown(self):
        if "SSCP_DATA_DIR" in os.environ:
            del os.environ["SSCP_DATA_DIR"]
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_creates_atomic_file_and_bak(self):
        custom = {
            "print_margin_top": 45.0,
            "print_margin_bottom": 35.0,
            "print_margin_left": 25.0,
            "print_margin_right": 18.0
        }
        res = self.pcs.save_print_config(custom)
        self.assertEqual(res["print_margin_top"], 45.0)

        main_file = self.pcs.get_print_config_path()
        self.assertTrue(main_file.exists())
        self.assertGreater(main_file.stat().st_size, 0)

        # Segundo guardado debe crear el .bak con la versión anterior
        update_cfg = {"print_margin_top": 50.0}
        self.pcs.save_print_config(update_cfg)

        bak_file = main_file.with_suffix(".json.bak")
        self.assertTrue(bak_file.exists())
        self.assertGreater(bak_file.stat().st_size, 0)

    def test_corrupted_main_file_recovers_from_bak(self):
        # 1. Guardar configuración inicial personalizada
        custom = {
            "print_margin_top": 42.0,
            "print_margin_left": 31.0
        }
        self.pcs.save_print_config(custom)
        # Guardar una actualización para asegurar que existe .bak
        self.pcs.save_print_config({"print_margin_right": 22.0})

        main_file = self.pcs.get_print_config_path()
        bak_file = main_file.with_suffix(".json.bak")
        self.assertTrue(bak_file.exists())

        # 2. Simular corrupción de archivo por corte de luz o apagado (archivo truncado o corrupto)
        with open(main_file, "w", encoding="utf-8") as f:
            f.write("{ CORRUPTED_JSON_DATA ...")

        # 3. get_print_config debe rescatar los datos del .bak sin perder márgenes
        recovered = self.pcs.get_print_config()
        self.assertEqual(recovered["print_margin_top"], 42.0)
        self.assertEqual(recovered["print_margin_left"], 31.0)

if __name__ == "__main__":
    unittest.main()
