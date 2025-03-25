#!/bin/bash
# Script para inicializar el repositorio Git

# Crea los directorios necesarios
mkdir -p data logs

# Crea archivos .gitkeep para mantener directorios vacíos en git
touch data/.gitkeep
touch logs/.gitkeep

# Inicializa el repositorio Git
git init

# Primer commit con la estructura básica
git add .
git commit -m "Estructura inicial del proyecto"

echo "Repositorio Git inicializado correctamente!"
echo "Recuerda crear y configurar tu repositorio remoto:"
echo "git remote add origin https://github.com/tu-usuario/stock-alerts.git"
echo "git branch -M main"
echo "git push -u origin main"