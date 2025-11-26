-- Script para crear la base de datos de test para integración
-- Ejecutar como usuario postgres
DO $$
BEGIN
	IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sdn_test_database') THEN
		CREATE DATABASE sdn_test_database OWNER sdn_user;
	END IF;
END$$;
