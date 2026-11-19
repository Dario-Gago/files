"""Pruebas automáticas del sistema POS.  Ejecutar:  python -m unittest test_pos -v"""
import os
import tempfile
import threading
import time
import unittest

from pos_ferreteria import ErrorNegocio, StockInsuficiente, Sistema


class PruebasPOS(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.sis = Sistema(os.path.join(self.dir.name, "test.db"))
        self.sis.crear_usuario("Vendedor", "v1", "clave123", "vendedor")
        self.vid = self.sis.iniciar_sesion("v1", "clave123")["id"]
        self.sis.guardar_producto("A-1", "Producto A", "Test", 1000)
        self.sis.guardar_producto("B-1", "Producto B", "Test", 500)
        self.sis.ajustar_stock("A-1", 20, "inicial", None, tipo="INGRESO")
        self.sis.ajustar_stock("B-1", 5, "inicial", None, tipo="INGRESO")

    def tearDown(self):
        self.dir.cleanup()

    def alertas_a(self):
        return [a for a in self.sis.listar_alertas() if a["codigo"] == "A-1"]

    def stock(self, cod):
        return self.sis.obtener_producto(cod)["stock"]

    # PB-01 / PB-03
    def test_venta_descuenta_inventario(self):
        self.sis.registrar_venta(self.vid, [("A-1", 3), ("a-1", 2)])  # mismo código se agrupa
        self.assertEqual(self.stock("A-1"), 15)

    # PB-04
    def test_rechaza_sobreventa_y_no_modifica_nada(self):
        with self.assertRaises(StockInsuficiente):
            self.sis.registrar_venta(self.vid, [("A-1", 2), ("B-1", 6)])  # B-1 solo tiene 5
        self.assertEqual(self.stock("A-1"), 20)  # la venta completa se revierte
        self.assertEqual(self.stock("B-1"), 5)

    def test_cantidad_invalida_y_producto_inexistente(self):
        with self.assertRaises(ErrorNegocio):
            self.sis.registrar_venta(self.vid, [("A-1", 0)])
        with self.assertRaises(ErrorNegocio):
            self.sis.registrar_venta(self.vid, [("ZZZ", 1)])
        with self.assertRaises(ErrorNegocio):
            self.sis.registrar_venta(self.vid, [])

    # PB-05
    def test_alerta_solo_bajo_10_unidades(self):
        self.sis.registrar_venta(self.vid, [("A-1", 10)])  # queda 10: NO alerta
        self.assertEqual(len(self.alertas_a()), 0)
        self.sis.registrar_venta(self.vid, [("A-1", 1)])   # queda 9: alerta
        al = self.alertas_a()
        self.assertEqual((len(al), al[0]["codigo"], al[0]["stock"]), (1, "A-1", 9))

    def test_alerta_no_se_repite_y_se_resuelve_al_reponer(self):
        self.sis.registrar_venta(self.vid, [("A-1", 12)])  # 8 -> alerta
        self.sis.registrar_venta(self.vid, [("A-1", 1)])   # 7 -> no duplica
        self.assertEqual(len(self.alertas_a()), 1)
        self.sis.ajustar_stock("A-1", 20, "reposición", None, tipo="INGRESO")  # 27 -> resuelta
        self.assertEqual(self.alertas_a()[0]["activa"], 0)
        self.sis.registrar_venta(self.vid, [("A-1", 18)])  # 9 -> nueva alerta
        self.assertEqual(len(self.alertas_a()), 2)

    def test_producto_con_stock_inicial_bajo_genera_alerta(self):
        self.assertEqual([a["codigo"] for a in self.sis.listar_alertas()], ["B-1"])  # B-1 tiene 5

    # PB-06
    def test_login_y_roles(self):
        self.assertIsNone(self.sis.iniciar_sesion("v1", "mala"))
        self.assertEqual(self.sis.iniciar_sesion("v1", "clave123")["rol"], "vendedor")
        with self.assertRaises(ErrorNegocio):
            self.sis.crear_usuario("X", "v1", "clave123", "vendedor")  # usuario repetido
        with self.assertRaises(ErrorNegocio):
            self.sis.crear_usuario("X", "x", "123", "vendedor")        # clave corta
        self.sis.cambiar_estado_usuario(self.vid, False)
        self.assertIsNone(self.sis.iniciar_sesion("v1", "clave123"))   # desactivado

    # PB-07
    def test_ajuste_exige_motivo_y_fija_stock(self):
        with self.assertRaises(ErrorNegocio):
            self.sis.ajustar_stock("A-1", 18, "  ", None, tipo="AJUSTE")
        self.sis.ajustar_stock("A-1", 18, "Conteo físico", None, tipo="AJUSTE")
        self.assertEqual(self.stock("A-1"), 18)

    def test_anular_venta_repone_stock(self):
        v = self.sis.registrar_venta(self.vid, [("A-1", 4)])
        self.sis.anular_venta(v, self.vid)
        self.assertEqual(self.stock("A-1"), 20)
        with self.assertRaises(ErrorNegocio):
            self.sis.anular_venta(v, self.vid)  # no se anula dos veces

    # PB-09
    def test_reportes(self):
        self.sis.registrar_venta(self.vid, [("A-1", 2)])
        hoy = time.strftime("%Y-%m-%d")
        r = self.sis.reporte_ventas(hoy, hoy)
        self.assertEqual((r[0]["ventas"], r[0]["total"]), (1, 2000))
        self.assertEqual([p["codigo"] for p in self.sis.reporte_stock_bajo()], ["B-1"])

    # RNF-03: 12 vendedores simultáneos compitiendo por las últimas 5 unidades
    def test_concurrencia_12_vendedores_no_vende_de_mas(self):
        self.sis.ajustar_stock("A-1", 5, "conteo", None, tipo="AJUSTE")
        exitos, fallos, errores = [], [], []

        def vender():
            try:
                self.sis.registrar_venta(self.vid, [("A-1", 1)])
                exitos.append(1)
            except StockInsuficiente:
                fallos.append(1)
            except Exception as e:  # cualquier otro error es una falla
                errores.append(e)

        hilos = [threading.Thread(target=vender) for _ in range(12)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(errores, [])
        self.assertEqual((len(exitos), len(fallos)), (5, 7))
        self.assertEqual(self.stock("A-1"), 0)

    # RNF-02: cada venta en menos de 3 segundos
    def test_rendimiento_menos_de_3_segundos(self):
        self.sis.ajustar_stock("A-1", 500, "stock para prueba", None, tipo="INGRESO")
        tiempos = []
        for _ in range(50):
            t0 = time.perf_counter()
            self.sis.registrar_venta(self.vid, [("A-1", 1)])
            tiempos.append(time.perf_counter() - t0)
        print(f"\n  Promedio: {sum(tiempos)/50*1000:.1f} ms | máximo: {max(tiempos)*1000:.1f} ms")
        self.assertLess(max(tiempos), 3.0)


if __name__ == "__main__":
    unittest.main()
