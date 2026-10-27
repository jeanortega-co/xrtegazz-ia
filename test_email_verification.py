import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from werkzeug.security import generate_password_hash

import xrtegazz


class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tables = {
            'usuarios': [],
            'historial_chat': [],
            'sesiones_chat': [],
            'retroalimentacion': [],
        }
        self.read_patch = patch.object(
            xrtegazz,
            '_local_leer',
            side_effect=lambda table: self.tables.setdefault(table, []),
        )
        self.write_patch = patch.object(
            xrtegazz,
            '_local_guardar',
            side_effect=lambda table, rows: self.tables.__setitem__(table, rows),
        )
        self.read_patch.start()
        self.write_patch.start()
        self.addCleanup(self.read_patch.stop)
        self.addCleanup(self.write_patch.stop)
        self.client = xrtegazz.app.test_client()

    def patch_email_sender(self, codigo='123456'):
        def enviar(registro):
            ahora = datetime.now(timezone.utc)
            xrtegazz.actualizar_usuario_auth(registro['username'], {
                'email_code_hash': xrtegazz.hash_codigo_verificacion(registro['username'], codigo),
                'email_code_expires': (ahora + timedelta(minutes=10)).isoformat(),
                'email_code_sent_at': ahora.isoformat(),
                'email_code_attempts': 0,
            })
            return {'ok': True, 'email': 'u***@example.com'}

        return patch.object(xrtegazz, 'enviar_codigo_verificacion', side_effect=enviar)

    def patch_reset_email_sender(self, codigo='654321'):
        def enviar(registro):
            ahora = datetime.now(timezone.utc)
            xrtegazz.actualizar_usuario_auth(registro['username'], {
                'password_reset_code_hash': xrtegazz.hash_codigo_verificacion(registro['username'], codigo),
                'password_reset_code_expires': (ahora + timedelta(minutes=10)).isoformat(),
                'password_reset_code_sent_at': ahora.isoformat(),
                'password_reset_code_attempts': 0,
            })
            return {'ok': True, 'email': 'u***@example.com'}

        return patch.object(xrtegazz, 'enviar_codigo_recuperacion', side_effect=enviar)

    def add_verified_user(self, username='ana', email='ana@example.com', password='clave-segura'):
        self.tables['usuarios'].append({
            'id': len(self.tables['usuarios']) + 1,
            'username': username,
            'email': email,
            'email_verified': True,
            'password_hash': generate_password_hash(password),
            'nombre': 'Ana',
        })

    def test_registration_requires_email_verification_before_login(self):
        with self.patch_email_sender():
            response = self.client.post('/registrar', json={
                'usuario': 'ana',
                'password': 'clave-segura',
                'nombre': 'Ana',
                'email': 'ana@example.com',
            })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['requiere_verificacion'])
        with self.patch_email_sender():
            login = self.client.post('/login', json={
                'usuario': 'ana',
                'password': 'clave-segura',
            })
        self.assertTrue(login.get_json()['requiere_verificacion'])
        with self.client.session_transaction() as session:
            self.assertNotIn('usuario', session)

        verification = self.client.post('/verificar-correo', json={'codigo': '123456'})
        self.assertEqual(verification.status_code, 200)
        self.assertEqual(verification.get_json()['usuario'], 'ana')
        self.assertTrue(self.tables['usuarios'][0]['email_verified'])

    def test_existing_account_must_add_and_verify_email(self):
        self.tables['usuarios'].append({
            'id': 1,
            'username': 'legado',
            'password_hash': generate_password_hash('clave'),
            'rol': 'invitado',
            'nombre': 'Cuenta antigua',
        })
        with self.patch_email_sender():
            response = self.client.post('/login', json={
                'usuario': 'legado',
                'password': 'clave',
            })
        self.assertTrue(response.get_json()['requiere_email'])

        with self.patch_email_sender():
            response = self.client.post('/login', json={
                'usuario': 'legado',
                'password': 'clave',
                'email': 'legado@example.com',
            })
        self.assertTrue(response.get_json()['requiere_verificacion'])
        self.assertEqual(self.tables['usuarios'][0]['email'], 'legado@example.com')

        response = self.client.post('/verificar-correo', json={'codigo': '123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['usuario'], 'legado')

    def test_invalid_codes_are_counted_and_email_is_not_marked_verified(self):
        with self.patch_email_sender():
            self.client.post('/registrar', json={
                'usuario': 'ana',
                'password': 'clave-segura',
                'nombre': 'Ana',
                'email': 'ana@example.com',
            })

        response = self.client.post('/verificar-correo', json={'codigo': '000000'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.tables['usuarios'][0]['email_code_attempts'], 1)
        self.assertFalse(self.tables['usuarios'][0]['email_verified'])

    def test_registration_rejects_invalid_or_duplicate_email(self):
        invalid = self.client.post('/registrar', json={
            'usuario': 'ana',
            'password': 'clave',
            'nombre': 'Ana',
            'email': 'not-an-email',
        })
        self.assertEqual(invalid.status_code, 400)

        self.tables['usuarios'].append({
            'id': 1,
            'username': 'otra',
            'email': 'ana@example.com',
        })
        duplicate = self.client.post('/registrar', json={
            'usuario': 'ana',
            'password': 'clave',
            'nombre': 'Ana',
            'email': 'ANA@example.com',
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_verification_code_is_six_digits(self):
        with self.patch_email_sender():
            self.client.post('/registrar', json={
                'usuario': 'ana',
                'password': 'clave-segura',
                'nombre': 'Ana',
                'email': 'ana@example.com',
            })
        response = self.client.post('/verificar-correo', json={'codigo': '12345'})
        self.assertEqual(response.status_code, 400)
        self.assertRegex(response.get_json()['error'], re.compile('seis dígitos', re.IGNORECASE))

    def test_logout_clears_the_authenticated_session(self):
        with self.client.session_transaction() as session:
            session['usuario'] = 'ana'
            session['nombre_completo'] = 'Ana'
            session['usuario_pendiente_verificacion'] = 'otra'

        response = self.client.post('/logout')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['mensaje'], 'Sesión cerrada correctamente.')
        estado = self.client.get('/estado_sesion')
        self.assertFalse(estado.get_json()['logeado'])
        with self.client.session_transaction() as session:
            self.assertNotIn('usuario_pendiente_verificacion', session)

    def test_password_reset_request_does_not_disclose_unknown_email(self):
        unknown = self.client.post('/recuperar-contrasena', json={'email': 'nadie@example.com'})
        self.add_verified_user()
        with self.patch_reset_email_sender():
            known = self.client.post('/recuperar-contrasena', json={'email': 'ana@example.com'})

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.get_json(), known.get_json())
        self.assertIn('Si el correo corresponde', known.get_json()['mensaje'])
        self.assertEqual(
            self.tables['usuarios'][0]['password_reset_code_hash'],
            xrtegazz.hash_codigo_verificacion('ana', '654321'),
        )

    def test_password_reset_requires_verified_email_and_valid_code(self):
        self.tables['usuarios'].append({
            'id': 1,
            'username': 'pendiente',
            'email': 'pendiente@example.com',
            'email_verified': False,
            'password_hash': generate_password_hash('clave-anterior'),
        })
        with patch.object(xrtegazz, 'enviar_codigo_recuperacion') as send_code:
            response = self.client.post('/recuperar-contrasena', json={'email': 'pendiente@example.com'})
        self.assertEqual(response.status_code, 200)
        send_code.assert_not_called()

        self.add_verified_user()
        with self.patch_reset_email_sender():
            self.client.post('/recuperar-contrasena', json={'email': 'ana@example.com'})

        invalid = self.client.post('/restablecer-contrasena', json={
            'email': 'ana@example.com',
            'codigo': '000000',
            'contrasena': 'nueva-clave-segura',
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.tables['usuarios'][1]['password_reset_code_attempts'], 1)
        self.assertTrue(xrtegazz.check_password_hash(
            self.tables['usuarios'][1]['password_hash'],
            'clave-segura',
        ))

    def test_password_reset_changes_password_and_consumes_code(self):
        self.add_verified_user()
        with self.patch_reset_email_sender():
            request_code = self.client.post('/recuperar-contrasena', json={'email': 'ana@example.com'})

        self.assertEqual(request_code.status_code, 200)
        response = self.client.post('/restablecer-contrasena', json={
            'email': 'ana@example.com',
            'codigo': '654321',
            'contrasena': 'nueva-clave-segura',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(xrtegazz.check_password_hash(
            self.tables['usuarios'][0]['password_hash'],
            'nueva-clave-segura',
        ))
        self.assertIsNone(self.tables['usuarios'][0]['password_reset_code_hash'])
        self.assertIsNone(self.tables['usuarios'][0]['password_reset_code_expires'])

        reused = self.client.post('/restablecer-contrasena', json={
            'email': 'ana@example.com',
            'codigo': '654321',
            'contrasena': 'otra-clave-segura',
        })
        self.assertEqual(reused.status_code, 400)

    @patch.dict('os.environ', {
        'SMTP_HOST': 'smtp.example.com',
        'SMTP_PORT': '587',
        'SMTP_USERNAME': 'sender@example.com',
        'SMTP_PASSWORD': 'test-password',
        'SMTP_FROM': 'sender@example.com',
        'SMTP_USE_TLS': 'true',
        'SMTP_USE_SSL': 'false',
    })
    def test_smtp_message_contains_a_hashed_six_digit_code(self):
        self.tables['usuarios'].append({
            'id': 1,
            'username': 'ana',
            'email': 'ana@example.com',
            'nombre': 'Ana',
            'email_code_sent_at': None,
        })
        servidor = Mock()
        servidor.__enter__ = Mock(return_value=servidor)
        servidor.__exit__ = Mock(return_value=False)
        with patch('xrtegazz.smtplib.SMTP', return_value=servidor):
            resultado = xrtegazz.enviar_codigo_verificacion(self.tables['usuarios'][0])

        self.assertTrue(resultado['ok'])
        mensaje = servidor.send_message.call_args.args[0]
        codigo = re.search(r'\b(\d{6})\b', mensaje.get_content()).group(1)
        self.assertEqual(mensaje['From'], 'XRTEGAZZ IA <sender@example.com>')
        self.assertEqual(self.tables['usuarios'][0]['email_code_hash'], xrtegazz.hash_codigo_verificacion('ana', codigo))
        self.assertNotEqual(self.tables['usuarios'][0]['email_code_hash'], codigo)
        servidor.starttls.assert_called_once()

    @patch.dict('os.environ', {
        'SMTP_HOST': 'smtp.example.com',
        'SMTP_PORT': '587',
        'SMTP_USERNAME': 'sender@example.com',
        'SMTP_PASSWORD': 'test-password',
        'SMTP_FROM': 'sender@example.com',
        'SMTP_USE_TLS': 'true',
        'SMTP_USE_SSL': 'false',
    })
    def test_password_reset_email_uses_separate_hashed_code(self):
        registro = {
            'id': 1,
            'username': 'ana',
            'email': 'ana@example.com',
            'email_verified': True,
            'nombre': 'Ana',
        }
        self.tables['usuarios'].append(registro)
        servidor = Mock()
        servidor.__enter__ = Mock(return_value=servidor)
        servidor.__exit__ = Mock(return_value=False)
        with patch('xrtegazz.smtplib.SMTP', return_value=servidor):
            resultado = xrtegazz.enviar_codigo_recuperacion(registro)

        self.assertTrue(resultado['ok'])
        mensaje = servidor.send_message.call_args.args[0]
        codigo = re.search(r'\b(\d{6})\b', mensaje.get_content()).group(1)
        self.assertIn('restablecer tu contraseña', mensaje['Subject'])
        self.assertEqual(
            registro['password_reset_code_hash'],
            xrtegazz.hash_codigo_verificacion('ana', codigo),
        )
        self.assertNotIn('email_code_hash', registro)

    @patch.dict('os.environ', {
        'SMTP_HOST': '',
        'SMTP_FROM': '',
        'SMTP_USERNAME': '',
        'SMTP_PASSWORD': '',
    })
    def test_smtp_missing_configuration_returns_actionable_error(self):
        resultado = xrtegazz.enviar_codigo_verificacion({
            'username': 'ana',
            'email': 'ana@example.com',
        })
        self.assertFalse(resultado['ok'])
        self.assertEqual(resultado['status'], 503)
        self.assertIn('SMTP_HOST', resultado['error'])


if __name__ == '__main__':
    unittest.main()
