import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import xrtegazz


class FallbackResponseTests(unittest.TestCase):
    def test_opening_postgres_pool_initializes_schema_once(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = cursor
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        pool = Mock()
        pool.connection.return_value = connection

        with (
            patch.object(xrtegazz, 'POSTGRES_POOL', pool),
            patch.object(xrtegazz, 'POSTGRES_POOL_OPEN', False),
            patch.object(xrtegazz, 'POSTGRES_SCHEMA_READY', False),
        ):
            xrtegazz.abrir_pool_postgres()
            xrtegazz.abrir_pool_postgres()

        pool.open.assert_called_once_with()
        pool.connection.assert_called_once_with(timeout=5)
        self.assertEqual(cursor.execute.call_count, len([
            statement for statement in xrtegazz.POSTGRES_SCHEMA.split(';') if statement.strip()
        ]) + 1)
        self.assertIn('pg_advisory_xact_lock', cursor.execute.call_args_list[0].args[0])

    def test_postgres_connection_returns_connection_to_pool_once(self):
        pool = Mock()
        connection = SimpleNamespace(closed=False)
        conexion_adaptada = xrtegazz.PostgresConnection(pool, connection)

        conexion_adaptada.close()
        conexion_adaptada.close()

        pool.putconn.assert_called_once_with(connection)
        self.assertFalse(conexion_adaptada.is_connected())

    def test_pool_timeout_returns_retryable_service_error(self):
        cliente = xrtegazz.app.test_client()
        with cliente.session_transaction() as datos_sesion:
            datos_sesion['usuario'] = 'ana'

        with patch('xrtegazz.obtener_conexion_db', side_effect=xrtegazz.PoolTimeout('pool exhausted')):
            respuesta = cliente.get('/historial')

        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(
            respuesta.get_json()['error'],
            'El servicio está ocupado. Inténtalo de nuevo en unos segundos.',
        )

    def test_local_helper_responds_to_greeting(self):
        respuesta = xrtegazz.responder_localmente('hola', 'Ana')
        self.assertIn('Hola, Ana.', respuesta)

    def test_local_helper_handles_casual_question(self):
        respuesta = xrtegazz.responder_localmente('quien te creo')
        self.assertIn('XRTEGAZZ IA', respuesta)

    def test_local_helper_reports_current_date_and_time(self):
        self.assertIn('La hora local del servidor es', xrtegazz.responder_localmente('que hora'))
        self.assertIn('Hoy es', xrtegazz.responder_localmente('a que dia estamos'))

    def test_local_helper_solves_basic_math(self):
        self.assertEqual(xrtegazz.responder_localmente('25 * 4'), 'Paso a paso:\n25 × 4\n= 100')
        self.assertEqual(xrtegazz.responder_localmente('raiz cuadrada de 144'), 'La raíz cuadrada de 144 es 12.')
        self.assertEqual(xrtegazz.responder_localmente('cuanto es 10 dividido entre 2'), 'Paso a paso:\n10 ÷ 2\n= 5')

    def test_local_helper_preserves_complete_expression_and_exact_results(self):
        self.assertEqual(
            xrtegazz.resolver_matematica_local('783 multiplicado por 942 dividido entre 38'),
            'Paso a paso:\n783 * 942 / 38\n= 368793/19',
        )
        with patch('xrtegazz.guardar_memoria_individual'):
            respuesta_api = xrtegazz.app.test_client().post(
                '/asistente',
                data={'comando': '783 multiplicado por 942 dividido entre 38'},
            )
        self.assertEqual(respuesta_api.status_code, 200)
        self.assertEqual(
            respuesta_api.get_json()['respuesta'],
            'Paso a paso:\n783 * 942 / 38\n= 368793/19',
        )
        self.assertEqual(
            xrtegazz.responder_localmente('9007199254740993 + 1'),
            'Paso a paso:\n9007199254740993 + 1\n= 9007199254740994',
        )
        self.assertEqual(
            xrtegazz.responder_localmente('1/2 + 1/4'),
            'Paso a paso:\n1/2 + 1/4\n= 3/4',
        )

    def test_local_helper_solves_fractions_primes_and_equations(self):
        self.assertEqual(xrtegazz.responder_localmente('17 es primo'), 'El número 17 es primo.')
        self.assertEqual(xrtegazz.responder_localmente('21 es primo'), 'El número 21 no es primo.')
        self.assertEqual(xrtegazz.responder_localmente('2x + 3 = 11'), 'La solución es x = 4.')
        self.assertEqual(
            xrtegazz.responder_localmente('quiero que me digas si yo tengo 4 mangos y un amigo me regala 10 cuantos mangos tengo'),
            'Paso a paso:\n4 + 10\n= 14',
        )

    def test_word_problem_with_giving_away_items_is_solved_locally(self):
        pregunta = 'Si Juan tiene 8 manzanas y regala 2 ¿cuántas le quedan?'
        self.assertEqual(
            xrtegazz.resolver_matematica_local(xrtegazz.normalizar_texto_local(pregunta)),
            'Paso a paso:\n8 - 2\n= 6',
        )
        with patch('xrtegazz.guardar_memoria_individual'):
            respuesta = xrtegazz.app.test_client().post(
                '/asistente',
                data={'comando': pregunta},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['proveedor'], 'local')
        self.assertEqual(respuesta.get_json()['respuesta'], 'Paso a paso:\n8 - 2\n= 6')

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_unresolved_math_questions_are_sent_to_gemini(self):
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(
            text='Gemini resolvió la consulta de matemáticas.'
        )
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            cliente = xrtegazz.app.test_client()
            respuestas = [
                cliente.post('/asistente', data={'comando': 'Calcula la integral de x al cuadrado'}),
                cliente.post('/asistente', data={'comando': 'Calcula la integral de x al cuadrado'}),
                cliente.post('/asistente', data={'comando': 'Find the derivative of x squared'}),
                cliente.post('/asistente', data={'comando': '1 +'}),
                cliente.post('/api/chat-local', json={'mensaje': 'Calcula la integral de x al cuadrado'}),
                cliente.post('/asistente', data={'comando': 'I had 12 marbles and lost some; how many are left?'}),
            ]
            igualdad = cliente.post('/asistente', data={'comando': '2=2'})

        for respuesta in respuestas:
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.get_json()['respuesta'], 'Gemini resolvió la consulta de matemáticas.')
            self.assertNotIn('proveedor', respuesta.get_json())
        self.assertEqual(igualdad.get_json()['respuesta'], 'La igualdad es verdadera.')
        self.assertEqual(cliente_modelo.models.generate_content.call_count, len(respuestas))

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_chat_api_sends_non_math_messages_to_gemini(self):
        cliente = xrtegazz.app.test_client()
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(text='Respuesta de Gemini.')
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo) as cliente_factory,
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            respuesta = cliente.post('/api/chat-local', json={'mensaje': 'gracias'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('proveedor', respuesta.get_json())
        self.assertEqual(respuesta.get_json()['respuesta'], 'Respuesta de Gemini.')
        argumentos = cliente_modelo.models.generate_content.call_args.kwargs
        self.assertEqual(argumentos['model'], 'gemini-2.5-flash')
        self.assertEqual(argumentos['config'].max_output_tokens, 512)
        opciones_http = cliente_factory.call_args.kwargs['http_options']
        self.assertEqual(opciones_http.timeout, 30000)
        self.assertEqual(opciones_http.retry_options.attempts, 2)
        self.assertEqual(opciones_http.retry_options.initial_delay, 0.25)
        self.assertEqual(opciones_http.retry_options.max_delay, 0.5)
        self.assertEqual(
            opciones_http.retry_options.http_status_codes,
            [408, 429, 500, 502, 503, 504],
        )

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_unknown_question_is_answered_by_gemini(self):
        cliente = xrtegazz.app.test_client()
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(
            text='La física cuántica estudia la materia a escala subatómica.'
        )
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            respuesta = cliente.post('/api/chat-local', json={'mensaje': 'explica fisica cuantica'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('proveedor', respuesta.get_json())
        self.assertIn('física cuántica', respuesta.get_json()['respuesta'])

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_uses_gemini_and_returns_answer(self):
        cliente = xrtegazz.app.test_client()
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(text='Respuesta fundamentada.')
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            respuesta = cliente.post('/asistente', data={'comando': '¿Qué ocurrió hoy?'})

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertNotIn('proveedor', datos)
        self.assertIn('Respuesta fundamentada.', datos['respuesta'])
        cliente_modelo.models.generate_content.assert_called_once()
        instrucciones = cliente_modelo.models.generate_content.call_args.kwargs['config'].system_instruction
        self.assertIn('palabras sencillas y frases cortas', instrucciones)
        self.assertIn('Nunca uses código LaTeX', instrucciones)
        self.assertIn('comprueba los valores finales', instrucciones)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_sends_greetings_to_gemini(self):
        cliente = xrtegazz.app.test_client()
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(
            text='¡Hola! ¿En qué puedo ayudarte?'
        )
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            respuesta = cliente.post('/asistente', data={'comando': 'hola'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('proveedor', respuesta.get_json())
        cliente_modelo.models.generate_content.assert_called_once()

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_waits_for_response_instead_of_returning_timeout(self):
        with (
            patch('xrtegazz.generar_respuesta_ia_con_fuentes', return_value=('Respuesta después de esperar.', [])),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual'),
        ):
            respuesta = xrtegazz.app.test_client().post(
                '/asistente',
                data={'comando': '¿Quién es Cristiano Ronaldo?'},
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['respuesta'], 'Respuesta después de esperar.')

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_hides_provider_timeout_details(self):
        with patch(
            'xrtegazz.generar_respuesta_ia_con_fuentes',
            side_effect=xrtegazz.httpx.TimeoutException('request timed out'),
        ):
            respuesta = xrtegazz.app.test_client().post(
                '/asistente',
                data={'comando': '¿Quién es Cristiano Ronaldo?'},
            )

        self.assertEqual(respuesta.status_code, 502)
        self.assertEqual(respuesta.get_json()['error'], 'No pude completar la respuesta. Inténtalo de nuevo.')
        self.assertNotIn('Gemini tardó', respuesta.get_json()['error'])

    @patch.dict('os.environ', {'GEMINI_API_KEY': '', 'GOOGLE_API_KEY': ''})
    def test_asistente_explains_when_gemini_key_is_missing(self):
        respuesta = xrtegazz.app.test_client().post(
            '/asistente',
            data={'comando': 'Explica la física cuántica.'},
        )

        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(
            respuesta.get_json()['error'],
            'El asistente no está disponible temporalmente. Inténtalo de nuevo más tarde.',
        )

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_returns_grounded_source_links(self):
        cliente = xrtegazz.app.test_client()
        candidato = SimpleNamespace(
            grounding_metadata=SimpleNamespace(
                grounding_chunks=[
                    SimpleNamespace(web=SimpleNamespace(uri='https://example.com/news', title='Fuente de prueba')),
                    SimpleNamespace(web=SimpleNamespace(uri='https://example.com/news', title='Fuente duplicada')),
                ]
            )
        )
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(
            text='Respuesta con búsqueda.',
            candidates=[candidato],
        )
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual') as guardar,
        ):
            respuesta = cliente.post('/asistente', json={'comando': '¿Qué ocurrió hoy?'})

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(datos['fuentes'], [{'titulo': 'Fuente de prueba', 'url': 'https://example.com/news'}])
        self.assertTrue(datos['respuesta_id'])
        self.assertIn('[Fuente de prueba](https://example.com/news)', guardar.call_args_list[-1].args[2])
        config = cliente_modelo.models.generate_content.call_args.kwargs['config']
        self.assertTrue(config.tools)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key', 'GOOGLE_API_KEY': ''})
    def test_asistente_passes_attached_image_to_gemini_without_persisting_it(self):
        cliente_modelo = Mock()
        cliente_modelo.models.generate_content.return_value = SimpleNamespace(text='Veo una imagen.')
        with (
            patch('xrtegazz.genai.Client', return_value=cliente_modelo),
            patch('xrtegazz.cargar_memoria', return_value=[]),
            patch('xrtegazz.guardar_memoria_individual') as guardar,
        ):
            respuesta = xrtegazz.app.test_client().post(
                '/asistente',
                json={
                    'comando': '',
                    'imagen_base64': 'aW1hZ2U=',
                    'mime_type': 'image/png',
                },
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['respuesta'], 'Veo una imagen.')
        contents = cliente_modelo.models.generate_content.call_args.kwargs['contents']
        self.assertEqual(contents[0], 'Analiza la imagen adjunta y describe su contenido de forma útil.')
        self.assertEqual(contents[1].inline_data.mime_type, 'image/png')
        self.assertEqual(contents[1].inline_data.data, b'image')
        self.assertEqual(guardar.call_count, 2)
        self.assertEqual(
            [call.args[2] for call in guardar.call_args_list],
            ['Analiza la imagen adjunta y describe su contenido de forma útil.', 'Veo una imagen.'],
        )

    def test_asistente_rejects_unsupported_image_types(self):
        respuesta = xrtegazz.app.test_client().post(
            '/asistente',
            json={
                'comando': 'Describe esta imagen.',
                'imagen_base64': 'aW1hZ2U=',
                'mime_type': 'image/svg+xml',
            },
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('PNG, JPG, WEBP o GIF', respuesta.get_json()['error'])

    def test_feedback_is_validated_and_saved(self):
        cliente = xrtegazz.app.test_client()
        with (
            patch('xrtegazz._local_leer', return_value=[]) as leer,
            patch('xrtegazz._local_guardar') as guardar,
        ):
            respuesta = cliente.post(
                '/api/feedback',
                json={
                    'respuesta_id': 'resp-123',
                    'calificacion': 'no_util',
                    'comentario': 'Le faltaron fuentes.',
                    'pregunta': '¿Qué pasó?',
                    'respuesta': 'Una respuesta.',
                },
            )
            invalida = cliente.post(
                '/api/feedback',
                json={'respuesta_id': 'resp-124', 'calificacion': 'neutral'},
            )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(invalida.status_code, 400)
        leer.assert_called_once_with('retroalimentacion')
        guardar.assert_called_once()
        self.assertEqual(guardar.call_args.args[0], 'retroalimentacion')
        self.assertEqual(guardar.call_args.args[1][0]['calificacion'], 'no_util')
        self.assertEqual(guardar.call_args.args[1][0]['comentario'], 'Le faltaron fuentes.')

    def test_feedback_storage_failure_returns_clear_error(self):
        with (
            patch('xrtegazz._local_leer', return_value=[]),
            patch('xrtegazz._local_guardar', side_effect=OSError('disk unavailable')),
            patch('xrtegazz.registrar_log') as registrar_log,
        ):
            respuesta = xrtegazz.app.test_client().post(
                '/api/feedback',
                json={'respuesta_id': 'resp-125', 'calificacion': 'util'},
            )

        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.get_json()['error'], 'No se pudo guardar tu opinión. Inténtalo de nuevo.')
        registrar_log.assert_called_once()


if __name__ == '__main__':
    unittest.main()
