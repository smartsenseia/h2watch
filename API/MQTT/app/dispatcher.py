import json
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# Tipo do handler: recebe (client, payload_dict) e retorna coroutine
HandlerFn = Callable[..., Awaitable[None]]


class Dispatcher:
    """
    Roteia mensagens MQTT para os handlers registrados.

    Suporta dois estilos de tópico:
    - Exato:    "measurements/create"   → handler único
    - Wildcard: "measurements/#"        → handler para qualquer subtópico

    Uso:
        dispatcher = Dispatcher()
        dispatcher.register("measurements/create", handle_create)
        dispatcher.register("sensor/#", handle_sensor)

        # No MQTTClient:
        await client.listen(dispatcher.dispatch)
    """

    def __init__(self):
        # tópicos exatos  → handler
        self._exact: dict[str, HandlerFn] = {}
        # prefixos (#)    → handler  (chave sem o '/#' final)
        self._wildcards: dict[str, HandlerFn] = {}

    # ── Registro ──────────────────────────────────────────────────────────

    def register(self, topic: str, handler: HandlerFn) -> None:
        """
        Associa um tópico (exato ou com wildcard '#') a um handler.

        Args:
            topic:   ex: "measurements/create" ou "sensor/#"
            handler: coroutine async def handler(client, payload: dict)
        """
        if topic.endswith("/#"):
            prefix = topic[:-2]  # remove '/#'
            self._wildcards[prefix] = handler
            logger.debug("Dispatcher: wildcard registrado '%s'", topic)
        else:
            self._exact[topic] = handler
            logger.debug("Dispatcher: tópico registrado '%s'", topic)

    @property
    def handlers(self) -> dict[str, HandlerFn]:
        """
        Retorna todos os tópicos registrados no formato que o MQTTClient
        usa para fazer subscribe (wildcards recompostos com '/#').
        """
        result = dict(self._exact)
        for prefix in self._wildcards:
            result[f"{prefix}/#"] = self._wildcards[prefix]
        return result

    # ── Despacho ──────────────────────────────────────────────────────────

    async def dispatch(self, client, topic: str, payload: bytes) -> None:
        """
        Chamado pelo MQTTClient a cada mensagem recebida.

        Resolve o handler pelo tópico (exato primeiro, wildcard depois),
        decodifica o payload como JSON e invoca o handler.

        Args:
            client:  instância do MQTTClient (repassada ao handler)
            topic:   tópico da mensagem recebida
            payload: bytes recebidos do broker
        """
        handler = self._resolve(topic)

        if handler is None:
            logger.warning("Dispatcher: nenhum handler para tópico '%s'", topic)
            return

        parsed = self._parse(topic, payload)

        logger.debug("Dispatcher: %s → %s", topic, handler.__name__)

        try:
            await handler(client, parsed)
        except Exception as e:
            logger.error(
                "Dispatcher: erro no handler '%s' [%s]: %s",
                handler.__name__, topic, e,
                exc_info=True,
            )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve(self, topic: str) -> HandlerFn | None:
        """Tópico exato tem prioridade sobre wildcard."""
        if topic in self._exact:
            return self._exact[topic]

        # Verifica wildcards: "sensor/#" cobre "sensor/temp", "sensor/umidade", etc.
        for prefix, handler in self._wildcards.items():
            if topic.startswith(prefix + "/"):
                return handler

        return None

    def _parse(self, topic: str, payload: bytes) -> dict:
        """
        Decodifica payload de bytes → dict.
        Payload vazio ou inválido retorna {} sem derrubar o dispatcher.
        """
        if not payload:
            return {}

        try:
            return json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(
                "Dispatcher: payload inválido no tópico '%s': %s", topic, e
            )
            return {}