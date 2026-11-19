"""
Interfaz gráfica (Tkinter) del Sistema de Punto de Venta - Ferretería "El Tornillo".

Ejecutar:  python app_pos.py
Usuarios de demostración (cámbielos antes de usar en serio):
    dueno / dueno123      vendedor1 / vend123      bodega / bodega123
"""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from pos_ferreteria import ErrorNegocio, STOCK_MINIMO, StockInsuficiente, Sistema


# ======================================================================
#  INTERFAZ GRÁFICA
# ======================================================================
def pesos(n):
    return "$" + f"{n:,.0f}".replace(",", ".")


class App(tk.Tk):
    def __init__(self, sistema):
        super().__init__()
        self.sis = sistema
        self.usuario = None
        self.title("POS - Ferretería El Tornillo")
        self.geometry("980x640")
        self.minsize(900, 560)
        ttk.Style(self).configure("Grande.TButton", font=("Arial", 13, "bold"), padding=8)
        ttk.Style(self).configure("Treeview", rowheight=26, font=("Arial", 11))
        self.mostrar_login()

    def limpiar(self):
        for w in self.winfo_children():
            w.destroy()

    # ---------- login ----------
    def mostrar_login(self):
        self.limpiar()
        self.usuario = None
        f = ttk.Frame(self, padding=40)
        f.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(f, text="Ferretería El Tornillo", font=("Arial", 22, "bold")).grid(columnspan=2, pady=(0, 4))
        ttk.Label(f, text="Sistema de Punto de Venta", font=("Arial", 12)).grid(columnspan=2, pady=(0, 20))
        ttk.Label(f, text="Usuario:", font=("Arial", 12)).grid(row=2, column=0, sticky="e", pady=6)
        ttk.Label(f, text="Clave:", font=("Arial", 12)).grid(row=3, column=0, sticky="e", pady=6)
        self.e_user, self.e_pass = ttk.Entry(f, font=("Arial", 12), width=24), ttk.Entry(f, font=("Arial", 12), width=24, show="*")
        self.e_user.grid(row=2, column=1, padx=8)
        self.e_pass.grid(row=3, column=1, padx=8)
        ttk.Button(f, text="INGRESAR", style="Grande.TButton", command=self.hacer_login).grid(columnspan=2, pady=20, sticky="ew")
        self.e_pass.bind("<Return>", lambda e: self.hacer_login())
        self.e_user.focus()

    def hacer_login(self):
        u = self.sis.iniciar_sesion(self.e_user.get().strip(), self.e_pass.get())
        if not u:
            messagebox.showerror("Acceso denegado", "Usuario o clave incorrectos.")
            return
        self.usuario = u
        self.mostrar_principal()

    # ---------- ventana principal por rol ----------
    def mostrar_principal(self):
        self.limpiar()
        barra = tk.Frame(self, bg="#1F4E79")
        barra.pack(fill="x")
        tk.Label(barra, text=f"  Ferretería El Tornillo   |   {self.usuario['nombre']} ({self.usuario['rol']})",
                 bg="#1F4E79", fg="white", font=("Arial", 12, "bold")).pack(side="left", pady=8)
        ttk.Button(barra, text="Cerrar sesión", command=self.mostrar_login).pack(side="right", padx=8, pady=4)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        rol = self.usuario["rol"]
        if rol in ("vendedor", "dueno"):
            nb.add(self._tab_venta(nb), text="  Venta  ")
        if rol in ("bodega", "dueno"):
            nb.add(self._tab_inventario(nb), text="  Inventario  ")
        if rol == "dueno":
            nb.add(self._tab_alertas(nb), text="  Alertas  ")
            nb.add(self._tab_reportes(nb), text="  Reportes  ")
            nb.add(self._tab_usuarios(nb), text="  Usuarios  ")

    # ---------- pestaña venta ----------
    def _tab_venta(self, nb):
        t = ttk.Frame(nb, padding=10)
        self.carrito = []  # [(codigo, nombre, cant, precio)]
        top = ttk.Frame(t)
        top.pack(fill="x")
        ttk.Label(top, text="Buscar producto (código o nombre):", font=("Arial", 12)).pack(side="left")
        self.e_buscar = ttk.Entry(top, font=("Arial", 13), width=30)
        self.e_buscar.pack(side="left", padx=8)
        self.e_buscar.bind("<KeyRelease>", lambda e: self._buscar())
        ttk.Label(top, text="Cantidad:", font=("Arial", 12)).pack(side="left")
        self.e_cant = ttk.Spinbox(top, from_=1, to=9999, width=6, font=("Arial", 13))
        self.e_cant.set(1)
        self.e_cant.pack(side="left", padx=6)
        ttk.Button(top, text="AGREGAR", style="Grande.TButton", command=self._agregar).pack(side="left", padx=6)

        self.t_res = ttk.Treeview(t, columns=("cod", "nom", "pre", "stk"), show="headings", height=5)
        for c, h, w in (("cod", "Código", 90), ("nom", "Producto", 420), ("pre", "Precio", 100), ("stk", "Stock", 80)):
            self.t_res.heading(c, text=h)
            self.t_res.column(c, width=w, anchor="w" if c == "nom" else "center")
        self.t_res.pack(fill="x", pady=8)
        self.t_res.bind("<Double-1>", lambda e: self._agregar())

        self.t_car = ttk.Treeview(t, columns=("cod", "nom", "cant", "pre", "sub"), show="headings", height=8)
        for c, h, w in (("cod", "Código", 90), ("nom", "Producto", 380), ("cant", "Cant.", 70), ("pre", "Precio", 100), ("sub", "Subtotal", 110)):
            self.t_car.heading(c, text=h)
            self.t_car.column(c, width=w, anchor="w" if c == "nom" else "center")
        self.t_car.pack(fill="both", expand=True)

        pie = ttk.Frame(t)
        pie.pack(fill="x", pady=8)
        ttk.Button(pie, text="Quitar seleccionado", command=self._quitar).pack(side="left")
        self.l_total = ttk.Label(pie, text="TOTAL: $0", font=("Arial", 18, "bold"))
        self.l_total.pack(side="right", padx=10)
        ttk.Button(pie, text="CONFIRMAR VENTA", style="Grande.TButton", command=self._confirmar).pack(side="right", padx=10)
        self._buscar()
        return t

    def _buscar(self):
        self.t_res.delete(*self.t_res.get_children())
        for p in self.sis.buscar_productos(self.e_buscar.get()):
            self.t_res.insert("", "end", iid=p["codigo"], values=(p["codigo"], p["nombre"], pesos(p["precio"]), p["stock"]))

    def _agregar(self):
        sel = self.t_res.selection()
        if not sel:
            messagebox.showinfo("Agregar", "Seleccione un producto de la lista.")
            return
        try:
            cant = int(self.e_cant.get())
            if cant <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Cantidad", "Ingrese una cantidad válida (número entero mayor a 0).")
            return
        p = self.sis.obtener_producto(sel[0])
        ya = sum(c[2] for c in self.carrito if c[0] == p["codigo"])
        if ya + cant > p["stock"]:
            messagebox.showwarning("Stock insuficiente", f"Solo quedan {p['stock']} unidades de «{p['nombre']}».")
            return
        self.carrito.append((p["codigo"], p["nombre"], cant, p["precio"]))
        self._refrescar_carrito()

    def _quitar(self):
        sel = self.t_car.selection()
        if sel:
            del self.carrito[int(sel[0])]
            self._refrescar_carrito()

    def _refrescar_carrito(self):
        self.t_car.delete(*self.t_car.get_children())
        total = 0
        for i, (cod, nom, cant, pre) in enumerate(self.carrito):
            self.t_car.insert("", "end", iid=str(i), values=(cod, nom, cant, pesos(pre), pesos(cant * pre)))
            total += cant * pre
        self.l_total.config(text=f"TOTAL: {pesos(total)}")

    def _confirmar(self):
        if not self.carrito:
            messagebox.showinfo("Venta", "Agregue al menos un producto.")
            return
        try:
            vid = self.sis.registrar_venta(self.usuario["id"], [(c[0], c[2]) for c in self.carrito])
        except StockInsuficiente as e:
            messagebox.showerror("Stock insuficiente", f"No hay stock suficiente de {e.codigo}.\nDisponible: {e.disponible}")
            self._buscar()
            return
        except ErrorNegocio as e:
            messagebox.showerror("Venta", str(e))
            return
        messagebox.showinfo("Venta registrada", f"Venta N° {vid} registrada.\nTotal: {self.l_total.cget('text')[7:]}")
        self.carrito = []
        self._refrescar_carrito()
        self._buscar()

    # ---------- pestaña inventario ----------
    def _tab_inventario(self, nb):
        t = ttk.Frame(nb, padding=10)
        self.t_inv = ttk.Treeview(t, columns=("cod", "nom", "cat", "pre", "stk"), show="headings", height=14)
        for c, h, w in (("cod", "Código", 90), ("nom", "Producto", 380), ("cat", "Categoría", 120), ("pre", "Precio", 90), ("stk", "Stock", 70)):
            self.t_inv.heading(c, text=h)
            self.t_inv.column(c, width=w, anchor="w" if c == "nom" else "center")
        self.t_inv.tag_configure("bajo", background="#FDECEA")
        self.t_inv.pack(fill="both", expand=True)
        f = ttk.Frame(t)
        f.pack(fill="x", pady=8)
        ttk.Label(f, text="Cantidad:").pack(side="left")
        self.e_inv_cant = ttk.Entry(f, width=8)
        self.e_inv_cant.pack(side="left", padx=4)
        ttk.Label(f, text="Motivo:").pack(side="left")
        self.e_inv_mot = ttk.Entry(f, width=28)
        self.e_inv_mot.pack(side="left", padx=4)
        ttk.Button(f, text="Ingresar mercadería (+)", command=lambda: self._mov("INGRESO")).pack(side="left", padx=4)
        ttk.Button(f, text="Ajustar a conteo físico", command=lambda: self._mov("AJUSTE")).pack(side="left", padx=4)
        self._refrescar_inv()
        return t

    def _refrescar_inv(self):
        self.t_inv.delete(*self.t_inv.get_children())
        for p in self.sis.listar_productos():
            self.t_inv.insert("", "end", iid=p["codigo"], tags=("bajo",) if p["stock"] < STOCK_MINIMO else (),
                              values=(p["codigo"], p["nombre"], p["categoria"], pesos(p["precio"]), p["stock"]))

    def _mov(self, tipo):
        sel = self.t_inv.selection()
        if not sel:
            messagebox.showinfo("Inventario", "Seleccione un producto.")
            return
        try:
            self.sis.ajustar_stock(sel[0], self.e_inv_cant.get(), self.e_inv_mot.get() or "Ingreso de mercadería",
                                   self.usuario["id"], tipo=tipo)
        except (ErrorNegocio, ValueError) as e:
            messagebox.showerror("Inventario", str(e) if isinstance(e, ErrorNegocio) else "Ingrese una cantidad numérica.")
            return
        self._refrescar_inv()

    # ---------- pestaña alertas ----------
    def _tab_alertas(self, nb):
        t = ttk.Frame(nb, padding=10)
        ttk.Label(t, text=f"Alertas de stock bajo (menos de {STOCK_MINIMO} unidades)", font=("Arial", 13, "bold")).pack(anchor="w")
        self.t_al = ttk.Treeview(t, columns=("id", "fecha", "cod", "nom", "stk", "est"), show="headings", height=14)
        for c, h, w in (("id", "N°", 50), ("fecha", "Fecha", 150), ("cod", "Código", 90), ("nom", "Producto", 340), ("stk", "Stock", 70), ("est", "Estado", 110)):
            self.t_al.heading(c, text=h)
            self.t_al.column(c, width=w, anchor="w" if c == "nom" else "center")
        self.t_al.tag_configure("nueva", background="#FFF3CD")
        self.t_al.pack(fill="both", expand=True, pady=8)
        f = ttk.Frame(t)
        f.pack(fill="x")
        ttk.Button(f, text="Marcar como leída", command=self._leer_alerta).pack(side="left")
        ttk.Button(f, text="Actualizar", command=self._refrescar_alertas).pack(side="left", padx=8)
        self._refrescar_alertas()
        return t

    def _refrescar_alertas(self):
        self.t_al.delete(*self.t_al.get_children())
        for a in self.sis.listar_alertas():
            est = "Nueva" if not a["leida"] else ("Pendiente" if a["activa"] else "Resuelta")
            self.t_al.insert("", "end", iid=str(a["id"]), tags=("nueva",) if not a["leida"] else (),
                             values=(a["id"], a["fecha"], a["codigo"], a["nombre"], a["stock"], est))

    def _leer_alerta(self):
        sel = self.t_al.selection()
        if sel:
            self.sis.marcar_alerta_leida(int(sel[0]))
            self._refrescar_alertas()

    # ---------- pestaña reportes ----------
    def _tab_reportes(self, nb):
        t = ttk.Frame(nb, padding=10)
        f = ttk.Frame(t)
        f.pack(fill="x")
        hoy = datetime.now().strftime("%Y-%m-%d")
        ttk.Label(f, text="Desde (AAAA-MM-DD):").pack(side="left")
        self.e_desde = ttk.Entry(f, width=12)
        self.e_desde.insert(0, hoy[:8] + "01")
        self.e_desde.pack(side="left", padx=4)
        ttk.Label(f, text="Hasta:").pack(side="left")
        self.e_hasta = ttk.Entry(f, width=12)
        self.e_hasta.insert(0, hoy)
        self.e_hasta.pack(side="left", padx=4)
        ttk.Button(f, text="Generar reporte", command=self._reporte).pack(side="left", padx=8)
        self.t_rep = ttk.Treeview(t, columns=("dia", "ven", "n", "tot"), show="headings", height=9)
        for c, h, w in (("dia", "Día", 110), ("ven", "Vendedor", 260), ("n", "N° ventas", 90), ("tot", "Total vendido", 130)):
            self.t_rep.heading(c, text=h)
            self.t_rep.column(c, width=w, anchor="center")
        self.t_rep.pack(fill="both", expand=True, pady=8)
        self.l_rep = ttk.Label(t, text="", font=("Arial", 11, "bold"))
        self.l_rep.pack(anchor="w")
        ttk.Label(t, text="Productos con stock bajo:", font=("Arial", 11, "bold")).pack(anchor="w", pady=(8, 0))
        self.l_bajo = ttk.Label(t, text="", wraplength=900, justify="left")
        self.l_bajo.pack(anchor="w")
        self._reporte()
        return t

    def _reporte(self):
        self.t_rep.delete(*self.t_rep.get_children())
        filas = self.sis.reporte_ventas(self.e_desde.get().strip(), self.e_hasta.get().strip())
        for r in filas:
            self.t_rep.insert("", "end", values=(r["dia"], r["vendedor"], r["ventas"], pesos(r["total"])))
        self.l_rep.config(text=f"Total del período: {pesos(sum(r['total'] for r in filas))}")
        bajo = self.sis.reporte_stock_bajo()
        self.l_bajo.config(text=", ".join(f"{p['nombre']} ({p['stock']})" for p in bajo) or "Ninguno")

    # ---------- pestaña usuarios ----------
    def _tab_usuarios(self, nb):
        t = ttk.Frame(nb, padding=10)
        self.t_us = ttk.Treeview(t, columns=("id", "nom", "usr", "rol", "act"), show="headings", height=8)
        for c, h, w in (("id", "ID", 50), ("nom", "Nombre", 260), ("usr", "Usuario", 140), ("rol", "Rol", 110), ("act", "Activo", 70)):
            self.t_us.heading(c, text=h)
            self.t_us.column(c, width=w, anchor="center")
        self.t_us.pack(fill="x")
        ttk.Button(t, text="Activar / desactivar seleccionado", command=self._toggle_usuario).pack(anchor="w", pady=6)
        lf = ttk.LabelFrame(t, text="Nuevo usuario", padding=8)
        lf.pack(fill="x", pady=8)
        self.nu = {}
        for i, (k, lbl) in enumerate((("nombre", "Nombre"), ("usuario", "Usuario"), ("clave", "Clave (mín. 6)"))):
            ttk.Label(lf, text=lbl).grid(row=0, column=i * 2, padx=4)
            self.nu[k] = ttk.Entry(lf, width=18, show="*" if k == "clave" else "")
            self.nu[k].grid(row=0, column=i * 2 + 1, padx=4)
        self.nu["rol"] = ttk.Combobox(lf, values=("vendedor", "dueno", "bodega"), state="readonly", width=10)
        self.nu["rol"].set("vendedor")
        self.nu["rol"].grid(row=0, column=6, padx=4)
        ttk.Button(lf, text="Crear", command=self._crear_usuario).grid(row=0, column=7, padx=8)
        self._refrescar_usuarios()
        return t

    def _refrescar_usuarios(self):
        self.t_us.delete(*self.t_us.get_children())
        for u in self.sis.listar_usuarios():
            self.t_us.insert("", "end", iid=str(u["id"]), values=(u["id"], u["nombre"], u["usuario"], u["rol"], "Sí" if u["activo"] else "No"))

    def _toggle_usuario(self):
        sel = self.t_us.selection()
        if not sel:
            return
        uid = int(sel[0])
        if uid == self.usuario["id"]:
            messagebox.showwarning("Usuarios", "No puede desactivar su propia cuenta.")
            return
        actual = self.t_us.item(sel[0], "values")[4] == "Sí"
        self.sis.cambiar_estado_usuario(uid, not actual)
        self._refrescar_usuarios()

    def _crear_usuario(self):
        try:
            self.sis.crear_usuario(self.nu["nombre"].get().strip(), self.nu["usuario"].get().strip(),
                                   self.nu["clave"].get(), self.nu["rol"].get())
        except ErrorNegocio as e:
            messagebox.showerror("Usuarios", str(e))
            return
        for k in ("nombre", "usuario", "clave"):
            self.nu[k].delete(0, "end")
        self._refrescar_usuarios()


if __name__ == "__main__":
    sistema = Sistema()
    sistema.cargar_datos_demo()
    App(sistema).mainloop()
