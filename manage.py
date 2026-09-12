#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    # Permite usar `vercel pull` + este archivo para correr comandos (migrate, etc.)
    # contra las variables de entorno reales del proyecto en Vercel.
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env.local')

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'restaurante.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
