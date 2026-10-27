# Despliegue con Neon y Vercel

La aplicación usa JSON local solo para desarrollo. En Vercel requiere PostgreSQL compartido; el almacenamiento del filesystem de una función no es persistente ni común entre instancias.

## Preparar Neon

1. Crea un proyecto de Neon desde Vercel Marketplace o en Neon y vincúlalo al proyecto de Vercel.
2. En la configuración de variables de entorno de Vercel, configura `DATABASE_URL` con la cadena pooled de Neon (pooler habilitado), `SECRET_KEY` con un valor aleatorio estable y `GEMINI_API_KEY` con la clave del servicio de respuestas. No uses la cadena directa de conexión para `DATABASE_URL` en las funciones serverless.
3. Mantén `DATABASE_POOL_SIZE` en `2` inicialmente. Cada instancia de función puede abrir hasta ese número de conexiones; escala con las métricas y el límite del pooler, no aumentando el valor a ciegas.
4. El esquema de PostgreSQL se crea automáticamente la primera vez que la aplicación usa la base. Si necesitas importar cuentas, sesiones, mensajes u opiniones guardados localmente, ejecuta una sola vez:

   ```powershell
   $env:DATABASE_URL = "CADENA_POOLED_DE_NEON"
   .\.venv\Scripts\python.exe .\migrate_json_to_postgres.py
   ```

   Ejecuta el comando desde el equipo que tiene los archivos JSON originales. La migración es idempotente: se puede volver a ejecutar sin duplicar los registros importados.
5. Despliega la aplicación. La función tiene un máximo configurado de 60 segundos; el límite efectivo depende del plan de Vercel.

El pool local por instancia reduce aperturas repetidas, pero `DATABASE_URL` debe usar el pooler de Neon. No compartas esa URL ni `SECRET_KEY` en el repositorio.

## Verificación de correo (SMTP)

Las cuentas nuevas y las cuentas existentes deben verificar un correo antes de iniciar sesión. Las cuentas antiguas sin correo podrán asociarlo después de validar su usuario y contraseña. Configura estas variables en `.env` para desarrollo y en el panel de Vercel para producción:

- `SMTP_HOST`: servidor SMTP del proveedor.
- `SMTP_PORT`: puerto SMTP; normalmente `587` para STARTTLS o `465` para SSL.
- `SMTP_USERNAME` y `SMTP_PASSWORD`: credenciales SMTP del remitente.
- `SMTP_FROM`: dirección remitente verificada por el proveedor. La aplicación muestra automáticamente `XRTEGAZZ IA <dirección>` en el campo De; si configuras un nombre visible en esta variable, se conserva.
- `SMTP_USE_TLS`: `true` para STARTTLS (por defecto).
- `SMTP_USE_SSL`: `true` para conexión SSL directa; úsalo con `SMTP_PORT=465` en lugar de STARTTLS.

Guarda las credenciales solo como variables de entorno y no en el repositorio. La aplicación genera códigos de seis dígitos que vencen en diez minutos, limita los intentos y espera 60 segundos entre reenvíos. La opción «¿Olvidaste tu contraseña?» envía un código al correo verificado de la cuenta; el usuario puede introducirlo y establecer una contraseña nueva. La solicitud no revela si el correo está registrado. Las cuentas y las direcciones de correo se conservan en el almacenamiento configurado; códigos y estado de verificación se migran automáticamente en PostgreSQL al inicializar el esquema. Las cuentas antiguas quedan sin verificar hasta que su propietario agregue y confirme un correo.

## Capacidad

La base compartida elimina la dependencia de archivos JSON locales para cuentas, sesiones, mensajes y comentarios. Esto no garantiza por sí solo 1.000 solicitudes simultáneas: la capacidad final depende del plan y la concurrencia de Vercel, el pool de PostgreSQL, las cuotas del proveedor de respuestas y el tamaño/tiempo de espera de cada petición. Mide la carga en un entorno de pruebas y ajusta esos límites antes de anunciar una cifra de capacidad.
