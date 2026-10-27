import json
from pathlib import Path

import xrtegazz
from werkzeug.security import generate_password_hash


def leer_filas(ruta):
    if not ruta.exists():
        return []
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        return [
            {
                'username': username,
                'password': contenido.get('password'),
                'password_hash': contenido.get('password_hash'),
                'nombre': contenido.get('nombre') or username,
                'rol': 'administrador' if username.lower() == 'xrtegazz' else 'invitado',
            }
            for username, contenido in datos.items()
        ]
    raise ValueError(f'Formato JSON inesperado en {ruta.name}.')


def migrar():
    if xrtegazz.POSTGRES_POOL is None:
        raise RuntimeError('Configura DATABASE_URL antes de ejecutar la migración.')

    xrtegazz.inicializar_postgres()
    directorio = Path(__file__).with_name('data')
    usuarios = leer_filas(directorio / 'usuarios.json') + leer_filas(Path(__file__).with_name('usuarios.json'))
    sesiones = leer_filas(directorio / 'sesiones.json')
    mensajes = leer_filas(directorio / 'conversaciones.json')
    opiniones = leer_filas(directorio / 'retroalimentacion.json')

    por_usuario = {}
    for usuario in usuarios:
        nombre_usuario = str(usuario.get('username') or '').strip().lower()
        if not nombre_usuario:
            continue
        password_hash = usuario.get('password_hash')
        if not password_hash and usuario.get('password'):
            password_hash = generate_password_hash(str(usuario['password']))
        if password_hash:
            por_usuario[nombre_usuario] = {
                'username': nombre_usuario,
                'password_hash': str(password_hash),
                'rol': str(usuario.get('rol') or 'invitado'),
                'nombre': str(usuario.get('nombre') or nombre_usuario),
                'fecha_registro': usuario.get('fecha_registro'),
            }

    if 'xrtegaz' in por_usuario and 'xrtegazz' not in por_usuario:
        administrador = dict(por_usuario['xrtegaz'])
        administrador.update(username='xrtegazz', rol='administrador')
        por_usuario['xrtegazz'] = administrador

    if not por_usuario:
        por_usuario['invitado_anonimo'] = {
            'username': 'invitado_anonimo',
            'password_hash': generate_password_hash('invitado123'),
            'rol': 'invitado',
            'nombre': 'Invitado Base',
        }

    with xrtegazz.POSTGRES_POOL.connection(timeout=10) as conexion:
        with conexion.cursor() as cursor:
            for usuario in por_usuario.values():
                cursor.execute(
                    """
                    INSERT INTO usuarios (username, password_hash, rol, nombre, fecha_registro)
                    VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()))
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        usuario['username'],
                        usuario['password_hash'],
                        usuario['rol'],
                        usuario['nombre'],
                        usuario.get('fecha_registro'),
                    ),
                )

            for sesion in sesiones:
                if not sesion.get('id') or not sesion.get('username'):
                    continue
                cursor.execute(
                    """
                    INSERT INTO sesiones_chat (id, username, titulo, fecha_creacion, fecha_actualizacion)
                    VALUES (%s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW()))
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        sesion['id'],
                        sesion['username'],
                        sesion.get('titulo') or 'Sesión importada',
                        sesion.get('fecha_creacion'),
                        sesion.get('fecha_actualizacion'),
                    ),
                )

            for mensaje in mensajes:
                if not mensaje.get('id') or not mensaje.get('username'):
                    continue
                cursor.execute(
                    """
                    INSERT INTO historial_chat (id, username, role, content, id_sesion, fecha)
                    VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()))
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        mensaje['id'],
                        mensaje['username'],
                        mensaje.get('role') or 'user',
                        mensaje.get('content') or '',
                        mensaje.get('id_sesion'),
                        mensaje.get('fecha'),
                    ),
                )

            for opinion in opiniones:
                if not opinion.get('respuesta_id') or not opinion.get('usuario'):
                    continue
                cursor.execute(
                    """
                    INSERT INTO retroalimentacion
                        (respuesta_id, usuario, sesion, calificacion, comentario, pregunta, respuesta, fecha)
                    SELECT %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW())
                    WHERE NOT EXISTS (
                        SELECT 1 FROM retroalimentacion
                        WHERE respuesta_id = %s AND usuario = %s
                    )
                    """,
                    (
                        opinion['respuesta_id'],
                        opinion['usuario'],
                        opinion.get('sesion'),
                        opinion.get('calificacion') or 'no_util',
                        opinion.get('comentario') or '',
                        opinion.get('pregunta') or '',
                        opinion.get('respuesta') or '',
                        opinion.get('fecha'),
                        opinion['respuesta_id'],
                        opinion['usuario'],
                    ),
                )

            for tabla in ('sesiones_chat', 'historial_chat'):
                cursor.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{tabla}', 'id'),
                        GREATEST(COALESCE((SELECT MAX(id) FROM {tabla}), 1), 1),
                        true
                    )
                    """
                )

    print(
        'Migración completada: '
        f'{len(por_usuario)} usuarios, {len(sesiones)} sesiones, '
        f'{len(mensajes)} mensajes y {len(opiniones)} opiniones revisados.'
    )


if __name__ == '__main__':
    migrar()
