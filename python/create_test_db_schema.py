"""
Script para crear todas las tablas en la base de datos de pruebas PostgreSQL.
"""
from database.models import Base
from database.connection import DatabaseSessionProvider, DatabaseSettings

if __name__ == "__main__":
    # Configuración para la base de datos de pruebas
    settings = DatabaseSettings(
        database="sdn_test_database",
        user="sdn_user",
        password="sdn_password",
        host="localhost",
        port=5432
    )
    provider = DatabaseSessionProvider(settings=settings)
    provider.init()
    print("Creando todas las tablas en sdn_test_database...")
    Base.metadata.create_all(provider.engine)
    print("Tablas creadas correctamente.")
