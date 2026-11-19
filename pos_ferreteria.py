"""
Lógica de negocio del Sistema de Punto de Venta - Ferretería "El Tornillo".
Usa solo la biblioteca estándar de Python (SQLite). La interfaz gráfica está en app_pos.py.
"""
import hashlib
import os
import secrets
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ferreteria.db")
STOCK_MINIMO = 10  # RF-04: alerta cuando el stock baja de 10 unidades


class StockInsuficiente(Exception):
    def __init__(self, codigo, disponible):
        super().__init__(f"Stock insuficiente de {codigo} (disponible: {disponible})")
        self.codigo, self.disponible = codigo, disponible


class ErrorNegocio(Exception):
    pass


def _hash(clave, sal):
    return hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), 120_000).hex()


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ======================================================================
#  LÓGICA DE NEGOCIO
# ======================================================================
class Sistema:
    def __init__(self, ruta_db=DB_PATH):
        self.ruta = ruta_db
        self._crear_tablas()

    # ---------- base de datos ----------
    def _con(self):
        con = sqlite3.connect(self.ruta, timeout=15, isolation_level=None)  # transacciones manuales
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _crear_tablas(self):
        con = self._con()
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE, sal TEXT NOT NULL, clave TEXT NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('vendedor','dueno','bodega')), activo INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS productos(
            codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL, categoria TEXT, precio REAL NOT NULL CHECK(precio >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0));
        CREATE INDEX IF NOT EXISTS idx_prod_nombre ON productos(nombre);
        CREATE TABLE IF NOT EXISTS ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
            vendedor_id INTEGER NOT NULL REFERENCES usuarios(id), total REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'CONFIRMADA');
        CREATE TABLE IF NOT EXISTS detalle_venta(
            id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER NOT NULL REFERENCES ventas(id),
            codigo TEXT NOT NULL REFERENCES productos(codigo), cantidad INTEGER NOT NULL CHECK(cantidad > 0),
            precio_unitario REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS alertas(
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, codigo TEXT NOT NULL REFERENCES productos(codigo),
            stock INTEGER NOT NULL, leida INTEGER NOT NULL DEFAULT 0, activa INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS movimientos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, codigo TEXT NOT NULL,
            tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, motivo TEXT, usuario_id INTEGER);
        """)
        con.close()

    def cargar_datos_demo(self):
        """Crea usuarios y productos de ejemplo solo si la base está vacía."""
        con = self._con()
        hay = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        con.close()
        if hay:
            return
        self.crear_usuario("Dueño Ferretería", "dueno", "dueno123", "dueno")
        self.crear_usuario("Vendedor Uno", "vendedor1", "vend123", "vendedor")
        self.crear_usuario("Encargado Bodega", "bodega", "bodega123", "bodega")
        demo = [
            ("TOR-001", "Tornillo hexagonal 1/4 x 2 (caja 100)", "Fijaciones", 3990, 50),
            ("TOR-002", "Tornillo autoperforante 8 x 1 (caja 100)", "Fijaciones", 2990, 40),
            ("CLA-001", "Clavos 2 pulgadas (1 kg)", "Fijaciones", 2500, 30),
            ("HER-001", "Martillo carpintero 16 oz", "Herramientas", 8990, 15),
            ("HER-002", "Cinta métrica 5 m", "Herramientas", 4500, 25),
            ("HER-003", "Alicate universal 8 pulgadas", "Herramientas", 6990, 12),
            ("HER-004", "Destornillador plano/cruz set 6 pzas", "Herramientas", 7990, 18),
            ("PIN-001", "Pintura látex blanca 1 galón", "Pinturas", 15990, 20),
            ("PIN-002", "Brocha 3 pulgadas", "Pinturas", 2990, 35),
            ("ELE-001", "Cable eléctrico 2.5 mm (metro)", "Electricidad", 890, 200),
            ("ELE-002", "Ampolleta LED 10 W", "Electricidad", 1990, 60),
            ("PLO-001", "Llave de paso 1/2 pulgada", "Gasfitería", 5490, 14),
        ]
        for d in demo:
            self.guardar_producto(*d[:4])
            self.ajustar_stock(d[0], d[4], "Carga inicial", None, tipo="INGRESO")

    # ---------- usuarios ----------
    def crear_usuario(self, nombre, usuario, clave, rol):
        if rol not in ("vendedor", "dueno", "bodega"):
            raise ErrorNegocio("Rol inválido")
        if len(clave) < 6:
            raise ErrorNegocio("La clave debe tener al menos 6 caracteres")
        sal = secrets.token_hex(16)
        con = self._con()
        try:
            con.execute("INSERT INTO usuarios(nombre,usuario,sal,clave,rol) VALUES(?,?,?,?,?)",
                        (nombre, usuario, sal, _hash(clave, sal), rol))
        except sqlite3.IntegrityError:
            raise ErrorNegocio("Ese nombre de usuario ya existe")
        finally:
            con.close()

    def iniciar_sesion(self, usuario, clave):
        """Devuelve dict del usuario o None si las credenciales son incorrectas."""
        con = self._con()
        f = con.execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1", (usuario,)).fetchone()
        con.close()
        if f and secrets.compare_digest(f["clave"], _hash(clave, f["sal"])):
            return {"id": f["id"], "nombre": f["nombre"], "usuario": f["usuario"], "rol": f["rol"]}
        return None

    def listar_usuarios(self):
        con = self._con()
        r = [dict(x) for x in con.execute("SELECT id,nombre,usuario,rol,activo FROM usuarios ORDER BY id")]
        con.close()
        return r

    def cambiar_estado_usuario(self, usuario_id, activo):
        con = self._con()
        con.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if activo else 0, usuario_id))
        con.close()

    # ---------- productos / búsqueda (PB-02) ----------
    def guardar_producto(self, codigo, nombre, categoria, precio):
        codigo = codigo.strip().upper()
        if not codigo or not nombre.strip():
            raise ErrorNegocio("Código y nombre son obligatorios")
        if float(precio) < 0:
            raise ErrorNegocio("El precio no puede ser negativo")
        con = self._con()
        con.execute("""INSERT INTO productos(codigo,nombre,categoria,precio) VALUES(?,?,?,?)
                       ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre,
                       categoria=excluded.categoria, precio=excluded.precio""",
                    (codigo, nombre.strip(), categoria, float(precio)))
        con.close()

    def buscar_productos(self, criterio, limite=30):
        """Búsqueda por código o nombre (coincidencia parcial)."""
        c = f"%{criterio.strip()}%"
        con = self._con()
        r = [dict(x) for x in con.execute(
            "SELECT * FROM productos WHERE codigo LIKE ? OR nombre LIKE ? ORDER BY nombre LIMIT ?", (c, c, limite))]
        con.close()
        return r

    def obtener_producto(self, codigo):
        con = self._con()
        f = con.execute("SELECT * FROM productos WHERE codigo=?", (codigo.strip().upper(),)).fetchone()
        con.close()
        return dict(f) if f else None

    # ---------- ventas (PB-01, PB-03, PB-04) ----------
    def registrar_venta(self, vendedor_id, items):
        """
        items: lista de (codigo, cantidad). Operación atómica:
          valida stock -> descuenta inventario -> guarda venta -> genera alertas.
        Lanza StockInsuficiente si algún producto no alcanza (no se modifica nada).
        Devuelve el id de la venta.
        """
        if not items:
            raise ErrorNegocio("La venta no tiene productos")
        agrupado = {}
        for codigo, cant in items:
            cant = int(cant)
            if cant <= 0:
                raise ErrorNegocio("La cantidad debe ser mayor a 0")
            agrupado[codigo.strip().upper()] = agrupado.get(codigo.strip().upper(), 0) + cant

        con = self._con()
        alertas_nuevas = []
        try:
            con.execute("BEGIN IMMEDIATE")  # bloqueo de escritura: evita vender la misma unidad dos veces
            total, detalle = 0.0, []
            for codigo, cant in agrupado.items():
                p = con.execute("SELECT precio, stock FROM productos WHERE codigo=?", (codigo,)).fetchone()
                if p is None:
                    raise ErrorNegocio(f"El producto {codigo} no existe")
                cur = con.execute("UPDATE productos SET stock = stock - ? WHERE codigo=? AND stock >= ?",
                                  (cant, codigo, cant))
                if cur.rowcount == 0:
                    raise StockInsuficiente(codigo, p["stock"])
                total += p["precio"] * cant
                detalle.append((codigo, cant, p["precio"]))
            vid = con.execute("INSERT INTO ventas(fecha,vendedor_id,total) VALUES(?,?,?)",
                              (_ahora(), vendedor_id, total)).lastrowid
            for codigo, cant, precio in detalle:
                con.execute("INSERT INTO detalle_venta(venta_id,codigo,cantidad,precio_unitario) VALUES(?,?,?,?)",
                            (vid, codigo, cant, precio))
                con.execute("INSERT INTO movimientos(fecha,codigo,tipo,cantidad,motivo,usuario_id) VALUES(?,?,?,?,?,?)",
                            (_ahora(), codigo, "VENTA", -cant, f"Venta #{vid}", vendedor_id))
                a = self._evaluar_alerta(con, codigo)
                if a:
                    alertas_nuevas.append(a)
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        for a in alertas_nuevas:  # el correo se envía fuera de la transacción
            self._enviar_correo(a)
        return vid

    def anular_venta(self, venta_id, usuario_id):
        """Anula una venta y repone el stock."""
        con = self._con()
        try:
            con.execute("BEGIN IMMEDIATE")
            v = con.execute("SELECT estado FROM ventas WHERE id=?", (venta_id,)).fetchone()
            if v is None:
                raise ErrorNegocio("La venta no existe")
            if v["estado"] == "ANULADA":
                raise ErrorNegocio("La venta ya estaba anulada")
            for d in con.execute("SELECT codigo,cantidad FROM detalle_venta WHERE venta_id=?", (venta_id,)).fetchall():
                con.execute("UPDATE productos SET stock = stock + ? WHERE codigo=?", (d["cantidad"], d["codigo"]))
                con.execute("INSERT INTO movimientos(fecha,codigo,tipo,cantidad,motivo,usuario_id) VALUES(?,?,?,?,?,?)",
                            (_ahora(), d["codigo"], "ANULACION", d["cantidad"], f"Anulación venta #{venta_id}", usuario_id))
                self._resolver_alertas_si_repuesto(con, d["codigo"])
            con.execute("UPDATE ventas SET estado='ANULADA' WHERE id=?", (venta_id,))
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    # ---------- inventario (PB-07) ----------
    def ajustar_stock(self, codigo, cantidad, motivo, usuario_id, tipo="AJUSTE"):
        """
        INGRESO: suma 'cantidad' al stock.  AJUSTE: fija el stock en 'cantidad' (conteo físico).
        """
        codigo = codigo.strip().upper()
        cantidad = int(cantidad)
        if tipo == "AJUSTE" and not motivo.strip():
            raise ErrorNegocio("El ajuste de inventario exige un motivo")
        if cantidad < 0 or (tipo == "INGRESO" and cantidad == 0):
            raise ErrorNegocio("Cantidad inválida")
        con = self._con()
        alerta = None
        try:
            con.execute("BEGIN IMMEDIATE")
            p = con.execute("SELECT stock FROM productos WHERE codigo=?", (codigo,)).fetchone()
            if p is None:
                raise ErrorNegocio(f"El producto {codigo} no existe")
            nuevo = p["stock"] + cantidad if tipo == "INGRESO" else cantidad
            con.execute("UPDATE productos SET stock=? WHERE codigo=?", (nuevo, codigo))
            con.execute("INSERT INTO movimientos(fecha,codigo,tipo,cantidad,motivo,usuario_id) VALUES(?,?,?,?,?,?)",
                        (_ahora(), codigo, tipo, nuevo - p["stock"], motivo, usuario_id))
            self._resolver_alertas_si_repuesto(con, codigo)
            alerta = self._evaluar_alerta(con, codigo)
            con.execute("COMMIT")
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        if alerta:
            self._enviar_correo(alerta)

    # ---------- alertas (PB-05) ----------
    def _evaluar_alerta(self, con, codigo):
        """Genera alerta si stock < 10 y no hay otra activa para ese producto (no se repite)."""
        p = con.execute("SELECT nombre, stock FROM productos WHERE codigo=?", (codigo,)).fetchone()
        if p["stock"] >= STOCK_MINIMO:
            return None
        if con.execute("SELECT 1 FROM alertas WHERE codigo=? AND activa=1", (codigo,)).fetchone():
            return None
        con.execute("INSERT INTO alertas(fecha,codigo,stock) VALUES(?,?,?)", (_ahora(), codigo, p["stock"]))
        return {"codigo": codigo, "nombre": p["nombre"], "stock": p["stock"]}

    def _resolver_alertas_si_repuesto(self, con, codigo):
        s = con.execute("SELECT stock FROM productos WHERE codigo=?", (codigo,)).fetchone()["stock"]
        if s >= STOCK_MINIMO:
            con.execute("UPDATE alertas SET activa=0 WHERE codigo=? AND activa=1", (codigo,))

    def listar_alertas(self, solo_no_leidas=False):
        q = ("SELECT a.id,a.fecha,a.codigo,p.nombre,a.stock,a.leida,a.activa FROM alertas a "
             "JOIN productos p ON p.codigo=a.codigo")
        if solo_no_leidas:
            q += " WHERE a.leida=0"
        con = self._con()
        r = [dict(x) for x in con.execute(q + " ORDER BY a.id DESC")]
        con.close()
        return r

    def marcar_alerta_leida(self, alerta_id):
        con = self._con()
        con.execute("UPDATE alertas SET leida=1 WHERE id=?", (alerta_id,))
        con.close()

    def _enviar_correo(self, a):
        """Envía el correo solo si hay variables de entorno SMTP_HOST, SMTP_USER, SMTP_PASS y CORREO_DUENO."""
        host, user, clave, destino = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "CORREO_DUENO"))
        if not all((host, user, clave, destino)):
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Alerta de stock bajo: {a['nombre']}"
            msg["From"], msg["To"] = user, destino
            msg.set_content(f"El producto {a['codigo']} - {a['nombre']} tiene solo {a['stock']} unidades "
                            f"(mínimo {STOCK_MINIMO}). Considere reponerlo.")
            with smtplib.SMTP_SSL(host, 465, timeout=10) as s:
                s.login(user, clave)
                s.send_message(msg)
            return True
        except Exception:
            return False  # la alerta en la aplicación igual queda registrada

    # ---------- reportes (PB-09) ----------
    def reporte_ventas(self, desde, hasta):
        """Ventas confirmadas por día y vendedor entre dos fechas (AAAA-MM-DD)."""
        con = self._con()
        r = [dict(x) for x in con.execute("""
            SELECT substr(v.fecha,1,10) AS dia, u.nombre AS vendedor, COUNT(*) AS ventas, SUM(v.total) AS total
            FROM ventas v JOIN usuarios u ON u.id=v.vendedor_id
            WHERE v.estado='CONFIRMADA' AND substr(v.fecha,1,10) BETWEEN ? AND ?
            GROUP BY dia, vendedor ORDER BY dia DESC, vendedor""", (desde, hasta))]
        con.close()
        return r

    def reporte_stock_bajo(self):
        con = self._con()
        r = [dict(x) for x in con.execute(
            "SELECT codigo,nombre,stock FROM productos WHERE stock < ? ORDER BY stock", (STOCK_MINIMO,))]
        con.close()
        return r

    def listar_productos(self):
        con = self._con()
        r = [dict(x) for x in con.execute("SELECT * FROM productos ORDER BY nombre")]
        con.close()
        return r
