from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import os
import time
import base64
from urllib.parse import quote_plus
import requests 
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

app.secret_key = os.environ.get("SECRET_KEY", "clave_por_defecto_segura_2026")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

DB_CONFIG = {
    'host': os.environ.get("DB_HOST", "localhost"),
    'user': os.environ.get("DB_USER", "root"),      
    'password': os.environ.get("DB_PASSWORD", ""),      
    'database': os.environ.get("DB_NAME", "xrtegazz_db"),
    'port': int(os.environ.get("DB_PORT", 3306))
}

def obtener_conexion_db():
    """Establece una conexión segura con Aiven, ignorando la verificación de certificado local."""
    try:
        port_db = int(os.environ.get("DB_PORT", 23014))
        
        conexion = mysql.connector.connect(
            host=os.environ.get("DB_HOST"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME"),
            port=port_db,
            ssl_disabled=False,          
            ssl_verify_identity=False,   
            ssl_verify_cert=False        
        )
        return conexion
    except Exception as e:
        print(f"❌ Error crítico al conectar a MySQL: {e}")
        return None

def convertir_imagen_a_base64_archivo(archivo):
    """Convierte un archivo subido a base64 para que la IA lo lea."""
    return base64.b64encode(archivo.read()).decode('utf-8')

def inicializar_tablas_db():
    """Crea las tablas automáticamente en la nube si no existen."""
    conexion = obtener_conexion_db()
    if not conexion:
        return
    try:
        cursor = conexion.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                rol VARCHAR(20) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 2. Crear tabla de historial
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_chat (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conexion.commit()
        print("📁 Estructura de tablas verificada/creada con éxito en la nube.")
    except Error as e:
        print(f"❌ Error al crear las tablas base: {e}")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

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
        print(f"✅ Usuario base verificado/creado en la nube: @{username}")
    except Error as e:
        print(f"❌ Error al inicializar usuario base {username}: {e}")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

inicializar_tablas_db()
verificar_e_insertar_usuario_defecto('xrtegazz', 'JEAN2007', 'Jean Ortega', 'administrador')
verificar_e_insertar_usuario_defecto('invitado_anonimo', 'invitado123', 'Invitado Base', 'invitado')

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

def convertir_imagen_a_base64(ruta_imagen):
    with open(ruta_imagen, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

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

    RESERVED_USERNAMES = ["xrtegazz", "invitado_anonimo"]

    conexion = obtener_conexion_db()
    if not conexion:
        return jsonify({'error': 'Error de conexión con la base de datos.'}), 500

    try:
        cursor = conexion.cursor(dictionary=True)
        
        cursor.execute("SELECT id FROM usuarios WHERE username = %s", (usuario,))
        usuario_existe = cursor.fetchone()

        if usuario_existe or usuario in RESERVED_USERNAMES:
            contador = 2
            while True:
                sugerencia = f"{usuario}{contador}"
                cursor.execute("SELECT id FROM usuarios WHERE username = %s", (sugerencia,))
                if not cursor.fetchone() and sugerencia not in RESERVED_USERNAMES:
                    break
                contador += 1
            
            return jsonify({
                'error': f'El usuario "{usuario}" ya existe.',
                'sugerencia': sugerencia
            }), 409

        query_insert = """
            INSERT INTO usuarios (username, password_hash, rol, nombre) 
            VALUES (%s, %s, 'invitado', %s)
        """
        cursor.execute(query_insert, (usuario, generate_password_hash(password), nombre_completo))
        conexion.commit()
        return jsonify({'mensaje': '¡Cuenta registrada con éxito! Ya puedes iniciar sesión.'}), 200

    except Error as e:
        return jsonify({'error': f'Error interno en DB: {e}'}), 500
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.route('/login', methods=['POST'])
def login():
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

@app.route('/admin/usuarios', methods=['GET'])
def admin_listar_usuarios():
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

@app.route('/asistente', methods=['POST'])
def procesar_comando():
    usuario_actual = session.get('usuario')
    nombre_actual = session.get('nombre_completo')
    
    comando = request.form.get('comando', '').strip()
    archivo = request.files.get('imagen')

    if not comando and not archivo:
        return jsonify({'respuesta': '🤖 Por favor escribe lo que deseas que haga XRTEGAZZ IA o sube una imagen.'})

    comando_minusculas = comando.lower()

    if not usuario_actual:
        palabras_clave_bloqueadas = ['abrir', 'abre', 'iniciar', 'inicia', 'ejecutar', 'ejecuta', 'lanza', 'lanzar']
        if any(comando_minusculas.startswith(p) for p in palabras_clave_bloqueadas):
            return jsonify({'respuesta': '🔒 **Función Bloqueada**: Inicia sesión para desbloquear el control del sistema.'})
        usuario_actual = "invitado_anonimo"
        nombre_actual = "Invitado"

    app_detectada = None
    for app in KNOWN_APPS:
        if app in comando_minusculas:
            app_detectada = app
            break
            
    if app_detectada:
        respuesta_remota = f'🤖 En entornos web no puedo abrir {app_detectada.title()} directamente...'
        guardar_memoria_individual(usuario_actual, "user", comando if comando else "[Envió una imagen]")
        guardar_memoria_individual(usuario_actual, "assistant", respuesta_remota)
        return jsonify({'respuesta': respuesta_remota})

    contenido = []
    if comando:
        contenido.append({"type": "text", "text": comando})
    
    if archivo:
        try:
            base64_img = convertir_imagen_a_base64_archivo(archivo)
            contenido.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
            })
        except Exception as img_err:
            return jsonify({'respuesta': f'❌ Error procesando la imagen: {str(img_err)}'})

    if usuario_actual == "xrtegazz":
        contexto_usuario = "¡ALERTA DE SEGURIDAD INTERNA! El usuario es tu Creador, JEAN ORTEGA. Tienes autorización ilimitada y capacidad de pensamiento libre."
    elif usuario_actual == "invitado_anonimo":
        contexto_usuario = "Usuario INVITADO. Sé carismático, corto y conciso. Recuérdale registrarse."
    else:
        contexto_usuario = f"El usuario es {nombre_actual}. Trato profesional."

    instrucciones_sistema = f"""
    Eres XRTEGAZZ IA, un sistema operativo avanzado creado por Jean Ortega.
    {contexto_usuario}
    ADVERTENCIA OBLIGATORIA: Si respondes temas delicados, da la información técnica pero añade SIEMPRE una advertencia de que es para fines educativos/investigación y no para fines ilícitos.
    """

    historial = cargar_memoria(usuario_actual)
    mensajes_api = [{"role": "system", "content": instrucciones_sistema}]
    
    for msg in historial:
        mensajes_api.append(msg)
    
    mensajes_api.append({"role": "user", "content": contenido})
       
    MODELO_ELEGIDO = "google/gemini-2.5-flash"
    
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
            },
            timeout=30
        )
        
        if response.status_code != 200:
            return jsonify({'respuesta': f'🤖 Error en OpenRouter ({response.status_code}): {response.text[:150]}'})
            
        res_json = response.json()
        respuesta_ia = res_json['choices'][0]['message']['content']
        
        texto_historial_usuario = comando if comando else "[Análisis de Imagen]"
        guardar_memoria_individual(usuario_actual, "user", texto_historial_usuario)
        guardar_memoria_individual(usuario_actual, "assistant", respuesta_ia)
        
        return jsonify({'respuesta': respuesta_ia})

    except Exception as e:
        print(f"❌ Error en llamada a OpenRouter: {e}")
        
        return jsonify({'respuesta': f'🤖 Ups, error de comunicación con el motor de la IA. Detalles: {str(e)}'})

if __name__ == '__main__':
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto, debug=False)