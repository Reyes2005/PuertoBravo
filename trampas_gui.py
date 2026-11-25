"""Menú de Trampas externo para Puerto Bravo: Ley del Asfalto. Punto de entrada."""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(os.path.abspath(sys.executable)))


def main():
    from trampas.ventana import ejecutar
    ejecutar()


if __name__ == "__main__":
    main()
