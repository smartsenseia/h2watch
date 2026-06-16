import asyncio
import logging
from typing import Callable, Awaitable, Optional

from asyncio_mqtt import Client, MqttError
from app.core.config import settings

logger = logging.getLogger(__name__)

# Tipo do callback que o dispatcher vai fornecer
MessageHandler = Callable[[str, bytes], Awaitable[None]]


class MQTTClient:
    """
    Gerencia o ciclo de vida da conexão MQTT:
    - Conexão/desconexão com o broker
    - Reconexão automática com backoff exponencial
    - Subscribe em todos os tópicos registrados
    - Repasse de mensagens ao dispatcher
    """

    def __init__(self):
        self._client: Optional[Client] = None
        self._topics: list[str] = []
        self._handler: Optional[MessageHandler] = None
        self._running = False

    # ── Registro de tópicos ───────────────────────────────────────────────

    def add_topic(self, topic: str) -> None:
        """Registra um tópico para ser assinado ao conectar."""
        if topic not in self._topics:
            self._topics.append(topic)

    def add_topics(self, topics: list[str]) -> None:
        for t in topics:
            self.add_topic(t)

    # ── Context manager ───────────────────────────────────────────────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.stop()

    # ── Conexão principal ─────────────────────────────────────────────────

    async def listen(self, handler: MessageHandler) -> None:
        """
        Inicia o loop de escuta. Reconecta automaticamente em caso de falha.
        Chame dentro de asyncio.run() ou como task.

        Args:
            handler: coroutine chamada com (topic: str, payload: bytes)
                     para cada mensagem recebida.
        """
        self._handler = handler
        self._running = True
        delay = settings.MQTT_RECONNECT_DELAY_MIN

        while self._running:
            try:
                await self._connect_and_listen()
                delay = settings.MQTT_RECONNECT_DELAY_MIN  # reset após sucesso

            except MqttError as e:
                if not self._running:
                    break
                logger.warning(
                    "Conexão MQTT perdida: %s. Reconectando em %.1fs…", e, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, settings.MQTT_RECONNECT_DELAY_MAX)

            except asyncio.CancelledError:
                logger.info("Loop MQTT cancelado.")
                break

            except Exception as e:
                logger.error("Erro inesperado no loop MQTT: %s", e, exc_info=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, settings.MQTT_RECONNECT_DELAY_MAX)

    async def stop(self) -> None:
        """Sinaliza o loop para parar na próxima iteração."""
        self._running = False
        logger.info("MQTTClient: parada solicitada.")

    # ── Loop interno de conexão ───────────────────────────────────────────

    async def _connect_and_listen(self) -> None:
        logger.info(
            "Conectando ao broker MQTT em %s:%s…",
            settings.MQTT_HOST,
            settings.MQTT_PORT,
        )

        async with Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME or None,
            password=settings.MQTT_PASSWORD or None,
            keepalive=settings.MQTT_KEEPALIVE,
            client_id=settings.MQTT_CLIENT_ID or None,
        ) as client:
            self._client = client
            logger.info("Conectado ao broker MQTT.")

            # Assina todos os tópicos registrados
            for topic in self._topics:
                await client.subscribe(topic)
                logger.debug("Subscrito em: %s", topic)

            # Loop de recebimento de mensagens
            async with client.messages() as messages:
                async for message in messages:
                    if not self._running:
                        break
                    topic = str(message.topic)
                    asyncio.create_task(
                        self._safe_dispatch(topic, message.payload)
                    )

    # ── Publicação ────────────────────────────────────────────────────────

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """
        Publica uma mensagem em um tópico.

        Args:
            topic:   tópico de destino
            payload: conteúdo (str é codificado para UTF-8)
            qos:     quality of service (0, 1 ou 2)
            retain:  se True, o broker retém a última mensagem
        """
        if self._client is None:
            logger.error("publish() chamado sem conexão ativa — tópico: %s", topic)
            return

        if isinstance(payload, str):
            payload = payload.encode()

        await self._client.publish(topic, payload, qos=qos, retain=retain)
        logger.debug("Publicado em %s (%d bytes)", topic, len(payload))

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _safe_dispatch(self, topic: str, payload: bytes) -> None:
        """Executa o handler capturando exceções para não derrubar o loop."""
        try:
            await self._handler(topic, payload)
        except Exception as e:
            logger.error(
                "Erro ao processar mensagem [%s]: %s", topic, e, exc_info=True
            )