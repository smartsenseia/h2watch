import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _serialize(data: Any) -> bytes:
    """Converte qualquer dado para bytes JSON, tratando datetime automaticamente."""
    return json.dumps(data, default=str).encode("utf-8")


class Publisher:
    """
    Helper de publicação MQTT.

    Centraliza todos os publish do sistema em métodos nomeados,
    evitando strings de tópico espalhadas pelos handlers.

    Uso dentro de um handler:
        publisher = Publisher(client)
        await publisher.measurements_list(rows)
        await publisher.error("measurements/create/response", "Timestamp inválido")
    """

    def __init__(self, client):
        """
        Args:
            client: instância do MQTTClient com método publish(topic, payload)
        """
        self._client = client

    # ── Measurements ──────────────────────────────────────────────────────

    async def measurements_list(self, rows: list[dict]) -> None:
        """Resposta para measurements/list/request"""
        await self._publish("measurements/list/response", rows)

    async def measurements_get(self, row: dict) -> None:
        """Resposta para measurements/get/request"""
        await self._publish("measurements/get/response", row)

    async def measurements_created(self, row: dict) -> None:
        """Resposta para measurements/create"""
        await self._publish("measurements/create/response", row)

    async def measurements_updated(self, row: dict) -> None:
        """Resposta para measurements/update"""
        await self._publish("measurements/update/response", row)

    async def measurements_deleted(self, detail: str) -> None:
        """Resposta para measurements/delete"""
        await self._publish("measurements/delete/response", {"detail": detail})

    # ── Erros ─────────────────────────────────────────────────────────────

    async def error(self, response_topic: str, message: str, code: int = 400) -> None:
        """
        Publica uma resposta de erro em qualquer tópico de response.

        Args:
            response_topic: tópico onde o erro será publicado
            message:        descrição do erro
            code:           código numérico opcional (equivalente ao HTTP status)
        """
        await self._publish(response_topic, {"error": message, "code": code})

    # ── Status do sistema ─────────────────────────────────────────────────

    async def heartbeat(self, asset_id: str, extra: dict | None = None) -> None:
        """
        Publica sinal de vida do sistema em 'sistema/heartbeat'.
        Útil para monitoramento externo.

        Args:
            asset_id: identificador do equipamento (ex: 'MD01BR01')
            extra:    campos adicionais opcionais (ex: versão, uptime)
        """
        payload = {
            "asset_id": asset_id,
            "timestamp": datetime.utcnow().isoformat(),
            **(extra or {}),
        }
        await self._publish("sistema/heartbeat", payload)

    # ── Baixo nível ───────────────────────────────────────────────────────

    async def raw(
        self,
        topic: str,
        data: Any,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """
        Publica diretamente em qualquer tópico sem passar por métodos nomeados.
        Use quando precisar de um tópico dinâmico (ex: f"sensor/{sensor_id}/data").

        Args:
            topic:  tópico de destino
            data:   qualquer valor serializável em JSON
            qos:    quality of service (0, 1 ou 2)
            retain: se True, o broker retém a última mensagem
        """
        await self._publish(topic, data, qos=qos, retain=retain)

    # ── Helper interno ────────────────────────────────────────────────────

    async def _publish(
        self,
        topic: str,
        data: Any,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        try:
            payload = _serialize(data)
            await self._client.publish(topic, payload, qos=qos, retain=retain)
            logger.debug("Publisher: enviado em '%s' (%d bytes)", topic, len(payload))
        except Exception as e:
            logger.error(
                "Publisher: falha ao publicar em '%s': %s", topic, e, exc_info=True
            )