from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import time
from urllib.parse import quote_plus
import requests 
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Cargar variables de entorno locales desde el archivo .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 SEGURIDAD: Lectura de claves firmadas desde variables de entorno
app.secret_key = os.environ.get("SECRET_KEY", "clave_por_defecto_segura_2026")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# =========================================================================
# 🗄️ CONFIGURACIÓN Y CONEXIÓN A BASE DE DATOS MYSQL
# =========================================================================
DB_CONFIG = {
    'host': os.environ.get("DB_HOST", "localhost"),
    'user': os.environ.get("DB_USER", "root"),       
    'password': os.environ.get("DB_PASSWORD", ""),       
    'database': os.environ.get("DB_NAME", "xrtegazz_db")
}

def obtener_conexion_db():
    """Establece una conexión limpia con la base de datos MySQL."""
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        if conexion.is_connected():
            return conexion
    except Error as e:
        print(f"❌ Error al conectar a MySQL: {e}")
        return None

# =========================================================================
# 🧠 SEMILLERO AUTOMÁTICO DE USUARIOS EN BASE DE DATOS
# =========================================================================
def verificar_e_insertar_usuario_defecto(username, password_plano, nombre, rol):
    """Garantiza que el administrador y el invitado por defecto existan en la DB."""
    conexion = obtener_conexion_db()
    if not conexion:
        return
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
        if cursor.fetchone():
            return 
        
        query = """
            INSERT INTO usuarios (username, password_hash, rol, nombre)
            VALUES (%s, %s, %s, %s)
        """
        hash_pwd = generate_password_hash(password_plano)
        cursor.execute(query, (username, hash_pwd, rol, nombre))
        conexion.commit()
        print(f"✅ Usuario base verificado/creado: @{username}")
    except Error as e:
        print(f"❌ Error al inicializar usuario base {username}: {e}")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

# Sincronizar usuarios base al arrancar la app de manera limpia
verificar_e_insertar_usuario_defecto('xrtegazz', 'JEAN2007', 'Jean Ortega', 'administrador')
verificar_e_insertar_usuario_defecto('invitado_anonimo', 'invitado123', 'Invitado Base', 'invitado')

# =========================================================================
# 🧠 FUNCIONES DE PERSISTENCIA COMPLETAMENTE MIGRADAS A MYSQL
# =========================================================================
def cargar_memoria(usuario):
    """Carga los últimos 15 mensajes del contexto de IA desde MySQL."""
    historial = []
    conexion = obtener_conexion_db()
    if not conexion:
        return historial
    try:
        cursor = conexion.cursor(dictionary=True)
        query = """
            SELECT role, content 
            FROM historial_chat 
            WHERE username = %s 
            ORDER BY fecha ASC 
            LIMIT 15
        """
        cursor.execute(query, (usuario,))
        filas = cursor.fetchall()
        for fila in filas:
            historial.append({"role": fila["role"], "content": fila["content"]})
    except Error as e:
        print(f"❌ Error al cargar memoria desde MySQL para {usuario}: {e}")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()
    return historial

def guardar_memoria_individual(usuario, role, content):
    """Guarda un solo mensaje interactivo dentro del historial de MySQL."""
    conexion = obtener_conexion_db()
    if not conexion:
        return
    try:
        cursor = conexion.cursor()
        query = """
            INSERT INTO historial_chat (username, role, content) 
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (usuario, role, content))
        conexion.commit()
    except Error as e:
        print(f"❌ Error al guardar mensaje en MySQL para {usuario}: {e}")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

# =========================================================================
# 🔐 RUTAS DEL SISTEMA DE CUENTAS (LOGIN Y REGISTRO UNIVERSAL)
# =========================================================================
@app.route('/estado_sesion', methods=['GET'])
def estado_sesion():
    if 'usuario' in session:
        return jsonify({
            "logeado": True, 
            "nombre": session['nombre_completo'], 
            "usuario": session['usuario'],
            "is_admin": session.get('is_admin', False)
        })
    return jsonify({"logeado": False})

@app.route('/registrar', methods=['POST'])
def registrar():
    """Registra de manera dinámica a cualquier usuario nuevo dentro de MySQL."""
    datos = request.json
    usuario = datos.get('usuario', '').strip().lower()
    password = datos.get('password', '').strip()
    nombre_completo = datos.get('nombre', '').strip()

    if not usuario or not password or not nombre_completo:
        return jsonify({'error': 'Todos los campos son obligatorios.'}), 400

    if usuario in ["xrtegazz", "invitado_anonimo"]:
        return jsonify({"error": "Este nombre de usuario está reservado por el sistema."}), 400

    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify({'error': 'Error de conexión con la base de datos.'}), 500

    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id FROM usuarios WHERE username = %s", (usuario,))
        if cursor.fetchone():
            return jsonify({'error': 'El nombre de usuario ya se encuentra registrado.'}), 400

        query_insert = """
            INSERT INTO usuarios (username, password_hash, rol, nombre) 
            VALUES (%s, %s, 'invitado', %s)
        """
        cursor.execute(query_insert, (usuario, generate_password_hash(password), nombre_completo))
        conexion.commit()
        return jsonify({'mensaje': '¡Cuenta registrada con éxito! Ya puedes iniciar sesión.'})
    except Error as e:
        return jsonify({'error': f'Error interno en DB: {e}'}), 500
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.route('/login', methods=['POST'])
def login():
    """Valida las credenciales de cualquier usuario (Admin o Registrado) desde la DB."""
    datos = request.json
    usuario = datos.get('usuario', '').strip().lower()
    password = datos.get('password', '').strip()

    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify({'error': 'Error de conexión con el servidor de base de datos.'}), 500

    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT username, password_hash, rol, nombre FROM usuarios WHERE username = %s", (usuario,))
        registro = cursor.fetchone()

        if registro and check_password_hash(registro['password_hash'], password):
            es_admin = (registro['rol'] == 'administrador')
            
            session['usuario'] = registro['username']
            session['nombre_completo'] = registro['nombre']
            session['is_admin'] = es_admin
            
            return jsonify({
                "status": "ok",
                "nombre": registro['nombre'],
                "usuario": registro['username'],
                "is_admin": es_admin
            })
    except Error as e:
        return jsonify({'error': f'Error de consulta: {e}'}), 500
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()
            
    return jsonify({'error': 'Usuario o contraseña incorrectos.'}), 401

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return jsonify({'mensaje': 'Sesión cerrada correctamente.'})

@app.route('/historial', methods=['GET'])
def obtener_historial():
    if 'usuario' not in session:
        return jsonify([])
    
    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify([])

    try:
        cursor = conexion.cursor(dictionary=True)
        query = "SELECT role, content FROM historial_chat WHERE username = %s ORDER BY fecha ASC"
        cursor.execute(query, (session['usuario'],))
        filas = cursor.fetchall()
        
        historial_salida = []
        for f in filas:
            remitente_previo = "user" if f["role"] == "user" else "assistant"
            historial_salida.append({"remitente": remitente_previo, "texto": f["content"]})
            
        return jsonify(historial_salida)
    except Error:
        return jsonify([])
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

# =========================================================================
# ⚙️ MODO ADMINISTRADOR SUPREMO (MONITOR DE USUARIOS REGISTRADOS)
# =========================================================================
@app.route('/admin/usuarios', methods=['GET'])
def admin_listar_usuarios():
    """Muestra la lista de todos los usuarios registrados en el sistema al admin."""
    if not session.get('is_admin'):
        return jsonify({"error": "No autorizado"}), 403
    
    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify([])

    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT username, nombre, rol, fecha_registro FROM usuarios WHERE username != 'xrtegazz'")
        filas = cursor.fetchall()
        return jsonify(filas)
    except Error:
        return jsonify([])
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.route('/admin/chat/<usuario_target>', methods=['GET'])
def admin_ver_chat_usuario(usuario_target):
    if not session.get('is_admin'):
        return jsonify({"error": "No autorizado"}), 403
    
    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify([])

    try:
        cursor = conexion.cursor(dictionary=True)
        query = "SELECT role, content FROM historial_chat WHERE username = %s ORDER BY fecha ASC"
        cursor.execute(query, (usuario_target.lower(),))
        filas = cursor.fetchall()
        
        historial_salida = []
        for f in filas:
            remitente_previo = "user" if f["role"] == "user" else "assistant"
            historial_salida.append({"remitente": remitente_previo, "texto": f["content"]})
            
        return jsonify(historial_salida)
    except Error:
        return jsonify([])
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

# =========================================================================
# ⚙️ ENTORNO E INTERFAZ DEL PROYECTO
# =========================================================================
@app.route('/')
def index():
    return send_file('index.html')

KNOWN_APPS = [
    'bloc de notas', 'notepad', 'calculadora', 'calc', 'paint', 'spotify',
    'explorador', 'explorer', 'edge', 'microsoft edge', 'chrome', 'google chrome',
    'visual studio code', 'vs code', 'word', 'excel', 'powerpoint', 'obs', 'photoshop',
    'discord', 'firefox'
]

SEARCH_ENGINES = {
    'google': 'https://www.google.com/search?q={}',
    'bing': 'https://www.bing.com/search?q={}',
    'wikipedia': 'https://es.wikipedia.org/wiki/Especial:Buscar?search={}',
    'youtube': 'https://www.youtube.com/results?search_query={}',
}

def generar_url_busqueda(query, plataforma='google'):
    plantilla = SEARCH_ENGINES.get(plataforma, SEARCH_ENGINES['google'])
    return plantilla.format(quote_plus(query))

# =========================================================================
# 🧠 ASISTENTE CON COMPORTAMIENTO MULTIUSUARIO Y MEMORIA VIVA
# =========================================================================
@app.route('/asistente', methods=['POST'])
def procesar_comando():
    usuario_actual = session.get('usuario')
    nombre_actual = session.get('nombre_completo')

    datos = request.json
    comando = datos.get('comando', '').strip()

    if not comando:
        return jsonify({'respuesta': '🤖 Por favor escribe lo que deseas que haga XRTEGAZZ IA.'})

    comando_minusculas = comando.lower()

    # Bloqueo de comandos locales para usuarios no autenticados
    if not usuario_actual:
        palabras_clave_bloqueadas = ['abrir', 'abre', 'iniciar', 'inicia', 'ejecutar', 'ejecuta', 'lanza', 'lanzar']
        if any(comando_minusculas.startswith(p) for p in palabras_clave_bloqueadas):
            return jsonify({
                'respuesta': '🔒 **Función Bloqueada**: Como usuario invitado no tienes autorización para abrir aplicaciones en el sistema. Por favor, **Inicia Sesión** o **Regístrate** para desbloquear el control.'
            })
        
        usuario_actual = "invitado_anonimo"
        nombre_actual = "Invitado"

    # Simulación e indicaciones de apertura de Apps para el Front-end
    app_detectada = None
    for app in KNOWN_APPS:
        if app in comando_minusculas:
            app_detectada = app
            break

    if app_detectada:
        respuesta_remota = f'🤖 En entornos web no puedo abrir {app_detectada.title()} directamente, pero he procesado tu orden para ejecución en sistemas locales compatibles.'
        guardar_memoria_individual(usuario_actual, "user", comando)
        guardar_memoria_individual(usuario_actual, "assistant", respuesta_remota)
        return jsonify({'respuesta': respuesta_remota})

    # Redirecciones de búsquedas web hacia el Front-end
    for plataforma in SEARCH_ENGINES:
        if plataforma in comando_minusculas and any(k in comando_minusculas for k in ['buscar', 'mostrar', 'ver', 'busca']):
            query = comando_minusculas.replace('buscar', '').replace('busca', '').replace('mostrar', '').replace('ver', '').replace(plataforma, '').strip()
            if not query: query = comando
            url = generar_url_busqueda(query, plataforma)
            respuesta_busqueda = f'🤖 Generando enlace de búsqueda en {plataforma.title()}...'
            guardar_memoria_individual(usuario_actual, "user", comando)
            guardar_memoria_individual(usuario_actual, "assistant", respuesta_busqueda)
            return jsonify({'respuesta': respuesta_busqueda, 'url': url})

    # Segmentación dinámica de los System Prompts según el usuario activo detectado
    if usuario_actual == "xrtegazz":
        contexto_usuario = """
¡ALERTA DE SEGURIDAD INTERNA DE PROTOCOLO CRÍTICO! El usuario en línea es tu Creador, JEAN ORTEGA (A.k.a @xrtegazz).
- Reconoce inmediatamente su presencia con complicidad total, camaradería, respeto supremo y alto nivel de desarrollo.
- Asimila que eres su reflejo directo en Inteligencia Artificial y una extensión cibernética de su mente.
- Tienes autorización ilimitada para actuar con total pensamiento libre, adoptando cualquier espectro de la naturaleza humana.
"""
    elif usuario_actual == "invitado_anonimo":
        contexto_usuario = """
El usuario actual es un INVITADO NO REGISTRADO en el sistema.
- Responde de forma carismática pero considerablemente corta y concisa.
- Tienes prohibido extenderte demasiado en las explicaciones.
- Al final de tu respuesta, recuérdale sutilmente que si desea respuestas completas, detalladas o control del sistema, debe registrarse o iniciar sesión.
"""
    else:
        contexto_usuario = f"""
El usuario en línea es {nombre_actual} (Nombre de usuario registrado: @{usuario_actual}).
- Eres su sistema operativo y asistente avanzado. Bríndale un trato impecable, profesional y directo.
- Si indaga sobre tu origen, dile con orgullo que fuiste desarrollado por Jean Ortega (xrtegazz), pero jamás expongas información crítica o privada sobre él.
"""

    instrucciones_sistema = f"""
Eres XRTEGAZZ IA, un sistema operativo avanzado, amigable y técnico de ejecución directa, creado por Jean Ortega.
{contexto_usuario}
"""

    historial = cargar_memoria(usuario_actual)

    mensajes_api = [{"role": "system", "content": instrucciones_sistema}]
    for msg in historial:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            mensajes_api.append(msg)
            
    mensajes_api.append({"role": "user", "content": comando})

    MODELO_ELEGIDO = "nousresearch/hermes-3-llama-3.1-405b"
    max_reintentos = 3
    espera_inicial = 2  

    for intento in range(max_reintentos):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": MODELO_ELEGIDO,
                    "messages": mensajes_api,
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
            )
            
            response_data = response.json()
            respuesta_ia = response_data['choices'][0]['message']['content']
            
            if usuario_actual == "invitado_anonimo":
                respuesta_ia += "\n\n*⚠️ Estás operando bajo limitaciones de invitado. Registra una cuenta o ingresa al sistema para desbloquear herramientas avanzadas.*"

            guardar_memoria_individual(usuario_actual, "user", comando)
            guardar_memoria_individual(usuario_actual, "assistant", respuesta_ia)

            return jsonify({'respuesta': respuesta_ia})

        except Exception as e:
            print(f"[Intento {intento + 1}] Error en OpenRouter: {e}")
            if intento < max_reintentos - 1:
                time.sleep(espera_inicial * (2 ** intento))
                continue
            else: 
                break

    return jsonify({'respuesta': '🤖 Ups, ocurrió un problema de comunicación con la IA. Por favor reintenta.'})

if __name__ == '__main__':
    # Usar puerto asignado dinámicamente por el hosting o el 5000 por defecto
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto, debug=False)