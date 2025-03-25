"""
Funciones para enviar alertas mediante Telegram.
"""
import requests
import re
import time
from utils.logger import logger

def sanitize_html_message(message):
    """
    Sanitiza un mensaje HTML para Telegram.
    Garantiza que todas las etiquetas HTML estén equilibradas
    y que los símbolos < y > que no forman parte de etiquetas HTML estén escapados.
    
    Args:
        message: Contenido del mensaje
        
    Returns:
        str: Mensaje sanitizado
    """
    # Lista de etiquetas HTML permitidas por Telegram
    allowed_tags = ['b', 'strong', 'i', 'em', 'u', 's', 'strike', 'del', 'a', 'code', 'pre']
    
    # Reemplazar < con &lt; cuando no va seguido de una etiqueta válida
    message = re.sub(r'<(?!(\/?' + r'|\/?'.join(allowed_tags) + r')[>\s])', '&lt;', message)
    
    # Verificar balance de etiquetas HTML
    for tag in allowed_tags:
        # Contar etiquetas de apertura y cierre
        opened = len(re.findall(fr'<{tag}[>\s]', message))
        closed = len(re.findall(f'</{tag}>', message))
        
        # Si hay más etiquetas abiertas que cerradas, añadir los cierres faltantes
        if opened > closed:
            message += f'</{tag}>' * (opened - closed)
        
        # Si hay más etiquetas cerradas que abiertas, eliminar el exceso
        elif closed > opened:
            excess = closed - opened
            for _ in range(excess):
                pos = message.rfind(f'</{tag}>')
                if pos >= 0:
                    message = message[:pos] + message[pos + len(f'</{tag}>'):]
    
    return message

def send_telegram_alert(message, bot_token, chat_id):
    """
    Envía un mensaje de alerta vía Telegram con mejor manejo de errores.
    
    Args:
        message: Contenido del mensaje
        bot_token: Token del bot de Telegram
        chat_id: ID del chat donde enviar el mensaje
        
    Returns:
        bool: True si el envío fue exitoso, False en caso contrario
    """
    try:
        # Validar formato del token (formato básico)
        if not bot_token or not bot_token.count(':') == 1:
            print(f"❌ Error: El token del bot parece tener un formato incorrecto: {bot_token}")
            return False
            
        # Validar chat_id (debe ser un número)
        try:
            # Intentar convertir a int para validación (pero seguir usando el original)
            int(chat_id)
        except ValueError:
            print(f"❌ Error: El ID del chat no parece ser un número válido: {chat_id}")
            return False
        
        # IMPORTANTE: Sanitizar mensaje para evitar problemas con HTML
        safe_message = sanitize_html_message(message)
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": safe_message,
            "parse_mode": "HTML"  # Permite formateo HTML básico
        }
        
        print(f"Enviando mensaje a Telegram...")
        response = requests.post(url, data=payload, timeout=10)
        response_json = response.json()
        
        if response.status_code == 200 and response_json.get('ok'):
            logger.info(f"Alerta enviada al chat de Telegram {chat_id}")
            return True
        else:
            print(f"❌ Error al enviar mensaje a Telegram: {response_json}")
            logger.error(f"Error al enviar mensaje a Telegram: {response_json}")
            
            # Si falla con HTML, intentar sin formato HTML
            if 'can\'t parse entities' in str(response_json):
                print("Intentando enviar mensaje sin formato HTML...")
                # Eliminar todas las etiquetas HTML
                plain_message = re.sub(r'<[^>]*>', '', message)
                # Reemplazar entidades HTML
                plain_message = plain_message.replace('&lt;', '<').replace('&gt;', '>')
                
                payload = {
                    "chat_id": chat_id,
                    "text": plain_message
                }
                
                print("Enviando mensaje de texto plano...")
                response = requests.post(url, data=payload, timeout=10)
                response_json = response.json()
                
                if response.status_code == 200 and response_json.get('ok'):
                    logger.info(f"Alerta enviada a Telegram en texto plano")
                    return True
                else:
                    print(f"❌ Error al enviar mensaje de texto plano: {response_json}")
            
            # Mostrar información de ayuda basada en el código de error
            if response.status_code == 404:
                print("→ Error 404: Bot no encontrado. Verifica que el token sea correcto.")
            elif response.status_code == 401:
                print("→ Error 401: No autorizado. El token del bot es inválido.")
            elif response.status_code == 400:
                if 'chat not found' in str(response_json):
                    print("→ Error: Chat no encontrado. Asegúrate de que el bot y el usuario hayan intercambiado al menos un mensaje.")
                elif 'chat_id is empty' in str(response_json):
                    print("→ Error: chat_id está vacío o es inválido.")
            
            return False
    except Exception as e:
        print(f"❌ Error al enviar alerta vía Telegram: {e}")
        logger.error(f"Error al enviar alerta vía Telegram: {e}")
        return False

def send_telegram_test(test_message="Test del Sistema de Alertas de Acciones", bot_token=None, chat_id=None):
    """
    Envía un mensaje de prueba vía Telegram para verificar la configuración.
    
    Args:
        test_message: Mensaje a enviar
        bot_token: Token del bot de Telegram
        chat_id: ID del chat donde enviar el mensaje
        
    Returns:
        bool: True si el envío fue exitoso, False en caso contrario
    """
    if not bot_token or not chat_id:
        print("❌ Error: Debes proporcionar bot_token y chat_id")
        return False
    
    complete_message = f"""
🔔 <b>{test_message}</b>

Si estás viendo este mensaje, tu configuración de Telegram está funcionando correctamente.
<i>Enviado desde tu Sistema de Alertas Técnicas de Acciones</i>
"""
    
    result = send_telegram_alert(complete_message, bot_token, chat_id)
    
    if result:
        print(f"✅ Mensaje de prueba enviado correctamente a Telegram")
    else:
        print(f"❌ Error al enviar mensaje de prueba a Telegram")
    
    return result

def send_market_status_notification(market_status, bot_token, chat_id):
    """
    Envía una notificación sobre el estado actual del mercado.
    
    Args:
        market_status: Diccionario con información del estado del mercado
        bot_token: Token del bot de Telegram
        chat_id: ID del chat donde enviar el mensaje
        
    Returns:
        bool: True si el envío fue exitoso, False en caso contrario
    """
    from market.utils import is_market_open, format_time_to_market_open
    
    if is_market_open():
        status_text = "🟢 <b>MERCADO ABIERTO</b>"
        detail_text = "El mercado de valores de EE.UU. está actualmente abierto para operaciones."
    else:
        status_text = "🔴 <b>MERCADO CERRADO</b>"
        detail_text = f"El mercado de valores de EE.UU. está cerrado. {format_time_to_market_open()}"
    
    message = f"""
{status_text}
{detail_text}

<b>Resumen del Mercado:</b>
• <b>Tendencia:</b> {market_status.get('tendencia', 'No disponible')}
• <b>Volatilidad:</b> {market_status.get('volatilidad', 'No disponible')}
• <b>Recomendación:</b> {market_status.get('recomendacion', 'No disponible')}

<i>Monitoreo continuo activo - Las alertas se enviarán cuando se detecten señales.</i>
"""
    
    return send_telegram_alert(message, bot_token, chat_id)