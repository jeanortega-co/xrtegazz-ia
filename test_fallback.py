import unittest

import xrtegazz


class FallbackResponseTests(unittest.TestCase):
    def test_removed_generic_helpers(self):
        self.assertFalse(hasattr(xrtegazz, 'generar_respuesta_informativa'))
        self.assertFalse(hasattr(xrtegazz, 'respuesta_es_refusal'))

    def test_core_ai_helpers_still_available(self):
        self.assertTrue(hasattr(xrtegazz, 'llamar_openrouter'))
        self.assertTrue(hasattr(xrtegazz, 'llamar_groq'))


if __name__ == '__main__':
    unittest.main()
