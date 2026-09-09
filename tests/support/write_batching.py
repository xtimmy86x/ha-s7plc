"""Controlled scheduling and coordinator creation for batch write tests."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant

from custom_components.s7plc.coordinator import S7Coordinator


class ControlledTimer:
    """Timer handle whose callback is fired explicitly by a test."""

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def fire(self):
        assert not self.cancelled
        self.callback()


class ControlledScheduler:
    """Minimal deterministic replacement for loop.call_later."""

    def __init__(self):
        self.timers: list[ControlledTimer] = []

    def call_later(self, delay, callback):
        timer = ControlledTimer(delay, callback)
        self.timers.append(timer)
        return timer


def make_batch_coordinator(*, batching=True):
    hass = HomeAssistant()
    coord = S7Coordinator(
        hass,
        host="plc.local",
        enable_write_batching=batching,
        max_retries=0,
    )
    return coord


def install_scheduler(coord):
    scheduler = ControlledScheduler()
    coord.hass.loop = scheduler
    background_tasks = []

    def create_background_task(coro, name=None):
        task = asyncio.create_task(coro, name=name)
        background_tasks.append(task)
        return task

    coord.hass.async_create_background_task = create_background_task
    return scheduler, background_tasks


async def enqueue(coord, address, value):
    task = asyncio.create_task(coord.write_batched(address, value))
    await asyncio.sleep(0)
    return task
