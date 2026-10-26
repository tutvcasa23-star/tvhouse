"""Consulta a Claude solo cuando el usuario aprieta el botón. Manda el contexto del TV sin datos sensibles.

La clave se toma del entorno (ANTHROPIC_API_KEY o un perfil de `ant auth login`); nunca se guarda en la app.
"""
from __future__ import annotations

import json
import re

MODELO = "claude-opus-5-5"

SISTEMA = """Eres el soporte técnico de "TV Casa", una herramienta que configura los Android TV / Google TV de una casa por ADB:
desactiva apps de fábrica (nunca desinstala apps del sistema), instala un inicio limpio (Clean Your TV), pone fondo y
protector de fotos, y verifica que sigan funcionando Google Cast (puerto 8009) y el control remoto de Home Assistant (6466).
Responde en español, breve y práctico: causa probable, cómo confirmarla y pasos concretos (comandos `adb shell` si aplica).
Separa lo comprobado de lo que es hipótesis. No propongas restablecer de fábrica, ni instalar apps de fuera de la tienda,
ni desactivar paquetes del sistema, del sintonizador, de Google Play/Cast o del control remoto."""

_MAC = re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")
_TOKEN = re.compile(r"\b(eyJ[\w-]{10,}\.[\w-]+\.[\w-]+|sk-ant-[\w-]+|[A-Za-z0-9_-]{40,})\b")
_CLAVE = re.compile(r'("?(?:token|password|contraseña|clave|secret|api_key)"?\s*[:=]\s*)("[^"]*"|\S+)', re.I)


def limpiar(texto: str) -> str:
    """Quita MAC, tokens y contraseñas antes de que algo salga de la casa."""
    texto = _MAC.sub("[MAC]", texto)
    texto = _CLAVE.sub(r"\1[OCULTO]", texto)
    return _TOKEN.sub("[TOKEN]", texto)


def armar_pregunta(pregunta: str, contexto: dict | None, registro: list[str] | None) -> str:
    partes = [f"Pregunta del usuario:\n{pregunta.strip()}"]
    if contexto:
        partes.append("Estado del TV (JSON):\n" + json.dumps(contexto, ensure_ascii=False, indent=1)[:20000])
    if registro:
        partes.append("Últimas líneas del registro de la acción:\n" + "\n".join(registro[-80:]))
    return limpiar("\n\n".join(partes))


def consultar(pregunta: str, contexto: dict | None = None, registro: list[str] | None = None) -> str:
    import anthropic  # se importa aquí para que el resto de la app funcione sin la librería

    cliente = anthropic.Anthropic()
    try:
        resp = cliente.beta.messages.create(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high"},
            system=SISTEMA,
            messages=[{"role": "user", "content": armar_pregunta(pregunta, contexto, registro)}],
        )
    except anthropic.AuthenticationError:
        return "No hay una clave válida de Anthropic. Define ANTHROPIC_API_KEY antes de abrir la app (ver README)."
    except anthropic.RateLimitError:
        return "Claude está con demasiadas consultas en este momento; prueba en un minuto."
    except anthropic.APIStatusError as e:
        return f"Error de la API de Anthropic ({e.status_code}): {e.message}"
    except anthropic.APIConnectionError:
        return "Sin conexión con Anthropic. Revisa internet."
    if resp.stop_reason == "refusal":
        return "Claude no respondió esta consulta (rechazo por política). Reformúlala o pregunta en el chat."
    return "\n".join(b.text for b in resp.content if b.type == "text").strip() or "(respuesta vacía)"
