from __future__ import annotations

import queue
import threading
from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List


# Shared topic names.
TOPIC_UTTERANCE = "speech.utterance"
TOPIC_STATE_UPDATE = "state.update"
TOPIC_VISUAL_EVENT = "visual.event"
TOPIC_NOTE_EVENT = "note.event"
TOPIC_STOP = "app.stop"
TOPIC_TRANSCRIPT = "transcript"

MessageHandler = Callable[[Any], None]


class Comms:
    """Small in-process message hub.

    Supports two ways of receiving messages:
    - callback subscription via subscribe()
    - queue subscription via open_queue()

    """

    def __init__(self):
        self._lock = threading.RLock()
        self._handlers: DefaultDict[str, List[MessageHandler]] = defaultdict(list)
        self._queues: DefaultDict[str, List[queue.Queue]] = defaultdict(list)

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        with self._lock:
            if handler not in self._handlers[topic]:
                self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: MessageHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(topic)
            if not handlers:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                self._handlers.pop(topic, None)

    def open_queue(self, topic: str, maxsize: int = 0) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._queues[topic].append(q)
        return q

    def close_queue(self, topic: str, q: queue.Queue) -> None:
        with self._lock:
            queues = self._queues.get(topic)
            if not queues:
                return
            try:
                queues.remove(q)
            except ValueError:
                return
            if not queues:
                self._queues.pop(topic, None)

    def send(self, topic: str, message: Any) -> None:
        self.publish(topic, message)

    def publish(self, topic: str, message: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(topic, ()))
            queues = list(self._queues.get(topic, ()))

        for handler in handlers:
            handler(message)

        for q in queues:
            self._put_queue_drop_oldest(q, message)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
            self._queues.clear()

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            return {
                "handlers": {topic: len(items) for topic, items in self._handlers.items()},
                "queues": {topic: len(items) for topic, items in self._queues.items()},
            }

    @staticmethod
    def _put_queue_drop_oldest(q: queue.Queue, message: Any) -> None:
        if q.maxsize <= 0:
            q.put_nowait(message)
            return

        try:
            q.put_nowait(message)
            return
        except queue.Full:
            pass

        try:
            q.get_nowait()
        except queue.Empty:
            pass

        try:
            q.put_nowait(message)
        except queue.Full:
            pass
