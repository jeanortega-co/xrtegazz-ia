# XRTEGAZZ IA

**Asistente web inteligente** con interfaz oscura de alto contraste, respuestas con contexto conversacional, análisis de imágenes, búsqueda de información actualizada en internet, resolución de operaciones matemáticas, historial de chats y soporte instalable como Progressive Web App (PWA).

**Demo en vivo:** [xrtegazz-ia.vercel.app](https://xrtegazz-ia.vercel.app)

## Funcionalidades

- Conversación con IA y contexto de hasta seis mensajes recientes.
- Análisis de imágenes PNG, JPG, WEBP y GIF.
- Búsqueda web para consultas de información actualizada, con fuentes.
- Resolución local de operaciones matemáticas y ecuaciones.
- Registro e inicio de sesión, verificación de correo y recuperación de contraseña.
- Historial de conversaciones y sesiones.
- Interfaz adaptable e instalable como PWA.
- Almacenamiento local para desarrollo y PostgreSQL para despliegues compartidos.

## Stack tecnológico

Python, Flask, JavaScript (ES6+), HTML5, CSS3, APIs de IA (Google Gemini), búsqueda web, PWA y despliegue en Vercel.

## Estructura del proyecto

```text
.
├── .env.example
├── .gitignore
├── DEPLOYMENT.md
├── admin.html
├── generate_logo.py
├── index.html
├── index.py
├── manifest.json
├── migrate_json_to_postgres.py
├── requirements.txt
├── static/
│   └── logo.png
├── sw.js
├── test_email_verification.py
├── test_fallback.py
├── vercel.json
└── xrtegazz.py
```

La carpeta `data/` y el archivo `usuarios.json` se crean o utilizan localmente y están excluidos de Git.

## Instalación y ejecución local

1. Clona el repositorio y entra al directorio:

   ```bash
   git clone https://github.com/jeanortega-co/Xrtegazz-ia.git
   cd Xrtegazz-ia
   ```

2. Crea y activa un entorno virtual:

   ```bash
   python -m venv venv
   ```

   En Windows PowerShell:

   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

   En macOS o Linux:

   ```bash
   source venv/bin/activate
   ```

3. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Copia el ejemplo de configuración y edita `.env`. Configura `GEMINI_API_KEY` (o `GOOGLE_API_KEY`) y un `SECRET_KEY` aleatorio. `DATABASE_URL` es opcional para desarrollo local; sin ella se usa el almacenamiento local. Las variables SMTP son necesarias para las funciones de correo.

   En Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   En macOS o Linux:

   ```bash
   cp .env.example .env
   ```

5. Inicia el servidor de desarrollo:

   ```bash
   python xrtegazz.py
   ```

   Abre [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Configuración y privacidad

No agregues `.env`, credenciales ni datos de usuarios al repositorio. Los mensajes y sus respuestas se almacenan para conservar el historial; las solicitudes de IA y las imágenes adjuntas se procesan mediante el proveedor externo configurado. Para el despliegue con PostgreSQL y Vercel, consulta [DEPLOYMENT.md](./DEPLOYMENT.md).

## Autor

**Jean Ortega** — [GitHub @jeanortega-co](https://github.com/jeanortega-co)
