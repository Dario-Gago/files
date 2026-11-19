# Sistema POS – Ferretería "El Tornillo"

Requisitos: Python 3.9 o superior (incluye Tkinter y SQLite; no hay que instalar nada más).

## Ejecutar
    python app_pos.py

La primera vez se crea `ferreteria.db` con datos de ejemplo.

| Usuario    | Clave     | Rol                 | Pestañas                                     |
|------------|-----------|---------------------|----------------------------------------------|
| vendedor1  | vend123   | Vendedor            | Venta                                        |
| bodega     | bodega123 | Encargado de bodega | Inventario                                   |
| dueno      | dueno123  | Dueño               | Venta, Inventario, Alertas, Reportes, Usuarios |

## Pruebas automáticas
    python -m unittest test_pos -v

## Archivos
- `pos_ferreteria.py` – lógica de negocio y base de datos (clases del diagrama UML).
- `app_pos.py` – interfaz gráfica.
- `test_pos.py` – 12 pruebas (descuento, sobreventa, alerta < 10, concurrencia, tiempo < 3 s).

## Alerta por correo (opcional)
Defina las variables de entorno `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` y `CORREO_DUENO`.
Sin ellas, la alerta igual aparece en la pestaña "Alertas" del dueño.
