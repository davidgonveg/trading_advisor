# Directorio de Datos

Este directorio está destinado a almacenar los archivos de base de datos SQLite y otros archivos de datos generados por la aplicación.

## Contenido

- `stock_alerts.db` - Base de datos principal que contiene:
  - Datos históricos de precios de acciones
  - Alertas generadas
  - Indicadores técnicos calculados

## Notas Importantes

- Los archivos de base de datos (*.db) no se incluyen en el control de versiones (están en .gitignore)
- Para backup, considere exportar periódicamente la base de datos
- La base de datos se creará automáticamente al ejecutar la aplicación por primera vez

## Estructura de la Base de Datos

La base de datos contiene las siguientes tablas:

1. `datos_historicos` - Almacena datos históricos de precios e indicadores
2. `alertas` - Almacena las alertas generadas por el sistema

## Mantenimiento

Para mantener el rendimiento de la base de datos:

- Periódicamente, ejecute `VACUUM` en la base de datos SQLite
- Considere limpiar datos históricos antiguos si la base de datos crece demasiado